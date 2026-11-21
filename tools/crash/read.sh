#!/bin/sh
# The crash reports nfsu.cc sent, one day (UTC, default today): count per stop line, browser and GPU path, then the newest 3 in full.
# Usage: tools/crash/read.sh [YYYY-MM-DD]
D=${1:-$(date -u +%F)}
rclone cat "r2:nfsu-crash/$D/" | python3 -c '
import sys, json, collections
rows = [json.loads(l) for l in sys.stdin if l.strip()]
print(len(rows), "reports")
c = collections.Counter((r["stop"][:90], r["ua"].split(")")[0][-40:], (r["head"] or ["?"])[0][-40:]) for r in rows)
for k, n in c.most_common(20): print(n, " | ".join(k))
for r in rows[-3:]: print(json.dumps(r, indent=1)[:3000])'
