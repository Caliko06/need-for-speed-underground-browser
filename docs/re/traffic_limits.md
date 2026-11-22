# Traffic limits: how many cars, which models, colours, lights (Speed.exe PC)

Read only, nothing was run. Tools: Ghidra live on the named project (G), capstone `tools/recomp/asm.py` (C),
`tools/re/carinfo.py` on GLOBALB.BUN (F), file listing of game/Cars (D). V = read in code, I = inferred, U = open.
Names: `census/names_trafficpool.tsv`. Earlier notes (docs/re/traffic.md, `re_racer_cap_probe`) were leads.

## Answers first

1. **Count.** The first hard cap is 30 entrants (`0x4322a0`, `cmp [race+0x12c], 0x1e`). With 1 player + 6 rivals that leaves
   **23 traffic cars with no patch** (V, G+C). The 26 in `tools/recomp/caves/traffic.s` is the cave's own clamp, not the game's.
   The next real wall is the collision body id table: 0xde = 222 ids, bitmap of only 216 bits, no bound check (V, C+G). It is code,
   not data. Soft limits (pools grow, neighbour list 16) do not stop cars. Not run: nothing here proves 23 cars survive the id table.
2. **Variety.** 35 rows, 15 with usage 2. In the real game district 0 (every shipped track id >= 1000) gives weight 1.0 to only six
   models, so only six traffic models can ever appear. The cave 0x63b270 gives all 12 normal traffic rows weight 1.0 and lets 8
   racer cars in. Repeats come from the type count (6, then 12) and from the 100 re-picks that only try to avoid a type already in
   the entrant list. Paint is a per-model list of 1..8 ids. The teleporter keeps the model and re-rolls the paint on every move.
3. **Lights.** `0x429100(ecx=car, A, B, C, lights, horn, gap)` is the one call. Shown in section 3.

## 1. COUNT, in the order it bites

| # | Limit | Address | Value | On overflow | Data or code |
|---|---|---|---|---|---|
| 1 | Entrants | 0x4322a0 (G, C) | 30 (0x1e), stride 0x750, count [race+0x12c] = 0x78a41c | the entrant is dropped without any message; later code uses a smaller list | code: the immediate 0x1e. The array is a static pool 0x77c790..0x78a2f0 (30 x 0x750 = 0xdb60 bytes, ends at RaceStatus), cleared by `0x431df0` on return to the front end (sets [0x78a418] = 0x77c790, count 0); the cap 30 is structural, so raising 0x1e alone overruns into RaceStatus (V) |
| 2 | Collision body ids | 0x466970 (C), id taken at 0x469b00 (C) | 0xde = 222 ids; table 0x736050 = 0xde dwords; bitmap 0x736070 = 0x1b bytes = 216 bits | no check: id 216..222 writes past the bitmap, id 222 past the table (heap corruption) | code (two malloc sizes and 0xde) |
| 3 | Track polygon bodies | 0x466970, 0x469810 (G) | pool n = 0xa0 (160), stops adding when full | cars late in the update get no road polygons (I: may fall through) | code; they also take ids from 2 (U how long they live) |
| 4 | Car body pool | 0x466970: CarCollisionBodySlotPool n=0x1e, slot 0x190 | 30, flags 0xb | grows by n/4+1 = 8 slots (V, G 0x567160) | none needed |
| 5 | World object pool | 0x466970 n=0x20 (props, not cars) | 32 | grows | none |
| 6 | AI slot pools | 0x455530 (`re_racer_cap_probe`, not re-read) | 26/27/27/640 | grow (I) | optional |
| 7 | Neighbour list | 0x57a910, `mov [esp+0x4c], 0x10` at 0x57abad (C) | 16 cars per AI car | farther cars are invisible to that AI (soft) | code, not needed |
| 8 | World car array | 0x41fe50 (G) | array at L+0x28 where L = [0x7361f8], layout room 150 until L+0x280; +0x18 total, +0x24 index of first traffic car | none up to 150 | none |
| 9 | LoadedCar pool | 0x58c3b0 (G), pool [0x734500] | 40 (docs, I) | evicts unused entries, then grows | none |
| 10 | Model memory | not found | U | U | U |

