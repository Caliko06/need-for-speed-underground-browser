"""Fast On-Demand REA engine: instant IAT/string anchors, C-speed .text xrefs, and 20ms single-function lift."""
from __future__ import annotations

import bisect
import re
import struct
import threading
import time
from pathlib import Path
from typing import Any

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

from recomp_kit.arch.x86_32.lifter import Lifter
from recomp_kit.config import ProjectConfig
from recomp_kit.patcher import PatchSet, load_patches
from recomp_kit.re.callgraph import IMPLEMENTED_APIS

_CACHE_LOCK = threading.Lock()
_PE_CACHE: dict[tuple[str, float], dict[str, Any]] = {}

_PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{5,120}\x00")

_CAT_DLLS = {
    "graphics": ("d3d9", "d3d8", "d3dx", "ddraw", "opengl32", "dxgi", "d3d11", "gdi32"),
    "audio": ("dsound", "xaudio", "winmm", "openal", "fmod", "binkw32", "miles", "mss32"),
    "input": ("dinput8", "dinput", "xinput"),
    "net": ("ws2_32", "wsock32", "wininet", "winhttp"),
}

_CAT_APIS = {
    "graphics": ("Direct3D", "D3D", "CreateDevice", "BitBlt", "StretchDIBits", "wgl"),
    "audio": ("DirectSound", "waveOut", "midiOut", "timeGetTime", "XAudio"),
    "input": ("DirectInput", "XInput", "GetAsyncKeyState", "GetKeyState", "GetCursorPos", "SetCursorPos"),
    "window": ("CreateWindow", "RegisterClass", "PeekMessage", "GetMessage", "DispatchMessage", "ShowWindow", "SetWindowLong", "DefWindowProc"),
    "files": ("CreateFile", "ReadFile", "WriteFile", "SetFilePointer", "FindFirstFile", "fopen", "fread", "DeleteFile"),
    "net": ("WSAStartup", "socket", "connect", "send", "recv", "InternetOpen"),
}


def _classify_api(dll: str, name: str) -> str:
    dl = dll.lower()
    for cat, prefixes in _CAT_DLLS.items():
        if any(dl.startswith(p) for p in prefixes):
            return cat
    for cat, prefixes in _CAT_APIS.items():
        if any(name.startswith(p) for p in prefixes):
            return cat
    return "os"


def _get_cached_pe(cfg: ProjectConfig) -> dict[str, Any]:
    binary = cfg.resolve_binary()
    st = binary.stat()
    key = (str(binary), st.st_mtime)
    with _CACHE_LOCK:
        hit = _PE_CACHE.get(key)
        if hit is not None:
            return hit

    t0 = time.monotonic()
    pe = pefile.PE(str(binary), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytearray(pe.get_memory_mapped_image())
    patch_toml = getattr(cfg, "patches_toml", None)
    patch_set = load_patches(patch_toml) if patch_toml and patch_toml.is_file() else PatchSet()
    if patch_set.code_area[1] > base + len(img):
        img += bytes(patch_set.code_area[1] - base - len(img))
    patch_set.apply(img, base)

    wanted = set(cfg.code_sections or [".text"])
    code_secs: list[dict[str, Any]] = []
    data_secs: list[dict[str, Any]] = []
    for s in pe.sections:
        nm = s.Name.rstrip(b"\0").decode("latin1", "replace")
        va = base + s.VirtualAddress
        vsize = max(s.Misc_VirtualSize, s.SizeOfRawData)
        raw = bytes(img[s.VirtualAddress : s.VirtualAddress + vsize])
        rec = {"name": nm, "va": va, "size": len(raw), "raw": raw}
        if nm in wanted:
            code_secs.append(rec)
        elif nm.lower() not in (".rsrc", ".reloc", ".securom"):
            data_secs.append(rec)
    if not code_secs:
        for s in pe.sections:
            if s.Characteristics & 0x20000000:
                nm = s.Name.rstrip(b"\0").decode("latin1", "replace")
                va = base + s.VirtualAddress
                raw = bytes(img[s.VirtualAddress : s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)])
                code_secs.append({"name": nm, "va": va, "size": len(raw), "raw": raw})

    iat_by_va: dict[int, dict[str, Any]] = {}
    imports: list[dict[str, Any]] = []
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            dll = e.dll.decode("ascii", "replace")
            for imp in e.imports:
                nm = imp.name.decode("ascii", "replace") if imp.name else f"ord_{imp.ordinal}"
                cat = _classify_api(dll, nm)
                rec = {
                    "va": f"0x{imp.address:08x}",
                    "va_int": imp.address,
                    "dll": dll,
                    "name": nm,
                    "category": cat,
                    "implemented": (dll.lower(), nm) in IMPLEMENTED_APIS,
                    "kind": "import",
                }
                iat_by_va[imp.address] = rec
                imports.append(rec)

    # Lightweight Lifter instance (skips 40 MB addr_taken scan so single-function lift takes ~15ms)
    lf = Lifter.__new__(Lifter)
    lf.pe = pe
    lf.base = base
    lf.img = img
    lf.patch_set = patch_set
    lf.code_area = patch_set.code_area
    lf.native_overrides = set()
    lf.t0 = min((s["va"] for s in code_secs), default=base)
    lf.t1 = max((s["va"] + s["size"] for s in code_secs), default=base + len(img))
    lf.md = Cs(CS_ARCH_X86, CS_MODE_32)
    lf.md.detail = True
    lf.funcs = {}
    lf.iat = set(iat_by_va.keys())
    lf._cache = {}
    lf.trace = False
    lf.addr_taken = set()
    lf.addr_taken_aligned = set()

    # Optional sorted function starts from functions.tsv (if discover was run earlier)
    func_starts: list[int] = []
    if cfg.functions_tsv.exists():
        try:
            func_starts = sorted(
                int(ln.split()[0], 16)
                for ln in cfg.functions_tsv.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            )
        except Exception:
            func_starts = []

    entry = {
        "binary": binary.name,
        "base": base,
        "entry_point": base + pe.OPTIONAL_HEADER.AddressOfEntryPoint,
        "img": img,
        "code_secs": code_secs,
        "data_secs": data_secs,
        "imports": imports,
        "iat_by_va": iat_by_va,
        "lifter": lf,
        "lifter_lock": threading.Lock(),
        "func_starts": func_starts,
        "load_ms": round((time.monotonic() - t0) * 1000.0, 1),
    }
    with _CACHE_LOCK:
        # Keep cache small (max 3 binaries in RAM)
        if len(_PE_CACHE) >= 3:
            _PE_CACHE.pop(next(iter(_PE_CACHE)))
        _PE_CACHE[key] = entry
    return entry


