# PC renderer of Speed.exe: what the Remaster needs

Marks: V = read in code or bytes this session (tool named), I = inferred, U = open.
Tools: C = capstone sweep of .text (`build/canon/w2/va.py` reads the PE by address), P = Ghidra pseudocode
`census/canon/c/401000.c`, D = bytes of the unpatched `pc/Speed.exe`, X = the seven `fx/*.efx`, decoded (XOR 0xAA, same as the loader
0x40e180 does; decoded copies in `build/canon/w2/*.efx.txt`).
Older notes stay valid: `render.md` (device, queue, frame flow) and `blur.md` (speed blur). This file adds what they lacked.

## Answer (the four things the Remaster asked for)
1. **Frame pass order**: see "Frame" below. World, then speed blur, then cars, then emitters/particles, then flares; reflection views first.
2. **Fog does not exist in the PC game** (V, C+X+D). The only `D3DRS_FOGENABLE` (28) write in all of .text is `0x408bb0`, inside
   `RenderState_ResetDefaults 0x408b20`, with value 0. No other fog render state (34..38) is ever set. `filter.efx` writes `fog = 1.0`; the
   six other .efx have no fog code. The effect parameter table (0x701860) still lists `FogOffset, FogScale, FogFalloffY, FogColor`
   (names 35..38) but no shipped .efx declares them. So the Remaster fog has no original values to copy; any fog is new.
3. **Blur / depth of field**: speed blur constants are in `blur.md` (start 25, full at 125, cap 0.65, half-res 320x240 chain). There is **no depth of field and no
   depth weighting** on PC (V, blur.md G+C). Nothing else blurs the scene.
4. **Reflective road flag** (V, P+D): a track mesh is drawn with `worldreflect.efx` when bit **0x40** of its flags (`mesh+0xc`) is set.
   Details below. The reflection itself is a **320 x 240 planar render target**, only when option `[0x700e90] != 0` (graphics level >= 1).

## Which effect draws a mesh (V, P+D)
`Mesh_FixupGroups 0x40c890` (once per solid at load) picks the effect slot from `mesh+0xc` with the table at **0x701440** (stride 12: mask, slot, 0),
first match wins, no match = slot 0:

| flags & mask | slot | effect | note |
|---|---|---|---|
| 0x01 | 4 | worldbone.efx | skinned/bone geometry |
| **0x40** | **2** | **worldreflect.efx** | **reflective surface (wet-looking road, glass)** |
| 0x80 | 5 | car.efx | car body |
| otherwise | 0 | world.efx | |
Slots: base 0x71abb8 + k*0xe0. Slot 1 = worldheadlight.efx and 3 = worldheadlightreflect.efx are never chosen by flags; they come from
the substitution below. Slot 6 = filter.efx (blur filter). File names: strings at 0x7014e0.. in .data, table 0x7010c0 (stride 0x80) (D).

**Substitution at draw time** (`0x40c910`, V, P+D): the slot index is remapped through a table of 7 pointers:
| condition | table | remap |
|---|---|---|
| view flag 0x200 off, or headlights option `[0x700e80]`==0, and road-reflection `[0x700e90]`==0 | 0x706898 | slot 2 -> slot 0 (**reflective road drawn plain**) |
| flag 0x200 on, `[0x700e80]`!=0, `[0x700e90]`==0 | 0x706818 | 0->1, 2->1 (headlight, no reflection) |
| flag 0x200 on, `[0x700e80]`!=0, `[0x700e90]`!=0 | 0x706798 | 0->1, 2->3 (headlight + reflection) |
| `[0x700e90]`!=0 and no headlights | none | slot 2 stays (reflection) |
Meaning of view flag 0x200 (I: night/headlight pass; set by the caller 0x446730). Also: a slot-1 material with `mat+0x56 != 0` and count > 1 falls back to slot 0.

