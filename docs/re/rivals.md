# Rivals: the AI racers of Speed.exe (PC)

Marks: V = verified (two tools agree: Hopper + Ghidra, or code + bytes of the game files), I = inferred, U = open.
Tools: G = Ghidra export `census/ghidra/decomp_*.c`, H = Hopper export `census/hopper/decomp.c`,
C = capstone `tools/recomp/asm.py dis`, D = data read from `game/` (`tools/re/events.py`, `tools/re/chunks.py`, scratch
scripts). Names: `census/names_rivals.tsv`. Earlier notes (`re_rivals_ai`, `re_rival_personality`,
`re_rival_turnback`, `re_racer_cap*`, `re_ai_interact`) were re-checked; section "Corrections" lists what was wrong.
Nothing was run. The REA MCP was not used.

## Answer

- **A career rival is a data row.** `EventDesc +0xd4` holds 3 rows of 0x1c bytes. A row has a name, a car preset hash,
  an AI skill 0..9 per difficulty, an optional car rating and an "aggression" byte. 313 rivals, 67 names. V (D, G, C)
- **Spawn path.** `0x4b5df0` (start career race) copies the event into race globals, builds the player entrant, then calls
  `0x4b4040(count, event)`. For each rival it builds the car from the preset (`0x4b26f0`), tunes its upgrade levels to a
  rating (`0x57f700` / `0x57f970`), wraps it in a DriverInfo (`0x5809c0`, id 100+k, kind 2, grid k+1, skill at
  entrant +0x735, aggression at +0x736) and adds it (`0x4322a0`). Then traffic (`0x4b3ac0`) and the grid swap
  (`0x4b6300`). V (G, H, C)
