"""Fast, lazy-cached PE binary analysis: metadata, strings, xrefs, callgraph, and binary coverage map."""
from __future__ import annotations

import bisect
import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

import capstone as cs

from recomp_kit.config import ProjectConfig
from recomp_kit.re.decompiler import _get_pe, _va_to_bytes, disassemble_function

# APIs currently implemented in runtime/win32/win32_min.c
IMPLEMENTED_APIS: set[tuple[str, str]] = {
    ("kernel32.dll", "GetStdHandle"),
    ("kernel32.dll", "WriteFile"),
    ("kernel32.dll", "WriteConsoleA"),
    ("kernel32.dll", "ExitProcess"),
    ("kernel32.dll", "GetProcessHeap"),
    ("kernel32.dll", "HeapAlloc"),
    ("kernel32.dll", "HeapFree"),
    ("kernel32.dll", "VirtualAlloc"),
    ("kernel32.dll", "VirtualFree"),
    ("kernel32.dll", "GetLastError"),
    ("kernel32.dll", "SetLastError"),
    ("kernel32.dll", "GetTickCount"),
    ("kernel32.dll", "QueryPerformanceFrequency"),
    ("kernel32.dll", "QueryPerformanceCounter"),
    ("kernel32.dll", "GetCurrentProcessId"),
    ("kernel32.dll", "GetCurrentThreadId"),
    ("kernel32.dll", "GetVersion"),
    ("kernel32.dll", "GetCommandLineA"),
    ("kernel32.dll", "GetModuleHandleA"),
    ("kernel32.dll", "OutputDebugStringA"),
    ("kernel32.dll", "lstrlenA"),
    ("kernel32.dll", "TlsAlloc"),
    ("kernel32.dll", "TlsGetValue"),
    ("kernel32.dll", "TlsSetValue"),
    ("kernel32.dll", "InitializeCriticalSection"),
    ("kernel32.dll", "EnterCriticalSection"),
    ("kernel32.dll", "LeaveCriticalSection"),
    ("kernel32.dll", "DeleteCriticalSection"),
    ("user32.dll", "MessageBoxA"),
    ("msvcrt.dll", "puts"),
    ("msvcrt.dll", "malloc"),
    ("msvcrt.dll", "free"),
    ("msvcrt.dll", "exit"),
}

_ASCII_STR_RE = re.compile(rb"[\x20-\x7e]{4,}")
_HEX_IMM_RE = re.compile(r"0x([0-9a-fA-F]{4,8})")
_GEN_CALL_RE = re.compile(
    rb"^(?:static\s+)?void\s+f_([0-9a-fA-F]+)(?:_lift)?\s*\(|\bf_([0-9a-fA-F]+)\s*\(",
    re.M,
)

# Lazy per-binary / per-project caches
_META_CACHE: dict[Path, dict[str, Any]] = {}
_STRINGS_CACHE: dict[Path, dict[int, tuple[str, str]]] = {}
_EXEC_SECTIONS_CACHE: dict[Path, list[tuple[int, bytes]]] = {}
_REV_CALL_CACHE: dict[Path, dict[int, list[int]]] = {}


def get_binary_meta(cfg: ProjectConfig) -> dict[str, Any]:
    """Return cached binary MD5, byte size, and PE section table."""
    bin_path = cfg.resolve_binary()
    if bin_path in _META_CACHE:
        return _META_CACHE[bin_path]

    raw = bin_path.read_bytes()
    md5 = hashlib.md5(raw).hexdigest()
    size = len(raw)

    pe, base = _get_pe(cfg)
    sections: list[dict[str, Any]] = []
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\x00").decode("ascii", "replace")
        va = base + sec.VirtualAddress
        vsize = int(sec.Misc_VirtualSize or sec.SizeOfRawData)
        is_exec = bool(sec.Characteristics & 0x20000000)
        sections.append({
            "name": name,
            "va": f"0x{va:08x}",
            "size": vsize,
            "exec": is_exec,
        })

    meta = {"md5": md5, "size": size, "sections": sections}
    _META_CACHE[bin_path] = meta
    return meta


