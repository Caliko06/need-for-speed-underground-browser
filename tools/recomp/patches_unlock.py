"""Patches: everything open (RN_UNLOCK). Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES, _rel

# PATCH: 0x735ec1, OWNER 2026-10-20 (everything available): a debug byte in .bss that no retail code writes (REA/Ghidra
# xrefs: 61 reads, 0 writes). When it is set, the game itself reports every part, paint, vinyl, rim and performance
# upgrade unlocked and owned (0x507e10, 0x509d70, 0x50aa90, 0x5a1550, 0x5a3570), every Quick Race track won
# (0x5a16f0 -> 0x4b9f40) and money as 1000000000 (0x5a1520). Mode flags of a track (0x4ab470) still apply.
PATCHES.append(dict(addr=0x735ec1, old="00", new="01", when=lambda: True))

# PATCH: unlock everything (AGENTS Scope), with a switch for the normal Underground (OWNER 2026-10-27). [0x7677ac] is the
# game's "career beaten" flag: 0x5a0dc0 sets it to 1 when the last event (0x71) is won, new profile 0x41cf40 clears it
# (Hopper beatgame.txt). Its 22 readers are lock queries that answer "open" when it is not 0 (0x4d7eb0: "if [0x7677ac]==0
# && [0x735ec1]==0 && ... return locked"), for tracks, cars and parts (0x506210..0x512dd8 next to the garage screen
# 0x505fb0); each one tests the register right after the read (test r,r / setne / jne), so flags from an OR are fine.
# Each read now calls a cave that returns [0x7677ac] | [0x13024] in the same register (call rel32, + nop for the 6-byte
# forms). The layer writes SCREEN_ADDR+0x24 = 1 (everything open, the default) or 0 with RN_UNLOCK=0: the game's own flag,
# as shipped. Caves: 0x63b370.. in the dead CRT routine past the traffic caves (0x63b366..0x63b3bf, no reference).
_UNLOCK_CAVE = {"a1": 0x63b370, "8b3d": 0x63b380, "8b0d": 0x63b390, "8b15": 0x63b3a0}   # eax, edi, ecx, edx
PATCHES.append(dict(addr=0x63b370, entries=tuple(_UNLOCK_CAVE.values()), when=lambda: True,
                    old="680c0100008d56045352e8313e0000566800f47000e8766a000083c4208b44241081c30c01000048894424100f85effeffff5f5e5d5b6854f47000c605",
                    new=("a1ac7776000b0524300100c3" + "cc" * 4 + "8b3dac7776000b3d24300100c3" + "cc" * 3
                         + "8b0dac7776000b0d24300100c3" + "cc" * 3 + "8b15ac7776000b1524300100c3")))
for a, old in [(0x4d7eb9, "8b3d"), (0x4d8077, "a1"), (0x4d8117, "a1"), (0x4d81c7, "8b0d"), (0x4d82b4, "8b0d"),
               (0x4d8334, "8b0d"), (0x4d83b3, "a1"), (0x5062d7, "8b15"), (0x5077f9, "8b15"), (0x507cff, "a1"),
               (0x507e54, "a1"), (0x50823f, "a1"), (0x509d88, "a1"), (0x50a708, "8b0d"), (0x50aac3, "a1"),
               (0x50ab04, "8b0d"), (0x50c1d7, "a1"), (0x50d1f3, "a1"), (0x50d6a4, "8b0d"), (0x50df69, "8b0d"),
               (0x512223, "a1"), (0x512dd8, "8b0d")]:
    new = "e8" + _rel(a, _UNLOCK_CAVE[old]) + ("" if old == "a1" else "90")
    PATCHES.append(dict(addr=a, old=old + "ac777600", new=new, when=lambda: True))

# PATCH: unlock gaps (row 9, 2026-11-11). Both tests read only the debug byte [0x735ec1] (the one the 48 retail checks use), so the
# patches follow it wherever it is set: with 0 every site runs the shipped instruction. Caves in CODE_AREA 0x797700.., one flag test each.
# Sponsor / preset car rows: 0x4bc34f (Quick Race car list 0x4bc170) and 0x4e0fa0 (multiplayer car select 0x4e0d90) read the style-reward
# byte [0x758ad8 + row] with no cheat test; the cave ORs the debug byte into cl (the code only tests cl, then jne -> car is listed).
_FLAG = "803dc15e730000"   # cmp byte [0x735ec1], 0
_STYLE_ROW = "8a88d88a7500"   # mov cl, [eax+0x758ad8]
PATCHES.append(dict(addr=0x797700, old="00" * 13, new=_STYLE_ROW + "0a0dc15e7300" + "c3", entry=True, when=lambda: True))
for a in (0x4bc34f, 0x4e0fa0):
    PATCHES.append(dict(addr=a, old=_STYLE_ROW, new="e8" + _rel(a, 0x797700) + "90", when=lambda: True))
# Spending: every purchase does cash -= price, spent += price (0x76026c, 0x760274, saved by Autosave 0x4c96f0). The price register is zeroed
# when the byte is set, so cash and spent stay as they are and nothing negative reaches the profile.
# 0x5a2555 (car purchase 0x5a2540): mov eax,[eax+0xc7c] (price in the car row) -> cave 0x797710, then the shipped sub/add see 0.
PATCHES.append(dict(addr=0x797710, old="00" * 18, new="8b807c0c0000" + _FLAG + "7402" "31c0" "c3", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x5a2555, old="8b807c0c0000", new="e8" + _rel(0x5a2555, 0x797710) + "90", when=lambda: True))
# 0x5a25d6 (performance upgrade 0x5a25a0): sub [edx+0x1374],ecx -> cave 0x797730 zeroes ecx first; the following add edi,ecx adds 0.
PATCHES.append(dict(addr=0x797730, old="00" * 18, new=_FLAG + "7402" "31c9" "298a74130000" "c3", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x5a25d6, old="298a74130000", new="e8" + _rel(0x5a25d6, 0x797730) + "90", when=lambda: True))
# 0x5a265b (part purchase 0x5a2620): sub [edx+0x1374],eax -> cave 0x797750 zeroes eax first; the following add [edx+0x137c],eax adds 0.
PATCHES.append(dict(addr=0x797750, old="00" * 18, new=_FLAG + "7402" "31c0" "298274130000" "c3", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x5a265b, old="298274130000", new="e8" + _rel(0x5a265b, 0x797750) + "90", when=lambda: True))
# 0x4c37cd (trade-in 0x4c3730): call _ftol_nocw 0x674898 (price difference in eax) -> cave 0x797770 calls it and zeroes eax; sub/add at 0x4c37de/e0 see 0.
PATCHES.append(dict(addr=0x797770, old="00" * 17, new="e8" + _rel(0x797770, 0x674898) + _FLAG + "7402" "31c0" "c3", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x4c37cd, old="e8c6101b00", new="e8" + _rel(0x4c37cd, 0x797770), when=lambda: True))
