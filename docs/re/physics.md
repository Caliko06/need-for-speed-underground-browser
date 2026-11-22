# Car physics and handling (Speed.exe PC)

Marks: V = read in code or bytes this session, I = inferred, U = open. Tools: G = Ghidra (gpar.sh on /root/ghidra_named, decomp and xref),
N = named decompile /root/re/named_export, C = capstone `tools/recomp/asm.py`, D = data read from the exe or GLOBALB.BUN (carinfo.py layout).
Rows for every function are in `census/names_physics.tsv`.

## Answers

**(a) Rear assist 0x4773f0.** Yes, it raises rear grip with slip angle, and speed too. V (N, C, D)
- Assist = min(0.35, (phys+0x280 + phys+0x284) * (v/30) * |slip|), v = CarState+0x394 in m/s, slip in radians (2*pi/65536 scale, 0x6cc980).
  Every one of the 35 cars has phys+0x280 = 0.0 and phys+0x284 = 2.5 (D, GOLF included). 0x735fa4 and 0x735fa8 have no writer, so they are 0.
- Grip scale of a rear wheel = base * (1 + (|body+0x38| + assist) * ramp). base = [this+0x78] (1.0) * 0.85 (0x6ffdd8) when CarState+0x3c0 == 0.
  ramp = [this+0x7c], 0.5..1.0 (falls 20/s while the handbrake input is >= 0.5, rises 1/s).
- GOLF, assist at 5 / 15 / 30 degrees:

  | speed | 5 deg | 15 deg | 30 deg |
  |---|---|---|---|
  | 15 m/s (34 mph) | 0.109 | 0.327 | 0.35 (cap, raw 0.65) |
  | 30 m/s (67 mph) | 0.218 | 0.35 (raw 0.65) | 0.35 |
  | 45 m/s (101 mph) | 0.327 | 0.35 | 0.35 |

  The cap binds when |slip| > 0.864/v rad: 8.3 deg at 15 m/s, 4.1 deg at 30 m/s, 2.7 deg at 45 m/s.
- Three things nobody wrote down: (1) no assist when handbrake input (tire+0x174) > 0.5 and |slip| < 20 deg. (2) The scale is
  cumulative in the wheel loop (stack slot [esp+0x20]), so RL gets the factor once and **RR gets it twice** (about 1.82 at the cap). (3) The slip fed in is 0 when forward
  speed < 1 m/s. Only rear wheels (offset >= 0x40) and only outside drift events (flags below).
- Runs for every car that uses this mover (player and AI), because the flags are globals.

**(b) Yaw assist 0x479350.** Yes, it damps only yaw that widens the slide. V (C, N)
- Needs slip * yaw_rate > 0. slip = heading - velocity direction; Atan2ToAngle16(x,y) is atan2(y,x) counter-clockwise (0x564db0), and
  yaw_rate = CarState+0x98 = body+0xc8 (angular velocity z). Positive yaw raises heading, so same signs means |slip| grows. The sign of body+0xc8 as
  counter-clockwise is I (right-handed, z up); the formula is built on it.
- Torque about (car+0xb0..b8) = row * g(|slip|) * yaw. Row values are negative (-14, -11, -7 for FWD, easy to hard), so it is a damper.
  g (table 0x779b70, built at 0x68a130): 0 at 0, 0.7 at 45, 0.9 at 75, 1.0 at 89 deg, then **0 at 90 deg and beyond** (flat end). At 5/15/30 deg g = 0.078 / 0.233 / 0.467.
- Rows of 0x6f0fc0 (0x6c bytes) are chosen by phys+0x1c0 = rear drive split (D: FWD cars 0, AWD 0.5, RWD 1.0): <0.2 row 0, <=0.8 row 1, else row 2.
  Column = difficulty [0x78a3fc] 0..2. Row 0 -14/-11/-7, row 1 -9/-7.5/-5, row 2 -10/-9/-8.
- It also sets rear wheel +0x180 = curve(0.55*|yaw| + 0.45*|slip|), 1.1 at 0 falling to 0.76 at 1.0 (table 0x6ffe6c).
- Called only from 0x4783c0 when ([0x735fa0] or [0x78a345] or [0x7361a4]) and not ([0x78a344] drag or [0x7361a8]). So **drift events only**, never circuit, sprint
  or drag. Player and AI both (global flags, no driver test). 0x479510 is the twin for [0x78a346]/[0x7361a0] with fixed -25.

