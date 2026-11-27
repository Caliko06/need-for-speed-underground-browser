"""Patches: the widened road graph. Split from patches.py (GOAL 2026-11-05); patches.py imports this file in a fixed order."""
from patches import PATCHES, _imm, _j32, _jcc32, ROAD_ADDR, ROAD_RB

# ---- WIDEN the road graph (OWNER 2026-10-30; docs/openworld/re_widen.md): the game's own AI/traffic on a whole-city net ----
# Stage 1, PATCH 0x77af20 users: the road-section manager (0x210 B in .bss: list heads +0 +8, 128 section pointers at +0x10;
# ctor 0x442b00 from 0x689eb0, dtor 0x696331) moves to ROAD_ADDR with 256 slots (0x410 B). ROAD_ADDR 0x796000 is zeroed guest
# RAM past SizeOfImage 0x794368 and below HEAP_LO 0x800000: no host code, patch or Windows image uses it (grep host/ web/ patches.py).
# Every use is an imm32: 42 x 0x77af20 (the object: mov ecx,..; list sentinels) and 62 x 0x77af30 (the slot table; [4*r+..]);
# a scan of the whole exe (capstone and raw bytes agree) finds no other form and no pointer to them in .data/.rdata. ctor and
# unload clear / walk 0x100 slots (0x442b14 rep stosd count, 0x442bd8), PostLoad 0x4430b0 walks the table twice
# (cmp esi,0x200 at 0x443116 and cmp ebp,0x200 at 0x4431e5 -> 0x400). EBASE (stage 3) lives at ROAD_ADDR + 0x410.
# Wine A/B: real Windows maps nothing at ROAD_ADDR, so tools/wine/mkexe.py leaves out every patch with widen=True.
_ROAD_MGR_SITES = (
    0x432ea7, 0x432eac, 0x442dde, 0x442e6f, 0x44b024, 0x44b029, 0x44b037, 0x44c9d2, 0x44c9d7, 0x44c9e7, 0x456224,
    0x456229, 0x4932e6, 0x4932fb, 0x5837ff, 0x583804, 0x583817, 0x598dec, 0x598e03, 0x598ed1, 0x598f0e, 0x599257,
    0x599287, 0x599342, 0x599634, 0x599682, 0x599862, 0x599a81, 0x599ab1, 0x599b58, 0x599f7c, 0x59a68c, 0x59a7ee,
    0x59af52, 0x59b0dc, 0x59b302, 0x59b33f, 0x59ba3b, 0x59ba4c, 0x59bcd5, 0x689eb1, 0x696332
)
_ROAD_TBL_SITES = (
    0x435de7, 0x44211f, 0x4421b3, 0x4430e0, 0x443106, 0x443196, 0x44a2b8, 0x44a2db, 0x44ae7b, 0x44d58b, 0x4531dd,
    0x453243, 0x45367f, 0x453f35, 0x4542c3, 0x454302, 0x4552e6, 0x455426, 0x456549, 0x45665c, 0x456eb6, 0x57af21,
    0x583656, 0x59bd81, 0x59bdff, 0x59c599, 0x5a5456, 0x5a546f, 0x5a5525, 0x5a562e, 0x5a564d, 0x5a5922, 0x5a595c,
    0x5a61b0, 0x5a6212, 0x5a6272, 0x5a6614, 0x5a6688, 0x5a6c22, 0x5a6c6d, 0x5a6d4f, 0x5a6dcf, 0x5a6df0, 0x5a7299,
    0x5a735b, 0x5a73bf, 0x5a7478, 0x5a7581, 0x5a7612, 0x5a76ac, 0x5a78da, 0x5a798a, 0x5a7a3a, 0x5a7aea, 0x5aab4c,
    0x5aab7b, 0x5aadcd, 0x5ab169, 0x5ab1ba, 0x5ab232, 0x5ab25d, 0x5ab27e
)
for _a in _ROAD_MGR_SITES:
    PATCHES.append(dict(addr=_a, old=_imm(0x77af20), new=_imm(ROAD_ADDR), when=lambda: True, widen=True))
for _a in _ROAD_TBL_SITES:
    PATCHES.append(dict(addr=_a, old=_imm(0x77af30), new=_imm(ROAD_ADDR + 0x10), when=lambda: True, widen=True))
for _a, _o, _n in ((0x442b14, 0x80, 0x100), (0x442bd8, 0x80, 0x100), (0x443118, 0x200, 0x400), (0x4431e7, 0x200, 0x400)):
    PATCHES.append(dict(addr=_a, old=_imm(_o), new=_imm(_n), when=lambda: True, widen=True))

