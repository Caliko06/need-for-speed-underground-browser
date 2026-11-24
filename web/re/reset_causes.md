# Why the car passes walls or falls after a reset: hypotheses ranked

> Source: `docs/re/reset_causes.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 70

# Why the car passes walls or falls after a reset: hypotheses ranked

Scope: the original code (pc/Speed.exe, hopper decomp in census/hopper/decomp.c, build/build/hopper/frame.txt,
build/build/hopper/collreset.txt) and the port (host/free.c free_tmove). No game run from this worktree for step 1;
step 2 only adds a probe. Markers: V read in the disassembly/decompile, I inference, U unknown.

Step 2 facts from Main (ghosts r_a/r_b, RN_RESETLOG=1 RN_FREETMOVE=1): 59 resets of traffic/rival cars, 0
MOVED-WHILE-SLOW, dz after the reset consistent with the road slope. Those go through 0x427f70 with a route path.
The OWNER's bug is the **player's** reset, and the autopilot never triggers it (see the trigger table below).

The reset RE lives in
[`docs/re/coll_reset.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/coll_reset.md) (cache/pool), the WORLD zone note `re_zones` (triggers; not published) and the Hopper exports of the reset functions.

## The reset, as the binary does it

- Entry used by the port: `0x427f70` (host/free.c free_tmove, and the same tail as the game's own respawn). It ends in
  `0x427c50` (V: [coll_reset.md](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/coll_reset.md) §1; the body at 0x427c50 reads arg0 = pointer to a 3-float position, arg1 = speed,
  arg2 = heading word).
- `0x427c50` writes, in this order (V, objdump of 0x427c50..0x427d84):
  - `car+0x3b4 = arg2` (heading word) and `car+0x3b6 = 0` (0x427c97/0x427c9e): **orientation is set**, not kept.
  - `car+0x60/64/68 = *arg0` (0x427cb1..0x427cb7) and `car+0x3d0 = arg1` (speed).
  - `call 0x440740(car+0x540)` (0x427cc0/0x427cc6): clears the car's collision cache: box = +inf/+inf/-inf/-inf and every
    body count 0 ([coll_reset.md](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/coll_reset.md) §1, V).
  - `call 0x4278d0` (0x427ccd), `car+0x460 = 0` (0x427d15).
  - `0x5673e0` output = unit heading * arg1 -> `car+0x70/74/78` (0x427d0a..0x427d13): **velocity is set** from the
    reset's own heading and speed, and its magnitude lands at `car+0x3d4` (0x427d2e..0x427d30).
- So a reset leaves a complete state: position, heading, velocity, speed, empty cache. Nothing is "left over".

## The sim step clamp (main loop)

- `GameFlow::MainLoop 0x447600` (V, frame.txt): at 0x4477d8 the QPC delta is clamped at 0 (`if < 0`), converted with
  `2^shift * delta * [0x7301d0] * 0.001` (0x4477f0..0x4477fa) and passed to `0x585b40`.
  `[0x7301d0] = 1000 / QPCfreq` (V: set at 0x564880 in `0x564860`), so the argument is `2^shift * seconds`.
- `0x585b40` turns that integer into `dt [0x73ad38] = int(arg) * 1/3600` (V: 0x585d5d, constant 0x6cc7e4 = 1/3600f),
  i.e. dt in seconds when the scaling gives 60 counts per second.
- `0x585d70` runs the fixed-step scheduler once per frame: `n = trunc(60 * (dt + rem [0x73456c]))` (V: 0x585d71..0x585da2;
  constant 0x6cc8b0 = 60.0f), keeps the remainder, and stores `n` at `[0x6f088c]`. At least 1 step (`if n == 0: n = 1`).
- At the end of the frame body the main loop clamps the frame counter to 3: `mov eax,3; cmp eax,ecx; jle; mov ecx,3`
  (V: 0x447a2f..0x447a3c, decomp "if (arg_18 > 0x3) arg_18 = 0x3"). 3 is exactly 3 sim steps of 1/60 s = **50 ms**,
  the same cap the NFSU2 port documents (I: the clamp and the tick quantity are the same frame value in the decomp,
  the binding of the two stack slots is not fully resolved by the aliasing decompiler; the number 3 and its position
  next to the dt computation are V).
- So Speed.exe already caps a frame at 3 steps. A frame cannot integrate more than 3 * v/60 metres: at 50 m/s, 2.5 m.
  The ground query inflates its box by `|vel|*0.05 + 3.0` m ([coll_reset.md](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/coll_reset.md), V), which covers exactly that. A 50 ms frame
  alone does not tunnel a wall, and it cannot make a car fall (falling = no ground body, not a big step).
- Turbo: `RN_TURBO=k` multiplies every guest clock by k (host/win32.c), so dt grows k times and the 3-step clamp binds
  harder (the game slows down, it does not step further). The web 60 fps path does not touch the clamp: dt still comes
  from the guest's own QPC/limiter. Neither changes the clamp value itself (V code, I effect on feel).

## Ranked hypotheses (step 1; step 2 updates in "The player's reset path")

1. **H1 - a big dt on the frame after the reset: PARTLY TRUE, not the cause of the fall.**
   V: the clamp exists and is 3 steps = 50 ms (0x447a33, 0x585d70). V: the reset itself runs outside the sim step (the
   host calls 0x427f70 from Present, free.c), so the following step uses the frame dt, which can be the 50 ms cap.
   I: with the swept ground box (+3 m and |v|*0.05) that step cannot pass a wall; it also cannot remove the ground.
   Step 2: 59 resets logged by Main show 0 MOVED-WHILE-SLOW and a dz that follows the slope, so in practice a 50 ms
   frame after a reset does not move the car through anything.
2. **H2 - the cache car+0x540 is not refilled after 0x440740: FALSE.**
   V: 0x427c50 calls 0x440740 with car+0x540, which writes an empty (infinite) box and zeroes every body count;
   0x4407b0 then must take the rebuild branch ([coll_reset.md](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/coll_reset.md) §1). No code path moves the car and leaves +0x540 stale.
3. **H3 - the 8192 collision pool is full: FALSE as stated, PLAUSIBLE under another name.**
   V: the body pool is 1,024 slots (raised to 8,192 by patch 0x4412bd in this line of work); when it is full,
   0x441b90 calls 0x441b20, and when nothing has count 0 it executes `int3` 0x441b82 -> TRAP -> the game stops. It does
   not fall or pass a wall. I: the silent "no bodies" path is pool B `[0x72cbf4]` (wall polygon/witness bodies): 0x469810
   tests `used == cap` and returns with nothing built, no int3 (`re_coll_pool`, V code / I consequence). That car then
   has no wall and no ground bodies: **both** symptoms, and exactly the pair reported. Pool B's cap is patched 0xa0 -> 0x800
   at 0x4669fe; a full raised pool A only makes the halt later.
4. **H4 - velocity/orientation not cleared by 0x427c50: FALSE.**
   V: heading word +0x3b4 written from the reset's argument, +0x3b6 zeroed, velocity +0x70/74/78 written from
   unit(heading) * arg1, speed +0x3d0 written, +0x460 zeroed (0x427c97..0x427d15).

## Which function the player's reset runs (step 2)

Every trigger only raises `car+0x87c` (the "reset me" flag); none of them moves the car:

| trigger | code | evidence |
|---|---|---|
| request / crash recovery | `0x428080` sets `car+0x87c = 1` unless (global 0x78a368 != 0 and driver kind 2); callers 0x42a4d0 (from the service), 0x44b1b0 (AI update), 0x479e20 / 0x47ac00 (collision outcomes: the accident) | V decomp 0x428080; callers funcs.jsonl |
| no ground every 32 frames, route > 5000 m | `JumpCamTrigger 0x426930`: `GroundQuery::HasGroundAt 0x440ce0` (wraps 0x440a40) at 0x426b29/0x426b50, then `mov [edi+0x87c],1` at 0x426b59; the 5000 m check sets it at 0x426ba2 | V objdump 0x426b29..0x426ba2 |
| RESET zone (2) | `Car::ApplyResetZone 0x427ed0` sets `car+0x87c = 1` | V decomp (WORLD note `re_zones`, not published) |
| AI accident | `0x452710` sets `car+0x87c = 1` (AI only) | V decomp |

The service is `Car::ServiceResetRequest 0x4264d0`, run from the car update (`CarCollisionBody::Move 0x46a030`):
it reads `car+0x87c`, gets the driver at `car+0x14`, and for **kind 1 (human) with driver+0x734 == 0** does
`mov eax,[esi+0x18]` (the controller) then `call 0x4314a0` (**V**: objdump 0x426526..0x42653e), clearing `car+0x87c`.
`Player::ResetToRoute 0x4314a0`:
- with a route path (`driver vtable +0x14` returns a node): `0x427f70(car, section, node, speed, 1, dir ±1, 0, 0, lateral)`,
  the same 9-argument stdcall free.c uses (V decomp 0x4314a0, host/free.c comment);
- with no path: it scans **all** route nodes (`[0x7372c0]` count, `[0x7372c4]` rows of 0x14 B), keeps the nearest one
  that has ground by its own `0x440a40`, then calls `0x427c50(&pos, 0, heading = 0x564db0(car+0x818/0x81c))` (V decomp).
  Speed 0 there, so the reset leaves the car stopped at a node height.

So the player's reset is **0x4314a0**, reached as `eax = car+0x18; call 0x4314a0` (no stack arguments). The Reset Car
*button* itself: the string `JOY_EVENT_RESET_CAR` sits at 0x6ba98c with 0 cross references in this exe
(build/build/hopper/resetcar.txt says the same; a byte scan for the store pattern finds only 0x426930 and 0x452710),
and host/input.c has no reset key. I: in this build the human path is the request flag (0x428080 / 0x87c), not a bound
action name; no code reads that event id.

### Ranking, updated with Main's 59 resets

1. **The player's no-path placement branch of 0x4314a0** (new #1). The 59 logged resets took the 0x427f70 branch with a
   route path and landed correctly; the branch the player can take instead (no path) picks a node by 2D distance with
   0x440a40 at the *node's* xy and places the car at the node's height with speed 0. In the merged world the nearest node
   of the loaded track with ground is not necessarily the road under the car, and the car keeps that node's z. I: this is
   the only reset path Main's data never exercised.
2. **H3 as pool B** (unchanged): silent no-bodies for walls/ground. The probe's `cache %u/%u/%u/%u` (total/ground/walls/
   rest, car+0x7e0..0x7ec) and `ground` show it.
