# Jump camera: trigger, camera, return, and why it was missing

Tools: G = Ghidra export `census/ghidra/decomp_0x401000_0x4a6800.c`, D = bytes of the unpatched exe (python struct, `tools/recomp/asm.py`),
H = our host code read. Earlier work: `re_jumpcam` (same chain, runtime logs of 2026-10-28). Not run in the pod this time
(the game does not run there yet): the new facts below are from code and bytes, the Mac must confirm with a jump.

## The chain (V, G+D)

1. `0x426930` (per car, every frame; the jump test runs when `frame % 8 == 3`). Input: `car+0x3cc` = wheels on the ground (0..4),
   `car+0x3d4` = speed (m/s), level x = option byte `[0x78a3fa]` (0x80 in a normal game).
2. Fires only if no special camera is running (`ctrl+0x60` not 6 or 7), `[0x7361e8] == 0`, all wheels in the air (`car+0x3cc == 0`),
   `ctrl+0x4ac == 0` and speed > curve `0x7062fc`. Curves are piecewise linear (x, y) pairs read by `0x583f20` (D):
   - speed `0x7062fc`: 50 m/s at x=0 to 5 m/s at x=255. At x=128: **27.4 m/s (99 km/h)**.
   - `0x706314`: 4.0 to 0.5 (look-ahead seconds fed to the flight predictor `0x429cf0`).
   - min height `0x7062cc`: 2.5 to 0.5. At x=128: **1.5 m**. Min distance `0x7062e4`: 2.5 to 0.5, at x=128: **1.5 m**.