def _get_exec_sections(cfg: ProjectConfig) -> list[tuple[int, bytes]]:
    bin_path = cfg.resolve_binary()
    if bin_path in _EXEC_SECTIONS_CACHE:
        return _EXEC_SECTIONS_CACHE[bin_path]
    pe, base = _get_pe(cfg)
    out: list[tuple[int, bytes]] = []
    for sec in pe.sections:
        if sec.Characteristics & 0x20000000:
            data = sec.get_data()[: sec.SizeOfRawData]
            out.append((base + sec.VirtualAddress, data))
    _EXEC_SECTIONS_CACHE[bin_path] = out
    return out


def _get_strings_map(cfg: ProjectConfig) -> dict[int, tuple[str, str]]:
    """Scan .rdata and .data sections for printable ASCII strings (len >= 4, max 120 chars)."""
    bin_path = cfg.resolve_binary()
    if bin_path in _STRINGS_CACHE:
        return _STRINGS_CACHE[bin_path]

    pe, base = _get_pe(cfg)
    target_secs = []
    fallback_secs = []
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\x00").decode("ascii", "replace")
        nl = name.lower()
        if nl in (".rdata", ".data", ".rodata"):
            target_secs.append((name, sec))
        elif not (sec.Characteristics & 0x20000000) and nl not in (".rsrc", ".reloc", ".idata"):
            fallback_secs.append((name, sec))

    scan_secs = target_secs or fallback_secs
    strings: dict[int, tuple[str, str]] = {}
    for name, sec in scan_secs:
        raw = sec.get_data()[: sec.SizeOfRawData]
        sec_va = base + sec.VirtualAddress
        for m in _ASCII_STR_RE.finditer(raw):
            va = sec_va + m.start()
            text = m.group(0)[:120].decode("ascii", "replace")
            strings[va] = (text, name)

    _STRINGS_CACHE[bin_path] = strings
    return strings


def _load_sorted_func_addrs(cfg: ProjectConfig) -> list[int]:
    if not cfg.functions_tsv.exists():
        return []
    addrs: list[int] = []
    for line in cfg.functions_tsv.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            addrs.append(int(line.split()[0], 16))
        except ValueError:
            continue
    addrs.sort()
    return addrs


def _find_string_xrefs_in_code(
    exec_secs: list[tuple[int, bytes]],
    func_addrs: list[int],
    str_va: int,
    cap: int = 12,
) -> list[str]:
    needle = struct.pack("<I", str_va & 0xFFFFFFFF)
    refs: set[int] = set()
    for sec_va, data in exec_secs:
        pos = 0
        while True:
            idx = data.find(needle, pos)
            if idx < 0:
                break
            ref_va = sec_va + idx
            if func_addrs:
                fi = bisect.bisect_right(func_addrs, ref_va) - 1
                if fi >= 0:
                    refs.add(func_addrs[fi])
                else:
                    refs.add(ref_va)
            else:
                refs.add(ref_va)
            if len(refs) >= cap:
                break
            pos = idx + 1
        if len(refs) >= cap:
            break
    return [f"0x{a:08x}" for a in sorted(refs)]


def extract_strings(cfg: ProjectConfig, q: str = "", limit: int = 80) -> dict[str, Any]:
    """Return cached .rdata/.data ASCII strings filtered by case-insensitive substring `q`."""
    smap = _get_strings_map(cfg)
    ql = q.strip().lower()
    matched: list[tuple[int, str, str]] = []
    for va, (text, sec) in smap.items():
        if ql:
            if ql not in text.lower() and ql not in f"0x{va:08x}":
                continue
        matched.append((va, text, sec))

    total = len(matched)
    page = matched[: max(0, limit)]
    exec_secs = _get_exec_sections(cfg)
    func_addrs = _load_sorted_func_addrs(cfg)

    items = [
        {
            "va": f"0x{va:08x}",
            "text": text,
            "section": sec,
            "xrefs": _find_string_xrefs_in_code(exec_secs, func_addrs, va),
        }
        for va, text, sec in page
    ]
    return {"total": total, "items": items}