def _extract_anchor_strings(pe_info: dict[str, Any], query: str = "", limit: int = 40) -> list[dict[str, Any]]:
    ql = query.strip().lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sec in pe_info["data_secs"]:
        raw = sec["raw"]
        base_va = sec["va"]
        for m in _PRINTABLE_RE.finditer(raw):
            txt = m.group(0)[:-1].decode("ascii", "replace")
            if not any(c.isalpha() for c in txt):
                continue
            if ql and ql not in txt.lower():
                continue
            if not ql and len(txt) < 7:
                continue
            if txt in seen:
                continue
            seen.add(txt)
            va = base_va + m.start()
            out.append({
                "va": f"0x{va:08x}",
                "va_int": va,
                "dll": sec["name"],
                "name": txt,
                "category": "strings",
                "implemented": False,
                "kind": "string",
            })
            if len(out) >= limit:
                return out
    return out


def scan_anchors(
    cfg: ProjectConfig,
    category: str = "all",
    query: str = "",
    limit: int = 60,
) -> dict[str, Any]:
    """Return high-signal RE anchors (Imports by subsystem + Strings) in <0.3s."""
    t0 = time.monotonic()
    pe_info = _get_cached_pe(cfg)
    imports = pe_info["imports"]

    counts: dict[str, int] = {"graphics": 0, "audio": 0, "input": 0, "window": 0, "files": 0, "net": 0, "os": 0}
    for imp in imports:
        counts[imp["category"]] = counts.get(imp["category"], 0) + 1

    cat = (category or "all").lower()
    ql = query.strip().lower()
    items: list[dict[str, Any]] = []

    if cat == "strings":
        items = _extract_anchor_strings(pe_info, query=ql, limit=limit)
    else:
        for imp in imports:
            if cat != "all" and imp["category"] != cat:
                continue
            if cat == "all" and not ql and imp["category"] == "os":
                # Keep default "all" view focused on high-signal subsystems first
                continue
            if ql and ql not in imp["name"].lower() and ql not in imp["dll"].lower():
                continue
            items.append(imp)
            if len(items) >= limit:
                break
        if (cat == "all" and ql and len(items) < limit) or (cat == "all" and not items):
            items.extend(_extract_anchor_strings(pe_info, query=ql, limit=max(10, limit - len(items))))

    return {
        "binary": pe_info["binary"],
        "entry_point": f"0x{pe_info['entry_point']:08x}",
        "counts": counts,
        "total_imports": len(imports),
        "category": cat,
        "query": query,
        "items": items[:limit],
        "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 1),
    }


def _guess_func_start(pe_info: dict[str, Any], sec_raw: bytes, sec_va: int, hit_off: int) -> int:
    hit_va = sec_va + hit_off
    starts = pe_info["func_starts"]
    if starts:
        idx = bisect.bisect_right(starts, hit_va) - 1
        if idx >= 0 and 0 <= hit_va - starts[idx] <= 0x4000:
            return starts[idx]

    # Fast backward scan for standard MSVC / x86-32 prologues or CC/90 padding
    lo = max(0, hit_off - 512)
    win = sec_raw[lo:hit_off]
    # Prefer `55 8b ec` (push ebp; mov ebp, esp) or `55 89 e5`
    for pat in (b"\x55\x8b\xec", b"\x55\x89\xe5"):
        pos = win.rfind(pat)
        if pos != -1:
            return sec_va + lo + pos
    # Otherwise look for `cc cc` (int3 padding between functions)
    pos = win.rfind(b"\xcc\xcc")
    if pos != -1:
        p = lo + pos + 2
        while p < hit_off and sec_raw[p] == 0xCC:
            p += 1
        if p < hit_off:
            return sec_va + p
    return hit_va


