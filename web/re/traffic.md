# Traffic: road network, spawn, recycling, models, AI (Speed.exe PC)

> Source: `docs/re/traffic.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 114

# Traffic: road network, spawn, recycling, models, AI (Speed.exe PC)

Marks: V = verified (two tools agree, or code plus file bytes), I = inferred, U = open. Tools: H = Hopper export
`census/hopper/decomp.c`, G = Ghidra export `census/ghidra/decomp_*.c`, C = capstone (`tools/recomp/asm.py`),
F = the game files read with `tools/re/chunks.py` and a small parser (the checks are quoted in the text).
Earlier notes (`re_traffic_teleport`, `re_citygraph`, `re_ai_interact`,
`docs/traffic_placement.md`, [`docs/openworld_e_re.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/openworld_e_re.md)) were used as leads, not as proof; section "Prior notes" lists
what changed. Names: `census/names_traffic.tsv` (120 rows; V 67, I 49, U 4).

## Answer

- **There is no spawner and no despawner.** The number of traffic cars is fixed when the race is built; the cars are
  placed once at race start and afterwards only moved ("teleported") or parked. Nothing in the traffic code deletes a car.
  V (H+G: `0x4b3ac0` creates entrants, `0x422a70` places them, `0x598600` only calls the move `0x599830` or the park `0x5832a0`).
- **How many:** `n = s8 TrackInfo row[0xc0 + 2*level + dir]` (level 1..3, level 0 = none, dir = 0 forward / 1 reverse).
  Of the 31 track rows, 25 have 12 for every level; the rest range 6..22 (table below). At most 30 entrants exist
  (4 players/racers + 26 traffic): `0x4322a0` stops at `0x1e`. V (H+G+C+F)
- **Which cars:** only the 15 `CarTypeInfo` records with usage 2 are candidates, and each has a weight per "district".
  Every shipped track id is >= 1000, which always selects district column 0. In that column only six models have weight
  1.0: 4DR_SEDAN02, TAXI02, PANELVAN, PARCELVAN, PICKUP, SUV (equal odds). TAXI, AMBULANCE, COUPE, FIRETRUCK, 4DR_SEDAN,
  BUS, MINIVAN, HATCHBACK and HATCHBACK02 have weight 0 there and never spawn. V (H+G+C+F: `0x57d000`, GLOBALB.BUN)
- **Where they start:** at race start `0x422a70` calls `0x598bf0` once per traffic entrant. It tries, in this order,
  a node on the race route (`0x5991a0`, only when a route exists), a designer spawn record (`0x598c80`, chunk 0x34124),
  and for Free Run a random road node (`0x598fb0`), 100 tries each. V (H+G)
- **Density near the player** comes from one gate, the spacing `0x59b3e0`: 99999 m (nothing is placed) unless the player
  stands in a `TRAFFIC_DENSITY` zone (type 4) and no slow car is within 250 m of route; then
  `min + rand * (max - min)` metres from the zone, per traffic level (35..190 m in the files). V (H+G+F)
- **Recycling:** `TrafficTeleporter::DoTimestep` `0x598600` runs each frame, reloads a timer of 0.3 s (route) or
  1.0 s (Free Run), then checks 22 cars (route) or 1 car per tick. A car that is parked, or has been passed and is
  hidden, is moved ahead of the player: designer spawn record first, else a walk along the road graph 250 m
  ahead (limit 500 m route distance). If no spot is found the car is parked (`+0x4d1 = 1`). V (H+G)
- **AI:** traffic drivers are kind 3 (class with vtable `0x6b96b0`, update `0x583350`). Goal 4/5 selects, in order,
  ObeyTrafficIntersections (priority 600), AvoidAvoidableAsTraffic (300), else a lane drive. Traffic does not react to
  being hit and honks at the player within 50 m. V (H+C for the goal cascade) I (the rest)