def _get_reverse_call_index(cfg: ProjectConfig) -> dict[int, list[int]]:
    """Build a lazy reverse call index (callee -> sorted callers) from build/gen/f*.c or Capstone."""
    key = cfg.root
    if key in _REV_CALL_CACHE:
        return _REV_CALL_CACHE[key]

    rev_sets: dict[int, set[int]] = {}
    gen_files = sorted(cfg.gen_dir.glob("f*.c")) if cfg.gen_dir.is_dir() else []

    if gen_files:
        for fp in gen_files:
            data = fp.read_bytes()
            cur_fn: int | None = None
            for m in _GEN_CALL_RE.finditer(data):
                g_def = m.group(1)
                if g_def is not None:
                    cur_fn = int(g_def, 16)
                elif cur_fn is not None:
                    callee = int(m.group(2), 16)
                    if callee != cur_fn:
                        rev_sets.setdefault(callee, set()).add(cur_fn)
    elif cfg.functions_tsv.exists():
        # Fallback: Capstone scan of functions.tsv
        pe, base = _get_pe(cfg)
        md = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_32)
        md.detail = True
        func_addrs = _load_sorted_func_addrs(cfg)
        for i, fn_va in enumerate(func_addrs):
            next_va = func_addrs[i + 1] if i + 1 < len(func_addrs) else fn_va + 512
            span = min(max(next_va - fn_va, 16), 1024)
            raw = _va_to_bytes(pe, base, fn_va, span)
            if not raw:
                continue
            for insn in md.disasm(raw, fn_va):
                if insn.mnemonic == "call" and insn.operands and insn.operands[0].type == cs.x86.X86_OP_IMM:
                    tgt = insn.operands[0].imm & 0xFFFFFFFF
                    if tgt != fn_va:
                        rev_sets.setdefault(tgt, set()).add(fn_va)
                if insn.mnemonic in ("ret", "retn"):
                    break

    rev = {k: sorted(v) for k, v in rev_sets.items()}
    _REV_CALL_CACHE[key] = rev
    return rev


