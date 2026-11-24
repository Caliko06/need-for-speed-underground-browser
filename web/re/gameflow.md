# GameFlow and FEng: boot, front end, track load, race, unload (Speed.exe PC)

> Source: `docs/re/gameflow.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 441

# GameFlow and FEng: boot, front end, track load, race, unload (Speed.exe PC)

Marks: V = a second tool agrees (H = Hopper export, G = Ghidra export, C = capstone over pc/Speed.exe), I = inferred or one tool,
U = open. The binary outranks old notes. Names: census/names_gameflow.tsv (163 rows: 123 V / 40 I). Already done elsewhere and not repeated:
EventDesc / save / languages (canon.md), garage screens (garage.md), HUD (hud_input.md), TRACKB streaming (track.md), the loaders and
the ResourceFile layer (assets.md: 0x4482f0 CreateResourceFile, 0x448110 BeginLoading, 0x4483c0 ServiceResourceLoading ...).

## Answer
- The game flow is **one global object at 0x77a904 holding "the next step"**. `GameFlow::MainLoop 0x447600` runs that function pointer every frame
  (clears it first, so a step must set the next one itself), and each step installs the next as a completion callback of an asynchronous file
  load. It is a continuation chain, not a `switch`. Eight state numbers (1..8) are written to `[0x77a920]` by the steps themselves (V H+C); the table also names a ninth, EXIT_DEMO_DISC, that nothing writes.
- The cycle is: boot -> LoadingFrontEnd (1) -> InFrontEnd (3) -> UnloadingFrontEnd (2) -> LoadingTrackCommon (4) -> LoadingTrackSpecific (5)
  -> Racing (6) -> UnloadingTrackSpecific (7) -> UnloadingTrackCommon (8) -> back to (1), or straight to (4) for a restart / next race.
  There is **no separate "results" state**: the results screens are FEng screens shown while the state is still Racing (I; see Open).
- The front end is EA's FEng: `FEManager` (global `[0x73578c]`) owns a `cFEng` (+8) and a renderer (+0xc). Each `.fng` is a `FEPackageData`
  record (list head 0x746104); activating one builds its **screen object through the name -> factory registry at 0x6f94d8** (140 rows, stride 0x14).
  The 61 non-garage, non-online factories and their constructors are named from that table (V).
- Only ~30% of the flow functions carried the right label in census/systems.tsv (audit below).

## 1. The GameFlow object (base 0x77a904; V G/H/C)
| addr | field | meaning |
|---|---|---|
| 0x77a904 (+0) | next | function pointer of the next step; 0 = none. MainLoop reads, zeroes and calls it, loops while it changes (@0x447707..0x44772a) |
| 0x77a908 (+4) | arg | argument passed to the step (always 0 in the paths read) |
| 0x77a90c (+8) | name | C string of the pending step ("LoadingFrontEnd", "UnloadingFrontEnd", "LoadingTrackCommon", "GameFlowBeginRacing" ...). Cleared when the step starts. Debug only |
| 0x77a910 (+0xc) | hook | optional function called twice per frame by MainLoop (@0x4476fc, 0x447760) |
| 0x77a918 (+0x14) | busy | byte, 1 while an async load is pending; every step that changes the plan clears it first |
| 0x77a91c (+0x18) | step | name of the current load sub-step ("GameFlowLoadingFrontEndPart1", "...TrackSpecificPart6"); set next to the load it starts |
| 0x77a920 (+0x1c) | state | 1..8 as in the diagram; `GameFlow::IsInFrontEnd 0x401d70` is `[0x77a920]==3`. Read by about 20 other functions (cmp 3 or 6) |
| 0x77a924 (+0x20) | resource list | sentinel of the ResourceFile list; first node `[0x77a928]`; node +8 = group (2 = FRONTB / front end, 3 = INGAME / track), +0x24 or +0x90 = done flag |
The state-name pointer table at 0x7007b8..0x7007dc (NONE, LOADING_FRONTEND, UNLOADING_FRONTEND, IN_FRONTEND, LOADING_TRACK_COMMON,
LOADING_TRACK_SPECIFIC, RACING, UNLOADING_TRACK_SPECIFIC, UNLOADING_TRACK_COMMON, EXIT_DEMO_DISC) has the same order as the values the steps
write (C: pointer words at those addresses point to strings 0x6c9fe4 .. 0x6c9eb0); I found no code that indexes it (U, debug build leftover).
"Loading-time" counters sit beside it: names "Total/Load/Sound/Track" stored in 0x7360c0..0x7360dc and floats in 0x72cbcc..0x72cbec, filled
with the timer 0x585fa0 at the start of the steps (I).

## 2. State diagram (function that changes state | state | what triggers it)
```
CRT start 0x670e19 -> GameFlow::Run 0x4472e0 -> InitSubsystems 0x4471b0 -> (disc check 0x401520)
   if [0x73465c] (SkipFE) -> QuickRace::LaunchFromSetupGlobals 0x4b6390 ----------------------------+
   else next = 0x448b10 ---------------------------------------------------------------+            |
                                                                                         v            |
