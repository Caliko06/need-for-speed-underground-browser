# Free Run traffic placement

Question: Free Run asked for 18 traffic cars, the race had 9 (1003) and 13 (1010). Where do they go?

## Measured (native, RN_FREELOG, host/free.c free_place = 0x598bf0 step by step, PATCH 0x422b36)
- 1003: the track table asks for 6 (i8 [0x441fe0() + side + sel * 2 + 0xc0]), x1.5 = 9, and 9 of 9 are placed. No loss;
  the "18" only holds for tracks with count 12 (1001 and the WORLD's 1010).
- 1001 / 1010: 18 asked, 13 to 14 placed (the first two by the grid slot 0x598c80, the rest by the last resort 0x598fb0).
  In Free Run 0x421a50 is false (route 0x5991a0 never runs). With 26 asked: 1001 14, 1010 13, 1003 26.
- The cars are not lost after placement (race list count = placed count), and AddTrafficCars registers all it is asked.

## Why the last resort fails (replay of its checks, 3000 tries per lost car, 1010)
The pool is `this+0xc` = 520 road nodes (the base track's network; the merged TRACKB keeps only that one).
Of 3000 random nodes: 2000 fail 0x4420a0 (node flag +0x84 bit 25), ~900 fail 0x59aa60, about 4 pass.
0x59aa60 (spacing test) fails on two rules, both from the track table [[0x736174] + side * 4 + ...]:
- +0xcc = 500 m: no car within 500 m of the player while he stands still (var_1; 0x432c90 speed <= 0);
- +0xd4 = 31 m to every car already in the race list (0x59b1e0).
Pool saturation, not a lifter or placer bug: more tries cannot help beyond ~14 cars at 500 m / 31 m.
Capacity by clear zone (26 asked, 1010, one run each): 500 m 13, 300 m 16, 200 m 18, 100 m 20, 0 m 23; zone 0 with 20 m
spacing 26.

## Fix (host/free.c free_place, only while free mode is live; RN_FREE=0 = as shipped)
- Clear zone 100 m (FREE_ZONE, RN_FREEZONE) for the placement; the table value is put back after each call.
- Last resort repeated up to 4 times (400 tries): the pool is near saturation, 100 tries lose about 1 in 10 cars.
- Count: FREE_TRAFFIC 13 (RN_FREETRAFFIC) written to the track table byte for the AddTrafficCars call and put back: x1.5 = 19.
Result (native, 5 runs: 1003, 1001, 1010 x3 seeds): 19 asked, 19 placed in every run. 21 asked: 1 lost in 4 runs; 22: 0 of 2.
19 is the safe default; the rides cap (64 entrants since PATCH 0x4322e0, `cmp [race+0x12c], 0x40`, was 30) is not the
limit, the network is. More density needs a bigger traffic network (OPENWORLD E) or a shorter spacing (+0xd4, 20 m gave
26 with zone 0).