def get_function_xrefs(
    cfg: ProjectConfig,
    addr: int,
    implemented_apis: set[tuple[str, str]] | None = None,
    disasm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract xrefs_in, xrefs_out, IAT APIs, and referenced strings for function `addr`."""
    if disasm is None:
        disasm = disassemble_function(cfg, addr)
    impl_set = IMPLEMENTED_APIS if implemented_apis is None else implemented_apis

    # Direct calls in executable sections
    exec_ranges = [(va, va + len(data)) for va, data in _get_exec_sections(cfg)]
    xrefs_out: list[str] = []
    for c_hex in disasm.get("calls", []):
        try:
            tgt = int(c_hex, 16)
        except ValueError:
            continue
        if not exec_ranges or any(lo <= tgt < hi for lo, hi in exec_ranges):
            xrefs_out.append(f"0x{tgt:08x}")

    # IAT APIs
    apis: list[dict[str, Any]] = []
    for api_str in disasm.get("apis", []):
        if "!" in api_str:
            dll, name = api_str.split("!", 1)
        else:
            dll, name = "", api_str
        apis.append({
            "dll": dll,
            "name": name,
            "implemented": (dll.lower(), name) in impl_set,
        })

    # String immediates from push / mov / lea operands
    smap = _get_strings_map(cfg)
    seen_str_vas: set[int] = set()
    strings: list[dict[str, str]] = []
    for line in disasm.get("lines", []):
        mnem = line.get("mnemonic", "")
        if mnem not in ("push", "mov", "lea"):
            continue
        op_str = line.get("op_str", "")
        for hm in _HEX_IMM_RE.finditer(op_str):
            val = int(hm.group(1), 16)
            if val in smap and val not in seen_str_vas:
                seen_str_vas.add(val)
                text, sec = smap[val]
                strings.append({"va": f"0x{val:08x}", "text": text, "section": sec})

    # Incoming callers from lazy reverse call index
    rev = _get_reverse_call_index(cfg)
    xrefs_in = [f"0x{a:08x}" for a in rev.get(addr, [])]

    return {
        "xrefs_in": xrefs_in,
        "xrefs_out": xrefs_out,
        "apis": apis,
        "strings": strings,
    }


def _load_project_annotations(
    cfg: ProjectConfig,
) -> tuple[dict[int, dict[str, str]], set[int], set[int]]:
    """Load (names_map, ran_set, trapped_set) for a project."""
    names: dict[int, dict[str, str]] = {}
    names_p = cfg.census_dir / "names.tsv"
    if names_p.exists():
        with names_p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                try:
                    names[int(r["addr"], 16)] = dict(r)
                except (ValueError, KeyError):
                    continue

    ran: set[int] = set()
    cov_p = cfg.census_dir / "cov" / "union.json"
    if cov_p.exists():
        try:
            ran = {int(x, 16) for x in json.loads(cov_p.read_text(encoding="utf-8")).get("addrs", [])}
        except Exception:
            ran = set()

    trapped: set[int] = set()
    if cfg.lift_report_json.exists():
        try:
            rep = json.loads(cfg.lift_report_json.read_text(encoding="utf-8"))
            trapped = {int(k, 16) for k in rep.get("blocked_functions", {}).keys()}
        except Exception:
            trapped = set()

    return names, ran, trapped


def get_callgraph(cfg: ProjectConfig, addr: int, depth: int = 1) -> dict[str, Any]:
    """Build a crisp, capped ego-centric callgraph around `addr` (callers, callees, APIs, strings)."""
    names, ran_set, trapped_set = _load_project_annotations(cfg)
    disasm = disassemble_function(cfg, addr)
    xrefs = get_function_xrefs(cfg, addr, disasm=disasm)

    center_id = f"0x{addr:08x}"
    center_ran = addr in ran_set

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    def _add_fn_node(fn_addr: int, kind: str, insn_count: int = 0) -> str:
        nid = f"0x{fn_addr:08x}"
        if nid in seen_nodes:
            return nid
        seen_nodes.add(nid)
        nm = names.get(fn_addr, {})
        nodes.append({
            "id": nid,
            "label": nm.get("name") or f"sub_{fn_addr:08x}",
            "kind": kind,
            "state": nm.get("confidence", "U") if nm.get("name") else "U",
            "ran": fn_addr in ran_set,
            "trapped": fn_addr in trapped_set,
            "system": nm.get("system", ""),
            "insn_count": insn_count,
        })
        return nid

    _add_fn_node(addr, "center", insn_count=disasm.get("insn_count", 0))

    # Cap callers at 12
    for c_hex in xrefs["xrefs_in"][:12]:
        c_addr = int(c_hex, 16)
        cid = _add_fn_node(c_addr, "caller")
        edges.append({
            "from": cid,
            "to": center_id,
            "kind": "call",
            "live": (c_addr in ran_set) and center_ran,
        })

    # Cap callees at 14
    for c_hex in xrefs["xrefs_out"][:14]:
        c_addr = int(c_hex, 16)
        cid = _add_fn_node(c_addr, "callee")
        edges.append({
            "from": center_id,
            "to": cid,
            "kind": "call",
            "live": center_ran and (c_addr in ran_set),
        })

    # Cap APIs at 10
    for api in xrefs["apis"][:10]:
        aid = f"api:{api['dll']}!{api['name']}"
        if aid not in seen_nodes:
            seen_nodes.add(aid)
            nodes.append({
                "id": aid,
                "label": f"{api['dll']}!{api['name']}" if api["dll"] else api["name"],
                "kind": "api",
                "state": "API",
                "ran": center_ran,
                "trapped": not api["implemented"],
                "system": api["dll"],
                "insn_count": 0,
            })
        edges.append({
            "from": center_id,
            "to": aid,
            "kind": "api",
            "live": center_ran,
        })

    # Cap strings at 8
    for s in xrefs["strings"][:8]:
        sid = f"str:{s['va']}"
        if sid not in seen_nodes:
            seen_nodes.add(sid)
            txt = s["text"]
            label = txt if len(txt) <= 36 else txt[:33] + "..."
            nodes.append({
                "id": sid,
                "label": label,
                "kind": "string",
                "state": "STR",
                "ran": center_ran,
                "trapped": False,
                "system": s["section"],
                "insn_count": 0,
            })
        edges.append({
            "from": center_id,
            "to": sid,
            "kind": "str",
            "live": center_ran,
        })

    return {
        "center": center_id,
        "nodes": nodes,
        "edges": edges,
        "xrefs_in": xrefs["xrefs_in"],
        "xrefs_out": xrefs["xrefs_out"],
        "strings": xrefs["strings"],
        "apis": xrefs["apis"],
    }


def get_binary_map(cfg: ProjectConfig, buckets: int = 180) -> dict[str, Any]:
    """Bin all discovered functions across [min_va, max_va] with coverage, trap, and V/I/U counts."""
    names, ran_set, trapped_set = _load_project_annotations(cfg)

    funcs: list[tuple[int, str]] = []
    if cfg.functions_tsv.exists():
        for line in cfg.functions_tsv.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split()
            try:
                a = int(parts[0], 16)
            except ValueError:
                continue
            seed = parts[1] if len(parts) > 1 else "?"
            funcs.append((a, seed))
    funcs.sort(key=lambda x: x[0])

    if not funcs:
        return {
            "total": 0,
            "min_va": "0x00000000",
            "max_va": "0x00000000",
            "buckets": [],
            "functions": [],
        }

    min_va = funcs[0][0]
    max_va = funcs[-1][0]
    n_buckets = min(max(1, buckets), max(1, len(funcs)))
    span = max(1, max_va - min_va + 1)

    bucket_data: list[dict[str, Any]] = []
    for i in range(n_buckets):
        b_start = min_va + (span * i) // n_buckets
        b_end = min_va + (span * (i + 1)) // n_buckets - 1
        if b_end < b_start:
            b_end = b_start
        bucket_data.append({
            "va_start": f"0x{b_start:08x}",
            "va_end": f"0x{b_end:08x}",
            "count": 0,
            "ran": 0,
            "verified": 0,
            "inferred": 0,
            "trapped": 0,
            "sample_addr": "",
            "sample_name": "",
            "_sample_prio": -1,
        })

    for a, _seed in funcs:
        idx = min(n_buckets - 1, (a - min_va) * n_buckets // span)
        b = bucket_data[idx]
        b["count"] += 1
        is_ran = a in ran_set
        is_trapped = a in trapped_set
        nm = names.get(a, {})
        st = nm.get("confidence", "U") if nm.get("name") else "U"
        fn_name = nm.get("name", "")
        if is_ran:
            b["ran"] += 1
        if is_trapped:
            b["trapped"] += 1
        if st == "V":
            b["verified"] += 1
        elif st == "I":
            b["inferred"] += 1

        # Pick the most interesting sample function in this bucket
        prio = (4 if (is_ran and is_trapped) else 3 if is_ran else 2 if fn_name else 1 if is_trapped else 0)
        if prio > b["_sample_prio"]:
            b["_sample_prio"] = prio
            b["sample_addr"] = f"0x{a:08x}"
            b["sample_name"] = fn_name

    for b in bucket_data:
        b.pop("_sample_prio", None)

    out: dict[str, Any] = {
        "total": len(funcs),
        "min_va": f"0x{min_va:08x}",
        "max_va": f"0x{max_va:08x}",
        "buckets": bucket_data,
    }
    if len(funcs) <= 400:
        out["functions"] = [
            {
                "addr": f"0x{a:08x}",
                "seed": seed,
                "ran": a in ran_set,
                "trapped": a in trapped_set,
                "state": names[a].get("confidence", "U") if a in names and names[a].get("name") else "U",
                "name": names[a].get("name", "") if a in names else "",
                "system": names[a].get("system", "") if a in names else "",
            }
            for a, seed in funcs
        ]
    return out
