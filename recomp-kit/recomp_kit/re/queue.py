"""Coverage-weighted RE & Trap priority queue (Principles 4 & 8)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from recomp_kit.config import ProjectConfig


def build_queue(cfg: ProjectConfig, limit: int = 25) -> dict[str, Any]:
    """Rank functions that need attention most:
    Tier 1: Executed (ran=True) AND blocked by a real non-int3 TRAP.
    Tier 2: Executed (ran=True) AND unnamed (no V/I name in names.tsv).
    Tier 3: Static real-trap functions (not yet covered by a run).
    """
    census = cfg.census_dir
    lift_rep = json.loads(cfg.lift_report_json.read_text(encoding="utf-8")) if cfg.lift_report_json.exists() else {}
    blocked: dict[int, list[str]] = {int(a, 16): reasons for a, reasons in lift_rep.get("blocked_functions", {}).items()}

    cov_path = census / "cov" / "union.json"
    ran: set[int] = set()
    if cov_path.exists():
        ran = {int(x, 16) for x in json.loads(cov_path.read_text(encoding="utf-8")).get("addrs", [])}

    named: dict[int, tuple[str, str]] = {}
    names_tsv = census / "names.tsv"
    if names_tsv.exists():
        with names_tsv.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                try:
                    named[int(r["addr"], 16)] = (r["name"], r.get("confidence", "I"))
                except (ValueError, KeyError):
                    continue

    tier1 = [
        {"addr": f"0x{a:08x}", "ran": True, "traps": blocked[a], "name": named.get(a, ("", "U"))[0]}
        for a in sorted(ran & set(blocked))
    ]
    tier2 = [
        {"addr": f"0x{a:08x}", "ran": True, "traps": [], "state": "U"}
        for a in sorted(ran - set(named) - set(blocked))
    ]
    tier3 = [
        {"addr": f"0x{a:08x}", "ran": False, "traps": blocked[a], "name": named.get(a, ("", "U"))[0]}
        for a in sorted(set(blocked) - ran)
    ]

    out = {
        "project": cfg.name,
        "summary": {
            "total_lifted": lift_rep.get("functions", 0),
            "total_ran": len(ran),
            "total_named": len(named),
            "total_real_trap_funcs": len(blocked),
            "tier1_ran_and_trapped": len(tier1),
            "tier2_ran_and_unnamed": len(tier2),
            "tier3_static_trapped": len(tier3),
        },
        "tier1": tier1[:limit],
        "tier2": tier2[:limit],
        "tier3": tier3[:limit],
    }
    (census / "queue.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
