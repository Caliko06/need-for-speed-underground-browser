# Feel probe fix

> Source: `docs/re/feel_probe_fix.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 20

# Feel probe fix

Run that exposed the bugs: `runs/w_d_a/log.txt`, 682 `FEEL` lines, every one `cam 0 pov -1 row 00000000 dist 0.00 h 0.00 fov 0`,
plus 5-line bursts of `FEEL A … 0-60 0.02 s`. Nothing was built or run for this fix; every offset below was read in
`pc/Speed.exe` (`tools/recomp/asm.py` + capstone) and cross-checked against the same run's `JC` lines, which were correct.

## What was wrong

1. **The FOV read was the angle, not the index.** `view+0xc4` is the word `0x485ff1` *writes* into the view, i.e. the FOV already
   resolved to 1/65536 turn units (`0x32dc` = 13020 = 71.5°, `0x0e38` = 3640 = 20° for the jump cam). The old probe took it as
   the POV code, so `pov` came out 13020 (guarded to -1 by `pov < 16`) and never matched a row. Same `JC` run shows the value is
   exactly this angle: `fov 13020` on the chase camera, `fov 3640` in mode 6.
2. **The chase row was looked up with that wrong number.** `feel_row` scanned 5 rows against 13020, found nothing, and printed
   `row 00000000 dist 0.00 h 0.00`. The five-row loop also ignored the count and the second row set.
3. **`cam 0` is not a bug.** `ctrl+0x60` is the camera *mode*; 0 is the normal chase camera and 6/7 are the jump views. The same
   run's `JC` lines print `mode 0` on normal driving. The field is now named `mode` so it stops looking broken.
4. **False starts.** The old rule was "speed < 0.3 then anything above 60 mph", and a car-pointer change between two frames
   turned into a 0.02 s run. The new rule needs the car under 1 m/s for 30 frames, and throws the run away on a car change, a
   stop or a jump of 8 m/s in one frame.

## What each field reads now

| Field | Source in Speed.exe |
|---|---|
| `mover` | `[ctrl+0x27c]`, `ctrl = [0x7361bc]` while race state `[0x77a920] == 6`. It is the camera object `0x48bcb0` updates; `mover+0x2c` is the car it drives (`0x48bd19` stores the `0x41ffe0` result there) and `mover+0x1c` the view it writes (`0x485fee`). The `JC` probe already used this pair and printed valid eyes and FOVs |
| `mode` | `[ctrl+0x60]` (0 = chase, 6/7 = jump views) |
| `pov` | `(s16)[mover+0x40]`. `0x48bf43` loads it and `0x48bf4e` passes it in `edi` to FindCameraRow `0x47d680`; when that returns no row the code at `0x48bf5b` retries with `edi = 0`, the far chase row, which only makes sense if this field is the POV code |
| `row` | FindCameraRow `0x47d680` rebuilt: base `[[car+0xc]+0xb50]`, `cmp [0x7364a0],3` picks count at `+4` / rows at `+0x60`, else count at `+0` / rows at `+0x10`; rows are 16 bytes and match on their s16 id. `+0` count is 5, second count 5 (`docs/re/camera.md` 4) |
| `dist`, `h` | `row+4` and `row+8`. `0x48b8c0` reads exactly those two at `0x48ba2a` (`mov ecx,[esi+4]`, `mov eax,[esi+8]`) and `0x489690` uses `-distance`, so a negative `dist` means behind the car. R34 far chase: -5.80 / 1.70 |
| `fov` | `(s16)[view+0xc4]`, the word `0x485ff1` writes from `ebx = mover`: `mov ecx,[ebx+0x1c]; mov [ecx+0xc4], ax`. It is what the projection got, so it follows `?speedfov`, the caves and the jump cam without guessing |
| `tab` | `(s16)[0x6fbdf4 + 2*pov]`, the per-POV angle the game resolves (`0x480750`: `sign_extend(s16[row]) * 2 + 0x6fbdf4`). POV 0/1/4 = `0x32dc` = 71.5°, POV 2/3 = `0x4000` = 90°. This is the word FEEL-C3 edits |
| `set` | `[0x7364a0] == 3`, the second row set |
| `sp` | `car+0x3d4` m/s (HUD unit, `0x6cc9f0` x 2.237 = mph). Nitrous on: `[0x73654c]` |
| `FEEL A` | Present clock, 60 per second: a run starts on the first frame at or over 1 m/s after 30 frames under 1 m/s, and logs 0-60 / 0-100 mph. Any stop, car change or 8 m/s single-frame jump cancels it |

## How to read a line

```
FEEL f2892 sp 0.00 m/s (0 mph) mode 0 mover 0119a800 pov 0 row 0119b0f0 dist -5.80 h 1.70 fov 13020 (71.5 deg) tab 13020 (71.5 deg) nit 0 set 0
```
`pov 0` + `row` non-zero + `fov`/`tab` at 71.5° is the normal chase camera; `fov` going up while `tab` stays is `?speedfov`;
`dist`/`h` moving while `fov` does not is `?chasecam` / `?nitrocam` on the host side.

## Still open

- `pov` depends on `[mover+0x40]` holding a 0..4 row id. The first `w_*` run after this fix confirms it in one line: if it
  prints `pov -1` with a live `fov`, `mover+0x40` is something else in that build and the fallback is `tab` plus POV 0.
- The probe still does not read the eye in world space, so "distance" is the row target, not the smoothed camera of the moving
  average `0x48ec00`. That is the number a `?chasecam` A/B moves, so it is the right one for the plan.
