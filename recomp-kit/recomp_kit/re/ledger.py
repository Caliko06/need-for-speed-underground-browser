"""Truth-State Ledger: V/I/U evidence state, name merger, and scoreboard (Principle 5)."""
from __future__ import annotations

import collections
import csv
import json
import re
from pathlib import Path
from typing import Any

from recomp_kit.config import ProjectConfig


def evidence_state(row: dict[str, str]) -> tuple[str, bool]:
    """Return (state, legacy): V (verified), I (inferred), U (unknown).
    Legacy is True only when V was inferred from old `high` without explicit V/I/U."""
    c = (row.get("confidence") or "").strip()
    if c in ("V", "I", "U"):
        return c, False
    m = re.match(r"\s*([VIU])\s*:", (row.get("evidence") or ""))
    if m:
        return m.group(1), False
    if c == "high":
        return "V", True
    return "I", False


def merge_names(cfg: ProjectConfig) -> dict[str, Any]:
    """Merge census/names_*.tsv -> census/names.tsv. V wins clashes; alternates preserved in aliases."""
    census = cfg.census_dir
    best: dict[int, list[str]] = {}
    alias: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
    legacy: set[int] = set()
    skipped = 0

    for p in sorted(census.glob("names_*.tsv")):
        if p.name == "names_seed.tsv":
            continue
        src_tag = p.stem.removeprefix("names_")
        with p.open(encoding="utf-8") as f:
            reader = csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t")
            for r in reader:
                if not r.get("name") or not r.get("addr"):
                    continue
                try:
                    a = int(r["addr"].replace("0x", ""), 16)
                except ValueError:
                    skipped += 1
                    continue
                st, leg = evidence_state(r)
                row = [f"0x{a:08x}", r["name"], r.get("system", ""), st, r.get("tool", ""), r.get("doc", ""), src_tag]
                alias[a].append((r["name"], src_tag))
                old = best.get(a)
                if not old or (("VIU".index(st), leg) < ("VIU".index(old[3]), a in legacy)):
                    best[a] = row
                    legacy.discard(a)
                    if leg:
                        legacy.add(a)

    out_tsv = census / "names.tsv"
    with out_tsv.open("w", encoding="utf-8") as f:
        f.write("addr\tname\tsystem\tconfidence\ttool\tdoc\tfrom\taliases\n")
        for a in sorted(best):
            al = " | ".join(f"{n}@{w}" for n, w in alias[a] if n != best[a][1])
            f.write("\t".join(best[a] + [al]) + "\n")

    counts = dict(collections.Counter(r[3] for r in best.values()))
    return {
        "merged_addresses": len(best),
        "by_state": counts,
        "with_aliases": sum(1 for a in best if any(n != best[a][1] for n, _ in alias[a])),
        "legacy_high_as_v": len(legacy),
        "non_hex_skipped": skipped,
        "output": str(out_tsv),
    }
