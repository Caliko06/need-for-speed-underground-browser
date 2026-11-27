"""Patches: steering input. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES

# PATCH: 0x4609e3/0x460a80/0x460b4f/0x460c02, OWNER choice 2026-10-26 (?steer=pad, "the car responds late, I can't hold the angle"):
# the steering model 0x460a80 reads [0x736514], 0 = keyboard (0x4070a0 clears it on the steer actions 3/4), 1 = gamepad
# (0x40664a, with a joystick axis; the layer has no joystick, so it is always 0 here). With 0 the angle cap grows with the
# time the key is held (S+0x14, 0.55 s to full) and 0x460de0 (called by 0x460970 on the same byte, 0x4609e3) limits the rate; with 1
# the angle is the speed cap at once. The four reads take SCREEN_ADDR+0x20 instead: the layer writes 1 with RN_STEER=pad,
# else 0 (the keyboard model, as before).
PATCHES.append(dict(addr=0x4609e3, old="a014657300", new="a020300100", when=lambda: True))
PATCHES.append(dict(addr=0x460a80, old="a014657300", new="a020300100", when=lambda: True))
PATCHES.append(dict(addr=0x460b4f, old="8a1d14657300", new="8a1d20300100", when=lambda: True))
PATCHES.append(dict(addr=0x460c02, old="8a1d14657300", new="8a1d20300100", when=lambda: True))
PATCHES.append(dict(addr=0x6436e3, old="cc" * 11, new="8b0d18300100e9d39ddeff", when=lambda: True))
