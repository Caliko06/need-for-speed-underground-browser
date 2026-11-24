# Slipstream (rebufo): car+0x47c, how much speed, and who gets it

> Source: `docs/re/ai_draft.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 26

# Slipstream (rebufo): car+0x47c, how much speed, and who gets it

Question: how many m/s does the draft give on a straight, is it applied to the player, rivals and traffic the same, does the
player feel it, and a log-only probe. V = read in code/data, I = inference, U = open. Nothing was run. Tools: census/hopper/decomp.c,
tools/recomp/asm.py (float tables from pc/Speed.exe), docs/re/physics.md and race_ai.md.

## Answer first

1. **In a stock car it gives 0 m/s**, to the player and to rivals. V for the data, I for the consequence (below).
   The draft is written into the aero factor `1 - car+0x47c` (V) and that factor is only ever multiplied into the aero drag
   product, whose coefficient `body+0x1e4` = `phys+0x290` is **0.0 in all 35 cars** (V, physics.md). Zero times anything is zero.
   So top speed with draft 0 and with draft 0.9 is the same number: the straight ends on gearing / rolling resistance, not aero.
2. Applied the **same way to every car in the race list**: `/0x426450/` sums the pair terms over all cars of `[0x7361f8]`, with no
   kind test, and both movers (`0x479160`, `0x474d40`) publish it for every car. V. Traffic is a *source* like any other car
   (`/0x426300/` only needs speed >= 1 m/s and <= 60 m), but traffic itself is driven by BeltMover (mode 4, spline + lateral) and
   never by the force mover, so for traffic the value is written and unused. V for the movers, I for "unused".
3. The player **does feel something, but it is not a force**: `/0x43fa90/` (from `RacingCar::UpdateStyleItems 0x43f240`) tests
   `car+0x3d4 >= 20.116` and `car+0x47c >= thr` and calls `StyleItem::Trigger 0x436230`, passing `car+0x47c` as the strength. V.
   That is the style/reputation item (sound + style bar), i.e. the game sells you the tow without pushing the car.
## The chain, address by address (V unless marked)

- Every frame `0x4774a0` -> `0x479160(arg = car+0x404)`:
  `engine+0xa0 = arg` (torque x), `body+0x1e8 = arg` (drag scale), `wheel+0x17c = arg` (grip), `[body?+0x50]+0xc = 1 - car+0x47c`.
  If `car+0x86c != 0 && [[car+0x3c]+0x1c] != 0` the power part is x0.0055 (`0x3bb40000`).
- `0x474a90` -> `0x474d40`: same set, with `car+0x404` as the drag/engine scale and the same `1 - car+0x47c` into `+0xc`; it also
  writes a throttle-gated power cut `0.008 * (1 - something)` into `+0x13c`/`+0x138` (`0x3c03126f`, `0x400f2b02` = 2.237).
- The only force consumer is `0x585410`, and its aero block is `if (body+0x1e4 != 0)`: drag = `(body+0x1e8 * body+0x1e4 + 1.9)`
  x speed ramp (x1.03 if `body+0x4f`) and then a speed-capped vector push against `-v/|v|`, capped by the 1200.0 table
  (0xc0400000 = -3.0, 0x44960000 = 1200.0). `body+0x1e4` = drag coefficient = `phys+0x290` = **0.0 stock** (physics.md, data read) ->
  the block is skipped and the `1 - draft` factor is never read by any force path. V for the gate and the data, I for "never read".
- Where `1 - car+0x47c` is **read**: only `0x456830` (AI speed prediction) and `0x43fa90` (style item). Nothing in 0x585410 reads +0xc. V.
- `0x456830` is the rival's own speed model, used by the Pass reach test and the avoid checks:
  `aero = (1 - car+0x47c) * body+0x260 * v² / body+0x110`, then `v_pred = var_18 - aero + gravity(0x7000ac * v)`, with
  `var_18 = sub_583ea0(v / car+0x404)` scaled by the gear/rev factor from `sub_57f2b0` when `body+0x424 != 0xff`.
  It uses a *different* coefficient (`body+0x260`, not `0x1e4`), so it can be nonzero even when the physics aero path is dead. U: its
  stock value was not read this session. Effect: it only changes the rival's *predicted* speed, never the force on the car.

## The pair term that fills car+0x47c (V, values read from the exe)

`0x426450` (called from `World::Step 0x420b40`) = clamp(sum over all cars of `0x426300(other, self)`, 0, **0.9** `0x6b7b54`).
Per pair: `other+0x3d4 >= 1.0` (`0x706288`), distance (3D, +0x60) clamped to **60.0 m** (`0x70629c`), cosine of the unit gap vector
against a heading >= cos_min, then `w = falloff(dist / reach)` and the cosine ramp, product.

- falloff `0x700d3c`: **1, 0.9, 0.75, 0.55, 0.3, 0** over `dist/reach` in 6 equal steps.
- reach table `0x7062b4`: {base 2.5, cap 255, slope 0.5} -> reach ~0.5 per m/s, 2.5 m at 0 and ~32 m at 60 m/s. I (`sub_583f20`).
- cosine: `(cos - c0) / (1 - c0)` with c0 near 0.95 (`0x6b7b50`; `0x6b7b40-44` holds 0.65 / 0.95 / 0.9). I for the exact c0.
- Full 1.0 needs `dist/reach < 1/6` (~5 m at 60 m/s) and cos = 1; one car at 15 m / 60 m/s gives ~0.58, 0.9 needs several. I.
- Which car's heading: `sub_567370` at `0x426300` has no visible argument. U (race_ai.md says the same).

## Wave 2: the rule that makes it real (RN_DRAFT_K, host/rivals.c)

Car+0x404 is the scale of engine torque (`engine+0xa0`), dead drag (`body+0x1e8`) and grip (`wheel+0x17c`), read per frame by
`0x479160`. Writers: `0x44bd10` for rivals (rubber band, `0x44bff5`, `max(scale,1)` every 0.3 s) and **only** `0x429b10`
(`UpdateTwoHumanCatchUp`, `0x429b8b`) for the player, i.e. only with two humans; a single player keeps 1.0 from the ctor. V.
`0x485c00` also stores `+0x404` but it is `TrackCarCameraMover::Update`, a camera field. V.

Rule (`RN_DRAFT_K=<k>`, off by default, logs `DRAFTK` 1/s): every present, kind 1 and 2, `car+0x404 = base * (1 + k*draft)` when
`draft > 0.2`. `base` = the value the game left; if it differs from ours it is the new base, so rubber band and tow never compound.
Traffic skipped (BeltMover, no force mover).

Arithmetic for k. With the aero path dead the terminal speed is where drive force meets the remaining resistance (rolling, drivetrain,
rev limiter), `F(v) = R`. Near v0 in a fixed gear the engine is at constant power, `F ~ P/v`, so scaling the torque (and P) by
`s = 1 + k*d` scales the terminal speed the same way:

  `s*F(v') = R, F(v) = F0*v0/v  ->  v' = s*v0  ->  dv/v0 = k*d`

| k | d = 0.9 (cap) | d = 0.58 (one car, 15 m) | at 60 m/s, full draft |
|---|---|---|---|
| 0.050 | +4.50 % | +2.90 % | 60 -> 62.7 m/s |
| **0.055** | **+4.95 %** | **+3.19 %** | **60 -> 62.97 m/s** |
| 0.060 | +5.40 % | +3.48 % | 60 -> 63.24 m/s |

k = 0.055 lands inside the 4-6 % window at the 0.9 cap (I, model above, not a measurement). Caveat: on the rev limiter in top gear the
extra torque adds no speed and 4-6 % would need gearing. Side effects: +4.95 % grip in the tow, no drag (coefficient 0), and `0x456830`
divides by 0x404, so rivals also predict the player 5 % faster. I.
## Probes (log only, host/aitel.c)

`AIDR` 1/s per player (kind 1) and rival (kind 2): `draft` = `car+0x47c`, `sp`, `d`/`lat` to the player. `AIP` adds the player's
`draft` and `tow>0.2 N/M x%` (seconds in tow over seconds in the race). `RN_AILOG=1` in a race ghost, `grep -E "AIDR|AIP"`; with
`RN_DRAFT_K=0.055` compare `grep DRAFTK` against the speeds.
