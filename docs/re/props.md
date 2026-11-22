# Props: smackable street objects (Speed.exe PC)

Marks: V = verified (two tools agree, or code + file bytes), I = inferred, U = open. Tools: H = Hopper export,
G = Ghidra export, C = capstone, F = game files ([census/openworld_props.json](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/census/openworld_props.json), built from the TRACKB chunks).
Prior notes in Spanish: `re_props` (this doc re-checks them and corrects two numbers).

## Answer
- A prop is smackable when a placed object of the base stream (`0x34103` row in STREAML1RA.BUN) has an instance row
  (`0x34027`, 0x70 bytes, TRACKB) whose class key exists in the class table (`0x34026`, 77 rows of 0x100). Everything
  else is static scenery (V F + H+G for the loader `0x5952a0`).
- 77 classes, identical in the 16 street tracks; 33 are placed, 44 unused. 4,580 instance rows, 1,122 unique
  positions (V F). Class = name, rigid-body params (mass +0x20, inertia, centre of mass +0xb0), release limit +0xc4,
  durability +0xc8, life +0xc0, surface +0xd4 and smack type +0xdc (16 types: cones, signs, drums, fences...).
- Life cycle: every instance starts as a cheap "Virgin" (`0x5962e0`, pool `VirginSmokeableSlotPool`); on contact
  the broadphase turns it into a full "Smokeable" rigid body (`0x596570`, 32-slot pool); hit `0x597980` decides
  absorb or release. A settled smokeable becomes a Virgin again in its original place after 2.0 s (respawn), or is
  removed after its class life time if it has one (`0x5977f0`). V (H+G).
- Reset: `0x595bf0` frees and rebuilds both pools at track load; `0x595d80` makes the Virgins; saved/restored per
  slot by `0x595f70`/`0x596f50` (index 0xffff = none). V (H+G for `0x595bf0`, `0x595f70`, `0x596f50`; G+C for `0x595d80`).

## Data (chunks in TRACKB<id>.lzc, loader index 29 of the table at `0x7007e0` = `0x5952a0` (an earlier draft said "loader 3", wrong; index 3 is `0x442040`; external audit 2026-10-29) -> array `0x734470`, count `0x734474`)
Instance `0x34027` (0x70): +0 class key, +4 s16 section id, +6 s16 placement index in the section, +8 model hash,
+0xc runtime Virgin pointer, +0x10/+0x20 AABB min/max, +0x30 4x4 world matrix, +0x60 translation (= placement
position, error < 0.01 over 4,580). V F.
Class `0x34026` (0x100): +0/+4 runtime links (list `0x737778`), +8 name[24], +0x20 rigid-body block (mass ->
body+0x144, 1/mass -> +0x148 in `0x584b10`, V H+G), +0x80 key (first duplicate wins), +0x84/+0x88 emitter keys,
+0x8c child count (0 in all PC data), +0xb0 centre of mass, +0xc0 life seconds, +0xc4 release limit (-> body+0x15c),
+0xc8 durability (-> +0x160), +0xd4/+0xd0 surface hash/index (29-row table `0x6ef2d0`), +0xdc/+0xd8 smack type
hash/index (17 names at `0x6ef240`). V F + G.
Collision shapes: TRACKB `0x80034020` -> `0x39200/1/2` triples (88 shapes; all 77 classes have one, 11 extra are
vehicles), found by key through `0x472c60`; no shape -> default box +-1.5 (`0x473cf0`). V H+G (`0x472c60`).

## Life cycle in detail
1. `0x595bf0` (from `0x41f6e0`): pools Virgin (max(count,1) x 0x68, `0x734464`) and Smokeable (32 x 0x4d0,
   `0x734468`); factory `0x73168c = 0x595230`. V H+G (0x4d0 in both).
2. `0x595d80`: per instance, find the class by key; unless excluded by `0x595b70` (only event 0x4b1 with
   XO_CONSTRUCSIGNA, V H+G), build a Virgin `0x5962e0`: stores instance (+0x60) and class (+0x64), writes inst+0xc,
   clears bit 0x10 of the placement flags (= visible), registers the AABB (`0x468680`). Dtor `0x5964c0` sets it again.
3. `0x445b00` (section loader `0x4457c0`): placement bit 0x10 set when the instance has no Virgin, so a class-less
   instance hides its placement (21 rows: XO_STOPSIGNA, XT_BUSHA). I (render mask not traced).
