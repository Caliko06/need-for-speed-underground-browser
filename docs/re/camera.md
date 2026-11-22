# Cameras (Speed.exe PC)

Marks: V = read in code or bytes this session, I = inferred, U = open. Tool after each claim: G = Ghidra 12.1.4 headless
(`tools/ghidra/gpar.sh`), H = Hopper export `census/hopper/decomp.c`, C = capstone `tools/recomp/asm.py`, D = bytes read
from the unpatched exe or `game/Global/GLOBALB.BUN` with python struct, M = PS2 map `ref/docs/re/out/x86-ps2-map.tsv`
(class-name hint only, never proof). Names and addresses: `census/names_camera.tsv`. Blur side: `docs/re/blur.md`.

## Answer

- **Selecting function.** `Player::ChangeCameraMover 0x42c6d0(player, type, flag)` is the factory. 23 types (0..0x16), jump
  table `0x42d2f4`, byte index table `0x42d330` (V, G+C). Each type is one mover object whose update is vtable slot 1.
- **Default camera in a race.** `0x42c670` (DefaultDriveCamera) asks the factory for type `([0x700aa4] != 0) ? 0x11 : 1`.
  `[0x700aa4]` is `1` in the unpatched exe image and Ghidra finds only reads of it (no code writer, no data pointer), so the
  shipped default is **type 0x11 CubicCameraMover** (update `0x48bcb0`). Type 1 DriveCameraMover (update `0x489690`) is
  the fallback if that byte were 0 (V for the value and the reads, G+C+D; I for "never written at runtime").
- **The key / option.** The camera button is joystick event `0x75` (`JOY_EVENT_CAMERA_POV_CHANGE`), looking back is `0x76`
  (`JOY_EVENT_CAMERA_LOOKBACK`); name pairs at `0x6f1850`/`0x6f185c` (D). Event `0x75` calls `Player::CyclePOV 0x42e020` (call at
  `0x431a32`, V, C). The physical key comes from the user's control config and was not read (U).
- **View codes (POV).** 5 rows per car: id 0 far chase, 1 close chase, 2 hood, 3 bumper, 4 high chase (names I, from the
  numbers). Cycle: `0x42e020` walks 4 slots stored in options `0x758938..0x758944`, 3 maps to 0, and the 4th slot needs
  `[0x78a345]` or `[0x7361a4]` (V code, G+C; names I).
- **Per-car or global.** Distance, height, lateral and a pitch word are **per car data** (CarTypeInfo chunk `0x34600`, 5 rows
  per car, almost identical for all 35 cars: only chase height is 1.7 vs 1.9). FOV is a **global** table `0x6fbdf4`.
  The smoothing and collision constants are global (V, D+C).
- **Speed-dependent FOV or shake in chase.** None found in `0x489690` or `0x48b8c0`: FOV is `table[pov]` only. Camera shake
  exists as a separate system (`0x575040`, `0x575200`) but I did not trace what triggers it in a normal race (U).
- **Free Run vs race vs garage.** Same factory and same default type in Free Run and a race (gates are identical; see below).
  Garage and front-end show cars with `SelectCarCameraMover` (not read, U). Countdown, intro, flyby and end cameras are
  coordinators that call the same factory (I).

## 1. Mover types (V, G+C: jump table; class names: EH = Ghidra unwind map V, M = PS2 map I)