def find_xrefs_to_va(cfg: ProjectConfig, target_va: int, limit: int = 40) -> dict[str, Any]:
    """C-speed little-endian VA scan across .text to find real call sites & string refs in ~15ms."""
    t0 = time.monotonic()
    pe_info = _get_cached_pe(cfg)
    needle = struct.pack("<I", target_va)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    hits: list[dict[str, Any]] = []
    seen_funcs: set[int] = set()

    for sec in pe_info["code_secs"]:
        raw = sec["raw"]
        sec_va = sec["va"]
        pos = 0
        while len(hits) < limit:
            idx = raw.find(needle, pos)
            if idx == -1:
                break
            pos = idx + 1
            # Back up 1..4 bytes to decode the instruction containing the 32-bit immediate/disp
            insn_text = ""
            hit_va = sec_va + idx
            for back in (2, 1, 3, 4):
                if idx - back < 0:
                    continue
                chunk = raw[idx - back : idx + 8]
                insns = list(md.disasm(chunk, sec_va + idx - back, count=1))
                if insns and insns[0].size >= back + 4:
                    hit_va = insns[0].address
                    insn_text = f"{insns[0].mnemonic} {insns[0].op_str}".strip()
                    break
            func_va = _guess_func_start(pe_info, raw, sec_va, hit_va - sec_va)
            hits.append({
                "hit_va": f"0x{hit_va:08x}",
                "func_va": f"0x{func_va:08x}",
                "section": sec["name"],
                "insn": insn_text or f"ref 0x{target_va:08x}",
                "unique_func": func_va not in seen_funcs,
            })
            seen_funcs.add(func_va)

    iat_rec = pe_info["iat_by_va"].get(target_va)
    label = f"{iat_rec['dll']}!{iat_rec['name']}" if iat_rec else f"0x{target_va:08x}"
    return {
        "target_va": f"0x{target_va:08x}",
        "label": label,
        "count": len(hits),
        "unique_funcs": len(seen_funcs),
        "hits": hits,
        "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 1),
    }


def lift_one_function(cfg: ProjectConfig, addr: int) -> dict[str, Any]:
    """On-demand single-function x86 -> C99 lift in ~20ms (zero bulk lift required)."""
    t0 = time.monotonic()
    pe_info = _get_cached_pe(cfg)
    lf: Lifter = pe_info["lifter"]
    iat_by_va = pe_info["iat_by_va"]

    with pe_info["lifter_lock"]:
        lf.funcs[addr] = lf.funcs.get(addr, "ondemand")
        try:
            res = lf.lift(addr)
            c_code = res[0] if isinstance(res, tuple) else str(res)
            err = None
        except Exception as exc:
            c_code = ""
            err = str(exc)

    # Extract traps and callees directly from lifted C99
    traps = re.findall(r'TRAP\([^,]+,\s*"([^"]+)"\)', c_code)
    callees: set[int] = set()
    for m in re.finditer(r'\bf_([0-9a-fA-F]{4,8})\(c\)', c_code):
        v = int(m.group(1), 16)
        if v != addr:
            callees.add(v)
    for m in re.finditer(r'rn_call\(c,\s*0x([0-9a-fA-F]+)\)', c_code):
        callees.add(int(m.group(1), 16))
    for m in re.finditer(r'r32\(c,\s*0x([0-9a-fA-F]+)\)', c_code):
        v = int(m.group(1), 16)
        if v in iat_by_va:
            callees.add(v)

    # Disassemble the single function window quickly for side-by-side display
    off = addr - pe_info["base"]
    img = pe_info["img"]
    disasm_lines: list[dict[str, Any]] = []
    if 0 <= off < len(img):
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        chunk = bytes(img[off : min(len(img), off + 1024)])
        for ins in md.disasm(chunk, addr, count=140):
            disasm_lines.append({
                "addr": f"0x{ins.address:08x}",
                "bytes": ins.bytes.hex(" "),
                "mnem": ins.mnemonic,
                "ops": ins.op_str,
            })
            if ins.mnemonic in ("ret", "retn", "int3") and len(disasm_lines) >= 2:
                break

    callee_list: list[dict[str, str]] = []
    for c_va in sorted(callees):
        if c_va in iat_by_va:
            r = iat_by_va[c_va]
            callee_list.append({"va": f"0x{c_va:08x}", "label": f"{r['dll']}!{r['name']}", "kind": "api"})
        else:
            callee_list.append({"va": f"0x{c_va:08x}", "label": f"sub_{c_va:08x}", "kind": "func"})

    return {
        "addr": f"0x{addr:08x}",
        "ok": err is None and bool(c_code),
        "error": err,
        "lifted_c": c_code,
        "traps": list(traps),
        "callees": callee_list,
        "disasm": disasm_lines,
        "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 1),
    }
