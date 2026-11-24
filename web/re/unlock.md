# Unlock state and checks in Speed.exe

> Source: `docs/re/unlock.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 50

# Unlock state and checks in Speed.exe
Tools: G Ghidra, C capstone, GC ref/_ext/gc/Speed.elf (NFSU1 GameCube, symbols). Everything below V unless marked I.
## State (inside the 0xf660 blob of Ugd::PackBlock 0x4ab120, file `<profile>.ugd`)
| What | Where | Proof |
|---|---|---|
| Profile | db 0x7588c4: blob = +0x210, +0x364 (0x18b4 dw), career +0x6634 (0x88b4 B), +0xeee8, +0xeef4, +0x214 | G+C PackBlock |
| Events | 0x75f244 = 0x75eef8+0x34c, byte per event, 2 = won | 0x5a1550/1630/16f0 test `== 2` |
| Rewards | event rec +0x38, count +0x74, {type,value,arg}: 0 part tier, 1 vinyl group, 2 car hash, 3 track+mode | career_oracle.json |
| Cars | CarTypeInfo +0xc58: 0 = always listed (8 cars), 4 = needs unlock (12); event 0 rewards 5 cars, others at events 4 8 17.. (names_unlock.tsv) | chunk 0x34600 bytes |
| Style rewards | flags 0x758ad8, points 0x758ad4, table chunk 0x34a08; sponsor rows 0x75ee04 | 0x4aa970, 0x4aa9d0 |
| Cash, spent, bought, beaten | 0x76026c, 0x760274, 0x75f344, 0x7677ac | all saved |
| New / load / save | Profile::CreateNew 0x41cf40, Load 0x41d030, UnpackBlock 0x4ab200, Ugd::Write 0x41d8a0, Autosave 0x4c96f0 | names_unlock.tsv |
## Checks (each starts with the unlock-everything test)
| Screen | Check | Debug test |
|---|---|---|
| Car lists: Quick Race 0x4bc170, Customize 0x4c66d0, Trade 0x4c3240, Career 0x4c42d0 | c58, cheat kind 0, IsCarUnlocked 0x5a1630 | 0x735ec1 |
| Sponsor/preset rows | byte 0x758ad8[idx] read at 0x4bc34f, 0x4e0fa0 | NONE |
| Parts, perf, rims, decals, paint, vinyl | 0x507e10, 0x509d70, 0x4d7eb0.., 0x4e62b0, 0x5a1550 | 0x735ec1, 0x7677ac |
| Tracks | 0x5a16f0 via 0x4b9f40; WORLD 1010 has no reward | never locked |
## Unlock-all globals the PC already tests (never written in .text; names from GC)
| PC addr | GC name | Effect |
|---|---|---|
| 0x735ec1 byte | UnlockEverythingThatCanBeLocked | every check above + cash 1e9. BEST GATE: its 48 readers match the GC reader set |
| 0x73494c dword | VersionHotImportNights (I) | same, also rival cars, track usage, event map: too wide |
| 0x73440c / 0x735728 / 0x735e10..12 / 0x735e74 | MoneyCheat / UnlockAllParts / paint cheats / AllTracksUnlocked | single purpose |
| rows 0x706918 (obj 0x73765c) | EasterEggs codes: kind 0 car, 1/2 parts lvl 2, 4 tracks, 6 preset | typed on Main menu; no lvl 3/4, no vinyl |
## WORLD detection
Race time: [0x78a2f0] == 1010 (host/free.c:48, set by 0x4b5c00 setups). Menu time: no exe state: Car Select (push 0x4bccc0) runs before Track Select (0x4bb1c0); Customize and garage have no race. So the gate is a host flag set by the WORLD entry (row 8): reuse word 0x13024 (ORed by the 22 caves of PATCH 0x63b370) and byte 0x735ec1.
## Patch candidates (none applied)
| Id | Change | Save writes | Outside WORLD |
|---|---|---|---|
| A | host sets/clears 0x735ec1 + 0x13024 on WORLD enter/leave (today boot-only, default ON, also in Original: web/mode.js:20, host/win32.c:1199) | none | default must become 0 |
| B | cave at 0x4bc34f, 0x4e0fa0: `mov cl,[eax+0x758ad8]; or cl,[0x13024]` (call + nop) | none | unchanged |
| C | price 0 in WORLD at 0x5a265b/61, 0x5a25d6/e2, 0x5a2567/69, 0x4c37de/e0 | avoids cash writes | unchanged |
| X | rejected: writing flags/events into the profile | persists | changes career |
Without C, A pushes cash negative and Autosave writes it (asas0.ugd -9875, garage.md). Parts installed stay on the profile car (FillFromRide).
UNKNOWN: reward type 4; 0x4e3d80 in IsVinylUnlocked; cheat rows in .cfg; no run of A+B+C.