| Type | Ctor | Size | Vtable | Update (slot 1) | Class | Name source |
|---|---|---|---|---|---|---|
| 0 | none | | | | clears the mover | V |
| 1 | 0x489360 | 0x3a0 | 0x6c7fc8 | 0x489690 | DriveCameraMover | M |
| 2 | 0x488420 | 0x4c | 0x6c7d80 | 0x488ae0 | DebugWorldCameraMover | EH |
| 3 | 0x4892c0 | 0x2c | 0x6c7c50 | 0x40a880 (a bare `ret`) | NullCameraMover (does nothing) | V, C |
| 4..12 | 0x4840c0 | 0xd0 | 0x6c8018 | 0x4843e0 | OrbitCarCameraMover | EH |
| 0xd | 0x48f090 | 0x368 | 0x6c7b98 | 0x4901e0 | ZoneFreezeCameraMover | EH |
| 0xe | 0x490ea0 | 0x450 | 0x6c7b50 | 0x492700 | ZonePreviewCameraMover | EH |
| 0xf, 0x10 | 0x4854e0 | 0x470 | 0x6c7d28 | 0x485c00 | TrackCarCameraMover (jump views) | M |
| 0x11 | 0x48afd0 | 0x54 | 0x6c7e58 | 0x48bcb0 | CubicCameraMover (default race camera) | EH |
| 0x12 | 0x48c1f0 | 0x2c | 0x6c7f80 | 0x48c220 | name U; created after AutoPilotOn in `0x42d520` | I |
| 0x13 | 0x48c280 | 0x38 | 0x6c7ea8 | 0x48c820 | DragRaceCameraMover | M |
| 0x14 | 0x48c990 | 0x58 | 0x6c7dc8 | 0x48d3b0 | DragRaceLeaderCameraMover | M |
| 0x15 | 0x48d6e0 | 0xa0 | 0x6c7ce0 | 0x48df00 | DragRaceAheadCameraMover | M |
| 0x16 | 0x48e210 | 0x310 | 0x6c7c08 | 0x48e490 | AnimationControllerCameraMover (NIS) | M |

Notes.

- Types 0x12, 0x13, 0x15 are refused while `[[0x7361f0]]` is 5, 6 or 10 (V, G+C). The mover's base ctor `0x4834e0` takes a kind id
  in edx (3 for the null mover, 6 for the rear mirror) (V, C).
- **Correction to earlier notes:** type 3 is not the rear-view mirror. The mirror is `RearViewMirrorCameraMover` (ctor
  `0x4852a0`, vtable `0x6c7e10`, update `0x485300`), created at `0x42c3c0` into `Player+0x288`, outside the factory (V, C+D).
- Other factory call sites (V, C): `0x4241fc` (type 0), `0x42d881` (0x12), `0x42dbcf` (0xd), `0x42dc27` (0xe), `0x42dd0c` (0xf),
  `0x42dd48` (0x10), `0x42df30` (debug cycler: types ebx, 4, 2, 3), `0x430a25` (0xd), `0x430d49`, `0x430d6c` (0x11), `0x430da3` (1)
  in `0x430730`, `0x47f002`/`0x47f795` (0x16, NIS), `0x47ef00` (IntroNis coordinator).
- Special strings: `CountdownCameraCoordinator` `0x6ca8dc`, `CubicCameraMover(DCC)` `0x6c8160`, `SpeedCam` `0x6c8060` (xref
  `0x48e949`), `DragCameras.bin` `0x6c806c` (`0x482fc0` = DragCameraManager::SaveData), `CAMERA SETTINGS` `0x6c80f4` (table `0x6fc59c`) (D).

## 2. Special modes (V, G+C; the names of modes 3..5 are I)

`Player::StartSpecialCamera 0x42da40` writes `ctrl+0x60 = mode`:

| Mode | Name | Mover | Notes |
|---|---|---|---|
| 0 | NONE | | |
| 1 | FREEZE | 0xd ZoneFreeze | |
| 2 | PREVIEW | 0xe ZonePreview | |
| 3 | SLOMO | | slow motion `0x420050` |
| 4 | SLOMO2 | | |
| 5 | WARP | | slow motion only |
| 6 | JUMPVIEW | 0xf + `0x42c640` | jump trigger `0x426930` |
| 7 | JUMPVIEW2 | 0x10 | |

Name table `0x700b1c`, enable bytes `0x700b44` = [0,0,0,1,1,1,1,1] (D). Gates (V, G+C): `[0x78a345]`, `[0x78a346]`,
`[0x7361a0]`, `[0x7361a4]`, `[[0x7361f0]] == 9`, `[[0x73619c]] != 4`, a cooldown (`0x421a30`, `ctrl+0x70+mode*4`), two players
(`[0x7361c4] == 2`) block it, modes 6 and 7 need byte `[0x78a3fa]` (from option `[0x758951]`, `0x4b47a0`), modes 1..5 need `[0x78a3fb]`.
Callers of `0x42da40` (G callers): `0x426930` (jump trigger, every 8 frames), `0x465d00` (the earlier notes call it the crash camera, I),
`0x431960` (three call sites). Each start sets `[0x73654c] = 1` (this is the flag that drives the blur n ramp) and `ctrl+0x270 = 1`
(camera cut). Jump view (V, G+C+docs): curves `0x7062fc` speed, `0x7062cc` height, `0x7062e4` distance; the camera point is placed at the
route-node edge +- 2.0 m (`0x6b7aac`), z + 1.0, ground check `0x440a40`; no collision after placement.

