# Night lighting in Speed.exe

Sources: Ghidra headless (tools/ghidra/gpar.sh on build/ghidra/proj), Hopper batches build/hopper/{hlproj,carlight,worldflare}.txt,
game/fx/*.efx (XOR 0xAA text HLSL). Checked at runtime with RN_WATCH/RN_POKE (native and Chrome).

## Graphics options (table 0x700ef0: name, flag, 12 bytes each)
| Option | Flag | Read by | Note |
|---|---|---|---|
| HEADLIGHTS | 0x700e80 | 0x408f00 (adds view 7), 0x40c910 (material remap), 0x409580 | projected headlight |
| CARLIGHTING | 0x700e84 | nobody | dead option |
| ROADREFLECTION | 0x700e90 | 0x40c910, 0x408f00 | picks the *reflect techniques |
| MOTIONBLUR | 0x700e98 | 0x409580, 0x40b3f0, 0x40cb80 | |
| LIGHTSTREAKS | 0x700e9c | 0x409580, 0x40b3f0, 0x40cb80 | flare buffer 0x71abb0 (PATCH 0x409bdb) |
| LIGHTGLOW | 0x700ea0 | 0x409580, 0x570c70 (racers), 0x570d00 (traffic) | car light flares |
| DEPTHOFFIELD | 0x700eac | nobody | dead option |
Presets: 0x410a00 scores the machine (0x41eff0, score 0x701088; < 0.3 / 0.6 / 0.9 = preset 0 / 1 / 2) and
0x410ce0 clamps each flag to the cap table 0x701040. Preset 1 sets HEADLIGHTS, MOTIONBLUR, LIGHTSTREAKS = 0.
At real clock our CPU scores 0.92 (preset 3, all on). RN_TURBO=4 lowers the score: turbo runs have no headlight.

## Projected headlight (one, the player's)
- 0x408410 turns view 7 (0x740760, flag 0x740768) on in a race with the player view. 0x408f00 adds it when HEADLIGHTS.
- 0x40c910: with flag 0x200 and HEADLIGHTS, world materials remap world -> worldheadlight (0x706818) or
  worldreflect -> worldheadlightreflect (0x706798).
- Effects 0x7014e0 + 0x80*i (world, worldheadlight, worldreflect, worldheadlightreflect, worldbone, car, filter);
  per-effect setup callbacks 0x702420 + 4*i (0x40e740 worldheadlight, 0x40e900 worldheadlightreflect).
- Parameter names 0x701860 + 0x40*k; the effect object keeps handle k at dword 7+k.
- Per draw 0x4100a0: HeadlightWVP (handle 0xe) from the view-7 matrix, HeadlightClipMat (0x2e), HeadlightColor
  (0x1c) = (0.8, 0.8, 0.9, 0) from 0x7010ac..0x7010b4 (constant, never written).
- HeadlightTex = texture "HEADLIGHTS" (cone shape). HeadlightClipTex 0x71abb4 = 64x1 built by 0x40e560: u = w*0.005+0.5,
  texels 0..32 = 0, 33..47 = 255, 48..63 = 239..0: light from ~3 m, full to ~50 m, gone at ~100 m.
- Shader: out = (headlight * clip * HeadlightColor + vertex colour) * diffuse * 2.
- Chrome draws it: A/B at 51.5 s on 1001 with RN_POKE=700e80=1/0 (same frame) shows the lit road.

## Car light flares (0x56d8d0, every racer and up to 99 traffic cars, gate LIGHTGLOW)
- Markers per model (list at car+0x500), by name hash (h = h*33 + c from -1): LEFT/RIGHT_HEADLIGHT 0x9db90133 /
  0xd09091c6, LEFT/RIGHT/CENTRE_BRAKELIGHT 0x31a66786 / 0xbf700a79 / 0xa2a2fc7c.
- Intensity: headlight 1.0 (0x6b5d9c); tail 0.7 (0x6b5da0), 0.85 (0x6b5da4) for car type 3; brake adds
  16 * [car+0x1e4] when > 0.05 (0x6b5dac, 0x6b5db0); everything clamps to 1.0, so a brake goes 0.7 -> 1.0 only.
  Debug forces: 0x7345e4 (head +1), 0x7345e8 (tail +1). Broken lights (damage state 0xd/0xe) skip a group.
- Each flare -> 0x5447c0: fade by distance, mode 0/2 from 32000 to 40000, mode 1 3900 -> 4000; type index +0xd picks
  textures from 0x6f4150 (2 per type); then 0x5443f0 draws the quad.

## Track lamps (0x544f30 from 0x409580 / 0x409b70)
Per visible track section (0x446fd0) a list of flare records, each to 0x544e90 / 0x5447c0 as above.

## Speed blur (0x40cd40, from 0x409580)
Speed = |v| of [0x740500]+0x1e0. t = clamp((speed - [0x702a38]) / ([0x702a3c] - [0x702a38])) + 1.1*[0x73641c],
capped by [0x702a40]; [0x73641c] ramps toward [0x73654c] (nitrous) by 0x702a48 / 0x702a4c per frame. The previous
frame (0x71ab9c, 0x71aba0) is drawn back zoomed toward the centre (offset x [0x702a44] streak) with that alpha:
a zoom feedback blur. web/tune.js presets write 0x702a38..0x702a44.

## Bridge host/lights.c (Block 7 parts 1-2, RN_LIGHTS=0 = shipped; F4 Original sets it)
REA (Ghidra 12.1.4, Speed.exe sha256 c0fad450...) checked each target before the patch: 0x6b5da0 has one reader
(0x56d9d7, ev_7cff0ca1), 0x7010ac one (0x4102ad in 0x4100a0, ev_0ee4a966), the cave 0x43a7e4 no reference and is CC
padding after the jump table at 0x43a7d8 (ev_6a127f7b, ev_a6bf0c32).
- Tail base 0.7 -> 0.35: a brake (16 * [car+0x1e4]) still clamps to 1.0, so braking now doubles the flare.
- Dropped (OWNER 2026-10-27, "too bright, the game feels slow"): HeadlightColor (1.0, 0.94, 0.82) and PATCH 0x40e6b5
  (full light to ~73 m). The player's headlight is the 2003 one again; 60 fps were steady in that session (p50 16.7 ms),
  so the slowness was the look: a long bright beam shows the road far ahead instead of pulling it out of the dark.
Chrome: RN_WATCH=6b5da0 reads 0.7 with RN_LIGHTS=0 and 0.35 by default.

## Part 3: projected headlights for rivals and traffic (bridge host/lights.c + host/sm1.c SM1_HL_*, web only)
REA (Ghidra 12.1.4) + runtime (RN_LIGHTSLOG, native and Chrome):
- 0x4100a0 (from 0x40ed50, EAX = 0x740760, ECX = the object World): HeadlightWVP = World x VP x S (ev_dfdc8ea9),
  VP = [[0x740760]]+0x80, S = T(0.5, 0.5, 0) (0x6cc7dc = 0.5, ev_f9491a5a). The block [0x740760] (0x78b340 at run time):
  +0 View, +0x40 Proj (near 1, far 100, y flipped), +0x80 View x Proj. 0x40bc10 = rigid inverse T(-p) R^T (ev_575f101e).
- View table 0x740460 + i * 0x60: +0 camera block, +8 enable, +0x40 camera object (0x40a7f0). Headlight view = entry 8
  (0x740760, enable 0x740768, set by 0x408410 from HEADLIGHTS 0x7364a4; ev_cf65f4e9).
- Measured: the projector sits 0.75 m above the player car's position, z axis = car x axis tilted 5.7 deg down,
  constant over a whole race. So VP_k = W_k^-1 W_p VP; the GPU takes tp_k = tp x M_k, M_k = (VP S)^-1 W_k^-1 W_p VP S.
- Cars in a race: list [0x7361f8] (0x570d00, ev_1ea79100), head node, next at +0, [+0x4d4] model ([model] = the node),
  matrix +0x90 rows 0..2 + position +0x50 (+0x4e0 / +0x520 when bit (1 << view) of +0x530; always 0 seen). The racer
  list 0x73d6d8 (0x570c70) is empty in a race; it holds the front-end cars. ~17 cars: 4 racers + traffic.
- Shaders (vs_1_1 / ps_1_1): worldheadlight vs 67da8f41 (oT1 = tp xyzw, oT2.x = w * c9.x + c9.w) / ps 91d5deec
  (t1 x t2 x c0 + v0, x t0 x2); worldheadlightreflect vs 102e066d / ps 9bb3f7c7 (+ t3 reflection). Clip ramp 64x1
  (0x40e560 CreateTexture 64, 1). t4..t7 are free: 4 more projectors from VS c16..c31.
- First try summed the cones and burnt the grid white (4 cars aim at one road); lights now combine as a screen,
  1 - (1 - Lp) prod(1 - g h_k), g = SM1_HL_GAIN 0.4, each ramp read at 1.5 x depth (SM1_HL_REACH). A/B in Chrome at the start of race 1001: rival cones on the road, no burn.
