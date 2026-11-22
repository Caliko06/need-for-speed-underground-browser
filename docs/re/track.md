# Track: loading, sections, streaming, collision, route (Speed.exe PC)

Marks: V = verified (a second tool agrees: Hopper export H vs Ghidra export G, plus capstone C over pc/Speed.exe, or file
bytes F through tools/re/chunks.py), I = inferred, U = open. Prior notes (`re_stream`, `re_coll`, `re_zones`,
`re_mesh`, `re_citygraph`) were D; every claim reused here was re-read in the binary, the ones that were not are marked I/U.
Loaders and chunk ids are in docs/re/assets.md and not repeated; this doc starts where a TRACKB chunk has been handed to its loader.
Names: census/names_track.tsv (62 rows, 48 V / 14 I). Road network (0x34121..24, traffic) belongs to docs/re/traffic.md.

## Answer
- A race track is five independent data sets that share the TRACKB<id>.lzc file: collision polygons (0x34130..34), the route and
  zones (0x80034147), the streamer tables (0x34107/08 + 0x80034150), the road network (traffic) and the marker list (0x34146).
  The visual world is not in TRACKB: it is the 423 `0x80034100` sections of STREAML1RA.BUN, read on demand (H+G+C).
- Collision is a quadtree of 32 m cells over 32-byte polygon rows; a row becomes a "body" (plane + 4 vertices) only when a query
  touches it, from the slot pool `TrackPolygonSlotPool` (0x80-byte slots) (V H+G). Cars ask `GroundQuery` (0x4407b0 / 0x440a40) with a cached box.
- Streaming is a per-frame state machine `0x445050` -> `0x445180`: the viewer (player car) position picks one of 101 boundary
  polygons, each boundary lists the sections to keep; up to 3 async reads, LRU eviction (V H+G+C).
- The race "path" (0x34148/49) is one route per track: closed (circuit, tracks 1001..1008) or open (sprints 1102..1109), 22..100 nodes
  of (x, y). The game builds a spline object per path (`0x4432a0`, class `Spline`, basis `0x59c850`) and uses the nodes for
  nearest-node search, reset-to-route and wrong-way logic. Zones (type 0..10) live in the same container (V F+H+G).

## Flow (addresses; V unless marked)
1. Load: `GameFlow` creates TRACKB<id> (`0x449765`), `0x4496a0` builds `TRACKS\STREAM%s.BUN` paths and calls `StreamSections::SetTrack 0x4445c0`
   (I for 0x4496a0; V for 0x4445c0). Each top-level chunk goes to its loader (table `0x7007e0`): collision 0x441ed0 -> 0x441380,
   sections table 0x4442a0, boundaries 0x446aa0 -> 0x446db0, route container 0x4441f0 -> 0x4434d0 -> `TrackPath::Init 0x443450`.
2. After load `0x449870` (I) runs: `0x4412b0` TrackPolygonSlotPool::Init, `0x4432a0` BuildSplines, `0x4435e0` SetReverse (G only),
   `0x4430b0` road net post-load. Loading screen then loops `0x445100` (WaitUntilIdle) until the first streaming round is done.
3. Sections: per frame `0x445050` Update -> `0x445180` Round. Viewers come from `0x48e8b0` (I) which copies the player cars' xy and velocity.
   `0x444fb0` gets the boundary id of each viewer with `0x444870` (3 look-ahead samples, type-10 zones, corridor 0x34153) and needs
   3 equal ticks to switch. `0x444b50` BuildWantedSet adds the specials {2500, 2400, 2600, 2499} (C: `mov word [esp+0x18..0x1e]` at 0x444b6e), the
   track's 0x34154 list, each viewer's 0x34152 list and (first round only) rows with preload flag +0xa; cap 0x100 (C cmp at 0x444d5b).
   `0x444ee0`/`0x444d80` allocate (2 per call, stop after 0x9c3c00 B), `0x444780` evicts the loaded unwanted row with the oldest LRU stamp.
   `0x4446e0` issues the read (state 2) through ResourceFile; `0x444740` sets state 3 when it finishes; the section loader `0x4457c0`
   parses it into the table `0x72a008` (indexed by section id).