Not a cap but what really limits the world: placement. Measured 19 placed of 21 asked in WORLD (docs/traffic_placement.md,
31 m spacing +0xd4 and 520 nodes). That is data in the TrackInfo row (host can write it).
Per-car sound/skid/shadow pools and model memory were not traced in the time given (U).

Largest count with no patch: 23 traffic (30 - 1 - 6), if placement and the id table allow it. Fewest patches for more: the immediate
0x1e plus (V) a larger array (the static pool ends at RaceStatus 0x78a2f0); the id table then needs 0xde and the two mallocs raised together.

## 2. VARIETY

Rows (F: carinfo.py, D: game/Cars). Columns: index name usage; skins +0xd9 and ids at +0xc80; weights +0xc60..+0xc70 (districts
0..4). Enable +0x40 is not a flag: it is the first byte of the geometry path ("CARS\NAME\GEOMETRY.BIN", 'C' = 67 in all 35),
so `0x57cfa0` accepts every row. Skin test: +0xd9 > 0 (0x57cfa0 skips the Lancer: 0 skins). All 35 have geometry; usage 0 files are
4.7 to 6.2 MB (full tuner models), usage 2 files are 60 to 90 KB (low detail). TEXTURES.BIN of usage 2 cars is 4616 bytes (U where
their body texture comes from).

| i | name | use | skins | weights d0..d4 | traffic now (stock / cave) |
|---|---|---|---|---|---|
| 0-12, 14-19 | GOLF FOCUS MIATA NEON CIVIC PEUGOT CELICA ECLIPSE RX7 SUPRA S2000 RSX IMPREZA INTEGRA TIBURON 350Z SENTRA 240SX SKYLINE | 0 | 1 each (id 1) | 1.0 all | stock no; cave: GOLF FOCUS NEON CIVIC PEUGOT CELICA INTEGRA SENTRA at 0.375 each |
| 13 | LANCER | 0 | 0 | 1.0 all | never (no skins) |
| 20 | TAXI | 2 | 1 | 0 0 1 0 1 | stock no; cave yes |
| 21 | 4DR_SEDAN02 | 2 | 8 (1-8) | 1 1 0 1 0 | yes / yes |
| 22 | AMBULANCE | 2 | 1 | all 0 | never |
| 23 | TAXI02 | 2 | 1 | 1 0 0 0 1 | yes / yes |
| 24 | PANELVAN | 2 | 6 (1-6) | 1 1 0 0 0 | yes / yes |
| 25 | COUPE | 2 | 8 | 0 0 0 1 1 | stock no; cave yes |
| 26 | FIRETRUCK | 2 | 1 | all 0 | never |
| 27 | PARCELVAN | 2 | 2 | 1 1 0 0 1 | yes / yes |
| 28 | PICKUP | 2 | 8 | 1 1 0 1 0 | yes / yes |
| 29 | 4DR_SEDAN | 2 | 8 | 0 0 1 0 0 | stock no; cave yes |
| 30 | BUS | 2 | 3 | all 0 | never |
| 31 | SUV | 2 | 8 | 1 1 0 1 0 | yes / yes |
| 32 | MINIVAN | 2 | 8 | 0 1 0 1 0 | stock no; cave yes |
| 33 | HATCHBACK | 2 | 5 | 0 0 1 0 1 | stock no; cave yes |
| 34 | HATCHBACK02 | 2 | 8 | 0 0 1 0 1 | stock no; cave yes |

Stock: 6 models (21, 23, 24, 27, 28, 31). Cave: 12 traffic rows + 8 racer rows = 20 models. BUS, AMBULANCE, FIRETRUCK stay 0.
The cave's weights were checked against the cave source only, not run.

Pick (V, G): `0x4b3ac0` calls `0x57d000`, which sums the weights of the rows `0x57cfa0` returns and walks with a random number.
After the pick it scans the entrant list for an entrant kind 0 with the same type; if found it picks again, at most 100 times
(`local < 100`), then accepts the repeat. With 12 cars and only 6 stock types, repeats are certain (more cars than types).
With 20 types the re-pick works and repeats fall. Tracks load all models up front: `0x448f70` asks `0x58c3b0` once per entrant
(U: whether equal types share one LoadedCar entry). No per-track model list was found; the repeat the OWNER sees is the type table.