## 3. POV selection and options (V, G+C)

- `0x42e020` cycles the 4 POV codes in `ctrl+0x2c..0x2f` (current mod 5). Valid codes 0..5 except 3 (else 0). It finds the
  car's row table with `0x47d680`, tells the mover through vtable slot `+0x20` (SetPOV), and stores the cycle index in
  `(&0x758948)[player]` and the code in `(&0x78a388)[player * 0x38]` = `(&0x758938)[idx * 4]`.
- `0x4b47a0` (ApplyOptionsToPlayerSettings) copies the options to the player settings: `[0x78a3fa] = [0x758951]`,
  `[0x78a388] = (&0x758938)[[0x758948] * 4]` (index 3 reset to 0 unless `[0x78a345]` or `[0x7361a4]`). Player 1 uses `0x78a3c0` and `[0x75894c]`.
  The options screen is `0x4be6c0` (I). The defaults of `0x758938` are not in the raw exe image (runtime data, U).

## 4. The per-car rows (V, D+C; names of the codes I)

Each `CarTypeInfo` record (chunk `0x34600` in `game/Global/GLOBALB.BUN`, file `0x199e00`, payload +8, 35 records of `0xc90`; the
record name is at +8 in the file, the in-memory struct is 8 bytes earlier) holds a table at `info+0xb50`:

- `+0` count (5), `+4` second count (5), rows of 16 bytes at `+0x10` (normal) and at `+0x60` (second set, used when `[0x7364a0] == 3`).
- `0x47d680` (FindCameraRow) matches the first s16 of a row with the POV code (V, G+H+C).
- Row layout: `{s16 id, s16 aux, f32 distance, f32 height, f32 lateral}`. `0x489690` uses `-distance`, so negative means behind
  the car; `aux` goes to a mover field (500 and 3040 look like pitch words, 65536 = 360 degrees, I).

First set, identical in all 35 records except the chase height (D; all 35 records read):

| POV id | Role (I) | distance | height | lateral | aux |
|---|---|---|---|---|---|
| 0 | far chase | -5.8 | 1.7 (GOLF, FOCUS, PEUGOT: 1.9) | 0 | 0 |
| 1 | close chase | -4.7 | 1.7 (same three: 1.9) | 0 | 0 |
| 2 | hood | 0.72 | 0.79 | 0 | 500 |
| 3 | bumper | -0.19 | 0.81 | -0.44 | 0 |
| 4 | high chase | -5.8 | 3.45 | 0 | 3040 |

Second set (printed for GOLF and FOCUS only, the other 33 records NOT VERIFIED): 0: -8.2 / 1.85, 1: -6.8 / 1.7, 2: 0.72 / 0.64 aux -1342,
3: -0.26 / 0.77 lateral -0.31, 4: -8.2 / 3.45 aux 2027.

In `0x489690`, POV 0, 1 and 4 add a speed-blend term to the distance: `(1 - v) * k - row.distance` with `v = 1 - 0.5 * (f + 1)`, `f` from `0x564b10`
(constants `[0x6cc7bc]` = 1.0, `[0x6cc7dc]` = 0.5, `k` a local; the meaning of f and k is U); the other POVs use `-row.distance` (V, C). A tweaker (`[0x735ee8] != 0`) replaces the rows by `[0x6fbde8]`/`[0x6fbdec]`
(2.3125)/`[0x6fbdf0]` (10000) defaults (I).

## 5. FOV (V, G+C+D)

Global table `0x6fbdf4`, s16 per POV code, 65536 = 360 degrees: codes 0, 1, 4 = `0x32dc` = 13020 = 71.5 degrees; codes 2, 3 =
`0x4000` = 90 degrees. Read by `0x489690` (write to `*(ctrl+0xc4)`, `+0xbc = [0x6fbf1c]` for POV 3), by the Cubic mover
`0x48b8c0` and by `0x480750` (Ghidra scalar search of `0x6fbdf4`). The rear mirror forces `0x4e20` = 109.9 degrees when
`[0x735f5c] == 0` (`0x485300`, also `+0xbc = 0.75` `[0x6b6cbc]`, `+0xc0 = 192.0` `[0x6b6cc0]`). Projection builder `0x40dd00`, focal `0x40dcb0` (I).

