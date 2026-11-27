"""Patches: widescreen, blur, car look, flares, road reflection. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES, _rel

# PATCH: 0x40bf09.., widescreen 2D: the sprite quad code (0x40beef) turns a position of the 640x480 screen into clip
# space as x/320 - 1 and 1 - y/240 for each of its four corners. The 4:3 layout was stretched over the whole
# back buffer. The x of each corner now uses x*(S/320) - S, with S = (4/3)/(W/H) (at most 1), so the 2D layer keeps
# its 4:3 shape, centred. S/320 and S live at SCREEN_ADDR+8 and +12 (host/win32.c). Operands of fmul [0x6cc914]
# and fsub [0x6cc7bc].
_OLD_MUL, _OLD_SUB = "14c96c00", "bcc76c00"
for _a in (0x40bf09, 0x40bf9a, 0x40bfff, 0x40c053):
    PATCHES.append(dict(addr=_a, old=_OLD_MUL, new="08300100", when=lambda: True))
for _a in (0x40bf17, 0x40bfa0, 0x40c00b, 0x40c064):
    PATCHES.append(dict(addr=_a, old=_OLD_SUB, new="0c300100", when=lambda: True))

# PATCH: 0x4f2f13 (+ caves 0x689391, 0x688b61: CC padding after a jmp, no call, jump or pointer reaches them), widescreen race
# screens: the FEng render 0x4f2eb0 walks its draw lists (0x746910..) and draws each object with 0x4f2cb0 (eax = FEObject,
# edi = the render; type 1 image 0x4f2000, 2 string 0x4f25f0, 9 multi-image 0x4f2280, cached nodes 0x514b90), whose quads
# reach DrawPrimitiveUP (0x40bef0) before it returns. That call now goes through cave A, which leaves the object in
# SCREEN_ADDR+0x40 while it draws and clears it after (cave B), so host/d3d9.c moves each race screen package as a whole, not single quads.
#   A: mov [0x13040],eax; call 0x4f2cb0; jmp B        B: and dword [0x13040],0; ret
PATCHES.append(dict(addr=0x4f2f13, old="e898fdffff", new="e8" + _rel(0x4f2f13, 0x689391), when=lambda: True))
PATCHES.append(dict(addr=0x689391, old="cc" * 15, entry=True, when=lambda: True,
                    new="a340300100" + "e8" + _rel(0x689396, 0x4f2cb0) + "e9" + _rel(0x68939b, 0x688b61)))
PATCHES.append(dict(addr=0x688b61, old="cc" * 8, new="832540300100" + "00" + "c3", when=lambda: True))

# PATCH: 0x408a24, widescreen: the first CreateDevice (0x408830) asked for 800x600 with push 0x320 / mov esi,0x258 and
# [0x702a80] = 0x15 (D3DFMT_A8R8G8B8). It now asks for the screen size at SCREEN_ADDR, so the front end is drawn at the
# size the race is. Same bytes count: push [0x13000]; mov esi,[0x13004]; push 0x15; pop [0x702a80]; the call stays.
PATCHES.append(dict(addr=0x408a24, old="6820030000be58020000c705802a700015000000",
                    new="ff35003001008b35043001006a158f05802a7000", when=lambda: True))

# PATCH: 0x4494c4, widescreen: back to the front end after a race, 0x449497 puts the device back to 800x600 (push 0x320 /
# mov esi,0x258; call 0x4086b0) unless the resolution option [0x700e70] is 1 (800x600 already). It now asks for the screen
# size, as 0x408a24 does at the start. Same 18 bytes: mov esi,[0x13004]; push [0x13000]; call 0x4086b0; pop ecx
# (for add esp,4: ecx is free here, the jmp 0x40a4e0 that follows takes no register).
PATCHES.append(dict(addr=0x4494c4, old="6820030000be58020000e8ddf1fbff83c404",
                    new="8b3504300100ff3500300100e8dbf1fbff59", when=lambda: True))

# PATCH: 0x702a38, OWNER 2026-10-21 (blur visible, as on the PS2): the PC motion blur 0x40cd40 weights its half-size
# copy by t = (|camera +0x1e0| - [0x702a38]) / ([0x702a3c] - [0x702a38]) + 1.1 * nitrous, at most 0.65 ([0x702a40]).
# PC ramp 25 -> 125 m/s: no blur under 90 km/h, full at 450 km/h. Now the PS2 ramp 0.1 -> 25 m/s (SLUS_208.11 0x4ff95c,
# 0x4ff960; ref/docs/re/postfx-elf.md). The PC algorithm and its 0.65 cap stay. Only 0x40ce70/0x40ce7a read them.
PATCHES.append(dict(addr=0x702a38, old="0000c8410000fa42", new="cdcccc3d0000c841", when=lambda: True))
# PATCH: 0x702a40, OWNER 2026-10-21 (the blur was too strong): the composite weight is min(1.5 * t, 1), so the PC cap 0.65
# put 97% of the blurred copy on screen from ~56 mph. The cap is now 0.26: weight 0.39, the strongest PS2 copy
# (alpha 50/128, SLUS_208.11 0x4485f0). The streak length scales with t too. Only 0x40ced6/0x40cee2 read it.
PATCHES.append(dict(addr=0x702a40, old="6666263f", new="b81e853e", when=lambda: True))

# PATCH: 0x40d615, 0x40d2a2, game bug (EA's 2011 patch notes call it the "NOS black screen effect"): the 4-tap blur passes
# 0x40d370 and 0x40d090 turn blending off with effect->SetInt(BaseAlphaBlendEnable, 0) when an effect is current, but
# filter.efx pass p3 never reads that parameter. The pass then inherits the light-streak decay state (blend on, ZERO /
# BLENDFACTOR 0x8296b4, restored by the D3DX End state block), so the blur copy never receives the scene and fades to
# black; the frame is then mostly that copy. The jne goes: both always take the SetRenderState(ALPHABLENDENABLE, 0)
# branch that is already there for "no effect".
PATCHES.append(dict(addr=0x40d615, old="7512", new="9090", when=lambda: True))
PATCHES.append(dict(addr=0x40d2a2, old="7512", new="9090", when=lambda: True))

# PATCH: 0x702a84, OWNER 2026-10-21 (sharper cars): the car reflection cube (0x40b340, ENVMAP) is 128 px a side; every
# reader (0x40aa20 view table, 0x40b340 cube and its depth surface) takes the size from here. Now 512.
PATCHES.append(dict(addr=0x702a84, old="80000000", new="00020000", when=lambda: True))

# PATCH: 0x40debb, 0x40deec, 0x40dcdb (+ caves 0x408799, 0x5f4a04, constant 0x707fc0), OWNER 2026-10-22: the camera look of
# the PS2 build. RE (Speed.exe): 0x40dd00 builds a view's projection from the camera FOV u16 F (0x484b53: 0x32dc = 71.5 deg).
# P[0] (view+0x40) = 1/tan(F/2): the horizontal view is fixed. P[5] (view+0x54) = -1/tan(A*F/2), A = viewport H/W (+0x18 / +0x14,
# view+0x58 struct) times 1.21 for view types 1, 2, 4, 5: the angle (not the tangent) follows the aspect, so 16:9 gives a 48 deg
# vertical view and pixels 12% too tall. 0x40dcb0 returns the focal length into view+0xc. The PS2 (SLUS_208.11 0x10a7f8) keeps the
# VERTICAL view (zoom 256/tan(F/2) over 512 x 448 = 64.4 deg) and widens x with the window. Now (types other than 8, 9), with
# k = 512/448 ([0x707fc0], free .data) and H' = max(H, 9W/16): P[0] = k/tan(F/2) * H'/W, P[5] = -P[0] * W/H. Up to 16:9 this is the
# PS2 look; wider windows stop at the 16:9 horizontal view (96 deg) and crop top and bottom, since the edge stretch of a flat
# projection past that made traffic look squashed wide. Focal (view+0xc) = (H'/2) k / tan(F/2), the same scale. Cave 0x408799 =
# A (P[0]) + fallback + focal; cave 0x5f4a04 (CC padding) = B (P[5]) + fallback. W is [0x701034], H is [0x701038].
# The 16:9 cap is for races only ([0x77a920] == 6): the front end keeps H' = H, so its 3D (the car on a magazine cover,
# full-screen viewport) keeps the scale of the 2D layout, which stays 4:3 and centred (PATCH 0x40bf09); with the cap the
# cover car was 1440/1116 = 1.29x too big at 2560x1116 and ran past the cover (runs/magn_wide, 2026-10-26). The focal
# keeps the cap (no room). The fallback (types 8, 9) puts back eax = ebp, the angle 0x40dec3 passes to sin 0x564b10.
PATCHES.append(dict(addr=0x707fc0, old="00000000", new="2549923f", when=lambda: True))
PATCHES.append(dict(addr=0x408799, old="909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090",
                    new="d83dbcc76c008b4c241c8a410424fe3c08742e8b4958d80dc07f7000803d20a97700068b4118750f6b411409c1e8043b41187f038b411850db042458da7114dec9d91f89e8e9e056000090a1341070008d04c0c1e8058b0d38107000d1f939c87f0289c8890424da3c24d80dc07f700059c3", when=lambda: True))
PATCHES.append(dict(addr=0x5f4a04, old="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                    new="8b44241c83780408741c8378040974168b4058ddd8d907db4014dec9da7018d9e0d95e54eb0bd83dbcc76c00d9e0d95e54e9bd94e1ff", when=lambda: True))
PATCHES.append(dict(addr=0x40debb, old="d83dbcc76c00d91f",
                    new="e9d9a8ffff909090", when=lambda: True))
PATCHES.append(dict(addr=0x40deec, old="d83dbcc76c00d9e0d95e54",
                    new="e9136b1e00909090909090", when=lambda: True))
PATCHES.append(dict(addr=0x40dcdb, old="a134107000d1f889442400da7c240059c3",
                    new="e904abffff909090909090909090909090", when=lambda: True))

# PATCH: 0x56e0d2, OWNER 2026-10-22 (remastered cars: rivals and traffic looked odd): the car draw 0x56dc30 picks the model
# LOD from its screen size, ftol(focal view+0xc * 3 / (dist - 3)) (0x545180), stepping up while size < [0x6b5dec + 4*lod] =
# 120, 45, 20, 0 px. With the focal of 0x40dcdb (~857 at 1080 lines) a rival is the full model only within ~24 m and model B
# out to ~60 m. The jp that enters the step loop is now a jmp: every car keeps the minimum LOD its caller asks for (0 = full;
# the reflection views pass 1, 0x6f1b38). The table stays: 0x56e77e fades by (size - 20) / (45 - 20).
PATCHES.append(dict(addr=0x56e0d2, old="7a1f", new="eb1f", when=lambda: True))

# PATCH: 0x409bdb (+ weight 0x707fcc), OWNER 2026-10-22 (light flares blind the view) and 2026-10-26 (now the trails are
# gone; wants the aura around moving lights back): with LIGHTSTREAKS (0x700e9c) the flares 0x544f30 go only into a half-size
# buffer 0x71abb0 (0x409b70). Each frame that buffer is multiplied by BLENDFACTOR k = 0x008296b4 (ZERO / BLENDFACTOR quad,
# filter.efx p0, mode 0xe) and then added to the screen (ONE / ONE, mode 2) modulated by the colour at [esp+8], 0x1fffffff
# (both 0x40d6e0 calls point at that slot; the decay quad ignores it, source factor ZERO). A still light builds to
# w/(1 - k): R 2.0x, G 2.4x, B 3.4x (the blinding, blue-white lamps); a moving one leaves a trail of 4.4 / 5.6 / 8.6 frames
# at 60 fps (73 / 93 / 143 ms). That decay stays as shipped: it is the PS2 trail in time (SLUS_208.11 glow buffer loses
# (90,79,53) per 30 fps frame: 94 / 107 / 160 ms; ref/docs/re/postfx-elf.md). The 2026-10-22 patch (k / 4, w 0.55)
# cut the trail to 1.7 frames and a still lamp to 0.65x, so the aura vanished. Now the colour comes from [0x707fcc] (free
# .data, no reference in the exe), set per channel to s (1 - k): a still light is s times its own flare in R, G and B alike,
# and the trail keeps the game's length. Default s = 1.5 (0x1fbc9e71); web/tune.js sets s per blur preset (F6/F7).
# The block 0x409bdb..0x409bfe is rewritten in place: same args to 0x40d6e0, same ecx / edx / eax as before the call.
PATCHES.append(dict(addr=0x707fcc, old="00000000", new="719ebc1f", when=lambda: True))
PATCHES.append(dict(addr=0x409bdb, old="8b46186a0e6a016a018d4c2414518d54241c52894424206a0133c0c7442420ffffff1f",
                    new="8b46188d4c2408894104a1cc7f700089018d51046a0e6a016a0151526a0131c0909090", when=lambda: True))

# PATCH: 0x40fbb7..0x40fc38, OWNER 2026-10-22 (less car reflection): 0x40fae0 sets the car material constants of car.efx.
# EnvmapMin = mat+0x84 * mat+0x80 * 0.5 and EnvmapMin + EnvmapRange = mat+0x94 * mat+0x90 * 0.5, both with the shared 0.5
# at [0x6cc7dc]; the shader adds 4 * diffuse.w * cube * (EnvmapMin + f * EnvmapRange). These six fmul now read 0.35 at
# [0x707fc4] (free .data, next to 0x707fc0): the cube reflection is 70% of the original. Specular and diffuse keep 0.5.
PATCHES.append(dict(addr=0x707fc4, old="00000000", new="3333b33e", when=lambda: True))
for a in (0x40fbb7, 0x40fbcd, 0x40fbe3, 0x40fbf9, 0x40fc1e, 0x40fc38):
    PATCHES.append(dict(addr=a, old="d80ddcc76c00", new="d80dc47f7000", when=lambda: True))

# PATCH: 0x410c1b (+ cave 0x63b3ad, the tail of the same dead CRT routine, 19 bytes past the unlock caves, no reference), OWNER 2026-10-27
# (?roadrefl=off, "wet everywhere"): 0x410b70 sets the hardware cap of the options, among them ROADREFLECTION [0x70105c]:
# ecx = (2 < [0x71ad84] ? -1 : 0) & -2, + 2 -> 2 (0 if [0x71ad84] > 2); 0x410a00 then clamps [0x700e90] to it (28292 of decomp.c) and
# 0x409580 draws the mirrored world into the 320x240 RT only while [0x700e90] > 1 (the RT is cleared black at level 1: a dry road).
# The 5 bytes `and ecx,-2; add ecx,eax` become a call to a cave doing the same with a word in SCREEN_ADDR+0x70 for the 2:
#   not ecx; and ecx,[0x13070]; ret      (ecx = 0 or -1 from the sbb; same result with the word = 2)
# host/win32.c writes the word: 1 with RN_ROADREFL=off (the game's level 1), else 2.
PATCHES.append(dict(addr=0x410c1b, old="83e1fe03c8", new="e8" + _rel(0x410c1b, 0x63b3ad), when=lambda: True))
PATCHES.append(dict(addr=0x63b3ad, old="68f4700001e8d9660000" + "81c40c010000c39090", entry=True, when=lambda: True,
                    new="f7d1230d70300100c3" + "cc" * 10))