4. Draw: `0x4465b0` -> `0x446400` (camera boundary -> ids 2600..2699 + the visible list; outside every polygon only id%100 < 10)
   -> `0x446140`/`0x446220` BVH walk (0x34104) -> `0x445ec0` per placement (LOD by distance, view mask) (I for the last three).
5. Collision query: `GroundQuery::FindSurfaceBelow 0x440a40` (cache box 0x4407b0 radius 8.0) -> `TrackCollision::QueryBox 0x441c10`
   -> per 32 m cell `0x441530` quadtree -> `0x441660` polygons (mark byte, bbox selector) -> `0x441b90` body from the pool -> `0x4400e0` edge test
   -> z from the plane. Walls/other rows have flag bits 2/8 (`(flags & 0x0a) == 0` is ground, re_coll). 160 rows cap per query (0xa0, V C/H/G).
6. Route: `TrackPath::UpdateCursor 0x443a10` (called by ~23 sites: cars, AI, road entries) keeps a cursor near the previous node or runs
   `FindNearestNode 0x443630`; `NeighbourNodes 0x443920` wraps closed paths; `WrapDistance 0x443d60` is the signed distance (17 callers, AI/traffic).
   Reverse races: `0x4435e0` replaces zone distance fields +0x1c/+0x20/+0x24 by length minus value (I, G only).
7. Zones: manager `0x7372b0`; search `0x4436d0` (named Zone_Find in names_traffic), range search `0x443790`. Consumers: wrong way `0x430e00`,
   reset `0x427ed0` / `0x4314a0` / `0x4264d0`, commentary `0x43fb50`, streamer type 10 in `0x444870`. Details and per-track counts: `re_zones`.

## Structures (offsets verified by the named code and, for files, by tools/re/chunks.py on TRACKB1001..1109)
- wsrc row 0x20 (0x34132): +0 query mark byte (1 while collected), +1 bbox selector byte, +2 flags->body+0xb, +3 ->body+0xa, +4 s16 z hi,
  +6 s16 body slot (loader 0x441380 writes 0xffff to every row), +8..+0xe s16 x[4], +0x10..+0x16 s16 y[4], +0x18..+0x1e s16 z lo[4].
  Vertex = (s16<<13, ...) times 2^-16 (0x43fd20: x = x16/8; z = (zhi*256+zlo)*256/65536). V H+G.
- Body (slot 0x80 of pool 0x736184): +8 refcount byte, +9 type (3 = quad flagged 0x10, 4 otherwise), +0xa/+0xb row flags, +0xc source row,
  +0x14/+0x18/+0x1c/+0x20 bbox x0,y0,x1,y1, +0x30/+0x40/+0x50/+0x60 vertices (16 B each), +0x70/+0x74/+0x78 plane normal, +0x7c plane d. V H+G (0x43ff30).
  Pool node: +8 next, +0x10 free list, +0x18 used, +0x1c peak, +0x24 count, +0x28 stride, +0x2c capacity, data at +0x30 (0x43fe70 / 0x566ed0).
- Ground cache (GroundQuery object): +0 box min xy, +8 max xy (floats), +0x10 box used, +0x20.. body pointers, +0xa8 count, +0xac last hit. V H+G.
- Collision manager 0x77b130, wmap/wcell/wsrc/widx and the world bbox: `re_coll` (layouts re-checked: 0x441380 stores
  +0 wmap, +4 rows, +8 wcell, +0xc rows, +0x10 wsrc, +0x14 rows = size>>5, +0x18 widx, +0x1c count; bbox +0x30/+0x40 from 0x34134).
- Streamer 0x77a980: row 0x38 (0x34107): +8 s16 id, +0xa preload, +0xb wanted, +0xc state 0..3, +0x10 file index, +0x14 offset, +0x18 bytes, +0x1c resident
  bytes, +0x24 LRU, +0x28 request, +0x2c buffer. Viewer slots +0xd4/+0x118 (0x44 B: xy, v, enabled, id, candidate, counter). +0x17c count, +0x180 requests[256],
  +0x580 pool, +0x584 size, +0x588/+0x58c done callback, +0x598 corridor row. V H+G (0x4443e0, 0x444840, 0x444d80, 0x445180).
