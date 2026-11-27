"""Patches: test-only seed and autopilot. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES

# PATCH: 0x4470f0 (+ cave 0x408814), TEST-ONLY seed for the A/B against the original (off unless RN_SEED is set): 0x4470d0,
# called once from the boot 0x4471b0, seeds the game RNG [0x6f227c] from (QPC >> [0x7349c8]) + 0x12345678. The step is
# inlined at ~60 sites (e.g. 0x41f81d). Cave (the jump table 0x408814 that PATCH 0x40877e left unused, no other reference):
# mov edi,[0x13010]; test edi,edi; jnz 0x447110 (edi = K, then + 0x12345678 as before); else the original lea/push and
# back to the QPC call. The layer writes RN_SEED to SCREEN_ADDR+0x10 (0 = the original clock seed). The Wine exe gets
# `mov edi,K; jmp 0x447110` at 0x4470f0 instead (tools/wine/mkexe.py --set parity).
PATCHES.append(dict(addr=0x408814, old="95874000ae874000c7874000e0874000f987400090909090",
                    new="8b3d1030010085ff0f85eee803008d44240450e9c9e80300", when=lambda: True))
PATCHES.append(dict(addr=0x4470f0, old="8d44240450", new="e91f17fcff", when=lambda: True))

# PATCH: 0x42d4b0, TEST-ONLY autopilot for the A/B and the lap runs (off unless RN_AUTOPILOT is set): Player::UpdateInputMode
# 0x42d470 picks the racing input mode as (Player+0x4ae != 0) ? 4 (PLAYER_MODE_AUTO_PILOT, name table 0x700b00) : 2
# (CAR_RACING); SetInputMode 0x42d520 then runs AutoPilotOn 0x42e230 (the car drives itself with the game's AI) and camera
# 0x12. Only joy event 0xa3 (0x431960) toggles +0x4ae and no code registers 0xa3 (FUN_00574020), so the byte is always 0
# in play. It now reads SCREEN_ADDR+0x14 (the layer writes RN_AUTOPILOT there). Wine: mkexe.py --autopilot (mov dl,1).
PATCHES.append(dict(addr=0x42d4b0, old="8a90ae040000", new="8a1514300100", when=lambda: True))
# PATCH: 0x42d4a9 (+ cave 0x6436e3, CC padding before 0x6436f0), TEST-ONLY autopilot in Drag: in 0x42d470 race state 3
# (case 0x42d49f) takes Player+0x4af != 0 (a drag race) as mode 3 PLAYER_MODE_DRAG_RACING (names 0x700af0: 0 NONE,
# 1 PAUSEMENU, 2 CAR_RACING, 3 DRAG_RACING, 4 AUTO_PILOT) before the autopilot read at 0x42d4b0, so the drag car never
# drove itself (runs 2026-10-24: drag 6/4, no finish). `mov ecx,3; jmp 0x42d4c1` now goes through the cave:
# mov ecx,[0x13018]; jmp 0x42d4c1. The layer writes SCREEN_ADDR+0x18 = 4 with RN_AUTOPILOT, else 3 (the original).
PATCHES.append(dict(addr=0x42d4a9, old="b903000000eb11", new="e9356221009090", when=lambda: True))
# PATCH: 0x42d87e, TEST-ONLY autopilot keeps the chase camera: SetInputMode 0x42d520 asks the factory 0x42c6d0 for camera 0x12 in
# PLAYER_MODE_AUTO_PILOT (update 0x48c220, a view that swings around the car); now 0x11, the mover the OWNER drives with (0x42c670), so
# autopilot shots show what the OWNER sees, and the FOV path through 0x48bcb0 runs (with 0x12 camera+0xc4 stayed at 0x32dc, 2026-10-30).
PATCHES.append(dict(addr=0x42d87e, old="6a12", new="6a11", when=lambda: True))
