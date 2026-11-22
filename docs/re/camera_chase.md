# Chase camera map (Speed.exe PC)

Tool for every line: G = Ghidra export `census/ghidra/decomp_*.c` (read this session), C = capstone `tools/recomp/asm.py dis`,
D = bytes read with python struct from the unpatched exe. V = read in code or bytes. I = inferred. U = still open.
Earlier notes: `docs/re/camera.md`. No `q_*.py` or new DecompAt run was needed: the export already had every function below.

## Flow of one frame (default race camera, mover type 0x11)

1. `0x48bcb0` (update, G+C). Picks the player car `mover+0x2c` (via `0x41ffe0`, V). Calls `0x48ead0(0.5)` (`[0x6b6e28]`) and `0x48ec00`.
2. `0x48ec00` is a **moving average**, not a spline (V, G). Ring buffer of 16-byte entries: count `+5`, filled `+6`, index `+7`,
   buffer `+8`, running sum `+0x10`, average `+0x20`. It adds the new vector, removes the oldest, divides by the filled count.
3. `0x47d680` finds the row of the POV code in the car's CarTypeInfo rows `[[car+0xc]+0xb50]` (V, C; set 2 at `+0x60` when `[0x7364a0] == 3`).
4. `0x48b8c0` SetDesired (V, G+C). For POV 0, 1, 4 it builds an eye and a target relative to the car:
   - `0x48b530` makes the look direction: blend of the car forward `car+0x90..0x98` and the velocity direction `car+0x70..0x78`
     (if forward dot velocity is negative the velocity is flipped by `[0x6ccc08]` = -2.0). The blend weight is the piecewise curve
     `0x705b20` (ptr `0x705b10`, 2 points: (8, 0) and (13, 1)) read at `car+0x3d4` (D). Below 8 the camera looks along the car, above 13
     along its velocity. This is the existing drift/slide follow. The unit of `car+0x3d4` is U (I: speed).
   - The z part is scaled by a ramp `(now - mover[0x13]) * 0.00025 / 2.0`, clamped 0..1 (`[0x6cca38]`, `[0x6b6e2c]`): after a camera cut
     (`mover[0x13]` = clock `0x73ad34`) the camera rises over 2 s.
   - eye offset = look * row.distance + row.height (up); lateral = row `+0xc`. Result is written as targets `+8` of three small
     interpolators `mover[0xc], [0xd], [0xe]` (`0x4831c0`); `0x483220` makes the cubic coefficients (`[0x6cc7ac]`).
   - FOV: `[0x6fbdf4 + 2 * pov]` goes to `mover[0xc]+8` (speedfov path, do not touch).
   - Wall/clearance: `0x483430` clamps the offset vector between two limit vectors (min/max per axis).
   - When the car is in contact (`car+0x38 != 0` and `car+0x3cc < 3`, vtable slot `+0x24` true) the eye is scaled by `[0x6b6eb0]` = 1.3.
5. Back in `0x48bcb0`: `0x575040(mover[4])` camera shake, `0x483640` noise (tables `0x6b6eb8` normal, `0x6b6f08` when `[0x78a344]` or `[0x7361a8]`),
   `0x483b90` MinGapTopology (camera vs world), `0x47d070` SetCameraMatrix. Smoothing constants: sub-objects are created with 10.0 in the ctor `0x48afd0`.

## What each wish maps to

| Wish | Where it lives | State |
|---|---|---|
| Per-car distance, height | rows `[[car+0xc]+0xb50]` (see camera.md section 4) | V, used by `?chasecam` and `?nitrocam` |
| Lag / follow | moving average `0x48ec00` + 10.0 smoothers `0x48afd0` | V structure, constants meaning U |
| Look-ahead in curves | none by distance; only the forward-to-velocity blend `0x705b20` (8..13) | V |
| Collision | `0x483430` clamp, `0x483b90`, wall push-out `0x4838e0` (type 1 only) | V names, maths U |
| Nitro | **no camera code reads nitro** (text search of `+0x3bc` in decomp_0x401000_0x4a6800.c: no hit between lines 97000 and 100000, where the 0x48xxxx camera code is) | V (G text search) |
| Drift | only the velocity blend above | V |
| Shake | `0x575040` called from `0x48bcb0`; its trigger is U | U |

## Nitro state (V, G)

Car state `car+0x3b0` / `+0x3b8` = tank ticks (4000 per second, `[0x6cca38]` = 0.00025 converts to seconds), `+0x3b4` = ticks per shot,
`+0x3bc` = clock stamp of the running shot (`0x4654f0` writes it from `0x73ad34`; `0x465530` clears it to 0). `0x465430` returns "firing" when the
stamp is not 0 or 0x7fffffff and `(now - stamp) <= +0x3b8` (G). Whether `car` (list node of `[0x7361f8]`) is the same object as that state is I:
the camera uses `car+0x3cc`, `+0x3d4`, `+0x540` on the same pointer, and `0x4654f0` takes the state in edx; the Mac must confirm with the
`CHASE nitro on/off` log line.

## The improvement shipped from this: ?nitrocam

While the stamp `car+0x3bc` is set, the rows go 10% farther and 5% lower (half-second low pass), on top of `?chasecam`. It changes only the row
values the mover already reads at `0x48ba2a`; nothing in the exe is patched. Off with `?nitrocam=0` (Original mode sets it to 0).
