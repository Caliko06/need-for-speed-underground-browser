"""Patches: collision pools. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES, _rel

# PATCH: 0x4412be, OWNER 2026-10-30 (WORLD stops at 85 s of Free Run: int3 0x441b82 in TrackPolyBody::ReleaseUnused 0x441b20). The track polygon
# collision body pool 0x4412b0 (0x566dc0, 0x80 B slots, flags 0xb & ~3: it never grows) holds 0x400 bodies; each car's ground cache pins up to 160
# (0x4407b0 passes 0xa0) and 0x441b20 frees only bodies of count 0, so 1 + 6 rivals + 19 traffic (26 x 160) outrun it; shipped 1001 already peaks at
# 1,024 in use (RN_AILOG TRAFLOG polymax). mov edi,0x400 -> 0x2000. The cap is read back from the pool ([+0x2c] at 0x441baa, [+0x24] at 0x43fe84);
# the slot index is a s16 at row +6 (0x4400c1), so it must stay <= 0x7fff; save 0x46a6e0 writes row indices. 0x4000 = 2 MB: 64 entrants x 160 + camera (2026-11-04).
# docs/openworld/re_coll_pool.md, census/names_collision.tsv.
PATCHES.append(dict(addr=0x4412bd, old="bf00040000", new="bf00400000", when=lambda: True))
# PATCH: 0x4669fe, OWNER 2026-10-31 (WORLD: the car passes walls, and after the reset it passes them always). Each car's DynamicCollisionBody builds up to
# 0x30 wall/ground bodies a step (0x469810) from TrackPolygonCollisionBodySlotPool [0x72cbf4] (0x466970, 0x270 B slots, 0xa0 of them); when used == cap
# (0x469810: [+0x18] == [+0x2c]) it returns with none, so that car has no walls. The OWNER's WORLD session 18-25 logs the pool at 160/160 for the whole
# drive (WALLCAP). 26 cars x 48 outrun 160. mov edi,0xa0 -> 0x800; the cap is only read back from the pool header. Cost 1.3 MB instead of 100 KB.
PATCHES.append(dict(addr=0x4669fe, old="bfa0000000", new="bf00080000", when=lambda: True))
# PATCH: 0x466b01 + 9 more, collision body ids. 0xde (222) = the sum of the shipped pools (0x20 world objects, 0x1e cars, 0xa0 polygons); the id allocator [0x736070], the id table [0x736050] (malloc 0x378) and the
# witness bitmap [0x72cbfc] (a * 0xde + b, malloc 0x1810) are sized for it and nothing checks: with PATCH 0x4669fe (2048 polygons) a live id >= 222 writes past all three and aliases bits, so "witness exists" is false-true and that wall is skipped.
# Id space 0x840 = 0x20 + 0x1e + 0x800. Costs 557 KB of bitmap. The first one rewrites the same 22 bytes: push 0x10c; xor eax,eax; mov [esi+4],eax; mov [esi+8],eax; mov [esi],0x840; nops. The call at 0x466b17 stays.
PATCHES.append(dict(addr=0x466b01, old="6a1b" "c7460400000000" "c7460800000000" "c706de000000", new="680c010000" "33c0" "894604" "894608" "c70640080000" "909090", when=lambda: True))
PATCHES.append(dict(addr=0x466b26, old="b906000000", new="b942000000", when=lambda: True))  # clears the allocator bitmap: 0x42 dwords + the stosw + stosb (0x10b B)
PATCHES.append(dict(addr=0x466b3b, old="6878030000", new="6800210000", when=lambda: True))  # id table: 0x840 x 4 B
PATCHES.append(dict(addr=0x466b55, old="b9de000000", new="b940080000", when=lambda: True))  # its clear loop
PATCHES.append(dict(addr=0x466b66, old="6810180000", new="6800820800", when=lambda: True))  # witness bitmap: 0x840 x 0x840 bits
PATCHES.append(dict(addr=0x466be1, old="b904060000", new="b980200200", when=lambda: True))  # its clear loop
for a in (0x466d7b, 0x466daa, 0x466e95, 0x466ece, 0x468317, 0x4696e1):  # imul r,r,0xde: witness ctor, dtor, DoesWitnessExist, WorldObjects::Broadphase (all six sites of the stride)
    PATCHES.append(dict(addr=a, old="de000000", new="40080000", when=lambda: True))
# PATCH: 0x466a3e, witness pool [0x72cc00] 0x100 -> 0x800 (0x280 B slots, 1.3 MB): 0x469770 and Broadphase 0x4695xx skip the witness when the pool is empty, so that wall is not tested and its polygon body, which frees only with its last witness (0x466e20), leaks. The bound follows PATCH 0x4669fe.
PATCHES.append(dict(addr=0x466a3e, old="bf00010000", new="bf00080000", when=lambda: True))
# PATCH: 0x4416c4 + 6 more, collision index entries u16 -> u32 (docs: census/ug2/coll_load.md; UG2 city + NFSU1 = 180k rows, the u16 widx stops at 65,534). The only reader of the widx entries is
# CollectPolys 0x441660 (5 loads; 0x441c10 and 0x4407b0 hold row POINTERS): lea ebx,[ebx+2*esi+4] -> [ebx+4*esi+8]; the four unrolled loads (word [ebx-4],[ebx-2],[ebx],[ebx+2]) -> dword [ebx-8],[ebx-4],[ebx],[ebx+4]
# (nop-padded to the same length); step add ebx,8 -> 0x10; the tail load word [ebx+2*esi] -> dword [ebx+4*esi]. The loader below keeps the 16 shipped u16 files working. widen: Wine runs the shipped u16 reader.
PATCHES.append(dict(addr=0x4416c4, old="8d5c7304", new="8d5cb308", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x4416c8, old="0fb74bfc", new="8b4bf890", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x44179d, old="0fb74bfe", new="8b4bfc90", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x441868, old="0fb70b", new="8b0b90", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x441932, old="0fb74b02", new="8b4b0490", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x441a09, old="83c308", new="83c310", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x441a30, old="0fb70c73", new="8b0cb390", when=lambda: True, widen=True))
# PATCH: 0x441423 (+ cave 0x797620 in CODE_AREA), the 0x34133 branch of the collision loader 0x441380 (lea edx,[ecx+8]; mov [eax+0x18],edx; mov ecx,[ecx+4]; shr ecx; mov [eax+0x1c],ecx): the host (host/openworld.c world_widx) sets mgr+0x18
# to u32 entries: a chunk that starts with 0xffffffff is already u32 (the merged UG2 + NFSU1 file), any other is the shipped u16 and is widened into a guest copy. push ecx (chunk); push eax (mgr); call cave; add esp,8; 4 nops.
PATCHES.append(dict(addr=0x441423, old="8d5108895018" "8b4904d1e989481c", new="51" "50" + "e8" + _rel(0x441425, 0x797620) + "83c408" "90909090", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x797620, old="00" * 6, new="ff25cc300100", entry=True, when=lambda: True, widen=True))
