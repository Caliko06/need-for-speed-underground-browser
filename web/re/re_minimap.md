# The in-race minimap: how Speed.exe draws it, and why it is blurry and pale in our port

> Source: `docs/re_minimap.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 38

# The in-race minimap: how Speed.exe draws it, and why it is blurry and pale in our port

Answer first. The minimap is not geometry and not a render target. It is a baked 256x256 texture (`TRACKn_MAP`) drawn
each frame as one perspective-transformed, clipped quad, plus small rotated textured quads for the cars. Everything goes
through the game's 2D "ePoly" path (`DrawPrimitiveUP`, triangle fan). The pale look is in the exe (vertex alpha x 0.2).
The blur is our scale: the default mode shows only 1/3 of the 256 texture over about 300 px of a 2560 back buffer.

Tools: Hopper export (census/hopper/decomp.c), capstone on the exe image (.venv python), file inspection of game/,
reading host/ and web/. NOT a runtime result unless marked. No game run was made for this note.

## 1. Draw functions (Hopper export, capstone)

| Address | Role |
|---|---|
| 0x409cd0 | Race HUD pass (called from 0x40a580). Z test and Z write off (RS 7, 14 = 0), FEng render (0x4f3030), then per player 0x58e810 when `[player+0x534]` has a map object. |
| 0x58e540 | Map object ctor. Looks up `TRACK%d_MAP` (hash, 0x5461c0, TPK list 0x740418). Textures from INGAMEB.BUN: CAR_MARKER -> +0x7c, CAR_MARKERB -> +0x80, TRACKMAPFRAME -> +0x84, MAPBACK -> +0x88, START_LINE -> +0x94, BKGBMP -> +0x98. Map picture -> +0x78. |
| 0x58e810 | Per-frame draw. Copies mode (+0xc0 -> +0xc4), then: 0x58efb0 (heading, only if the rotate flag), 0x58fa50 (MAPBACK), 0x58f090 (the map quad), 0x58f640 with START_LINE (mode != 0xb), then one 0x58f640 per car (CAR_MARKER for the player, others pick colour/texture from byte_7313d4/da/dd/e0/e9/ef; the chased car uses byte_7313e9), then 0x58fa50 for TRACKMAPFRAME. |
| 0x58f090 | Map quad. Four corners via 0x590b50 (rotation and zoom with D3DX 0x5ac69c/0x5abdaf) and 0x590dd0 (perspective, focal 200, per-corner brightness byte, default 0x80). Each corner's vertex alpha byte is multiplied by the mode-row float at +0x34 (asm 0x58f4a2-0x58f512, ftol 0x674898). RGB is scaled by 200/(d+200) per corner (0x58f517-0x58f614): the far edge fades. Calls 0x58fb10 with texture +0x78, flag 0xe. |
| 0x58fb10 | 2D polygon clipper (Sutherland-Hodgman, up to 32 vertices) against the map rect; emits triangles through 0x40bef0. |
| 0x58f640 | Icon draw: the icon texture, rotated by heading, clipped by 0x58fb10. |
| 0x58fa50 | MAPBACK and TRACKMAPFRAME draw, only if row byte +0x39 != 0. That byte is 0 in every mode row, so these two are never drawn (inference from the table; NOT VERIFIED at runtime). |
| 0x590ad0 | World -> map: u=(x-X0)/S, v=(Y0-y)/S (car x,y at car+0x60/+0x64). |
| 0x40be70 / 0x40bef0 | ePoly init (vertex colour default 0x80808080) / render: packs 4 vertices (stride 0x20), half-texel UV shift (0.5/w, 0.5/h), 0x40f3d0 sets texture and blend states (via 0x410650/0x410550), then `DrawPrimitiveUP` type 6 (fan), 2 primitives. |
| 0x42e4f0 | Sets the live mode (map object +0xc0). 1 player: from saved byte_78a3f6, validated against table dword_6f03d4 = {1, 3, 11, 5, 6}, default 1. 2 players: byte_78a3f7. Fallback 6. |
| 0x4bf610 | Options menu: cycles byte_78a3f6 / saved dword_7588ec through 1 <-> 3 <-> 6. |
| 0x5912b0 | Fills the mode table at 0x737850, stride 0x3c, 12 modes. |

Correction to `re_trackmap`: "mode 6 shows the whole picture" is wrong. Row 6 is all zeros and means
"map off". The live mode comes from the saved option (1, 3, 11 or 5); the shots match 1 or 3.

## 2. Data source

- Picture: `TRACKn_MAP` in game/Tracks/TEX<id>TRACK.BIN, 256x256 A8R8G8B8 (raw BGRA), single level. For 1001 the pixels are at
  file offset 0xaad00, 262144 bytes. The route is already painted light blue (~170,200,255); the city is dark teal
  (mean RGB 28,55,66); alpha mean 237 (transparent border). No road nodes are read at draw time.
- Bounds per track: GLOBALB chunk 0x34201 rows, stride 0xFC: +0x6c id, +0x8c X0, +0x90 Y0, +0x94 S, +0x98 rotation,
  +0x9a/+0x9c start/finish angles.
- Icons and frame: INGAMEB.BUN (see ctor above).
- Placement: the FEng element `track_map_placeholder` gives centre (+0x68/+0x6c) and half size (+0x70/+0x74); the mode row adds to it.

## 3. Exact draw path

1. Mode row (base 0x737850 + mode*0x3c). Fields that matter: +0x4 = 200 (focal); +0x10/+0x14 half-size additions (mode 1: 37/75; mode 3: 30/30);
   +0x18/+0x1c fraction of the picture shown (mode 1: 0.564 x 0.284; mode 3: 0.33 x 0.33; modes 0, 5, 7-9, 11: whole);
   +0x28/+0x2c icon size (mode 3: 0.04/0.185; mode 1: 0.025/0.135); +0x30 rotate with heading, +0x31 follow player,
   +0x32 rotate icons (modes 1, 3, 10: all 1); **+0x34 alpha multiplier: 0.2 for modes 1-4, 7, 8, 10; 0.29 for 5 and 9; 1.0 for 0 and 11**;
   +0x38 draw flag (1 except mode 6); +0x39 frame flag (0 everywhere).
2. Map quad: 0x58f090 -> corners with brightness fade -> vertex alpha x row+0x34 -> 0x58fb10 clip -> 0x40bef0 per triangle -> fan.
3. Cars: 0x58f640 per car; heading = car+0x3b4 minus row+0x98; in rotate modes the arrow angle is 180 deg + player heading - car heading.
   Conditions on car+0x4d0 and car+0x8a9. Loop over `[0x7361f8]`.
4. State: no render target and no off-screen texture. Direct to the back buffer, after FXAA, bloom and psblur, so none of those touch it.
   Sampler defaults from device init: MIN/MAG linear, MIP point, address clamp. The texture has one level, so filtering is plain bilinear.
5. Size: the HUD is 640x480 virtual. Our PATCH 0x40bf09 (tools/recomp/patches.py:31-39) maps it to a centred 4:3 island:
   at 2560x1116 about 2.325 px per virtual unit (island 1488 px). The map box measures about 295x307 px in the 2560 frame
   (about 115x120 in the 1000 px shots).

NOT VERIFIED: which vertex and pixel shader the ePoly effect uses (0x71abb8 / `[0x73640c]`), the exact blend factors
(render states 19/20 chosen in 0x410550), whether the pixel shader doubles alpha, and the placeholder half size in virtual units.
It is not in game/fx/*.efx (decrypted, no 2D shader there). One run with RN_VS=1 or RN_TRACE settles it.

## 4. Why it is blurry and pale in our port

Pale (faithful to the exe): vertex alpha 0x80 x 0.2 is about 25/255, so the dark teal ground is nearly invisible and only the
bright route shows. The original at 640x480 looks the same kind of faint. This is design, so it stays in RN_MAP=0.

Blurry (our scale, two causes):
1. Magnification. Mode 1/3 shows 1/3 (or 0.56 x 0.28) of a 256 texture. That is about 85 texels stretched over ~300 px: ~3.5x,
   against ~1.5x in the original at 640x480. Bilinear on a 256 texture at 3.5x is soft.
2. The texture has one level, so `host/d3d9.c:2008` writes `t[T_MIP] = 0` (`tx->levels > 1 ? dev.ss[k][7] : 0`) and
   `web/gpu.js:590` sets `lodMaxClamp = 0`. The ANISO bridge at `web/gpu.js:593` needs a non-zero T_MIP, so it never applies.
   No sharper filter exists for single-level HUD textures.

The remaster pack already replaces the map for track 1001: key 029832a82daf9507 (FNV-1a 64 of the 262144 pixel bytes, computed in
`host/d3d9.c:1299-1307`, GPU_TEXKEY) is in web/remaster/index_world_v2.tsv and index_world_bc.tsv -> world2/029832a82daf9507.webp,
1024x1024 RGBA (4x UltraSharpV2). `web/gpu.js:106-188` (HD_MAX 1024, useHd/loadHd) binds it. So for 1001 the picture is already 1024;
the blur that remains there is from the 0.2 alpha plus the HUD being drawn at 2560 with bilinear and no sharpening of the quad
itself (and the pack image has no visible white border). Other tracks: NOT VERIFIED whether they have a pack hit.
The HUD edge bridge (`host/d3d9.c:2506-2560`) only shifts the whole quad in X, it does not scale or filter it.

## 5. Variants (switch RN_MAP, 0 = original)

Common hook: `host/d3d9.c` DrawPrimitiveUP / draw_cmd already knows the bound texture. Tag a draw as "minimap" when its
texture key is a `TRACKn_MAP` (the pack key family) or an INGAMEB marker; pass one flag in the draw command (reuse an unused
t[] slot next to T_MIP at line 2008). `web/gpu.js` reads RN_MAP once (RN_Q style, like `sharp`/`hdmax`).

- RN_MAP=0: original. Nothing changes.
- RN_MAP=1, sharp at full resolution: keep shape and alpha 0.2. For tagged draws force `T_MIP` to 2 and use the HD texture with a full
  mip chain (loadHd already builds it), Catmull-Rom or bicubic sampling in the map fragment (small WGSL variant in `web/gpu.js`
  near the HUD note ~1107), or CAS only on the map rectangle. Lowest risk; fixes the soft look.
- RN_MAP=2, 1 + soft glow on route and border: extra pass for tagged draws: draw the quad a second time slightly blurred (3x3
  taps in the shader) with additive blend, lower alpha (~0.1), tinted light blue. Border: reuse the quad's transparent edge so it
  glows without a new texture. Hook: a second draw in `host/d3d9.c` DrawPrimitiveUP at the tag, or a shader branch in `web/gpu.js`.
- RN_MAP=3, 2 + clearer car arrows: the CAR_MARKER/CAR_MARKERB draws (0x58f640) are small, 0.025-0.04 wide. Tag them, draw with the
  same sharp sampler, add a 1 px dark outline (4 offset taps in the shader) and raise their alpha toward 1.0 (they also
  receive the 0.2 multiplier only if routed through the map's alpha path; NOT VERIFIED). Their pack keys are unknown (NOT VERIFIED);
  if no pack texture exists, the outline shader carries the improvement.
- Optional (variants 1-3 only): raise the 0.2 multiplier. It is a float in the mode rows at 0x737884 + mode*0x3c (mode 1 = 0x7378c0,
  mode 3 = 0x737938). Put it behind RN_MAP in the patch table (tools/recomp/patches.py), one line with why.
  The exe's own value stays for RN_MAP=0.

## 6. Next check (one run, bounded)

RN_VS=1 / RN_TRACE on a race frame to read the ePoly shader and blend factors; RN_TEXHASH to confirm the map and marker keys and
the in-race mode (1 vs 3). Then A/B the four values in one strip.