- **Collision with the player:** no traffic-specific collision code was found in the traffic functions; traffic cars are
  ordinary car bodies in the 30-body car pool. The only "hit" logic in the AI (`IJustGotHit`) is for racers. I, U for scoring.

## Data layout

### Chunks (loader 23 `0x442dd0`, top level of every `TRACKB*.lzc`)

| chunk | stored at | record | files (31 TRACKB) | V |
|---|---|---|---|---|
| 0x34121 RoadSections | manager `0x77af20`, slots `+0x10 + 4*id` (128) | header 0x27c + n x 0x88 nodes | 504 sections, 32,460 nodes, all tile exactly; max 43 per file | H+C+F |
| 0x34122 RoadPathEntries | `[0x736150]`, count `[0x736154]` = size >> 5 | 32 B | 1,433 entries, 24..144 per file | H+C+F |
| 0x34123 RoadIntersections (was "traffic data") | `[0x736158]`, count `[0x73615c]` = size / 0x170 | 0x170 B | 49 records in 14 files (0 in 1001, 1007, 1008, 12xx except 1201) | H+C+F |
| 0x34124 RoadSpawnRecords (was "routes") | `[0x736160]`, count `[0x736164]` = size / 0x108 | 0x108 B | 94 records, 1..8 per file, 0 in 1008, 1202 and 13xx | H+C+F |

TRACKB1099 and the drag tracks (13xx: 2 sections each) have no intersections and no spawn records. Limits (V from code):
section id < 128 (table of 128), link byte < 255 (u8 everywhere), intersection index 5 bits (31 = none), entrants 30.

### Section (0x34121 record)

| offset | meaning | evidence |
|---|---|---|
| +0x0 / +0x4 | list links, written at load (file holds 0x0b) | V H+C |
| +0xa s16 | section id (slot index) | V H+C |
| +0xc s32 | list tag: 0 = list at manager+0, 1 = list at manager+8. List 1 holds exactly the 94 sections that carry a spawn record (94/94, none in list 0) | V C+F |
| +0x10 / +0x12 s16 | node count (equal in all 504 sections) | V H+C+F |
| +0x270..+0x27b | 12 lane flag bytes (6 per side; `0x442950` tests six at `+0x270` or `+0x276`) | I G |
| +0x27c | first node; next section = this + 0x27c + n x 0x88 | V H+C |

### Node (0x88 bytes)

| offset | meaning | evidence |
|---|---|---|
| +0 / +4 / +8 | x, y, z (f32) | I |
| +0x38 | route distance along the track loop (read by `0x442570` / `0x5ab160`) | I G |
| +0x68..+0x7f | lane data bytes | I |
| +0x81 / +0x82 | link slots: index into 0x34122, 0xff = none | V G+F (every link byte points at an entry whose source is this node: 1433/1433) |
| +0x83 | the node's own section id (0 mismatches in 32,460 nodes) | V F |
| +0x84 | bits 20..24 = intersection index (31 = none), bits 6/25/27 forward and 19/26/28 backward "drivable" flags (zero = the walker treats the node as a dead end) | V H+G (index), I G (flags) |

### Path entry (0x34122, 32 bytes) — corrects older notes

