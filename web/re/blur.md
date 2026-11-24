# Speed blur (Speed.exe PC)

> Source: `docs/re/blur.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 103

# Speed blur (Speed.exe PC)

Marks: V = read in code or bytes this session, I = inferred, U = open. Tool after each claim: G = Ghidra 12.1.4 headless
(`tools/ghidra/gpar.sh`), H = Hopper export `census/hopper/decomp.c`, C = capstone `tools/recomp/asm.py`, D = bytes read
from the unpatched exe or from the PS2 ELF with python struct, M = PS2 map `ref/docs/re/out/x86-ps2-map.tsv` (hint only).
Names and addresses: `census/names_blur.tsv`. Camera side: `docs/re/camera.md`.

## Answer

- **What triggers it.** One function, `0x40cd40` (SpeedBlurPass), runs once per frame inside the main render `0x409580`.
  It needs option MOTIONBLUR `[0x700e98]` (or LIGHTSTREAKS `[0x700e9c]`) so that the scene is drawn into a render target,
  and it blurs when t >= 1/255 (V, G+H+C).
- **Strength, in one line.** `t = min( clamp((|v_cam| - 25) / 100, 0, 1) + 1.1 * n , 0.65 )`, where `v_cam` is the
  velocity of the camera eye in m/s (not of the car) and `n` is a 0..1 ramp that is pulled to 1 while a special camera
  (jump view, slow motion, zone preview) is active. The result is composited over the scene with weight
  `w = min(1.5 * t, 1)`, so the blur is at most 97.5 % blurred copy (V, G+C+D).
- **Which pass.** A half-resolution (W/2 x H/2) A8R8G8B8 chain: downsample, two 4-tap "zoom" passes (the second with 4x the
  vector, 16 effective taps), then one alpha-blend of the result over the scene with D3DRS_BLENDFACTOR (V, G+C).
- **Why the car is sharp.** It is drawn after the blur (order in `0x409580`): world, blur, then cars, emitters and
  flares. There is no depth weighting on PC (V, G+C).
- **PLAN guesses refuted.** PS_FAR = 200 and the "far = strong" depth weight have no PC counterpart. The W/512 offsets are a
  PS2 pixel to fraction conversion only; PC offsets are UV fractions. `[0x73654c]` is not nitrous (it is a special-camera
  flag). See the section "What psblur gets wrong".

## Frame order (V, G+H+C)

`0x409580` draws only view index 1 (the loop breaks after it). For the player view:

1. `0x592100` RenderWorldModels (track, scenery).
2. If `[0x736384] != 0 && [0x73645c] == 1` and `[0x700e98]` (MOTIONBLUR) then `0x40cd40`.
3. `0x408b20` render-state reset.
4. `0x571050` race car list (car draw `0x56dc30`, up to 99 cars), `0x570950` showcase cars (list `0x73d6d8`), `0x4ae650`
   emitters and particles, then flares (`0x409b70` path, light streaks, U).

## Render targets (V, G+C)

| What | Address | Detail |
|---|---|---|
| Scene RT | texture `[0x736460]`, surface `[0x736464]` | `0x40a890`: size `[0x701034]` x `[0x701038]` (default 800 x 600), format `[0x702a80]`; created when `[0x73645c] == 1`. `0x40abd0(flag)` makes it the render target. |
| Blur A, B | textures `[0x71ab9c]`, `[0x71aba0]`; surfaces `[0x71aba8]`, `[0x71abac]` | `0x40cb80`: `[0x702a2c]` = W/2, `[0x702a30]` = H/2 (320 x 240), format `[0x702a28]` = 21 (A8R8G8B8). |
| Light-streak RT | `[0x71aba4]`, surface `[0x71abb0]`, format `[0x702a34]` = 21 | only if LIGHTSTREAKS `[0x700e9c]`; not analysed (U). |

`0x40b3f0` sets `[0x73645c]` and `[0x736384]` to (MOTIONBLUR or LIGHTSTREAKS) and then creates the scene RT. `0x40cce0` and
`0x40b4e0` release the targets (I, C).

## The strength formula in detail (0x40cd40, V, G+H+C)

Inputs.

- Speed = |v|, v = camera object `[0x740500]` (= `0x78d270`, stored by `0x40a7f0`) at +0x1e0..+0x1e8. It is written by
  `Camera::SetCameraMatrix 0x47d070` as (pos - prevpos) / dt (dt at +0x274). It is the **camera eye velocity**, not the car's.
- `n` = `[0x73641c]`, moved toward the flag `[0x73654c]` by +`[0x702a48]` (0.2) or -`[0x702a4c]` (0.1) per frame, and only when
  |n - flag| > 1/255 (`[0x6ccd00]`). Only `0x40cd40` touches `[0x73641c]` (G xref: reads and the two writes at 0x40cd8a, 0x40cd9e).

Constants (static `.data`, no code writer; D from the unpatched exe, G xref shows only `0x40cd40` reads them):

| Addr | Value | Role |
|---|---|---|
| `0x702a38` | 25.0 | speed where the blur starts (units I: the exe gives only the number 25; m/s, 90 km/h is an assumption until the unit of the speed passed in is read) |
| `0x702a3c` | 125.0 | speed where the speed term is 1 (units I, see above) |
| `0x702a40` | 0.65 | cap on t |
| `0x702a44` | 0.00625 | streak length per tap per unit t (UV) |
| `0x702a48` / `0x702a4c` | 0.2 / 0.1 | n ramp up / down per frame |
| `0x6cccf8` | 1.1 (double) | weight of n in t |
| `0x6cc970` | 1/255 | blur is skipped if t is below this |
| `0x6ccb7c` | 1e-5 | direction is normalised only if speed is above this, else the vector is 0 |
| `0x6ccc64` | 1.2 | multiplier in s |
| `0x6cc7dc` / `0x6cc7bc` | 0.5 / 1.0 | in s = t * 0.00625 * (1 + 0.5 n) * 1.2 |
| `0x6cc9d8` | 4.0 (double) | second pass vector multiplier |
| `0x6ccc0c` | 1.5 | w = min(1.5 t, 1) |

Steps.

1. base = 0 if speed <= 25, 1 if speed >= 125, else (speed - 25) / 100. Then t = base + 1.1 n, capped at 0.65.
2. The velocity is transformed by the camera object matrix (camobj + 0, row vector; CRT thunk `0x5ac443` -> `0x5ac449`) and
   normalised (`0x567450`) to (a, b, c). The four UV shifts are v0..v3 = (a + c, b + c, a - c, b - c), each times s,
   with s = t * 0.00625 * (1 + 0.5 n) * 1.2.
3. Pass 1 `0x40d370` BlurDownsample4Tap: scene texture -> A (half size), 4 taps of weight 0.25 at (+-0.5, +-0.5) source
   texels (table `0x7024b8`), through the "filter" effect (`game/fx/filter.efx`, ps_1_1, FilterWeights[4], CLAMP, LINEAR).
4. Pass 2 `0x40d090(A, 4 taps, weight 0.25, vec = s * v)`: A -> B. Tap k = 0..3 shifts the four UV corners:
   TL (-k v0, -k v1), TR (1 - k v2, -k v1), BR (1 - k v2, 1 - k v3), BL (-k v0, 1 - k v3). So a pixel mixes itself with copies
   scaled about the screen centre; the shift is 0 at the centre and grows toward the edge. This is a radial zoom blur.
5. Pass 3: the same `0x40d090` with vec x 4.0, B -> A. Together 4 x 4 = 16 effective taps; the reach at the edge is about
   15 s.
6. Composite `0x40d6e0(1, &0x71ab9c, ...)` onto the scene surface with SrcBlend 0xe (BLENDFACTOR) and DestBlend 0xf
   (INVBLENDFACTOR). Weight w = min(1.5 t, 1) * 255 -> `_ftol` (`0x674898`) -> D3DRS_BLENDFACTOR (0xc1) = c | c<<8 | c<<16 | c<<24.
   Result = lerp(scene, blurred, w). Maximum w is 0.975 at t = 0.65.

Examples (I, from the formulas). Camera speed 60 m/s: base 0.35, t = 0.35, w = 0.525, s = 0.0026, edge reach about 3.9 % of the
screen width. Speed 125 m/s with no special camera: t = 0.65 (cap), w = 0.975. A special camera at speed 0: t = 0.65 after
the n ramp (about 5 frames), w = 0.975.

Device vtable slots used (V, C): 0x94 SetRenderTarget, 0x9c SetDepthStencilSurface, 0xe4 SetRenderState, 0x14c
DrawPrimitiveUP (fan, 2 primitives, stride 0x30), 0xbc SetViewport, 0xac Clear, 0x5c CreateTexture. Vertex layout in the
passes: position xyz, colour dword, four texcoord pairs.

## What drives n: `[0x73654c]` is not nitrous (V, G+C)

`[0x73654c]` is a "special camera active" flag.

- Set to 1 by `0x42da40` (every special mode 1..7, JUMPVIEW included), `0x426930`, `0x430a3b`, `0x492949` (ZonePreview
  start), `0x431c65`.
- Cleared by `0x42ddc0`/`0x42ddd5` (mode end), `0x431107`, `0x427dfe`, `0x460f86` (destructor), `0x4900fd` (ZoneFreeze
  destructor), `0x4922f2`, `0x492966`, `0x492a3b`.
- `0x4010e0` is a setter (`[0x73654c] = arg & 0xff` if `view[arg2].enable == 1`) with no direct callers (I).

Nitrous only changes the blur indirectly, by raising the camera speed. This corrects `docs/night_re.md`, which says
`[0x73641c]` ramps toward nitrous.

## What the port's psblur gets wrong (V for the PC side, G+C+D; port side read from web/gpu.js, host/d3d9.c, web/tune.js)

The port default is `BLUR_DEFAULT = 6` ("PS2 depth"): the PS2 4 (+2) full-resolution copies, alphas scaled by t / 128, run on
the final scene colour before the HUD, with the game's own blur forced off (cap 0).

| # | Port | PC original |
|---|---|---|
| 1 | Reverse depth weight with PS_FAR = 200 ("far = strong") so the car stays sharp | No depth term at all. The car is sharp because the blur sits between the world draw and the car draw. PS_FAR and the depth hack are an invention. |
| 2 | 4 (+2) full-res copies, alpha from a table | Half-res 16-tap cascade (downsample, 4 taps, 4 taps with 4x vector), composited once with w = min(1.5 t, 1) |
| 3 | Offsets x W/512 (pixels of a 512-wide PS2 frame) | UV fractions, resolution independent: s = 0.0075 t (1 + 0.5 n) per tap, edge reach about 15 s (t = 0.35 gives 3.4 % of the width) |
| 4 | `nitro` reads `[0x73654c]`, so passes 5/6 and k 2 -> 15 fire on "nitro" | The flag is the special-camera flag. They would fire in jump view, slow motion and zone preview, not with NOS. In PC the flag adds 1.1 to t (through n) |
| 5 | Ramp for the default: PC `[25, 125]` cap 0.65 is already right | PC ramp 25 -> 125 m/s, cap 0.65 is the original. The PS2 ramp is 0.1 -> 25, cap 1 (D) |
| 6 | Zoom-in sprite enlargement (PS2) | PC samples a larger source range for z > 0 (zoom-out, edge clamp smear). Sign of z for forward motion: I, not confirmed (see U) |

PS2 reference values read from the ELF (D, struct): offsets at `0x4485c0` = 2.3, 6.4, 8.8, 11.4, 22, 40; alphas at
`0x4485f0` = 50, 35, 28, 17, 8, 4; enables at `0x448590` = 1,1,1,1,0,0; ramp `0x4ff95c` = 0.1, `0x4ff960` = 25, max `0x4ff954` = 1.0;
k `0x4ff8f8`/`0x4ff8fc` = 2.0/15.0. PS2 max blur is about 70 % at t = 1 and the car is kept sharp by a depth to alpha trick
(`ref/docs/re/postfx-elf.md`).

`tools/recomp/patches.py` already patches the PC constants: `0x702a38` -> (0.1, 25) and `0x702a40` -> 0.26 ("too strong").
The old bytes (25.0 and 125.0, 0.65) match this document (D second source). The "NOS black screen" skip at `0x40d615` and
`0x40d2a2` (7512 -> 9090) removes a SetInt BaseAlphaBlendEnable (not analysed here).

## Open (U)

- U: sign and direction of the blur (z > 0 for forward motion) in the camera object matrix `0x78d270`. Old logs
  `build/psblur/log1.log` show "view1 v*R" with z about +speed for the render block `[0x7404c0]`, which is not proven to be the same
  matrix. A bounded run with `RN_WATCH` on the `0x78d270` matrix and `0x78d450` would settle it. Not done tonight.
- U: light streaks (`0x700e9c`, RT `0x71aba4`, `0x409b70`, decay BLENDFACTOR `0x008296b4` at `0x409bca`).
- U: exact format `[0x702a80]` of the scene RT.
- U: the "NOS black screen" patch sites.

## Second-tool agreement (10 random names)

Names drawn with `random.seed(20261029)` from the V/I rows of both registries, then re-derived with a tool other than the primary.

| Name | Primary | Second tool and result | Agree |
|---|---|---|---|
| `0x73641c` gBlurSpecialN | C | G xref: reads and writes only in `0x40cd40`, writes at 0x40cd8a and 0x40cd9e | yes |
| `0x700e9c` OPT_LIGHTSTREAKS | C | G xref: readers `0x40cb80` `0x40b3f0` `0x409580` `0x410ce0` `0x4160b0`; writers `0x410a00` `0x410ce0` `0x410ed0` `0x416a40` | yes |
| `0x6cc9d8` 4.0 double | C+D | G xref: four reads in `0x40cd40` (0x40cfb9..0x40cffb); also read by `0x438b60` and `0x606110`, so it is a shared constant | yes (note: shared) |

The full table of 10 names (these three and seven camera names, with three corrections) is in `docs/re/camera.md`.