Paint (V, G+C): `0x4b3ac0`: paint id = byte [row+0xc80 + rand mod [row+0xd9]], `Ride_Init(id)`, `0x57d340` fills the parts,
`0x57e9a0` sets ride+0x4c4 to the first part of kind 0x1e. Usage 1 rows use id 1 or 2. Skins per model: 1, 8, 6, 2, 8, 8 for the
six stock models (up to 8 for the others). At run time: call `0x569c30(ecx=car, id)` (sets [[car+0x10]+7], then 0x56c310).
`0x59a7c0` (the teleporter move) ends with `0x59b5d0`, which calls `0x59b590` (random id of the same type) and `0x569c30` when it
differs: so a recycled car keeps its model, and its colour changes with each move. A different model needs a new car (U).
The `+0x17` entrant byte is overwritten at placement by 0x5992f0 with `0x59b590` too (G).

## 3. LIGHTS

Fields (V, G+C): `0x429100` stores them, `0x429190` (every frame, not for human drivers) uses them. Time unit: `0x73ad34` runs at
4000 per second, 0.00025 converts to seconds.
- +0x844 time of the last arm. `0x429100` refuses a new arm until A + B + C seconds have passed since it.
- +0x848 A, +0x84c C, +0x850 B (floats, seconds). Pattern: on for A; if gap flag +0x840 = 1, off for A, else continuous; then on
  until A + B + C counted from the start (I from the compare order in 0x429190).
- +0x83e lights flag, +0x83f horn flag, +0x840 gap flag.
- Output: +0x855 = light is on (the flash phase with +0x83e, else the base +0x854). The sound object car+0x30 gets vtable +0x48 (horn on)
  when a flash phase and +0x83f, +0x4c (off) otherwise, +0x50 asks if it plays.
- +0x854 is a base "lights on" byte. Only writers: init to 0 in `0x425350` and the network field list `0x425af0`. No game code sets it
  (V, scalar scan). +0x855 is also set by the lights key, case 0x9a in `0x431960`, for human cars. The draw test `0x5693b0` returns 1
  for every traffic car (kind 3), else +0x855 (I: traffic lights may be always on at the draw; U whether a flash is visible).

Call in the game (V, `0x44c2e0` at 0x44c539): `ecx = car`; stack, last pushed first: gap (+0x840), horn (+0x83f), lights (+0x83e), C, B, A.
The game rolls: horn flag is rolled first (probability 1.0 / 0.75 / 0.05 / 0.075 by who the other car is and its relative lane speed);
only if the horn flag is set is the lights flag rolled (0.5, or 0.9 when the closing value [slot+4] > 50). A = 0.1..0.5 s (rand * 0.4 + 0.1),
B = 0.05..0.25 s, C = 0.1..0.5 s, +0.6 when closing > 50. Trigger: the other car is a human, not traffic and not usage 1 (`0x57a6b0`),
and it is in the traffic car's slot list. The older "within 50 m" is not what the code compares: 50 is tested against slot +4
(a closing speed, per `re_traffic_rivals`).

To flash and honk from the host: `0x429100` with ecx = traffic car, A = 0.3, B = 0.15, C = 0.3, lights = 1, horn = 1, gap = 1
(chosen values, not game values). It is silently ignored if the last arm is too recent.

## Flash visible: one byte (not applied, tools/recomp/patches.py is the orchestrator's)
0x5693b0 (C): `cmp [ecx+4],3 / jne +3 / mov al,1 / ret / mov al,[eax+0x855]`: a traffic car's head flare is always on (caller 0x56da42 in 0x56d8d0), so 0x429100's lights flag cannot show.
Byte 0x5693b7 `75` -> `eb` makes every car read +0x855. host/rivals.c traffic_tick already keeps the base +0x854 at 1 for traffic and at 0 for 48 frames during a flash, so the lights blink.
Without the byte nothing changes on screen; the horn works either way.
