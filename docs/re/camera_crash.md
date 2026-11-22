# Jump cam refusals and the crash cam

Source: OWNER log nfsu-session-2026-11-01T00-54-07 (WORLD 1010), disasm of pc/Speed.exe, Ghidra export. Nothing was run.
V = read in code, I = inference, NV = not verified (needs the OWNER's F10 log).

## 1. Why eye_check refuses (host/free.c eye_check, line 940)
- `dist 0` in `JCPICK ... refused` is NOT a measurement: line 981 prints the literal `e > k ? dist : 0.0f`. (V)
  A refusal says only: for every e in k+1..e0 no edge passed the portal test with dist >= 30 m.
- The args to 0x457300 are right (V): eax = k, ecx = route, stack = car+0x60, eye, e-1, caller pops 12 (game call 0x42cf02);
  lane/offset math equals the game's 0x42cd24..0x42cf6e. 0x457180 is a plain 2D segment-segment crossing (t,u in [0,1]).
- 0x457300 needs the car->eye segment to CROSS the cross-section of every node k..e-1 (loop esi..eax inclusive, 0x457360..0x4573da).
  If the car is already past node k, the segment can never cross it: the test is false for every e, both edges. (V)
  The game does not mind: on failure it takes the other edge unchecked (0x42cf12). Our eye_check turns that into a refusal.
- Why k is behind the car (I): `k` = 0x5a6150(route, car+0x60) = 0 in all 9 queries (even while the car moved 56 m in the 8
  consecutive refusals f4482..f4538, speed 55 m/s). The route head is the driver cursor, refreshed only every 60 frames
  (0x426b63: `frame % 0x3c`, TrackPath__UpdateCursor), so at 55 m/s it lags up to ~55 m = 5 nodes (node gap ~11 m: 124 m / 12 nodes).
  The one `clear` (f16681) was at 5 m/s (crash cam, car at rest), k = 0 ahead of the car, dist 142 m. Fits.
- Second cause (I): even without the lag, e can only go DOWN from e0 = end-2 (= 5..6 here), so e*11 m is 11..60 m from node 0,
  and nodes 0..4 are behind or at the car: no candidate is both ahead and >= 30 m.
- Minimal fix in eye_check (not applied):
  1. f = first node i in k..e-1 whose centre is ahead of the car: `node_point(c, node_i, 0.5*(ldf(node+0x20)+ldf(node+0x3c)), 0, scratch)`
     (scratch = jump_scr+48, the 64 B block is big enough), ahead means `dot(p - car+0x60, car+0x70..78) > 0`. Call 0x457300 with
     eax = f (skip the test when f > e-1: nothing between car and eye).
  2. Loop e UP from f+1 to count-1 (`count = ld(route+4)`), take the first e with portal ok and dist >= 40 m (JUMP_MIN_M).
     [5cc] rule stays: `e-k<=4 ? e : e+2` (only 0x42ca9b reads [5cc], V grep; node k+2 stays valid, k unchanged).
  3. Make the log honest: print the best dist seen and how many e failed the portal vs the distance.

## 2. Other reasons the jump cam is rare (log: 71 fast airborne samples, ~14 episodes, 9 queries)
- 0x42c4b0 itself returns 0 when the route has < 5 nodes over 75 m: the log shows episodes with `nodes 1 last 0` (f8605, f13625..13821
  at 69 m/s): the host never sees them. The route is 1 node for long stretches of this session. (V from 0x42c4b0 code, log)
- Trigger gate `ctrl+0x4ac == 0` (0x426930, Ghidra line 30068; ctrl = car+0x18). ctrl+0x4ac is the WRONG WAY flag, stored every frame
  from 0x430e00 at 0x430730 (V). 0x430e00 = heading vs route direction (car+0x818/0x81c) more than a threshold apart, car moving
  (|car+0x3d0*..| > [0x6b7b14]), velocity also against it. In WORLD, driving against the route direction is common and the HUD
  hides it (free_hud), so this gate can block the jump cam half the time. Value in the log: NV. Add `ctrl+0x4ac` to jumpcam_log.
- Episodes with 10..14 nodes and no JCPICK (f9487, f9597, f9709, f10306, f16524, f17332): flight predictor under the curves
  (1.5 m height, 1.5 m distance at x=128), or 0x4ac = 1. NV.
## 3. Crash cam: 0x465d00 (SpecialCamCaller_465d00) (V, Ghidra 72405 + asm 0x465d00..0x466330)
- Not a separate camera: it calls 0x42c4b0 (our cave at 0x4662e0) then 0x42da40(mode 6,0,1,1) = the same JUMPVIEW shot
  (slow motion 0.4 for 8 s, mover 0xf). No mode 7/other mover for crashes. Mode 7 (landing) follows only after mode 6.
- Caller chain: rigid-body pair resolver 0x46bae0 -> 0x465830(body_pair, contact, impulse, |v|) -> 0x465d00(pair, contact pt, impulse vec).
  pair+0x64 -> bodies at +0x258 / +0x25c. local = |impulse| clamped to [0x6b72c0] = 50.0.
- Gates, all must hold (asm 0x466286..0x4662e5):
  1. `[0x78a345] == 0` and `[0x7361a4] == 0` (global "no special cam" flags; 0 in WORLD per re_jumpcam RN_WATCH).
  2. 0x4663a0: BOTH bodies have type byte `+0x15 == 0` (vehicle vs vehicle). A wall or prop (type 4, I) never gives the cam.
  3. |impulse| >= `[0x6b72b8]` = **35.0**. (Same value is compared as `<=` in Ghidra; asm: `fcomp; test ah,1; jne` skips when < 35.)
  4. The body is the human player: 0x424d60: `[veh+0x14]+4 == 1` and `[[veh+0x14]+0x734] == 0`. Traffic and rivals: never.
  5. camera ctrl mode `[ctrl+0x60]` not 6 or 7.
  6. 0x42c4b0 returns non-zero (route >= 5 nodes over 75 m) -- our eye_check sits here too.
  7. 0x42da40(6): `[0x78a3fa] != 0` (jump-cam option, 0x80), cooldown 5.0 s `[0x6b7a88]` per mode (shared with the jump cam),
     `[0x7361c4] != 2`, `[[0x73619c]] == 4`, `[[0x7361f0]] != 9`, `[0x78a346]`, `[0x7361a0]` = 0, no other player in modes 3..7.
     [0x7361e8] and ctrl+0x4ac are NOT read on this path (only the jump trigger reads them).
- Crash state, separate from the cam (first block of 0x465d00): impulse >= `[0x6b72bc]` = **30.0**, body `+0x38 == 0`, both bodies
  vehicles (or vehicle + type-4): sets `car+0x38 = 1`, `car+0x4cc = 0`, `car+0x4c8 = now` (0x426930 ends mode 6 0.5 s after 4 wheels down).
  Other constants: 0x6b72b4 = -0.97 (head-on dot), 0x6b72c8 = 35.0 / 0x6b72cc = 15.0 (impulse gate of the [0x78a344]/[0x7361a8] branch, not the cam).
- No crash-cam option byte exists: the only user byte on this path is `[0x78a3fa]` (jump cam option, 0x80 in the log = on). (V)
- Fired in WORLD: yes, once in this log (f16681, 21.6 -> 5.1 m/s, right after a respawn, `clear` 142 m) and in the 2026-10-28 runs
  (taxi). Why it is rare: needs a car-vs-car hit with |impulse| >= 35 by the player, then the same eye_check. The unit of the
  impulse is NOT known (NV): add one rn_log of `local` (esp+0x1c) at 0x4662b0 in the probe build and ask for F10.
## Patch proposal
host/free.c eye_check as in section 1 (f = first node ahead; e ascends f+1..count-1; min 40 m; honest log); log ctrl+0x4ac and the crash impulse too. patches.py unchanged.
