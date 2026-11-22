"""Patches: engine audio. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
import struct
from patches import PATCHES, _rel, _imm, _j32, _jcc32, ROAD_ADDR, EBASE_ADDR, ROAD_RB, CODE_AREA

# PATCH: 0x52536a (+ cave 0x5256e8, 8 CC bytes of padding after the ret of the EAXTunerCar helpers, no reference), OWNER 2026-11-04
# (lane 3, horns): the honk branch of EAXTrafficCar::Update 0x5251e0 calls StartHorn 0x524f30 here, the only such call in the image
# (edi = the sound object car+0x878, [esp+4] = sample index, callee ret 4). The sound path tests no parked byte, no draw flag and no
# world visibility, so cars the world does not draw still honk. The call now goes to the cave, jmp [SCREEN_ADDR+0xa4] =
# host/horn.c horn_start: HORNL line per honk (RN_HORNLOG=1) and, with RN_HORNFIX=1, no StartHorn for a parked, undrawn or
# just-recycled (<3 s) car. Both flags off: the original call with the same argument.
PATCHES.append(dict(addr=0x52536a, old="e8c1fbffff", new="e8" + _rel(0x52536a, 0x5256e8), when=lambda: True))
PATCHES.append(dict(addr=0x5256e8, old="cc" * 6, new="ff25a4300100", entry=True, when=lambda: True))

# PATCH: 0x537a60 EAXS_StreamManager::CreateStream type 0 = music. Skip before its 0x620 object and
# 0x6400 stream buffers are allocated; speech/ambience types 1..9 retain the original path. REA/Hopper
# + Ghidra 0x537a60; objdump 0x537a60..0x537c9e (ret 0x10). Update/pause/destruction check null slots
# (0x5384e0, 0x537cc0, 0x5379c0), and music preview 0x51c720 also checks null. host/files.c owns
# RN_NOMUSIC; host/trackfiles.c writes the byte at SCREEN_ADDR+0xe4 before the first bank load.
PATCHES.append(dict(addr=0x7976b0, old="00" * 30,
    new="803de430010000740a837c2404007503c2100064a100000000e99803daff", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x537a60, old="64a100000000",
    new="e9" + _rel(0x537a60, 0x7976b0) + "90", when=lambda: True))
