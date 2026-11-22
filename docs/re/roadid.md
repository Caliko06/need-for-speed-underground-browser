# Road section IDs
Scope: retail `pc/Speed.exe`, existing road patches, UG2 source graph; no patch, build, game run or git write.
Status: PARTIAL inventory, not proof of every carrier. `census/names_roadid.tsv` has 392 rows, including 358 distinct PC/cave/data addresses; exact final patch count is UNKNOWN.
Evidence: PC Capstone + Ghidra/Hopper exports; GC ELF symbols + PPC accessors. Existing function names are retained; field labels below describe behavior, not recovered member spellings.
Prior art: the WORLD road-widening note `re_widen` (not published), [`tools/openworld/citygraph.py:217-234`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/tools/openworld/citygraph.py#L217-L234), [`census/ug2/roads.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/census/ug2/roads.md); no externally proven NFSU1 widening implementation was located.

| Carrier / path | Proven layout and exact PC sites | Width consequence |
|---|---|---|
| TrackRoute / manager | Header section s16 +0xa, nodes s16 +0x10; parse 0x442b80/0x442b84/0x442bb2 | Header already accommodates >255; table capacity must grow |
| FuturePoint (NodeRef in earlier notes) | Section byte +0x5c, node s16 +0x5e; 0x44a2a0/0x44a2ae, init 0x455006, write 0x5a556a | All byte reads/extensions/sentinels change; +0x5d padding reuse remains UNKNOWN |
| TrackRoutePoint (road node) | Byte section +0x83; 0x424f50/0x442d77/0x44d3e4; size 0x88, first node route+0x27c | u16 at +0x83 overlaps packed flags +0x84; stride/tail users must move under direct expansion |
| Signpost (road entry) | +9 destination/new section, +0xa source/old section; 0x442110/0x4421a8; size 0x20 | Adjacent section bytes and type +0xb require layout/stride changes |
| TrafficIntersection | Section bytes +4/+5; nodes s16 +8/+0xa; size 0x170; 0x45466c/0x5aab25/0x5aada0 | Widened pair overlaps car IDs +6/+7; relocate later fields and stride users |
| DriveTarget | section[20] bytes +0x150, nodes u16[20] +0x164, direction bytes +0x18c; size 0x1c0; writer 0x459617 | Section array needs 20 extra bytes; subsequent arrays, owners and stack frames need relocation |
| Snapshots | FuturePoint 0x5a710d and DriveTarget 0x458e9e encode section bytes | Two proven snapshot codecs change; separate replay/save coverage UNKNOWN |
| Pointer snapshots | 0x442d77 load, 0x442d8c header, 0x442da8 shift16; restore 0x442d44 | Already section16/node16; no wider handle required below 32768 sections; node load/stride still change |
| Packed node flags | 0x44d570 decodes +0x84 bits20..24, sentinel31 | Intersection index, NOT a section ID; preserve its semantics |

| Widen inventory / list locator in TSV | Count or addresses | Scope of estimate |
|---|---|---|
| `FuturePointField`, `ByteExtension`, `SectionSentinel`, `RoutePointField`, `SignpostField` | 45 / 50 / 29 / 10 / 8 rows = 133 DISTINCT instruction locations | Overlapping load/extension rows counted once; 20 `NodeSentinel` rows are node checks, not section conversions |
| DriveTarget and snapshot additions; `DriveTarget_bulk_count` | 47 further retail candidates, including 30 whole-object copy/clear counts | Candidate edits, not an assertion that each instruction must change under every possible new layout |
| Existing cave byte readers, `CaveSectionByte` | 0x797067, 0x797190, 0x7971d0, 0x79720f, 0x79724c | Source entry +0xa and node +0x83 still byte-sized in patched build |
| Manager/table reuse sites | 42 manager +62 table immediates, enumerated as `ManagerAddress` / `SectionTableIndex` | Existing relocation sites; NOT 104 automatically additional width patches |
| Table/range/allocation changes | 0x442b13,0x442bd7,0x443116,0x4431e5; 0x456ca8,0x435e79; 0x41f8a1; current ROAD_RB caves | Retail table128, current256; EBASE256 at0x796410 and ROAD_RB0x796810 overlap a larger table unless allocation changes |
| Integration dependency | `host/input.c:383` reads old0x77af30; patches use0x796010 | Existing host lookup requires reconciliation; not changed here |

| TRACKB chunk | Section-bearing fields | Data tool consequences |
|---|---|---|
| 0x34121 | TrackRoute s16 +0xa; point byte +0x83 after header0x27c | New node layout/stride must match parser and every node consumer; `ug2_traffic.py:67-71,380-428,542` |
| 0x34122 | Count u32, records at payload+4; byte +9/+0xa, stride0x20 | New entry layout/stride must match readers, writer and EBASE hook; `ug2_traffic.py:363,367-379` |
| 0x34123 | Section bytes +4/+5, stride0x170 | Loader 0x442e18/0x442e29 and intersection users change if present; current generated WORLD omits it |
| Format producers | `ug2_traffic.py` reader/writer/checker; `citygraph.py` MAX_SEC/city_chunks/slot_entry; `caves/road.s` | At least 2 Python data modules + existing assembly cave source; `ug2_collfile.py:75` already calls apply() |

| Longer-section constraint | Proof | Meaning for ~175 UG2 sections |
|---|---|---|
| Count versus maximum ID | `citygraph.py:32` sets MAX_SEC=254; 0x456ca8 patched compare accepts ID254,0xff means none | Byte encoding has255 non-sentinel values0..254; current254-section writer uses0..253. One extra value cannot resolve the855-section gap |
| Nodes/section <=32767 | Signed +0x10 reads 0x442bb2,0x456cc9; FuturePoint node s16 +0x5e | Full UG2 has10603 nodes; arithmetic average60.59/section, below this bound |
| 2 outgoing slots/node; 255 local entries/section | 0x4564b0 and +0x81/+0x82; EBASE readers above; `ug2_traffic.py:367-379` requires rank<255 | Merging retains branch/entry constraints; cannot flatten arbitrary junctions into one chain |
| 2047 global entries, 11-bit cache | `patches_road.py` Stage3 masks0x458c29/0x458cf0/0x458c95; source UG2 has3289 entries | Full source links do not fit unchanged; remap/dedupe and preserve topology, or widen entry capacity too |
| Walker / AI lookahead | 0x456753:102400 iterations; 0x45673d:100 alternatives; 0x5a59ae:minimum10 points,0x5a59b8:maximum40 | Traversal guards, not allocated nodes/section or proven metric length limits |
| Spawn | 0x59a4a5 loads250m, walk0x59a4b8; distance rejection500m0x59a598 | This FreeRun path has no per-section car quota; absence elsewhere UNKNOWN |
| Length and distance offsets | `ug2_traffic.py:380-407` computes cumulative float offsets; TrackRoutePoint+0x38 consumers | No metric section-length cap proved; cycle/wrap behavior of a new partition remains UNKNOWN |
| Coverage, same source-header metric | `ug2_roads.load('A')`:855 sections,184305.699m; `ug2_traffic.select(g,175)`:175,44049.563m,2102 nodes | Current23.90% of raw centerline sum; duplicated centerlines mean this is NOT unique geographic coverage |
| Existing merge measurement | `citygraph.build(radius=3,undirected=True)` on UG2 geometry:450 sections,113.477km; directed586 | Brief's ~410 is parameter-sensitive; this measured variant needs275 further reductions to reach175 |
| Topology obstacle | Raw entries:2530/3289 sources interior; only35 unique endpoint-to-endpoint pairs | Simple raw concatenation is insufficient; full175-section valid coverage UNKNOWN until a partition exists |

| Risk / estimate | Facts and proof |
|---|---|
| Crash family (cause found 2026-11-13, census/names_crash.tsv) | 0x44c56e and 0x5838c3 call driver vtable+0x3c through AIVehicle+8. Writer: the decider cache of 0x458bd0 (8 dwords at AIVehicle+0xc). When all 8 slots are in use the free-slot scan leaves ebp=-1 and the store at 0x458caf `mov [edi+ebp*4+0xc],esi` writes AIVehicle+8 (the driver pointer) with (old & 0xffffe001) \| entry<<2 \| 1. FACT: RN_STW run, traffic car v 017585f0, store 01758f95 over 01758af0 by guest pc 458caf, entry 997, all 8 slots in use, 96 s into WORLD. Retail has the same instructions; INFERENCE: it never filled the cache (an entry every ~22 nodes, the city net every ~3). Fix: PATCH 0x458c86 skips the store when the cache is full (cave F 0x797280, counter at [0x7977f0]; patches_road.py). Proof runs: unfixed crash at 96 s (RN_STW names pc 458caf); fixed, same route, 600 s and 600 s silent; fixed with every traffic cache forced full (RN_CWFILL=1), 300 s silent, fix path ran. The widened table is not the cause; our masks only changed which bits the corrupt value holds. |
| A: widen past byte | Estimate:185 candidate instruction locations (180 retail+5 existing cave), 5 carrier schemas plus manager/EBASE/teleporter arrays and embedded owners, >=2 Python data modules + cave source, 2 snapshot codecs, up to3 road chunk layouts. TSV lists every counted location. Exact patch count and transitive stride/owner closure UNKNOWN; this is a lower-bound review surface, NOT a complete patch plan. |
| B: resegment to175 | Lower bound:0 section-width patches,0 new carrier layouts,1 implementation data module (`ug2_traffic.py`, reusing citygraph), regenerate34121/34122 through unchanged collfile caller. Capacity arithmetic permits10603 nodes averaging60.59 and1053.18m per section; achievable connected/full-city coverage and additional entry-cap patches UNKNOWN. |
| Remaining RE | Whole-binary pointer aliases/copies, every stride/embedded-owner displacement, independent minimap/replay carriers, authentic GC member names, and topology-preserving175-section construction are unresolved. No runtime verification or screenshot: explicitly RE-only. |
