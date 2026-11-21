"""Shared function inspection & V/I/U tagging helpers used by CLI, UI, and MCP."""
from __future__ import annotations

import bisect
import csv
import json
import re
from pathlib import Path
from typing import Any

from recomp_kit.config import ProjectConfig
from recomp_kit.re.callgraph import get_binary_meta, get_function_xrefs
from recomp_kit.re.decompiler import (
    build_eli5_summary,
    disassemble_function,
    read_ghidra_pseudocode,
    read_hopper_pseudocode,
)
from recomp_kit.re.ledger import merge_names


def read_lifted_c(cfg: ProjectConfig, addr: int) -> str | None:
    """Extract the lifted C body of `f_<addr>` from build/gen/fNNN.c."""
    gen = cfg.gen_dir
    if not gen.exists():
        return None
    pat = re.compile(
        rf"^(?:static\s+)?void\s+f_{addr:x}(?:_lift)?\s*\(.*?^\}}\n",
        re.M | re.S,
    )
    candidates: list[Path] = []
    if cfg.functions_tsv.exists():
        addrs = sorted(
            int(l.split()[0], 16)
            for l in cfg.functions_tsv.read_text(encoding="utf-8").splitlines()
            if l.strip()
        )
        if len(addrs) >= cfg.chunks:
            bounds = [addrs[k * len(addrs) // cfg.chunks] for k in range(1, cfg.chunks)]
            idx = bisect.bisect_right(bounds, addr)
            p = gen / f"f{idx:03d}.c"
            if p.exists():
                candidates.append(p)
    if not candidates:
        candidates = sorted(gen.glob("f*.c"))

    for p in candidates:
        text = p.read_text(encoding="utf-8", errors="replace")
        m = pat.search(text)
        if m:
            return m.group(0)
    for p in sorted(gen.glob("f*.c")):
        if p in candidates:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def get_function_detail(cfg: ProjectConfig, addr: int) -> dict[str, Any]:
    """Combine seed kind, traps, V/I/U ledger, coverage, lifted C, x86 disasm, Ghidra/Hopper, and ELI5."""
    seed = "unknown"
    if cfg.functions_tsv.exists():
        key = f"{addr:08x}"
        for line in cfg.functions_tsv.read_text(encoding="utf-8").splitlines():
            if line.startswith(key):
                parts = line.split()
                if len(parts) >= 2:
                    seed = parts[1]
                break

    traps: list[str] = []
    if cfg.lift_report_json.exists():
        rep = json.loads(cfg.lift_report_json.read_text(encoding="utf-8"))
        traps = rep.get("blocked_functions", {}).get(f"{addr:08x}", [])

    ran = False
    cov_path = cfg.census_dir / "cov" / "union.json"
    if cov_path.exists():
        ran = any(int(x, 16) == addr for x in json.loads(cov_path.read_text(encoding="utf-8")).get("addrs", []))

    ledger_row: dict[str, str] = {}
    names_tsv = cfg.census_dir / "names.tsv"
    if names_tsv.exists():
        with names_tsv.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                try:
                    if int(r["addr"], 16) == addr:
                        ledger_row = dict(r)
                        break
                except (ValueError, KeyError):
                    continue

    lifted = read_lifted_c(cfg, addr)
    if lifted is None:
        # On-demand single-function lift (~20ms) so Compare & Lab work without bulk lift!
        try:
            from recomp_kit.re.ondemand import lift_one_function

            od = lift_one_function(cfg, addr)
            if od.get("ok") and od.get("lifted_c"):
                lifted = od["lifted_c"]
                if not traps and od.get("traps"):
                    traps = list(od["traps"])
        except Exception:
            pass
    disasm = disassemble_function(cfg, addr)
    ghidra = read_ghidra_pseudocode(cfg, addr)
    hopper = read_hopper_pseudocode(cfg, addr)
    xrefs = get_function_xrefs(cfg, addr, disasm=disasm)
    meta = get_binary_meta(cfg)
    eli5 = build_eli5_summary(
        addr=addr,
        disasm=disasm,
        traps=traps,
        ran=ran,
        ledger=ledger_row,
        has_ghidra=bool(ghidra),
        has_hopper=bool(hopper),
    )

    raw_hex_tokens: list[str] = []
    for ln in disasm.get("lines", []):
        raw_hex_tokens.extend(ln.get("bytes", "").split())
        if len(raw_hex_tokens) >= 16:
            break
    bytes_preview = " ".join(raw_hex_tokens[:16])

    tools_present: list[str] = []
    if disasm.get("lines"):
        tools_present.append("capstone")
    if lifted:
        tools_present.append("lifted_c")
    if ghidra:
        tools_present.append("ghidra")
    if hopper:
        tools_present.append("hopper")

    bin_name = cfg.resolve_binary().name
    evidence_pack = {
        "binary_name": bin_name,
        "binary_md5": meta["md5"],
        "va": f"0x{addr:08x}",
        "bytes_preview": bytes_preview,
        "tools_present": tools_present,
        "suggested_evidence_line": (
            f"{bin_name} md5={meta['md5'][:12]} va=0x{addr:08x} "
            f"({'+'.join(tools_present) or 'static'})"
        ),
    }

    return {
        "addr": f"0x{addr:08x}",
        "seed": seed,
        "ran": ran,
        "traps": traps,
        "ledger": ledger_row,
        "lifted_c": lifted,
        "disasm": disasm,
        "ghidra_c": ghidra,
        "hopper_c": hopper,
        "eli5": eli5,
        "xrefs_in": xrefs["xrefs_in"],
        "xrefs_out": xrefs["xrefs_out"],
        "strings": xrefs["strings"],
        "evidence_pack": evidence_pack,
    }


def tag_function(
    cfg: ProjectConfig,
    addr: int,
    name: str,
    system: str,
    state: str = "V",
    evidence: str = "",
    tool: str = "agent",
    doc: str = "",
) -> dict[str, Any]:
    """Append a V/I/U record to census/names_<system>.tsv and re-merge census/names.tsv."""
    st = state.strip().upper()
    if st not in ("V", "I", "U"):
        raise ValueError(f"Invalid state '{state}': must be V, I, or U")
    sys_clean = re.sub(r"[^a-z0-9_]+", "_", system.strip().lower()) or "misc"
    cfg.census_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = cfg.census_dir / f"names_{sys_clean}.tsv"
    write_hdr = not tsv_path.exists()
    with tsv_path.open("a", encoding="utf-8") as f:
        if write_hdr:
            f.write("addr\tname\tsystem\tconfidence\ttool\tdoc\tevidence\n")
        clean = lambda s: s.replace("\t", " ").replace("\n", " ").strip()
        f.write(
            f"0x{addr:08x}\t{clean(name)}\t{sys_clean}\t{st}\t{clean(tool)}\t{clean(doc)}\t{clean(evidence)}\n"
        )
    merged = merge_names(cfg)
    return {"written_to": str(tsv_path), "addr": f"0x{addr:08x}", "name": name, "state": st, "merge": merged}
