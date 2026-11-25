#!/bin/sh
# Funnel telemetry (rn-funnel-1) for one UTC day (default today): conversion to run + load_ms p50/p90 by OS and tier.
# Usage: tools/crash/read_funnel.sh [YYYY-MM-DD]
D=${1:-$(date -u +%F)}
rclone cat "r2:nfsu-crash/funnel/$D/" | python3 -c '
import sys, json, collections
rows = [json.loads(l) for l in sys.stdin if l.strip()]
print(len(rows), "sessions")
by_os = collections.defaultdict(lambda: [0, 0, []])
for r in rows:
    e = by_os[(r.get("os", "?"), r.get("tier", "?"))]
    if r.get("ev") == "run":
        e[0] += 1
        e[2].append(r.get("load_ms", 0))
    else:
        e[1] += 1
for (osn, tier), (ok, st, ms) in sorted(by_os.items(), key=lambda x: -(x[1][0] + x[1][1])):
    ms.sort()
    p50 = ms[len(ms)//2] if ms else 0
    p90 = ms[int(len(ms)*0.9)] if ms else 0
    pct = 100.0 * ok / max(1, ok + st)
    print(f"{osn:8s} {tier:10s} | run={ok:4d} stop={st:4d} ({pct:5.1f}%) | load p50={p50}ms p90={p90}ms")
'
