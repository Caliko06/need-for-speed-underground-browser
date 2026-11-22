# Hitches in `runs/w_L1/log.txt`: what `spike:` and `SMOOTHJOB` are

Log: `runs/w_L1/log.txt` (37,033 lines). Nothing was built or run; every number below comes from reading that log
and `pc/Speed.exe` (objdump, image base 0x400000) plus the host sources. Markers: **F** = read in the log or in the
code, **I** = inference from that evidence, **NV** = not verified (no run, no counter).

## 1. What the two line types are

`spike:` (5,671 lines) — `host/d3d9.c:817-841`, `spike_log()`, called at Present. It logs **only** when all of these
hold (F, source): the frame is longer than **25,000 us** Present-to-Present, the game state `[0x77a920] == 6` (race),
the race manager `[0x7361f0]` is set, and `[race_manager] != 1`. So the probe sees race frames only; menus and loads
are invisible to it. The payload is *not* a stack sample: `host/win32.c:559-566` `clk_site()` counts, per frame and on
the main thread only, every clock read (`QueryPerformanceCounter`, `GetTickCount`, `timeGetTime`) keyed by the
**return address** of the game's `call *0x69717c`; the line prints the 3 hottest sites with their counts.

- All 5,671 spikes have `reads 0 (0 KB, 0.0 ms)` (F). **No spike in this run is disk/file streaming.**
- The three sites are almost always the same family: `0x403a7a` in 5,670 of 5,671 (2 reads, the per-frame timer),
  `0x474c24`/`0x474aa9` in 5,053, `0x585bf7` in 353, `0x477de0`/`0x477511` in 263 (F).

`SMOOTHJOB` (425 lines) — `host/d3d9.c:2464`, only with `RN_FREELOG` set. It is **not** a hitch: it is the main thread
picking up one finished async car-smoothing job (`host/carsmooth.c`, worker thread) and copying its vertices into the
cache slot. 425 jobs for the whole race, cumulative worker CPU 45.9 ms = **0.11 ms per job** (F). Ignore it as a cause;
it only tells you how many car meshes were smoothed on first sight.

## 2. Size of the problem

- 5,671 spikes over 35,634 race frames (frames 3060 to 38693) = **15.9 %** of race frames over 25 ms (F).
- 335 s of the run sit inside spike frames (F, sum of the logged ms).
- `gpu:` windows (100 frames each, 389 of them) give the whole-run frame time: mean **23.0 ms** (43 fps), median
  17.4, p10 16.7, p90 30.2 (F). CPU raster thread: 0.8 % of the wall (F) — the raster backend is idle, this is not GPU.
- Not isolated stutters: **75 % of spikes are followed by another spike** (base rate 15.9 %), 87 % of spikes live in
  runs of 2+, longest run 248 consecutive frames, and the 116 runs of >= 10 frames hold **54 % of all spike frames**
  (mean 26 frames, mean 78.5 ms per frame) (F). The bad stretches are self-sustaining.

## 3. Spikes by frame time, with the events around them

Dominant site = the clock site with the most reads that frame. "nearby" = the event's line within +-3 frames.

| ms bucket | count | share | of spike time | substep loop `0x474c24` | limiter `0x585bf7` | per-car `0x477de0` | AIHIT near | FREE tp near | REFILL near | flow/load near |
|---|---|---|---|---|---|---|---|---|---|---|
| 25-30 | 1,662 | 29.3 % | 13.5 % | 84 % | 13 % | 2 % | 19 % | 18 % | 2 % | 1 % |
| 30-40 | 1,357 | 23.9 % | 13.8 % | 91 % | 6 % | 3 % | 19 % | 20 % | 2 % | 1 % |
| 40-60 | 1,154 | 20.3 % | 16.8 % | 91 % | 3 % | 6 % | 22 % | 24 % | 2 % | 2 % |
| 60-100 | 849 | 15.0 % | 19.2 % | 89 % | 2 % | 8 % | 22 % | 27 % | 2 % | 2 % |
| 100-150 | 304 | 5.4 % | 11.0 % | 92 % | 1 % | 7 % | 26 % | 30 % | 2 % | 3 % |
| 150-250 | 214 | 3.8 % | 12.1 % | 93 % | 0 % | 7 % | 30 % | 31 % | 2 % | 0 % |
| 250-500 | 118 | 2.1 % | 11.3 % | 86 % | 0 % | 14 % | 36 % | 36 % | 2 % | 1 % |
| 500+ | 13 | 0.2 % | 2.3 % | 85 % | 0 % | 15 % | 54 % | 38 % | 0 % | 0 % |

Readings (F for the numbers):

