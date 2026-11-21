"""Multi-tool decompiler bridge: live Capstone x86 disassembly, Ghidra/Hopper pseudocode, and ELI5 explainer."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import capstone as cs
import pefile

from recomp_kit.config import ProjectConfig

# Lazy caches keyed by project root
_PE_CACHE: dict[Path, tuple[pefile.PE, int]] = {}
_HOPPER_INDEX: dict[Path, dict[int, tuple[int, int]]] = {}
_GHIDRA_FILES: dict[Path, list[Path]] = {}

TRAP_EXPLANATIONS = {
    "int3": "Compiler padding / debug breakpoint (harmless unless jumped to directly).",
    "unhandled": "An uncommon x86 instruction the lifter hasn't translated yet — needs a 3-line lifter rule.",
    "fpu": "A rare x87 floating-point instruction — can be added to the x87 lifter table.",
    "mmx": "An MMX/SIMD vector instruction — needs a vector helper in rt.h.",
    "sse": "An SSE floating-point instruction — needs an SSE helper in rt.h.",
    "sys": "A privileged or OS-level instruction (like in/out/sysenter) that shouldn't run in user mode.",
}


def _get_pe(cfg: ProjectConfig) -> tuple[pefile.PE, int]:
    key = cfg.resolve_binary()
    if key not in _PE_CACHE:
        pe = pefile.PE(str(key), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        _PE_CACHE[key] = (pe, pe.OPTIONAL_HEADER.ImageBase)
    return _PE_CACHE[key]


def _va_to_bytes(pe: pefile.PE, base: int, va: int, size: int) -> bytes:
    rva = va - base
    if rva < 0:
        return b""
    try:
        return pe.get_data(rva, size)
    except Exception:
        return b""


def _iat_map(pe: pefile.PE, base: int) -> dict[int, str]:
    out: dict[int, str] = {}
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode("ascii", "replace")
            for imp in entry.imports:
                nm = imp.name.decode("ascii", "replace") if imp.name else f"ord_{imp.ordinal}"
                out[imp.address] = f"{dll}!{nm}"
    return out


def disassemble_function(cfg: ProjectConfig, addr: int, max_insns: int = 120) -> dict[str, Any]:
    """Disassemble an x86-32 function straight from the PE binary using Capstone."""
    pe, base = _get_pe(cfg)
    raw = _va_to_bytes(pe, base, addr, 1024)
    if not raw:
        return {"lines": [], "insn_count": 0, "calls": [], "apis": [], "has_loop": False, "has_branch": False}

    iat = _iat_map(pe, base)
    md = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_32)
    md.detail = True

    lines: list[dict[str, Any]] = []
    calls: list[str] = []
    apis: list[str] = []
    has_loop = False
    has_branch = False
    seen_ret = False

    for insn in md.disasm(raw, addr):
        if len(lines) >= max_insns:
            break
        if seen_ret and insn.mnemonic in ("int3", "nop"):
            break
        comment = ""
        m = insn.mnemonic
        op_str = insn.op_str

        # Detect branches / loops
        if m.startswith("j") and m != "jmp":
            has_branch = True
            if insn.operands and insn.operands[0].type == cs.x86.X86_OP_IMM:
                if insn.operands[0].imm < insn.address:
                    has_loop = True
        elif m == "jmp" and insn.operands and insn.operands[0].type == cs.x86.X86_OP_IMM:
            if insn.operands[0].imm < insn.address:
                has_loop = True

        # Detect direct calls & IAT calls
        if m == "call":
            if insn.operands and insn.operands[0].type == cs.x86.X86_OP_IMM:
                tgt = insn.operands[0].imm & 0xFFFFFFFF
                calls.append(f"0x{tgt:08x}")
            elif insn.operands and insn.operands[0].type == cs.x86.X86_OP_MEM:
                disp = insn.operands[0].mem.disp & 0xFFFFFFFF
                if disp in iat:
                    apis.append(iat[disp])
                    comment = f"Win32 API: {iat[disp]}"

        lines.append({
            "addr": f"0x{insn.address:08x}",
            "bytes": insn.bytes.hex(" "),
            "mnemonic": m,
            "op_str": op_str,
            "comment": comment,
        })
        if m in ("ret", "retn"):
            seen_ret = True
            # Stop at first ret if there is no forward jump past it
            break

    return {
        "lines": lines,
        "insn_count": len(lines),
        "calls": sorted(set(calls)),
        "apis": sorted(set(apis)),
        "has_loop": has_loop,
        "has_branch": has_branch,
    }


def _find_ghidra_dirs(cfg: ProjectConfig) -> list[Path]:
    dirs: list[Path] = []
    if (cfg.census_dir / "ghidra").is_dir():
        dirs.append(cfg.census_dir / "ghidra")
    # Also support RE-NFSU shared census if this is the nfsu1 example
    repo_ghidra = cfg.root.parents[2] / "census" / "ghidra" if len(cfg.root.parents) >= 3 else None
    if cfg.name == "nfsu1" and repo_ghidra and repo_ghidra.is_dir():
        dirs.append(repo_ghidra)
    return dirs


def _find_hopper_file(cfg: ProjectConfig) -> Path | None:
    p = cfg.census_dir / "hopper" / "decomp.c"
    if p.exists():
        return p
    if cfg.name == "nfsu1" and len(cfg.root.parents) >= 3:
        repo_h = cfg.root.parents[2] / "census" / "hopper" / "decomp.c"
        if repo_h.exists():
            return repo_h
    return None


def read_ghidra_pseudocode(cfg: ProjectConfig, addr: int) -> str | None:
    """Locate Ghidra decompiled C for `addr` from census/ghidra/decomp_*.c."""
    dirs = _find_ghidra_dirs(cfg)
    if not dirs:
        return None
    hex_l = f"{addr:08x}"
    hex_s = f"{addr:x}"
    # Range-filtered file lookup first (e.g. decomp_0x401000_0x4a6800.c)
    candidates: list[Path] = []
    for d in dirs:
        for f in sorted(d.glob("decomp*.c")):
            m = re.search(r"0x([0-9a-fA-F]+)_0x([0-9a-fA-F]+)", f.name)
            if m:
                lo, hi = int(m.group(1), 16), int(m.group(2), 16)
                if lo <= addr < hi:
                    candidates.insert(0, f)
            else:
                candidates.append(f)

    hdr_pat = re.compile(rf"^//\s*0x0*{hex_s}\b|^/\*.*0x0*{hex_s}\b|\bFUN_0*{hex_l}\s*\(", re.I | re.M)
    for f in candidates:
        txt = f.read_text(encoding="utf-8", errors="replace")
        m = hdr_pat.search(txt)
        if not m:
            continue
        start = txt.rfind("\n\n", 0, m.start())
        start = 0 if start < 0 else start + 2
        # Extract until closing brace at column 0
        end = txt.find("\n}\n", m.start())
        if end < 0:
            end = min(len(txt), start + 4000)
        else:
            end += 3
        return txt[start:end].strip()
    return None


def _ensure_hopper_index(path: Path) -> dict[int, tuple[int, int]]:
    if path in _HOPPER_INDEX:
        return _HOPPER_INDEX[path]
    idx: dict[int, tuple[int, int]] = {}
    # Fast scan for Hopper function headers: `// 00401000 sub_401000` or `int sub_401000(`
    pat = re.compile(rb"^(?://\s*([0-9a-fA-F]{6,8})\s+sub_|[A-Za-z_][A-Za-z0-9_ \t\*]*\bsub_([0-9a-fA-F]{5,8})\s*\()")
    with path.open("rb") as f:
        prev_addr: int | None = None
        prev_off = 0
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            m = pat.match(line)
            if m:
                if prev_addr is not None:
                    idx[prev_addr] = (prev_off, off)
                prev_addr = int(m.group(1) or m.group(2), 16)
                prev_off = off
        if prev_addr is not None:
            idx[prev_addr] = (prev_off, f.tell())
    _HOPPER_INDEX[path] = idx
    return idx


def read_hopper_pseudocode(cfg: ProjectConfig, addr: int) -> str | None:
    """Instant byte-offset lookup into Hopper's decomp.c."""
    hp = _find_hopper_file(cfg)
    if not hp:
        return None
    idx = _ensure_hopper_index(hp)
    span = idx.get(addr)
    if not span:
        return None
    start, end = span
    length = min(end - start, 12000)
    with hp.open("rb") as f:
        f.seek(start)
        return f.read(length).decode("utf-8", errors="replace").strip()


