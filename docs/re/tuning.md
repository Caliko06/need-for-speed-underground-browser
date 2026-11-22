# Tuning, parts and garage (Speed.exe PC)

Marks: V = read in code or bytes this session, I = inferred, U = open. Tool after each claim: G = Ghidra 12.1.4
(REA MCP or headless `tools/ghidra/gpar.sh`), H = Hopper export `census/hopper/decomp.c`, C = capstone `tools/recomp/asm.py`,
D = data read with `tools/re/carinfo.py`. PS2/GC names come from `ref/docs/re/out/x86-ps2-map.tsv` and are hints only
until a row in `census/names_tuning.tsv` says V.

## Answer

- **Where the numbers live.** All car physics comes from one chunk, `0x34600` in `game/Global/GLOBALB.BUN`.
  It holds 35 `CarTypeInfo` records of 0xc90 bytes (20 tuners, then 15 traffic cars).
  Each record has the stock `CarPhysicsInfo` (0x2b0 bytes at +0x110). After it come the per-car upgrade tables for
  levels 1..3 of every performance path, then one "Junkman" delta per path. V (G, H, D)
- **How upgrades reach physics.** Every rebuild (`RideInfo::RebuildPhysicsInfo` 0x57f2b0) copies the stock block
  into the ride (`RideInfo+0x60`), then applies each path's table row for the level in
  `PhysicsUpgradeSpecification` (`RideInfo+8`: `int level[11]`, `int junkman[11]`). Some paths replace fields
  (gear set, tires, suspension, nitrous) and others add (engine/ECU/turbo torque, brakes, aero). Weight scales
  the mass. There is no formula per part: the designers' table row *is* the part. V (G, H)
- **Visual parts** are a separate database: chunk `0x80034602`, with 4,537 parts, 8,113 attributes and a string
  table. Each part has a car hash, a slot/type byte, a level byte (0..4) and a list of (bStringHash, value)
  attributes (colour, texture, rim size...). The visual parts do not touch physics. The only link is the aero
  term in RebuildPhysicsInfo, which grows with the *handling* levels, not with the kit. V (G, D)
- **Prices and cash exist** (corrected 2026-10-29 by night-opus-a2; the earlier "no prices" was wrong). Cash is
  `[0x76026c]` (career+0x1374). The cost table is chunk `0x34a01` in `FrontEnd/FrontB.lzc` → `[0x733f78+4*type]`,
  with cost L1/L2/L3 at +4/+8/+0xc (100..4000) and rating points at +0x10..+0x1c. Readers are `0x5a08f0` (visual)
  and `0x5a08b0` (perf); the payment is `0x5a2620`/`0x5a25a0`. A tier unlocks when a career event whose reward is
  {type 0, price type, level} is won (`0x5a1550`). V (C, G, D). Full flow: `docs/re/garage.md`.
- **Two old labels were wrong.** `0x583ea0` is not a speed cap. It is the generic lookup in a uniformly sampled
  float table `{n, xmin, xmax, 1/step, data*}` with linear interpolation and clamping, V (G). The "tuning block"
  `0x705f48..0x705f84` is four of those tables for **steering**: maximum wheel angle vs speed (45° at 0 down to
  2.9°/7° at the axis end 160; the unit of that axis, km/h?, is I: the exe gives only the number), a 6-point factor and a 0..1 return scale. They are read by the steering limiter
  `0x460a80`/`0x460de0`, not by the garage. V (G, D)

## Corrections to older notes (for the orchestrator to apply)