- The same loop dominates **every** bucket: 84-93 %. There is no separate class of "load hitch".
- `REFILLWHY` (traffic refill/spawn decisions) sits at 14.4 % of its own frames vs 15.9 % baseline: **no effect** (F).
- `flow open` / `flow fe` lines (file opens, HUD `.fng` sets) are near 1-3 % of spikes, no better than their base rate;
  27 `flow open` frames have 59 % spikes, but most are the race-start window (F).
- `AIHIT` and `FREE tp` (traffic teleport) rise monotonically with bucket: whatever makes a frame long also makes
  contact events and traffic respawns *log in that frame*; direction unknown (I).
- 88.6 % of spikes are dominated by the substep loop, 6.2 % by the limiter spin, 4.6 % by the per-car update (F).

## 4. Where the time is: two named loops (disassembly of `pc/Speed.exe`)

**The substep loop, `0x474a90`** (the physics step; `docs/re/race_ai.md:51`). At `0x474be4`:
`flds 0x8(%ebp)` / `fdivs 0x6fff10` (= **0.0084 s**) / `call 0x674898` / `incl %eax` -> `n = (int)(dt / 8.4 ms) + 1`;
then `0x474c10..0x474c4b` loops `n` times, each pass reading QPC (the site logged as `0x474c24`), calling the Euler
step `0x46aa40` and one more QPC read (F, disasm at `0x474be4-0x474c4b`).

The dt that reaches that division is **clamped**: the limiter's clock at `0x585c6a` loads `[0x6f0894] = 3.0` (a max of
3 frame targets) and `0x585c82`/`0x585ca3` multiply it by `0x6cc7d0 = 0.02` or `0x6cc7b0 = 0.016667` and keep the
smaller of dt and that product, i.e. **dt <= 60 ms or 50 ms** (F for the constants and the min pattern, I for which
branch). That is exactly what the log shows: over the bad stretches `0x474c24` reads / `0x474aa9` step calls = **6.0**
(168/28, 120/20, 188/32, 212/37), i.e. 6 substeps of 8.4 ms = 50 ms, the clamp, no matter whether the frame took 685 ms
or 143 ms (F). So the amplifier is real but saturates at ~6 steps: a frame longer than 50 ms cannot shorten itself,
and each of those 6 steps costs 4-7 ms per car in the worst frames instead of the ~0.1 ms it needs at 60 fps (I from
the same counts).

**The limiter spin, `0x585bf7`** (F, `host/win32.c:567-573` comment + disasm: `call *0x69717c` at `0x585bf5`, return
`0x585bf7`, loop until the wait expires). 353 spikes have 100 % of their clock reads there, median 32,939 reads in a
median 27.9 ms frame: that whole interval is the game spinning on its own 60 Hz limiter, not work. Their share falls to
0 % above 250 ms, as expected (a frame that is really late does not wait).

**`0x477de0`** (263 spikes) is a QPC read inside the per-car frame update `0x4774a0`; its count is cars x substeps
(x12 = 12 car updates = one pass over ~12 nearby cars, F for the site; I for the decomposition). These are the worst:
median 58.7 ms, mean 87.9 ms, and 14-15 % of the 250 ms+ buckets.

## 5. By position: player and traffic

Player position comes from `AIP fNNNN ... pos x,y,z` (one every 60 frames, F). Traffic comes from the `carpos` blocks
(21 cars every ~100 frames, `carpos <t> <idx> k3 x y`, F).

**Nearest traffic car vs spike rate** (control: every race frame with a `carpos` block in the previous 400 frames):

| nearest traffic | frames | spikes | rate |
|---|---|---|---|
| 0-10 m | 15,100 | 2,275 | 0.151 |
| 10-20 m | 11,962 | 2,033 | 0.170 |
| 20-30 m | 4,022 | 643 | 0.160 |
| 30-40 m | 1,697 | 174 | 0.103 |
| 50-60 m | 574 | 133 | 0.232 |
| 60-70 m | 247 | 82 | 0.332 |

86 % of race frames have traffic within 30 m and their rate is the baseline. Traffic in your face is **not** the
trigger; the mild rise at 50-100 m is thin data and coincides with faster road sections (I).

**The (1846,-727) spot.** That exact coordinate appears in this repo only as an `AIHIT` wall hit in other runs:
`runs/w_a/log.txt:17230` (f12390), `runs/w_b/log.txt:20286` (f14299), `runs/w_d/log.txt:2555` (f5237), all
`at 1846,-727,53` — a wall that a rival hits deterministically (F). In `w_L1`:

- the player never gets closer than **102 m** to it (minimum at frame 2880, spawn area 1861,-626) (F);
- 0 spikes within 200 m, 391 spikes (6.9 %) in the 200-400 m band, at a rate of **0.096**, i.e. *below* the 0.159
  baseline; 93 % of spikes happen 400 m+ away (F);