# Stage 2, section ids up to 254. A section id is a BYTE in NodeRef +0x5c, node +0x83, entry +9/+0xa and the [+4]/[+5] pairs of a
# road link; 0xff means none. The game reads +0x5c and the pairs as signed bytes (movsx), so ids 128..254 would turn negative and
# read as none. 50 sites become movzx (0f be -> 0f b6, same length; the 41 of re_widen.md plus 9 found by scanning every movsx
# byte read of a road function: 0x45466c 0x4546d4 0x454744 (trigger record pairs), 0x5aab25 0x5aab6f 0x5aada0 0x5aadc1 0x5aae05
# (link pairs) and 0x5a5f23 (NodeRef +0x5c against the section header id, 16 bit)). Each is followed by 'test r,r; jl' (none) or a
# compare with another read of the same id; 255 now indexes slot 255 of the table, which no section may use (always 0 = none).
_ROAD_MOVZX = (
    0x44a2af, 0x44a2d2, 0x44d582, 0x4531d4, 0x45323a, 0x453674, 0x453f2c, 0x4542ba, 0x45464b, 0x45466d, 0x4546b1,
    0x4546d5, 0x454735, 0x454745, 0x57af18, 0x583d58, 0x5a52cd, 0x5a5625, 0x5a5639, 0x5a5674, 0x5a5919, 0x5a5953,
    0x5a5f25, 0x5a61a7, 0x5a6209, 0x5a6269, 0x5a6538, 0x5a660b, 0x5a667f, 0x5a6c19, 0x5a6c64, 0x5a6d46, 0x5a6de7,
    0x5a6e4c, 0x5a7290, 0x5a7352, 0x5a73b6, 0x5a746f, 0x5a7578, 0x5a7609, 0x5a76a3, 0x5a78d1, 0x5a7981, 0x5a7a31,
    0x5a7ae1, 0x5aab26, 0x5aab70, 0x5aada2, 0x5aadc2, 0x5aae06
)
for _a in _ROAD_MOVZX:
    PATCHES.append(dict(addr=_a, old="be", new="b6", when=lambda: True, widen=True))
