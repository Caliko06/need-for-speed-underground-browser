# Traffic cap plan: every fixed per-car array blocking 30 / 40 / 48 / 64

> Source: `docs/re/traffic_cap_plan.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 75

# Traffic cap plan: every fixed per-car array blocking 30 / 40 / 48 / 64

Read-only RE on `pc/Speed.exe` (base 0x400000). Every address below was read with
`objdump -d`; bytes are quoted from that output. F = read in code, I = inference, NV = not
verified. No build, no run. The entrant table alone buys **nothing** past 32: the car list
`sorted[]` at `[0x7361f8]+0x28` is the first wall (row 0). Steps are ordered by that.

## Answers first
- Fixed per-car storage that blocks N, in bite order: car-list `sorted[]` (32), entrant table
  (30 + RaceStatus behind it), collision bodies (30), AI slot pools (26/27/27 + 640 points),
  collision id table (0xde ids, 216-bit bitmap), loaded-car pools (40), neighbour list (16).
- The 45-car fault is *layout*, not count: `sorted[]` is 32 dwords at `L+0x28` and the
  checksum writes 0x10-byte records from `L+0xa8`, so they overlap (F).

## 0. Car list `sorted[]` — blocks 33+, the real 32 (F)

Object `L = [0x7361f8]`, malloc `0x17a0`, ctor `0x41f6e0` (F: `movl %esi,0x7361f8` at
`0x41f7d4`). Fields: `+0x18` count, `+0x1c` players, `+0x20` players+opponents, `+0x24` first
traffic index, `+0x28` `sorted[32]` ends at `+0xa8` (F: ctor sets `+0x18..+0x24` and leaves the
rest zero; the next init in the ctor is `+0x300`).

- Writer: sort `0x41fe50` does `movl %edi,0x28(%esi,%edx,4)` / `incl 0x18(%esi)` in four passes
  (`0x41fe83`, `0x41feac`, `0x41fed8`, `0x41ff01`) with **no bound check** (F).
- Reader that dies: `0x421170`, `leal 0x28(%edi),%ebp` (`0x42118d`) + `addl $0xa8,%edi`
  (`0x421191`), loop `movl (%ebp),%esi` / `flds 0x64(%esi)` (`0x421197`..`0x42119a`), count from
  `+0x18` (`0x42117d`), 0x10-byte record per car written at `edi-8..edi` (F).
  At count > 32 the record for car 0 overwrites `sorted[32]`, so car 32 is read as a float
  pointer: fault in `0x42119a` (F for the overlap, NV for the exact index of the fault).
- Lift: records out of the object. `0x421191` is 6 bytes (`81 c7 a8 00 00 00`); `bf imm32 90`
  (`mov $scratch,%edi; nop`) fits exactly. `sorted[]` then runs to 182 entries before the
  `+0x300` buffers; 64 needs `+0x128` (F).
- Scratch: 64 x 0x10 = 0x400. `0x7e0000` assumed free (NV; entrants at `0x7c0000` end at `0x7dd400`).
- Nothing else in the object is touched. Failure of this step: the same `0x42119a` fault, or a
  new one in `0x4211xx`; if a reader of `L+0xa8..` exists it now reads stale memory (NV, see
  open question 1).

## 1. Entrant table + cap — blocks 31+ (F)

- Array 30 x 0x750 at `0x77c790..0x78a2f0`; `RaceStatus` at `0x78a2f0` (F: ctor
  `0x431e9d` `mov ecx,0x36d8` dwords, `0x431ea2` `mov edi,0x77c790`, `0x431ec4` stores the
  pointer at `+0x128`).
- Cap: `83 bd 2c 01 00 00 1e` at `0x4322e0`, immediate **`0x4322e6`** (F).
- AddEntrant `0x4322a0`: index `count` x 0x750 + `[+0x128]` (`0x43231c`..`0x43232a`), then
  `incl 0x12c` (`0x432331`). 12 callers, all in `0x4b3xxx..0x4b6xxx` (F: `0x43b488`,
  `0x4b3c40`, `0x4b4332`, `0x4b4bde`, `0x4b4e1c`, `0x4b504c`, `0x4b5288`, `0x4b551c`,
  `0x4b594c`, `0x4b5bb3`, `0x4b613d`, `0x4b66c6`).
- Old base (hard-coded): ctor `0x431ea2`/`0x431ec4` and the startup loop `0x689d22`
  (`mov esi,0x77cec4`, count `0x1e`, `call 0x417600`, byte `+0x734=0`). Every reader uses the
  pointer at `0x78a418` (14 sites, plus 0x4b6309 which does `sub $0x78a418`).
- Lift: 64 x 0x750 = 0x1d400 zeroed at `0x7c0000`; write the pointer to `[0x78a418]` before the
  race build; `0x4322e6` `1e` -> `40`. Leave the two hard-coded sites alone only if the new
  block is zeroed (the init loop's `0x417600` sub-object is then skipped: NV, doc traffic_cap
  says the same).
- Raise `0x4322e6` alone: entrant 31 writes over `RaceStatus` (crash / silent corruption) (F).

## 2. Collision bodies — blocks 31+ (F, size I)

- `CarCollisionBodySlotPool`: `bf 1e 00 00 00` at `0x4669be`, size 0x190 (`0x4669b9`), alloc
  `0x566dc0` (F). Also `WorldObjectCollisionBodySlotPool` `bf 20` / 0x410 at `0x46697e`.
- Id table: `movl $0xde,(%esi)` `0x466b11`, `movl $0xde,%ecx` `0x466b55`; bitmap 0x1b bytes =
  216 bits (F for the immediates; the 216-bit read is from `docs/re/traffic_limits.md`, NV here).
- Lift: `0x4669bf` `1e` -> `40`, and ids/bitmap together only when teleport recycles bodies past
  216 (NV which pool id cars take). Failure if not raised: car 31 has no body, passes through
  walls, no contacts (I), or the pool grows by n/4+1 (NV, pool ctor).
- 30-entry array at `0x4632be` (`c6 46 05 1e`, object vtable `0x6b9694`, alloc `0x78` at
  `0x4632b8`) (F). What it holds is NV; if it is the AI contact list, 40 is its size too.

## 3. AI slot pools — blocks 27+ (F)

`0x45553c` 26 (0x18), `0x45557c` 27 (0x220), `0x4555bc` 27 (0xc4), `0x4555f9` 640 x 0x70
(0x280) (F, values from `re_racer_cap` §1.7, immediates re-checked in the
disassembly). One goal + one action + ~24 future points per AI car. Lift: 64/64/64/1536.
`patches.py` already has 48/49/49/1280 for these (F, main's note) -> at 64 traffic the pools are
short again: 56 AI cars need 64.
Not raised: `0x566dc0` returns 0 (NV what the caller does; likely no goal -> car idles).

## 4. Loaded car pools — blocks 41+ (F, meaning NV)

`0x58b1d3` (0x68), `0x58b213` (0x28 x 0x1f4), `0x58b250` (0x1c): all 40. Loaded by car *type*,
not per car (I). Lift to 64 only if the log shows rides failing to load; 64 traffic over ~20
types does not need it (I).

## 5. Physics pools — automatic (F)

`0x4764e0` reads `[0x78a41c]` (entrant count) and sizes RigidBody = count+0x20, `0x1f0`,
`0xa0` x count, Wheel/Suspension x 4*count (`0x4764f0`, `0x476565` `leal (,%esi,4)`). No patch
needed **if** it runs after every entrant is registered (NV, doc open item). If it runs first,
48 cars share 30 bodies: symptom is cars with no physics or bodies recycled.

## Order of steps, and how each one fails visibly
1. `sorted[]` records out (row 0). Fail: still `STOP 0042119a`, or a new fault inside `0x4211xx`.
2. Entrant relocation + `0x4322e6` = 0x40. Fail: `RN_FREELOG` entrant count stays at 30 (silent
   drop), or a write-fault near `0x78a2f0` if the pointer was not moved before the build.
3. Collision body 0x4669bf = 0x40. Fail: cars drive through geometry, COLLOG orphans climb.
4. AI pools 64/64/64/1536. Fail: some cars never move or never brake (no goal/action slot).
5. Loaded pools 64 only on evidence. Fail: a ride loads as a placeholder or the car is invisible.

## Per-car CPU cost that grows with N (F unless marked)

- `0x421170`: ~20 instructions + 1 round per car, runs once per frame (NV how often it is
  called; `0x4474b3` also calls it).
- Neighbour/contact list: `0x57abad` `movl $0x10,0x4c(%esp)` caps each AI car's neighbours at 16,
  so the distance work is 16 x N, not N^2 (F for the constant, I for the loop shape).
- Collision: per body `imull $0xde` at `0x466d79`, `0x466da8`, `0x466e93`, `0x466ecc`,
  `0x468315`, `0x4696df` (F: id -> row math, 6 sites). Pairwise contact resolution cost at N
  cars is NV; expect the 30 -> 48 step to cost more than the 48 -> 64 step.

## Open questions (valid results, not guesses)

1. Does anything read the checksum records at `L+0xa8..`? If yes, the step-1 patch must move the
   reader too; if no, the record block is dead weight and can be dropped.
2. Is `0x7e0000` mapped and writable in the guest (scratch for the records)?
3. Does `0x4764e0` run after the last AddEntrant? (decides whether 40+ physics bodies exist)
4. What is the 30-entry array at `0x4632be`?

## Draft patch (step 0 + cap, all off)

The candidate file (not published): flip `when=lambda: False` -> `True` and rebuild; the build
stops if `old` stops matching. Step 0 is one site; step 1 is the immediate only (the entrant
block is host memory: point `[0x78a418]` at `0x7c0000` from `host/` before the race build).