- the only traffic cars logged near it are `carpos 40.55 20 1790.5 -729.5` and `44.61 20 1782.7 -709.5` (F).

So in `w_L1` that wall is **not** a hitch hotspot (F). In `w_a` and `w_b` the +-120 frames around their 1846,-727 hit
are 241/241 spiking frames, but those two runs spike 19,416 and 17,911 times overall — they are bad everywhere, so the
coincidence says nothing about the spot (F for the counts, I for the reading). If the OWNER saw a hitch there, it is
from `w_a`/`w_b`, not from L1, and it needs its own log with `spike:` positions (NV).

## 6. The five worst spikes, 20 log lines around each

Frame 38329, 827.5 ms (`0x477de0` x12 = one car pass, 791 clock reads, no file reads):

```
AIHIT f38326 kind 2 car 01751300 sp 16.5 -> 11.0 act 1 car (nearest kind 3 at 4.2 m) d 133 at 727,256,50
spike: frame 38327 116.0 ms, clock 518: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
AIEV 38327 TODD act 1
spike: frame 38328 117.0 ms, clock 660: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
AIHIT f38328 kind 2 car 0175a690 sp 34.5 -> 25.3 act 1 car (nearest kind 3 at 3.9 m) d 201 at 753,320,49
spike: frame 38329 827.5 ms, clock 791: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
FREE tp car 8: 277 m (route +73) behind, player 92 m/s, frame 38329
spike: frame 38330 143.0 ms, clock 709: 0x474c24 x212 0x474aa9 x37 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
carpos 872.60 9 k3 740.9 395.4
carpos 872.60 10 k3 870.3 359.1 N
carpos 872.60 11 k3 994.6 355.9 N
carpos 872.60 12 k3 724.9 163.7
carpos 872.60 13 k3 748.4 317.2
carpos 872.60 14 k3 852.8 -15.1
carpos 872.60 15 k3 744.3 314.5
carpos 872.60 16 k3 722.6 269.6
```
(player at ~740,330 with 92 m/s and a pile of traffic cars at 724-870, 160-395, two rival-vs-rival hits 4 m apart.)

Frame 38230, 731.4 ms (same site class, a 12-car pass; worst of a 40-frame bad stretch):

```
carpos 858.33 25 k3 738.9 100.4 N
carpos 858.33 26 k3 724.7 197.0
carpos 858.33 27 k3 724.7 255.3
carpos 858.33 28 k3 851.5 352.9
carpos 858.33 29 k3 741.7 315.1
spike: frame 38230 731.4 ms, clock 531: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38231 197.7 ms, clock 485: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38232 92.9 ms, clock 486: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38233 56.1 ms, clock 465: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38234 109.4 ms, clock 495: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38235 115.6 ms, clock 473: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
AIEV 38235 WILL act 1
spike: frame 38236 52.4 ms, clock 487: 0x477de0 x18 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38237 180.9 ms, clock 589: 0x477de0 x23 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38238 53.1 ms, clock 461: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38239 65.7 ms, clock 464: 0x477de0 x12 0x403a7a x2 0x4040b4 x2, reads 0 (0 KB, 0.0 ms)
```
(identical clock pattern for 10 frames, 12 car updates each, ms from 731 down to 52: the work per car pass changes,
not the number of passes.)

Frame 37207, 685.5 ms (substep loop x168 = 28 step calls x 6 substeps = the 50 ms dt clamp; frame 38194 has x188 = 32 x 6):

```
spike: frame 37207 685.5 ms, clock 536: 0x474c24 x168 0x474aa9 x28 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 37207 TODD act 0
spike: frame 37208 143.4 ms, clock 532: 0x474c24 x168 0x474aa9 x28 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 37208 HUNTER nos
spike: frame 37209 217.8 ms, clock 563: 0x474c24 x168 0x474aa9 x28 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
spike: frame 37210 127.2 ms, clock 558: 0x474c24 x168 0x474aa9 x28 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIHIT f37210 kind 2 car 017783c0 sp 66.2 -> 42.1 act 7 wall (nearest kind 2 at 114.1 m) d 250 at 1676,630,50
spike: frame 37211 60.6 ms, clock 530: 0x474c24 x169 0x474aa9 x29 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 37211 WILL act 7
AIEV 37211 WILL nos
AIHIT f37211 kind 2 car 017783c0 sp 42.1 -> 36.8 act 7 wall (nearest kind 2 at 115.0 m) d 252 at 1676,631,50
carpos 789.20 21 k3 1459.8 633.4
carpos 789.20 22 k3 1197.6 359.2
carpos 789.20 23 k3 1411.2 554.5
carpos 789.20 24 k3 1510.4 672.5
carpos 789.20 25 k3 1295.4 448.2
```

