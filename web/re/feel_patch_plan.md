# Feel patch plan

> Source: `docs/re/feel_patch_plan.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 32

# Feel patch plan

Base: `feel_candidates`, the archived feel notes (not published) (OWNER complaints), `camera.md`,
`camera_chase.md`, `blur.md`. Nothing in this plan was built or run: every byte below was read from `pc/Speed.exe` and checked
with the same `old` test `patches.apply()` uses (script run, 11/11 match). The look and the numbers are expectations, not
measurements; the probe is what turns them into numbers.

## The probe (default OFF)

`host/feellog.c`, called from `IDirect3DDevice9_Present` next to `ai_tel`. Enabled with `RN_FEELLOG=1`; with the env unset it
returns on its first line, so every build keeps it at zero cost.

- `FEEL` every 30 frames: speed m/s and mph, camera mover mode (`9000`), the POV code the mover uses, the chase row that resolves
  to it (`row` + its `dist` / `h` from the car's `CarTypeInfo`), the FOV word for that POV in degrees (from `0x6fbdf4`, the table
  FEEL-C3 edits), nitrous, and which row set is live.
- `FEEL A` once per standing start: 0-60 and 0-100 mph, counted on the Present clock (60/s, the limiter is 1:1). A run that stays
  under 100 mph for 20 s logs what it got and ends.

Grep `FEEL` in the page log. Flip a candidate, rebuild, run one Free Run with a standing start and compare the two lines.

## Candidates (`tools/recomp/patches.py`, `FEEL_CANDIDATES`, all `when=lambda: False`)

| # | Symptom | Patch | Expected number | Risk |
|---|---|---|---|---|
| C1 | Blur too strong | Copy the shared double 4.0 (`0x6cc9d8`) to free `.data` `0x707fd0` as 1.0; repoint the four `fmul qword` operands at `0x40cfb9`, `0x40cfda`, `0x40cfed`, `0x40cffb` | Second-pass edge reach / 4 (the "~15 s to ~4 s of travel" smear in `feel_candidates` 1); same weight, so the frame gets directional instead of soupy. Probe: no number changes, this is a look patch | Low. `0x6cc9d8` is shared by `0x438b60` and `0x606110`, which is why it is copied. The four operands are stack locals of the blur chain; no other reader |
| C2 | Lamp halos ("astigmatism", also stopped) | Flare weight 1.0 → 0.6 at both lamp flare draws: `0x544ff8` (into `0x5447c0`) and `0x54502e` (into `0x544e90`), `push 0x3f800000` → `push 0x3e99999a` | Still-lamp radiance 0.6x at the source; with the existing add colour 1.5x (`0x707fcc`) a still lamp lands at 0.9x its own flare instead of 1.5x. Trail length unchanged | Medium-low. Dims the star, every headlight flare and the garage lamps, not only the halo; the OWNER asked on 2026-10-26 for the aura around moving lights back, so this can read as too dim |
| C3 | Camera low/flat at speed, car small | FOV table `0x6fbdf4` POV 0, 1, 4: `0x32dc` (71.5°) → `0x2ee0` (65.9°) | Car 1/tan(32.95°)/1/tan(35.75°) = **1.11x bigger** on screen; vertical view 64.4° → 59.1°, horizontal 96.0° → 90.0° at 16:9. Probe: `fov <word> (… deg)` shows 71.5 → 65.9 | Medium. Speed.exe has no speed term for eye distance, height or pitch (`camera_chase.md`), so this enlarges the car at rest too, and the front end reads the same table: the garage cover car grows |
| C4 | Acceleration too fast (~2.7 s 0-60) | `jne 0x474d51` → nop nop at `0x474d47`, so the drivetrain setup `0x474d40` always takes the 1.0 at `0x6cc7bc` instead of `car+0x404` (gate `0x6ffe54` is 1, no writer) | Removes the per-frame power/drag/grip scale. If the player's `car+0x404` is 1.0, 0-60 is unchanged (`FEEL A` says so); the delta it does show is what the scale was worth. Reference: shipped 3.63 s stock, 2.9-3.3 s with the OWNER's parts | Medium. Applies to the player and every rival; rivals lose their multiplier. `0x6cc7bc` is a shared float and is only read here, never edited |

## Already patched (do not propose again)

- Blur: ramp `0x702a38` = 0.1-25 m/s, cap `0x702a40` = 0.26 (weight 0.39), NOS black-screen blend fix `0x40d615` / `0x40d2a2`.
- Halos: the light-streak add colour `0x707fcc` = 1.5 per channel (was R 2.0 / G 2.4 / B 3.4 shipped); the decay is the shipped one.
- Camera: projection caves `0x40debb` / `0x40deec` / `0x40dcdb` (PS2 vertical view, 16:9 cap), widescreen 2D `0x40bf09..`,
  cube 512 px `0x702a84`, reflection 0.7x `0x707fc4`, LOD lock `0x56e0d2`, autopilot camera `0x42d87e`.
- Acceleration: nothing patched. `0x735ec1` (unlock byte) is ruled out: front-end readers only, it marks parts bought, it does not
  install them. The 2.7 s is the shipped formula with weight L3 / turbo L1 / tires L3 (`re_accel`).

## Not in this plan

- Port-side knobs that would confound an A/B: `?chasecam=1` (distance x1.12, height x0.90), `?nitrocam=1`, `?speedfov=10`,
  `?bloom` (the wide glow when stopped is `web/gpu.js:357`, there is no x86 bloom). Turn them off before judging C2 or C3.
- Original mode is not the shipped game: every `PATCHES` entry has `when=lambda: True`, so it runs the same caves. The shipped
  reference is the Wine exe (`tools/wine/mkexe.py`).