| offset | meaning | evidence |
|---|---|---|
| +0 f32 | distance, 0 in the file, filled at load (`0x442150`) | I H+F |
| +4 u16 | destination node index | V G (`0x5a53c0`) + F |
| +6 u16 | source node index (the node whose link byte points here) | V F (1433/1433) |
| +9 u8 | destination section id (`[0x77af30 + 4*byte]`) | V G + F (1433/1433 valid) |
| +0xa u8 | source section id | V F |
| +0xb u8 | type: file histogram 0:82 1:19 2:614 3:277 4:44 5:76 7:308 8:12 9:1; racer rule in [`docs/openworld_e_re.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/openworld_e_re.md) B1 | V F, I meaning |
| +0xd u8 | direction: 0 = forward entry, 1 = its reverse twin (21/21 pairs in 1006) | V F+G (`0x5a53c0` tests it with type 3) |
| +0x14 | 0xffffffff in the file | I F |

The older note "+0xc node index u16, +0xa section id" was wrong: +0xa is the source section and the nodes are at +4 / +6.

### Intersection (0x34123, 0x170 bytes)

Reached from a node by `0x44d570` (bits 20..24 of `[node+0x84]` x 0x170 + `[0x736158]`, H+G). In the file: `+0` u32 = 1 (all 49),
`+4` u8 section A, `+5` u8 section B, `+8` u16 node in A, `+0xa` u16 node in B, `+0xc` s32 = -1 (runtime current state),
`+0x10..+0x16f` = 22 runtime items of 0x10 bytes (byte flag, s32 state 0..3, f32 time, f32), initialised to 0 / -1 / -1.0 / -1.0.
V F: record k is referenced by exactly the two nodes (A, nodeA) and (B, nodeB) (49/49 in 14 files; example 1006 record 0 = section 102 node 13
and section 8 node 17). So an intersection is the crossing of two road sections. The runtime part is saved by
`TrafficIntersection` (`0x5aa9f0`) and `IncomingTrafficCar` (`0x5aaa90`) (H+C: the strings are pushed there). I: `0x5aaf10`
keeps `+0xc` only while an item for that state is live (time < 12.0 s); the stop/go choice is in `0x454490` via `0x5aaca0`.

### Spawn record (0x34124, 0x108 bytes) — designer spawn point

| offset | meaning | evidence |
|---|---|---|
| +0 s32 | section id (all 94 exist and the node indexes are inside them) | V G+F |
| +4 s16 x2 | node index for district/side 0 and 1 (-1 = none) | V G+H (`0x5ab210`, `0x5983d0`) |
| +8 f32 x2 | lateral offset per side (e.g. 8.68, -2.54) | I (passed to `0x59a7c0`) |
| +0x10 + 8*level + 4*dir f32 | factor x player speed = how far ahead it may be used (min), floor 20 m (`[0x6b5a4c]`) | V H+G (`0x599fc0`) |
| +0xe0 + 8*level + 4*dir f32 | same for the upper bound, floor 120 m (`[0x6b5a48]`) | V H+G |
| +0x70 / +0x90 + 8*level + 4*dir f32 | placement distance: `+0x70 + rand * (+0x90 - +0x70)` (1006: 25..35 m) | V H+G (`0x599c80`) |
| +0xb0 + 8*level + 4*dir f32 | start speed in mph (x 0.447; 1006: 23..25) | V H+G |
| +0xd0 + dir + 4*level + 2*side u8 | allowed flag (1006 record 0: off at level 1, on at levels 2 and 3) | V G+F |
| +0x100 u8 | must be < 6 (all 94 = 0) | V H+G, I meaning |
| +0x30, +0x50 tables | read nowhere I found | U |

### Track row (chunk 0x34201 in GlobalB, 31 rows x 0xfc, `[0x736168]`; current row `[0x736174]`)

+0x20 name, +0x6c s16 track id. Traffic fields (V G+C+F):

| offset | meaning | values in the files |
|---|---|---|
| +0xc0 + 2*level + dir s8 | traffic cars asked | table below |
| +0xc8 + dir u8 | 1 = skip the start clear zone | 1202 forward and 1210 forward only |
| +0xcc + 4*dir f32 | start clear zone radius (m): no spot within it of the player's start while he stands still | 500; 1202 reverse 775; 1210 350 |
| +0xd4 + 4*dir f32 | spacing to every other car (m) | 31; 1201 and 1210 60; 1206 45; 1202 reverse 55 |
| +0x6a | a byte used as the start speed cap by `0x42adf0` | I (value 0..2, meaning not proven) |

Cars asked (level 1 / 2 / 3, forward direction; reverse equal except where shown):

| track | L1 | L2 | L3 |
|---|---|---|---|
| 1001, 1002, 1005, 1006, 1099, 1102..1109, 1206, 1207, 1214, 1301..1308 | 12 | 12 | 12 |
| 1003 | 6 | 10 | 12 |
| 1004, 1008 | 9 | 10 | 11 |
| 1007 | 12 | 10 | 12 |
| 1201 | 10 | 11 | 12 |
| 1202 | 14 (rev 9) | 20 (rev 11) | 22 (rev 12) |
| 1210 | 12 | 14 | 15 |

Level text (lang.py, English): TRAFFIC_NONE "None", TRAFFIC_LIGHT "Minimum", TRAFFIC_MEDIUM "Moderate", TRAFFIC_HEAVY "Maximum" (V F).
That level 1/2/3 are these three is I. 1202 at level 3 asks 22, so 26 entrants fit under the cap of 30.

### TRAFFIC_DENSITY zone (type 4 row of 0xb4 bytes in `0x3414a`, inside container 0x80034147)

`+0x7c` holds 6 s32 = (min, max) spacing in metres for levels 1, 2, 3 (`0x59b670` reads `+0x7c + 4*(2L-2)`, `0x59b6a0` `+0x7c + 4*(2L-1)`; C+G).
V F: 31 files hold 0..6 such zones (45 in all); examples 1001 (80,95 / 50,65 / 35,45), 1202 (170,190 / 150,175 / 135,155). More traffic = smaller spacing.

### Car records used by traffic (`CarTypeInfo`, 35 x 0xc90, `[0x734588]`)

`+0xc50` index, `+0xc54` usage (0 tuner x20, 2 traffic x15), `+0xc60` five f32 weights (districts 0..4), `+0xd9` paint count,
`+0xc80` paint ids. Column 0 and paint counts: 4DR_SEDAN02 1.0 (8 paints), TAXI02 1.0 (1), PANELVAN 1.0 (6), PARCELVAN 1.0 (2),
PICKUP 1.0 (8), SUV 1.0 (8); the other nine traffic types 0.0. District = 0 for ids >= 1000, else `id/10 - 1` (60 -> 4); all 31 shipped
ids are >= 1000 (V F), so columns 1..4 are unused. Traffic rides get no tuner skin slot (`0x448f70` sets the entrant byte +0x17 to 0xff, I H).

### Globals

| address | meaning |
|---|---|
| `0x78a300` traffic level 0..3, `0x78a2fc` track direction, `0x78a2f0` track id, `0x78a304` = 0.5, `0x78a347` "no traffic" flag | V H+G |
| `0x78a418` / `0x78a41c` entrants (0x750 each; +1 id, +3 grid, +4 kind 1 human / 2 racer / 3 traffic, +0x10 car type, +0x17 paint) | V H+G |
| `0x7361f8` world car list (count `0x41f680`, car `0x41f690`) | I |
| `0x6b5a30` 1.0 s, `0x6b5a34` 0.3 s (timer); `0x6b5a38` 250 m, `0x6b5a3c` 500 m; `0x6cc988` 24.5865 m/s; `0x6b5a5c` 20 m/s; `0x6b5a64` 0.35 | V G+F |
| traffic driver object: `+0x410` no path, `+0x4d0` active, `+0x4d1` parked / needs move, `+0x4d2` parked once, `+0x4d4` direction, `+0x4d8` mode (9/4/0), `+0x4dc` target speed | I G+C |

## How it runs

1. **Race build.** Each mode setup (`0x4b49e0` circuit, `0x4b5df0` event, others) sets `[0x78a300]` and calls
   `Race::SpawnTraffic` `0x4b3ac0`. For each of `n` cars: pick a type (`0x57d000`: weighted, retried up to 100 times to avoid a
   type already in the entrant list, then a repeat is accepted), pick a paint (`rand mod [type+0xd9]` -> `[type+0xc80+i]`), add an entrant
   of kind 3, id `0x32 + i` (`0x5809c0`, `0x4322a0`). No factor 1.5 appears here (the Free Run factor in `docs/traffic_placement.md` is U). V (H+G+C)
2. **Race start.** `0x422a70` places players and racers, then each kind-3 entrant with `0x598bf0` (see Answer) and links the car into `[0x7361f8]`.
   `0x5992f0` builds the car: driver mode (`0x59b620` maps `[0x78a3fc]` 0/1/2 to 9/4/0), paint, goal 4 or 5, start speed. I (G)
3. **Each frame.** `0x598600`: updates intersections (`0x59b6d0`); if the level is nonzero, cars and players exist and the teleporter is enabled, the timer
   runs down, `0x5988c0` asks "needs a move" (parked, or passed and not visible), `0x599830` moves it. V (H+G)
4. **Move** `0x599830`: pick a player (`0x59b370`). With probability 1.0 (0.35 if that player is below 20 m/s) try the spawn records
   (`0x599c80`: needs records; side = rand < 0.5; window = the player's route position, +-60 m if a slow player is near, else a spot ahead;
   `0x599fc0` picks a record at random among those allowed; the car is put `+0x70 + rand(+0x90 - +0x70)` metres out at `+0xb0` mph). Else route mode
   `0x5999c0` (a node 250 m ahead on the route) or Free Run `0x59a2c0` (walk the road graph 250 m from the player's node, doubling the step,
   give up past 500 m; side random below 24.5865 m/s, else the player's way). A spot needs a lane (`0x5995e0`), a drive flag (`0x4420b0`) and
   `0x59aa60`: not inside the start clear zone, not within 250 m of a player's route (`0x59ad90`, race state 4), and not closer than the
   spacing to any other car (`0x59b1e0`). On failure `0x5832a0` parks the car. V (H+G)
5. **Despawn.** None. Parked cars wait for the next move; the 500 m rule of `re_traffic_teleport` (free_recycle) is a host patch,
   not in the game. I
6. **Driving.** `0x583350`: per tick one traffic car of N is updated (round robin on `[0x6f08a4]`, I); a car with `+0x410` set only brakes; a failed route update
   parks it. Goal selectors `0x44e020` / `0x44e140`: if the action type is not 0x12 and the ceiling is <= 600, finder `0x4543d0` (intersection, priority 600);
   if the type is not 3 and the ceiling is <= 300, finder `0x453920` (car ahead in my lane within 5 m, priority 300). `0x453c60` changes lane (5 lanes) or
   drops to 6 m/s at 15..30 m and 0 at <= 15 m. `0x44c2e0` honks at the player within 50 m. V (H+C) for the cascade, I for the rest (`re_ai_interact` section 3)
7. **Collisions.** Traffic cars use the common car body (`CarCollisionBodySlotPool`, 30 bodies; `re_racer_cap`). Parking increments a counter at
   `[[veh+0x3c]+0x1b]` (U what tests it). Racers avoid traffic through the shared neighbour list (`re_ai_interact` section 4, I).

Placement rules in detail (V asm, 2026-11-06; scratchpad gap1):
- `0x59b1e0` (Spot_NearOtherCar) walks the WHOLE car list `[0x7361f8]` (players, racers, traffic, parked or not). Metric = route position, not Euclid:
  `d = 0x443d60(node+0x38, car+0x814)`, wrapped to +-L/2 on a loop. Skips self, any car with byte `[car+0x8a8] != 0` (meaning U) and, when flag == 0 (teleporter), cars with `[car+0x4d0] == 0`.
  Traffic car (entrant kind 3): near if `|d| < spacing` (31 m). Racer or player: near only if `0 < d < spacing`, i.e. the spot is 0..31 m AHEAD of it; a racer 20 m ahead does not block.
- `0x59aa60` has NO camera, frustum or line-of-sight test. "Out of sight" = route distance >= 250 m (`[0x6b5a38]`, rule b, state 4 only) from every player. It is a pure predicate
  but rejects every spot within 250 m of the player route, so it is wrong for placing rivals. Straight-line variants 0x59acd0 / 0x59b130 are dead code.
- `0x59a2c0` Free Run move is the only candidate walk: one chain from the player's node (`0x4563d0`, 250 m, then step doubles from max(spacing, node length): about 250, +s, +3s, +7s), give up past 500 m.
  There is no stored candidate list and no reusable generator: every path tests spots inline and then moves a TRAFFIC car (driver mode, goal 4 / 5), so calling it on a racer would corrupt its AI.
- Failure: `0x5832a0` parks the car; it is looked at again when the round-robin cursor returns (1 s in Free Run). The 49 intersections are not a placement input (no call to 0x44d570 / 0x442100 in 0x598600..0x59b700).

## Functions

The 120 names with evidence are in `census/names_traffic.tsv`. Main ones:

| address | name | role |
|---|---|---|
| `0x442dd0` / `0x442b70` | RoadNetwork_Load / RoadSections_Parse | chunk loader; section slots and lists |
| `0x44d570`, `0x442100`, `0x42ae20`, `0x42ae30` | Node_GetIntersection, RoadIntersection_Get, SpawnRecord_Get / Count | data accessors |
| `0x5a53c0`, `0x4563d0`, `0x458bd0` | RoadPath_Step, RoadGraph_Walk, RoadPath_LinkAccepted | graph walkers |
| `0x4b3ac0`, `0x57d000`, `0x4322a0`, `0x422a70` | SpawnTraffic, PickType, AddEntrant, PlaceAllRacers | build and start |
| `0x598bf0`, `0x5991a0`, `0x598c80`, `0x598fb0`, `0x5992f0` | placement chain | race start |
| `0x598600`, `0x5988c0`, `0x599830`, `0x599c80`, `0x599fc0`, `0x5999c0`, `0x59a2c0`, `0x59a7c0` | teleporter | recycling |
| `0x59aa60`, `0x59ad90`, `0x59b1e0`, `0x59b3e0`, `0x59b670`, `0x59b6a0` | spot tests and spacing | density |
| `0x583350`, `0x583700`, `0x5832a0`, `0x582f90` | TrafficAI update / reset / park / ctor | driver |
| `0x44e020`, `0x44e140`, `0x4543d0`, `0x454490`, `0x453920`, `0x453c60`, `0x44c2e0` | goals, intersection and avoid actions, honk | AI |

## Prior notes: what the binary changed

| note | claim | result |
|---|---|---|
| `names_raw/assets_loadersA.tsv` | 0x34122 "+0xc node index u16, +0xa section" | wrong: source section +0xa, source node +6, destination +9 / +4 (V G+F) |
| same | 0x34123 "per-section traffic rows" | they are intersections (two crossing sections, 49 in the game) (V H+G+F) |
| same, [`openworld_e_re.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/openworld_e_re.md) | 0x34124 "traffic route/junction records" | designer spawn points with per-level tables (V H+G+F) |
| `re_traffic_teleport` | timer, 22 vs 1 car, 250/500 m, 0.35 gate, 99999 spacing | all confirmed (V H+G+F) |
| `re_traffic_teleport` | "0x421a50 = route mode" | `[race+0x54] != 0 or [0x7361a8] != 0` (V H+G) |
| `traffic_placement.md` | Free Run asks 12 x 1.5 | the factor is not in `0x4b3ac0` (U: host patch or other path) |
| `re_ai_interact` | goal cascade 600 / 300 | confirmed (V H+C) |