4. Contact: `0x469580` (from `0x420380`) -> `0x469670`: car AABB vs object AABB, ignore matrix, slot-0x14 predicate
   `0x5927d0` (`byte [this+0x1b]==0`, C), object type 2 = Virgin -> `0x596570` builds the Smokeable if the active pool
   is not full (else no smack). V H+G for `0x469580`, `0x596570`.
5. Hit `0x597980` (vtable slot 18): release limit 0 -> released at once (`0x597c90`, flag +0x4c2); else impulse below
   the limit is absorbed. V H+G (0x4c2 in both). 8 of the 33 placed classes have a limit > 0: CS_STREETSIGN_B,
   ZCS_BridgeGateB, ZCS_BusSignPostA, ZCS_Chevrons, ZCS_GardenGate, ZCS_GateKnockA, ZCS_ParkgateA, ZCS_WaterBarrel
   (V F; the earlier note said only CS_STREETSIGN_B).
6. Update `0x597420`; respawn/expire `0x5977f0` (G read): if the instance link +0x170 is set, the body is at rest
   (+0x168 = 0 or 0x7fffffff), byte +0x1a = 0 and more than 2.0 s (`0x6ccc00`) passed since +0x164 (clock `0x73ad34`
   x 0.00025 s), it rebuilds a Virgin from the instance and deletes itself; else if a timer +0x168 runs and class
   life +0xc0 != 0 and has passed, it kills the object (vtable +0x7c). V H+G (same callees, 0x7fffffff).
   Byte +0x1a meaning (on screen?) U.
7. Pool cleanup `0x595670`/`0x595750`: forced when fewer than 4 slots are free, else every 128 frames
   (0x8000007f mask). V H+G.