[1] LOADING_FRONTEND   0x448b10  (writers: Run, 0x4493a0)                                              |
      FRONTEND\FRONTB.LZC -cb-> 0x448ac0 Part2 (ROAD_SEGMENT.BIN) -cb-> 0x448a40 Part3 -> 0x448a10 End    |
      -> next 0x448c40                                                                                 |
[3] IN_FRONTEND        0x448c40 EnterFrontEnd  (FEng screens run; MainLoop calls FEManager::Update)     |
      leave by: 0x4b5c00 QuickRace::StartRaceByMode (QR menus 0x4b8050/0x4bb2b0/0x4bd710), 0x4b5df0      |
      career event start (0x4b62b3), 0x4b6390 (0x4b6778), or the online lobby 0x43ada0 -> 0x448530      |
[2] UNLOADING_FRONTEND 0x448d10  waits for the loader, frees FRONTB group, -> next 0x449250 <------------+
[4] LOADING_TRACK_COMMON 0x449250  shows PC_Loading.fng; GLOBAL\INGAMEA.BUN (sync), INGAMEB.LZC -cb->
      0x448f70 CreateRides (installs job 0x448ee0 in [0x737b58]) -> 0x448ee0 BeginLoadingTrackSpecific -> next 0x449760
[5] LOADING_TRACK_SPECIFIC 0x449760  TRACKB<id>.LZC -cb-> 0x4496a0 SetStreamPaths -> jmp 0x449600 Part2
      -> 0x4491a0 QueueRaceCars (cb 0x449590 via 0x4495c0 Part3) -> 0x449520 Part6 TEX<id>TRACK.BIN -cb-> 0x4494f0 End
      -> next 0x449870 TrackWorldInit -> next 0x449840
[6] RACING             0x449840  every frame: 0x43a2e0 test, 0x43ae40 race update
      leave by: Race::OnFlowMessage 0x422bb0 (message 9 / 10) -> next 0x449a10 ; or race message 8 (Restart) rebuilds in place, flow stays 6 (section "Race coordinator states"); 0x43ada0 is the online lobby, not Restart
[7] UNLOADING_TRACK_SPECIFIC 0x449a10  PC_Loading.fng, tears down the world (0x445350 streamer, 0x441320, 0x4433f0, 0x466bf0) -> next 0x4493a0
[8] UNLOADING_TRACK_COMMON   0x4493a0  frees INGAME group; if ([0x777b4c]==1 or [0x777b4c] in {2,4} with [0x777cc8]==4) and [0x778898] in {0,3}
      -> next 0x449250 (race again)  else -> next 0x448b10 (front end)
      8 -> 4 is the career retry (I): [0x778898] = 3 / 0 is written by 0x4973df / 0x49753e, both after 0x4abc20
