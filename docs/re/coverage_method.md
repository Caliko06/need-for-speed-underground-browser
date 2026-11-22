# Coverage: which guest functions ever ran

Count at function ENTRY, direct calls included. Off by default; the normal build is byte-identical (md5 of build/gen
`07b9d06a976fb6136bd302f1ed3619a6` before and after, `census/lift_report.json` unchanged by the lift).
## How it works
- `tools/recomp/lift.py`: with `Lifter.cov` set, each `f_xxxx` starts with `RN_COV(RNI_xxxx);` before `goto`.
  A tail jump to another function (`f_x(c); return;`) enters that function too, so it counts.
- `tools/recomp/build.py` with `RN_COV=1`: lifts to `build/gen_cov` (funcs.h gets `RNI_<addr>` = position in the sorted
  table `rn_fn_addr`, and `RN_COV(k)` = one byte store), objects in `build/obj_cov`, binary `build/speed_cov`. The normal
  files are not touched; `census/lift_report.json` is not rewritten by a cov build.
- `host/cov.c`: the byte map, and `rn_cov_report()` (empty in a normal build). Called from `dispatch_report` (stop,
  halt, RN_SECS watchdog) and before the two `_exit` of RN_JUMP / RN_CAREER in `host/input.c`.
  `RN_COV_OUT=file` gets `"RNCV"`, u32 N, bitmap "entered", bitmap "seen by rn_call" (the old measure, kept for
  comparison; set in `host/dispatch.c` under `#ifdef RN_COV`). Log line: `coverage: N of 13739 (rn_call alone saw M)`.
## Rerun
    RN_COV=1 .venv/bin/python tools/recomp/build.py native          # about 3 min, all cores
    python3 tools/census/cov_run.py run [scenario ...]               # default all; build/cov/<s>.bin, census/cov/<s>.json
    python3 tools/census/cov_run.py union                            # census/cov/union.{bin,json} + the checks
Runs are native, off-screen (`--shot`), through macgate.sh, RN_TURBO=4, each bounded by RN_SECS (title 60, title_skip 30,
garage/options 45, movies 420, races: the RN_JUMP row ends on its own, bound 420). Keys and RN_JUMP rows come from
`tools/completion.py`. Run dirs `build/cov/run/<s>/` (game hard-linked, a copy of save/).
## Numbers (functions entered, of 13,739; second column = what rn_call alone saw)
title 2,776 / 1,044 | title_skip 2,800 / 1,054 | garage 3,325 / 1,117 | options 3,263 / 1,121 | movies 5,242 / 1,639
circuit 5,536 / 1,736 | sprint 5,524 / 1,735 | drag 5,416 / 1,704 | drift 5,106 / 1,580 | lapko 5,490 / 1,724
freerun (1002) 5,390 / 1,719 | world (1010) 5,384 / 1,724
**Union 6,038 of 13,739 = 43.9 %**; rn_call alone, same runs: 1,876 (31.1 % of the union).
Scenarios: title = no keys (the intro movie and its idle replay play); title_skip = the first tap of every key run, then idle;
movies = career0 (new profile, 01_DAY, 02_FAN_S, 1003, ExtroFMV; the OWNER's save is not used); world = Free Run on 1010
with the merged TRACKB (it ends about 30 s wall after the race starts; no long drive).
Not run: career events past the career0 prologue, other tracks, pause/replay, the OWNER's sessions: the union is a floor.
## Sanity checks
- (a) title is NOT a strict subset of circuit: title_skip 2,800, 2 outside circuit (0x4de520, 0x4de3c0; chain 0x4df400
  > 0x4de520 > 0x4de3c0). The full title run adds 0x64583f and 0x64635f (the idle replay of the intro movie, also seen in
  options). Reading: a branch on the title screen the race route never takes, not an instrument error. 2,798 of 2,800 are inside.
- (b) 0x674898: entered in all 12 runs, seen by rn_call in none; the lifter calls it as plain C. 4,162 functions in the
  union were entered and never seen by rn_call in any run.
- (c) union 6,038 vs old 1,876; the old set is a strict subset (old not in new: 0). Per run it is 1,736 vs 5,536 (circuit).
## Limits
Entry of a function, not instructions inside it. ABK modules (`M_` functions, build/gen/abk.c) are not counted. Threads
write the map without a lock (byte stores). A run killed by the OS writes nothing.

Copies of the 12 raw bitmaps (3,444 B each: header, `entered`, `seen by rn_call`) are kept in census/cov/bitmaps/ so the union can be rebuilt after build/ is cleaned (external audit 2026-10-29: census/cov/<s>.json keep only counts).

Second wave (2026-10-29 later): 10 more scenarios (circuit2 1006, sprint2 1108, lapko2 1005, freerun2 1004, drag2 1203, drift2 1301, cj3, cj12, cj25, cj60). Union 6,038 -> 6,067 (44.2%): more tracks of the same modes add almost nothing, so the ceiling of this method is near. drag2 stops at `d3d9: Present with rects/window` (host 0x4b585b), 3,212 functions. cj3 and cj25 ran to the 420 s bound without finishing. Bitmaps for all 22 are in census/cov/bitmaps/.
