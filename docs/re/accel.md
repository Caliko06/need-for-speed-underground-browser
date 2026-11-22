# Acceleration chain and the knobs that scale it

Question from the OWNER: "0-60 in ~2.7 s feels too fast". Sources read this session: `docs/re/physics.md`,
`docs/archive/remaster/feel_2026-10-31.md` §5, `build/re_accel_2026-10-31.md` (read-only symlink to Main's), `census/hopper/decomp.c`
(0x46cff0, 0x4774a0, 0x46aa40, 0x585410), direct float reads of `pc/Speed.exe`.
Marks: F = read in code/data this or a prior RE session (cited), I = inference/model output, NV = not verified (no build, no run).

## 1. Formula chain, force to speed

Per frame, `PhysicsMover 0x4774a0`: inputs -> per-wheel scales -> substeps `0x46aa40` (semi-implicit Euler, dt/n) ->
`0x4783c0` -> CarState refresh `0x4789d0` (F, physics.md "How the pieces fit").

1. **Base torque** `Engine::ComputeTorque 0x46cff0` (F, decomp 0x46cff0):
   `T = curve(rpm) * Engine+0xa0` then `* 1.05` if `Engine+0x1d != 0` (float `0x700024`, one reader only).
   `curve` = 9 samples 850..9000 rpm at `Engine+0x200..0x220` (ctor 0x46c7c0), turbo samples `+0x224..0x244`
   already folded into the curve by `0x575bc0` (F, physics.md, build/re_accel §3).
2. **Nitrous** is added after that product: `+ curve(rpm) * info+0x2ac` (F, same function). So nitrous L3 (6 s, strength
   0.5) does not scale with the 1.05 constant, and is not on during a 0-60 (F/I: not pressed in the logged run).
3. **Wheel force** `F = T * gear * fd / r` (F for the fields, I for the port): gears/fd at `DriveTrain+0x54` /
   `phys+0x1b0..`, `r = 0.3266`, `fd = split*[0x1bc] + (1-split)*[0x1b8]` (physics.md; build/re_accel §3).
4. **Drag** is a body force, not a wheel term: `body+0x1e8 * body+0x1e4` in `0x585410` (F). Stock `phys+0x290 = 0`,
   so the shipped car has no body drag; the ported table integration uses `k = 0.00043` (I, build/re_accel §7).
5. **Acceleration** `a = (F - k v^2) / mass`, mass in tonnes, torque kN.m, force kN (F for units, I for the port).
6. **Shift**: the acceleration table `0x581b30` rescans the shift rpm in 50 rpm steps from (idle+redline)/2; R34 lands at
   7900 (F, build/re_accel §3). Each gear change costs ~0.25-0.4 s of torque interruption in the model (I, fitted there
   and re-fitted here).
7. **Weight**: `0x576250` sets `mass = row[0] * stock_mass`, rows at spec chunk `0x2b0`; L1/L2/L3 = x0.932/0.866/0.800
   for the R34 (F, build/re_accel §4).
8. **Turbo**: level rows at `0x520` are 9 floats copied to `info+0x224` and added into the curve (F, tuning.md §1);
   R34 stock peak 0.3428, turbo L1 0.3496 kN.m (F, build/re_accel §4).
9. **Engine / ECU / transmission** change the curve and the rpm limits; transmission L3 only touches top gear and
   `out+0x1cc`, so 0-60 is unchanged (F, build/re_accel §4).

## 2. Constants and addresses that scale acceleration

| Knob | Address | Value / source | What it scales | Mark |
|---|---|---|---|---|
| Torque boost flag multiplier | `0x700024` (float) | 1.05, single reader 0x46cff0 | whole torque of every car with `Engine+0x74 != 0` (AI too); not nitrous | F |
| Engine torque multiplier | `Engine+0xa0` | per car, set by PhysicsMover ctor 0x476840 | torque | F (prior), NV here |
| Torque curve / turbo curve | `Engine+0x200..0x244` | built by 0x575bc0 from spec rows 0x3a0/0x520 | torque vs rpm | F (prior) |
| Nitrous strength | `phys+0x2ac` (via `Engine+0x7`) | 0 / 0.5 at L3 | only while NOS burns | F |
| Mass | `phys+0x110` | 0x576250, rows at 0x2b0 | inertia of the whole chain | F (prior) |
| Gears / final drive | `phys+0x1b0..`, `+0x1b8/1bc` | transmission rows 0x2e0 | rpm vs speed, force multiplication | F (prior) |
| Body drag | `body+0x1e4/0x1e8` | `phys+0x290` = 0 stock | top speed only | F |
| Global power/grip scale | `car+0x404` via `0x479160` | 1.0 unless rubber-band | engine + grip + drag | F (physics.md d) |
| Rear grip cap | `0x6ffdd4` | 0.35 stock / 0.18 Remaster | launch traction only, not 0-60 here | F |

The only in-exe global that scales acceleration without touching data chunks, per-car torque curves or mass is
**`0x700024`**: a 4-byte float, read once, single consumer. Mass/transmission/grip constants are per-level rows or
per-car fields; patching those means either data edits in GLOBALB.BUN or a cave.

## 3. The OWNER's levels (F, build/re_accel §2)

R34 `SKYLINE`, spec `(weight 3, susp 1, engine 0, turbo 1, nitrous 3, ECU 0, trans 3, tires 3, brakes 2, spoiler 0, gf 0)`:
mass 1.5 -> 1.2 t, peak torque 0.3496, gears 1-2 and fd unchanged, tires never traction-limited (mu ~2 vs ~1 g
demand), nitrous not pressed. So the relevant chain is: mass x0.8, turbo L1, x1.05, ~0.4 s per shift.

## 4. Port of the chain, calibrated (I: model, not a measurement)

Model: 9-point curve interpolation, `a = (T*gear*fd/r - k v^2)/m`, shift at 7900 rpm, dt 0.5 ms, target 26.82 m/s.
Reproduces `build/re_accel_2026-10-31.md` within 0.02 s:

| case | prior report | this port |
|---|---|---|
| stock (m 1.5) | 3.63 | 3.56 |
| installed, no x1.05, no shift loss | 2.86 | 2.85 |
| installed, x1.05, no shift loss | 2.72 | 2.71 |
| installed, x1.05, 0.25 s shift | 3.12 | 2.96 |
| installed, x1.05, 0.4 s shift | 3.13-3.27 | 3.11 |

The logged Original run (0 -> 9.9 -> 20.0 -> 25.4 -> 30.5 m/s) crosses 60 mph at ~3.1-3.3 s, so the "2.7 s" the
OWNER recalls is the ideal no-shift figure, not the measured one (F log, I reading).

## 5. Candidate patch -> predicted 0-60 (OWNER's levels)

Patch = overwrite the float at `0x700024` (old bytes `66 66 86 3f` = 1.05). All predictions are I (model, same
cartesian chain as above); the shift columns bound the shift loss.

| patch (float at 0x700024) | new bytes | 0-60, 0.4 s shift | 0-60, 0.25 s shift | 0-60, no shift |
|---|---|---|---|---|
| 1.05 (stock, today) | `6666863f` | 3.11 | 2.96 | 2.71 |
| 1.00 (drop the boost only) | `0000803f` | 3.25 | 3.10 | 2.85 |
| 0.95 | `3333733f` | 3.40 | 3.25 | 3.00 |
| 0.90 | `6666663f` | 3.57 | 3.42 | 3.17 |
| 0.85 | `9a99593f` | 3.76 | 3.61 | 3.36 |
| 0.80 | `cdcc4c3f` | 3.97 | 3.82 | 3.57 |
| 0.75 | `0000403f` | 4.21 | 4.06 | 3.81 |
| 0.70 | `3333333f` | 4.49 | 4.34 | 4.09 |

Reference for scale: a stock 1.5 t R34 runs 3.56 s in the same model. k = 0.90 puts the OWNER's upgraded car at
about stock time (3.57 s); k = 0.85 puts it behind stock (3.76 s). That is the trade the table shows.

## 6. Limits and open points

- The patch is global: it slows every car with `Engine+0x74 != 0` (AI included) and leaves nitrous untouched. If the
  OWNER wants "calmer acceleration" as a player-only feel, this is too blunt; a cave on 0x46cff0 keyed on the player
  ride would be the surgical version.
- No run, no build, no Chrome, no ghosts: every 0-60 here is model output. The one precedent is the logged Original
  run, which the model matches to ~0.2 s at 5 s.
- Whether the shipped game with the same save does 3.1-3.3 s is still NV (needs the Wine reference run the earlier
  report asked for).
- Alternative knobs not written as candidates: mass rows (GLOBALB.BUN data), per-car `Engine+0xa0`, the accel table
  `0x581b30` shift rpm (`DAT_00700030`). All need either data edits or a cave; parked.