## Second-tool agreement (10 sampled names)

Hopper and Ghidra exports both hold the entry, show the same compares and the same direct callee set for all 10:

| address | callees H / G | shared compares and constants | result |
|---|---|---|---|
| `0x4b3ac0` | 8 / 8 same | `[0x78a347] == 0`, row offset `0xc0`, entrant stride `0x750`, `0xc54`, 100 tries | agree |
| `0x57d000` | 2 / 2 same | `1000` (0x3e8), weights `+0xc60`, index `+0xc50` | agree |
| `0x598bf0` | 4 / 4 same | order 0x5991a0, 0x598c80, 0x598fb0 | agree |
| `0x598a50` | 5 / 5 same | section compare through vtable `+0x40`, route difference `0x443d60` | agree |
| `0x59b1e0` | 8 / 8 same | iterate `0x421960`, skip `0x4280f0`, `0x443d60` vs spacing | agree |
| `0x59ad90` | 6 / 6 same | race state `== 4`, `< [0x6b5a38]` (250 m) | agree |
| `0x59ae60` | 1 / 1 same | `0x421a50` -> 0x3e99999a (0.3) else 0x3f800000 (1.0) | agree |
| `0x59b6d0` | 3 / 3 same | loop to `0x44a320` = `[0x73615c]` | agree |
| `0x422a70` | 4 / 4 same | slot compare `<= 4`, kind, stride `0x750` | agree |
| `0x4322a0` | 1 / 1 same | `cmp [+0x12c], 0x1e` (also C) | agree |

