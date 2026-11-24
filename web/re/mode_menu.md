# Native Original / Remaster menu button

> Source: `docs/re/mode_menu.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 19

# Native Original / Remaster menu button

OWNER 2026-11-14: add a seventh main-menu button in both modes. This is the sole permitted addition to Original's shipped menu. No shipped action is relabelled.

| Address / data | Evidence and use |
|---|---|
| `0x4b309b` | `Screen_MU_Main_PC` ctor tail, after package initialization; original `mov [0x748f75],dl` retained by cave `0x797640`. objdump + Hopper `sub_4b2c33` (`ev_d551896b782bf50c24cef5f5550038e5280f4285740833ff39e6978b16903884`). |
| `0x4f65d0` | Loaded-package lookup, EAX name -> package. Calls `0x4f3f90` with registry `0x746104`, then reads node `+0x18`. objdump + Ghidra `FUN_004f65d0`. The active-package list is populated after the main ctor returns; first runtime run proved it is too early there. |
| `0x5009a0` | FEString virtual Clone(bool), ECX source, ret 4. Clone STATISTICS (`0xf20e404a`) with false; base `0x4fec30` assigns a unique instance id and duplicates scripts/messages. objdump + REA/Hopper (`ev_3a183b5e349d5c2b86436faaf1bfa02149d4d66033c8f468ca6a1744a9dba32f`). |
| `0x5013a0`, `0x5017d0` | `Butn` count becomes package `+0x88`, pointer array `+0x84`; loader fills it for flag `0x10000000`. Object list count/head/tail `+0x3c/+0x40/+0x44`, sibling next/prev `+4/+8`. objdump + Ghidra/Hopper. |
| `0x4ff030`, `0x5001b0`, `0x4fcb20` | Position uses parameter slots 7..9. Frames stride `0x38`, target slot byte `+7`, position kind `4`, inline Y `+0x1c`, subsequent key Y `+0x14`. Shared key wrappers at frame `+0x28` are resolved and copied with `0x4fcb20` before moving tracks. objdump + Ghidra/Hopper (`ev_e3cceead77090312cd3b7ea40a4476d53538c182a946d1c322fa73a7dd2a3cb9`). |
| `0x4f68a0` | EAX object, cdecl format string sets custom text using `0x4f6780`. Target label comes from browser mode passed as `RN_MODE`. objdump + REA/Hopper (`ev_b0a19e000c501c2d6d6a8125ed673527c8a5587d0c6164a56a90ce5b5258cc79`). |
| `0x4b33db` | Main accept message `0x0c407210` already passed transition guard. Cave `0x797660` recognizes reserved object hash `0x5f524e4d`, calls host slot `0x130d8`, exits through `0x4b3769`. Others retain original `cmp eax,0xa936c3a2` and branch flags. objdump + REA/Hopper `0x4b3240`. |

Implementation: `host/mode_menu.c`, `tools/recomp/patches_mode_menu.py`. Clone inserted below STATISTICS; CUSTOMIZE, OPTIONS and Online/WORLD move down one 42-unit row. JS `window.rnSwitchMode` is shared with second F4; stores `rn_mode`, changes any URL mode override to the chosen mode and reloads the page.

Prior art: [NFSU2Unlimiter FEPackage.h](https://github.com/nlgxzef/NFSU2Unlimiter/blob/master/FEPackage.h), virtual object cloning followed by linked-list insertion. UG1 offsets above are independently verified, not copied from UG2.

Validation (FACT): `RN_JOBS=4 .venv/bin/python tools/recomp/build.py web` passed. Two headless launches on 5183 / CDP 9384, muted. Run 1 was stopped after identifying the premature active-list lookup. Run 2 took 116.1 s; entered Original with seven buttons and `MODO REMASTER`, then ArrowDown twice + Enter reached the new accept handler. CDP observed `RN_MODE=remaster`, `localStorage.rn_mode=remaster`, URL `mode=remaster`, and a fresh boot. After Enter on the profile screen the new menu logged `MODO ORIGINAL`, seven buttons. Final inspected screenshot: `web/plan/shots/mode_button.png` (1280x900).

Known limitation (FACT): the new entry accepts keyboard navigation but does not inherit the native focus highlight artwork; focusing it shows the shipped placeholder `RACE MODE DESCRIPTION`. The six original highlight backgrounds retain their shipped positions while their lower three labels move down. These cosmetic differences are visible; they are not claimed fixed. UNKNOWN: Remaster -> Original acceptance, double-F4 after refactor, mouse/touch/gamepad, real display. No third run was made.
