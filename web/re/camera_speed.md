# Camera at speed: distance, height, pitch, FOV

> Source: `docs/re/camera_speed.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 40

# Camera at speed: distance, height, pitch, FOV

Wish: "camera low/flat and car small at speed". Tools: capstone on the unpatched `pc/Speed.exe` (read-only, no build,
no run), `census/hopper/decomp.c`, `docs/re/camera*.md`, the archived feel notes (not published) §1, port code
`host/d3d9.c` + `web/tune.js`. Marks: **F** = read in bytes/code, **I** = inferred from F, **NV** = not verified.

## Answer

- **The exe has no speed term for distance, height or FOV (F, negative result).** `0x48bcb0` (Cubic update, the default
  race camera) never reads `car+0x3d4` (speed). The row values are used as they sit in `CarTypeInfo` at **any** speed:
  far chase `d = -5.80 m`, `h = 1.70 m`; close chase `-4.70 / 1.70`; high chase `-5.80 / 3.45` (R34, F). FOV is
  `0x6fbdf4[pov]` and nothing else (F, bytes `dc32 dc32 0040 0040 dc32 0000` = 71.5 / 71.5 / 90 / 90 / 71.5 deg).
- **The only speed-dependent camera geometry is the look direction (F).** `0x48b530` blends the car's forward with its
  velocity through the curve `0x705b20` read at the speed `car+0x3d4`, and applies that blend **twice** (weight of the
  velocity = `f²`, F, see §3). Above 13 m/s (47 km/h) the camera looks 100 % along the velocity (I: it is a yaw follow,
  not a distance).
- **Pitch is deliberately killed (F).** The z of that look direction is multiplied by a ramp
  `r = clamp(1 - (now - mover+0x4c)·0.00025 / 2, 0, 1)` (ticks of 4000/s), i.e. the camera is level 2 s after every
  camera cut. In steady driving the camera looks exactly horizontal: it never tilts up as speed grows. That is the
  "flat".
- **"Car small" is not the exe, it is the port's projection (F).** The 2026-10-22 cave (`0x40debb`, `0x707fc0`) rebuilds
  the projection as the PS2 vertical view: 64.4 deg vertical / 96 deg horizontal at 16:9, against 56.7 v / 87.6 h for the
  PC 4:3 view (Hor+). Car height on screen ∝ `1/(tan(vfov/2)·d)`, so the port draws the car at **0.86x** the 4:3 size at
  rest and at every speed (I, from the F numbers; §5). `?chasecam` (`CHASE_BACK`/`CHASE_LOW` = 0.0) and `?speedfov`
  (`SPEEDFOV` = 0) no longer add anything (F, `host/d3d9.c:944-951`, `web/tune.js:33-39`); `CHASE_TILT` 8 deg only
  steepens the eye, it does not move it (F).

## 1. Where the numbers come from (F, instructions read with capstone)

| Quantity | Site | Instruction | Value |
|---|---|---|---|
| speed input | `0x48b5f9` | `fld [esi+0x3d4]` (`esi` = player car), pushed to `0x583f20` | m/s (`docs/re/camera_jump.md` §1, F) |
| blend curve | `0x48b603` | `push 0x705b20`, `call 0x583f20` | 2 points, clamps outside (F) |
| second blend | `0x48b61e..0x48b681` | `x·f`, then `+ (1-f)·forward` on all 3 axes | velocity weight = `f²` (F) |
| pitch leveling | `0x48b685..0x48b6d7` | `fild dt`, `·[0x6cca38]` (0.00025), `/ [0x6b6e2c]` (2.0), `fsubr 1.0`, clamp 0..1, `·dir.z` | `r` → 0 at 2 s (F) |
| row read | `0x48ba2a..0x48ba44` | `[esi+4]`→d, `[esi+0xc]`→lat, `[esi+8]`→h, `[esi+2]`→aux | per-POV row (F) |
| tan(yaw) scale | `0x48ba48..0x48ba77` | `0x674898()`+aux → `sin(a)/sin(a+0x4000)` = `tan(a)` | a yaw, not a speed (F; corrects the "sine ratio at speed" guess in `feel_candidates` §3) |
| chase eye/target | `0x48bb21..0x48bb36` | POV 0/1/4: target z = `d·tan(a) + h`, lateral = 0 | pitch swings with yaw error (F) |
| contact eye | `0x48bafd` | eye `· [0x6b6eb0]` (1.3) when `car+0x38 != 0`, `car+0x3cc <= 2` | 1.3x, no speed (F) |
| FOV | `0x48bbed` | `movzx eax, word [pov*2 + 0x6fbdf4]` → view `+8` | constant per POV (F) |
| follow lag | `0x48ec80..0x48ecbd` | `1/filled`, ring at `+8`, count `+5` | moving average, not speed (F) |
| smoothing | `0x48afd0` | `edi[0xa] = 0x41200000`, `sub_48ead0(0x3f000000)` | 10.0 time constant, 0.5 (F) |

## 2. Curves at `0x705b20` (F, bytes)

`0x705b20` is a *descriptor*: `{ptr = 0x705b10, count = 2}`. The data lives at `0x705b10`:

| addr | value | meaning |
|---|---|---|
| `0x705b10` | `8.0` (`00000041`) | speed where the velocity look starts, m/s |
| `0x705b14` | `0.0` (`00000000`) | weight there |
| `0x705b18` | `13.0` (`00005041`) | speed where it is complete, m/s |
| `0x705b1c` | `1.0` (`0000803f`) | weight there |

`0x583f20` clamps below the first x to y0, above the last x to yN, interpolates linearly between points (F).
Effective velocity weight (`f²`, F for the math, I for reading it as the yaw follow):

| speed m/s (km/h) | 8 (29) | 10 (36) | 13 (47) | 20 (72) | 30 (108) | 60 (216) | 90 (324) |
|---|---|---|---|---|---|---|---|
| f | 0.00 | 0.40 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| velocity weight `f²` | 0.00 | 0.16 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

The same descriptor is read by `0x489690` (type 1, the fallback mover) and by `0x48cbd0` / `0x48da20` (drag-race
movers), so a curve patch moves those too (F, callers of `0x583f20` + literal `0x705b20` per function).

There is **no** second curve for distance or height anywhere in the chase path: the only other curves in the camera
are the jump-view ones (`0x7062fc` speed, `0x7062cc` height, `0x7062e4` distance, F, `camera.md` §2) and they belong to
modes 6/7, not to the chase.

## 3. Shipped feel vs the port, at speed

| | distance 30 m/s | 60 m/s | 90 m/s | height 30/60/90 | FOV | car height on screen |
|---|---|---|---|---|---|---|
| Speed.exe, PC 4:3 (Hor+ ref) | 5.80 | 5.80 | 5.80 | 1.70 / 1.70 / 1.70 | 71.5 h, 56.7 v | 1.00 |
| Speed.exe, own 16:9 (anamorphic, F from `patches.py` comment) | 5.80 | 5.80 | 5.80 | 1.70 | 71.5 h, 48.0 anamorphic | 1.21 (stretched, `I`) |
| Port now (cave `0x40debb`, default `?hfov`) | 5.80 | 5.80 | 5.80 | 1.70 | 96 h, 64.4 v | **0.86** (`I`) |
| Port with `?chasecam=1` (`CHASE_TILT` 8) | 5.80 | 5.80 | 5.80 | 2.49 (far row, `-5.51/2.49`) | same | 0.86, pitch 24.3 deg instead of 16.3 |
| Port with `?speedfov=10` (off by default) | 5.80 | 5.80 | 5.80 | 1.70 | up to 80.5 → 105 h / 73 v | 0.59 (`I`, the `feel` §1 0.65 figure) |

Pitch of the shipped chase: `atan(h/d) = atan(1.7/5.8) = 16.3 deg` at every speed (F inputs, I on the on-screen read),
leveled to 0 deg of *look* pitch by the `r` ramp (§1) 2 s after a cut.

## 4. Three candidates (patches in a candidate file, not published, all `when=lambda: False`)

Numbers are the row values the mover would use; `size` = `1/(tan(vfov/2)·d)` relative to the 4:3 reference (I).

**A. FOV table: recover the 4:3 car size.** `0x6fbdf4` POV 0, 1, 4: `13020` (71.5 deg) → `11527` (63.3 deg). Under the
port cave that is 56.7 deg vertical, i.e. the PC 4:3 view (Hor+). Distance/height untouched at every speed.

| speed | d | h | vfov | size vs now |
|---|---|---|---|---|
| 30 / 60 / 90 m/s | 5.80 | 1.70 | 56.7 v | 1.00 / 0.86 = **+16 %** |

Second value if the OWNER wants the exe's own 16:9 pixel scale instead: `9812` (53.9 deg) → 48.0 v, +21 %.
Caveat: the table is global, so hood/bumper POV 2/3 stay at 90 deg and the mirror (`0x4e20`, `0x485300`) is separate (F).

**B. Curve knee: stop yawing off the car at city speed.** `0x705b10` 8.0 → 25.0 and `0x705b18` 13.0 → 45.0. Velocity
weight becomes `f²` with `f = (v-25)/20` clamped: at 30 m/s 6 %, at 60 m/s 78 %, at 90 m/s 100 %. Distance/height/FOV
unchanged; what changes is how far the aim point slides off the car when the car slides (drift, kerb, throttle steer).

| speed | f | velocity weight | target shift with a 10 deg slip (approx, I) |
|---|---|---|---|
| 30 m/s | 0.25 | 6 % | `tan(0.6 deg)·5.8` = 0.06 m (was 1.02 m) |
| 60 m/s | 1.00 | 100 % | 1.02 m (unchanged) |
| 90 m/s | 1.00 | 100 % | 1.02 m (unchanged) |

**C. Speed ramp on the eye (needs a cave, no data site exists).** Hook `0x48ba2a` (6 bytes `8b4e048b560c`, F): scale
`[esi+4]` (d) and `[esi+8]` (h) by a speed ramp before the mover stores them. Proposed shape, the same 25..75 m/s
smoothstep the port already uses for FOV: `d(v) = 5.80·(1 - 0.10·t)`, `h(v) = 1.70·(1 + 0.15·t)`.

| speed | t | d | h | eye pitch | size vs now |
|---|---|---|---|---|---|
| 30 m/s | 0.028 | 5.78 | 1.71 | 16.4 deg | +0.3 % |
| 60 m/s | 0.784 | 5.35 | 1.90 | 19.6 deg | +8.5 % |
| 90 m/s | 1.000 | 5.22 | 1.96 | 20.5 deg | +11.1 % |

This is the one the OWNER asked for in words ("steeper and closer as speed grows") but it is the only one that is **not**
a plain byte patch: the cave is designed, not assembled or built (**NV**). The 5.8/1.7 numbers are the R34 rows (F); the
GOLF/FOCUS/PEUGOT rows are 1.9 high (F), so the ramp has to be relative, not absolute.

## Open (U)

- Which row set a normal race uses (`[0x7364a0]`), so whether the numbers above are the normal or the `==3` set.
- Whether the 10.0 smoother and the 16-entry average are the whole "camera is left behind" feel; no measurement was made.
- No run, no build: every "expected" number is arithmetic on the row and FOV values, not a screenshot.
