# Garage UI flow, end to end (Speed.exe PC)

> Source: `docs/re/garage.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 197

# Garage UI flow, end to end (Speed.exe PC)

Source: night-opus-a2 with a sonnet-exec worker (2026-10-29). Data reader for the career chunk: tools/census/career.py.
Marks: V = read in code or bytes, I = inferred, U = open. Tools: H = Hopper export census/hopper/decomp.c,
G = Ghidra whole-program export census/ghidra/decomp_*.c (not live REA), C = capstone (tools/recomp/asm.py),
D = data (save/*.ugd, FrontB.lzc, exe bytes). The PS2 names are hints only.

## Answer

- **Prices exist.** (docs/re/tuning.md said "No prices"; it is corrected now.) Cash is career+0x1374 = [0x76026c], spent is +0x137c = [0x760274]. V (C 0x5a1520, 0x5a2620)
- **Price table** = FrontB chunk 0x34a01, 25 records in [0x733f78+4*type]. Types 0..15 are visual, 16..24 are the 9 perf paths. V (D, G 0x5a08f0)
- **Visual part price** = record[0x5a03d0(part.type)].cost[part.level-1]. Level 0 and level 4 cost 0. V (C 0x5a08f0)
- **Perf price** = record[0x5a0350(path)].cost[level-1]; path 0..8 maps to types 0x10..0x18. V (G 0x5a0350, 0x5a25a0, D). The function has 11 cases (`cmp eax,0xa`): paths 9 and 10 map to the visual types 8 and 5; this matches `level[11]` in tuning.md. The chooser shows 9 paths, the data model has 11 (external audit 2026-10-29, capstone).
- **Screens** are made by a name -> factory registry at 0x6f94d8.. (name ptr, factory ptr, flag; stride 0x14). V (C, D)
- **Hub:** `MU_Garage.fng` (GarageScreen, mode 1 from the career menu 0x4eaff0) lists Visual / Performance / Presets / Trade-in. V (G 0x504be0)
- **Garage state** is one global object at 0x744ff0: [+8] = FECarConfig*, [+0x10] ride A (preview), [+0x730] ride B (committed). V (C 0x504450, 0x5044b0)
- **Preview** = 0x504450 changes only ride A. **Cancel** = 0x504890 copies B over A. Nothing is committed until Install. V (C)
- **Buy a part** = 0x5a2620 (cash -= price, spent += price, mark bought) then 0x5044b0 (rebuild B from the config, set slot, write B back into the config). V (C 0x508a04..0x508a1c)
- **Buy a perf level** = 0x5a25a0 (pay) then 0x5047d0 (config spec[path] = level, rebuild, rebuild physics). V (C 0x50bc8f, 0x50bc9d)
- **Slot index = part type byte** (CarPart+0x10). The saved config has type bytes 1..25,30,119 as slot numbers. V (D asas0.ugd, C 0x508a10)
- **Unlock** of a tier = a career event with reward {type 0, value = price type, arg = level} was won (0x5a1550). 67 such rewards in 40 events. V (G, D career_oracle.json)
- **Star rating** 0x5a05b0 = a 0..5 "how customised" score from visual part points. It is not a speed rating. Shown by 0x4b0fd0. V (C), display I
- **Save:** the whole career object (config, spent, cash, bought table) is inside the 0xf660 blob written to `<profile>0.ugd` / `_autosave.ugd` by 0x41d8a0. V (G, D)
- **Autosave** fires when leaving the hub if the blob changed since garage entry (0x4c9570 -> 0x4c96f0). V (G)

## 1. Screens

Modes ([0x745e40], set by 0x504990, V G): 1 = career garage (prices, cash, career locks), 2 = main-menu "Car Customize"
(no prices; unlock records), 0 = called from 0x504a20 (caller 0x4e8580, new-career flow) I.
Entry: career menu 0x4eaff0 runs `0x504990(1, "MU_Garage.fng", 0)` with eax = 0x75eef8 (V C 0x4eb0a8). Car customize
0x4c6ab0 and 0x4bd0c0 run it with mode 2 (V C). 0x504990 stores cfg in [0x744ff8], builds ride A at 0x745000 and B at
0x745720 with BuildRide 0x4ac5a0, then pushes the hub (V G).

Registry rows (name -> factory -> ctor; V C/D):

| FNG name | factory | ctor / class | what it lists |
|---|---|---|---|
| GarageMain.fng | 0x4b2000 | 0x4af620 GarageMainScreen | the 3D car, stats bars, cash text, stars |
| GarageMain_2P.fng | 0x4b1fa0 | 0x4b2070 | 2-player variant |
| MU_Garage.fng | 0x504b80 | 0x504be0 GarageScreen | BROWSER_VISUAL, BROWSER_PERFORMANCE, BROWSER_PRESETS, BROWSER_TRADE_IN (mode 1 only) |
| MU_GaragePerformanceCategory.fng | 0x509d10 | 0x509dd0 ChooseGaragePerfPath | 9 paths via 0x50a070 AddCategory |
| MU_GaragePerformanceTuner.fng | 0x50a570 | 0x50a5d0 GaragePerfTuner | levels 0 (stock), 1, 2, 3 via 0x50abf0 |
| MU_GaragePerformanceBrand.fng | 0x50b680 | 0x50b6e0 GaragePerfBrandPackage | confirm / buy the chosen level |
| MU_PerformanceStats.fng | 0x509000 | 0x509060 PerfStatsScreen | stats panel |
| MU_GaragePartsChooseVisual.fng | 0x505660 | 0x505780 | BODY, RIMS, ACCESSORIES, PAINT, DECALS, VINYL |
| MU_GaragePartsCategoryVisual.fng | 0x506100 | 0x506210 | body kit pieces, then PartsBrowser |
| MU_GarageAccessoriesCategory.fng | 0x512cb0 | 0x512d10 | muffler tip, roof, tint, neon |
| MU_GaragePartsBrowser.fng | 0x507220 | 0x507540 GaragePartsBrowser | the part list, buy / install |
| MU_GarageRimsBrandBrowser.fng | 0x50d0a0 | 0x50c9e0 | WHEEL_MANUFACTURERS |
| MU_GarageRimsStyleBrowser.fng | 0x50e6f0 | 0x50d420 | styles, RIM_SIZE_15..21 |
| MU_GarageRimsBrowser.fng | 0x50f990 | 0x50e7c0 | rim parts |
| MU_GaragePaintMod.fng | 0x50c090 | 0x50c0f0 | paint of parts; opens PC_ColorPicker.fng |
| MU_GarageDecals_Zone/Size/Slot/Brand.fng | 0x50faa0 / 0x510670 / 0x510d60 / 0x511aa0 | 0x50fb00 / 0x5106d0 / 0x510f50 / 0x511ff0 | zone -> layout -> slot -> brand |
| MU_GarageVinylType/Group/Browser/LayerV2.fng | 0x4e4ae0 / 0x4e5630 / 0x4e6600 / 0x4e3a60 | 0x4e40d0 / 0x4e4c40 / 0x4e5700 / 0x4e2a00 | vinyls |
| MU_GaragePresets.fng | 0x4e8120 | 0x4e7a40 | saved presets |
| MU_UG_JunkmanGiveth / TradeCareerCar / MainMenuCarCustomize | 0x4c7670 / 0x4c3610 / 0x4c64d0 | 0x4c6cb0 / 0x4c2ed0 / 0x4c6530 | Junkman part, car trade, entry from main menu |

Moving around (V G/C): every list screen answers the same FE messages. 0xc407210 = accept, 0x911ab364 = back,
0xb5971bf1 = next item, 0x9120409e = previous item (0x505130 moves the list node), 0xc98356ba = screen shown again,
0x2f6484d0 = "yes" of a dialog, 0xf0aadebb = perf confirm. On accept the screen stores the choice in a global
(hub [0x73571c]; path chooser [0x6f8864], [0x6f889c], [0x735730]; parts browser [0x735724] category, [0x735720] car hash),
calls PushScreen 0x504320 and queues a command with 0x4f0800 (V G 0x505200, 0x50a2a0). Back calls PopScreen 0x504390. PushScreen
sends GarageMain.fng a depth message 0x1c2d8258+depth (0x504260, I: camera / panel slide). The next screen's name is kept in the
list node (+0x14 hub, +0x10 chooser). How the queued command makes the manager create it from the registry is U.
Path order in the chooser: engine 2, transmission 6, tires 7, ECU 5, turbo 3, brakes 8, weight 0, suspension 1, nitrous 4 (V G 0x509dd0).

## 2. Part list (GaragePartsBrowser ctor 0x507540, V G + C)

- Category table 0x706530 (stride 0x1c: id, thumb hash, name fmt, 0, **part type byte** at +0x10, 0, generic car hash at +0x18).
  D: 0 front bumper type 1, 1 rear bumper 2, 2 skirt 0xa, 3 spoiler 0xb, 4 hood 8, 5 headlight 0xd, 6 brakelight 0xe,
  7 wheel kit 0x11, 8 roof 7, 9 window tint 0x73, 10 neon 0x74, 0xc muffler tip (special path, type 5/0xf).
- Loop: `0x57ce10(carHash=[0x735720], type, 0, prev, -1)` walks the CarPart db (0x30-byte records: +4 car hash, +0x10 type, +0x11 level).
  A second loop repeats with the generic hash (table +0x18) so shared parts appear. V (G)
- Lock flags per level 0..4 are stored at screen+0x88..0x98: true when cheat [0x735ec1], career-beaten [0x7677ac],
  unlock record `0x59e5c0` (records at [0x737668]), or `0x5a1550(career, 0x5a03d0(type))` with edi = level. V (C 0x5077f6..0x50792x)
- Filters: level 4 parts need tier 4 plus a bought part (0x5a3570); NOHATCHBACK spoilers are hidden for cars 0, 1, 5; in mode 2
  levels > 1 show only if an unlock record is owned; in mode 0/2 a level > 1 part is dropped unless bought. V (G)
- Each kept part becomes a list node by 0x507280(part, thumb hash, lock flag of its level). V (G)
- `0x507e10` IsPartLocked: false when cheat [0x735ec1] / [0x735728] or part null; else locked iff flag[level] == 0. V (G)
- Paint check `0x4d7eb0` -> `0x5a1550` and owned check `0x4d8180` are the same idea for colours (see docs/re/tuning.md section 4). V (H names file)
- `0x5a1550(career, id)` with edi = level: scans events 0..255 for a reward {type 0, value id, arg level} and returns "that event status == 2".
  Any cheat flag [0x73494c] / [0x735ec1] returns 1. V (G). D: 67 type-0 rewards, e.g. event 6 -> ids 0x12,0x13,0x14 level 1 (engine, transmission, tires);
  event 12 -> id 1 level 2; event 111 -> id 0xf level 4.

## 3. Price, cash, rating

Visual cost (record = [0x733f78+4*0x5a03d0(part.type)], level 1..3 -> +4/+8/+0xc; V C 0x5a08f0). 0x5a03d0 type map (V G):
1->9, 2->0xb, 6->0xf, 7->0xd, 8->0xc, 0xa->5, 0xb->8, 0xd->6, 0xe->0xa, 0xf->2, 0x11->3, 0x1e and 0x25..0x39->0, 0x1f..0x22->7, 0x3a->1, 0x73->4, 0x74->0xe, other -> -1 (free).
Costs L1/L2/L3 (D FrontB): 0 paint+decal zones 300/600/900; 1 sponsor logo 100/200/300; 2 muffler tip 100/200/300; 3 rims 400/800/1200;
4 tint 100/200/300; 5 skirt 400/800/1200; 6 headlight 0/0/600; 7 vinyl 300/600/900; 8 spoiler 300/600/900; 9 front bumper 500/1000/1500;
0xa taillight 0/0/600; 0xb rear bumper 500/1000/1500; 0xc hood 300/600/900; 0xd roof 0/400/600; 0xe neon 200/400/600; 0xf 0/0/0.
Perf cost by path (type = 0x10+, D): weight 750/1500/3000, suspension 750/1500/3000, engine 500/1000/2000, turbo 1000/2000/4000,
nitrous 750/1500/3000, ECU 1000/2000/4000, transmission 500/1000/2000, tires 500/1000/2000, brakes 1000/2000/4000.
Perf price function is 0x5a08b0 (eax = type, ecx = level; V C), used by 0x50ab90 and the tuner heading 0x50ada0.

Show: 0x507ec0 (parts RedrawHeading) calls 0x5a08f0 and prints "%d" ([0x6ca778]) to FE object 0x82d80bc when price != 0, [0x777b4c] == 1,
no cheat, [0x7677ac] == 0 and the part is not bought (0x5a3570 == 0). V (C 0x508238..0x508298)
Cash text: GarageMainScreen::Update 0x4b0340 prints "%d" with [0x76026c] (1e9 if cheat [0x73494c] / [0x735ec1] / [0x73440c]) to FE object 0x29566d7;
SetRideInfo 0x4b0e50 prints "Cash: %d" to 0x13c45e. V (G/C)
Compare: `0x508510` CanPlayerPurchasePart (mode 1 only): not locked, then `cash(0x5a1520) >= price(0x5a08f0)` signed, skipped if cheat [0x73440c]. V (C)
Perf compare: `0x50ab90`: same with 0x5a08b0. V (G)
Flow in the parts browser (accept 0xc407210, V G/C): IsPartLocked -> deny sound; `0x508560` IsInstalling (already installed -> message);
`0x508620` IsBuying: not bought and mode 1 -> CanPurchase, else "GenericOKDialog" (can't afford, hash 0x2c0344a3); then GenericDialog confirm.
"Yes" (0x2f6484d0) -> `0x5a2620` (mode 1 only) -> `0x5044b0`. V (C 0x508a04..0x508a1c).
Deduct: `0x5a2620(part)`: cash -= price, spent += price, then `0x5a34d0(career+0x44c)` = bought table. `0x5a25a0(path, level)`: same for perf, then `0x5a34a0`
(not for types 5 or 8). `0x5a2540` is the car purchase (CarTypeInfo+0xc7c). V (G)
Bought table (career+0x44c = 0x75f344; object with vtable first, per type 0x90 bytes of u32 keys). Key: rims = NAME attribute (0x4bbd70);
types 5,6,8,9,0xa,0xb,0xc,0xd,0xf = (level<<16 | sub-index<<8 | type); else the part name hash; perf = the level. HasBought `0x5a3570`: cheat -> 1, level 0 -> 1. V (G)

Rating 0x5a05b0 (edi = RideInfo; V C/G): table 0x6ee3d8 = 16 rows {price type, ride slot, flags} (D), flags bit 1/2/4 add the type's
points at +0x10/+0x14/+0x18 to totals A/B/C (each part's own level picks +0x10..+0x1c for the score S). Type 7 uses the max level of slots 31..34, type 1
uses slots 0x3b..0x70. Result: S<A -> 2S/A; A..B -> 2..4; B..C -> 4..5; cap 5.0 ([0x6cc954]). It never reads perf points (+0x1c of rows 16..24 is unused here, I).
Callers: GarageMainScreen::Update 0x4b0340 stores it at screen+0x78 (committed ride B 0x745720) and +0x7c (preview ride A 0x745000) when [0x745e40] != 0
(V C 0x4b0665..0x4b0696); `0x4b0fd0` (named DisplayReputation by the PS2 map) reads both and flashes 5 star objects
between them (V C reads, 5-star loops V G; star meaning I); `0x51b060` (magazine task check, rating >= 1.0 -> task flag); `0x4b5df0` stores it in a local at race start (no later read, V G).
`0x4b4380` MatchCarPerformance uses ride+0x424/+0x428 (speed class), not this rating. V (G)

## 4. Purchase effects

Garage object at 0x744ff0 (V C 0x504450/0x5044b0/0x504990): +8 FECarConfig*, +0x10 ride A (preview), +0x72c preview part,
+0x730 ride B (committed), +0xe50 mode. RideInfo: +0 car type, +8 spec (level[11], junkman[11]), +0x60 physics,
+0x44c CarPart*[0x78], +0x62c dirty counter byte[0x78]. FECarConfig: [0]=1 valid, +8 car hash, +0x10 part type byte[0x78],
+0x88 car-type index[0x78], +0x100 name hash[0x78], +0x2e0 spec (0x16 dwords). V (G 0x4ac5a0/0x4ac750, D asas0.ugd)

`0x5044b0` InstallPart(this=eax, slot=ebx, part): 1. [+0x72c]=0. 2. BuildRide(cfg, B) rebuilds B from the saved config (drops any preview).
3. B.part[slot]=part, B.counter[slot]++. 4. 0x57ea80(B) (parts enabled update, I). 5. FillFromRide 0x4ac750(cfg, B) writes slots and spec back into the config:
this is the persistent change. 6. A=B. 7. B -> 0x748850, [0x72cc80]=2, SetRideInfo(screen, 0x748850, 2). 8. 0x51b060. No cash here. V (C)
Slot for a part is its type byte ([0x508a10] movsx part+0x10). 0x5086a0 / 0x508910 call it with NULL 16 / 8 times to clear slots (conflicts such as wide body; I).

`0x5047d0` InstallPhysicsUpgrade(path=eax, level=ecx, this=edx) (V C): cfg[+0x2e0+4*path] = level. Brakes (path 8): part = 0x504550(level)
(type 0x10, "BRAKES" hash, level byte == level) and InstallPart slot 0x10. Then BuildRide(cfg, B) (its end calls RebuildPhysicsInfo 0x57f2b0, so physics uses the new level),
engine-bay part B.part[12] = 0x504630(type 0xc, level of path 2) when found, counter++, 0x57ea80, RebuildPhysicsInfo(B), A=B, push to screen, 0x51aed0 (magazine task for all-levels).
It does **not** call FillFromRide, so the engine-bay part (slot 12) is not written to the config (V by reading; effect after reload U).
Physics effect itself is in docs/re/tuning.md (spec level -> table rows in 0x57f2b0).

## 5. Preview and cancel

- `0x504450` PreviewPart(slot=eax, part=ecx, this=edx): [+0x72c]=part, A.part[slot]=part, A.counter[slot]++, 0x57ea80(A), copy A -> 0x748850, [0x72cc80]=2, SetRideInfo. Config and B untouched. Callers: 0x507ec0 (when the list highlight moves), 0x5046d0, 0x5083c0, others. V (C)
- `0x5046d0` PreviewPhysicsUpgrade(level=eax, path=ecx): A.spec[path]=level; path 8 previews the brake part (slot 0x10), path 2 previews the engine-bay part (slot 0xc);
  then RebuildPhysicsInfo(A) and SetRideInfo, so the stat bars (0x4aff90 uses GetAccel/TopSpeed/Handling ratings 0x5802c0/0x5801b0/0x580400) move before buying. V (C, G)
- `0x4b0e50` SetRideInfo(screen, ride, reason): `0x4af0e0` copies the ride into the GarageCarLoader (loader+0x10), RebuildPhysicsInfo, sets request flag +0x1c9c; sets CAR_NAME text and "Cash: %d" (mode [0x777b4c]==1). V (G)
- The loader (0x4af140 state machine, 4 RideInfo slots at +0x10/+0x730/+0xe50/+0x1570) queues the real model load; `0x4b0340` waits until it is ready, then calls
  FrontEndRenderingCar::ReInit 0x56a040(loader+0x1570) for screen+0x40 / +0x44 (the FrontEndRenderingCar objects made by ctor 0x569c50, caller 0x4af620). V (G)
- Cancel: `0x504890` SyncActualToEditing: A=B, B -> 0x748850, SetRideInfo. Called on back in the parts browser (0x508de6), tuner and brand screens (0x50b31c, 0x50bc5a) and hub (0x505330 msg 0xaabbccdd). V (C)

## 6. Save

- The garage writes the career object in memory only (config at 0x75eef8, bought table 0x75f344, cash/spent). V (G)
- `0x4ab120(buffer, 0xf660)` serializes the frontend DB (0x7588c4): [u32 0][u32 db+0x210][db+0x364, 0x18b4 dwords][db+0x6634, 0x88b4 bytes = career at 0x75eef8][...]. `0x41d8a0` writes
  `<profile><n>.ugd` = u32 version 0x13, 0x12 name, 0x19 date/time, the 0xf660 blob, u32 checksum 0x41dd10 (file size 63123 = 4+18+25+63072+4, D). V (G, D)
- D check on save/asas0.ugd: career at blob+0x62d8 has cfg[0]=1, car hash +8, type bytes 1..25,30,119 at +0x10, spec zeros at +0x2e0, spent 20500 at +0x137c. The three saves have no bought parts (only the vtable word). V
- Autosave: hub back message 0x911ab364 (0x505330) calls `0x4c9570` (compares the garage-entry snapshot [0x735e38], taken in the hub ctor 0x504be0, with a fresh 0xf660 serialization); if changed -> `0x4c96f0(msg,1)` -> `0x41d8a0(&0x78a478,"auto")` + `0x41c7a0` (.cfg). V (G)
- Reload: the profile load is the inverse of 0x4ab120; BuildRide 0x4ac5a0 rebuilds the ride from cfg. Not read here. savegate.py only checks event status bytes. NOT VERIFIED for parts.

## 7. Open items 3, 4, 7 answered by reading (night-opus-a2, sonnet-exec; no run)

- **Reload (7).** Profile load `0x41da40` → `0x4ab200` (V G+C) is the exact inverse of the writer `0x4ab120`.
  - It checks version 0x13 and the checksum `0x41dd10`.
  - It copies the 0x88b4-byte career block back to `0x75eef8` with `rep movsd`, then restores `[0x7677ac]`.
  - The FECarConfig is career+0: type bytes +0x10, car index +0x88, name hashes +0x100, spec +0x2e0. It returns
    byte for byte.
  - BuildRide `0x4ac5a0` rebuilds the ride only from that config.
  - So bought parts and perf levels survive a reload. V (code); there was no run.
- **Engine-bay part (3).** Slot 12 (ride+0x47c, type 0xc) is set only by `0x5047d0`, `0x5046d0` and, at race start,
  `0x422410`/`0x57d860`. BuildRide never derives it from spec level[2]. The save bytes agree:
  `save/asas_autosave.ugd` has engine level 3 and an empty slot 12. So the engine-bay visual is missing in the garage
  after a reload and comes back in a race. Code and bytes are V; what the screen shows is I until a run.
- **Negative cash (4).** The spend writers `0x5a2620`, `0x5a25a0`, `0x5a2540` (car) and `0x4c3730` subtract with no
  check of their own. The check is in the UI, which reads cash through `0x5a1520`. That function returns 1e9 when any
  of `[0x735ec1]`, `[0x73494c]`, `[0x73440c]` is set. No retail code writes those flags. **Our patch
  `0x735ec1 = 1` (`tools/recomp/patches.py:71`, OWNER 2026-10-20 "everything available") turns the check off, so
  purchases drive cash below zero.** That is the most likely source of the −9,875 in `save/asas0.ugd`
  (earned 10,625, spent 20,500). I (strong). `[0x7677ac]` and the mode `[0x745e40]` do not touch cash. Event entry
  fees are all 0 (D). `0x4c8720` and `0x4e6390` were not read for their own check (U).

## Functions

| addr | name | mark | tool | evidence |
|---|---|---|---|---|
| 0x504990 | GarageManager::Init(mode, fng) | V | G,C | sets [0x744ff8]=cfg, [0x745e40]=mode, builds rides 0x745000/0x745720 |
| 0x504450 | GarageManager::PreviewPart | V | C | writes A.part[slot], SetRideInfo |
| 0x5044b0 | GarageManager::InstallPart | V | C,G | BuildRide(B), set slot, FillFromRide(cfg), A=B |
| 0x5046d0 | PreviewPhysicsUpgrade | V | C | A.spec[path]=level, rebuild A |
| 0x5047d0 | InstallPhysicsUpgrade | V | C | cfg+0x2e0+4*path=level |
| 0x504890 | SyncActualToEditing | V | C | A=B, push to screen |
| 0x504550 | GetBrakeForPerfUpgrade | V | G | part type 0x10 "BRAKES" with level |
| 0x504630 | FindPartOfTypeAndLevel | V | G | engine-bay part type 0xc by level |
| 0x504320 / 0x504390 | PushScreen / PopScreen | V | H | list node + depth message 0x504260 |
| 0x504be0 | GarageScreen ctor (MU_Garage) | V | G | BROWSER_* entries, snapshot [0x735e38] |
| 0x505330 | GarageScreen::NotificationMessage | V | G | back -> 0x4c9570 -> autosave |
| 0x509dd0 | ChooseGaragePerfPath ctor | V | G | 9x 0x50a070 |
| 0x50a070 | ChooseGaragePerfPath::AddCategory | V | G | node {path, label hash, fng}, lock byte via 0x5a4370 |
| 0x509d70 | IsPerformanceUpgradeLocked | V | G | cheat, 0x59e5f0, 0x5a1550(0x5a0350(path)) |
| 0x50a5d0 | GaragePerfTuner ctor | V | G | 4 level entries, first preview 0x5046d0 |
| 0x50b2d0 | GaragePerfTuner::NotificationMessage | V | C | accept / back / scroll / 0xf0aadebb -> 0x5047d0 |
| 0x50ab90 | CanAffordUpgrade | V | G | 0x5a08b0 vs 0x5a1520 |
| 0x50b6e0 / 0x50bc10 | PerfBrandPackage ctor / handler | V | C | yes: 0x5a25a0 then 0x5047d0 |
| 0x507540 | GaragePartsBrowser ctor | V | G | category table 0x706530, 0x57ce10 loop |
| 0x507e10 | IsPartLocked | V | G | flag[level] at screen+0x88 |
| 0x508510 | CanPlayerPurchasePart | V | C | cash >= price in mode 1 |
| 0x508560 / 0x508620 | IsInstalling / IsBuying | V | G | dialogs, bought check |
| 0x5089b0 | PartsBrowser::NotificationMessage | V | C | 0x2f6484d0 -> 0x5a2620 + 0x5044b0 |
| 0x507ec0 | PartsBrowser::RedrawHeading | V | C | price "%d" to 0x82d80bc |
| 0x5a03d0 | PartTypeToPriceType | V | G | switch, -1 = free |
| 0x5a0350 | PerfPathToUpgradeId | V | G | 0..8 -> 0x10,0x15,0x12,0x16,0x18,0x17,0x13,0x14,0x11 |
| 0x5a08f0 | PartPrice | V | C | record[type].cost[level-1] |
| 0x5a08b0 | PerfPrice | V | C | same for perf |
| 0x5a1520 | GetCash | V | C | career+0x1374, 1e9 with cheats |
| 0x5a1550 | IsUpgradeUnlocked | V | G | reward {0, id, level} event won |
| 0x5a2620 | BuyPart | V | G | cash/spent, 0x5a34d0 |
| 0x5a25a0 | BuyPerfUpgrade | V | C | cash/spent, 0x5a34a0 |
| 0x5a2540 | BuyCar | V | G | CarTypeInfo+0xc7c |
| 0x5a34a0 / 0x5a34d0 / 0x5a3570 | bought table add (perf / part) / HasBought | V | G | career+0x44c, 0x90 per type |
| 0x5a0100 | LoadPriceTables | V | brief+D | chunk 0x34a01 -> [0x733f78+4*type] |
| 0x5a05b0 | CarStarRating (0..5) | V | C | table 0x6ee3d8, points +0x10..+0x1c |
| 0x4b0fd0 | GarageMainScreen::DisplayReputation (stars) | I | C,G | reads screen+0x78/+0x7c, 5-star loops |
| 0x4b0340 | GarageMainScreen::Update | V | G,C | rating store, cash text, ReInit when loaded |
| 0x4b0e50 | GarageMainScreen::SetRideInfo | V | G | 0x4af0e0, "Cash: %d" |
| 0x4af0e0 / 0x4af140 | GarageCarLoader::LoadRideInfo / Update | V | G | loader+0x10, flags 0x1c9c.. |
| 0x569c50 / 0x56a040 | FrontEndRenderingCar ctor / ReInit | V | G | caller 0x4af620 / Update |
| 0x4ac5a0 / 0x4ac750 | FECarConfig::BuildRide / FillFromRide | V | G | cfg+0x10/+0x88/+0x100/+0x2e0 |
| 0x4c9570 | HasProfileChanged | V | G | compares [0x735e38] with fresh 0xf660 blob |
| 0x4ab120 | cFrontendDatabase::Serialize | V | G | copies db+0x364 and db+0x6634 (career) |
| 0x41d8a0 / 0x4c96f0 | WriteUGD / Autosave | V | G | header 0x13, blob 0xf660, "auto" |
| 0x6f94d8.. | screen registry (name, factory) | V | C,D | stride 0x14 |

## Open (U)

1. How the queued command (0x4f0800, vtable 0x6c2c64) turns the chosen node into the next screen from the registry.
2. Meaning of [0x745e40] = 0 (0x504a20 caller 0x4e8580) and the exact difference of [0x745e40]==1 vs [0x777b4c]==1.
3. Engine-bay visual (slot 12) after reload: 0x5047d0 never calls FillFromRide. Needs a run: buy engine L2, reload, look at cfg+0x10+12.
4. Price after career beaten: label is hidden when [0x7677ac] != 0, but 0x5a2620 / 0x508510 do not test that flag. Does cash go negative? (asas0.ugd cash -9875 is unexplained).
5. Who reads the rating beyond the stars (0x4b5df0 and 0x4c5f20 keep it in a local; no reader seen). Perf points (+0x1c of rows 16..24) have no reader found.
6. GaragePerfBrandPackage: what "brand" changes (cosmetic or data), and 0x5a4480/0x5a4370 (career forces a level from the current event reward) beyond the lock byte.
7. Profile load for the career block (inverse of 0x4ab120) and a run showing a bought part survives reload. NOT VERIFIED.
8. Paint (0x50c0f0), decals (0x511ff0) and vinyl purchase paths: same pattern assumed (0x5a2620 callers 0x4e6390, 0x50e340, 0x50f780, 0x4c8720), not read.