## Classes (V F from [census/openworld_props.json](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/census/openworld_props.json); roles by name = I)
| # | class | smack type | surface | mass | release limit | life s | rows | unique |
|---|---|---|---|---|---|---|---|---|
| 0 | CS_AFrame | SAW_HORSE | WOOD | 0.5 | 0.4 | 0 | 0 | 0 |
| 1 | CS_BBoardA_Lg | ROAD_SIGN_WOOD | WOOD | 0.05 | 0.05 | 0 | 0 | 0 |
| 2 | CS_BBoardA_Sm | ROAD_SIGN_WOOD | WOOD | 0.05 | 0.05 | 0 | 0 | 0 |
| 3 | CS_BREAKAWAY_PLANK | WOODBOX | WOOD | 0.05 | 0.05 | 0 | 0 | 0 |
| 4 | CS_BarrelA_L | WOODBOX | WOOD | 0.5 | 0.4 | 0 | 0 | 0 |
| 5 | CS_BoxWood_01 | WOODBOX | WOOD | 0.5 | 0.4 | 0 | 0 | 0 |
| 6 | CS_DANGERSIGN_00 | ROAD_SIGN_WOOD | WOOD | 0.005 | 0.3 | 0 | 0 | 0 |
| 7 | CS_GasPump | METAL_BIG | METAL | 2 | 3 | 0 | 0 | 0 |
| 8 | CS_LADDER_1_00 | METAL_BIG | METAL | 0.85 | 0.4 | 0 | 0 | 0 |
| 9 | CS_LitepostA | METAL_BIG | POST | 0.5 | 4 | 0 | 0 | 0 |
| 10 | CS_Mail_Garbage | METAL_BIG | METAL | 0.65 | 0.6 | 0 | 0 | 0 |
| 11 | CS_Metalcontainer_e1_01 | METAL_BIG | METAL | 0.5 | 0.4 | 0 | 0 | 0 |
| 12 | CS_STREETSIGN_A | ROAD_SIGN_METAL | METAL | 0.005 | 0.2 | 0 | 0 | 0 |
| 13 | CS_STREETSIGN_B | ROAD_SIGN_METAL | METAL | 0.005 | 0.2 | 0 | 767 | 175 |
| 14 | CS_STREETSIGN_B (dup) | NONE | POST | 0.005 | 0.2 | 0 | 0 |  |
| 15 | CS_STREETSIGN_C | ROAD_SIGN_METAL | METAL | 0.005 | 0.2 | 0 | 0 | 0 |
| 16 | CS_Sharpturn_A | ROAD_SIGN_WOOD | WOOD | 0.005 | 0.3 | 0 | 0 | 0 |
| 17 | CS_StopBar | ROAD_SIGN_WOOD | WOOD | 0.5 | 0.4 | 0 | 0 | 0 |
| 18 | CS_StopBar_bad | METAL_SMALL | METAL | 0.5 | 0.4 | 0 | 0 | 0 |
| 19 | CS_StopBarx | METAL_BIG | METAL | 0.5 | 0.4 | 0 | 0 | 0 |
| 20 | CS_StopSign | ROAD_SIGN_METAL | METAL | 0.2 | 0.2 | 0 | 0 | 0 |
| 21 | CS_StripeBarrier | TRAFFIC_CONE | PLASTIC | 0.85 | 0.4 | 0 | 0 | 0 |
| 22 | ZCS_BarrelFireA | OIL_DRUM | METAL | 0.1 | 0 | 7 | 0 | 0 |
| 23 | ZCS_Barrel_FireA | OIL_DRUM | METAL | 0.05 | 0.01 | 7 | 0 | 0 |
| 24 | ZCS_BenchB | MARKET_STALL | WOOD | 0.2 | 0 | 0 | 0 | 0 |
| 25 | ZCS_BoxWhseA | METAL_BIG | WOOD | 0.5 | 0 | 0 | 0 | 0 |
| 26 | ZCS_BoxesWHse | WOODBOX | WOOD | 0.5 | 0 | 0 | 2 | 1 |
| 27 | ZCS_BridgeBarrierA | METAL_SMALL | METAL | 0.0001 | 0.1 | 0 | 0 | 0 |
| 28 | ZCS_BridgeGateA | SAW_HORSE | WOOD | 0.0001 | 0 | 0 | 8 | 4 |
| 29 | ZCS_BridgeGateB | METAL_SMALL | METAL | 0.08 | 0.1 | 0 | 24 | 8 |
| 30 | ZCS_BusSignPostA | ROAD_SIGN_METAL | POST | 0.2 | 0.2 | 0 | 41 | 7 |
| 31 | ZCS_CardboardBoxA | WOODBOX | WOOD | 0.03 | 0 | 0 | 52 | 32 |
| 32 | ZCS_CardboardBoxB | WOODBOX | WOOD | 0.03 | 0 | 0 | 86 | 41 |
| 33 | ZCS_Chair | METAL_SMALL | METAL | 0.1 | 0 | 0 | 0 | 0 |
| 34 | ZCS_Chevrons | ROAD_SIGN_WOOD | WOOD | 0.01 | 0.05 | 0 | 231 | 51 |
| 35 | ZCS_ConstrucSignA | ROAD_SIGN_WOOD | WOOD | 0.01 | 0 | 0 | 109 | 18 |
| 36 | ZCS_GarbageBagA | GARBAGE_BAG | PLASTIC | 0.04 | 0 | 0 | 300 | 76 |
| 37 | ZCS_GarbageBin | METAL_BIG | METAL | 5 | 0 | 0 | 0 | 0 |
| 38 | ZCS_GarbageCanA | TRASHCAN | METAL | 0.2 | 0 | 0 | 79 | 31 |
| 39 | ZCS_GardenGate | SANDWICH_BOARD | WOOD | 0.15 | 0.2 | 0 | 12 | 4 |
| 40 | ZCS_GateKnockA | METAL_BIG | METAL | 0.15 | 0.1 | 0 | 6 | 2 |
| 41 | ZCS_HOTBOXA | WOODBOX | WOOD | 0.03 | 0 | 0 | 0 | 0 |
| 42 | ZCS_LadderA | ROAD_SIGN_WOOD | WOOD | 0.05 | 0 | 0 | 4 | 2 |
| 43 | ZCS_LuggageCart | METAL_BIG | METAL | 0.4 | 0.1 | 0 | 0 | 0 |
| 44 | ZCS_OilBarrel | OIL_DRUM | METAL | 1 | 0 | 0 | 174 | 48 |
| 45 | ZCS_OilBarrel (dup) | OIL_DRUM | METAL | 0.1 | 0 | 0 | 0 |  |
| 46 | ZCS_Oil_Link_Fence_GateA | METAL_FENCE | METAL | 0.1 | 0 | 0 | 12 | 3 |
| 47 | ZCS_OrangeBumper | TRAFFIC_CONE | PLASTIC | 0.2 | 0 | 0 | 139 | 21 |
| 48 | ZCS_ParkBenchD | METAL_SMALL | METAL | 0.3 | 0 | 0 | 18 | 3 |
| 49 | ZCS_ParkgateA | METAL_FENCE | METAL | 0.1 | 0.1 | 0 | 14 | 6 |
| 50 | ZCS_PedstrnGateA | METAL_FENCE | METAL | 0.3 | 0 | 0 | 48 | 14 |
| 51 | ZCS_PylonA | TRAFFIC_CONE | PLASTIC | 0.05 | 0 | 0 | 86 | 25 |
| 52 | ZCS_PylonA (dup) | TRAFFIC_CONE | PLASTIC | 0.1 | 0 | 0 | 0 |  |
| 53 | ZCS_RWPilonA | TRAFFIC_CONE | PLASTIC | 0.185 | 0 | 0 | 522 | 90 |
| 54 | ZCS_RoadBarrierB | ROAD_SIGN_WOOD | WOOD | 0.06 | 0 | 0 | 444 | 98 |
| 55 | ZCS_RoadsignA | ROAD_SIGN_WOOD | WOOD | 0.06 | 0 | 0 | 126 | 29 |
| 56 | ZCS_SaleboardA | SAW_HORSE | WOOD | 0.05 | 0 | 0 | 26 | 13 |
| 57 | ZCS_Shopping_Cart | SHOPPING_CART | CHAINLINK | 1 | 0 | 0 | 0 | 0 |
| 58 | ZCS_Shopping_CartA | SHOPPING_CART | METAL | 0.05 | 0 | 0 | 42 | 15 |
| 59 | ZCS_SignNoParkingA | ROAD_SIGN_METAL | METAL | 0.2 | 0 | 0 | 911 | 187 |
| 60 | ZCS_SmokeGate2 | ROAD_SIGN_METAL | METAL | 0.1 | 0 | 0 | 0 | 0 |
| 61 | ZCS_SmokeGate3 | ROAD_SIGN_METAL | METAL | 0.1 | 0 | 0 | 0 | 0 |
| 62 | ZCS_SprayPaint | METAL_SMALL | METAL | 0.2 | 0 | 0 | 0 | 0 |
| 63 | ZCS_SubwayDrEntA | METAL_SMALL | METAL_GRATE | 0.2 | 0 | 0 | 3 | 2 |
| 64 | ZCS_SubwayDrEntB | METAL_SMALL | METAL_GRATE | 0.2 | 0 | 0 | 2 | 2 |
| 65 | ZCS_SubwaySDdoorAB | METAL_SMALL | METAL_GRATE | 0.2 | 0 | 0 | 4 | 4 |
| 66 | ZCS_SuitcaseA | TRAFFIC_CONE | PLASTIC | 0.1 | 0 | 0 | 0 | 0 |
| 67 | ZCS_SuitcaseB | TRAFFIC_CONE | PLASTIC | 0.1 | 0 | 0 | 0 | 0 |
| 68 | ZCS_SuitcaseC | TRAFFIC_CONE | PLASTIC | 0.1 | 0 | 0 | 0 | 0 |
| 69 | ZCS_SuitcaseD | TRAFFIC_CONE | PLASTIC | 0.1 | 0 | 0 | 0 | 0 |
| 70 | ZCS_Table | METAL_SMALL | METAL | 0.1 | 0 | 0 | 0 | 0 |
| 71 | ZCS_Tire | TRAFFIC_CONE | PLASTIC | 0.0001 | 0 | 0 | 0 | 0 |
| 72 | ZCS_Tire (dup) | TRAFFIC_CONE | PLASTIC | 0.85 | 0.4 | 0 | 0 |  |
| 73 | ZCS_TrafficCone | TRAFFIC_CONE | PLASTIC | 0.05 | 0 | 0 | 0 | 0 |
| 74 | ZCS_WaterBarrel | WATER_DRUM | PLASTIC | 0.1 | 0.1 | 0 | 223 | 90 |
| 75 | ZCS_WoodePlank | ROAD_SIGN_WOOD | WOOD | 0.06 | 0 | 0 | 24 | 6 |
| 76 | ZCS_WoodePlankB | ROAD_SIGN_WOOD | WOOD | 0.06 | 0 | 0 | 20 | 5 |

## Second-tool agreement (10 sampled names)
H and G show the same entry and callees, and share these constants: `0x5952a0` (0x34026, 0x34027), `0x595bf0`
(0x4d0), `0x596570` (0xffff), `0x597980` (0x4c2), `0x597420` (13/14 callees), `0x5977f0` (0x7fffffff),
`0x595670` (0x8000007f), `0x595b70` (0x4b1), `0x596f50` (0x164), `0x584b10` (0x144, 0x148). 10/10 agree.
`0x595d80`, `0x445b00`, `0x469670` are not separate functions in the Hopper export (called only): G/C only.

## Open
- U: who reads the smack type index +0xd8 (FX/sound?); byte +0x1a in the respawn test; emitter lists (+0x84/+0x88
  set on 4 classes, lists empty on PC); unit of inertia; the render mask that hides class-less placements.
- Child break-up parts (`0x597e10`, `0x597d10`, "_CHILDn") exist in code but no PC class has children.