**(c) Cap 0.35 -> 0.18 and yaw row x0.6.** The two knobs live in different modes, so they never act together. V for the code, I for the driving result.
- Cap: only circuit, sprint, drag. Rear grip at the cap goes 1.35 -> 1.18 (-13%), RR 1.82 -> 1.39 (-24%). Above about 4 deg at 67 mph (3 deg at 100 mph) the rear no
  longer gains grip as the slide grows, so the tail lets go earlier and does not come back. Risk is oversteer snap at high speed in long fast corners and on lift-off or
  nitro exit, worst for cars with big drive-torque (RWD). Straight line and slip < 2 deg are unchanged. The RL/RR imbalance shrinks, which is a side effect.
- Yaw row: **no effect in street races**. In drift events damping weaker means more spin: damper is 0 when |slip| >= 90 deg, so a car that gets past 90 deg is on its own.
  RWD hard (-8) x0.6 = -4.8. Limits: body+0x1e0 (17.0 when CarState+0x3c0 == 0) clamps yaw torque in 0x585410, so at high yaw rate the damper is already saturated
  and x0.6 only matters at low and middle rates.
- **Do not scale the whole 27-float row.** Columns 3..26 are other data: column 3 is the 0.55 mix, the DriveTrain ctor 0x46d390 gets the same row pointer
  (0x476cf6, 0x473fc0), and 0x479640 reads columns 19..23 (0x6f100c). Scale only floats 0..2 of each row (0x6f0fc0 + row*0x6c).

**(d) car+0x404 through 0x479160.** It works: scale of engine, drag and grip (checked by the lane owner: the first version of this note read 0x6ffe54 as 0). V (C, D)
- 0x479160 starts with `if ([0x6ffe54]==0) arg = 1.0`. 0x6ffe54 is 1 in the image (bytes 01 00 00 00, tools/recomp/asm.py read) and has no writer, so the value
  written to car+0x404 is used. Writers of car+0x404: RacerAI::UpdateRubberBand 0x44bff5 (AI) and Racer::UpdateTwoHumanCatchUp 0x429b8b (player, only with 2 players).
- The scale goes to **engine and grip and drag**: Engine+0xa0 (torque multiplier in 0x46cff0, x0.4 if car+0x86c and [[car+0x3c]+0x1c] != 0),
  body+0x1e8 (drag scale in 0x585410), wheel+0x17c on all 4 wheels (multiplies both the sliding and the static limit in 0x587330/0x587830).
  A second call at the end of 0x4774a0 uses car+0x484 (override when != 0 and car+0x86c == 0).
- Writing it from outside each frame: read once per frame at the top of 0x4774a0 (single thread); car+0x484, when != 0, overrides it at the end of that function.

## How the pieces fit (all V unless marked)

Per frame 0x4774a0: inputs -> wheel scales -> substeps (0x46aa40 Euler, dt/n) -> 0x4783c0 post step (drift yaw damping) -> CarState refresh 0x4789d0.

Objects (this of 0x4774a0, built by ctor 0x476840): +0x20 body (RigidBody), +0x28..+0x34 four Suspension (class name "Suspnsn"), +0x38..+0x44 four Wheel
(FL, FR, RL, RR; class name "Wheel"), +0x48 Engine, +0x4c DriveTrain (gear at +0x54), +0x54 CarPhysicsInfo, +0x58 CarState (= car+0x40), +0x5c Car, +0x78 base grip scale,
+0x7c handbrake ramp. Controls (this+4): +0x1d0 steer short, +0x1dc throttle, +0x1e0 handbrake, +0x1e4 brake (0x461650 writes them).