3. **H1**: exists (50 ms cap) but Main's logs show no effect after a reset.
4. **H2 / H4**: refuted by code (above).

## Probe (host/aitel.c, off by default)

- `RN_RESETLOG=1`: `reset_call(c, target)` from `rn_call` at 0x427f70/0x427c50 logs `RST` (frame, which call, car, race
  index, pos/speed/heading before, dt, cache counts). `reset_tel(c)` from Present logs `RSTA` on the first frame after
  and `RSTW` every 10 frames for 120: position, dz since the reset, distance moved, speed, `zroad` (the game's own
  ground height at the car by 0x440a40 on its cache object, flag byte), `dzroad` (car z minus road z), `ground` 1/0 and
  the four cache counters, plus `MOVED-WHILE-SLOW` when it slid > 3 m between samples with speed < 1. The ground query
  can rebuild the cache, so the counters are read before it and the FPU stack is saved/restored around it.
- `RN_RESETEVERY=<seconds>` (default off): every N s of a Free Run (flow mode 6) calls the player's own reset
  `0x4314a0` on the kind-1 car with the same argument the game passes (`eax = car+0x18`, no stack args), then clears
  `car+0x87c`, and logs it as `RSTE` through the same RST/RSTA/RSTW watch.
  Recipe: [`tools/openworld/ghost.sh`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/tools/openworld/ghost.sh) `rst 240 RN_RESETLOG=1 RN_RESETEVERY=3` (native, WORLD), or on :5186
  `?env=RN_RESETLOG=1` with `RN_RESETEVERY=3` in the environment. Non-player resets: `RN_RESETLOG=1 RN_FREELOG=1
  RN_FREETMOVE=1` with `?traffic=15&trafrefill=1`.