| Note | Says | This RE shows | Evidence |
|---|---|---|---|
| [`docs/driving_patches.md:4`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/driving_patches.md#L4) | "the speed caps 0x583ea0, tuning 0x705f48..0x705f84" | `0x583ea0` is the generic lookup in a sampled float table (with clamping and linear interpolation; no cap of its own). `0x705f48..0x705f98` are four of those table headers for **steering vs speed**, read by `0x460a80`/`0x460de0`. Car tuning lives in GLOBALB chunk 0x34600 | V (G, D) |
| an archived plan (not published) | "speed caps 0x583ea0 on 0x705f48..0x705f84 (lead); bought upgrades really change the tuning values" | Same correction. Upgrades do change the physics, through `0x57f2b0` → `0x575960` with the table rows in §1. The 0x705f48 tables are the steering limit (relevant to the "rigid, late" handling item, not to upgrades) | V (G) |
| [`docs/re_scoreboard.md:57`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re_scoreboard.md#L57) | tuning block `0x705f48..`, speed caps `0x583ea0` | Point it to this doc and to chunk 0x34600 / `0x57f2b0` | V |
| `ref/docs/re/out/x86-ps2-map.tsv` row 0x473fc0 | `PhysicsUpgradeSpecification::GetUpgradeLevel` (tier I) | `0x473fc0` picks a row of the drift/drag blend table `0x6f0fc0` by a float vs 0.2/0.8; not GetUpgradeLevel | V (G, H) |
| `re_rivals_ai` | position curve "through sub_4175c0 / sub_583ea0" | Consistent: 0x583ea0 is the table lookup that reads that curve. No change needed | V |

## 1. Data: CarTypeInfo (chunk 0x34600)

Loader `0x57c8b0` (V, G+H): if the chunk id is `0x34600`, it sets `[0x734588] = (chunk+0x17) & ~0xf` and, for each
of 0x23 records whose `+0xc54 == 0`, calls `0x581d30` (it clamps per-car grip/load sums against limits at
`0x6f0d30..`). In the data, `+0xc54` is 0 for the 20 tuners and 2 for the 15 traffic cars (D).
Strings at the start of each record: name, name, `CARS\<X>\GEOMETRY.BIN`, `.LZC`, maker (D).

Upgrade tables, offsets from `CarTypeInfo+0x110` (level n at `base+(n-1)*size`). Builder addresses are V (G, H).
The field meaning is V where a consumer is named and I otherwise.

| Path (spec index) | Base | Row | Builder | Effect |
|---|---|---|---|---|
| 0 weight | 0x2b0 | 0x10 | 0x576250 | mass `[+0x110] = row[0] * stock`; inertia recomputed as a box `m/12*(b²+c²)` from dims +0x114..0x11c |
| 6 transmission | 0x2e0 | 0x40 | 0x576360 | replaces the gear set at +0x1b0 (final drive, reverse, gears; gear count = non-zero gears) |
| 2 engine | 0x3a0 | 0x40 | 0x575bc0 | adds 16 floats to the torque curve +0x1f0..0x220 and +0x248..0x250 |
| 5 ECU | 0x460 | 0x40 | 0x575bc0 | same shape as engine; the first floats raise the rpm limits (GOLF L3 +1500/+2000 rpm, D) |
| 3 turbo | 0x520 | 0x30 | 0x575bc0 | copies 9 floats to +0x224 (turbo curve) and adds them into the torque curve |
| 4 nitrous | 0x670 | 0x10 | 0x575bc0 | copies {seconds, shots(int), ?, strength} to +0x2a0..0x2ac; stock is 0 s, 0 shots |
| 7 tires | 0x5b0 | 0x40 | 0x575a90 | replaces 8+8 floats at +0xd0/+0xf0 (front/rear grip blocks) |
| 9 spoiler | 0x6a0 | 0x10 | 0x575b30 | adds 3 floats to aero +0x264..0x26c |
| 10 ground effects | 0x6d0 | 0x10 | 0x575b30 | same as spoiler |
| 8 brakes | 0x700 | 0x10 | 0x575960 | replaces 3 floats at +0x274..0x27c |
| 1 suspension | 0x730 | 0x50 | 0x575a10 | replaces springs/dampers +0x170, +0x190; lowers ride height (+0x8, wheel y +0x18/0x48/0x78/0xa8) |

Junkman deltas (one per path, applied when `spec.junkman[path] != 0`, V G+H): weight 0x820 (subtracted from the mass
factor), transmission 0x824, nitrous 0x828 (+strength), brakes 0x82c, tires 0x830 (4 floats), engine 0x840 (9),
ECU 0x864 (9), turbo 0x888 (9). The suspension junkman flag (spec+0x30) is never read, matching the PS2 note. V (G, H)

Values, GOLF (D): stock mass 1.33; weight L1..3 = ×0.949/0.900/0.850; transmission L3 adds a 6th gear (0.73);
nitrous L1..3 = 2/4/6 s in 2/4/6 shots. All 20 tuners share the nitrous rows. Transmission L3 gives every tuner
6 gears. The ECU rpm rows differ per car.

## 2. RebuildPhysicsInfo 0x57f2b0 (V G+H)

`edi` = RideInfo: `+0` car index (-1 = none), `+8` spec, `+0x60` output physics. Order of work:
1. `BuildCarPhysicsInfo 0x575960(stock = CarTypeInfo+0x110, out = ride+0x60, spec = ride+8)`: memcpy of 0xac dwords,
   then suspension 0x575a10, tires 0x575a90, aero 0x575b30, brakes (inline), engine/turbo/ECU/nitrous 0x575bc0,
   transmission 0x576360, and weight 0x576250 last.
2. Mode blend (only when `[0x78a344]==0 && [0x7361a8]==0` and one of `[0x735fa0]`, `[0x78a345]`, `[0x7361a4]`;
   0x78a345/0x7361a4 are the drift flags per `re_zones`): `0x473fc0` picks one of 3 rows of the
   0x6c-byte table `0x6f0fc0` from `out+0x1c0` (thresholds 0.2/0.8 at 0x6cc960/0x6cc95c). The row pulls several
   fields back toward stock by factors and snaps `out+0x1c0` to 0.175/0.5/0.825. V for the mechanics, I that this is
   the drift/drag handling assist. The map name "GetUpgradeLevel" for 0x473fc0 is **wrong**.
3. Aero top-up: `out+0x264..0x26c += (CarTypeInfo+0x7d0.. + +0x800..) * (level[0]+level[1]+level[7]) / 9 * blend`
   (0x6ccb88 = 0.1111): the L3 spoiler and ground-effects rows, scaled by weight+suspension+tires levels. V (G)
4. `0x581b30(ride+0x410)` builds the force-vs-speed table: for 75 speed steps it shifts gear when the gear's rpm
   limit is passed and stores wheel force/mass. It then resamples the result into the table at ride+0x410. V
   mechanics (G); naming I.
5. Tuners only (`+0xc54==0`): integrate (force(v) − drag k·v²/m) over the speed range of that table in steps of
   1.3411 m/s (3 mph) until the drag wins. Compare with thresholds `0x6b5bd8 = {0, 280, 390, 500}` and store
   the class 0..3 at `ride+0x424` and the integral at `ride+0x428`. V (G, C); meaning I (performance rating
   shown in the garage / used by matchmaking).

Nitrous at race time (V, C+H): the CarState reset 0x464c80 sets `[cs+0x3b0]=[cs+0x3b8] = ftol(seconds*4000+0.5)`
(4000 ticks/s, 0x6cc9fc) and the per-shot ticks `[cs+0x3b4] = seconds/shots*4000` when shots ≥ 1.
`0x465490` = available (time left ≥ threshold and not firing). `0x4654f0` = start: it stamps `[cs+0x3bc]` with
the clock `[0x73ad34]`, then subtracts one shot, or keeps the tank full when `[0x7000e8]` (infinite-NOS cheat or
mode flag, I).

## 3. Data: car part database (chunk 0x80034602)

Sub-chunks (V, D + loader 0x57c8b0 G):
- `0x34603` header: `+0x10` part count 4,537, `+0x18` attribute count 8,113.
- `0x34606` strings.
- `0x34605` attributes, 8 bytes each: `(bStringHash name, value)`.
- `0x34604` parts, 0x30 bytes each.

Part record:

| Off | Field | Evidence |
|---|---|---|
| 0x00 | string offset (display name) | D |
| 0x04 | car name hash (`bStringHash("GOLF")` etc.; one shared hash for generic parts) | D: resolves to the 20 car names |
| 0x08 | part name hash | D |
| 0x0c | brand/group hash (paint: GLOSS, METALLIC... = 7 groups) | loader buckets 7 hashes × 3 levels into 0x73ad54..0x73adf8 (G) |
| 0x10 | slot/type byte | loader: 0x1e paint, 0x1f vinyl get special lists (G) |
| 0x11 | level (0..4) | loader clamps level-1 to 0..2 for the paint lists (G); data 0..4 (D) |
| 0x12 | sub-index (kit/style number) | D |
| 0x14 | first attribute index | loader: `+0x14 = attrs + idx*8` when count `+0x1c` ≠ 0 (G) |
| 0x18 | second attribute list index (count +0x1e) | G |
| 0x20, 0x24 | two hashes (texture / model) | D, I |

Type byte by content (D; labels I unless a garage function confirms them):
0 base, 1/2/10 body kit pieces (16 kits ACE..WOLFPACK × 20 cars), 3/4 mirrors, 5 stock body/tire, 6 MANTIS/VAPOR (level 4),
7 roof scoops (BLIZZARD, GILLS...), 8 hoods (with "CF" carbon variants), 9 trunk, 11 spoilers (AEROMAX, KATANA...),
12 engine bay style, 13 headlights, 14 taillights, 15 exhaust tips, 16 brake kit, 17 rims (`BRAND STYLE SIZE`, attrs
0xeb0101e2 = 15..21 and 0xce7d8db5 = 23..26 are sizes, I), 18 plate, 19..29 decal zones, 30 paint (body and caliper
colours, RED/GREEN/BLUE/GLOSS), 31 vinyls + sponsor decals (TEXTURE, REMAP, NUMCOLOURS), 58 sponsor logos,
115 window tint, 116 neon, 118 rim brands, 119 collision volumes.
Chunk `0x34601` (95 × 0x40) holds named colour presets ("Graphite Black w/ Silver Stripe"), read by 0x4322a0,
0x56a130 and 0x56dc30. I: these are the traffic/AI car liveries.

Reader: `tools/re/carinfo.py check` re-packs every decoded table and every part record and compares them with the
file. The result is 1435/1435 tables and 4537/4537 parts byte-equal, with all 8,113 attributes referenced.
V (D, 2026-10-29).

## 4. Unlocks (paint as the read example)

`0x4d7eb0` (map: IsPaintLocked, V-graph) and `0x4d8180` (IsPaintOwned). V (G), with the arguments partly lost by
Ghidra:
- A paint part with level byte (`part+0x11`) ≤ 1 is never locked.
- Otherwise the code asks `0x5a1550(&0x75eef8, key)` five times, once per level 0..4, and the part is locked when
  the answer for its own level is false. `0x75eef8` is the career/unlock state object (I).
- `[0x7677ac]` bypasses the lock entirely. It is the "career beaten" flag: `0x5a0dc0` writes 1 when the last
  event (0x71) is won, and the new-profile code `0x41cf40` clears it. V (G xref + patches.py:311 note). So beating
  the career unlocks every part. `[0x735ec1]` also bypasses (U).
- "Owned" first looks for the level in the list at `[0x737668]` (count `[0x73766c]`, 0x34-byte entries, type 1).
  It then accepts when any of `[0x7677ac]`, `[0x735e12]`, `[0x735ec1]` is set. Otherwise it compares the level
  with 2 or 3, using the flags `[0x735e10]`/`[0x735e11]` and the same `0x5a1550` queries.

So the level byte in the part DB is the unlock tier: tier n opens when the career reaches it.
The part record has no price field; the price comes from the per-type cost table (see garage.md §3). V (D)

## Open (U)
- Answered in garage.md §2: `0x5a1550` keys are price types; a tier opens when an event with reward {0, type, level} is won.
  Old note: the keys passed to `0x5a1550` and the perf-package unlock (same object?).
  Candidates that use attribute hash 0x10c98090: 0x4bbd70, 0x4bc790, 0x4c7790, 0x50d420, 0x580b00.
- Who writes spec levels 9/10 (spoiler/ground effects). The garage leaves them 0 on PS2. On PC only the
  RebuildPhysicsInfo aero top-up (step 3) is seen.
- The exact meaning of the out+0x1c0 float that picks the drift row (it is copied from the gear-set row +0x10).