- Boundary 0x34151 row 0x8c (+8 id, +0xa nverts, +0xc xy pairs), visible set 0x34152 row 0x94 (+0x10 count, +0x14 ids), corridor 0x34153 (0x110),
  always set 0x34154 (0x20). V H+G (0x446db0 consts 0x8c 0x94 0x110 0x34151..54).
- Path row 0x28 (0x34148): +0 u8 0, +1 u8 closed flag, +2 s16 first node, +4 s16 end (exclusive), +6 s16 same, +0xc f32 length, +0x24 runtime Spline object
  (0x2c B: +0xe point count, +0x20 points, 16 B each (x, y, 0, 0); built by 0x4432a0). V F (16 tracks: closed=1 for 1001..1008, 0 for 1102..1109; length 2.9..8.2 km)
  + H+G for +2/+4 (0x443630, 0x443920) and +1 (0x443920, 0x443d60).
- Node 0x14 (0x34149): +0 f32 x, +4 f32 y, +8 u8 path index; +9..+0x13 U (0xff/-1 fillers in 1001). V F+G.
- Manager 0x7372b0 (init 0x443450): +0 total length (path0 +0xc), +4 reverse flag, +8 path count, +0xc rows, +0x10 node count, +0x14 nodes, +0x18 zone
  count, +0x1c zone rows (0xb4), +0x20..+0x48 first row per type (11 entries + end). V H+G.
- Zone row 0xb4 (0x3414a): +0 type, +4/+8 target xy, +0xc/+0x10 direction, +0x14 z limit, +0x18 selector (-1 any), +0x1c..+0x24 route distances (I),
  +0x28..+0x34 bbox, +0x38 nverts, +0x3c polygon, +0x7c boundary id, +0x80 track ids. V G (0x4436d0, 0x443450) + H.

## Functions by stage (62 names, census/names_track.tsv)
Collision body and query: 0x4412b0 0x43fd20 0x43fe70 0x566ed0 0x43ff30 0x4400d0 0x4400e0 0x4407b0 0x440a40 0x440ce0 0x440e00 0x441500 0x441530 0x441660 0x441b20 0x441b90 0x441c10 0x5679b0 0x567600 0x46a6e0.
Streaming: 0x444480 0x4443e0 0x4445c0 0x4446e0 0x444740 0x444780 0x444840 0x444870 0x444af0 0x444b50 0x444d80 0x444e90 0x444ee0 0x444fb0 0x445050 0x445100 0x445180 0x446400 0x4465b0 0x446fd0 0x48e8b0 0x4496a0 0x449870 0x58a850.
Sections/placements: 0x445520 0x445580 0x445ca0 0x445ec0 0x446140 0x445d00 (debug dump).
Route/zones: 0x443790 0x4435e0 0x443a10 0x443630 0x443920 0x443d60 0x430e00 0x427ed0 0x4314a0 0x4264d0 0x43fb50 0x564db0.
Already named elsewhere (not repeated): loaders in names_assets.tsv (0x441380, 0x4434d0, 0x443450, 0x4432a0, 0x4442a0, 0x4457c0, 0x446db0 ...),
road net and Zone_Find in names_traffic.tsv, props 0x445b00 / 0x469580.