| Field | Meaning | Proof |
|---|---|---|
| wheel +0x108 | wheel torque; brake and handbrake torques subtract against spin | 0x587330 |
| wheel +0x10c | locked by brake (spin set to 0) | 0x587220 |
| wheel +0x155 | contact flag | 0x586f10 |
| wheel +0x158 | **load** = suspension force * alignment factor (min 0.3) | 0x586f10 |
| wheel +0x160 | longitudinal slip speed = radius*spin - ground speed | 0x587330 |
| wheel +0x16c | per-wheel flag from bit i of car+0x86c; when set the suspension builds an extra rotation (0x588580). Meaning I (special wheel state) | 0x4774a0, 0x588580 |
| wheel +0x170 / +0x174 | brake / handbrake input (rear only for handbrake); 0x4774a0 adds +0.5 to handbrake when 3c0 != 0 and slip > 0.3 rad under 80 mph... | 0x4774a0, 0x587330 |
| wheel +0x178 | per-frame grip scale (assist, 0.85, nitro/launch factors) | 0x4774a0, 0x479640 |
| wheel +0x17c | global power/grip scale from 0x479160 | 0x479160 |
| wheel +0x180 | drift-mode rear slide scale, default 1.0 | 0x479350, ctor 0x5868e0 |
| wheel +0x168 | grip use |F|/limit, 0..1 | 0x587830 |
| this+0x78 | base grip scale, ctor 1.0, x0.85 outside drift/drag when 3c0 == 0. Other writers U | 0x4774a0 |
| this+0x7c | assist ramp 0.5..1.0 | 0x4774a0 |
| body +0x1e0 | cap on yaw torque, 17.0 (phys+0x288) when 3c0 == 0 | 0x585410, 0x4774a0 |
| body +0x1e4 / +0x1e8 | drag coefficient (phys+0x290) / drag scale from 0x479160 | 0x585410 |
| CarState +0x374 | heading angle16; +0x30 velocity; +0x390 forward speed; +0x394 speed; +0x98 yaw rate | 0x4789d0 |
| CarState +0x3c0 | mode int, default 0 (ctor 0x464860). Set to 1 by 0x4bef54 when the player toggles per-player option [0x78a386+p*0x38]. Reads: x0.85 base grip, assist k, handbrake limit factor, engine braking x0.4. What the option is: U | xrefs |
| CarState +0x3c8..+0x3d4 | launch wheelspin pulse state | 0x479640 |
| phys +0x27c | front brake share (0.5..0.6); rear = 1 - it; brake torque factor = 2*share*brake | 0x4774a0 |
| phys +0x1c0 | rear drive split 0 FWD, 0.5 AWD, 1.0 RWD | D (all 35 cars) and rows of 0x6f0fc0 |
| phys +0x288/+0x28c/+0x290 | yaw cap 17.0 / alt cap 0.0 / drag 0.0 (stock) | 0x4774a0, D |

Mode flags (V): [0x78a344] drag event, [0x78a345] drift event, [0x78a346] third (U), [0x7361a8/a4/a0] the same three from the other setter,
[0x735fa0] drift mode (read by RideInfo::RebuildPhysicsInfo and IsDriftModeActive). Career sets them from event type [ctx+0x58a8]: 1 drag, 3 drift (0x4b5f32..0x4b5fcc).

Weight transfer, aero, drivetrain:
- Weight transfer has no formula of its own. Spring and damper force per corner (0x588580, progressive spring, bump/rebound damping, anti-roll preload) becomes wheel load
  (0x586f10); the body integrates the sum, so load moves with pitch and roll.
- Aero: drag = body+0x1e8 * body+0x1e4 in 0x585410. Downforce terms come from phys+0x264..0x27c upgrades; their consumer was not traced (U).
- Engine torque 0x46cff0: curve(rpm) * Engine+0xa0 * throttle, nitro adds curve * nitrous strength (info+0x2ac), rev limiter and engine braking. Gears and clutch live in the
  DriveTrain 0x46d9f0/0x46e020 (see names_car.tsv); not re-read here.
- Tire force (0x587330, 0x587830, 0x587740): sliding limit (surface 0x6ef2f8 * tire+0x10) and static limit (0x6ef2f4 * tire+0xc), both times +0x180 * +0x17c * +0x178 * load.
  Inside the static limit the lateral force is a curve of slip angle; past it the force is the sliding limit along the slip vector.

## Not done / open

- Whether body+0x38 is the forward vector z (I; the heading uses +0x30,+0x34 as x,y) matters only for the small |body+0x38| term in the assist.
- Meaning of CarState+0x3c0 option, [DriveTrain+0x68], [0x78a346], and other writers of this+0x78: U.
- No run was made. Everything is from code and data; the numbers in (a) are formula results, not measurements.
