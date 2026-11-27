"""Patches: feel candidates and feel defaults. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES

# ---- FEEL CANDIDATES (docs/re/feel_patch_plan.md): one patch per OWNER complaint, ALL OFF ----------------------------------
# Not one of these is in PATCHES: active(), c_table() and the loader never see them until Main flips a candidate. To flip, change
# that candidate's `when=lambda: False` to `when=lambda: True` and rebuild; the build stops if `old` no longer matches.
# Every `old` below was read from pc/Speed.exe (tools/recomp/asm.py read(addr, len)); 0x707fd0 was checked for references (none).
FEEL_CANDIDATES = [
    # FEEL-C1 BLUR (feel_2026-10-31.md 2; already patched: ramp 0.1-25 m/s at 0x702a38, cap 0.26 at 0x702a40, blend bug 0x40d615).
    # The 4-tap pass 0x40d090 scales its four weights (0x3e800000 = 0.25) by the SHARED double 4.0 at 0x6cc9d8 right before the
    # second pass. 0x6cc9d8 also feeds 0x438b60 and 0x606110, so it is not edited: a copy holding 1.0 goes to the free .data slot
    # 0x707fd0 (zero, no reference in the image) and only these four operands move. Effect: the second zoom pass keeps the reach of
    # the first instead of 4x it, so high speeds smear instead of the whole frame going soupy. Flip copy + 4 operands together.
    dict(addr=0x707fd0, old="0000000000000000", new="000000000000f03f", when=lambda: False),
    dict(addr=0x40cfb9, old="dc0dd8c96c00", new="dc0dd07f7000", when=lambda: False),
    dict(addr=0x40cfda, old="dc0dd8c96c00", new="dc0dd07f7000", when=lambda: False),
    dict(addr=0x40cfed, old="dc0dd8c96c00", new="dc0dd07f7000", when=lambda: False),
    dict(addr=0x40cffb, old="dc0dd8c96c00", new="dc0dd07f7000", when=lambda: False),
    # FEEL-C2 LAMP HALOS (feel_2026-10-31.md 3; already patched: the add colour [0x707fcc] = 1.5x the flare, and the decay is the
    # shipped one). 0x544f30 walks the lamp flare list 0x740a60 and draws each flare with weight 1.0: push 0x3f800000 at 0x544ff8
    # (into 0x5447c0) and at 0x54502e (into 0x544e90). Both go to 0.6 (0x3e99999a): the lamp's own glow and the streak buffer that
    # amplifies it both start 40 % lower, while the geometry and the trail length stay. Flip both.
    dict(addr=0x544ff8, old="680000803f", new="689a99993e", when=lambda: False),
    dict(addr=0x54502e, old="680000803f", new="689a99993e", when=lambda: False),
    # FEEL-C3 CAMERA AT SPEED (feel_2026-10-31.md 1; already patched: the projection caves 0x40debb/0x40deec/0x40dcdb make the
    # PS2 64.4 deg vertical view, 96 deg horizontal at 16:9, and Speed.exe has NO speed term for eye distance, height or pitch).
    # The only knob left inside the exe is the FOV table 0x6fbdf4 (s16 per POV, 1/65536 turn per unit): POV 0, 1 and 4 hold
    # 0x32dc = 71.5 deg. 0x2ee0 = 65.9 deg makes the car 1/tan(32.95)/1/tan(35.75) = 1.11x bigger on screen at every speed.
    # The front end reads the same table, so the garage cover car grows too: judge it in a race. Flip the three words together.
    dict(addr=0x6fbdf4, old="dc32", new="e02e", when=lambda: False),
    dict(addr=0x6fbdf6, old="dc32", new="e02e", when=lambda: False),
    dict(addr=0x6fbdfc, old="dc32", new="e02e", when=lambda: False),
    # FEEL-C4 ACCELERATION (feel_2026-10-31.md 5: the 2.7 s 0-60 is NFSU itself, shipped formulas 2.9-3.3 s with the OWNER's
    # parts; the unlock byte 0x735ec1 is ruled out). The drivetrain setup 0x474d40 picks the power/drag/grip scale from
    # car+0x404 because the gate [0x6ffe54] is 1 and has no writer. `jne 0x474d51` (7508) becomes two nops, so the scale is the
    # 1.0 at 0x6cc7bc (a shared float: untouched) for the player and every rival. Effect: whatever car+0x404 adds to engine,
    # drag and grip disappears; the probe (RN_FEELLOG, host/feellog.c) says how many seconds of 0-60 that was worth.
    dict(addr=0x474d47, old="7508", new="9090", when=lambda: False),
]

# ---- FEEL batch 1 (OWNER 2026-11-04: feel changes replace the default; one commit per change so it reverts) -------------------------
# C1 blur: the four operands always read [0x707fd0], which holds the shipped 4.0 here (the same value as 0x6cc9d8, so original mode
# blurs as in 2003); host/win32.c writes 1.0 there at boot unless RN_FEEL=0 (web/mode.js original): smear reach /4, directional.
PATCHES += [dict(p, when=lambda: True) for p in FEEL_CANDIDATES[1:5]]
PATCHES.append(dict(addr=0x707fd0, old="0000000000000000", new="0000000000001040", when=lambda: True))
# C3 camera: FOV of POV 0/1/4 71.5 -> 65.9 deg (0x2ee0, FEEL_CANDIDATES[7:10]) is written by host/win32.c at boot unless RN_FEEL=0,
# so the table keeps the shipped 0x32dc in original mode. The car reads 1.11x bigger; no speed term in the exe (docs/re/camera_speed.md).