## 6. DriveCameraMover (type 1, the fallback) `0x489690`

Verified structure (V, G+H+C): it picks the player's car (`ebx[0xb]`, or a debug id `[0x6fbf18]`), moves a heading filter toward the
car's velocity heading, finds the row (`0x47d680`), builds an eye from distance and height, adds road-roughness noise
(`0x441d80`, surface table `0x6ef2d0` stride 0x94), and runs the wall push-out `0x4838e0` (sweep `0x441030`, then up to 3 passes).
Bumper and hood types clamp z to ground (`0x440a40`) + 0.7. Heading history lives at `ebx[0xcd..0xe5]`.

Constants it reads (D values; **meaning of each is U** unless a note says otherwise): `0x6fbec0` = 1.0 (rewritten every frame, scale of
all following), `0x6fbec4` 0.03, `0x6fbec8` 0.012, `0x6fbecc` 2.0, `0x6fbed0` 25, `0x6fbed4` 0.05, `0x6fbed8` 0.02, `0x6fbedc` 6.0,
`0x6fbee0` 0.6, `0x6fbee4` 0.045, `0x6fbee8` 0.7, `0x6fbeec` -0.3, `0x6fbef0` 1.0, `0x6fbef4` 1.0, `0x6fbef8` 500, `0x6fbefc` 0.2,
`0x6fbf00` 6.0, `0x6fbf04` -1, `0x6fbf08` 0.4, `0x6fbf0c` 3.0, `0x6fbf10` 250, `0x6fbf1c` 0.4. In the code `0x6fbee4 * scale * x`
is compared with `0x6fbeec * scale` (I: a lateral-speed threshold and gain, each to pick a sign branch) and `0x6fbee0`/`0x6fbee8` form a second
band (I). Values with `[0x7364a0] == 3`: `0x6b6c5c` = 18.0, `0x6b6c60` = -3.0, `0x6b6c64` = 16.0, `0x6b6c68` = -1.0 (blend distance and height
between modes). Airborne ramp step `0x6b6c78` = 0.24316 (only read by `0x489690`, G xref), sweep trim `0x6b6c80` = 0.01, wall push-out `0x6b6c98` = 0.7, speed curve
`0x705b20` through `0x583f20` (I).

## 7. CubicCameraMover (type 0x11, the default) `0x48bcb0`

What is verified (V, G+H+C unless noted): ctor `0x48afd0` allocates smoothing sub-objects of size 0x30 and 0x90 (`0x42ad10(x, 10.0)`, `0x4830f0(10.0)`) and calls `0x48ead0(0.5)`. Update `0x48bcb0` (about 2200 lines in Hopper, most of it
duplicated branches) chooses the player's car like `0x489690`, calls `0x48ec00` to produce the target and eye parameters, runs the
sub-objects, applies `Camera::ApplyNoise 0x483640`, `ApplyCameraShake 0x575040`, `MinGapTopology 0x483b90`, and ends in
`Camera::SetCameraMatrix 0x47d070`. `SetDesired 0x48b8c0` (M name) reads the desired distance, height and lateral from the car row (its
first argument is the row, because it indexes the FOV table with the row's first s16): V for the FOV read, I for "same row data".
Fallback numbers when the car's dword at `car+0xa4` is 0 and mover flag `[0x45]` is set: table `0x705af0`, stride 16, set 0 = (-17.2, 6.0,
aux 5200 `[0x6b6c58]`), set 1 (when `[0x7364a0] == 3`) = (-15.8, 4.4, aux 3540 `[0x6b6c5a]`) (D; use I). Debug values `0x705c60..68` = (-10, 0, 5).
**Not done (U):** the per-constant meaning of the 10.0 smoothing parameters, the `0x48ec00` math, and the speed behaviour of this mover.

## 8. Shake and noise (I/U)

- `ApplyCameraShake 0x575040(effect id, matrix)`: a switch on the effect id, table `0x73b220` (32-byte entries), rotation scales
  `0x704508`, `0x704514`, `0x704518`; called by `0x485300` (rear mirror, V) and by the Cubic update (V, call sites). The trigger is U.
