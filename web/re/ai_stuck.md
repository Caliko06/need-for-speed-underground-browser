# Rivals: how often they get stuck, and what GetUnstuck really is

> Source: `docs/re/ai_stuck.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 36

# Rivals: how often they get stuck, and what GetUnstuck really is

Question: how often are rivals stuck or sideways, what triggers GetUnstuck (type 0xa, update 0x452070),
how long does the recovery last, what does it do to the car, and is the trigger or the timer the cause.
V = read in code (address) or measured in the logs; I = inference; U = doubt. Nothing was run.

## Answer

1. The game's stuck test is **not** "speed < 2 m/s". It is: the car has been within 0.4 s of a contact/keep
   list entry **and** its speed is below **5.0 m/s**, **or** it is more than **20 m** off its route line, **or**
   two special modes (vehicle+0x24 == 3 at < 25 m/s, == 4 at < 20 m/s) with `0x44e9c0(...)==1`. V
2. Trigger cost is tiny: 0.4 s under 5 m/s is enough, and the returned priority is **500**, the highest in the
   race selector. A rival that is merely slowed behind traffic or another car burns the recovery. V
3. The recovery is a **reverse**, not a reset: the action's own speed target (racer+0x1e4) is set to
   **-15.0 m/s** when vehicle+0x24 == 3, else **-6.0 m/s**, and route-node speed is disabled (racer+0x1f0 = 0). V
   Duration from the ctor slot 0x462ae0 = **1.3 s** default, **1.6 s** (float 0x3fa66666 / 0x3fcccccd) under one
   condition. Cooldown **6.0 s** since the last creation (racer+0x408, 0x462aa0). V
4. Measured: rivals spend **2.7 % to 8.8 %** of their sampled seconds below 2 m/s (telemetry definition), with
   single stops of **13.7 s to 17.9 s**. GetUnstuck is entered **7 to 25 times per minute** across 8 rivals
   (~1 to 3 per rival-minute), and **27 % to 38 % of those entries happen at speed >= 5 m/s**, i.e. above the
   game's own threshold: those reversals are false positives, not recoveries. V (numbers below)
5. So: yes, the trigger is the cause, and the timer makes it worse (0.4 s is far too short for a 5 m/s test on a
   car that is 0.4 s behind traffic). A patch is drafted, opt-in, data only.

## The trigger, line by line (asm, sub_451b00 = finder)

- Gate: `0x435ca0` early-out (race not live), slot list head `ctx+0x38c` must be non-zero, `0x57a7d0` must pass. V
- Off-route branch: cross product of (car - route point) with the route segment > **20.0** (0x6b7690) = off road
  > 20 m, flag stuck. V for the constant and the compare at 0x451b87.
- Contact/speed branch (loop over the list at ctx+0x3c, 0x451be0..0x451c76): for each entry it needs
  `(now - entry+8) * 0.00025 >= 0.4` (0x6b7680) and then own speed `< 5.0` (0x6b7684), with a fuzz call
  `0x424b50(speed, 5.0, 0.001)` that can still veto (I: a rare escape roll; U: exact semantics). On a hit the
  local flag is set to 1. V for constants and flow, I for what the list membership means.
- Mode branch (0x451b94..0x451bdb): vehicle+0x24 == 3 and speed < 25.0 (0x6b7688) or == 4 and speed < 20.0
  (0x6b768c), then `0x44e9c0(ctx+0x38c, 1) == 1` sets the flag. V for constants; U for what modes 3/4 are.
- Return: flag set -> `mov eax,0x1f4` = **priority 500** at 0x451c9b, else -1. V
- Two selector sites call it (0x44d924 in the race selector `sub_44d8c5`, 0x44dd89 in a second goal selector at
  0x44dd45); both require current type != 0xa, current priority <= 500, and the 6.0 s cooldown vt+0x6c
  (`0x462aa0`), then set racer+0x408 = now and take the duration from vt+0x70 (`0x462ae0`). V
- Lower levels also fire it: ctor 0x4519f0 is also called directly from 0x462656 (`sub_4624d0`, the "make action"
  entry), so at least one path can create the action without the finder. I (callers V, semantics I).

## The update, 0x452070 (what it does to the car)

- `racer+0x1f0 = 0` (speed no longer from route nodes), `+0x1f1 = 1`, `+0x1f2 = 0`, `+0x1e0 = 1` (keep alive). V
- Steer/lane target: `0x45c370(racer+0x20, ctx, 1.0, 2, 0, 25.0)` (25.0 = 0x47c34f80) every tick. V
- Then `[vehicle+0x24] == 3` -> `racer+0x1e4 = [0x6b7674] = -15.0`, else `[0x6b7678] = -6.0`. V
  The telemetry contract says +0x1e4 is the action's own speed target when +0x1f0 is 0, so the car drives
  backwards at 6 to 15 m/s, on a lane target, for 1.3 to 1.6 s. V for the stores, I for "reverse".
- If `ctx+0x38c` is empty (no slot) it sets `+0x1e0 = 0`, the action dies, and `0x44bbd0` requests type 4
  (Draft, priority 100, duration -1) at 0x44bc11. That is the sideways behaviour at low speed. V (addresses),
  I (link to the visible sideways drift).
- No position reset, no teleport, no invulnerability: the recovery only reverses. V

## Numbers (AIR logs, 1 Hz per rival; `runs/w_*`)

| run | span | rivals | stuck <2 m/s | max stop | entries | per min | entries at >=5 m/s | time in 0xa |
|---|---|---|---|---|---|---|---|---|
| w_ai_s1 | 234 s | 8 | 5.3 % | 17.7 s | 29 | 7.4 | 34 % | 3.1 % |
| w_ai_s2 | 243 s | 8 | 4.9 % | 13.9 s | 46 | 11.4 | 28 % | 5.2 % |
| w_ai_s3 | 225 s | 8 | 8.8 % | 14.1 s | 94 | 25.1 | 27 % | 10.3 % |
| w_x_base | 190 s | 8 | 6.6 % | 13.7 s | 57 | 18.0 | 35 % | 7.3 % |
| w_b | 314 s | 8 | 3.3 % | 17.9 s | 78 | 14.9 | 38 % | 3.7 % |
| w_L3 | 618 s | 8 | 2.7 % | 8.1 s | 149 | 14.5 | 30 % | 5.8 % |

- Worst single stops: SAMANTHA 17.9 s (w_b), WART 16.7 s (w_ai_s1), ISHII 13.7 s and PRISS 13.9 s (w_x_base, w_ai_s2). V
- Action-length streaks (samples in 0xa): mostly 1 to 2 samples (the 1.3 s action), but bursts of 4 to 7 samples
  exist (w_L3 CARL 5, 5, 6 s; w_b FISH 2-3 s runs), so the action is re-created inside the 6 s cooldown or the
  duration taken was longer. I/U (1 Hz sampling cannot tell a re-create from one long action).
- Where (nearest AIP position of the player at each entry, 400-unit cells): w_ai_s1-2 cluster around
  (800,-400) and (2000,0); w_x_base (2000,-400) and (1600,0); w_b (2000,0), (1600,400); w_L3 (1600,0).
  Those are the same corners where AIHIT wall hits cluster; w_ai_s3 has all 94 entries on one cell (2000,-800),
  which is a single bad corner, not a global problem. V for the cells, I for "bad corner".
- 31 % to 83 % of the entries happen with the rival behind the player (d < 0), i.e. in traffic, not alone. V
- The player's own frame counter is 60 frames per second in the s1-s3 baselines (measured: 1.00 s between AIP
  lines by distance/speed), 2.4 s in w_a (that run is not usable for timing). V

## Proposed patch (opt-in, data only, reason: trigger + timer)

`tools/recomp/patches.py`, both floats are read only by the three stuck finders
(refs: 0x451c2e, 0x451eaf, 0x451ffb for the timer; 0x451c48/0x451c54, 0x451ec5, 0x45201b/0x452027 for the speed):

- `0x6b7680  cdcccc3e -> 0000c03f`  0.4 s -> 1.5 s (a car must be slow for 1.5 s, not 0.4 s)
- `0x6b7684  0000a040 -> 00004040`  5.0 m/s -> 3.0 m/s (18 km/h, not 11 km/h, counts as stopped)

Both behind `RN_AI_STUCK=1`, so original mode stays untouched and the log prints what changed. Not done here:
the 20 m off-route branch and the mode 3/4 branch (needs to know what vehicle+0x24 is), and the -15 m/s
strength (a 15 m/s reverse at speed is what looks clumsy; halving it is a separate experiment).

## Not verified (U)

- Meaning of ctx+0x3c list membership and of `0x44e9c0` (I read its call sites, not its body).
- Whether `0x424b50(speed, 5.0, 0.001)` is a random escape; if it is, the 0.4 s rule is per-tick fuzzed.
- Real wall clock of w_a (frames per second is not 60 there); its percentages are shares, not rates.