3. The predictor `0x429cf0` returns max height and distance of the flight. If both are above the curves, `0x42c4b0()` must return non-zero
   (it builds the camera spline from the driver's route; fails if the route has fewer than 5 nodes over 75 m, see `re_jumpcam`), then
   **`0x426930` calls `0x42da40(mode 6, 0, 1, 1)`** (call at `0x426dd7` region; the call to `0x42c4b0` at `0x426dd7` is the one our cave replaces).
4. `0x42da40` mode 6: slow motion `0x420050(0.4, 8.0 s)` (`[0x6b7ab0]`, `[0x6b7a74]`), camera mover **type 0xf** (TrackCar, update `0x485c00`) through
   `0x42c6d0(ctrl, 0xf, 1)`, `ctrl+0x60 = 6`, `[0x73654c] = 1`. Cooldown: 5 s per mode (`[0x6b7a88]`). Refusals: see `re_jumpcam`.
5. The shot (`0x485c00`, G): the eye is a point of the route spline (`mover+0x410..0x428`, segment chosen by the car's progress), the target is the
   car (`mover+0x438` car, position `+0x60`); FOV `mover[0x1c]+0xc4` is set here from the distance (`0x564db0`), `+0xbc = [0x6b6cd0]`. No wall sweep is
   run on this eye (the push-out `0x4838e0` has two call sites in the export, neither inside `0x485c00`, which calls `0x483860` and `0x485b90` instead).
6. Back to the chase: while `ctrl+0x60` is 6 or 7, `0x426930` calls `0x42ddc0(ctrl, 1)` when the car touches down: if `car+0x38 == 1`, with all 4 wheels down and
   0.5 s (`[0x6b7ba4]`) after `car+0x4c8`; otherwise as soon as one wheel touches (`car+0x3cc > 0`). `0x42ddc0` clears `[0x73654c]`, `ctrl+0x60 = 0`, restores time, and
   `0x42c450` calls the default camera `0x42c670` (type 0x11, the chase). The mode-7 shot (landing view, mover 0x10) follows through the same gates.

## Why it did not show in our build (V, H)

- **Cause: our own patch.** `PATCH 0x426dd7` and `0x4662e0` (cave `0x5567e3`) send the `0x42c4b0` question to `host/free.c free_jumpcam`, which returned 0
  in free mode (Free Run and WORLD, `live`). With 0 the jump shot is refused every time, so the chase stayed. That was added on 2026-10-28
  because the spline eye sits inside buildings in the city. Circuits and Quick Race always ran the original call.
- Not the cause (checked in code): `?chasecam` and `?nitrocam` only rewrite CarTypeInfo rows `[[car+0xc]+0xb50]`, read by mover 0x11; mover 0xf
  does not read them. `PATCH 0x42d87e` only changes the autopilot's camera type (0x12 to 0x11). `fov_frame` writes the FOV table, which mover 0xf does not read
  (it sets its own FOV at `+0xc4`).
- The same cave also feeds the crash camera (`0x465d00`, call `0x4662e0`): it came back too.

## The fix and its exit (updated 2026-10-31)

`free_jumpcam` runs the original call in free mode too (the switch `?jumpcam` / `RN_JUMPCAM` is deleted: the OWNER wants the jump cam, 2026-10-30)
and then the route check below. A race and `RN_FREE=0` stay the exact original call.

## Correction: `cam 0 span -1` in mode 6 is normal (V, capstone on pc/Speed.exe)

- The old `JC` comment said `span -1` means the last `0x42c4b0` call failed. Wrong during modes 6 and 7. `0x42c4b0` sets `ctrl+0x5c4` = route clone
  (+4 count, +8 node pointers), `ctrl+0x5c8` = k (the node nearest the car), `ctrl+0x5cc` = first node 75 m or more past k. `0x42da40` mode 6 runs
  `0x42c6d0(ctrl, 0xf, 1)`; then `0x42dd11` always calls `0x42c640`, which frees the clone and sets `5c4 = 0`, `5c8 = 5cc = -1`. So the log
  line sees `cam 0 span -1` for the whole shot. Only a refusal at the time of the call shows as a missing jump cam.
- `host/d3d9.c jumpcam_log` now also prints `eye` (`ctrl+0x560..0x568`), `fov` (the word at `[[ctrl+0x27c]+0x1c]+0xc4`: `ctrl+0x27c` is the active
  mover, `0x42c6bd`; `mover+0x1c` is its camera view, written by `TrackCarCameraMover__Update` at `0x485fee..0x485ff1`) and `rp` (`car+0x810`,
  copied at `0x42cb34`).

## The eye is fixed, and the city blocks it (V, capstone)

- Case `0xf` of `0x42c6d0` (`0x42ca9b..0x42d0a0`) takes the eye node e = `[5cc] - 2` if `[5cc] - k >= 5`, else `[5cc]`. The eye is one point at a road
  edge of node e: `0x5a7270(out, node+0x58, vt[+0xc](lane) - 2.0, lane)` (left, `0x42cd24`) or `0x5a7270(out, node+0x58, vt[+8](lane) + 2.0, lane)`
  (right, `0x42cd4d`), `2.0` is `[0x6b7aac]`, lane = driver `vt[+0x1c](0)` clamped at 0 (`0x42cae9`). Node vtable `0x6c8f5c`: `+8 = 0x5a7ac0`,
  `+0xc = 0x5a7a10`, both return a float in st(0). The edge first tried is the one less far ahead along `car+0x70..0x78` (`0x42cdb1..0x42ce3c`).
  The eye is then raised to the ground + 1 (`GroundQuery__FindSurfaceBelow`) and stays there for the whole shot (about 3 s). FOV is constant, no wall check.
- The game has a portal test: `0x457300` (eax = first node, ecx = route; stack: car position pointer, eye pointer, last node; the caller pops) checks that
  the car -> eye segment crosses the cross-section `[node+0x20, node+0x3c]` (`0x5a7270` at lateral `node+0x20` and `node+0x3c`, lane 0) of every node
  from k to e-1, with the 2D segment test `0x457180` on x and y. If it fails, the game switches to the other road edge (`0x42cf12`) and uses it
  **without testing it**. In a city, 80 to 100 m along a road that bends, both edges are behind buildings. That is the bug.

## The route check (H, `host/free.c free_jumpcam`)

- After the original call, in free mode: for e from the game's eye node down to k+1, `eye_check` places the eye exactly as above, runs `0x457300` on the
  edge the game takes first and, if it fails, on the other edge; e is accepted when one passes and the edge used is 30 m or more from the car (2D).
- Taking e: `[5cc] = e` if e - k <= 4 (then `[5cc] - k < 5` gives e), else `[5cc] = e + 2`. This never goes past the original `[5cc]`. Lower limit: e >= k+1
  (the portal range k..e-1 is empty below that and `0x457300` answers 0). Node k+2, which the case reads for the second point (`0x42cdc6`), stays valid
  because the original call guaranteed `[5cc] - k >= 4`.
- Nothing qualifies: `0x42c640` (reads esi only) frees the clone and the answer is 0, so the chase camera stays.
- One line per query in free mode, in build/web.log: `JCPICK f<frame> k <k> end <5cc now> eye <e or -1> of orig <e0> dist <m> clear|refused`.
  `eye == orig` and `clear`: the game's own eye was fine. `eye` lower than `orig`: the eye was moved closer. `refused`: no clear eye, chase camera stays.
  Read it together with `JC ... eye .. fov .. rp ..` of the same jump.
- Not run in the pod (no game files): the Mac must confirm with jumps in WORLD. Exit: if the OWNER is happy with the shots, nothing more to delete; if
  `refused` is frequent, the next step is a wall sweep on the eye of `0x485c00` (the push-out `0x4838e0` takes a car collision cache, so it only
  works near the car).