def build_eli5_summary(
    addr: int,
    disasm: dict[str, Any],
    traps: list[str],
    ran: bool,
    ledger: dict[str, str],
    has_ghidra: bool,
    has_hopper: bool,
) -> dict[str, Any]:
    """Generate a plain-language ELI5 explanation of what this function is and what to do next."""
    n = disasm["insn_count"]
    bullets: list[str] = []

    if ledger.get("name"):
        st = ledger.get("confidence", "U")
        st_txt = {"V": "verified against the binary", "I": "inferred from call graph", "U": "unverified"}.get(st, st)
        bullets.append(f"Named `{ledger['name']}` in subsystem `{ledger.get('system', 'misc')}` ({st_txt}).")
    else:
        bullets.append(f"Unnamed function at 0x{addr:08x} ({n} x86 instructions).")

    if disasm["apis"]:
        bullets.append(f"Talks to Windows via: {', '.join(disasm['apis'][:5])}.")
    elif disasm["calls"]:
        bullets.append(f"Calls {len(disasm['calls'])} other internal function(s) — likely game/app logic.")
    else:
        bullets.append("Leaf function (calls nothing else) — pure math, memory, or helper logic.")

    if disasm["has_loop"]:
        bullets.append("Contains a loop (jumps backwards) — repeats work over data or a counter.")
    elif disasm["has_branch"]:
        bullets.append("Contains conditional branches (if/else logic).")

    if ran:
        bullets.append("Executed at runtime (RN_COV=1): this function is confirmed LIVE code.")
    else:
        bullets.append("Not seen in runtime coverage yet (static discovery only).")

    if traps:
        trap_notes = []
        for t in traps:
            prefix = t.split(":")[0]
            trap_notes.append(f"{t} — {TRAP_EXPLANATIONS.get(prefix, 'needs lifter support')}")
        bullets.append("Has translation trap(s): " + "; ".join(trap_notes))
        next_step = "Inspect the trapped x86 instruction below, add a lifter rule or patch, then run Unicorn Verify."
        status = "needs_fix"
    else:
        bullets.append("Zero translation traps — 100% lifted to clean portable C.")
        if not ledger.get("name") and ran:
            next_step = "This function ran live! Read the pseudocode/x86 and give it a Verified (V) name below."
            status = "ready_to_name"
        else:
            next_step = "Click 'Verify with Unicorn' to prove the translated C matches real x86 CPU bit-for-bit."
            status = "clean"

    sources = ["x86 Disasm", "Lifted C"]
    if has_ghidra:
        sources.append("Ghidra")
    if has_hopper:
        sources.append("Hopper")

    return {
        "status": status,
        "headline": bullets[0],
        "bullets": bullets,
        "next_step": next_step,
        "sources": sources,
    }
