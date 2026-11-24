# HUD and input (Speed.exe PC): FEng HUD widgets, minimap, DirectInput8 action maps, EZ Wheel wrapper

> Source: `docs/re/hud_input.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 235

# HUD and input (Speed.exe PC): FEng HUD widgets, minimap, DirectInput8 action maps, EZ Wheel wrapper

Marks: V = a second tool agrees (Ghidra export G and Hopper export H show the same callee set, at least 80 %, and/or capstone C over
pc/Speed.exe confirms a cited instruction or constant), I = inferred from one tool or from the shape of the code, U = open.
A V on a name means the structure it rests on was seen by two tools; the English name itself is still my reading.
Prior notes (docs/re_minimap.md, docs/re_audio_default.md) were D; only what was re-read in the binary is reused here.
Names: census/names_hud.tsv (58 rows, 50 V / 8 I) and census/names_input.tsv (50 rows, 23 V / 27 I). None of these addresses was in another names file.

## Answer
- The in-race HUD is not drawn by 17 draw calls. It is 17 small widget objects (one per gauge) owned by a `HudManager` per player (player +0x95c).
  Each widget holds FEng objects found by name hash at construction. Each frame the game computes a 64-bit visibility mask per player
  (`0x42e620`), `HudManager::SetFlags` (`0x4a9540`) shows or hides each widget's FEng objects when its bit changes, `HudManager::Update`
  (`0x4a9440`) calls each widget's update to write numbers and run scripts, and the FEng package itself is drawn later by `0x409cd0` -> `0x4f3030`.
  The minimap is separate: `TrackMap::Draw 0x58e810` runs inside the same pass (V G+H+C).
- Input is DirectInput 8 "action mapping": two DIACTIONFORMAT tables (Game, 40 actions; Menu, 36 actions) for the keyboard, plus a bundled
  "EZ Wheel Wrapper v4.26" (plain DIJOYSTATE + force feedback) for wheels and joysticks. Both fill one 0x270-byte slot per device; the slots
  are merged into one 64-bit button mask plus 4 axis bytes, and `InputEvents::Update` turns that into JOY_EVENT ids per player (V G+H+C).

## Flow of input (poll -> action -> game)
1. Startup: window init `0x408830` calls `0x413000` (DirectInput8Create into 0x736350). Later `InputEvents::Init 0x5741c0` creates
   SlotPool "EventNodeSlotPool" and calls `Input::Init 0x405660`: AddRef (vtable +4), `0x4075e0` fills the two DIACTIONFORMAT headers
   (dwSize 0x148, action size 0x28, genre 0x1000000, GUID 5a589134-30914687-9d68236f, "NFS Underground Game" / "... Menu"; C `mov edx,0x148` @0x407618),
   `EnumDevicesBySemantics` (vtable +0x24, C `call [edx+0x24]` @0x4056a7) with callback `0x405630`, then `malloc(0x2c18)` -> `EZWheel::Create 0x419c60` into 0x736500 (C `push 0x2c18` @0x4056aa).
2. Callback `0x405630` (dwDevType at +0x24 == 0x13, DI8DEVTYPE_KEYBOARD) -> `0x405c60`: keyboard device kept in 0x7187c8, slot = 0x78daa8 + n*0x270,
   `0x407ca0` copies the default action tables (Game 0x702c98 -> live 0x7187d0, Menu 0x7032d8 -> 0x718fa0) and the template headers 0x719b38/0x719c80
   into the live DIACTIONFORMATs 0x719798 (Game, index 0) and 0x7198e0 (Menu, index 1); BuildActionMap (+0x74), SetActionMap (+0x78).
3. Wheels: `EZWheel::CreateDInputAndEnumerate 0x418e10` (DirectInput8Create, EnumDevices class 4 = game controllers) -> callback `0x418e70` -> `OpenChannel 0x418ee0`
   (CreateDevice +0xc, SetDataFormat +0x2c, SetCooperativeLevel +0x34, autocenter off). Handle per channel in 0x71d89c[2]; flags 0x71d888 (FF wheel), 0x71d88c, 0x71d898, 0x71d890.
   `Input::AssignNewWheels 0x4058d0` gives a free slot (of 6) to each channel with a handle: `0x4063a0` sets slot +0x130 = channel and +0x134 = 0x16 / 0x14 / 0x15 (driving / joystick / gamepad).
   `Input::DropUnpluggedWheels 0x405860` frees slots whose handle vanished.
4. Per frame (end of the render frame `0x40a580`, also in the loading loops `0x401520` / `0x4016e0`): `0x405860`, `0x4058d0`, `Input::SelectActionMapForGameState 0x4057c0`
   (race -> Game map index 0, menus -> Menu map index 1, via `0x407760`), then `EZWheel::Poll 0x419ea0` (re-enumerates every 32nd call, C `and ecx,0x1f` @0x419eb5)
   which runs `EZWheel::ReadChannel 0x419220` for 2 channels (Poll +0x64 @0x41924f, Acquire +0x1c, GetDeviceState +0x24, 0x110 bytes = DIJOYSTATE copied to 0x71d8a8 + ch*0x110). Sets DAT_0073650c = 1.
5. Main loop `0x447600` calls `InputEvents::Update 0x573cb0`: while 0x73650c is set it clears it and, for the 2 players (0x73b260 + n*0x18c, C `imul ebx,ebx,0x18c` @0x573fd9),
   calls `Input::GetState 0x405980` (C `call 0x405980` @0x573e05). GetState reads every slot with `InputDevice::ReadState 0x406580` (-> `0x4070a0`: keyboard GetDeviceData +0x28
   with 0x14-byte elements, wheel buttons at DIJOYSTATE+0x30 = 0x71d8d8, POV, axes scaled to bytes), merges into the aggregate 0x719780 (mask, 0xffffffff = nothing pressed) and previous frame 0x7187b8,
   then services force feedback (`0x41a250`, `0x41b150`, `0x41b830`, `0x41bb30`).
6. `InputEvents::MatchBindings 0x573ab0` asks every source node of the player (matcher at profile +0xc) for an event, and `InputEvents::PostEvent 0x573c30` appends 12-byte records
   (short id, byte player, byte source) to the output array at 0x73b578 (cap 0x100). Ids are the JOY_EVENT numbers (name table at 0x6f1704..0x6f19f4, e.g. STEER 0x88, THROTTLE 0x8a,
   BRAKE 0x8d, EBRAKE 0x92, SHIFTUP 0x94, RESET_CAR 0x9a, NITRO_BOOST 0x9c, PAUSE 0xac, AUTO_PILOT 0xa6, CYCLE_HUD 0xab). The game objects (car, camera, menu) read them from that array; the consumers were not traced (Open).
7. Controls screen: `0x413a70` (title keyboard_config_title) lists slots; `ControlsScreen::SetBindingLabel 0x414830` writes the bound key/axis name (keyboard `0x4079f0`, wheel `0x407800`);
   a rebind sets slot +0x23c, `InputKeyboard::PollRebindCapture 0x406b10` waits for a key (GetDeviceData, GetObjectInfo), `InputKeyboard::ApplyRebind 0x406f00` writes it into the live list 0x7187d0 and re-applies both maps.

### Action tables (V: read from the exe with capstone/rd, 40 + 36 rows of 0x28 bytes: uAppData, dwSemantic, flags, name pointer)
Game table 0x702c98, two semantics per action (arrows and numpad): Throttle (app 1, DIK 0xc8 UP / 0x48 NUMPAD8), Brake (2, 0xd0 DOWN / 0x4c NUMPAD5), Left (3, 0xcb / 0x4b NUMPAD4), Right (4, 0xcd / 0x4d NUMPAD6), Handbrake (5, 0x36 RSHIFT / 0x2a),
Nitrous (6, 0x39 SPACE / 0x31 N), Shift Up (7), Shift Down (8), Look Back (9), Camera (0xa), HUD (0xb), Pause (0xc, 0x01 ESC / 0x19 P), Respot (0xe),
then Debug Camera actions 0x26..0x33. Menu table 0x7032d8: Menu Up/Down/Left/Right (0x10..0x13), Select (0x14), Select Alternate (0x15), Help (0x16), Back (0x17), Customise (0x18), Button 2/3 (0x19, 0x1a),
L1/R1 (0x1b, 0x1c), Rotate (0x1d..0x20), Zoom In/Out (0x21, 0x22), Preset (0x23), Quit (0x24), Race Options (0x25). Semantic = 0x81000400 | DIK (DIKEYBOARD_*); the DIK names in brackets come from that formula and the standard DIK table (I).

### Slot structure (0x78daa8 + n*0x270, 6 slots; read by 0x405860, 0x4058d0, 0x406580, 0x4070a0, 0x405c60, 0x4063a0)
+8/+0xc 64-bit button mask (1 = not pressed after the AND), +0x10..+0x13 axis bytes (0x80 centre; +0x12 steer; +0x11/+0x10 throttle/brake), +0x118 current action map index, +0x11c..+0x128 keyboard guid,
+0x130 channel (-1 free), +0x134 DI8 device type (0x13 keyboard, 0x14 joystick, 0x15 gamepad, 0x16 driving), +0x138 name string, +0x23c pending rebind action, +0x240 binding half (0/1),
+0x244..+0x268 wheel axis config. Aggregate state 0x719780 (mask), 0x719788 (4 bytes), previous 0x7187b8. Player event list head 0x73b260 + n*0x18c.

## Flow of HUD per frame (who draws what)
1. Game loop `0x447600` -> `Players::UpdateAll 0x4311c0` -> `Player::UpdateFrame 0x430b90` per player.
2. `0x430b90`: state switch on 0x7361f0, then `Player::ComputeHudFlags 0x42e620` (returns the 64-bit mask in edx:eax; C `mov edi,0x40000` @0x42e65d, `or edi,0x20000000` @0x42e72e).
   If it differs from player +0x4b0/+0x4b4, `Player::SetHudFlags 0x42ed40` runs `HudManager::SetFlags 0x4a9540` and stores it. Then `HudManager::Update 0x4a9440` (C `mov eax,[esi+0x95c]` @0x430dd9, `call 0x4a9440` @0x430de9).
3. `HudManager::HudManager 0x4a8e40` is built by the player constructor `0x42b0d0` (V H callers). Slots and bits (SetFlags tests, Update dispatches; widget ctor stores the same offset):

| slot | mask bit | widget ctor | update | FEng objects (from the ctor, capstone) |
|---|---|---|---|---|
| +0x18 | 0x40 | 0x4a03d0 HudTach | 0x4a0f50 | RPM_%d, rpm_fill, Redline, Shift_light, 3rdPersonNeedle/Speed/Gear, PerfectShift, MissedShift |
| +0x38 | 0x40 | 0x4a3f00 HudTachDrag (drag races) | 0x4a4a50 | DRAG_Shift_light, ShiftMessage, gear_fill, speed_backing |
| +0x1c | 0x40 | 0x4a1290 HudTurbo | 0x4a13a0 | 3rdperson_Turbofill/lines/dial/TurboRed, TurboPSI, TurboPlus/Minus |
| +0x20 | 0x200 | 0x4a00c0 HudPosition | 0x4a01a0 | RacePositionNumber/Nth, NumberRacers, RaceTime |
| +0x24 | 0x20000000 | 0x4a5860 HudEngineHeat | 0x4a5b60 | EngineTemp, heat_fill, heat_lines, back_heat_%d |
| +0x28 | hi 0x40000 | 0x4a5ca0 HudNos | 0x4a67a0 | nos_fill, nos_lines, NOS_bar_%d_%d, SR_NOS_Text |
| +0x2c | 0x80000000 | 0x4a6f10 HudSpeedTrapDrift | 0x4a7660 | SpeedTrap_Speed_DATA, SlowMessage, 3rdperson_driftometer, drift_multiplier_text |
| +0x30 | 4 | 0x4a7c90 HudRaceOver | 0x4a7d60 | RaceOverMessage, Top/BottomVignette |
| +0x34 | 0x10000 | 0x4a68a0 HudSmokeApplause | 0x4a6a10 | applause_bar, smoke_shape_*, score_*_text, timer_box |
| +0x3c | 1 | 0x4a8140 HudTrackMap | none (see TrackMap::Draw) | track_map_placeholder, TrackMapStart/Finish |
| +0x40 | 0x400 | 0x4a1580 HudLapCounter | 0x4a1820 | LapNumber, NumberLaps, CurrentLapTime, BestLapTime |
| +0x44 | 0x800000 | 0x4a1f40 HudLeaderboard | 0x4a2b10 | LBData_%d, LeaderText_%d, LBBacking_%d |
| +0x48 | 0x4000 | 0x4a3ba0 HudWrongWay | 0x4a3c60 | WrongWayImage/Text/CountDown |
| +0x4c | 0x80 | 0x4a1b50 HudSplitTime | 0x4a1bf0 | SplitTimeText, SplitTimeLapTime |
| +0x50 | 0x20000 | 0x4a8200 HudStylePoints | 0x4a83c0 | Style_Points_Title, SP_*, Style_Point_Backing* |
| +0x54 | (online only) | 0x4a8b80 HudOnline | 0x4a8cb0 | Online_DATA_01/02 |
| +0x58 | hi 0x20000 | 0x4a7f90 (U) | 0x4a8000 | no FEng names found |

(The standard tach and the drag tach both react to bit 0x40; the ctor picks one: `0x78a344 || 0x7361a8` -> drag. Slot +0x24 uses `uVar2 & 0x20000000`, slot +0x28 and +0x58 test the high word `uVar3`.)
4. Widget base: +0/+4 object list, +8 FEng package, +0x10/+0x14 widget mask, +0x18/+0x1c last mask. `HudWidget::SetVisible 0x49fec0` shows or hides every object in the list;
   lookups use `FEng::HashName 0x4fd230` (h = h*33 + toupper(c), start -1; C `imul eax,eax,0x21` @0x4fd240) then `0x49fdb0` (text objects, type 2) / `0x49fe10` (images, type 1) / `0x49fe70`;
   updates write text with `FEObject::SetFormattedText 0x4f68a0`, change visibility with `0x4f6910` (set invisible, flag bit 0 + 0x400000) / `0x4f6970` (visible), and play animation scripts with `FEObject::SetScript 0x4f6b70` ("FadeIn", "ZoomIn", "Blink", "Highlight").
5. Draw: the render frame `0x40a580` calls `Hud::RenderPass 0x409cd0` twice (arg 1 and 0): Z off, `FEng::RenderPackages 0x4f3030` (ePoly 0x40be70/0x40bef0, textures by 0x5461c0), then per player `TrackMap::Draw 0x58e810`.
6. Minimap: `TrackMap::TrackMap 0x58e540` (texture TRACK%d_MAP, INGAMEB icons, mode table 0x737850 by `0x5912b0`), `TrackMap::Draw 0x58e810` -> heading `0x58efb0`, backdrop `0x58fa50`,
   quad `0x58f090` (alpha multiplied by mode row float +0x34, C `fld [ebp+0x34]`; clip `Poly2D::ClipToRect 0x58fb10`), icons `0x58f640`, world to map `0x590ad0`; mode chosen by `TrackMap::SelectMode 0x42e4f0`. G and H have identical callee sets for all of these. Pixel-level claims (pale alpha 0.2, never-drawn frame) stay in docs/re_minimap.md as D.

## Functions by stage
Input startup/slots: 0x413000 0x405660 0x4075e0 0x405630 0x405c60 0x407ca0 0x405570 0x4057c0 0x405860 0x4058d0 0x4063a0 0x405fa0 0x407760.
Read/rebind: 0x406580 0x4070a0 0x405980 0x406b10 0x406f00 0x4079f0 0x407800 0x414830.
Events: 0x5741c0 0x574020 0x574a00 0x573ab0 0x573c30 0x573cb0 0x5742b0.
EZ Wheel: 0x419c20 0x419c60 0x419d60 0x419e40 0x418d70 0x418d10 0x418e10 0x418e70 0x418ee0 0x419220 0x419ea0 and effects 0x419900 0x419ab0 0x41bda0 0x41bf20 0x41c070 0x41c240 0x41bab0 0x41bb30 0x41bbb0 0x41bc60 0x41bcf0.
HUD core: 0x4311c0 0x430b90 0x42e620 0x42ed40 0x4a8e40 0x4a9440 0x4a9540 0x49fec0 0x4a9900 0x49fe70 0x49fdb0 0x4fd230 0x4f6910 0x4f6970 0x4f68a0 0x4f6b70; 16 widget ctors and 15 updates (table above); frame/minimap 0x409cd0 0x4f3030 0x58e540 0x58e810 0x58f090 0x58f640 0x58fa50 0x58fb10 0x590ad0 0x5912b0 0x42e4f0.
Already named elsewhere (not repeated): 0x49fe10 HudElement::RegisterImage, 0x4a5a30 EngineTempGauge::BuildTempBarImageList.

## Second-tool agreement (10 re-derived names)
G = Ghidra export, H = Hopper export, C = capstone over pc/Speed.exe. Name read from G first; H asked the same question; C confirms an instruction.
| addr | name | what was re-derived | result |
|---|---|---|---|
| 0x4a9440 | HudManager::Update | 16 per-slot update calls | G&H share 16 of 17 callees (the 17th is G self-call); C: `call 0x4a0f50 / 0x4a4a50 / 0x4a8000 / 0x4a2b10` |
| 0x4a9540 | HudManager::SetFlags | mask bits 0x40 0x200 0x20000000 0x80000000 0x800000 ... and `0x49fec0` | all 11 constants in G and H; C: `and ecx,0x80000000` @0x4a964f, `and edx,0x40000` @0x4a962f |
| 0x4fd230 | FEng::HashName | multiply 33, fold a..z | G, H agree (H shows `*0x21`, `0x61..0x7a`); C: `imul eax,eax,0x21` @0x4fd240, `cmp cl,0x61` @0x4fd243, `cmp cl,0x7a` @0x4fd248 |
| 0x4075e0 | Input::InitActionFormats | 0x148, GUID dwords, genre 0x1000000, "NFS Underground Game/Menu" | G has all 9 constants, H 7 of 9 (two GUID words folded); C: `mov eax,0x5a589134` @0x4075e5, `mov edx,0x148` @0x407618 |
| 0x405660 | Input::Init | vtable +0x24 EnumDevicesBySemantics, malloc 0x2c18, callees 0x4075e0 / 0x419c60 | G&H share 0x2c18 and 0x24; C: `call [edx+0x24]` @0x4056a7, `push 0x2c18` @0x4056aa |
| 0x419220 | EZWheel::ReadChannel | DIJOYSTATE size 0x110, Poll +0x64, Acquire +0x1c, GetDeviceState +0x24, actuators +0x58 | G, H share all 6 constants; C: `call [ecx+0x64]` @0x41924f, `push 0x110` @0x4193ab |
| 0x419ea0 | EZWheel::Poll | re-enumerate every 32 calls, 2 channels | G, H share 0x1f, 2, 0x10 and the callee 0x419220; C: `and ecx,0x1f` @0x419eb5 |
| 0x573cb0 | InputEvents::Update | player stride 0x18c, call to GetState | G has 0x18c and callees 0x405980 / 0x573ab0 / 0x573c30; H lists the sub-function 0x573df0 that holds the loop (`call 0x405980` @0x573e05, `add esi,0x18c` @0x573e38) |
| 0x406580 | InputDevice::ReadState | +0x23c, +0x134 == 0x13, callees 0x4070a0 / 0x406b10 | G&H share 3 callees; C: `cmp [esi+0x134],0x13` @0x40658e |
| 0x430b90 | Player::UpdateFrame | HudManager::Update call with player+0x95c | H merges it into 0x4311c0 (shares 0x4a9440, 0x42e620, 0x42ed40); C: `mov eax,[esi+0x95c]` @0x430dd9, `call 0x4a9440` @0x430de9 |
10/10 agree on the cited facts. Where H and G differ it is Hopper fragment merging (0x430b90 inside 0x4311c0, 0x573df0 inside 0x573cb0), not a semantic difference.
Script: scratchpad gen.py / agree2.py (callee-set overlap and capstone patterns; not committed). Rows with V in the TSV carry the check that earned it in the evidence column.

## Label audit of census/systems.tsv (read while working, not a recount)
`input` (140 rows): the real cluster is 0x405570-0x407ca0, 0x413000, 0x414830, 0x418d10-0x41c240, 0x573ab0-0x574a00. Wrong labels seen: 0x411b70-0x412fe0 and 0x4130d0 (mesh/streaming-like code reached from
0x644xxx tables), 0x429620 (24 KB, force-feedback driver of the car, close to input but belongs to car/physics), 0x44a1e0 (drag steer helper), 0x4ec990 and its neighbours (KB_SYMBOL_* FEng screen, keyboard glyph UI, front end),
0x61c3e1/0x687xxx (CRT thunks). `hud` (395 rows): the core is 0x49fc50-0x4a9900, 0x409cd0, 0x4f3030, 0x58e540-0x590dd0; wrong: 0x40f3d0 (49 KB D3D render-state code), 0x4969e0 and 0x49a3e0 (front-end results screens),
0x4c0b60 (options menu), 0x4e1d70, 0x4f48b0, 0x5abd45-0x5ac6a2 (D3DX math), 0x674898 (ftol), 0x68xxxx thunks, 0x432a30 (camera "3RDPERSON_" views).

## Open (U)
- Consumers of the JOY_EVENT array 0x73b578: which car/camera/menu code turns ids 0x88..0xac into steering, throttle and nitro; no xref hits the name table 0x6f1704 directly (only `0x5742b0` uses 0x6f1458..0x6f14b8).
- The 6 slots vs 2 players: how `0x7306c4` (player -> slot map) is set and how split-screen players claim the keyboard.
- `0x4067d0` / `0x4067f0` (wheel rebind capture), `0x406680`, `0x406c40`, `0x406cd0`, `0x406d50`, `0x406e10` (axis calibration helpers, not read); wheel profile table 0x7041c8 (guid -> axis config, 0x90 per row) and `0x41cda0`.
- Force feedback sources: the higher-level players `0x41a250 0x41a4b0 0x41a6c0 0x41a8c0 0x41ab00 0x41ad20 0x41af40 0x41b210 0x41b670` and `0x429620` (who calls them with which road/crash event).
- HudManager slot +0x58 (ctor `0x4a7f90`, update `0x4a8000`), helper updates `0x4a14d0 0x4a1460 0x4a6360 0x4a64b0 0x4a2ef0 0x4a3020 0x4a31e0 0x4a34c0.. 0x4a3aa0`, and the exact meaning of the mask bits that `Player::ComputeHudFlags` sets
  (0x1, 0x2000000, 0x40004, 0x42000 ...) per game mode: only the widget-side bits are known.
- Unnamed HUD tails: `0x4a1ee0` (ZoominRed/Green script helper), `0x4a7990`, `0x4a8a70`, `0x4a8b10`, `0x4a9810`; `0x4f2xxx` FEng object lifecycle and `0x4ef050` / `0x4f65d0` (current package lookup) are only I from how widgets use them.
- Minimap runtime facts in docs/re_minimap.md (alpha 0.2, frame never drawn, shader) remain D until a run; `0x4bf610` (options cycle 1/3/6) not re-read.

HANDOFF: hud_input.md done (108 names: hud 58, input 50; 10/10 second-tool); next: trace JOY_EVENT consumers (steer 0x88, throttle 0x8a) from the 0x73b578 array into the car update, and the mask bits of 0x42e620.
