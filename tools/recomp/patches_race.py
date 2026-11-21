"""Patches: rivals, Free Run, traffic. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
import struct
from patches import PATCHES, _rel, _imm, _j32, _jcc32, ROAD_ADDR, EBASE_ADDR, ROAD_RB, CODE_AREA

# PATCH: 0x4b4321 (+ cave 0x6736b1, CC padding after the ret of 0x673690, no reference), OWNER 2026-10-27 (rivals with a
# soul): the race setup 0x4b4040 registers each opponent with 0x5809c0(id, 2, ride, record, skill, ?, index), esi = the
# ride slot (stdcall, ret 0x1c). That call now goes to the cave, jmp [SCREEN_ADDR+0x60] = host/rivals.c rival_ride, which
# rebuilds the ride from a procedural persona through the game's preset code (0x4b26f0, 0x57f700) and then makes the
# original call with the same arguments and esi. RN_RIVALS=0: the host makes only the original call.
PATCHES.append(dict(addr=0x4b4321, old="e89ac60c00", new="e8" + _rel(0x4b4321, 0x6736b1), when=lambda: True))
PATCHES.append(dict(addr=0x6736b1, old="cc" * 6, new="ff2560300100", entry=True, when=lambda: True))

# PATCH: 0x57119a (+ cave 0x43a7e4, CC padding after the jump table at 0x43a7d8, no reference), OWNER 2026-10-27 (rivals as
# well made as the player's car): the race list draw 0x571050 calls the car draw 0x56dc30 (stdcall, 12 arguments, ret 0x30,
# no register input). That call now goes to the cave, jmp [SCREEN_ADDR+0x64] = host/rivals.c car_draw, which forces LOD A
# for every car that is not traffic through the game's debug words 0x6f1b30 / 0x6f1b34 and makes the original call.
PATCHES.append(dict(addr=0x57119a, old="e891caffff", new="e8" + _rel(0x57119a, 0x43a7e4), when=lambda: True))
PATCHES.append(dict(addr=0x43a7e4, old="cc" * 6, new="ff2564300100", entry=True, when=lambda: True))

# PATCH: 0x4b528d (+ cave 0x6736b7, CC padding after the rivals cave, no reference), OWNER 2026-10-27 (free mode: real
# rivals on the track): Free Run's setup 0x4b5090 ends with AddTrafficCars 0x4b3ac0 (no arguments, no register input) and
# never builds opponents. That call now goes to the cave, jmp [SCREEN_ADDR+0x68] = host/free.c free_setup, which builds
# three career rivals with the game's opponent builder 0x4b4040(3, 0) and then makes the original call. RN_FREE=0: only the
# original call.
PATCHES.append(dict(addr=0x4b528d, old="e82ee8ffff", new="e8" + _rel(0x4b528d, 0x6736b7), when=lambda: True))
PATCHES.append(dict(addr=0x6736b7, old="cc" * 6, new="ff2568300100", entry=True, when=lambda: True))
# PATCH: 0x4b3c2f (+ cave 0x43a7ea, CC padding after the car_draw cave, before 0x43a7f0), same OWNER request (tuned traffic):
# AddTrafficCars 0x4b3ac0 registers each traffic ride with 0x5809c0(0x32 + i, 3, ride, "", -1, 0, 0), esi = the ride slot
# (stdcall). That call now goes to the cave, jmp [SCREEN_ADDR+0x6c] = host/free.c free_traffic, which dresses racer rows
# in a career rival's preset while free mode builds its traffic and then makes the original call.
PATCHES.append(dict(addr=0x4b3c2f, old="e88ccd0c00", new="e8" + _rel(0x4b3c2f, 0x43a7ea), when=lambda: True))
PATCHES.append(dict(addr=0x43a7ea, old="cc" * 6, new="ff256c300100", entry=True, when=lambda: True))
# PATCH: 0x422b36 (+ cave 0x673842, CC padding after a ret, no reference): race start 0x422a70 calls the traffic
# placer 0x598bf0 once per kind 3 entrant (ecx = [esi+0x2f0], push entrant); now host/free.c free_place, which runs its three
# steps (0x5991a0 route, 0x598c80 grid, 0x598fb0 last resort) in the original order and logs which one placed the car. In free
# mode it clears 100 m round the start instead of the game's 500 m ([[0x736174]+side*4+0xcc]) and repeats the last resort 4x
# (RN_FREE=0: as shipped). Why: docs/traffic_placement.md (on 1001/1010 13 of 18 fit; now 19 of 19).
PATCHES.append(dict(addr=0x422b36, old="e8b5601700", new="e8" + _rel(0x422b36, 0x673842), when=lambda: True))
PATCHES.append(dict(addr=0x673842, old="cc" * 6, new="ff257c300100", entry=True, when=lambda: True))
# PATCH: 0x598774 (+ cave 0x673848, the CC padding right after the one above): TrafficTeleporter 0x598600 asks 0x59b3e0 for the
# spacing of each Free Run move; now host/free.c free_spacing, which calls it and in free mode turns its 99999 m (no
# TRAFFIC_DENSITY zone under the player, or a stopped car near him) into the track's 31 m. Why: with 99999 every move fails
# and the car is parked (0x5832a0), so all traffic stood still after ~60 s on 1001 and the WORLD.
PATCHES.append(dict(addr=0x598774, old="e8672c0000", new="e8" + _rel(0x598774, 0x673848), when=lambda: True))
PATCHES.append(dict(addr=0x673848, old="cc" * 6, new="ff2580300100", entry=True, when=lambda: True))
# PATCH: 0x5833eb (+ cave 0x6729f6, CC padding after a ret, no reference): TrafficAI update 0x583350 reads the no-path byte
# [ebp+0x410] (mov al, 6 bytes) and, when set, only brakes the car for good: never re-pathed, never parked, so the
# TrafficTeleporter never recycles it. Now call host/free.c free_nopath (+ nop), which returns that byte, or 0 in free mode so
# the car retries 0x44cf30 and is parked (0x5832a0) on failure, as every other car. RN_FREE=0: the original byte.
PATCHES.append(dict(addr=0x5833eb, old="8a8510040000", new="e8" + _rel(0x5833eb, 0x6729f6) + "90", when=lambda: True))
PATCHES.append(dict(addr=0x6729f6, old="cc" * 6, new="ff2584300100", entry=True, when=lambda: True))
# PATCH: 0x59a5cf, 0x59a669 (+ cave 0x439a94, CC padding after a ret, no reference): the Free Run move 0x59a2c0 asks 0x4420b0
# whether traffic may spawn on a road node (bit 25/26 of [node+0x84]); 1001 sets it on 40 % of its route only, so with the
# player in the other stretches every move failed and all cars stood parked. Now host/free.c free_tnode: every node in free
# mode, the node's bit otherwise.
PATCHES.append(dict(addr=0x59a5cf, old="e8dc7aeaff", new="e8" + _rel(0x59a5cf, 0x439a94), when=lambda: True))
PATCHES.append(dict(addr=0x59a669, old="e8427aeaff", new="e8" + _rel(0x59a669, 0x439a94), when=lambda: True))
PATCHES.append(dict(addr=0x439a94, old="cc" * 6, new="ff2588300100", entry=True, when=lambda: True))
# PATCH: 0x59a4b8, 0x59a763 (cave 0x439a94 above, told by their returns 0x59a4bd, 0x59a768): the Free Run move 0x59a2c0 walks the
# road (0x4563d0) from the player until a spot is accepted, 500 m of race route or a dead end; on the strongly connected WORLD net it
# circled a block within 500 m for good (froze the game ~10 s into WORLD, OWNER 2026-10-28). Now host/free.c free_walk: in free
# mode the metres walked in one move stand for its route distance, and a walk past [0x6b5a3c] is undone; otherwise the original.
PATCHES.append(dict(addr=0x59a4b8, old="e813bfebff", new="e8" + _rel(0x59a4b8, 0x439a94), when=lambda: True))
PATCHES.append(dict(addr=0x59a763, old="e868bcebff", new="e8" + _rel(0x59a763, 0x439a94), when=lambda: True))
# PATCH: 0x5987f6 (+ cave 0x439a9a, the CC padding right after the one above): TrafficTeleporter 0x598600 asks 0x5988c0 whether a car
# needs a move; its rules are all along the race route, so in free roam a car that drove into another street was never moved and
# drove on 1..2.5 km away (17 of 19 cars on the WORLD). Now host/free.c free_recycle: the game's answer, or in free mode also yes
# when the car is farther than 500 m ([0x6b5a3c], the move's route limit) in a straight line from the player.
PATCHES.append(dict(addr=0x5987f6, old="e8c5000000", new="e8" + _rel(0x5987f6, 0x439a9a), when=lambda: True))
PATCHES.append(dict(addr=0x439a9a, old="cc" * 6, new="ff258c300100", entry=True, when=lambda: True))
# PATCH: 0x430dbd (+ cave 0x554495, CC padding after a ret, no reference): the player update 0x430730 asks 0x42e620
# (stdcall 1, edx:eax) for the HUD widget mask; now host/free.c free_hud, which calls it and in free mode clears WRONG_WAY
# (lo 0x4000) and SPLIT_TIME / LIVE_SPLIT (lo 0x80 / 0x800000, the green gap). Why: docs/openworld/re_hud_free.md.
PATCHES.append(dict(addr=0x430dbd, old="e85ed8ffff", new="e8" + _rel(0x430dbd, 0x554495), when=lambda: True))
PATCHES.append(dict(addr=0x554495, old="cc" * 6, new="ff2590300100", entry=True, when=lambda: True))


# PATCH: 0x422a78, 0x422a85, 0x422afa, 0x4345a9, OWNER 2026-10-28 (Free Run with 6 rivals, docs/openworld/re_racer_cap_probe.md 4):
# the game never has more than 4 racers, two places stop more. (a) The race start 0x422a70 asks 0x422580 for 4 start positions
# into a 4 x 0x20 byte stack buffer and builds the car of the entrant with grid 1..4: the frame 0x84 -> 0x144, `push 4` -> 10 and
# `cmp edi,4` -> 10 make room for 10 slots (the buffer still ends at the saved ebp; 0x422580 is generic in n). (b) The
# RaceManager 0x421f00 keeps 4 records of 0x13c at +0x30 and a pointer array at +0x520: 0x434590 calls 0x434a80 (esi = RM) at
# 0x4345a9, which adds a record (ctor 0x4333c0, eax = car, ecx = record; it sets car+0x1c) for every racer of the car list
# [0x7361f8] (+0x1c players, +0x20 players + opponents): a 5th record would overwrite the pointers and the laps at +0x530. The
# racer AI reads car+0x1c unguarded (0x44b1b0 at 0x44b37e: `cmp word [rec+0x10],0`; a recordless 5th racer faults on its first
# frame). The call now goes to the existing cave 0x439a94 (jmp [SCREEN_ADDR+0x88] = host/free.c free_tnode, which tells this
# call by its return address 0x4345ae): rm_records lowers [list+0x20] to 4 for the call, and gives the other racers a record of
# their own outside the RM (0x4333c0 on spare memory), so they race but are not ranked.
PATCHES.append(dict(addr=0x422a78, old="84000000", new="44010000", when=lambda: True))
PATCHES.append(dict(addr=0x422a85, old="04", new="0a", when=lambda: True))
PATCHES.append(dict(addr=0x422afa, old="04", new="0a", when=lambda: True))
PATCHES.append(dict(addr=0x4345a9, old="e8d2040000", new="e8" + _rel(0x4345a9, 0x439a94), when=lambda: True))
# PATCH: 0x422a86 (same cave): the call 0x422580(n, buf) of the start positions goes to free_tnode too (return address 0x422a8b),
# host/free.c grid_fix: the game's call, then with more than 3 rivals the slots that lie within 8 m of an earlier one move to the end
# (the WORLD's odd marker slots overlap; docs/openworld/re_racer_cap_probe.md Implemented).
PATCHES.append(dict(addr=0x422a86, old="e8f5faffff", new="e8" + _rel(0x422a86, 0x439a94), when=lambda: True))

# PATCH: 0x57d060, 0x57d0c1, (0x57cfc7 off), 0x4b3b01, 0x583a37, 0x583a5b (+ cave 0x63b270, a dead CRT routine: no call, jump or pointer
# reaches 0x63b270..0x63b3bf; source tools/recomp/caves/traffic.s), OWNER 2026-10-25 (traffic alive). AddTrafficCars
# 0x4b3ac0 spawns i8 [trackinfo + side + sel*2 + 0xc0] cars (GLOBALB 0x34201: 12 on most tracks), each of a type from
# 0x57d000: weights f32 [row + 0xc60 + district*4] of the rows the iterator 0x57cfa0 keeps (usage +0xc54 == 2, enable
# +0x40, skins +0xd9 > 0) in the table [0x734588] (GLOBALB 0x34600, 35 rows x 0xc90). District 0 (every Quick Race)
# weights only 6 of the 12 normal traffic types. Now: the 12 types weigh 1.0 in every district (BUS, AMBULANCE and
# FIRETRUCK stay 0), the iterator also lets the traffic pick take racer rows (usage 0) and 8 compact racers weigh 0.375
# (stock skin: d9 = 1, skin 1); +0xc60 has no other reader. The count is x1.5 (12 -> 18), at most 26 (rides cap 30 at
# 0x4322a0); the 100 re-picks at 0x4b3b30 keep every ride a distinct type (run: 6 -> 18 types on track 1001). The
# traffic driver 0x583910 (ctor 0x582f90, vtable 0x6b96b0; racers use 0x5a6ef0 from 0x462b30) asks 0x5a6b00 the lane speed
# (node +0x6a via 0x5a7690) twice a frame; each car now drives at x0.85..1.15 of it, from a hash of its AI object (esi), so
# a car keeps its pace (a spawn speed alone would not last). [0x1301c] (SCREEN_ADDR+28) = 0 (RN_TRAFFIC=0) = original.
PATCHES.append(dict(addr=0x63b270, entries=(0x63b280, 0x63b28a, 0x63b310, 0x63b331), old="8b44240881ec0801000085c00f8424010000538b9c24100100005556578944241053e8b91e000083c40484c00f85eb000000a1f4756e008d5424142bd08d49008a08880c024084c975f68bc38bf38bff8a084084c975f98d7c24142bc64f8bff8a4f014784c975f88bc8c1e9026a00f3a568800000006a036a006a008bc868000000808d44242c83e10350f3a4ff15c07169008bf883ffff745268fc8c6a006a07e84a7b000053e834fdffff8be883c40c85ed750f8b0d18766e0051e81f71000083c4048b3590f470006a005783c610ff15b871690001068356040057c6850401000001ff1528716900eb316a00681001000068f08c",
                    new="ffdf0f003694573e9a99593fce339a3a5089c8e80200000058c3833d1c300100007508d984b0600c0000c3528b90540c000085d274248b90600c00000b90640c00000b90680c00000b906c0c00000b90700c00007420d9e85ac38b90500c000083fa1f77110fa31570b263007308d90574b263005ac3d9ee5ac38b88540c000039f17412833d1c30010000740e85c9750a83fe027505e9c61cf4ffe9dd1cf4ff0fbe9479c0000000833d1c30010000740f8d1452d1fa83fa377e05ba37000000c3ff742404e8c6b7f6ff833d1c3001000074205089f069c0b179379ec1e81850db042458d80d7cb26300d80578b26300dec958c20400", when=lambda: True))
PATCHES.append(dict(addr=0x57d060, old="d984b0600c0000", new="e825e20b009090", when=lambda: True))
PATCHES.append(dict(addr=0x57d0c1, old="d984b1600c0000", new="e8bae10b009090", when=lambda: True))
# 0x57cfc7 (cave iter: the traffic pick also took racer rows, usage 0) is on again (2026-10-28, with the overlay below): a racer model
# has no body texture of its own. Cars/TEXTURES.BIN holds baked <MODEL>_SKIN1..8 only for traffic models (4DR_SEDAN, PICKUP, TAXI...);
# a racer body is DUMMY_SKIN<n>, whose hash 0x4b4040 puts at ride +0x444 (+0x448 DUMMY_WHEEL<n>) for slots 1..4 only, and
# AddTrafficCars 0x4b3ac0 -> 0x57d160 sets +0x444 = 0. So a GOLF or CIVIC in traffic drew wheels, seat and driver with no
# body (the OWNER's "invisible cars", PLAN 6.2). Now host/free.c free_traffic gives each racer ride DUMMY_SKIN5..12 / DUMMY_WHEEL5..12,
# render targets that exist in the overlay build/openworld/CARS_TEXTURES.BIN (tools/remaster/world_overlays.py cars, served by
# host/trackfiles.c). Without that file the racer rows stay invisible: build it first.
PATCHES.append(dict(addr=0x57cfc7, old="8b88540c00003bce751c", new="e91ee30b009090909090", when=lambda: True))
PATCHES.append(dict(addr=0x4b3b01, old="0fbe9479c0000000", new="e80a781800909090", when=lambda: True))
PATCHES.append(dict(addr=0x583a37, old="e8c4300200", new="e8f5780b00", when=lambda: True))
PATCHES.append(dict(addr=0x583a5b, old="e8a0300200", new="e8d1780b00", when=lambda: True))

# PATCH: 0x598c4b, OWNER 2026-10-27 (few cars). The traffic placer 0x598bf0 tries 0x5991a0 (along the route, only when
# 0x421a50 = [0x78a344] or [0x7361a8]), then 0x598c80 (a grid slot), then 0x598fb0 (any free spot, 100 tries, 31 m apart via
# 0x59aa60) only when 0x421a50 is false. (Measured later: in Free Run it is false, so the last resort ran anyway; see 0x422b36 above) with 18 entrants (the x1.5 above) 0x598c80 fails 793 of 795
# tries at the start and 7 never get a car (11 cars; vanilla places 10 of 12). With [0x1301c] != 0 (RN_TRAFFIC, the switch above)
# the last resort runs too: ecx = (al == 0 ? -1 : 0) | [0x1301c], then the original test ecx / je 0x598c69. eax is dead there.
PATCHES.append(dict(addr=0x598c4b, old="0fb6c0f7d81bc0400fb6c8", new="3c011bc90b0d1c30010090", when=lambda: True))

# PATCH: 0x4aa21e (+ data 0x6d3440: .rdata slack past its virtual size 0x3c439, zero, no reference), OWNER 2026-10-28:
# the audio volumes of the OWNER's profile asas are the default. The profile/options ctor 0x4aa200 (callers 0x4a9bc0,
# 0x4cadc0, 0x4ccab0: every new profile) set the 9 volume floats at +0x38..+0x58 to 0.9. The .opt file (save 0x41e200,
# load 0x41e330) is dword 0x13, the 0x2e5-byte block of 0x4aaad0 (+0x39 = those floats, so file 0x3d) and its Adler-32
# (0x41dd10). The 9 floats now come from asas.opt file 0x3d..0x60 (0.2 0.7 0.5 0.7 0.8 0.9 0.9 0.9 0.9), same bits:
#   lea edi,[esi+0x38]; push esi; mov esi,0x6d3440; mov ecx,9; rep movsd; pop esi; nop x15
# ecx ends 0 as before (0x4aa20d); edi and eax are set again right after (0x4aa23e, 0x4aa25e).
PATCHES.append(dict(addr=0x4aa21e, old="b86666663f894638" + "89463c894640894644894648" + "89464c894650894654894658",
                    new="8d7e3856be40346d00b909000000f3a55e" + "90" * 15, when=lambda: True))
PATCHES.append(dict(addr=0x6d3440, old="00" * 36, when=lambda: True,
                    new="c8cc4c3e3233333ffdffff3e3233333fcccc4c3f6666663f6666663f6666663f6666663f"))

# PATCH: 0x426dd7, 0x4662e0 (+ cave 0x5567e3, CC padding after a ret, no reference: REA xrefs), OWNER 2026-10-28 (camera breaks on
# jumps in WORLD): the jump trigger 0x426930 and the crash camera 0x465d00 both ask 0x42c4b0 (esi = camera ctrl, returns al) to build
# the JUMPVIEW spline from the player's route nodes (mode 6, mover 0x485c00: a point 2 m off the road edge, no collision after
# placement), which in the city lands inside buildings. Both calls now go to the cave, jmp [SCREEN_ADDR+0x94] = host/free.c
# free_jumpcam: the original call; in free mode it also moves the eye node to one with a clear view along the road, or answers 0 (the chase
# camera stays). docs/re/camera_jump.md.
PATCHES.append(dict(addr=0x426dd7, old="e8d4560000", new="e8" + _rel(0x426dd7, 0x5567e3), when=lambda: True))
PATCHES.append(dict(addr=0x4662e0, old="e8cb61fcff", new="e8" + _rel(0x4662e0, 0x5567e3), when=lambda: True))
PATCHES.append(dict(addr=0x5567e3, old="cc" * 6, new="ff2594300100", entry=True, when=lambda: True))

# Traffic goal-5 finder 0x453920 dropped any obstacle that is a racer (race record [car+0x1c] != 0) going > 20 m/s, which is the
# player too, so spawn-record traffic never braked, swerved or honked for him. Now only rivals (driver kind 2, [[rec+0x14]+4]) keep the
# exemption (docs/re/traffic_react.md item b): cave 0x797500 (CODE_AREA, called from 0x4539db; returns al for the test/je kept at 0x4539e3). Gated on [0x1301c] (RN_TRAFFIC,
# 0 in Original mode, web/mode.js): 0 = the shipped test [rec+0x1c] != 0 (every racer, the player too); 1 = driver kind [[rec+0x14]+4] == 2 (rivals only).
# It was ungated (the Remaster reaction leaked into Original); ecx, edx are dead after the block (docs/re/ai_review2.md (b)).
PATCHES.append(dict(addr=0x797500, old="00" * 29, new="833d1c30010000740b8b4914837904020f94c0c38b511c85d20f95c0c3", entry=True, when=lambda: True))
PATCHES.append(dict(addr=0x4539db, old="8b511c85d20f95c0", new="e8" + _rel(0x4539db, 0x797500) + "909090", when=lambda: True))
# PATCH: 0x45399f (+ cave 0x44dd21, NOP padding after a ret, no reference: asm.py free), a traffic car sees the player closing from behind. The
# finder 0x453920 asks 0x44f470 for the nearest car AHEAD in its lane (slots own-1 down to 0 of the neighbour list); nothing reads the slots
# own+1.. behind it, and the Avoid action cannot take a car behind (its vt[7] 0x453a60 ends it at once, its brake branch 0x45406c would stop the car).
# The call now goes to the cave, jmp [SCREEN_ADDR+0x98] = host/rivals.c traffic_behind: the original call first (same ecx and args, the caller
# still pops 0x14); if it found nothing and the car is traffic in a lane 11..16, the rows behind are scanned while the list is valid and a car
# that sees the player closing in takes a clear neighbour lane itself (ctx+0x394 / +0x398 as 0x453e21..0x453e4b) and honks. It returns 0 for
# every behind case. RN_TRAFYIELD=0 (original mode): the original call only. Replaces traffic_tick's host-side "yield" case.
PATCHES.append(dict(addr=0x45399f, old="e8ccbaffff", new="e8" + _rel(0x45399f, 0x44dd21), when=lambda: True))
PATCHES.append(dict(addr=0x44dd21, old="90" * 6, new="ff2598300100", entry=True, when=lambda: True))
# PATCH: 0x45553b/0x45557b/0x4555bb/0x4555f8, AI slot pools (ctor 0x455530) 26/27/27/640 -> 64/64/64/1536 (the bytes below): each AI car (racer or traffic) takes 1 goal, 1 action, 1 FuturePoints and ~24 future points, so the shipped pools cap AI cars at 26; WORLD runs 8 rivals + 21 traffic (host/free.c world_ai). Capacity only: a race with fewer cars allocates the same slots as before.
PATCHES.append(dict(addr=0x45553b, old="bf1a000000", new="bf40000000", when=lambda: True))  # AIGoalSlotPool 26 -> 64
PATCHES.append(dict(addr=0x45557b, old="bf1b000000", new="bf40000000", when=lambda: True))  # AIActionSlotPool 27 -> 64
PATCHES.append(dict(addr=0x4555bb, old="bf1b000000", new="bf40000000", when=lambda: True))  # FuturePointsSlotPool 27 -> 64
PATCHES.append(dict(addr=0x4555f8, old="bf80020000", new="bf00060000", when=lambda: True))  # FuturePointSlotPool 640 -> 1536

# PATCH: traffic cap 30 -> 64 entrants (OWNER 2026-11-04; docs/re/traffic_cap_plan.md, each site read in Speed.exe). Entrant table 30 x 0x750 ends at RaceStatus 0x78a2f0; only three sites hold its base.
ENTRANT_ADDR, CHECK_ADDR = 0x7c0000, 0x7e0000  # RAM past SizeOfImage 0x794368, below HEAP_LO: 64 x 0x750 = 0x1d400, then the 0x400 of checksum records
PATCHES.append(dict(addr=0x431e9d, old="b9d8360000" "bf90c77700", new="b900750000" "bf0000" "7c00", when=lambda: True))  # ctor memset: 64 entrants at the new base
PATCHES.append(dict(addr=0x431ec4, old="c7862801000090c77700", new="c786280100000000" "7c00", when=lambda: True))  # RaceStatus+0x128 = [0x78a418], every reader's pointer
PATCHES.append(dict(addr=0x689d22, old="bec4ce7700" "bf1e000000", new="be34077c00" "bf40000000", when=lambda: True))  # static init of each entrant's sub-object, 64 of them
PATCHES.append(dict(addr=0x4322e0, old="83bd2c0100001e", new="83bd2c01000040", when=lambda: True))  # AddEntrant cap 0x1e -> 0x40
PATCHES.append(dict(addr=0x421191, old="81c7a8000000", new="bf00007e0090", when=lambda: True))  # checksum 0x421170 wrote records at L+0xa8 over sorted[32..], so car 33 read a float as a pointer (STOP 0042119a): records go to CHECK_ADDR
PATCHES.append(dict(addr=0x4669be, old="bf1e000000", new="bf40000000", when=lambda: True))  # CarCollisionBodySlotPool 30 -> 64
# PATCH: 0x44c573 (+ cave 0x43b556, CC padding after the ret 8 of 0x43b4xx, no reference: asm.py free), OWNER order 2026-11-01 (rival personalities
# in WORLD): the racer's desired-speed step 0x44c550 calls the catch-up 0x44bd10 (eax = AIVehicle) right before it reads the speed inputs. The call
# now goes to the cave, jmp [SCREEN_ADDR+0xb0] = host/rivals.c persona_step: the original call first, then per personality (WORLD only, ?ai=0 off).
PATCHES.append(dict(addr=0x44c573, old="e898f7ffff", new="e8" + _rel(0x44c573, 0x43b556), when=lambda: True))
PATCHES.append(dict(addr=0x43b556, old="cc" * 6, new="ff25b0300100", entry=True, when=lambda: True))
# PATCH: 0x45c8c2 (+ cave 0x43db2a, CC padding after the ret of 0x43dxxx, no reference: asm.py free), OWNER order 2026-11-01 (clean WORLD rivals
# pass wide): the side-line builder 0x45c760 calls the clearance 0x45cea0 (ecx = ctx, edx = row, 2 args, st0). The call now goes to the cave,
# jmp [SCREEN_ADDR+0xb4] = host/rivals.c persona_clear: the original call, then + 1.5 m for a clean rival (WORLD only, ?ai=0 off).
PATCHES.append(dict(addr=0x45c8c2, old="e8d9050000", new="e8" + _rel(0x45c8c2, 0x43db2a), when=lambda: True))
PATCHES.append(dict(addr=0x43db2a, old="cc" * 6, new="ff25b4300100", entry=True, when=lambda: True))