Frame 9871, 653.5 ms (x120 / 20 cars, constant across the stretch):

```
AIEV 9869 AL nos
spike: frame 9870 364.0 ms, clock 541: 0x474c24 x120 0x474aa9 x20 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
spike: frame 9871 653.5 ms, clock 535: 0x474c24 x120 0x474aa9 x20 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 9871 TODD nos
spike: frame 9872 368.0 ms, clock 436: 0x474c24 x120 0x474aa9 x20 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
spike: frame 9873 271.7 ms, clock 443: 0x474c24 x120 0x474aa9 x20 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 9873 KAZ act 7
AIEV 9873 KAZ nos
spike: frame 9874 217.1 ms, clock 450: 0x474c24 x120 0x474aa9 x20 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
carpos 243.57 9 k3 1307.5 -299.7
carpos 243.57 10 k3 868.6 -157.5
carpos 243.57 11 k3 1494.3 -265.6
carpos 243.57 12 k3 856.1 -83.0
```

Frame 38194, 590.4 ms (wall hit repeated at 886,340 for 4 frames, x188):

```
AIEV 38189 AL act 12
spike: frame 38190 133.9 ms, clock 573: 0x474c24 x190 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
spike: frame 38191 99.5 ms, clock 536: 0x474c24 x186 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIHIT f38191 kind 2 car 01751300 sp 46.4 -> 42.3 act 7 wall (nearest kind 3 at 14.3 m) d 139 at 886,340,49
spike: frame 38192 118.4 ms, clock 548: 0x474c24 x190 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 38192 HUNTER nos
AIHIT f38192 kind 2 car 01751300 sp 42.3 -> 37.8 act 7 wall (nearest kind 3 at 14.5 m) d 139 at 884,340,49
spike: frame 38193 63.8 ms, clock 530: 0x474c24 x192 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIHIT f38193 kind 2 car 01751300 sp 37.8 -> 33.6 act 7 wall (nearest kind 3 at 14.7 m) d 138 at 882,340,49
spike: frame 38194 590.4 ms, clock 562: 0x474c24 x188 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
AIEV 38194 CHAD nos
spike: frame 38195 163.9 ms, clock 535: 0x474c24 x192 0x474aa9 x32 0x403a7a x2, reads 0 (0 KB, 0.0 ms)
carpos 854.27 9 k3 733.3 301.1
carpos 854.27 10 k3 1002.6 356.0 N
```

## 7. Ranked guess at the causes

1. **CPU overrun inside the physics substep loop, self-sustaining.** F: 88.6 % of spikes are dominated by the
   `0x474c24` site, which lives in a loop whose count is `(int)(dt/8.4 ms)+1`, dt clamped at 50-60 ms (so ~6 steps);
   75 % of spikes follow a spike and 54 % of spike frames sit in 116 stretches of >= 10 frames. I: the game is behind,
   runs its clamped 6 substeps, is still behind, and the stretch only ends when the car/work mix changes.
2. **Per-car cost blow-up (contact/solver), not per-car count.** F: inside the worst stretches the site count is
   constant (x120, x168, x188) while ms varies 5-10x — 6 substeps x 20-32 cars every frame, yet 4-7 ms per car-step
   against ~0.1 ms at 60 fps; `AIHIT` co-occurs in 19 % of 25-30 ms spikes rising to 54 % of 500 ms+, and the worst
   five all sit in stretches with rival-vs-rival or wall contact at 4-15 m. I: some per-car contact/solver path gets
   expensive when cars pile up; the clock sites cannot see inside a single step, so this is the open part.
3. **The 60 Hz limiter inflates 6.2 % of "spikes".** F: 353 frames are 100 % `0x585bf7` spin, ~33k QPC reads, median
   27.9 ms — the interval is the wait, not work. Do not chase these: they are not hitches, they are the limiter
   landing late (or its wait target being wrong: I).
4. **Nothing from I/O, loads, refills or the GPU.** F: 0 of 5,671 spikes read a file; `REFILLWHY` is at baseline;
   `flow`/load lines are 1-3 % of spikes; the raster thread uses 0.8 % of the wall time.

What would settle #1 vs #2 (NV, needs a run): a counter of `dt`, substep count and the per-step `now_us()` inside
`0x474a90` (or a host timer around `0x46aa40`) printed only when a frame passes 25 ms — that separates "more steps"
from "slower steps" without guessing. A second, cheaper probe: log `[0x6f0738]` (the step index written at 0x474c19)
with the spike line.

No patch is proposed: the evidence names two loops but not a defect, and any change to 8.4 ms, the substep count or the
limiter would change physics timing with nothing measured behind it. No `tools/recomp/cand/memo.py` was written.
