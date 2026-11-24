# Racer AI of Speed.exe: how rivals race each other

> Source: `docs/re/race_ai.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 76

# Racer AI of Speed.exe: how rivals race each other

Tools: Ghidra named decompile (/root/re/named_export, live Ghidra for missing functions), capstone scans of the whole
.text (`asm.py`). Nothing was run. V = code read, I = inference, U = doubt. Names: census/names_raceai.tsv.
Slots below are rows of the neighbour list (0x38 bytes each, own index byte ctx+0x388).

## Answers

**(a) Draft.** Reachable, but rare, and it is a brake, not a gain.
- Only request: `Racer::RunAction` 0x44bbd0 (racer vtable 0x6c89f0 slot 0x88) runs the action update. If the action leaves
  byte `[action+0x1e0]` = 0, it deletes the action and calls slot 0x84 (0x4624d0) with type 4 at 0x44bc11 (priority 100,
  duration -1.0, ctor 0x450400, call site 0x4625a3). A scan of every `call [reg+0x84]` found no other type-4 request. V
- Only two updates ever store 0 to +0x1e0 (scan of all 24 byte stores): Pass update 0x450bb0 at 0x450c33 (its target is no
  longer in the neighbour list) and GetUnstuck update 0x452070 at 0x452181 (ctx+0x38c empty). V
- Draft update 0x450480: lane drive. If the nearest car ahead (slot own-1) is a racer or human (driver kind 2 or 1), overlaps
  laterally and is closer than 6 m (0x6b7628), the speed target is `lead speed - (20 - gap)` (0x6b7620 = 20), only if lower
  than the current target. So it only slows the rival. Priority 100 and no timer, and JustDrive (0) cannot replace it
  (0x44bc30 keeps a new action only if its priority is strictly higher), so it stays until a finder fires. V
- A speed gain behind another car DOES exist, outside the AI: `car+0x47c`. `World::Step` 0x420b40 writes it for every car each
  step = `0x426450` = sum over all cars of `0x426300(other, self)`, capped at 0.9 (0x6b7b54). Pair term: other speed >= 1 m/s
  (0x706288), distance <= 60 m (0x70629c), cosine >= 0.95 (0x6b7b50) between the line to the other car and a heading
  (whose heading: I), reach from a speed table (0x7062b4), falloff table 0x700d3c = 1, .9, .75, .55, .3, 0 over dist/reach. V
  It enters physics as `(1 - car+0x47c)` at 0x479160 / 0x474d40 (`[ph+0x50]+0xc`, an aerodynamic factor: I, same product as
  the drag term in 0x456830) and the AI speed prediction. Player and rivals both get it. So "the game has no slipstream"
  (host/rivals.c comment at "Slipstream") is wrong: the game has one. Its size in m/s is not measured.

**(b) Pass and Block.**
- Pass finder 0x450730 (selector step 8, only if current priority <= 200). Needs the race clock stamp `[[0x73619c]+4]` set and
  older than 5.0 s (0x6cc954). Walks slots 0..own-1 = cars ahead, FARTHEST first (sort order of 0x57a910, V). A slot qualifies
  if gap > 0, |lateral| < 2*gap, reach test 0x4569b0 (gap < 3*(1.5*S + rel speed): I), planner 0x45bae0 finds a clear path
  and 0x450b40 allows it (target >= 20 m/s needs state 1 or a planner flag). First qualifying slot wins, returns priority 200,
  then the personality draw 0x462740 (record +0xc = 1.0 for all skills, so always true, per docs/re/rivals.md). Action lasts 5.0 s
  (0x6b75ac). V
- Side: planner 0x45bae0 tries the current state, then state 1, then a side state: 0x45c0d0 compares the lateral values of
  both cars and the road edges and returns 1, 2 or 3; the planner takes state 2 or 3 (the other side of the target), each
  checked by `0x45b050` over 2.0 s (0x7006ec). Any failure falls back to state 1 (lane). V for the order, I for what each
  of 2/3 means in metres.
- Update: path to the pass line; once the target is behind (gap <= 0) back to state 1. If |rel speed| <= 5 it calls 0x44f6c0
  which sets the nitro flag (+0x1f3) when the driver is kind 2 and `0x462b30` agrees. V
- Block finder 0x450ec0 (step 7, ceiling `0x77a340[8*aggr]` = 200/200/400). The target is the car BEHIND: it scans slots after
  own, takes the first car (kind 6, driver flag +0x1c != 0, speed >= 10 m/s), then: bumper gap < 0 and > -50 m, rel speed
  > -5, non-human follower only if |gap / rel speed| <= 2.0 s (0x6b7638), human follower anywhere within 35 m (0x6b763c)
  with no closing needed. Not in the 12 s start window (0x435ca0). V
- Block update 0x451230: the line is aimed at the follower's own lateral value (slot lane value for the route state) through
  0x45c370, so yes it moves across to cover the follower's lane. The blend is 1.0, or a table value of gap/rel speed
  (0x7061f4) when the follower is already >= 10 m ahead. Speed stays the goal cruise speed. V

**(c) car+0x404 and racer+0x4b8 rewritten at 1.12 every frame.**
- `0x44bd10` writes `car+0x404 = max(scale, 1.0)` (0x44bff5) and `racer+0x4b8 = scale` (0x44bffe) every [0x77a49c] s. Early
  returns (no vehicle, drag, [0x78a344], [0x7361a8], flag +0x46c) write nothing. V
- Readers of car+0x404: physics step 0x474a90 -> 0x474d40 and 0x4774a0 -> 0x479160 (engine/tire scale, every step);
  AI speed prediction 0x456830 (speed / 0x404, feeds the Pass reach test); stats 0x4338c0 (clamped >= 1). Other writers: init
  0x4648c0 / 0x464f20 and the two-human catch-up 0x429b10. V
- Reader of racer+0x4b8: only 0x44c550 at 0x44c731: `route speed * record+0x14 * 4b8`, and only when the current action
  has +0x1f0 != 0. Actions that set +0x1f0 = 0 (Draft near a car, IJustGotHit, Accident, GetUnstuck) bypass it. V
- Risks: (1) "stuck high": when 0x44bd10 returns early (drag, Free Run, no vehicle) nobody resets the values, the outside value
  stays; (2) "never slowed": the game's own lead-slowing (scale < 1, rubber band for a rival ahead) is lost on 4b8, and 404
  was already clamped to >= 1; (3) 1.12 on 404 also changes 0x456830, so the Pass reach test and speed prediction see a
  faster car (<= 12 %). No crash path seen. V for readers, I for effect.

**(d) Strongest behaviour that rarely fires.** Block against a car behind (code read, frequency not measured: no run).
The single hold-back is the finder's "first car behind" test at 0x450ec0: only the first behind slot that is a racer with
flag +0x1c != 0 and speed >= 10 decides, and for a rival follower it needs a closing time <= 2.0 s (0x6b7638). The table
`0x77a340` (200/200/400) only sets the ceiling over other actions. The writer and meaning of driver flag +0x1c are U.
Second candidate: nitro. `0x44cac0` needs the nitro count `[car+0x3d8] >= [0x700784]` = 2 in street races, and `0x462b30`
needs a cooldown of rec+0x34 = 35 s (skill 0) to 17 s (skill 9) between shots (0 in the final stretch of the last lap). I

## Where things sit
- Selector 0x44d8b0 order: GetUnstuck 500 (finder 0x451b00 + 6 s cooldown 0x462aa0), 0x13 600, IJustGotHit 400 (0x44ed70),
  AvoidCross 400 (0x452b40), Avoid 300 (0x44f8a0 + draw), Accident 500 (0x452630), Block, Pass, else JustDrive. V
- IJustGotHit update 0x4522a0 is a back-off: speed = culprit speed - 6 (or - 0.1) via 0x44e850, or coast via 0x44e950 (0.2);
  there is no revenge code. V
- Avoid update 0x44fb30: state 2 or 3, planner 0x45b150 over 2.0 s, falls back to lane when not clear and speed <= 20. V
- Neighbour list 0x57a910: max 16 cars, key = along^2 + lateral^2, negative for cars behind, sorted descending: index 0
  farthest ahead, own-1 nearest ahead, own+1 nearest behind. V (the older note said "ahead first"; it means farthest first.)