```
All writes of `[0x77a904]` with an immediate were enumerated with capstone (list in the section "Evidence"): 0x422bfd, 0x44732c, 0x448a21,
0x448a9d, 0x448e6c, 0x448f35, 0x44943e, 0x4494a7, 0x449501, 0x4499de, 0x449d1b, 0x4b5ceb, 0x4b62b3, 0x4b6778, 0x4b67a0 and the setters 0x448530 / 0x448560.

Triggers in detail (V unless marked):
- **Menu -> race**: `QuickRace::StartRaceByMode 0x4b5c00` switches on the mode `[0x777cc8]` (table 0x4b5d04: 0 circuit 0x4b49e0, 1 sprint 0x4b4c30,
  2 knockout 0x4b4e60, 3 free run 0x4b5090, 4 0x4b52a0, 5 drag 0x4b55b0, 6 drift 0x4b59b0 (names of 4/5/6 from `re_freerun_menu`, I)), fills RaceStatus
  0x78a2f0 and sets next = UnloadingFrontEnd. Career starts through `Career::StartRaceFromEvent 0x4b5df0` (writer 0x4b62b3, same next).
- **SkipFE / direct start**: `0x4b6390` copies the menu staging globals (0x734660.., 0x6f1d48..) into RaceStatus, creates the entrants with
  `0x5809c0(.., "SkipFE", ..)` and spawns opponents; from state 3 it requests UnloadingFrontEnd, from any other state it jumps straight to LoadingTrackCommon.
- **Race end**: `Race::OnFlowMessage 0x422bb0` (vtable method; jump table 0x422c20, ids 1..10 -> cases 0,0,0,4,4,4,4,1,2,3) handles ids 9 and 10 by
  setting next = 0x449a10 with name "BeginGameFlowUnloadingTrackSpecific" (id 10 first calls 0x495e90). Who sends 9/10 is U.
- **Restart**: NOT `0x43ada0`. Restart is race message 8 (see "Race coordinator states and object lifetime"); flow stays 6. `Race::RequestStartOrRestart 0x43ada0`
  (only callers 0x546b41, 0x548721 = Net_HostStartRaceWhenAllReady 0x546980) is the online lobby start: `SetNextUnloadingFrontEnd 0x448530` when `IsInFrontEnd`, else `SetNextLoadingTrackCommon 0x448560`. V (gap2)

## 3. How a step loads (the continuation pattern; V C/H)
`file = CreateResourceFile(path, type, flags, ..)  (0x4482f0)`, then `BeginLoading(file, callback)  (0x448110)` with `eax` = callback; the step also writes
`[0x77a918]=1` and `[0x77a91c]=<step name>`. When the loader (0x4483c0, driven from the main loop and from `0x58a850`) finishes the file, the callback runs
and installs the next step. Steps that must not return before the data exists loop on `0x4483c0` themselves (`INGAMEA.BUN` in 0x449250; the waits in 0x448d10 / 0x4493a0 / 0x449a10 on a node's done flag).
Two idioms to know when reading: (1) a callback pointer can be 0 (synchronous load); (2) after the load the step copies a path over the file node
(`FRONTEND\FRONTB.BUN` over `...LZC`, `TRACKB%d.BUN`, `GLOBAL\INGAMEB.BUN`) so the resource keeps its `.BUN` name (H+C loops at 0x448c17, 0x449811).
Hopper and Ghidra **miss the handlers that are reached only by pointer** (0x448ac0, 0x449250, 0x449520, 0x449590, 0x449600, 0x449760): they appear as
labels inside neighbouring functions, so the existing names 0x449765 and 0x44952b are mid-function addresses of 0x449760 and 0x449520.

## 4. FEng (front end engine; V unless marked)
Objects: `FEManager` `[0x73578c]` (ctor 0x4f5240, vtable 0x6c1b18; +8 `cFEng` 0x5254 B, +0xc `FEngRenderer` 0x3420 B), init `0x4f60e0` (also two screen pools
`[0x735dfc]` 0x4c B and `[0x735e18]` 0x48 B used by PC_Loading and Chyron). `cFEng` keeps loaded packages in lists at +0xdc and +0xec; its back pointer to the manager is +0x10c.
- `FEPackageData` record (list head **0x746104**): +0x10 = chunk (id 0x30203 raw FNG, 0x30210 compressed "COMP"/"JDLZ"), +0x14 = screen object, +0x18 = package in cFEng,
  +0x24 copied from the chunk. FNG header: magic 0xe76e4546, chunk "PkHd" 0x64486b50 at +8, version >= 0x20000 at +0x10, name hash at +0x28.
  `Activate 0x4f3b60` creates the screen and prints "Activate %s\n"; `Deactivate 0x4f3bd0` pops the package and deletes the screen; `GetFngData 0x4f3c40` unpacks.
  `FEPackageList::FindByName 0x4f3f90` (name in eax, list in the stack arg) is called from 300+ places: hash with `FEng::HashName 0x4fd230`, MRU move-to-front.
- **Registry 0x6f94d8**: rows of 5 dwords (name, factory, flag, ?, hash). The flag is 1 for garage and list/browser screens (CreateScreen then also pushes `MU_HorizontalBrowserBack.fng`).
  `CreateScreen 0x4f37e0` takes the hash (h=-1; h=h*33+toupper(c)), calls `factory(&{name,arg,&row+0xc,row+0x10})`; `FindEntry 0x4f3940`, `SetFactory 0x4f39a0` (6 callers in 0x4dc600..0x4dcfd0) are the other users.
  Factory = `operator new(size)` (or a pool) + constructor; **every constructor calls `FEScreen::FEScreen 0x4f78e0` first** (vtable 0x6c1874: slot 0 scalar deleting dtor 0x4f7b30,
  slots 1 and 5 the stub 0x4134b0) which itself calls `FEScreenBase 0x4cd2a0` (stores the name hash at +8) and looks up shared objects by hash (0xaa68bfce, 0xaa68bfd4, 0xaa68bfc6 ..).
  Nine factories (twelve registry rows) build the base class directly: background, DiscError, MU_ScreenPos, LS_Demo_Legal, LS_THXMovie, LS_ESRB_PC, LS_Demo_Disclaimer, MU_UG_Explained and Chyron* (4 rows, pool [0x735e18]). Nine more rows have factory 0 (GenericDialog, GenericOKDialog, MU_PauseConfirm, HELP_Generic ...: made by other code, U).
- Messages are 32-bit hashes of names. Seen in handlers (garage.md + this pass): 0xc407210 accept, 0x911ab364 back, 0xb5971bf1 next item, 0x9120409e previous item,
  0xc98356ba "screen shown again" (broadcast each frame by `FEManager::Update 0x4f6170` through `BroadcastMessage 0x4f3dc0`), 0x35f8620b / 0x58c164c4 / 0x368a0075 / 0x541307a8 /
  0x8816789f / 0x689e2e13 / 0x7f007e43 / 0xfd8a3b6d (option-menu moves, U), 0xabc08912 (U). Joystick events are the strings JOY_EVENT_FENG_* (0x6bb848..).
- Package API wrappers: `FEManager::ShowPackage 0x4f61f0` (name in eax: push if absent, then joy handlers `0x4f5ab0`), `cFEng::PushPackage 0x4eede0` (31 callers), `cFEng::PopPackage 0x4eebf0`.
  `0x4f6360 / 0x4f63a0 / 0x4f63e0 / 0x4f6430` are thin wrappers that find the active package with `FindByName(…, 0x746104)` and queue a command (0x4f0800 / 0x4eebf0 / 0x4f08f0 / 0x4f09b0): purpose per wrapper U.

## 5. Loading screens
- `PC_Loading.fng`: factory 0x4dd230 (screen from pool [0x735dfc]), ctor 0x4dd290 (vtable 0x6c3778). GameFlow pushes it with `FEManager::ShowPackage` in LoadingFrontEnd 0x448b10 (@0x448b97, when no package is active), in
  LoadingTrackCommon 0x449250 (@0x4492ca, only when `[0x7183c8]==0`) and in UnloadingTrackSpecific 0x449a10 (@0x449a7e). The screen has no per-step progress code read yet (U);
  the steps only publish `[0x77a91c]` and the timing floats. `Chyron*.fng` and `LS_*.fng` (Splash, EAlogo, PSAMovie, THXMovie, IntroFMV, LangSelect, Disclaimer, ESRB) are the boot screens (factories in the table below).
- Boot order before the first menu: `0x401520` (named `DiscCheck_ModalFrameLoop` in names_render.tsv) shows `DiscErrorPC.fng` while `0x411ab0` fails; then the state chain starts.

## 6. Options and profile screens (what is read; V = registry + ctor, rest I)
- `MU_Options_PC.fng` (ctor 0x4ce760, 0x4ec B, sliders SliderBase_n / VolSliderBase_n), `MU_OptionsSelector_PC.fng` (ctor 0x4d4370), `MU_OptionsHUD.fng`, `MU_ScreenPos.fng`, `MU_PauseOptions_PC.fng`
  (0x2b8 B), `MU_PauseOptionsSelector.fng`, `PC_Graphics.fng`, `PC_Customize_Graphics.fng` (0x2b8 B), `PC_Controller_Config.fng` (one factory 0x413550 serves Keyboard / Joypad / Wheel / Controller), `Keyboard.fng` (0x210 B).
- `OptionsSelectorScreen::NotificationMessage 0x4d4610` (I): accept pushes MU_Options_PC.fng or Credits.fng, back shows `MemCardCheck.fng` and calls 0x4c9570 (the autosave of garage.md); the nine button
  objects Audio, Camera, Car, Controller, Display, EATrax, SavingOptions, Credits, GameTrailers get script "Idle" (C strings).
- Profile: `MU_PlayerLogin.fng` (ctor 0x4c9740, 0xbc B), `PC_LoadSave.fng` (ctor 0x416d10, 0x270 B, vtable 0x6cbcc0), `MU_UG_NewOrLoad_PC2.fng` (ctor 0x417700, 0x28c B: also builds the DUMMY_SKIN%d / DUMMY_WHEEL%d / FE_SKYLINE preview car).
  Save file logic is in canon.md (0x4c9570 and the writers); only the screens that drive it are named here.

## 7. Screen factories and constructors (registry 0x6f94d8; names in census/names_gameflow.tsv)
Table = fng | factory | constructor | object size | vtable. Garage, online (out of scope) and already named rows are not listed.

**Boot, legal, movies**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| DiscErrorPC.fng | 0x4df4d0 | 0x4df560 | 0x44 | 0x6c37fc |
| DiscError.fng | 0x4f9ff0 | 0x4f78e0 | 0x40 | 0x6c1874 |
| Credits.fng | 0x4d71e0 | 0x4d7240 | 0x60 | 0x6c3d50 |
| TrailerMovie.fng | 0x4d5fb0 | 0x4d6010 | 0x40 | 0x6c3e5c |
| LS_Demo_Legal.fng | 0x4de6e0 | 0x4f78e0 | 0x48 | 0x6c1874 |
| LS_PSAMovie.fng | 0x4dec90 | 0x4debf0 | 0x40 | 0x6c37a8 |
| LS_EAlogo.fng | 0x4deb60 | 0x4deaa0 | 0x44 | 0x6c3758 |
| LS_IntroFMV.fng | 0x4de8f0 | 0x4de950 | 0x40 | 0x6c3768 |
| LS_LangSelect.fng | 0x4dee30 | 0x4dee90 | 0x4c | 0x6c37c8 |
| LS_THXMovie.fng | 0x4ded20 | 0x4f78e0 | 0x40 | 0x6c1874 |
| LS_Splash_PC.fng | 0x4df170 | 0x4df1d0 | 0x48 | 0x6c3748 |
| LS_Disclaimer_PC.fng | 0x4de5a0 | 0x4de600 | 0x44 | 0x6c37e8 |
| LS_ESRB_PC.fng | 0x4e01f0 | 0x4f78e0 | 0x44 | 0x6c1874 |
| LS_Demo_Disclaimer.fng | 0x4de800 | 0x4f78e0 | 0x44 | 0x6c1874 |
| DemoDisc_Marketing.fng | 0x4e0160 | 0x4e0030 | 0x44 | 0x6c37d8 |

**Main menu, quick race**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| MU_TrackMapScroller.fng | 0x4bbc30 | 0x4bb5d0 | 0x58 | 0x6c5bc0 |
| MU_QuickRaceModeSelect.fng | 0x4b6820 | 0x4b6880 | 0x64 | 0x6c5ecc |
| MU_QuickRaceTrackSelect.fng | 0x4b9ae0 | 0x4b9b40 | 0xb0 | 0x6c5ba8 |
| MU_QuickRaceCarSelect.fng | 0x4bbda0 | 0x4bbe00 | 0xa8 | 0x6c5b60 |
| MU_MultiplayerCarSelect.fng | 0x4e0740 | 0x4e07a0 | 0xcc | 0x6c36b4 |
| MU_MPChooseGarage.fng | 0x4e1c90 | 0x4e1cf0 | 0x70 | 0x6c3654 |
| MU_QuickRaceLapPopup_PC.fng | 0x4bd310 | 0x4bd370 | 0x48 | 0x6c5b04 |
| MU_QuickRaceOptions_PC.fng | 0x4b7ee0 | 0x4b7f40 | 0xa4 | 0x6c5dcc |
| MU_Main_PC.fng | 0x4b2b70 | 0x4b2c30 | 0x4c | 0x6c614c |

**Career (UG)**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| MU_UG_ChooseCareerCar.fng | 0x4c4640 | 0x4c3db0 | 0xa0 | 0x6c5460 |
| MU_UG_MapScreen.fng | 0x4c5100 | 0x4c46a0 | 0x54 | 0x6c52f0 |
| MU_UG_EventBriefing.fng | 0x4c6400 | 0x4c53c0 | 0x58 | 0x6c52e0 |
| MU_UG_Explained.fng | 0x4b38d0 | 0x4f78e0 | 0x44 | 0x6c1874 |
| MU_UG_RankScreen.fng | 0x4ea1b0 | 0x4e9ce0 | 0x50 | 0x6c2da4 |
| MU_UG_StatsScreen.fng | 0x4eab60 | 0x4ea210 | 0x58 | 0x6c2d74 |
| MU_UG_MovieTheaterViewer.fng | 0x4c3d50 | 0x4c3a40 | 0x44 | 0x6c5488 |
| MU_UG_UndergroundMenu.fng | 0x4eb390 | 0x4eabc0 | 0x44 | 0x6c2d94 |
| MU_UG_NewCareerFMV.fng | 0x4e8640 | 0x4e8180 | 0x44 | 0x6c2d84 |
| MU_UG_NewCareerExtroFMV.fng | 0x4e8ab0 | 0x4e86d0 | 0x40 | 0x6c2d64 |
| MU_UG_NewOrLoad_PC2.fng | 0x4176a0 | 0x417700 | 0x28c | 0x6cbc18 |

**Options, pause, input**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| Options.fng | 0x494910 | 0x494970 | 0x58 | 0x6c7ad8 |
| MU_PauseOptionsSelector.fng | 0x4c25d0 | 0x4c2630 | 0x48 | 0x6c56b8 |
| Keyboard.fng | 0x4ec410 | 0x4ec470 | 0x210 | 0x6c2c8c |
| EA_TRAX_Jukebox.fng +3 more | 0x4d49c0 | 0x4d4b10 | 0xb4 | 0x6c3e2c |
| MU_OptionsHUD.fng | 0x4d6210 | 0x4d6270 | 0x68 | 0x6c3dc0 |
| MU_ScreenPos.fng | 0x4d7380 | 0x4f78e0 | 0x40 | 0x6c1874 |
| MU_Options_PC.fng | 0x4ce700 | 0x4ce760 | 0x4ec | 0x6c3e3c |
| PC_ColorPicker.fng | 0x4d9960 | 0x4dab10 | 0xbd8 | 0x6c3c14 |
| PC_Controller_Config.fng +3 more | 0x413550 | 0x4135b0 | 0xa0 | 0x6cbf14 |
| PC_MenuBar.fng | 0x4e66e0 | 0x4e6740 | 0x164 | 0x6c3124 |
| PC_Graphics.fng | 0x414be0 | 0x414c40 | 0xb8 | 0x6cbe64 |
| PC_Customize_Graphics.fng | 0x415550 | 0x4155b0 | 0x2b8 | 0x6cbcfc |
| MU_Pause_PC.fng | 0x4cd5b0 | 0x4cd660 | 0x74 | 0x6c41c8 |
| MU_PauseOptions_PC.fng | 0x4bd8a0 | 0x4bd900 | 0x2b8 | 0x6c56c8 |
| MU_OptionsSelector_PC.fng | 0x4d4310 | 0x4d4370 | 0x48 | 0x6c3e4c |

**Race, results**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| PreRaceStats.fng | 0x494de0 | 0x494e40 | 0xdc | 0x6c7a00 |
| PostRaceResults.fng | 0x497bf0 | 0x497c50 | 0x44 | 0x6c75b8 |
| PostRaceStats.fng | 0x49be80 | 0x49bee0 | 0x140 | 0x6c75a8 |
| PostRaceMenu.fng | 0x496140 | 0x4961a0 | 0xb8 | 0x6c7588 |
| background.fng | 0x4b1f10 | 0x4f78e0 | 0x40 | 0x6c1874 |
| RewardPopup.fng | 0x49ef50 | 0x49efb0 | 0x40 | 0x6c7574 |
| StyleAnimator.fng | 0x49fac0 | 0x49fb20 | 0x78 | 0x6c7598 |
| Chyron.fng +3 more | 0x4d7450 | 0x4f78e0 | pool | 0x6c1874 |

**Profile, loading**

| fng | factory | ctor | size | vtable |
|---|---|---|---|---|
| MU_PlayerLogin.fng | 0x4c95f0 | 0x4c9740 | 0xbc | 0x6c5134 |
| PC_Loading.fng | 0x4dd230 | 0x4dd290 | pool | 0x6c3778 |
| PC_LoadSave.fng | 0x416cb0 | 0x416d10 | 0x270 | 0x6cbcc0 |

## 8. Label audit (census/systems.tsv)
- The 27 flow functions of sections 1-3 plus the two QR/career launchers: **0x447600 `track`**, 0x449250 `assets`, 0x4b6390 `rivals`, 0x43ada0 `runtime`, 0x4471b0 / 0x401d70 /
  0x4491a0 / 0x449840 `unknown`, 0x449520 untagged: 9 of 27 (33%) are not `canon`. 0x448a10..0x448d10 and 0x449a10 are correctly `canon`.
- The 26 FEng / options rows of names_gameflow.tsv with system `hud`: systems.tsv says canon 12, runtime 5, hud 3, render 3, input 1, audio 1, unknown 1: the
  FE engine (0x4ee000..0x4fa000) is not `hud` in the graph; hud_input.md's HudManager is a different layer.
- 122 of the 163 named addresses are `canon` in systems.tsv (screen factories/ctors: right by design, they are front-end screens).

## 9. Second-tool agreement (11 re-derived names)
Rule: the name was read from one export, the same question asked of another tool (H Hopper, G Ghidra, C capstone).
| addr | name | what was re-derived | result |
|---|---|---|---|
| 0x447600 | GameFlow::MainLoop | clear-then-call of `[0x77a904]`, arg `[0x77a908]`, hook `[0x77a910]`, `[0x77a920]==6` test | G, H and C agree (C: jmp [..+0x77a904] @0x44772a, cmp @0x44776b) |
| 0x448d10 | UnloadingFrontEnd | state value 2 and next 0x449250 | H `*dword_77a920 = 0x2`; C `mov ebx,2` @0x448d19, `mov [0x77a920],ebx` @0x448d1f, `mov [0x77a904],0x449250` @0x448e6c |
| 0x4493a0 | UnloadingTrackCommon | state 8 | H `= 0x8`; C `mov [0x77a920],8` @0x4493a8 |
| 0x449a10 | UnloadingTrackSpecific | state 7, next 0x4493a0 | H `= 0x7`; C `mov [0x77a920],7` @0x449a15, `mov [0x77a904],0x4493a0` @0x449d1b |
| 0x449840 | Racing | state 6 | H `= 0x6`; C @0x449845 |
| 0x448c40 | EnterFrontEnd | state 3 | H `= 0x3`; C @0x448ce9 |
| 0x448530 / 0x448560 | SetNext... | setters write 0x448d10 / 0x449250 + name | H `*eax = sub_448d10`, `*eax = 0x449250`; C bytes |
| 0x4b5c00 | StartRaceByMode | 7-way switch on `[0x777cc8]` | H switch cases 0..6; C `cmp eax,6; jmp [eax*4+0x4b5d04]` and the 7 table words |
| 0x4b6390 | LaunchFromSetupGlobals | "SkipFE", next 0x448d10 vs 0x449250 on `[0x77a920]!=3` | G source text; C writes @0x4b6778 / 0x4b67a0; H callee list |
| 0x4f37e0 | CreateScreen | hash multiplier 0x21, stride 0x14, table end 0x6f9fdc | G loop (`ppuVar7 + 5`, 0x6f9fdb) == C (imul 0x21 @0x4f3800, add esi,0x14 @0x4f381e, cmp @0x4f3822) |
| 0x4f78e0 | FEScreen::FEScreen | vtable 0x6c1874 and the hash constants 0xaa68bfce / 0xaa68bfd4 / 0xaa68bfc6 | G, H and C share all (script: 0x6c1874 = 7084148 in H and C) |
11/11 agree. Factory rows were checked by Hopper too (`sub_<ctor>` in the callee list of the factory) for the ones tagged `capstone+hopper`; the rest stay capstone-only (I-level naming).

## Race coordinator states and object lifetime (2026-11-06)
V = code read, I = inferred, U = open. Sources: scratchpad gap2 and gap4 (REA, Ghidra, capstone).

**What [0x7361f0] is.** The RaceCoordinator, built by 0x421f00 (`[0x7361f0] = this`), message driven. `[coord+0]` = state. Only the pump `0x421b10` writes it: message 1 sets
`*coord = arg`, message 2 (leave) writes 0 after the handler. Handler = table `0x700db8[state]` (12 entries). The game loop 0x447600 queues message 3 (tick) every frame.
`0x421ae0(N)` = transition helper: queue 2 (leave), 1 (enter N), 3 (tick). Fields: +4 enter stamp, +0x14 "next mode" (4 / 2 / 9 / 10 at start, 8 = results), +0x18 initial stage,
+0x20 state saved by pause, +0x24 paused byte. V

| state | handler | meaning |
|---|---|---|
| 1 | 0x422eb0 | loading / streaming step (grid, seed, SetRaceStage), then `0x421ae0([coord+0x14])`. Also REUSED after the finish with `[coord+0x14] == 8` |
| 2 | 0x423070 | pre-race wait (when [0x73465c] or [coord+0x44]); starts cars, then 3 |
| 3 | 0x423280 | pre-race NIS / countdown, then 4 |
| 4 | 0x423530 | RACING; tick runs the FINISH CHECK |
| 5 | 0x4239c0 | instant replay / THE_PRESENT camera (pause menu choice 4) |
| 6 | 0x423b50 | in-race replay, returns to 4 |
| 7 | 0x423870 | PAUSE MENU (saves old state in +0x20); result 1 resume, 2 quit-to-results (msg 8), 3 unload (msg 10), 4 replay |
| 8 | 0x424160 | RESULTS / post-race screens; msgs 9 / 10 queue the unload (flow 7). Flow stays 6 here |
| 9 / 10 | 0x422c80 / 0x422d70 | alt. modes ([0x78a308] / [0x78a309]); 10 plays a replay. Role beyond that: I |
| 0xb | 0x4237a0 | queued by 0x4211f0; FEng package; purpose U |

**Finish edge (V).** `Race::Update 0x435570` -> `Race::FinishCar 0x4350d0` for the player (racer+0x10 short = finish reason, +0x110 time, +0xc rank, Race+0x28 count++).
State 4 tick (0x423630, `0x435b30` AreAllPlayersFinished) or msg 4 (0x423686) -> `call 0x423f20` FinishRaceFlow (only these 2 callers, both in state 4): first `0x435a70`
SimulateRaceFinish (call at 0x423f3e, ret 0x423f43) = FinishCar for EVERY unfinished racer; then offline `[coord+0x14] = 8`, enter 1, and 1 -> 8 after streaming.
Online (0x43a2e0 true) queues msg 10 instead. 4 -> 1 with `[coord+0x14] == 8` -> 8; flow stays 6 the whole time.
- Test `state == 8 || (state == 1 && [coord+0x14] == 8)`. Never use 7 (pause) or 5 / 6 (replay): they return to 4. A plain "state == 1" also fires on the grid. V
- Racer finished flag: Race = [0x73619c], racers at `Race+0x520 + 4*i`, count `[Race+0x24]`; `short racer+0x10` = finish reason, 0 = still racing. Rivals may finish before the player. V
- A finished rival (car+0x24 == 3): FinishCar sets `[ctrl+0x3f4] = 0x11` (0x43532c) -> AIActionEndOfRace ctor 0x453730 (priority 600), plan with zero speed: it brakes to a stop in place. V
- Pause "quit to results" (state 7 arg 2) goes by msg 8 with no 0x423f20; whether racers get FinishCar there (0x495e20): U.

**Restart and next race (V).** Restart = race message 8 (posters 0x42395e, 0x4243e3, 0x4973b1 DoRestartRace). `0x422bb0` case 8 (0x422bd4): `call 0x422130` (tear down) then
`call 0x421f00` (build again); flow stays 6; `[0x7361f0]` keeps its address. Msg 9 (DoRestartEvent 0x4973d0, DoNextRaceInEvent 0x497410, handler 0x423530 case 9) -> state 0 handler
0x422bed -> 0x449a10: flow 6 -> 7 -> 8 -> 4 (career retry, [0x778898] in {0,3}, gate in 0x4493a0) -> 5 -> 6. Msg 10 (quit): 7 -> 8 -> 1 -> 3.
Build order in 0x421f00: PlaceAllRacers 0x422a70 (call at 0x421fc7) runs BEFORE the records 0x434590 (call at 0x422047). Car fields: car+0x14 = entrant, car+0x2c = driver.
Free + build run inside one guest handler; during the 4/5/7/8 loading frames [0x7361f8] and [0x7361f0] are 0, so code gated on flow 6 never sees freed cars.

**Race block reset (V, gap3).** RaceStatus 0x78a2f0..0x78a427 (+ entrant pool 0x77c790) is reset by `0x431df0`, not by track load. Callers: 0x448b3f (LoadingFrontEnd, flow 1), 0x4b5c15
(StartRaceByMode), 0x4b5d33 (LAN start), 0x4b5e18 (Career::StartRaceFromEvent). Flow 4 / 5 / 6 never store into it. Restart and 8 -> 4 keep it; 8 -> 4 re-copies only track, laps,
direction ([0x78a2f0], [0x78a318], [0x78a31c], [0x78a2fc]) through 0x4abc20.

**Object lifetime** (cars are created only at 0x4224f2 / 0x599463, freed only in the sweep 0x422b70; nothing is created or freed mid-race):
| object | created | freed | host edge |
|---|---|---|---|
| race coordinator [0x7361f0] (0xb0, ctor 0x421c70) | 0x449976 (TrackWorldInit 0x449870, flow 5) | 0x449a9f, zeroed 0x449ab1 (flow 7) | same pointer on Restart |
| car list head [0x7361f8] (0x17a0, ctor 0x41f6e0) | 0x421fb9 in 0x421f00 (flow 5, or msg 8) | 0x4221ff in 0x422130; [0x7361f8] = 0 | rn_race change |
| human + racer cars (0x8f0) | 0x422410 BuildRacerCar from PlaceAllRacers 0x422aec | sweep 0x422b70 (dtor 0x425990) | rn_race change; address may repeat for another car |
| traffic cars (0x8f0) | 0x599463 via 0x5992f0 <- 0x598bf0 <- 0x422b36 (PlaceCar may return 0) | same sweep | RECYCLED IN PLACE by 0x599830 (same car, driver, entrant) |
| driver car+0x2c | placeholder at 0x425665, real by Car::SetDriver 0x425fe0 | car dtor and every 0x425fe0 call | replaced in flow 6 for player and finishing cars (FinishCar 0x435315, World::Step 0x420c2a, 0x42e1a4..); traffic never |
| RaceManager [0x73619c] (0x568, ctor 0x434270) + records | 0x421f8c; records by 0x434590 | 0x422130, zeroed | rn_race change |
| teleporter L+0x2f0 (0x1a0) | with L (0x598440 in 0x41f6e0) | with L | read live as ld(L+0x2f0) |
| players [0x7361bc+4i] | head of 0x421f00 (I) | tail of 0x422130 | re-read each time |
| entrants car+0x14 (pool 0x77c790, stride 0x750) | front end / mode setup | never in 4..6 | same record across Restart |
Msg 8 and next stage both free and re-malloc everything; only [0x7361f0] keeps its address on Restart.

## Evidence notes
- Writers of `[0x77a920]` (capstone scan of .text): 0x448b11 (1), 0x448ce9 (3), 0x448d1f (2 via ebx), 0x449257 (4), 0x4493a8 (8), 0x44976a (5), 0x449845 (6), 0x449a15 (7); readers cmp 3 / 6 at 0x403bc5 0x4081c0 0x4085b8 0x408f24
  0x40a5d9 0x44776b 0x4b675f 0x4f308f 0x539847 0x53cc51 0x542eaa 0x543a8b 0x544f47 0x56dc63 0x5704a7 0x570db0 (cmp 3 = front-end-only code: FEng render, input; cmp 6 = race-only code).
- Scratch scripts are not committed (scratchpad gf/).

## Open (U)
- Who else sends message ids 9 and 10 (known: DoRestartEvent 0x4973d0, DoNextRaceInEvent 0x497410, state 4 case 9; quit 10), and the first branch `[0x6f1f64]` of the online lobby start `0x43ada0`.
- Which trigger fires World::Step 0x420c2a and the 0x42e* SetDriver calls (player driver swap in flow 6); how a tournament advances a stage (probably via the front end, I); whether 0x495e20 finishes racers.
- Where the results screens (PostRaceResults / PostRaceStats / PostRaceMenu, factories 0x497bf0 0x49be80 0x496140) are pushed and how they return to state 7: no GameFlow state covers them; the push site is probably in the race end code of
  `0x43ae40` or its callees (not traced).
- What `[0x6f1dd8]==1` selects in steps 0x448a40 / 0x449600 / 0x448d10 / 0x449a10 (calls 0x51da90 / 0x51dec0 with callback 0x448a10 / 0x4495c0): looks like the online path (I), out of scope.
- Progress logic of the loading screen `Screen_PC_Loading` (vtable 0x6c3778) and consumers of `[0x77a91c]` and the timing floats 0x72cbcc..: not read.
- The full message list per screen (accept / back are known; the other hashes of option menus are not decoded), the command queue vtable 0x6c2c64 behind `0x4f0800`, and the four thin wrappers 0x4f63xx.
- 0x4471b0's callee order is H only (named `InitSubsystems`, I); 0x4f60e0, 0x4eede0, 0x4eebf0, 0x4f5ab0, 0x4f5b90 are single-tool names (I).
- The 25 online screens (out of scope) and the 28 garage / performance / magazine rows of the registry are not named here (garage.md names most garage ones).