10/10 agree. Other entries checked: `0x598600` (H 24 callees, G 20), `0x599830` (16 / 11), `0x599c80` (23 / 17), `0x59aa60` (14 / 10) and `0x5988c0` (8 / 7): in each case G is a subset of H and the
extra Hopper calls sit in dead `if (0x0 != 0x0)` blocks or tiny accessors Ghidra drops (seen in `0x598600` and `0x599830`; the others not traced, I). `0x59a2c0` (H 27, G 20, G subset) and `0x583350`
(H 13, G 14; Ghidra adds `0x44ca70`) agree on every call that matters. `0x442dd0` is not in the Ghidra export; H and capstone agree there (compares 0x34121..0x34124).

## Open

1. Who writes the traffic level: `[ebx+0x59d4]` is read at `0x4b5e61` and no writer was found by a scan of the whole `.text`; the options block `+0x18` feeds `0x4b49e0`.
   EventDesc `+0x134` holds 0..3 (38 / 36 / 32 / 10 events) but no link to `[0x78a300]` is proven. The front-end "Traffic:" option is not traced.
2. `[0x78a3fc]` 0/1/2 -> driver mode 9/4/0 (`0x59b620`): meaning unknown; the strings "Traffic mode" (0x6c8ce8) and "Traffic in mellow mode" (0x6c8cd0) have no direct reference.
3. Free Run count 12 -> 18 (x 1.5) in `docs/traffic_placement.md`: not found in `0x4b3ac0`.
4. Car state setter `0x426110` (states 0..4) and the counter at `[[veh+0x3c]+0x1b]`: what each state does to collision and drawing of a parked car.
5. Player-vs-traffic contact: no traffic-specific code found; the HUD string STYLE_TRAFFIC_HIT exists but no code referencing its hash was found; scoring of traffic hits is not located.
6. Intersections: the gate `0x5aaca0`, the 22 items and the `type` field (all files hold 1; `0x454490` has cases 2 and 3) are not decoded.
7. `CCrossTrafficEmitter` / `CrossTrafficEmitters` (drag races, strings at 0x6b7d03 / 0x6b7d18) have no direct reference; the drag cross traffic is not covered here.
8. Entry fields +8, +0xc, +0xf and node bytes +0x68..+0x7f; spawn record tables at +0x30 / +0x50; track row byte +0x6a; the "usage 1" car branch in `0x4b3ac0` (no record has it).
9. District columns 1..4 of the traffic weights are dead for the shipped tracks (ids < 1000 only); whether any mode feeds a smaller id is not shown (I from the 31 rows).
