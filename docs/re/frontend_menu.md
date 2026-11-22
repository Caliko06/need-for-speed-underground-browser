# Main menu flow

V = capstone + Hopper agree, I = one tool, U = unknown. FEng objects are hashes (FEng::HashName 0x4fd230, upper-cased); text is a string-table hash.

## Main menu = MU_Main_PC.fng (FRONTB, chunk hash 0x5b543f80), ctor 0x4b2c30, vtable 0x6c614c
- 6 buttons in the FNG (objects UndergroundMode 0xd7ba6011, QuickRace 0xde511657, Online 0x70fbb1e4, Options 0x95ad096b, CUSTOMIZE 0xa936c3a2, STATISTICS 0xf20e404a); labels are string hashes inside the FNG:
  MU_MAIN_UNDERGROUND 0xc6fd2991 "GO UNDERGROUND", MU_MAIN_QUICK_RACE 0x961626db, MU_MAIN_PLAY_ONLINE 0x36dbec3e, MU_MAIN_OPTIONS 0x99e650b0, CUSTOMIZE, UNDERGROUND_STATS 0xda20a5da "STATISTICS" (found by scanning the decompressed FNG for English.bin hashes).
- Text lookup: hash -> 0x59fc00 -> 0x59fb80 binary search in [0x734434] (count [0x73442c]); English.bin chunk 0x39000 (3846 pairs); miss -> label 0xc01a6f63.
- Action: vtable slot 2 `Screen_MU_Main_PC::NotificationMessage 0x4b3240`. Accept 0xc407210 switches on the object hash, writes [0x777b4c] (the only writer of it in the exe) and calls FEngSwitchPackages 0x4f6360 (edi = package name):
  | button | [0x777b4c] | next package |
  |---|---|---|
  | UndergroundMode | 1 | MU_UG_UndergroundMenu.fng (the path 0x4b3513..0x4b35b6 also calls MU_UG_Explained or a new-career setup 0x5a0a00/0x5a0ce0; not fully read, I) |
  | QuickRace | 2 (@0x4b34e9) | MU_QuickRaceModeSelect.fng |
  | Online | 8, only if [0x7346c4] | MU_Online_NetworkLogin.fng |
  | Options | 0x10 | MU_OptionsSelector_PC.fng |
  | CUSTOMIZE | 0x20 | MU_MainMenuCarCustomize.fng |
  | STATISTICS | 0x80 | MU_UG_StatsScreen.fng |
  | 0x14d83e4e (no button in this FNG) | 0x40 | MU_UG_NewOrLoad_PC.fng |
  | 0x11793157 (bit 4, no button, no accept case) | - | text 0xe4db4839 "head-to-head racing": vestigial multiplayer |
- Free Run is NOT on this menu: it is a mode button of MU_QuickRaceModeSelect (ctor 0x4b6880): AddModeButton 0x4b6fe0 builds nodes {+8 mode}; Free Run = mode 3, object hash("QR_freerun"), label 0xcc4e72b1 "FREE RUN".

## Quick Race chain (each screen's accept = slot 2 handler)
MU_Main_PC (QuickRace) -> ModeSelect 0x4b7a94 (writes [0x777cc8] = mode) -> CarSelect 0x4bcb40 (writes [0x758c28] = car handle) -> TrackSelect 0x4bb2b0 (0x4bafe0 writes record+8 = track id, +0xc = reverse) -> Options 0x4b8050 / LapPopup 0x4bd710 -> QuickRace::StartRaceByMode 0x4b5c00.
- 0x4b5c00: [0x777ccc]=0, RaceStatus::Reset 0x431df0 (esi 0x78a2f0), switch [0x777cc8] via 0x4b5d04 (3 -> RaceStarter::SetupFreeRun 0x4b5090), 0x4df790, then [0x77a90c] = "UnloadingFrontEnd" (0x6c9e8c), [0x77a904] = 0x448d10, [0x77a918] = 0 (@0x4b5ce1..0x4b5cf7). GameFlow does the rest (docs/re/gameflow.md state 3 -> 2 -> 4 -> 5 -> 6).
- Per-mode settings record = 0x4ab510(0x748f70, mode); Free Run = 0x7589e0 (0x24 bytes): +8 track id, +0xc reverse. Setup 0x4b5090 copies +8 -> [0x78a2f0], +0xc -> [0x78a2fc], +0x18 -> [0x78a300]. (`re_freerun_menu` says +0x18 is the reverse flag: wrong, the track pick stores it at +0xc, 0x4b9d5f / 0x4bb0bc.)
- WORLD is already the 32nd track row, id 1010, mask 0x90 (host/openworld.c world_rows), name pair TRACK_NAME_1010 -> "WORLD" (world_lang): it shows in the Free Run track list.

## What ?pool=1 / completion.py jump 3:1010 drives
Keys: profile MU_UG_NewOrLoad_PC2 RETURN, MU_Main_PC RETURN (the cursor starts on QuickRace, observed, completion.py:30) -> [0x777b4c]=2 -> MU_QuickRaceModeSelect. host/input.c input_jump then (flow state 3, screen up 30 frames) stores [0x777cc8]=3, [0x7589e8]=1010 and calls 0x4b5c00. Nothing else: no car, track, options screen. It is a host hook, not game code.

## WORLD button (row 8, built 2026-11-11)
Online accept 0x4b342a -> cave 0x7977c0 -> host world_arm (host/input.c) -> QuickRace case 0x4b34e9 (ModeSelect builds, its ctor does the 0xf660 copy) -> world_go sets [0x777cc8]=3, 0x7589e0+8=1010, +0xc=0, calls 0x4b5c00 (6 frames after the screen is up). Label: world_lang repoints hash 0x36dbec3e at "WORLD".
Track 1010 needs its row in the track-info table (setup 0x4b5090 looks it up by id, +0x69; TRACKB/TEX/STREAM names come from it), NOT the Free Run list: lists filter by mask bits (0x4ab470), so Original gets the row with mask 0x80 = in no list (RN_WORLDROW=2, web/mode.js). Run: shots web/plan/shots/world_menu*.png, world_launcher*.png.