- `MaybeCameraShake 0x575200`: caller `0x420fd2` (I).
- `Camera::ApplyNoise 0x483640` with parameter tables `0x6b6f08`/`0x6b6eb8` from `0x48c1b0` (I). `CameraMover::VelocityNoise 0x527480`: caller `0x52c7ce` (I).

## 9. Free Run vs race vs garage

- **Race and Free Run (I).** The same `0x42c670` choice (type 0x11) and the same special-mode gates; an earlier WORLD runtime table
  (`re_jumpcam`) shows the same gates in Free Run. A difference by game mode exists in the factory block list (`[[0x7361f0]] in {5, 6, 10}`)
  and in `[0x7364a0]` (row set, view count kind). Which row set a normal single-player race uses (`[0x7364a0]` value) is U: the
  values 0..3 are set by `0x408370`/`0x408410` from the view list `[0x740504]` (G xrefs, C).
- **Garage and front end (U).** Showcase cars are drawn by `0x570950`; the camera class is `SelectCarCameraMover` (M: ctor `0x486c80`, Update
  `0x4870c0`, GetMainStaticCameraPosition `0x487590`). Not read.
- **Cinematics (I, M).** Countdown `0x47edb0`/`0x47ee50`/`0x42c3e0`, IntroNis `0x47ef00`, EndingNis `0x47f680`, PreRace `0x47eae0`,
  FlyBy `0x47ea20`, PostRace `0x47eca0`, DemoCamera `0x47e250`.

## Open (U)

- The physical key bound to events `0x75` and `0x76`; defaults of options `0x758938..`.
- Per-constant meaning of the block `0x6fbec0..0x6fbf1c`, and the whole Cubic mover maths.
- Which row set (normal or `[0x7364a0] == 3`) applies in single-player races; second set of rows for 33 cars.
- Replay cameras (`ReplayManager` strings `0x6cae54`, `RCSTATE_CAMERA_FLYBY` `0x6cb078` -> `0x423070`), crash camera, finish camera `0x42d9a0`.
- Speed-dependent shake in a normal race; the trigger of `0x575040` for effect ids.

## Second-tool agreement (10 names drawn with `random.seed(20261029)` from the V/I rows of both registries)

| Name | Primary | Second tool and result | Result |
|---|---|---|---|
| `0x6b6c78` CamAirborneRampStep (blur doc not involved) | D value, C | G xref: one read, in `0x489690` at `0x48a3b6`; value 0.24316 | agree on the read and value; the meaning stays I |
| `0x6c7fc8` vtable_DriveCameraMover | D | G xref: data refs in the ctor `0x489360` and in `0x4894b0` (destructor); slot 1 = `0x489690` read from bytes | agree |
| `0x6cc9d8` 4.0 | C+D | G xref: four reads in `0x40cd40`, plus `0x438b60` and `0x606110` | agree; shared constant |
| `0x705b34` RearView_Offset_x | C+D | G xref: one read, in `0x485300` | agree (0.5) |
| `0x48c1f0` type 0x12 ctor | C | G decompile: ctor only sets vtable `0x6c7f80` and zeroes `camera+0x280` when `[0x735f5c] == 0` | **disagree on the name**: "AutoPilotCameraMover" dropped, now "CameraMover_Type12" (I) |
| `0x7364a0` | C | G xrefs: writers `0x408370`, `0x408410`; readers include `0x42e020`, `0x47d680`, `0x489690`, `0x592100`, `0x56dc30` | **disagree**: it is a view-count kind (0..3), not a game flow; renamed `gViewCountKind` |
| `0x465d00` | C | G callers of `0x42da40`: `0x4662f3` in `0x465d00` | agree on the call; "crash camera" not confirmed (I) |
| `0x73641c` | C | G xref: only `0x40cd40`, writes at `0x40cd8a`, `0x40cd9e` | agree |
| `0x4b47a0` | C | G decompile: copies options to player settings (`[0x78a3fa] = [0x758951]`, `[0x78a388]` from `0x758938`) | **disagree on the name**: not "Save", it is "Apply"; renamed |
| `0x700e9c` OPT_LIGHTSTREAKS | C | G xref: readers `0x40cb80` `0x40b3f0` `0x409580` `0x4160b0` `0x410ce0`; writers `0x410a00` `0x410ce0` `0x410ed0` `0x416a40` | agree |

Result: 7 agree, 3 corrected (two names, one class identity), all in the registry.
