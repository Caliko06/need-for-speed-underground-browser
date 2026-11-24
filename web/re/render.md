# Render: D3D9 layer, effects, queue, views, EAGL and the static D3DX (Speed.exe PC)

> Source: `docs/re/render.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 156

# Render: D3D9 layer, effects, queue, views, EAGL and the static D3DX (Speed.exe PC)

Marks: V = read in code and a second tool agrees (Hopper H, Ghidra G, capstone C), I = inferred, U = open. Names: census/names_render.tsv
(84 rows; same-address rows in other names_*.tsv were skipped). Blur, camera, TPK/assets and CRT are in blur.md, camera.md,
assets.md, runtime.md and are only referenced here. Method note: I swept all of .text with capstone for calls through a register loaded
from `[0x73636c]` (the device) and compared that fingerprint with the H and G pseudocode (table "Re-derived" below).

## Answer
- **The "render" tag is mostly not game render code.** census/systems.tsv has 2,374 render rows, 1,708 of them real Ghidra function starts.
  Of those, 997 sit in a **statically linked D3DX9** (0x5ab730..0x61e000: HLSL/effect compiler, preprocessor, ps_1_x/vs_x assembler, math),
  297 in **EAGL** (EA's graphics runtime, 0x61e000..0x640000) and 65 in SEH funclets (0x684b..0x696e). Only about 350 are the game's own
  render code, and only 65 of those (0x401e50..0x411f00) touch Direct3D.
- **The whole D3D9 device surface is one file's worth of code**: 38 functions in 0x401520..0x410e50 call the device `[0x73636c]` (capstone sweep).
  Everything else (cars, world, particles, flares, HUD) queues work or calls these. There is no `SetVertexShader`/`SetPixelShader` in game code:
  shaders come from **ID3DXEffect objects** compiled at run time by the linked D3DX (503 of 997 D3DX functions ran in the coverage union,
  so the .efx text is compiled on this machine at startup; U which functions exactly).
- **One frame** = `RenderFrame 0x40a580`: update views, BeginScene, main render `0x409580` per view, optional scene-RT composite, EndScene, Present,
  recover a lost device, then recycle per-frame memory (flow below).
- **Draws are batched by effect.** Items are queued into per-effect buckets (`RenderQueue_GetBucket 0x40f0f0`) and drawn by
  `RenderQueue_Flush 0x40ed70`, which selects the effect, binds VB/IB only when they change, and issues `DrawIndexedPrimitive`.
  Seven effect slots (stride 0xe0) at 0x71abb8.

## Address map (V unless marked)
| Range | What | Evidence |
|---|---|---|
| 0x401520..0x401e50 | modal frame loops (disc check, simple 2D frame) | G+H+C |
| 0x401e50 | dynamic quad VB/IB pool (30 VBs, 300-quad index buffer) | G+H+C |
| 0x407db0..0x408220 | texture D3D creation (named earlier), vertex declarations | G |
| 0x408830 | D3D init: Direct3DCreate9(0x1f), pools, window class "GameFrame", CreateDevice | G |
| 0x408b20 | state reset; 0x408f00..0x409b70 per-view render pieces; 0x409580 RenderFrameMain | H+G |
| 0x40a4e0..0x40b4e0 | device lost/reset, scene RT, RT table, reflection cube | G+H+C |
| 0x40cb80..0x40d6e0 | blur chain (blur.md) | |
| 0x40e180..0x40e900 | effect creation, ramp texture, per-effect parameters | G |
| 0x40ed50..0x4102f0 | effect select, queue flush, buckets, lights, bones | H+C |
| 0x410400..0x410ed0 | caps, resolutions, quality levels, option block 0x700e70.. | G+C |
| 0x403a60, 0x404110 | particle systems (update, draw) | H, G |
| 0x4ae650..0x4ae830 | emitters/flares | H |
| 0x5443f0..0x544f30 | flare quads and lamp flares (docs/flare_re.md) | |
| 0x56d8d0..0x571870 | car draw and car lists | H |
| 0x5ab730..0x61e000 | **D3DX9 static**: math thunks 0x5ac449..0x5ac8e5, PSGP init 0x5b065b, effect compiler (strings "ID3DXEffectCompiler: ...") 0x5b2d7a.., HLSL parser/typechecker 0x5ba0ab..0x5c7bd2, preprocessor 0x5c5700.., asm assembler 0x5e4ca2..0x5e8cd0, ps_1_x backend 0x604024..0x60f23a, vs backend 0x60fcaa..0x61808b | G strings |
| 0x61e000..0x640000 | **EAGL**: dynamic loader (.symtab/.strtab), symbol pool, RenderContext, PC caps/window, VertexBuffer/IndexBuffer wrappers, EAGLAnim | G strings |

## Flow of one frame (V: H+G, addresses in order)
1. `Render_InitSubsystem 0x53e020` (once, from 0x4471b0): `0x408830` creates IDirect3D9 `[0x736368]`, the window `[0x736380]` and the device
   `[0x73636c]` with present parameters `[0x71a96c]` (filled by `0x4086b0`), then `0x40a7f0`, `0x40ac80`, `0x40c600`, EAGL `0x61f020/30`, `0x627b90` and the
   pools `DynamicFrameMemory`, `eLightFlare`, `ePointSprite3D`, `ePoly`. `0x410e50` reads caps; `0x40e180` creates the 7 effects.
2. `RenderFrame 0x40a580`, every frame:
   a. `0x408410` (view/Z mode), set the two zero flags `[0x734608]/[0x73460c]` from option `[0x700eb4]`; `0x5707b0` updates views (`0x40ad60` builds matrices).
   b. Loop `i = 0..15` over `gViews` (0x740460, stride 0x60): active views get `0x40dd00` (camera.md); view 8 first runs `0x40a140`.
   c. If `TestCooperativeLevel` (+0xc) is OK: `BeginScene` (+0xa4), `0x409cd0(1)` (HUD pass in, hud docs), **`0x409580`**, and when `[0x73645c]==1`
      `0x40d6e0` composites the scene RT into the back buffer, `0x409cd0(0)`, `EndScene` (+0xa8).
   d. `Present` (+0x44). On `D3DERR_DEVICELOST` (0x88760868) and then NOTRESET (0x88760869): `Device_HandleLost 0x40a4e0` -> `Device_ResetAndRecreate 0x40a510`.
   e. `0x403a60(0x78e980, 1/60)` particle update, `0x545ea0` texture animation, `Clear` (+0xac, flags 7, z=1.0), `0x53e210` ping-pong the scratch arena,
      `0x53e330` recycle per-frame lists, frame counter `[0x7364dc]++`, then input/audio ticks (`0x405860`, `0x4058d0`, `0x4057c0`, `0x419ea0`, `0x4130d0`, `0x41e670`).
3. `RenderFrameMain 0x409580` (H, order verified against blur.md): reflection views first (6 slots 0x740820..0x740a00, `0x571870`, `0x40ed50`, `0x446730`, `0x4ae650`, flares),
   then for the player view: `0x4090a0`, scene RT select `0x40abd0`, `0x446730` (queue world sections), `0x58a240`, `RenderWorldModels 0x592100`, motion blur `0x40cd40`,
   `0x408b20`, cars `0x571050`/`0x570950`, emitters `0x4ae650`, particle systems `0x404110` x2 (if `[0x700ea8]`), then flares (`0x544f30`, `0x4ae7d0`, `0x570d00/0x570c70`) or
   the light-streak path `0x409b70`; after the view the **rear-view mirror**: `0x409180(RVM)` and `0x409180(RVM_MASK)` (textures from `0x408610`).
4. Every `0x40ed50` call increments `[0x71b1dc]` and runs `RenderQueue_Flush 0x40ed70`.

## RenderQueue_Flush 0x40ed70 (V: H body, C device-call fingerprint)
For each effect slot k (0..6) at `0x71abd0 + k*0xe0` with bucket list heads at `0x78a4e8..0x78a868` (stride 8 per kind):
select effect (`0x40e6d0` logic inline: End old, init callback, `SetVertexDeclaration(slot+4)`, `Begin` = effect vtbl +0x100), then for each queued item
(node: +0 next, +4 prev, +0x10 item, +0x18 sub-list): `0x40f3d0` sets blend/cull, `0x410400` loads matrices, `0x4100a0` per-object params, `0x40f7c0` lights (SetLight +0xcc,
LightEnable +0xd4), `0x40fae0` material, then per pass `Pass` (+0x104) and `DrawIndexedPrimitive` (+0x148) after `SetStreamSource` (+0x190) / `SetIndices` (+0x1a0) only if the
buffer differs from `[0x7363e8]` / `[0x7363ec]`. Items with no index data use `DrawPrimitiveUP` strip (+0x14c, stride 0x18). Counters: `0x71b1d8` items, `0x71b1e8` VB changes,
`0x71b1ec` IB changes, `0x71b204` effect switches (I for what each one counts).

## Structures (offsets V from H+G unless noted)
- **Effect slot** (0x71abb8 + i*0xe0, 7 slots): +0 index, +4 IDirect3DVertexDeclaration9*, +8 vertex stride, +0xc flag read by `0x4100a0`, +0x18 ID3DXEffect*, +0xd8 init callback,
  +0x84/+0x88/+0x8c/+0x38 parameter handles used by `0x40e7b0/0x4100a0` (I). Created by `0x40e180` from the descriptor table 0x7010c0 (stride 0x80, vertex element indices).
- **View record** (0x740460 + i*0x60, 16 views): +8 active, +0x40 camera object (matrix at +0x40 inside it, `0x40bc10`), +0x58 render target entry; +4 view type index used by `0x571870`.
- **D3DPRESENT_PARAMETERS** 0x71a96c: width, height `[0x701038]`, format `[0x702a80]`=0x15, SwapEffect 1, windowed `[0x73637c]`, AutoDepthStencil 1, DS format 0x4b/0x50.
- **Quad pool** (0x401e50): 30 dynamic VBs (`[0x71abc0]*0x4b0` bytes = 1200 vertices each) + one INDEX16 buffer of 300 quads (indices b+3,b,b+1,b+1,b+2,b+3).
- **Bucket node** (0x40f0f0): 0x20 bytes from SlotPool 0x567160; +0x10 owner mesh, +0x18/+0x1c self-linked sub-list head; list heads at 0x78a4e8 + (kind*7+effect)*8 or 0x78a6a8 + ..*0x20 (flag at mesh+0x54).
- **Scratch arena**: cursor 0x7355b4, limit 0x7355b8, overflow flag 0x7355c4, overflow bytes 0x7355c8, high water 0x7355cc; `0x53e210` swaps halves each frame (base `[0x72f5fc]`).
- **Reflection cube**: 6 faces + 6 depth surfaces (0x71ab6c / 0x71ab84), size `[0x702a84]` (patched 128 -> 512 by patches.py), only when option `[0x700e74] != 0`.
- **Option block** 0x700e70..0x700eb4 (dwords) set by `GraphicsQuality_Set 0x410ed0(level 0..3)`: level 0 everything off; 3 enables MOTIONBLUR `0x700e98` and LIGHTSTREAKS `0x700e9c`.

## D3D9 calls the game makes (V, capstone sweep; counts of call sites)
SetRenderState 59, SetSamplerState 24, SetRenderTarget 12, SetVertexDeclaration 9, SetTextureStageState 9, CreateTexture 8, Clear 7, DrawPrimitiveUP 7, SetDepthStencilSurface 4,
SetViewport 4, SetTransform 4, BeginScene/EndScene/Present 3 each, CreateVertexDeclaration 3, SetTexture 3, CreateDepthStencilSurface 3, GetDepthStencilSurface 3, CreateVertex/IndexBuffer 2,
Reset 2, LightEnable 2, SetStreamSource/SetIndices/DrawIndexedPrimitive 1 each, SetLight 1, SetMaterial 1, CreateCubeTexture 1, SetFVF 1. Not called by game code: SetVertexShader, SetPixelShader,
Set*ShaderConstant*, DrawPrimitive. The host (host/d3d9.c) therefore sees shaders only through the D3DX-created effects.

## Re-derived with a second tool (12)
Method: first the capstone fingerprint (which device calls a function makes and with what immediate arguments), written down as a guess, then H and G pseudocode.
| Addr | Fingerprint (C) | H / G reading | Result |
|---|---|---|---|
| 0x401e50 | CreateVertexBuffer, CreateIndexBuffer | G: 30 VBs, 0xe10 INDEX16 filled with quad pattern | match |
| 0x40e560 | CreateTexture(0x40,1,0,0,0x15,1,0x71abb4) | G: 64x1 A8R8G8B8 ramp fill | match |
| 0x40b340 | CreateCubeTexture, CreateDepthStencilSurface | G: cube + 6 faces + 6 depth surfaces | match |
| 0x40a510 | Reset x2 | H: calls 0x401e50, 0x40a890, 0x40aa20, 0x40b340, 0x40cb80 after Reset; G merges it with 0x40a4e0 | match (G boundary differs) |
| 0x410e50 | GetDeviceCaps, LightEnable | G: caps, adapter id, disable all lights | match |
| 0x408220 | CreateVertexDeclaration x2 | G: two element arrays | match, element meaning open |
| 0x40ed70 | SetDecl, SetStreamSource, SetIndices, DrawIndexedPrimitive, DrawPrimitiveUP | H: bucket flush | match (G merges with 0x40ed50) |
| 0x40e6d0 | SetVertexDeclaration | H: effect switch | match |
| 0x409180 | 8x SamplerState ADDRESS=3, SetTexture, DrawPrimitiveUP(6,2,?,0x18) | G: textured quad | match |
| 0x410ed0 | stores to 0x736334, 0x700e74 | G: level 0..3 option table | match |
| 0x40aa20 | GetDepthStencilSurface x2 | G: 7-entry target table | partial (field meaning I) |
| 0x40a580 | TestCooperativeLevel, BeginScene, Clear, EndScene, Present | H and G same order | match |
Score: 10 match, 1 match with boundary difference, 1 partial; the fingerprint was not blind for 0x40a580 (frame order already in blur.md).

## Open
- Which of the 7 effects is which (world, car body, glass, road, particle, UI, blur filter) and what each descriptor row at 0x7010c0 means; the .efx text is loaded through 0x594c60.
- Whether the 503 D3DX functions that ran compile effects every start or only on a cache miss; the D3DX create/compile entry points `0x5af9e5/0x5afb2f` are called only from 0x40e180 and are not named.
- EAGL: 71 of 297 render-tagged functions ran. Is EAGL's device context (`[0x709d80]`, `0x620ed0`) the same IDirect3DDevice9 as `[0x73636c]` or a second one? Its role (animation `EAGLAnim`, `RenderMethod` dynamic code) is only known by strings.
- Meaning of `[0x700ea8]`, `[0x700e78]`, `[0x700e7c]`, `[0x700e80]`, `[0x700e84]..[0x700e94]` option fields (names exist only for MOTIONBLUR/LIGHTSTREAKS).
- `0x404110` (5,000 lines in Hopper, 399 in Ghidra): spray/particle drawing by type switch is I; the item layout is not decoded. `0x403a60` update is not read.
- Car body/wheel/shadow draw (`0x56dc30`, 1,493 lines H; shadow strings `*_SHADOWIG`, `BLURTEST`, `ALPHA`, `GREEN2`, `GLOSS` at 0x56a130..0x5aa800), light flares (flare_re.md) and `FEng` (hud docs) were not re-read here.
- systems.tsv: the D3DX, EAGL and funclet bands (about 1,360 functions) should leave "render"; the FEng band 0x4fa3..0x503f belongs to hud.

HANDOFF: names_render.tsv has 84 rows; next: decode the 7 effect descriptors (0x7010c0) and the .efx loader 0x594c60, then name the car draw 0x56dc30 sub-passes and the D3DX create-effect entry points.
