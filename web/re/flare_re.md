# Car light flare size (PC Speed.exe vs PS2 SLUS_208.11)

> Source: `docs/flare_re.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 31

# Car light flare size (PC Speed.exe vs PS2 SLUS_208.11)
Marks: V = read in disassembly/decompile this session, I = inferred, U = open. PC: Ghidra headless (build/ghidra/proj). PS2: ref/tools/rea/out/corpus/c and ref/docs/re/flares.md.

## 1. PC formula
Chain: 0x56d8d0 (car markers) or 0x544e90/0x544f30 (lamps) -> 0x5447c0 -> 0x5443f0 (quad). Per layer (V):
- x = min(1, pow(facing, rec[0x28]) * intensity). facing = |dot| (flag bit 0) or max(dot, 0). Intensity 1.0 head, 0.7/0.35 tail.
- alpha = rec[0] + (rec[4] - rec[0]) * x. Skip if alpha <= 0, so a lamp facing away draws nothing.
- k = clamp(z / [view+0xc], rec[0x30], rec[0x34]). z = view depth (I).
- half-size in world = alpha * k * 1.5. The 1.5 (0x6b633c, one reader 0x5444a9) is skipped only when mode == 2.
- Quad = centre +- right*half +- up*half (camera axes); centre pulled toward the camera by rec[0x2c]. Colour lerps rec[8..0x14] -> rec[0x18..0x24] by x; alpha * fade; limit 255 (0x6f41a4).
- Fade on squared distance (I) 32000..40000 (0x6b6350/54); lamps mode 1 3900..4000 (0x6b6360/64). Texture = 0x72fa14[rec[0x38]].
- [view+0xc] (writer 0x40dd00 via 0x40dcb0) = ([0x701034] >> 1) / tan(fov/2). [0x701034] is the back buffer WIDTH (writer 0x4086b0). It is the horizontal focal in pixels: 756 at 1280 wide, I: 1512 at 2560.
- Modes (V, call sites in 0x409580): view 0x7405e0 -> 570d00(1)/570c70(1)/544f30(2) = mode 2 (I: the reflection view; PS2 mode 2 is views 4..5). Every other view (0x740580, the flare-buffer path 0x409b70 with 0x7404c0) passes 0 = mode 0 = the 1.5 applies.

Descriptors (table 0x6f4150, two per type, 0x3c bytes; V from the dump):
| addr | alpha lerp | colour end RGBA | exp | pull | k min..max | tex |
|---|---|---|---|---|---|---|
| 0x6f3ef8 | 0..64 (+0,+4) | 100,120,170,80 | 1.45 | 0.8 | 0.01..0.015 (0x6f3f28/2c) | 0 |
| 0x6f3f34 | 28..28 | 100,120,140,20 | 3.0 | 0.8 | 0.01..0.015 | 1 |
| 0x6f3f70 | 20..30 | 128,0,0,80 (red) | 1.0 | 0.2 | 0.01..0.02 | 2 |
Types 0, 7, 8 draw rec0 + rec1; the rest as the PS2 table. I: the blue star is rec0. U: which type the car head markers carry (+0xd comes from the model file).

## 2. Resolution dependence (I, from the V formula)
F = [view+0xc]. Screen half-size in px = alpha * k * 1.5 * F / z.
- z/F between 0.01 and 0.015: k = z/F, size = alpha*1.5 = up to 96 px, fixed in PIXELS. It does not grow with resolution.
- z < 0.01*F: k = 0.01, size fixed in WORLD: 0.96 m half (1.9 m quad) at x = 1, px = 0.96*F/z. This zone widens with width: z < 3.8 m at 640, 7.6 m at 1280, 15 m at 2560. Front-end and post-race cars (z about 4-8 m) are here.
- z > 0.015*F: world 1.44 m half.
- As a share of WIDTH the star equals 640 when clamped and is smaller when not. As a share of HEIGHT it is about 1.7x the 4:3 value at 2560x1116 (0x40dd00 builds the vertical angle from fov*H/W; flare size uses the horizontal focal only), like the whole car.
- So resolution does not make the star bigger than native relative to the car. It is big natively: a 1.9 m quad on a 4.4 m car when the lamp faces the camera.

## 3. PS2 (V: corpus 0x29ad30, 0x29b198, 0x101098; tables in ref/docs/re/flares.md)
- Same code and tables (0x4d99b0 = PC 0x6f3ef8, same numbers), same fade, same k clamp 0.01..0.015, same pow (bit trick, floor 0.01).
- view+0xc (0x10a7f8 -> 0x101098) = (target width at +0x1c >> 1) / tan(fov/2): same formula, width 512 (0x4ff424). Car lights 0x2cb598 -> 0x29b198 modes 0/1/2; mode 2 only scales z by 10 (0x50329c).
- DIFFERENCE (V): PS2 0x29ad30 has NO 1.5. size = lerp * k, so max half = 64*0.015 = 0.96 m; PC main view max = 1.44 m. PS2 star = 2/3 of PC at every distance.
- PS2 draws flares into the half-res GLOW buffer (postfx-elf.md), 2x down and up: softer and blurrier than the PC sharp quad. Same star texture? U (PS2 slots 0,1 are hashes only).
- PC mode 2 (reflection) skips the 1.5, so it already equals PS2.

## 4. Our layer (read only)
- Quads are the game's own geometry; host/ adds no size. F follows the game's back buffer width. U: that [0x701034] equals the real canvas width on every screen (check RN_WATCH=701034 in the front-end).
- web/gpu.js bloom (l.322-391): quarter-res bright pass (luma > 0.72), 9-tap blur (about +-16 full-res px), added at 0.2. ?bloom=lights: 0.55 / 0.35. A fixed pixel halo, not scaled with the star. I: adds little to a blue star (luma under 0.72), more in lights mode. U: not measured on screen.
- host/lights.c changes intensity only (tail 0.7 -> 0.35), not size.

## 5. Lever
Write float 1.0 (0x3f800000) at 0x6b633c (only reader 0x5444a9; patch it in the host like 0x6b5da0). Main-view stars shrink by 1/3 linear = PS2 size. If still large: lower rec0 alpha end 0x6f3efc (64.0) and rec1 0x6f3f38 (28.0) together; that is a taste choice, the PS2 values are the same 64/28. Leave k min/max (0x6f3f28/2c) alone: they set the zone limits above.
NOT VERIFIED on screen (no build, no run, per brief).