## Second-tool agreement (10 re-derived names)
Rule: the name comes from reading one export; the other tool is asked the same question. G = Ghidra export, H = Hopper export, C = capstone.
| addr | name | what was re-derived | result |
|---|---|---|---|
| 0x441500 | CollisionGrid::Floor32 | `& 0xffe00000` then scale | G, H, C (and eax,0xffe00000 @0x44150f) agree |
| 0x441530 | CollisionQuadtree::FindCell | descent from -16384.0, 0 = empty, -1 on fallback | G and H agree on 0xffffffff and callees; levels read from G |
| 0x43ff30 | TrackPolyBody::Build | 14 shared field offsets (+0x38..+0x7c, plane) and callee set | G == H |
| 0x4400e0 | TrackPolyBody::EdgeDistanceMax | 8 shared vertex offsets 0x30..0x64, type byte +9 == 4 | G == H |
| 0x444af0 | StreamSections::ComputePoolSize | ids 0x9c4 0x960 0xa28 0x9c3 (2500 2400 2600 2499) | G == H; C: `add eax,0x200000` @0x4499a0 in its caller |
| 0x444b50 | StreamSections::BuildWantedSet | 4 specials, cap 0x100, offsets 0x164 0x6c | G, H shared; C: words at 0x444b6e..0x444b83, `cmp ecx,0x100` @0x444d5b |
| 0x444fb0 | UpdateViewerBoundaries | +0xec counter, 3-tick rule, 0x3e8 = 1000 | G, H share 0xec 0x179 0x3e8; C: `mov [esi],0x3e8` @0x444ffa |
| 0x446400 | StreamBoundaries::BuildDrawList | 0xa28..0xa8c (2600..2699), % 100 < 10 | G, H share 0xa28 0xa8c; C: `mov eax,0xa28`, `cmp eax,0xa8c` @0x446473/0x446497 |
| 0x4264d0 | Car::ServiceResetRequest | +0x734, +0x818/+0x81c, +0x888, 0x7fffffff | G, H share 11 constants; C: `[eax+0x734]` @0x426531, `cmp edx,0x7fffffff` @0x4266f9 |
| 0x444ee0 | StreamSections::AllocateRequested | give-up limit 0x9c3c00 (10,239,000 B) | G, H share 0x9c3c00; C: `cmp ebp,0x9c3c00` @0x444f00 |
10/10 agree. Wider check over the 62 rows: 59 exist in both exports and 53 of them have the same callee set. The 6 that differ are Hopper
fragment splits or inlined labels: 0x444780, 0x444870 and 0x444e90 were checked with C (0x4447d8 call 0x4483c0, 0x44495c call
0x4436d0, 0x444eb3 call 0x565ce0); 0x446140, 0x449870 and 0x58a850 are only I. Single-tool rows: 0x444740 (H+C), 0x4496a0 (H), 0x4435e0 (G).
Script: scratchpad agree.py (callee sets and shared constants, not committed).

## Label audit of census/systems.tsv `track` (827 rows)
Seen wrong while reading (the graph labelled them track): 0x4655f0 and 0x465770 (CollisionSlotPool / "Collision" are the car-body collision, not
track polygons; the track pool is `TrackPolygonSlotPool 0x4412b0`), 0x46d510 DriveTrain (car), 0x54cc10 "TRACK"/"HOST" (online), 0x4ba100..0x4bb160 (menu
track pictures), 0x417700 / 0x4b2c30 (FE_SKYLINE, front end), 0x578820 / 0x692e50 DrawBridge (props), 0x562660 / 0x5627e0 TRACK_NAME_%d (text).
The solid core is 0x430e00-0x4483c0 range pieces, 0x4264d0 family and 0x564db0/0x5679b0. Not a recount: only the rows read here.

## Open (U)
- Who advances race progress along the path (laps, position): `0x443a10` has 23 callers (0x422410, 0x422580, 0x426930, 0x4314a0 ...) but the
  lap/finish logic was not traced; cursor field meanings (+0x10..+0x1c) are I.
- Node bytes +9..+0x13 of 0x34149, path row +6, zone +0x1c..+0x24 meaning (route distances, I from 0x4435e0 only), zone types 7/8 readers.
- Row +0x1c vs +0x18 of the stream table and the code that shrinks the 19.5 MB TempTextures buffer (re_stream doubt 1).
- `0x58a850`'s OS mechanism (thread vs overlapped I/O); `0x48e8b0`'s other per-player objects; `0x449870` full duty (many calls, only the track ones named).
- Meaning of 0x34146 marker records beyond (type hash, index) and chunk 0x34250 trigger volumes (loader 0x588d10, V assets.md, consumers not traced).
- 0x440e00 (segment sweep) and 0x440d30 callers: wall response not traced. 0x4435e0 has no Hopper function (label inside 0x449870): G only.

HANDOFF: track.md and census/names_track.tsv done (62 names, 10/10 second-tool); next: trace lap/progress consumers of 0x443a10 and the 0x34146 markers.