**What the reflective pixel does** (X, `worldreflect.efx` ps_1_1): `out = 2 * diffuse * vertexColor + vertexColor.a * diffuse.a * reflectedSample`.
So the amount of reflection per pixel is **vertex alpha x diffuse-texture alpha**, i.e. the artists paint where it is wet. Projection:
`t1 = clip-space position, y flipped, (xy + w) * 0.5` (screen-space lookup into the reflection texture). Fallback techniques in the same file:
`world` (vs_1_1/ps_1_1), `world_fixed_single_pass`, `world_fixed_2pass`, `world_fixed` (fixed function, `ReflectedProj` texture transform).
`Effects_CreateAll 0x40e180` takes the first technique that validates (+0xf4), skipping some old GPUs (vendors 0x1039, 0x8086/0x2572, 0x10de 0x153..0x1f0,
0x102b); it sets `[0x736418]=1` when technique 0 (shaders) is used, `[0x736414]=1` for a fixed-function fallback (V, P).
Per-slot init callbacks (table 0x702420, V, D): 0 Null `0x40a880`, 1 `Effect_BindHeadlightTextures 0x40e740`, 2 `Effect_BindSceneParams 0x40e7b0`,
3 `Effect_BindHeadlightParams 0x40e900`, 4 Null, 5 `0x40eb30`, 6 `0x40eb60`. The reflection callback (2) binds `ReflectedTex = [0x71aa28]`,
sets `ReflectedTexMin = 0.1` (0x3dcccccd; the shipped .efx does not declare it, so it has no effect) and `ReflectedProj` = view matrix x (0.5 scale/bias).

## Render targets (V, P)
| What | Where | Size / format |
|---|---|---|
| Planar reflection | texture `[0x71aa28]`, surface `[0x71ab68]`, depth `[0x71ab64]`, made by `SceneRTCreate 0x40a890` only if `[0x700e90]!=0` | **320 x 240** (0x140 x 0xf0), format `[0x702a94]`, depth `[0x702a98]` |
| Scene RT | `[0x736460]`, `[0x736464]` | `[0x701034]` x `[0x701038]` (window size), format `[0x702a80]`; only if `[0x73645c]==1` (motion blur or light streaks) |
| Blur A/B, streak RT | blur.md | W/2 x H/2, A8R8G8B8 |
| Another RT pair | `[0x736470]/[0x736478]` | `[0x702a9c]` x `[0x702aa0]` (U what it holds) |
| Car cube reflection | render.md | 6 faces, size `[0x702a84]` (patched 512), only if `[0x700e74]!=0` |

## Graphics levels (`GraphicsQuality_Set 0x410ed0`, V, P)
| option | 0 | 1 | 2 | 3 | use |
|---|---|---|---|---|---|
| 0x700e74 | 0 | 1 | 2 | 3 | car cube reflection quality; loop over 6 reflection views |
| 0x700e78 | 0 | 0 | 1 | 1 | world sections also drawn into car reflection views |
| 0x700e80 | 0 | 0 | 1 | 1 | headlights (slots 1/3) |
| 0x700e90 | 0 | 1 | 2 | 2 | planar road reflection; 2 = also cars and showcase cars in it |
| 0x700e98 / 0x700e9c | 0 | 0 | 0 | 1 | MOTIONBLUR / LIGHTSTREAKS |
| 0x700ea8 | 0 | 1 | 1 | 1 | particle systems |
| 0x700eb0 | 1 | 1 | 3 | 3 | U |
Other flags: 0x700ea0 and 0x700ea4 set to 1 on every call (flares).