# Caps that were constants (re_widen.md section 1): the road id bound RB at ROAD_RB (retail 100, the game's own value; after every
# PostLoad it is 1 + the highest list-0 section id, at least 100, so retail loops and ranges are the same and a wider net gets its
# ids scanned). Code lives in CODE_AREA (zero RAM past the image: lift.py lifts it like .text), source caves/road.s, regenerate
# with caves/road_asm.py. H: PostLoad 0x4430b0 at 0x443123 (was mov eax,[0x736154]) computes RB, then the original and on (jmp 0x443128).
# C1 0x59b2f8 PickRandomSection, C2 0x599b4a FindNodeAtRoute (bound RB-1), C3 0x59af45 teleporter table: the loop head
# 'cmp i,100; jae; mov eax,..' becomes call + the same jae. R1 0x4627ee racer range hi (RB-1), R2 0x5836ed traffic roads hi (RB-1),
# S 0x5836d5 traffic stub range (100..119 when RB is 100, else 255..255). 0x435e79 'cmp eax,0x77; jg' (section header id sanity,
# 0..119) is 'cmp al,0xfe; nop; ja'. 0x41f8a2: the teleporter's heap block holds 0x10 + 4 * 256 bytes (was 100 sections).
_ROAD_CODE = "b96300000031d28b04951060790085c0740c83780c00750639ca7e0289d14281fa0001000072e041890d1068790031c9c7048d10647900000000004181f90001000072eca1546173003dff0000007705e9d3c0caff89c18b355061730085c974144989cac1e2050fb654160a890c9510647900ebe8e90cc2caffcccccccccccc8b45f43b0510687900c3cccccccccccccccccccccccccccccccccccccccccccc518b0d10687900498b45f439c859c3cccccccccccccccccccccccccccccccccc8b45fc3b05106879008b450cc3cccccccccccccccccccccccccccccccccccccca110687900488902c3cccccccccccccccccccccccccccccccccccccccccccccc50a11068790048890158c3cccccccccccccccccccccccccccccccccccccccccc833d1068790064740dc700ff000000c701ff000000c3c70064000000c70177000000c3cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc0fb6ac178100000081fdff00000074190fb68783000000032c8510647900c1e505a15061730001c5c331edc3cccccccccccccccccccccccccccccccccccccccc0fb6b4298100000081feff00000074190fb6818300000003348510647900c1e605a15061730001c6c331f6c3cccccccccccccccccccccccccccccccccccccccc0fb68429810000003dff000000741a0fb6bd830000000304bd10647900c1e0058b3d5061730001f8c331c0c3cccccccccccccccccccccccccccccccccccccccc0fb68c2e8100000039c1741a0fb69583000000030c9510647900c1e1058b155061730001d1c331c9c3ccccccccccccccccccccccccccccccccccccccccccccccff05f0777900e9281accff"
PATCHES.append(dict(addr=0x797000, old="00" * (len(_ROAD_CODE) // 2), new=_ROAD_CODE, when=lambda: True, widen=True,
                    entries=(0x797000, 0x797080, 0x7970a0, 0x7970c0, 0x7970e0, 0x797100, 0x797120, 0x797180, 0x7971c0, 0x797200, 0x797240, 0x797280)))
PATCHES.append(dict(addr=ROAD_RB, old="00000000", new=_imm(100), when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x443123, old="a154617300", new=_j32(0x443123, 0x797000), when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x59b2f8, old="837df4647369" "8b45f4", new=_j32(0x59b2f8, 0x797080, "e8") + "7368" + "9090", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x599b4a, old="837df4630f8dda000000" "8b45f4", new=_j32(0x599b4a, 0x7970a0, "e8") + _jcc32(0x599b4f, 0x599c2e) + "9090",
                    when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x59af45, old="837dfc64734d" "8b450c", new=_j32(0x59af45, 0x7970c0, "e8") + "734c" + "9090", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x4627ee, old="c70263000000", new=_j32(0x4627ee, 0x7970e0, "e8") + "90", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x5836d5, old="c70064000000c70177000000", new=_j32(0x5836d5, 0x797120, "e8") + "90" * 7, when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x5836ed, old="c70163000000", new=_j32(0x5836ed, 0x797100, "e8") + "90", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x435e79, old="83f8777f25", new="3cfe907725", when=lambda: True, widen=True))
# 0x456ca8: the same 0..119 cap in the NodeRef check 0x456c90 ('movsx edx,[sec+0xa]; test; jl; cmp edx,0x77; jg' -> false), called by the traffic
# placement 0x598fb0 (0x599012), the Free Run move 0x59a2c0 (0x59a333) and host/rivals.c traffic_refill: a node in section 120..254 was refused,
# so no car was placed or moved there (WORLD + UG2 net, 254 sections, deep-city spawn: REFILLWHY 'early' 1,041 of 1,041). 'cmp dl,0xfe; ja', same length.
PATCHES.append(dict(addr=0x456ca8, old="83fa777f26", new="80fafe7726", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x41f8a2, old=_imm(0x1a0), new=_imm(0x410), when=lambda: True, widen=True))

# Stage 3, more than 255 entries (11 bits = 2047). PostLoad hook (caves/road.s H): EBASE (0x796410, u32 per section, cleared at every load)
# and, above 255 entries, EBASE[section] = first entry of the section and no sort/remap. The 4 readers of a node's slot byte (0x4564bd walker,
# 0x5a53f8 path step, 0x5a56ce, 0x5a6da9) take EBASE[node section] + byte (caves E1..E4; retail EBASE = 0). The decider cache
# (0x458bd0 writes, 0x458cc0 reads) stores the entry index in bits 2..9 of a dword: widened to bits 2..12 (masks 0xff -> 0x7ff, keep mask
# 0xfffffc01 -> 0xffffe001, movzx esi,al -> mov esi,eax). ctx+0x478 (last type-2 entry, 0x4629e0 / 0x462a00) is an int that was cut to a byte.
PATCHES.append(dict(addr=0x4564bd, old="0fb6ac178100000081fdff000000740ca150617300c1e50503e8eb0233ed",
                    new=_j32(0x4564bd, 0x797180, "e8") + "90" * 25, when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x5a53f8, old="0fb6b4298100000081feff000000740ca150617300c1e60503f0eb0233f6",
                    new=_j32(0x5a53f8, 0x7971c0, "e8") + "90" * 25, when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x5a56ce, old="0fb68429810000003dff000000740d8b3d50617300c1e00503c7eb0233c0",
                    new=_j32(0x5a56ce, 0x797200, "e8") + "90" * 25, when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x5a6da9, old="0fb68c2e810000003bc8740d8b1550617300c1e10503caeb0233c9",
                    new=_j32(0x5a6da9, 0x797240, "e8") + "90" * 22, when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x458be8, old="0fb6f0", new="89c690", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x458c29, old="25ff000000", new="25ff070000", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x458cf0, old="25ff000000", new="25ff070000", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x458c95, old="81e6ff000000", new="81e6ff070000", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x458c9d, old="81e201fcffff", new="81e201e0ffff", when=lambda: True, widen=True))
# FIX (crash family 0x5838c3 / 0x44c56e, docs/re/roadid.md, census/names_crash.tsv): the decider cache of 0x458bd0 (8 dwords at [AIVehicle]+0xc, bit 0 = in
# use) is searched for a free slot with ebp = -1 as the answer when none is free (0x458c57, 'or ebp,-1'); the loop exit jumps to 0x458c86 ('mov eax,[edi];
# mov ecx,edi; call [eax+0x40]' = a GetDirection call whose result is dropped) and falls into the store at 0x458caf, 'mov [edi+ebp*4+0xc], esi' = [edi+8],
# the driver pointer of the AIVehicle (v+8: [v+8]+0x3c is called at 0x5838c3 and 0x44c56e). Retail has the same code; the answer is only a memo, so a full
# cache now just skips the store (cave F 0x797280: counts at [0x7977f0], then jmp 0x458cb3, the epilogue the type-9 exit at 0x458c55 uses): the nearest decisions, cached first, stay. Retail never
# filled the cache (a road entry every ~22 nodes); the city net has one every ~3.
PATCHES.append(dict(addr=0x458c86, old="8b078bcfff5040", new=_j32(0x458c86, 0x797280, "e9") + "9090", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x4629f3, old="0fb6c0", new="909090", when=lambda: True, widen=True))
PATCHES.append(dict(addr=0x462a38, old="0fb6c8", new="89c190", when=lambda: True, widen=True))