- **Quick race has no event.** `0x4b4040(count, 0)` picks 4 random names (`0x4b3a20`, 48 names), a random tuner car
  (`0x4b3c60`, 20 cars, never the player's model more than once, stock rating <= player rating + window), skill
  from a cumulative table by difficulty (`0x4b4590`: easy 0..2, medium 3..5, hard 6..8), aggression 1, and matches each
  rival's rating to the player's best car (`0x4b4380`). V (G, H, C, D)
- **Rating:** 303 of 313 rivals have rating -1 = "copy the player's upgrade levels and tune to the player's ride rating
  (+-5, widening)". 10 rivals (URL ladder and boss races) have 7, 8 or 9 = fixed target 140 + 63.1 x value on the
  140..771 rating scale. V (G, H, D)
- **The AI reads one 523-float table** (chunk `0x34b00`, copied to `0x779c78..0x77a4a0` by `0x462070`). It holds 10
  per-skill records (stride 0x54 at `0x779ff8`), 8 distance curves, 2 position curves, 8 player-factor pairs, the Block
  table, the quick-race skill table and the rubber-band period (0.3 s). V (C, D, G)
- **Rubber band** = `0x44bd10`, once per racer per 0.3 s. Scale = `1 + curve(distance, skill) + S x gain(position, skill)`,
  then x `max((f-1) x v(skill, rank) + 1, floor(skill))`; stored in `veh+0x404` as `max(scale, 1.0)` and in `ctx+0x4b8`
  raw. It is neutral for the first 3..19 s (by skill). S = `EventDesc +0x12c` (0.8..1.2). V formula, I directions
- **The AI reads time as 4000 ticks per second** (`0x6cca38` = 0.00025). Older notes used milliseconds. V (C, D). `0x6cca38` has 260 references across the whole binary: it is a global clock constant, not something of the AI (external audit 2026-10-29).
- **Skill at entrant +0x735 and aggression at +0x736 is I**: the constructor only copies arg5/arg6; which is which follows the caller's values. The rubber band reads skill. To make it V, read what each field is used for.

## 1. Where the data lives

### 1.1 EventDesc rival rows (chunk `0x34a02` in `game/FrontEnd/FrontB.lzc`, 116 records x 0x14c)
Rival k (k = 0..2) starts at `0xd4 + 0x1c*k`. Reader: `0x4b4040` (G, C; H lists only part of it). Reader tool: `tools/re/events.py`.

| off | size | meaning | mark | evidence |
|---|---|---|---|---|
| +0x00 | 8 | name, NUL padded (empty = no rival) | V | 0x5809c0 copies up to 16 chars from rival+0 into entrant +0x73c (C, G); 313 non-empty |
| +0x08 | u32 | 0x007f8060 / 0x007f7f80 / 0x007f9300-like value, no reader | U | scan found no read (older canon note) |
| +0x0c | u32 | preset key hash; 0 or unknown index -> random car | V | 0x4b4040 `[rival+0xc]==0`; 313/313 hashes are found in chunk 0x30220 (D) |
| +0x10,+0x12,+0x14 | i16 x3 | skill 0..9 for difficulty 0,1,2 (else -1) | V | `[rival+0x10+[0x78a3fc]*2]` (C, G) |
| +0x16 | i16 | rating: -1 auto, else 7/8/9 | V | 0x4b4040: -1 -> 0x57f700, else 0x57f970((float)v) (C, G) |
| +0x18 | u8 | aggression class 0..2 (else 1) -> entrant +0x736 | V | 0x4b4040 clamp; reader Block (0x44dbc9, 0x450ff5, 0x45116f, 0x45125a) (C) |
| +0x19..+0x1b | 3 | constant 0x37 0x40 0x00 | U | no reader |

Event fields that shape the rivals (all V by C + G on 0x4b5df0; D for values):
`+0x128` rival count -> `[0x78a324]` (3 on 102 events, 1 on 7, 0 on 7; forced 0 in Drift);
`+0x12c` float -> `[0x78a404]` (rubber-band strength S: 0.8x1, 0.9x14, 1.0x85, 1.1x14, 1.2x2);
`+0x134` class 0..3 -> `[0x78a300]` (curve set bit, section 3);
`+0x138` player grid slot (1 on 115 events, 2 on event 0) -> `0x4b6300`;
`+0x13c` float per difficulty -> `[0x78a380]` (1.0 on 109 events, 0.25..0.9 on 7 early ones; AI tournament score, section 5);
`+0x148` -> `[0x78a40c]` (0 on drag events 4, 9, 11, 17; 2 on the other 112; drag AI top-speed fraction, section 4);
`+0xd0` forced player car preset hash (only event 0, `0xffaad92a`; else the garage car, 0x4ac5a0).
Event kind 8 (repeatable cash races, ids 120..122): skills rewritten by `0x5a1b10` by progress band (<0x32: (1,2,3) (1,3,4) (2,3,4);
<0x4e: (3,4,5) (2,3,4) (2,3,4); 0x4d..0x71: (3,4,5) (3,4,5) (4,5,6)). V (G)

Data facts (D): skill values 0..9 = 20/42/126/176/164/167/135/78/22/9 over 939 cells; skills never decrease with difficulty;
mean easy/medium/hard rises from 1.1/2.2/3.9 (ids 0..19) to 4.9/5.9/7.5 (ids 100..119). Aggression 2 on 19 rows (Kurt 7x,
Chad 7x, Todd 3x, Eddie 1x... the URL ladder and boss rivals); 1 on 294. Ratings 7 on events 107/108/110 (7 rivals), 8 on 111
(TJ) and 112 (Eddie), 9 on 113 (Melissa).

### 1.2 Preset cars (chunk `0x30220` PresetRide[], `FrontB.lzc`, 184 rows x 0x408)
Row: `+0/+4` list links (head `0x748844`), `+8 char[0x20]` car type name (e.g. `ECLIPSE`, hashed case-sensitive, found by `0x57cf70`),
`+0x28 char[0x20]` key (hashed upper-case; this is the rival hash), `+0x48` 120 pairs `(slot id, part name hash)`.
`0x4b2640(hash)` walks the list; `0x4b26f0(hash in eax, ride buffer)` resets the ride to the car type (`0x57d160`), keeps the skin/wheel hashes
(+0x444/+0x448), then for each pair installs a visual part (`0x57ce10`) into `ride+0x44c+slot*4`, bumps `ride+0x62c+slot`
and calls `0x57ea80`. Slot ids 0x1e, 0x26..0x39 and 6/0xf/0x10/0x11/0x73/0x74 have special part lookups. V (G, H, D)
The presets are visual only: no upgrade levels. Performance comes from the rating match. 20 car models appear (Celica 22,
Supra 21, 240SX 21, RSX 19, Golf 18...). V (D)

### 1.3 Entrant (0x750 bytes, array `[0x78a418]`, count `[0x78a41c]`, cap 30 in `0x4322a0`)
`+0` flag, `+1` id (player 0, rivals 100+k), `+3` grid slot, `+4` kind (1 player, 2 rival, 3 traffic), `+0x10` RideInfo
(`+8` int level[11] + junkman[11], `+0x424` int8 "rating valid", `+0x428` float ride rating, `+0x444` skin hash,
`+0x448` wheel hash, `+0x44c` part pointers), `+0x734` remote flag, `+0x735` **skill** (i8; player and traffic 0xfe = -2),
`+0x736` **aggression class** (i8), `+0x73c` name[16]. Built by `0x5809c0(id, kind, ride, name, skill, aggr, grid)`. V (C, G, H)
The racer reads the skill through vtable slot `+0x58` = `0x44ca10`: `[[this+4]+0x14]+0x735`. Callers use `max(0, skill)`. V (C, H)

### 1.4 RacerAITuning (chunk `0x34b00`, GLOBALB, 523 f32; loader `0x462070` `rep movsd` 0x20b dwords to `0x779c78`)
Addresses are 0x779c78 + 4 x index. Values read from the file (D) and readers from the code (C, G).

| range (addr) | content | readers |
|---|---|---|
| `0x779c78 + 0x58k`, k=0..3 | 4 curves x 11 points (x = metres, y = speed delta), skill 0 | 0x44c101 (0x44c010) |
| `0x779dd8 + 0x58k` | the same 4 curves for skill 9 | 0x44c107 |
| `0x779f38` / `0x779f78` | 16 f32 each: position gain for skill 0 / 9 (index 1..14 used) | 0x44c20d, 0x44c214 |
| `0x779fb0` / `0x779fd0` | 8-byte pairs `(value at skill 0, value at skill 9)`, one per rank | 0x44bf82, 0x44bf8c |
| `0x779ff8 + 0x54*lvl`, lvl 0..9 | skill records, table in section 2 | many |
| `0x77a340 + 8*a`, a=0..2 | Block table: i32 priority ceiling (200, 200, 400) + u8 flag (1) | 0x44dbd0, 0x450ffc, 0x451176, 0x451261 |
| `0x77a358..0x77a3ff` | 12 floats (1.2 1.1 1 1.1 / 1.7 1.6 1.5 1.6 / 2.1 2.3 2 2.1) then 3 x 10 floats (0.3 0.8 1... / 0 0 0 0.2 0.5 0.8 1... / 0 0 0 0 0 0 0.5 1...) | no direct reader found (U) |
| `0x77a400 + 0x28*difficulty` | cumulative skill distribution, 10 floats: easy (.3 .7 1..) = skill 0/1/2; medium (0 0 0 .3 .7 1..) = 3/4/5; hard (0 0 0 0 0 0 .25 .75 1 1) = 6/7/8 | 0x4b4590 (0x4b42a1) |
| `0x77a478` | 4 points (-600 1.08, -250 1.03, -120 1.015, -50 1.0): two-human catch-up curve | 0x429b70 (0x429b10) |
| `0x77a498` = 5.0 | seconds between re-rolls of the speed-table jitter | 0x44c651 |
| `0x77a49c` = 0.3 | seconds between rubber-band updates | 0x44bdcf |
| `0x77a4a0` = 100000 | distance limit in 0x44c010 | 0x44c0a3 |

The four curves of a group: curve index `k = 2 x (laps >= 4) + (class in {2,3})`, laps from `[0x78a31c]` (thresholds `0x70077c` = {0, 4}; if
`[0x78a318]` != 0 the lap part is 0), class `[0x78a300]` = EventDesc +0x134. V (G, C)

## 2. Skill record (stride 0x54 at `0x779ff8`, index = skill 0..9)
Offsets are from the record start (recomputed from the addresses the code uses; the older table in `re_rival_personality` was shifted).
Values for skill 0 -> 9. "Reader" = instruction address (C).

| off | skill 0 -> 9 | reader | meaning |
|---|---|---|---|
| +0x00, +0x04, +0x08 | 0 / 0 -> 0.9 / 1 | 0x46298e, 0x462997, 0x4629a1 | cumulative chances at a road fork (section 6). V reader, I meaning |
| +0x0c | 1 for all | 0x4627ac (0x462740) | Pass/Avoid accept threshold; with 1.0 the draw always passes. V |
| +0x10 | 0.8 -> 2.1 | 0x44df02 (drag goal selector 0x44dd30) | argument of the avoid-cross-traffic action in drag. V reader, I meaning |
| +0x14 | 0.95 -> 1.0 | 0x44c72b (0x44c550) | multiplier on the speed taken from the route. V |
| +0x18 | 0.76 -> 0.92 | 0x44bf4a (0x44bd10) | floor of the player-factor term. V |
| +0x1c, +0x20 | -5 -> -1.5, -4.3 -> -0.8 | 0x44b21a (0x44b1b0) | random range of the timer at `[obj+0x4a0]`. V reader, I meaning |
| +0x24, +0x28, +0x2c, +0x30 | 0, 0.01, -900 -> -110, 300 -> 15 | 0x476e0d (0x476840) | copied to car AI struct `+0xd0, +0xd4, +0xc8, +0xcc`, only in drag. V |
| +0x34, +0x38 | 35 / 30, 17 / 15 | 0x462ca8, 0x462cb4 | distances in the pass/avoid rule 0x462b30. V reader, I meaning |
| +0x3c, +0x40 | 0.7 -> 0.5, 1.0 | 0x462e34, 0x462c5d | 0x40 is a time in seconds (x 0.00025 ticks). V reader, I meaning |
| +0x44, +0x48 | 0.025 -> 0.95, 0.1 -> 1.1 | 0x43ece4, 0x43ecf6 (0x43eb00) | low / high of an AI score gain (section 5). V |
| +0x4c | 3,4,5,6,8,10,13,15,17,19 | 0x44bd9d (0x44bd10) | seconds of race clock during which the rubber band stays neutral. V |
| +0x50 | 8,7,6,6,5,4,... (bytes) | 0x44c667 | jitter of the route node used for the speed (+-(b+1) nodes). V reader, I meaning |
| +0x51, +0x52 | 5..2, 0/1 | 0x44cb49, 0x462bf9 | not decoded (U) |

## 3. Rubber band (`0x44bd10`) and catch-up
Called from `0x44c550` for each racer. It runs only if: AIVehicle `[ctx+0x46c]` != 0, vehicle `+0x18` == 0, `[0x78a344]` == 0 (not drag),
`[0x7361a8]` == 0, and at least 0.3 s passed since `[ctx+0x420]`. V (G, H, C)

1. `scale = 1.0` (`0x6b77dc`). `ctx+0x470` = target = 0.
2. If `[0x7360ac]` == 0, `[[0x7361f0]]` != 9, `[0x78a320]` > 0 and the racer's action flag (`[[ctx+0x3f8]+0x1f2]`) is set, and the race clock
   is past the neutral window (record `+0x4c`): target = player object `[0x7361bc]` (one player; with two players the one chosen by race position
   against `[0x78a324]/2`). Then `0x44c010(rivalCar, targetCar, &out1, &out2)` and
   `scale = [0x78a404 + 4*target.slot] x out2 + 1.0 + out1`. V
3. `0x44c010` (needs `[0x78a400]` != 0): `d = (rival.progress - target.progress) x route length` (metres, + = rival ahead).
   `out1 = lerp_skill(curveA_k(d), curveB_k(d)) + clamp(((speedRival - speedTarget) x -0.005) / (0.01 x d^2 + 1), +-0.05)`;
   `out2 = lerp_skill(A[i], B[i])` with `i = (target.pos - rival.pos) + 7` (+8 if negative), curves `0x779f38` / `0x779f78`; `lerp_skill` = value A + (B - A) x skill / 9. V (G, C)
   Sample (curve 0, skill 0): d=-900 -> +0.13, d=0 -> +0.004, d=+640 -> -0.5 (rival ahead is slowed). Skill 9 uses the second group: +0.18 / +0.044 / -0.3. V (D)
   Direction of `out2` (negative when the rival is behind in rank) looks odd and is not tested (I).
4. If action flag and target: `scale x= max((f - 1) x v + 1, floor)`. `f = [[target+0xa8]+0xc]` (what it is: U), `floor` = record `+0x18`,
   `v` = pair table value at skill (`0x779fd0 + 8*rank` if f < 1.0 else `0x779fb0 + 8*rank`, interpolated by skill, rank = target car byte `+0xa`
   taken as 1-based: I). Table values rank 1..4: f >= 1: 0.75/0.97, 0.6/0.7, 0.4/0.5, 0.2/0.2; f < 1: 1.02/0.5, 1.07/0.74, 1.17/0.81, 1.27/1.0. V values, I indexing
5. `veh+0x404 = max(scale, 1.0)` (a rival is never slowed below 1.0 by this field) and `ctx+0x4b8 = scale` (raw). V (C: 0x44bfe9, 0x44bffe)

Who turns it on or off: quick race `[0x78a400]` = race options byte `+0x1f` (`0x4b4a56`, `0x43b199`); career sets 1 (`0x4b5f47`).
`[0x78a404]` (S, player 1) defaults to 1.0: reset `0x431e37` (RaceStatus reset `0x431df0`). Writers: `0x4b541c` (1.0, mode 4), `0x4b5f53` (career, event +0x12c), `0x4b65f2` (1.0, SkipFE); reader `0x44bed9`. No other store in the text, so quick-race circuits keep S = 1.0 (V). `[0x78a400]` (gate) is set by Reset (1), `0x4b4a56` circuit, `0x4b4caa`, `0x4b4edc`, `0x4b50f2` (free), `0x4b5365`/`0x4b5416` (mode 4), `0x4b5631`, `0x4b5a2a`, career `0x4b5f47` (1), LAN `0x43b199`; quick race = options byte +0x1f.
Two humans: `0x429b10` (called from `0x4264e2`) sets `veh+0x404` for the player behind by `d` metres: 1.08 at -600, 1.03 at -250, 1.015 at -120, 1.0 at -50. V (G, H, C)

## 4. Speed, skill and difficulty elsewhere
- **Desired speed** (`0x44c550`, per frame): `v = routeSpeedByte x record+0x14 x ctx+0x4b8`, capped by the car's own limit (vtable `[obj+0xff]` slot +0x10). The byte is read
  from route node `idx`, `idx = current node + jitter`, jitter in `[-(b+1), b]` re-rolled every 5.0 s (`0x77a498`) with `b` = record `+0x50`; speed byte = `(byte << 16) x 1/65536`
  at node `+0x6a` (array start; node stride 0x88, route base +0x27c). If the byte is 0 the code uses 30.0 (`0x6ccac0`). V (G, H, C), unit I
- **Drag only** (`[0x78a344]` or `[0x7361a8]`): `0x422410` (kind 3 = AI racer) sets `[driver+0x1fc] = 0x6b7c20[[0x78a40c]]` = 0.93 / 0.97 / 1.0
  (events 4, 9, 11, 17 use 0.93; all others and quick race use 1.0). `0x476840` (0x476d97) adds `0x6b70e0[difficulty]` = 3.0 / 1.5 / 1.0 for the
  human racer, and for AI racers `0x6b70ec[difficulty]` = 0.4 / 0.8 / 1.0 plus the record `+0x24..+0x30` values. V (G, C, D)
- **Difficulty** `[0x78a3fc]`: quick race = options `+0x14`, career = `[0x75f240]`. It picks the skill column (+0x10/+0x12/+0x14), the quick-race skill row, the drag tables,
  `+0x13c[difficulty]`, cash and the target time. It does not change the AI code. V (C, G)

## 5. Tournament points of AI racers (`0x43eb00`)
The race-manager update adds to each AI racer record `+0x10`: `1.0 x pointsTable[rec+0xc] x lerp(record+0x44, record+0x48, rec+0x24) x [0x78a380] x [0x700a18]`
for racers with ids 100+k (k < 4 - humans). It is the standing of the AI in point-based events. V code (G, H, C), role I.

## 6. Choosing actions (selector `0x44d8b0`, goal type 1 "road race")
Goal chosen once by `0x4623d0` (vtable slot +0x60): normal races (`[0x78a344]` == 0, `[0x7361a8]` == 0, not the 0x44b special track) = goal 1; drag: goal 3 for the human, goal 2 for rivals.
`0x44aa10(type)` builds goals 1..5 (ctors 0x44a150/190/1c0/200/230). V (H, C, G)
The selector (called as `goal->vt[5](ctx, currentType, currentPriority)`) is a fixed cascade; first hit wins. V (G, C: `cmp 0x1f4, 0x258, 0x190, 0x12c, 0x1f4, [0x77a340+..], 0xc8`)

| # | action (type) | needs current priority <= | finder -> constructor |
|---|---|---|---|
| 1 | GetUnstuck (10) | 500 | 0x451b00 and cooldown 6.0 s (vt+0x6c = 0x462aa0) -> 0x4519f0 |
| 2 | PickRouteToAvoidAnimation (0x13) | 600 | path+0xc0 != -1 -> 0x454930 |
| 3 | IJustGotHit (12) | 400 | 0x44ed70 -> 0x4521c0 |
| 4 | AvoidCrossTraffic (2) | 400 | 0x452b40 -> 0x452990 (arg 2.0) |
| 5 | AvoidAvoidable (1) | 300 | 0x44f8a0 and draw vt+0x74 (0x462740) -> 0x44f750 |
| 6 | AccidentRecovery (14) | 500 | 0x452630 -> 0x452570 |
| 7 | Block (5) | `0x77a340[8*aggr]` = 200 / 200 / 400 | 0x450ec0 -> 0x450e20 |
| 8 | Pass (0) | 200 | 0x450730 and draw vt+0x74 -> 0x450660 |
| - | JustDrive (7) | - | vt+0x18 (0x44b1b0 family) |

`aggr` = entrant `+0x736` = rival `+0x18`. So class 2 rivals (Kurt, Chad, Todd, Eddie) may start Block while doing actions up to priority 400; classes 0 and 1 only
over JustDrive and Pass. The names come from the action vtable strings (earlier notes: I). Finder bodies (Pass, Block, GetUnstuck) were only compared between H and G (same callees and constants), not re-read: I.
**Draw `0x462740` (vt+0x74)**: returns false if the same target was already refused less than 1.0 s ago (`0x6b734c`); else draws `rand01 < record+0x0c`; true = allowed.
With record `+0x0c` = 1.0 for every skill the draw always passes; a refused draw (never in shipped data) stores the target and time. V (C, D)
The "same target returns true" wording of `re_rivals_ai` was wrong.
**Fork decider `0x462840` (vt+0x44)**: by fork type byte (`[fork+0xb]`): type 8 true only for the human, 2 true, 5 and 7 false, 9 asks 0x454a20; otherwise one roll `r`:
`r <= rec+0` -> `type == 1`; `r <= rec+4` -> `type == 0`; `r <= rec+8` -> the default computed before. At skill 9 that is 90 % "type 0". V code, I meaning

## 7. Placement on the grid
1. Entrants get grid byte `+3`: player = `[0x78a334]` = 4 (`0x4b5df0`, `0x4b4a4c`), rival k = k+1 (1..3). V (C, G)
2. Career: `0x4b6300(eventGridSlot)`: finds the rival with id 100+k whose grid equals the slot and swaps its grid byte with the player's.
   Slot 1 (115 events) puts the player on pole and the first rival at the back; slot 2 (event 0). V (G, C, D)
3. Quick race: `0x4b4610`: one human = swap entrant 0 with a random entrant (`rand % (rivals+1)`, game RNG `[0x6f227c]`); two humans = pair shuffle. V (G, H)
4. At race start `0x422a70`: for slot s = 1..4 find the entrant with that grid byte, make it with `0x422410` (kind 1 human, 3 rival, 0 remote), position from
   `0x422580(4, buf)`. Only slots 1..4 exist. V (G, H, C)
5. `0x422580` uses the track markers `ForwardStartingPosition` / `BackwardStartingPosition` (0x21-hash, direction `[0x78a2fc]`); marker `+0xc` = slot index (0-based). If there
   are fewer than 4 markers it computes: row `(i/2) x 17.0 + 100.0` m along the route, lateral +3.0 / -3.0 m alternately (`0x6b7c2c`, `0x6b7c34`, `0x6b7c30`). V (G, C, D)

## 8. Turn-back, direction and driving line
- Direction of every racer = vtable slot +0x40 = `0x45d640` = `mov eax, [0x78a2fc]`. Nothing in the racer AI turns a racer around. V (C, H, G)
- The racer's path object type is its direction; it is built once when the ctx is created (`0x44cd30`, earlier note: not re-read, I) and grown per frame by `0x458cc0`.
  The traffic decider `0x59c210` shows the game's own reversal (path retype + clearing 8 cache bits). `host/free.c` already uses this for Free Run (see `re_rival_turnback`). I
- Driving line = the route object (node records of 0x88 bytes, speed byte per node, future-point pools: goal 26, action 27, FuturePoints 27, FuturePoint 640; overflow chunks make them soft caps).
  Slot pools do not fail when full (`re_racer_cap_probe`, I). The racer sees every car (human, rival, traffic) through the neighbour list built by `0x57a910` (16 cars max). I (earlier notes)
- AI random numbers: world RNG at `[[0x7361f8]+0x2d0]` (`0x4216b0` int, `0x4216f0` float), same xorshift as the global `[0x6f227c]` used for names, cars, skills and grid: `s ^= 0x1d872b41; t = (s >> 5) ^ s; s = (t << 27) ^ t ^ s`. V (G, C)

## 9. Corrections to older notes
| Note | Said | Binary shows |
|---|---|---|
| `re_rivals_ai` s4 | `[0x78a40c]` = difficulty | EventDesc `+0x148` (0 on 4 drag events, 2 elsewhere); difficulty is `[0x78a3fc]` |
| `re_rivals_ai` s2 | draw returns yes for the same target | returns no; draw is always true at record `+0x0c` = 1.0 |
| `re_rivals_ai` s4 | window threshold = record `+0x44` | `0x77a044` = record `+0x4c` (3..19 s); `+0x44` is the AI score gain |
| `re_rival_personality` B | `+0x04` fork chance, `+0x10` catch-up strength, `+0x14/+0x18` top / corner speed | `+0x00/+0x04/+0x08` fork thresholds, `+0x10` drag action arg, `+0x14` speed multiplier, `+0x18` band floor |
| `re_rivals_ai`, others | race clock in ms (x 0.001) | ticks, 4000 per second (x 0.00025) |
| `re_rivals_ai` s4 | catch-up strength `[0x78a404]` writer unknown | EventDesc `+0x12c` in career; unset in quick race |
| `re_rivals_ai` s4 | per-difficulty cap 0.93/0.97/1.0 | indexed by `[0x78a40c]` (event field), not difficulty |

## 10. Functions
Full list with evidence in `census/names_rivals.tsv`. Main entries: `0x4b5df0` StartRaceFromEvent, `0x4b4040` SpawnOpponents, `0x4b26f0` PresetRide::ApplyToRide,
`0x57f700` / `0x57f970` rating match, `0x5809c0` DriverInfo, `0x4322a0` AddEntrant, `0x4b6300` grid swap, `0x4b4380` quick-race rating match, `0x4b3c60` random rival car,
`0x4b3a20` names, `0x4b4590` skill roll, `0x422a70` / `0x422580` grid, `0x44bd10` / `0x44c010` rubber band, `0x44c550` desired speed, `0x462740` draw, `0x44d8b0` selector,
`0x462070` tuning loader, `0x429b10` two-human catch-up, `0x43eb00` AI score.

## 11. Second-tool agreement (10 sampled names)
H and G show the same entry, compares and callees for these (callee sets compared by address, self excluded; compared constants from `==, <, >` tests):
| fn | callees H / G / common | compares | result |
|---|---|---|---|
| `0x4b5df0` | 14 / 14 / 14 (417600 431df0 4322a0 43de90 4ac5a0 4b26f0 4b3ac0 4b4040 4b47a0 4b6300 5748c0 5809c0 5a05b0 674898) | 0,1,3,4 both; G also 8 | agree |
| `0x4b4380` | 4 / 4 / 4 (57d860 57f2b0 57f700 57f970) | 0,1,2,3 both; H 255 = G -1 | agree |
| `0x4b3c60` | 9 / 8 / 8 (H adds 0x4b3ef0, a shared tail) | 0,5,20,27,100,101,102 both | agree |
| `0x4b26f0` | 11 / 11 / 11 (40a880 4b2640 4b26b0 4b26d0 4bc790 53e400 567c70 57ce10 57cf70 57d160 57ea80) | 31 constants incl. slot ids 0x1e, 0x26..0x39 | agree (loop bound 120 vs 121) |
| `0x44bd10` | 4 / 4 / 4 (401c40 4175c0 44c010 583ea0) | 0,1,9 | agree |
| `0x44c550` | 11 / 11 / 11 (4216b0 421a30 424b50 4420e0 442110 44bd10 458f10 459ac0 465430 4654f0 59bb80) | 0,10,16 | agree |
| `0x422410` | 10 / 9 / 9 (H adds 0x67121a, the SEH helper) | 0,3 | agree |
| `0x422a70` | 4 / 4 / 4 (41fe50 422410 422580 598bf0) | 1,2,3 (H also 0,4) | agree |
| `0x43eb00` | 24 / 24 / 24 | 0,11 | agree |
| `0x44aa10` | 7 / 7 / 7 (44a080 44a150 44a190 44a1c0 44a200 44a230 567160) | 0 | agree |
Result: 10/10 agree. Not in both exports: `0x4623d0`, `0x462740`, `0x462aa0`, `0x462840`, `0x45d640` (H or C only; Ghidra merged them into
`0x462430`); `0x4b4040` is whole in G, split in H (3 callees). Those names rely on C plus file bytes.

## 12. Open (U)
- What `[[target+0xa8]+0xc]` (factor f in the rubber band) is; whether car byte `+0xa` is a 1-based rank; sign of `out2` in a real race.
- Reader of `0x77a358..0x77a3ff` (12 + 30 floats); records `+0x51`, `+0x52`; `+0x04..+0x08` of fork meaning in play.
- Rival row `+0x08..+0x0b`, `+0x19..+0x1b`; Drift mode rivals (`0x43de90`, ids 100..102 placeholders).
- Bodies of Pass / Block / GetUnstuck finders (re-read with both tools); path rebuild in `0x44cd30`; what the speed byte unit is (m/s?).
- Whether AI rating match for 4+ rivals (`0x4b4380` default branch) is correct for the cap patches (older note says OK).