## Frame (V, P; addresses in order; `RenderFrame 0x40a580` calls `RenderFrameMain 0x409580`)
1. `0x40a580`: update views; `BeginScene`; `0x409cd0(1)`; **`0x409580`**; if `[0x73645c]==1` `0x40d6e0` composites the scene RT; `0x409cd0(0)`; `EndScene`; `Present`.
2. Inside `0x409580`:
   - `0x408f00`, then if `[0x700e90]`: `SceneRTSelect(1)` (reflection RT 320x240), if `>1` queue world + cars + showcase cars, emitters, flush `0x40ed50`, flares (`LampFlares_Draw(view 0x7405e0, 2)`).
   - if `[0x700e74]`: for each of 6 reflection views (0x740820..0x7409a0, stride 0x60): `SceneRTSelect(1)`, ZENABLE/ZWRITE off around `CarOverlays_QueueByView`, world (if `[0x700e78]`), emitters, flush, flares.
   - view 0x740580 (secondary view, if active): world, race cars, flush, particles (if `[0x700ea8]`), lamp flares, optional screen quads (`[0x7364ac]`, `[0x7364b0]`), `RenderState_ResetDefaults`.
   - player view (index 1): `0x4090a0`, `SceneRTSelect`, headlight callback pass if `[0x700e80]`, then world (`0x446730`, `0x58a240`, `RenderWorldModels 0x592100`), **speed blur `0x40cd40`**, `0x408b20`, cars `0x571050`/`0x570950`, emitters `0x4ae650`, particle systems `0x404110` x2, flares or light streaks; then rear-view mirror `0x409180` x2.
3. Queue: `FUN_0040c910` (this file: `Solid_QueueGroups`) puts each mesh group into per-slot buckets (`RenderQueue_GetBucketAlt 0x40f1e0`); `0x40ed50` flushes (`RenderQueue_Flush 0x40ed70`).

## Correction and additions (game-side pass, W2 second stretch)
- `[0x700e70]` is the **resolution index**, not a quality bit: `Resolution_ApplyIndex 0x408760` maps 0->640, 1->800, 2->1024, 3->1280, 4->1280 wide
  (V). `GraphicsQuality_Set` writes 0 for level 0 and 1 for levels 1..3, so level 0 is 640 wide and others 800. `GraphicsQuality_AutoDetect 0x410a00` picks
  the level from `MachinePerformanceScore` stored in `[0x701088]`: <0.3 level 0, <0.6 level 1, <0.9 level 2, else 3 (V).
- **Fog data exists but is dead.** Every frame `0x4090a0` (called from `0x409580` at 0x40989d) turns the per-view "zone" blend of `FogZones_BlendAtView 0x588f40`
  into 1/range, 250/range, alpha*1.5/255, x*1.35 and RGB/255 at `0x71a05c`. Nothing reads `0x71a05c` (byte search of the whole exe finds only the `mov esi, 0x71a05c` at 0x409897).
  The zone records (in the global block at 0x737bf0: records from +0x44, 0x50 bytes each, count at +0x3078 = 0x73ac68; fields include position x/z and two radii) are a ready-made per-section atmosphere dataset the Remaster could
  use for a real fog instead of a guess (I that they are fog; V that the blend is distance-weighted and the effect params FogOffset/FogScale/FogFalloffY/FogColor exist).
- `RenderQueue_BindMaterial 0x40f3d0` (V): translucent material (mesh+0x56) => alpha blend on, ZWRITE off (non-car slots); car slot 5 uses cull 2 when translucent, 1 otherwise;
  UV scroll from mesh+0x52 (mode 3 = static offsets, else flare-phase animation of the time `[0x73ad34] * 0.00025`).
- **Car lighting is spherical harmonics**, computed on the CPU (`SH_AddDirectionalLight 0x5416e0`, constants 0.282095/0.488603/1.092548/0.315392/0.546274, 10 coefficients x 4)
  and uploaded as `HarmonicCoeff[10]` of car.efx. Car shadows: `CarShadow_SunVector 0x56d700` uses the sun position `[0x735518]` (default -16384, 0, 7000).

## Render states the game sets directly (V, C: 66 SetRenderState call sites, immediates only)
ZENABLE(7) 12, ZWRITE(14) 22, ALPHABLEND(27) 9, ALPHATEST(15) 4, CULL(22) 3, ALPHAREF(24) 3, COLORWRITEENABLE(168) 2, BLENDFACTOR(193) 2 (speed blur),
ZFUNC(23), ALPHAFUNC(25), SPECULAR(29), LIGHTING(137), FOGENABLE(28)=0, SRCBLEND(19), DESTBLEND(20), TEXTUREFACTOR(60) 1 each. Everything else comes from the .efx passes.

