# Misc: the "unknown" bucket of census/systems.tsv (Speed.exe PC)

> Source: `docs/re/misc.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 50

# Misc: the "unknown" bucket of census/systems.tsv (Speed.exe PC)

Marks: V = read in code or bytes and a second tool agrees, I = inferred (one tool, or shape of code), U = open. Tools: H = Hopper export
`census/hopper/decomp.c`, G = Ghidra export `census/ghidra/decomp_*.c`, C = capstone over pc/Speed.exe (`.venv/bin/python`, helpers from
`tools/verify_re.py`). Files: `census/names_misc.tsv` (67 names), `census/systems_override.tsv` (601 rows, each with the evidence read).

## Answer
- Of the 1,560 lifted functions tagged unknown, 1502 had no name in names_*.tsv and are not listed in names_seed.tsv. 857 of those ran in the coverage scenarios (census/cov/union.json).
- 601 are reassigned in `census/systems_override.tsv` (503 of them ran). 67 get a name in `census/names_misc.tsv` (names are my reading, all I except
  the ones marked V in the file).
- The bucket is not "unknown code". 42% of it (625 functions, all above 0x684000) is compiler glue: static initializers, `atexit` registrations and
  destructor funclets. Their system is the system of the global or object they build, which only the readers of that global tell.
  The rest (0x401000-0x684000) is small helpers that sit under a named parent.
- Still unclassified after this pass: 904 functions (357 ran): 264 ran functions below 0x684000 that I did not read, 93 ran glue
  functions above 0x684000 (83 are `ctor + atexit` stubs whose ctor is itself unnamed), 547 never ran.
- Nothing here changes game behaviour. No edit outside the three files.

## Clusters
| cluster | where | count in override | what it is | system | evidence |
|---|---|---|---|---|---|
| Derived math constants | 0x689930-0x696170 | 422 | `fld [rdata const]; fmul/fadd [const]; fstp [global]` run once at startup: the compiler's dynamic init of `static const float X = a*b` (pi*0.5, 2*pi, deg2rad multiples; 0x6cc7dc = 0.5, 0x6b5c24 = pi, C reads). The written global has no code reader in a disp32 scan of .text. | runtime | C: instruction pattern of each function (shown in the evidence column) |
| Static init / dtor funclets with a reader | 0x689xxx-0x696xxx | 65 | `mov esi, G; call ctor; push dtor; call 0x67100d (atexit)` or a funclet that calls a destructor. System = majority of named functions that read G (>=60 % of votes; shown in the evidence column). 22 of them have two or more readers and get a `StaticInit_<reader>_G<addr>_<func>` name. | assets 32, car 13, camera 5, audio 4, traffic 3, others 8 | C refs scan of .text (disp32/imm32) + names.tsv |
| String-hash initializers | 0x68ab60, 0x68abc0, 0x692530, 0x692cb0, 0x692ce0 | 5 | `h = 0xffffffff; for c in str: h = h*0x21 + c` over an rdata string, stored in a global: "Bip01", "SALLY" (NIS rig names), "EXHAUST_TIP_DECAL", "Rotate_360_t/q". The same loop is `bStringHashSeeded` 0x567ca0. | camera, car | C: string bytes read from rdata |
| Vector / matrix math | 0x401xxx-0x402xxx | see below | Matrix4 inverse (0x4020b0) and its cofactor helper, vec3 copy/scale, `DegToRad` 0x4055e0 (= x * 0.017453292), angle16 conversion | runtime | H+C (DegToRad: constant read at 0x6cca50) |
| Runtime utilities | 0x4010xx, 0x50xxxx, 0x56xxxx, 0x58xxxx | see below | circular list head init `IList_InitEmpty` 0x589260 (`*eax=eax; eax[1]=eax`), `RandomInt` 0x564a50 (state 0x6f227c, `% n`), wchar buffer class (`WString_Grow/Assign/Free` 0x5040e0/0x504080/0x504010), `StringList_Find` 0x53e4f0, `FileSystem_Create` 0x63a3f0, CPU detect 0x41e860 | runtime | H+C, G for 3 |
| SNDSTRM request queue | 0x411be0-0x412930 | see below | request alloc/push/service around `SNDSTRMI_queue`, `STRM` magic 0x4d525453 checks, size formula `SNDSTRM_OverheadBytes` 0x4124d0 | audio | H+G (formula identical in both) |
| FEng screen base and helpers | 0x4134d0-0x41f4d0, 0x4f08f0-0x4f89d0 | see below | object lookup chain 0x4f65d0 / 0x4ffb70 / 0x4ef050 (same as `HudWidget::RegisterObjectByHash`), screen base ctor 0x41f0c0, message handler 0x41f240 (hash 0xc98356ba), list node alloc 0xabadcafe fill | canon | H |
| Player / Car / RaceManager sub-functions | 0x421xxx-0x4a4xxx | see below | one-caller helpers of `Player::ComputeHudFlags`, `RaceManager::UpdateAIScore`, `Car::ServiceResetRequest`, `Player::StartRaceCameras`; Car field tables | rivals, hud, car, camera | H, parent named |
| Renderer sub-functions | 0x4016e0, 0x542xxx-0x570xxx | see below | D3D device reset (0x4016e0), car lit-body paths A and B (0x5437f0 2951 B, 0x542e40 2455 B), frame car draw 0x570db0 | render | H |
| Hud / audio / assets leaves | various | see below | callees of `HudSmokeApplause::Update`, `HudTachDrag::Update`, `EAXSound::Update`, `LightPack_Load` (chunk-id switch 0x40c4b0), `CarLoader::AllocateSkin` | hud, audio, assets | H |

Counts of the 114 rows below 0x684000 by system (from the override file): runtime 20, audio 16, car 15, render 11, camera 11, hud 10,
canon 9, rivals 7, assets 5, traffic 4, track 3, online 1, input 1, props 1. 101 of the 114 ran.

## What is weak
- The 422 math-constant initializers are tagged runtime because the function is startup glue; the module that owns the constant is unknown (no
  reader). They are honest about what they are, not about who uses them. If the OWNER prefers, they can be dropped from the override and
  stay unknown: the 179 other rows do not depend on them.
- The 65 funclet rows with readers trust that a global is used by one system. Rows whose readers split are skipped, not guessed.
- Names are readings. Only rows with a V mark in names_misc.tsv were seen identically in two tools.
- Not checked: whether tools/census/systems.py applies `systems_override.tsv` (it does not read it today; I did not edit it).

## Re-derived with a second tool (10 rows)
First tool H, second tool C (capstone over pc/Speed.exe) or G, run in this session.
| # | addr | claim | second tool | result |
|---|---|---|---|---|
| 1 | 0x4055e0 | DegToRad: `x * 0.0174533` | C: `fld [esp+4]; fmul [0x6cca50]; ret`, f32 at 0x6cca50 = 0.01745329238 | agrees |
| 2 | 0x567ca0 | `eax = eax*0x21 + byte` loop (bStringHash with seed) | C: `imul eax,eax,0x21 ... add eax,ecx`, loop to NUL | agrees |
| 3 | 0x589260 | circular list head init | C: `mov [eax],eax; mov [eax+4],eax; ret`; G: called as `FUN_00589260(param_1, ...)` from ctors | agrees |
| 4 | 0x564a50 | `RandomInt`: `state % n`, xor 0x1d872b41, shifts 5 and 0x1b | C: `div dword [esp+4]`, `xor ecx,0x1d872b41`, `shr 5`, `shl 0x1b`; G: `DAT_006f227c % param_1`, same xor/shifts | agrees (both tools) |
| 5 | 0x4124d0 | `a*0x128 + (b*3+0x7b)*4 + (c<<4)` | C: `imul ecx,ecx,0x128; lea eax,[eax+eax*2+0x7b]; lea [ecx+eax*4]; shl edx,4`; G: `param_1*0x128 + (param_2*3+0x7b)*4 + param_3*0x10` | agrees (both tools) |
| 6 | 0x41e860 | CPU detection with cpuid | C: `cpuid` present in the first 80 instructions | agrees |
| 7 | 0x692ce0 | static hash of "Rotate_360_q" | C: rdata string at 0x6ba5e8 reads "Rotate_360_q"; same loop; hash 0x7799e3f6 computed offline | agrees on string and loop; stored value (0x73b0b8) NOT VERIFIED at run time |
| 8 | 0x4134a0 | thin wrapper over `_malloc` | C: `push eax; call 0x67121a; add esp,4; ret` | agrees |
| 9 | 0x504010 | WString_Free: free if non-null | C: `mov eax,[ecx]; test; je; push eax; call 0x671102` | agrees |
| 10 | 0x42ad10 | CameraMoverBase_InitFields (zeroes fields) | C: 18 `mov dword [eax+...]` stores in 120 bytes, starts with `xor ecx,ecx; mov [eax],ecx; mov [eax+4],ecx` | agrees on shape; that the 5 named camera ctors call it comes from H only, so it stays V on shape and I on role |

## Rerun
Scratch scripts (candidate list, dossier, global-reader index) were in the session scratchpad, not in the repo. To redo: lifted list = `f_<hex>(` in
build/gen/f*.c; unknown = systems.tsv; reader index = capstone linear sweep of 0x401000-0x697000 for disp32/imm32 operands in 0x697000-0x7a0000.

HANDOFF: next pass reads the 265 unread ran functions below 0x684000 (list = unknown, not in override, in union.json, sorted by callers), then
asks the OWNER whether tools/census/systems.py should read census/systems_override.tsv.
