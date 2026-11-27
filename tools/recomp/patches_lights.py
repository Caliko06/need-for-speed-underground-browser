"""Patches: car lights, horn flash, neon. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES, _rel

# PATCH: 0x5693b7 (jne +3 -> jmp +3 in Car::LightsOnForDraw 0x5693b0, only caller 0x56da42 = the head flare of DrawLampFlares 0x56d8d0): a traffic
# car (driver kind 3) no longer answers "lights on" at once, it reads car+0x855 like every car, so the flash of 0x429190 can be seen.
PATCHES.append(dict(addr=0x5693b7, old="75", new="eb", when=lambda: True))
# PATCH: 0x425853 (Car::Car 0x425350, 28 bytes: the +0x854, +0x83e, +0x83f, +0x840 byte stores): the base "lights on" byte +0x854 is 1 for a traffic car
# (entrant kind [[car+0x14]+4] == 3; car+0x14 is stored at 0x425582) and 0 for the others as before, so with 0x5693b7 above its head flare stays lit.
# The kind is final when the ctor runs: the only store of an entrant's kind is 0x5809e6 (0x5809c0, called at the race setup 0x4b3c2f traffic, 0x4b4321..0x4b6681
# racers; host/free.c free_traffic and free_rival pass its arguments through), cars are built after. mov eax,[ebx+0x14]; cmp [eax+4],3; sete [ebx+0x854];
# mov [ebx+0x83e],si (esi = 0 since 0x42580a); mov byte [ebx+0x840],0 (eax is dead until 0x425896). Replaces the host +0x854 loop of traffic_tick.
PATCHES.append(dict(addr=0x425853, old="c6835408000000c6833e08000000c6833f08000000c6834008000000",
                    new="8b4314" "83780403" "0f9483540800" "00" "6689b33e080000" "c6834008000000", when=lambda: True))
# PATCH: 0x4291ec (Car::UpdateHornFlash 0x429190, `xor cl,cl; jmp 0x42920f` -> `jmp 0x429219; nop nop`): the dark half of a flash (the gap flag +0x840 set by
# 0x429100, from HonkAtPlayer 0x44c539 or the host) used to fall back to the base byte +0x854, which is 1 for traffic now, so the flash had no dark phase.
# Now it stores +0x855 = 0 there (0x429219: xor eax,eax; cl is already 0 since 0x4291b4).
PATCHES.append(dict(addr=0x4291ec, old="32c9eb1f", new="eb2b9090", when=lambda: True))
# PATCH: 0x56f21e (+ cave 0x67358a, CC padding after a ret), OWNER 2026-11-03 (more neon on tuned cars): the neon pass setup of DrawLampFlares 0x56d8d0 calls host/rivals.c neon_pass, jmp [SCREEN_ADDR+0xb8]: same eax and [esp+0x20], but with RN_POOL (?pool=1) a wider, stronger glow on the others' cars.
PATCHES.append(dict(addr=0x56f21e, old="8b45088b4c241c8b80bc040000894c2420", new="e8" + _rel(0x56f21e, 0x67358a) + "90" * 12, when=lambda: True))
PATCHES.append(dict(addr=0x67358a, old="cc" * 6, new="ff25b8300100", entry=True, when=lambda: True))
