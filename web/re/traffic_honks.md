# Traffic: count byte, 0xcc / 0xd4 data, and who honks

> Source: `docs/re/traffic_honks.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 38

# Traffic: count byte, 0xcc / 0xd4 data, and who honks

Sources: build/hopper/trafficrow.txt + honk.txt (Hopper, complete), census/hopper/decomp.c, capstone (C). V = read in code, I = inferred, U = open. Nothing ran.

## 1. Count, 500 m zone and 31 m spacing are row data

- V count, one reader, 0x4b3b01 `movsx edx, byte [ecx+edi*2+0xc0]`, ecx = [0x78a2fc] + 0x441fe0() (row of the id in esi), edi = [0x78a300].
  PATCH 0x4b3b01 sends it to the cave count, which reads the same byte then x1.5, cap 26 (gated on [0x1301c] = RN_TRAFFIC, on by default). The byte stays live.
- V zone 0x59aac3 `mov edx, [eax+ecx*4+0xcc]`, eax = 0x42ae10() = [0x736174], ecx = [0x78a2fc]; compared to the player only while his speed <= 0 (0x432c90).
- V spacing 0x599111 `mov eax, [eax+edx*4+0xd4]`, pushed into 0x59aa60, compared per placed car at 0x59b27d / 0x59b290 (0x59b1e0).
- V per track: 0x4484f0 sets [0x736174] to the row whose +0x36 == track id; rows at [0x736168], stride 0xfc, count [0x73616c]. And no
  500.0 or 31.0 immediate in those paths, every compare uses the loaded float: data, writable, no code patch.
- V extra lever 0x59aa87 `movsx edx, byte [eax+ecx+0xc8]`: nonzero skips the zone test for that side.

## 2. WORLD 1010: row = [0x736168] + i*0xfc with row[0x36] == 1010; side = [0x78a2fc], sel = [0x78a300]

| field | address | old | new | why |
|---|---|---|---|---|
| spacing | row+side*4+0xd4 | 31.0f 0x41F80000 | 20.0f 0x41A00000 | the binding limit: 21 asked, 20 placed today |
| count | row+side+sel*2+0xc0 | 14 0x0e | 15 0x0f | 22 asked, one under the ceiling |
| zone off | row+side+0xc8 | 0 | 1 | cheapest: skips the 500 m test |
| zone | row+side*4+0xcc | 500.0f 0x43FA0000 | 100.0f 0x42C80000 | alternative to +0xc8 |

Ceilings: 26 from the count cave, 23 from 30 entrants (0x4322a0). Measured on 1010: 500 m/31 m 13-14, 100 m/31 m 20, 0 m/20 m 26. Write once per race or track load: the row outlives the race (host/free.c puts its values back after AddTrafficCars).

## 3. Who calls 0x429100

- V one caller only: 0x44c539 in 0x44c2e0 (HonkAtPlayer).
- I 0x44c2e0 is a vfunc of the AI goal machine, entered from 0x44d8c5 (also 0x44dd45): goal id at [esp+0x50] (0x13, 0xc, 0xe, 5, 1, 0) and priority (0x258 600, 0x1f4 500, 0x190 400, 0x12c 300, 0xc8 200) pick it.

## 4. A horn with no car in sight

- V gates before the arm, all on the other car, each exits: 0x44c315 (its type row +0xc54 == 1), 0x44c346 (its kind == 3), 0x44c35d (0x57a6b0 false, not the human), 0x44c395 / 0x44c3a0 (kind 3 or 4).
- V nothing else: 0x44c2e0..0x44c544 never calls 0x5693b0 (the visible test) and never reads +0x4d1 (parked). The finder 0x44ed70 is called with -1.0f (0x44d9de `push 0xbf800000`), so its distance test 0x44edab cannot reject a car: no range limit.
- V 0x429190 (every frame, from 0x426930) keys the horn on +0x844/0x848/0x84c/0x850 and +0x83f only: no distance, no visibility.
- Gate 0x44c35d fires for a car behind the camera, and for a car 0x59a2c0 moves 150-250 m right after 0x44c539 armed it: only 0x425350 clears +0x83e/0x83f/+0x840, so it sounds at the new spot for up to A+B+C ~1.85 s.
- I a parked car (+0x4d1) still updates, so it finishes the window. U whether the sound engine mutes it by distance.

Q1: data write row(1010): +0xd4 0x41F80000 -> 0x41A00000 (31 m -> 20 m), +0xc0 0x0e -> 0x0f (22 asked), or +0xc8 0 -> 1 instead of +0xcc; no code patch.
Q2: no patch; probe = cave at 0x44c539 to the host logging car, tick and distance to the player plus whether that car is drawn, so a ghost horn names its gate.