## D3DX9 / EAGL band (0x5ab730..0x640000), state
Entry points used by the game: `D3DXCreateEffectPool 0x5af9e5` (V: checks out pointer, error 0x8876086c, creates the pool object) and
`D3DXCreateEffect 0x5afb2f` (V: device, source, size, defines, include, flags, pool, **ppEffect, ppErrors**; a leading dword -1 means a compiled effect).
`Effects_CreateAll` decodes each .efx in memory (`^0xAA`) and passes the text, so the HLSL/asm compiler in this band runs at startup (render.md U).
Band map used for the bulk rows (V where a string in the function says it, I for the rest of the band; boundaries are the landmark strings):
| Range | Module | Landmark (V) |
|---|---|---|
| 0x5ab730..0x5b1f00 | D3DX_Cpu: math thunks, PSGP, CPU detect | "DisableMMX" 0x5b0506, "GenuineIntel" 0x5b05b6 |
| 0x5b1f01..0x5b2d7a | D3DX_HlslLex: lexer, error text | "error X%u" |
| 0x5b2d7a..0x5ba0ab | D3DX_EffectCompiler | "ID3DXEffectCompiler: ..." |
| 0x5ba0ab..0x5c3e7d | D3DX_HlslSema: AST, type check, constant folding | "cannot convert from", "division by zero" |
| 0x5c3e7d..0x5c4000 | D3DX_HlslParse: yacc parser | "yacc stack overflow" |
| 0x5c4000..0x5c7bd2 | D3DX_Preproc | "#elif", "DIRECT3D_VERSION", macro errors |
| 0x5c7bd2..0x5e4ca2 | D3DX_HlslGen: HLSL to IR | "function must return a value" |
| 0x5e4ca2..0x5fe000 | D3DX_Asm: shader assembler | "D3DX9 Shader Assembler" 0x5e6ae3 |
| 0x604024..0x60fcaa | D3DX_Ps1Back: ps_1_x backend | "texreg2ar", "ps_1_%d" |
| 0x60fcaa..0x61808b | D3DX_VsBack: vs backend | "relative addressing not supported in vs_1_0" |
| 0x61808b..0x61e000 | D3DX_Ps2Back, debug info | "D3DX9 Shader Compiler" 0x619309 |
| 0x61e000..0x632000 | EAGL: dynamic loader + animation runtime | "EAGL::SymbolEntry" 0x61f2e0 |
**EAGL is not a renderer** (V): of its 26 functions called from outside, the callers are the animation code 0x47aeb0..0x47b6d0 (`GetFirstAnimBank`),
`AnimSkeleton_Load/Unload 0x5a4de0/0x5a4e90` and `Render_InitSubsystem 0x53e020` (installs the malloc/free hooks 0x61f020/30 and
`EAGLAnim::FnAnimFactory::New 0x627b90`). Its strings are the dynamic ELF loader, `CAnimSkeleton`, `CAnimBank`, `GlobalPoseBuffer`. The Remaster
can ignore it for rendering. Likewise 0x6385a0..0x640000 is EA's file system / timer / CPU-detect library ("FILESYS_*", "TIMER_init",
"GenuineIntel"), also not render; the systems tag "render" for these bands is wrong (about 1,400 functions with the D3DX band staying as library).
D3DX itself is a static copy of the D3DX9 effect compiler: the game needs only `D3DXCreateEffectPool 0x5af9e5` and `D3DXCreateEffect 0x5afb2f`
(plus D3DXMatrixMultiply used by the effect callbacks); nothing inside the band touches the frame path.

## Open
- Meaning of view flag 0x200 and who sets it (0x446730 caller chain).
- What mesh flag 0x40 means in the track format (which authoring tool sets it; not the same as the headlight flag); count of meshes with 0x40 per track needs the track loader (a data question, no game run needed).
- Contents of RT pair `[0x736470]`.
