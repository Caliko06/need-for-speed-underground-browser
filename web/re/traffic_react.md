# Why traffic ignores the player, and the smallest fix

> Source: `docs/re/traffic_react.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 64

# Why traffic ignores the player, and the smallest fix
Tools: G = Ghidra live (named project), C = capstone `tools/recomp/asm.py`. V = code read, I = inferred, U = open. Names: `census/names_traffic_w4.tsv`. Slot = 0x38-byte row of the neighbour list (ctx = car+0x2c of the AI object, own index byte ctx+0x388).

## Root cause
The traffic AI has no code that looks at a car behind it, and its one "car ahead" rule exempts the player for part of the cars.
Lights and horn are armed from the same blocked-ahead branch only. (V, G+C)

## Decision chain (V, G+C)
1. `TrafficAI::Update` 0x583350 (vtable 0x6b96b0 slot 3) updates ONE traffic car per sim step: `[0x6f08a4]` (+1 per step, 0x585e00) mod 2N,
   only odd values, car index = value/2 (N = traffic cars). Each car thinks once per 2N steps: 24 at N=12, 44 at N=22 (0.4 to 0.7 s at 60 fps).
2. In the active branch: 0x44ca70, 0x458cc0, route update 0x44cf30, which builds the neighbour list with 0x57a910 at 0x44d30e (<= 16 cars, R =
   max(50 m `[0x700680]`, vt+0x50 x speed), route delta <= 3R). The list is sorted by signed distance^2 (key x -1.0 `[0x6cc8a8]` when behind):
   index 0 farthest ahead, own-1 nearest ahead, own = the car, own+1.. behind. 0x44c940 empties it at every return, so it exists only inside an update.
3. Selector: goal vt+0x14 = 0x44e020 (goal 4, `AIGoal::Create(4)`) or 0x44e140 (goal 5), same code: if current type != 0x12 and priority < 0x259:
   Finder_ObeyIntersections 0x4543d0 (600). If type != 3 and priority < 0x12d: Finder_AvoidAsTraffic 0x453920 (300), then
   `TrafficCar_HonkAtPlayer` 0x44c2e0, then the Avoid action ctor 0x453860 (vtable 0x6c939c, update 0x453c60). Else default lane drive (type 8).
4. Finder 0x453920 calls 0x44f470(lane, lateral, range 99999.0, &out0, &out1). 0x44f470 walks slots own-1 DOWN to 0 only (cars ahead, nearest
   first; asm 0x44f4aa/0x44f668). A slot qualifies if |its lane value - mine| <= 0.5 (`[0x6b7604]`) + half widths. With range 99999 the first
   qualifier is accepted and out0 = 0, so the "< 5 m" test (`[0x6b76d8]`) at 0x453a0d is vacuous: the 5 m in older notes is wrong. The range
   that matters is act+0x208 = 30 m (`[0x6b76e0]`) inside the Avoid update. Then 0x44efd0 must say 1: it returns 1 for every car (the player
   included) except a traffic car inside a junction (its old name TrafficCar_IsIntersectionObstacle is inverted). Priority 300.
5. Avoid update 0x453c60: obstacle found in the slots by id (act+0x200) with relative speed > -40 m/s (`[0x6b76e8]`): lanes tried in order
   current, +-1, +-2 (0x453ba0 = lane clear: 0x5a7700 + a car-in-lane rescan); the first clear one goes to ctx+0x394 and ctx+0x398 = 1 (swerve). If
   none: speed target act+0x1e4 = 6 m/s when the car ahead is 15..30 m (`[0x6b76e4]` = 15), 0 at <= 15 m, gain act+0x1ec = 2.0, act+0x1f0 = 0. Clear:
   cruise speed. car+0x88c..0x89c is a debug tint (255.0 on one channel per state), not gameplay. (V)
6. Speed to pedals: 0x583910 (min of action target and lane speed) -> 0x583850 -> RealDriver vt+0x38 `SetDesiredSpeed` 0x45e180 (+0x200 = speed) and
   vt+0x3c (driving line). `PsychoDriver::Update` 0x45e970 is the only PID: throttle at driver+0x1dc, BRAKE at driver+0x1e4 (stores 0x45f8e3..0x45f903,
   braking branch 0.9). Steering goes through the steer point (vt+0x40 0x45db30, angles 0x45e370). (V for stores, I that +0x1e4 is the brake)

## Exact conditions that make a traffic car ignore the player (V unless marked)
a. The player is behind (slot index > own): 0x44f470 never reads those slots. No other finder exists for goals 4/5. Head-on in another lane: no
   lateral overlap, so no reaction (correct). Head-on in the same lane: found; no lane change if closing faster than 40 m/s, then it brakes.
b. Goal 5 only (cars from spawn records, 0x598c80; goal vt[3] = 0x577fd0 returns 1; goal 4 = 0x5314d0 returns 0): at 0x4539cf..0x4539fb the
   finder drops the obstacle when entity kind == 6, `[[obstacle+0x90]+0x1c] != 0` (race record, set for the player and every rival: I,
   names_seed 0x4333c0) and its speed (0x44d5f0) > 20 m/s (`[0x6ccb4c]`). The player is almost always above 20 m/s, so a goal-5 car never brakes,
   swerves or honks for him. Goal 4 cars (route placer 0x5991a0, random node 0x598fb0, teleporter with record 0) do react to a player ahead in lane.
c. Beyond 30 m and not closing, or not within list range, nothing is armed. The reaction waits for the car's turn (item 1 above).

## Lights, horn, brake lights (V, G+C)
- Horn: only `HonkAtPlayer` 0x44c2e0, reached only after the finder fired (blocked by the obstacle ahead). Needs obstacle usage != 1 and kind != 3,
  `[0x7361f0]` == 9 or obstacle is human (0x57a6b0), 0x456780 true. Horn flag roll: 1.0 if slot+4 > 50, 0.75 for the player (`[0x6cca08]`), else 0.05/0.075;
  lights flag only if horn: 0.9 if slot+4 > 50 else 0.5. Times 0.2..0.3 s etc. Writer 0x429100 (ecx = car, 6 args), fields +0x83e lights, +0x83f horn,
  +0x840 gap, +0x844..+0x850 timing; 0x429190 turns them into +0x855 (flash phase, else base +0x854) and the sound object vt +0x48/+0x4c.
- Base +0x854: only written to 0 at 0x425853 and by the net field list: nothing sets it. Draw test 0x5693b0 returns 1 for every traffic car at
  0x5693b7 (`75 03`), so a traffic flash is never visible. No hazard flag exists (scalar 0x83e / 0x854 / 0x855 scans).
- Brake lights: 0x56d8d0 adds 16 x `[[car+0x30]+0x1e4]` to the tail flare when > 0.05 (`[0x6b5db0]`); car+0x30 is the RealDriver (I, same object as
  TrafficAI+8). So a traffic car that brakes gets brake lights from the game, nothing to add.

## Minimal change (not implemented; effects NOT VERIFIED at run time)
1. Patch table, one entry: 12 bytes at 0x4539db, `8b 51 1c 85 d2 0f 95 c0 84 c0 74 18` -> `8b 49 14 83 79 04 02 75 1b 90 90 90`: the goal-5
   exemption (item b) then covers only rivals (driver kind 2, `[[car+0x14]+4]`), not the player. Why: goal-5 cars then use the game's own brake,
   lane change and honk for a player ahead. Rivals keep their pass-through. No cave.
2. Player closing from behind: no byte can change it (the finder would need a new scan of slots own+1..; flipping the sort key makes gap 0 and the
   car stops dead). Keep the host rule `traffic_tick` (host/rivals.c:595, `?trafyield`): inputs are the player's pos/vel (+0x50/+0x70) and each
   traffic car's ctx+0x394/+0x398 and 0x5a7700; it already swerves and calls 0x429100. Changes: make it default instead of opt-in (web/mode.js
   `trafyield: '0'`) when the OWNER agrees, and add patch 0x5693b7 `75` -> `eb` so the flash it arms is visible (the host already keeps +0x854).

## Open (U)
Meaning of Car+0x24 values 3/4 tested by HonkAtPlayer; 0x454240 and 0x5aad10 (junction gate); who clears act+0x1f0 for lane drive; steer stores
(`+0x1e0` is not written by 0x45e970 alone). Nothing here was run: no check that item 1 changes behaviour, or that 0x44f470 accepts at out0 = 0 live.
