# Systems tags (census/systems.tsv)

> Source: `docs/re/systems_method.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 10

# Systems tags (census/systems.tsv)
One row per function start of pc/Speed.exe (17,368: Hopper 14,333 + 3,035 lifter starts Hopper lacks); all 13,739
lifted functions have a row. Columns: addr, system, confidence, how, evidence.

## Method (tools/census/systems.py; rules in tools/census/sys_rules.py)
1. Seeds: strings (direct, tables, pool neighbours, decompile literals), imports (census/imports_sites.tsv), addresses
   in docs and q_*.py (doc -> system map; mixed docs skip lines with >3 addresses), PATCH headers. Strings in an
   unwind funclet count for its owner. Static CRT band 0x672000-0x6830a0: string/import evidence is forced to runtime.
2. Propagation, 8 rounds: callers 1/sqrt(n), callees 0.5, vtable peers 0.5, pieces of one function 1.5, unwind owner 2.0,
   nearest seeds in link order; far edges weigh less. Called from >=3 systems = runtime (hub). Then shared globals,
   then neighbour sandwich. Leftovers: EH glue and padding = runtime/low; the rest unknown/low.
3. Confidence is rule-based, not a probability: high = seed score >=3, share >=0.6; med = >=1.4, >=0.5 (graph: early,
   strong, >8 instructions); low = the rest.

## Counts, lifted functions (high/med/low)
| system | h/m/l | total | % | system | h/m/l | total | % |
|---|---|---|---|---|---|---|---|
| canon | 275/678/1103 | 2056 | 15.0 | audio | 83/322/894 | 1299 | 9.5 |
| track | 130/199/462 | 791 | 5.8 | assets | 12/39/103 | 154 | 1.1 |
| traffic | 67/52/78 | 197 | 1.4 | props | 33/51/99 | 183 | 1.3 |
| rivals | 258/368/459 | 1085 | 7.9 | input | 12/50/67 | 129 | 0.9 |
| car | 147/270/548 | 965 | 7.0 | runtime | 56/468/1247 | 1771 | 12.9 |
| camera | 44/42/175 | 261 | 1.9 | online | 126/171/394 | 691 | 5.0 |
| render | 179/730/1334 | 2243 | 16.3 | unknown | 0/0/1560 | 1560 | 11.4 |
| hud | 85/81/188 | 354 | 2.6 | all | 1507/3521/8711 | 13739 | 100 |

200 runtime/low rows are EH glue (how=eh-glue), not real functions: leave them out of per-system denominators.

## Manual check (I read the Hopper decompile of every sampled function)
`--sample N --seed S` prints tag, evidence and decompile. agree = content fits; plausible = fits region and neighbours;
unverifiable = stub or thunk, tag only matches neighbours; wrong; unknown = tagged unknown.
- Seed 31337, n=50, after one rule fix: agree 19, plausible 9, unverifiable 9, wrong 6, unknown 7. Strict 19/50,
  agree+plausible 28/50, with unverifiable 37/50. Target 40/50 NOT met. The fix came from this sample (3 rows: camera
  mover ctor, Loaded*SlotPool = assets, CRT file I/O = runtime), so it is not held out.
- Seed 4242, n=24, held out, same rules: agree 9, plausible 5, unverifiable 5, wrong 2, unknown 3 (19/24 lenient).
- Wrong tags are about 8-12% in both; the gap is unverifiable tiny functions and 11% unknown.
- External audit 2026-10-29: of the 886 named functions, 419 (47%) had a different system in systems.tsv than in names.tsv
  (normalised sound->audio, tuning/garage->car, blur->render). The strict agreement of 19/50 (38%) is the better estimate
  of the graph's accuracy, not "8-12% wrong". Rule now: a name with a system (V or I) overrides the graph tag
  (tools/census/scoreboard.py); `tagged` counts only med/high confidence or named functions.
- Tuning samples: seeds 7, 101, 202; earlier reads: 1029 (n=50), 2026 (n=30).

## Rerun
`.venv/bin/python tools/census/systems.py` (10 s; needs capstone and pefile from .venv). Writes census/systems.tsv and
prints the table. Hopper live, Ghidra live and REA are not used.

## Known weak spots
- 0x480000-0x4a0000 mixes camera, track, rivals; some camera movers stay track (0x48df00, 0x48c820).
- FEng 2D UI (0x4f0000-0x520000): canon vs hud is ambiguous, mostly canon/low.
- A doc naming an address in passing seeds a wrong system (0x566e60, a pool allocator, is rivals/high).
- Tiny stubs and thunks follow neighbours only; 1,560 lifted functions have no evidence at all (unknown).
- Tried and rejected: tag a constructor by strings near the vtable it stores (agreed 37% with string seeds).
- 0x684000+ holds ~4,400 unwind funclets, thunks, misaligned lifter seeds, padding (1,725 rows); they take the owner's tag.
- Not mined: ref/ PS2 and NFSU1 notes, runtime coverage (census/cov/union.json).
