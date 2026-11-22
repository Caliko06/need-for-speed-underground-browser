# Sound (Speed.exe PC)

Marks: V = read in code or bytes this session, I = inferred, U = open. Tools: G = Ghidra 12.1.4 (REA MCP / headless
`tools/ghidra/gpar.sh`), H = Hopper export `census/hopper/decomp.c`, C = capstone `tools/recomp/asm.py`,
D = data read with `tools/re/ast.py` / `tools/re/abkbank.py`. Earlier work: `docs/re_audio_default.md` (the 9 volume
sliders, `0x4aa200`, category volume `0x51cb70`), `tools/recomp/abk.py` (ABK code modules lifted ahead of time).

## Answer

- **Two kinds of files.**
  - **ABK** (`game/Sound/**`, 106 files): a small x86 code module (the "patch" that plays a sound) plus a `BNKl`
    bank of short samples. There are 94 banks with 469 samples, 6.7 min in all. V (D)
  - **AST** (`game/SNDSTREAMS`, `game/SpeechStreams`): banks of long EA `SCxl` streams packed back to back.
    Music has 27 streams (97 min), stereo ambience 320, mono point ambience 102, special 33, English speech 277.
    V (D)
- **One name table drives every load.** `0x521c80` turns a request {class `+0x38`, index A `+0x3c`, index B `+0x40`} into a
  file name (table `0x6f7f10..0x6f80e8`) and a directory (table `0x6f7eb0`, 23 entries). Classes: 0 FE, 1 stream
  (name + second name per language/variant), 3 environment, 6 impact/scrape, 7 skids (A×5+B), 8 nitrous,
  10 shifting, 12 engine `C<A>U<B>_M0_ENG_MB`, 13 exhaust `C<A>U<B>_M0_EXH_MB`, 14 turbo (A×5+B). V (G)
- **Engine sound = family × upgrade level.** There are 4 engine families (`Car_0..3`) × 4 engine levels
  (`Eng_UG_0..3`). Each pair has an ENG bank and an EXH bank (3 mono loops of ~1.5 s at 22,050 Hz each), a shift
  bank (SML/MED/LRG by level) and a spark-chatter bank. So buying engine upgrades swaps the engine *recording*, not
  only the pitch. V for the file layout and the resolver (G, D). Which car field picks the family: U (asked of the
  sound agent; see below).
- **Music is a playlist, not random.** V (G):
  - The song table `0x6f4d08` (26 × {title, artist, album, "IG"|"FE"}) holds 19 in-game and 7 menu songs.
  - The picker `0x53c3a0` walks the order array at `0x758b58` (stride 8) from the position at `player+0xf8`
    (wraps at 26).
  - It skips songs whose bit is off in `0x758930` (in race: `[0x77a920]==3` or player mode 8) or in `0x758934`
    (menus). These are the EA Trax jukebox toggles in the options block `0x7588c4`.
  - It plays stream `song+1` of `STRM_Music_UG0_MB.ast`. Stream 0 (30 s) is outside the playlist.
  - Mode 99 at `player+0xf0` plays one chosen song (the jukebox preview).
  - `0x51c7b0` points the sound manager's `+0xa8` at the now-playing record (title/artist on screen).

## 1. Files

| Dir (table 0x6f7eb0) | Files | Content (D) |
|---|---|---|
| `Car_<0..3>\Eng_UG_<0..3>\` | 16 dirs × {C?U?_M0_ENG_MB, C?U?_M0_EXH_MB, shifting_*, SparkChatter_0?} | engine + exhaust loops, shifts |
| `TURBO\` | TURBO_00..02, 00A..02C (3 sizes × 4 variants) | turbo spool / blow-off |
| `NOS\` | nitrous_00/01 | nitrous |
| `Skids\` | SKID_PAV(2), SKIDS_DRIFT(2) | tyre squeal by surface / drift |
| `IG_GLOBAL\` | ENV_COMMON, ENV_CHINA01, WIND_00/01, IMPACT, SCRAPE, ROADNOISE_00 | in-game shared |
| `FE\`, `Global\` | FE_MB, FE_COMMON_MB | menus |
| `Evt_Sys\`, `STRMBANK\` | event system banks, stream-bank descriptors | U: role of STRMBANK |

`tools/re/abkbank.py check`: 106 files parse; every non-empty `BNKl` slot is a PT header whose data offset lies
inside the bank, and the header field `+0x14` equals the file size. V (D, 2026-10-29).
ABKC header: `+0x10` module id, `+0x14` file size, `+0x18` header size, `+0x20/+0x24` bank offset/size,
`+0x30/+0x34` relocation tables (`tools/recomp/abk.py`). BNKl: `u16 version=5, u16 slots, u32 size`; slots at `+0x10`
are self-relative offsets (0 = empty) to PT tag lists.

`tools/re/ast.py check` walks all 5 AST files byte by byte: every stream is `SCHl SCCl SCDl* SCEl`, and the gaps
are zero padding only. Coverage is 100 % of the bytes of all five files. V (D). PT tags used: 0x82 channels,
0x84 rate (absent = 22,050), 0x85 samples. Ambience and special streams are 24 kHz; music and speech carry no rate
tag (22,050 Hz default).

## 2. Load path

- `0x51d240` is the sound manager's per-frame service (manager at `[0x7356a8]`; G). It drains the pending-load
  queue (entries 0x1c bytes at `mgr+0x1ec`, `mgr+0x7c` → `mgr+0x78`). For each entry it calls `0x522020`, which
  resolves the name through `0x521c80` and starts the load. Then it updates the object lists `mgr+0xc4`, `+0xd0`
  and `+0xe4` (vtable `+0x30` = update) and the stream manager `mgr+0x104`. V (G); object names: see
  `census/names_sound.tsv`.
- `0x51c5f0` switches the stream set (arg 1..4, 9 → set 5..9) and blocks, servicing loads (`0x58a850`) until no
  slot in `0x72ce58..0x72cfd7` is busy. V (G); I that this runs between front end and race.

## 3. Music selection (detail)

Song table record (16 bytes, `0x6f4d08..0x6f4ea8`): `char* title, artist, album, where` with where = "IG"
(songs 0..18) or "FE" (19..25). V (D).
Picker `0x53c3a0` (V, G). It reads `p = player`, `order = 0x758b58[pos*2]`, where `pos = p+0xf8`.
- In race, it advances while `!(0x758930 & 1<<(order+1))`; otherwise it uses `0x758934`.
- It gives up after 26 tries and leaves the music off.
- It then sets `stream = order+1` into the stream request (+0x4c/+0x54/+0x58) and `p+0xfc = stream-1`, and
  advances `pos`.

## 4. Engine sound chain (sonnet-exec agent, Ghidra; names checked against Hopper, census/names_sound.tsv)

- **Bank choice.**
  - `0x51dec0` (LoadInGameSoundBanks) walks the race entrants: 0x750 bytes each at `[0x78a418]`, `+0x10` RideInfo.
    It keeps local human entrants only (`+4==1`, `+0x734==0`). When `[0x734658]!=0`, every level is forced to 3.
  - **Family A** (classes 12/13) = fixed table `0x6f8100` indexed by car index (`RideInfo+0`, mapped by the
    20-case switch `0x520320`; the switch bytes at 0x5203d4 are not read byte by byte, I). It is not a
    CarTypeInfo field. Car index→family: 0→2, 1→0, 2→0, 3→0, 4→0, 5→0, 6→2, 7→2, 8→1, 9→3, 10→2, 11→2, 12→3,
    13→2, 14→2, 15→3, 16→1, 17→0, 18→2, 19→1.
  - **Level B** = spec `level[2]`, the engine path. TunerCar::Initialize `0x526420` stores it at `this+0x1efc`
    (`mov eax,[edx+0x20]` at 0x526494) and the family at `+0x1ef4`.
  - Turbo: B = `level[3]`, A = `clamp(byte [entrant+0x435], 0..3)` (field U).
  - Nitrous: B = `level[4]`. Skids: B = `level[7]`.
  - The shifting class 0xa is never queued: its `0x521c80` branch is dead, and shift sounds come from the engine
    bank.
  - AI and traffic cars reuse one of two already loaded engine banks (`[mgr+0x68+k*4]`, alternating by
    `[0x78eae4]`, 0x526500..0x526516).
- **Per frame.**
  - `EAXTunerCar::Update 0x52c620` → `0x52c3f0` reads RPM `car+0x3e0` (/ `this+0x1f24`) into `this+0x1f20` and
    torque `car+0x3ec` into `this+0x1f90`.
  - `UpdateTorque 0x527080` / `UpdateRPM 0x527180` smooth them with curve `0x5326f0`.
  - `UpdateEngineVol 0x529cd0` (AI `0x5235a0`) crossfades two volume layers by load `this+0x2ac` (0..0x400) with
    table `0x6f7220`.
  - `0x52bf70` pushes L/R volume, four 0..0x400 values, load and pan to the engine's Csis instance
    (`this+0x1760`, created by `InitializeEngine 0x529b60` in class `0x7441c8`).
- **Down to dsound.**
  - EA's SND software mixer owns the buffers: `DirectSoundCreate` from `0x654340`/`0x654880`, primary `0x71406c`,
    500 ms streaming secondary `0x714070`.
  - The pump `0x654050` runs the 100 Hz server `0x64e330`, then the mixer `0x656d70`, then Lock/Unlock.
  - `EAXSND8Wrapper::Initialize 0x532a20` sets 32 voices and 22,050/44,100 Hz from `0x6f7e88`.
  - `EAXMixMgr 0x5364e0` holds 4 groups × 11 channels, with presets at `0x743ca8` (stride 0x6c).
- Names and the 20 corrections to the x86-ps2 map: agent TSV (night_log.md handoff), to be merged into
  `census/names_sound.tsv`.

## 5. Engine patch: from RPM to the four voice chains (night-opus-a2)

- **Parameters.** `0x52bf70` writes the engine Csis instance (`[this+0x1760]`) every frame. Then `0x64bc30`
  commits it. V (H, 2026-10-29). The Csis param slots are ints:
  | slot | value | scale |
  |---|---|---|
  | `+0x14`, `+0x18` | RPM `this+0x1f1c` | × 0.1024, clamped 0..0x400 (0x400 = 10,000 rpm) |
  | `+0x1c`, `+0x20` | torque/load `this+0x1f8c` | × 10.24, clamped 0..0x400 (0x400 = 100) |
  | `+0x24`, `+0x28` | volume L/R `this+0x238`/`+0x23c` | clamped 0..0x7fff |
  | `+0x44` | `this+0x2ac` (the load used by UpdateEngineVol) | clamped 0..0x400 |
  | `+0x48` | `this+0x6c` | clamped 0..0x10000 |
  | `+0x4c` | pan from the car's i16 `+0x52` | −0x3fff..0x3fff |

  The constants 0.1024 and 10.24 come from `0x3dd1b717` and `0x4123d70a`.
- **The patch is a node graph, not code with formulas.** The ENG module (for example `C0U0_M0_ENG_MB.abk`, module
  id 121576) has one patch function at `+0xa8`. It is 0x5a2 bytes of straight-line code: `push esi; call node; mov
  [esi+k],eax; add esi,size`. Each call evaluates one node whose state block lives in the instance, and each result
  is written into the input slots of later nodes. V (C, capstone on the relocated header, `tools/recomp/abk.py`
  relocate). The node functions live in Speed.exe:
  | node | what it does (H, C) |
  |---|---|
  | `0x64cdd0` (27 uses) | curve: clamps the input to [min,max] of a curve record, then reads an int8/int16 table at `+0x10`, with a float scale at `+0xc` |
  | `0x64d0b0` (23) | product: `a * b * scale` |
  | `0x64db50` (10) | pass-through/copy of three values |
  | `0x64cb90` (4) | gate with hysteresis: on inside window [a,b], off inside window [c,d] |
  | `0x64cf90` (4) | select: `list[index]` |
  | `0x64da70` (4) | ramp/slew toward a target over N steps |
  | `0x64d960` (3) | oscillator (phase wrap, sine through `0x713ca0`) |
  | `0x64d860` (3) | voice node: state 0 stop / 1 start / 2 update; picks the sample from a list by index `+0x14`, then calls the voice-type handlers `0x6e9a98` (start), `0x6e9aa8` (stop), `0x6e9ab8` (update) |
- **Shape (V, C; `tools/re/csiscurves.py`).** The patch instance is a copy of a template in the module header
  (`T = hdr+0x664` for ENG, `+0x65c` for EXH). Every curve node's block starts with a relocated pointer to its curve
  record, so the reader finds T from the relocation table and dumps every curve. The order of the patch is:
  1. A fan-out of the inputs `in0..in17` (`P+0x2c..`).
  2. Two pairs of hysteresis gates on `in0`/`in1`, feeding the trigger node `0x64cc60`.
  3. Three oscillators (`in8..in13`).
  4. A copy node `N194` (from `in3`) that drives 11 curves.
  5. Four identical voice chains: `curve → select → ramp → curve → product → voice 0x64d860` (4 voice nodes,
     corrected from 3).
  `python3 tools/re/csiscurves.py check` reports 32 ENG/EXH patches and 864 curves, every table the length its
  record states.
- **The curves (V, D; meaning I).** Seven curves take input 0..1024, which is the 0..0x400 scale of `0x52bf70`, as
  128 int16 points. ENG `C0U0`, 8 samples from input 0 to 1024:
  | node | values | reads as (I) |
  |---|---|---|
  | N1a0 | 11526 → 30862 → 30005 | loop gain, rising |
  | N1b0 | 25333 → 32767 | loop gain, saturating |
  | N1c0, N1d0 | 1024 → 0 by ~60 % | low loop fades out |
  | N1e0 | 861 → 1024 | high loop fades in |
  | N1f0 | 0 → 190 | small added term (detune?) |
  | N200 | 691 → 20994, linear | pitch ramp |
  Other curves: `0x1bd0` has 1024 points from 32767 down (a crossfade law), and `0x23e0`/`0x2470` are int8 0/1
  selectors over 0..32767 that pick a loop. Upgrade levels of one family share the ENG curves (C0U0 = C0U1); EXH
  differs. Which Csis param is `in3` (RPM or load) is U: a dispatcher in the SND layer sits between `0x52bf70`'s
  block and the patch argument (`0x64bc30` calls `node+8` with `H+4`).

## 6. Speech: who plays the 277 lines (night-opus-a2 + sonnet-exec)

- All 277 lines are played by ONE path: `EAXSound::PlaySpeechStream 0x51c830` and 3 direct callers. All are front-end
  screens (map, garage, Junkman, perf tuner). No race code touches the speech stream. V (C, H)
- The unit is an EVENT id 0..94, not a line. Table `0x6f6bc8` (95 dwords) = number of lines per event. It sums to 277.
  Stream index = sum(count[0..event)) + line. V (D, C 0x539b10)
- Two ways in:
  1. Normal events, vfunc `+0x90(event)`: the line is chosen at random inside the event. 90 events, 244 streams.
  2. Event `0x59` (89), vfunc `+0x98(0x59, line)`: the line is fixed by table `0x6f8728`. 15 lines (streams 236..250).
- Reachable: 259 of 277. Never asked for: events 10, 27, 86, 87 (streams 39-40, 102-105, 231-234) and lines 15..22 of
  event 0x59 (streams 251..258). 18 streams. V (D) for the tables; I that no other table feeds them.
- `0x6f8728` has 15 set entries (lines 0..14). An earlier version of this doc said 7, from reading only 24 dwords. V (D)
- `STRM_English_Speech_MB.abk` (id 1497) holds NO event/line table. It is a stream directory: u32 count 277 at file
  `+0x1d0`, then 277 records {1, AST byte offset, 0} at `+0x1d4`. All 277 offsets equal `ast.py list` offsets. V (D)

### Evidence
1. Class and manager. V (C, H)
   - Stream manager = `EAXSound+0x104` (ctor `0x537930`); `mgr+0x24` = speech stream. `0x537a60` makes it for type
     4..9 (ctor `0x537830`, vtable `0x6bde10`, name `EAXS_SpeechStream` at `0x6be21c`). Other types: 0 music, 1 stereo
     ambient, 2 mono ambient (`0x6be150`), 3 TCM.
   - It is created at front-end load `0x51dce4` (args: type 4, 0x5f groups, `[0x6f6d44]`=0x6f6bc8, `0x6f6f9c[slot]`)
     and at in-game load `0x51eb5b`. Created in race, never called in race.
   - Vtable slots: `+0x90 = 0x53dc30` (mode 1), `+0x98 = 0x53db60` (mode 0). `+0x14` of the manager is the MUSIC stream;
     its `+0x98` callers (0x4afe00, 0x4cf194, 0x4d4aa6, 0x4d4bd4, 0x51c749, 0x53c200, 0x5a45e2) are not speech.
   - String xrefs: "SPEECHSTREAMS\" `0x6bf4a8` only in the path resolver `0x521e8c`; "STRM_English_Speech_MB" `0x6bec7c`
     only in the name table `0x6f7f30`. "EAXS_SpeechStream" only in an unwind funclet `0x68520e`.
2. How the line is chosen. V (C 0x5396a0, 0x53dc30, 0x53db60), partly I
   - Play stores: `obj+0x268 = event`, `obj+0x26c = line`, `obj+0x230 = mode` (0 for `+0x98`, 1 for `+0x90`).
   - `0x5396a0` jump table `0x539aac`: mode 0 = use the given line; mode 1 = line = PRNG(`[0x7356d8]`) mod count[event]
     (inline xorshift); modes 2..4 = repeat / other random picks (not used by speech callers).
   - A flag array (`obj+0x2b0`) marks lines already played; code at `0x539833` skips played lines and resets with
     `0x539dd0`. I: no repeats until the event is used up.
   - Final index: `0x539b10` adds count[0..event) to the line and stores it at `obj+0x270`. Streams `0..276` = AST order.
   - Per-event gain table: `0x6f6e48` / `0x6f6ec8` via `0x6f6f9c[slot]` (volumes, 0x7fff = full). I
3. Callers and tables (event sets by D read of each table). V
   | Caller (screen) | Source of the event | Events | Streams |
   |---|---|---|---|
   | `0x4c5320` career map | table `0x6fa5d0`, 45 pairs {key, event} | 43 | 151 |
   | `0x4c5320`/`0x4c5fa0` | switch `0x4c52d0` (calls 0x4c55a2, 0x4c634c) | 23,25,29,31,46,47,52,59,61 | 29 |
   | `0x4c6cb0` Junkman | switch `0x4c6c00` (`GetJunkmanRewardSpeech`) | 24,26,28,30,32 | 12 |
   | `0x4c7790` | switch `0x4c76d0` | 48,53,60 | 10 |
   | `0x4c3db0` garage, `0x4cd490`, `0x50a5d0` perf tuner | table `0x6fa7f0`, 25 pairs {flag bit, event}; one-shot, bit set in `[0x76029c]` after play | 62..85, 88 | 30 |
   | `0x4cd3e0` | table `0x6fa738`, 15 pairs {key, event} | 5,12,19,22,39,45,49,50,51,54..58,94 | 48 |
   | `0x4c5fa0` (0x4c6319), `0x4c5320` (0x4c54ec) | `0x4c5200` returns id; `0x6f8728[id*2+variant]` = line of event 0x59 | 0x59 | 15 lines |
   | `0x513780` (called by 0x513610) | ids from `0x6f88f8` (27 entries) -> `0x6f872c[id*2]` -> `+0x98(0x59, line)` | 0x59 | same 15 |
   - Union of the event sets (events overlap between callers): 90 events, 244 streams. Plus 15 lines of event 0x59 = 259.
   - Screen meaning is I (names from `census/names*.tsv`: 0x4c3db0 garage main, 0x4c6cb0 Junkman, 0x50a5d0 perf tuner;
     0x4c5320 / 0x4c5fa0 are career map openers per `tools/hopper/q_hub.py`). Race start, rival taunts: no caller found.
4. Event 0x59 table `0x6f8728[id*2+v]` (id 1..26): id2 -> 0,1; id5 -> v1 2; id6 -> v1 3; id7 -> v1 4; id11 -> 5,6;
   id12 -> 7,8; id13 -> 9,10; id15 -> v1 11; id16 -> v1 12; id17 -> 13,14; all else -1 = stop (`+0x90(0x59)`). Entry 0
   holds two string pointers ("Fabolous" ...), skipped because the caller tests `id >= 1`. V (D)

## Open (U)
- `entrant+0x435` (turbo variant); the 0x520320 switch read byte by byte.
- Engine patch: which Csis param feeds each patch input (in0..in17); the curve values are dumped (§5), their roles are I.
- Speech: what each of the 95 events says (needs a listen); modes 2..4 of 0x5396a0; whether any caller reaches the
  speech object without its `+0x90`/`+0x98` slots (§6 scanned only those).
- Mixer path to dsound: the categories and sliders are in `docs/re_audio_default.md`. The voice/3D mixer names
  are in `census/names_sound.tsv` (EAXS_3DMixer, EAXMixMgr, EAXSND8Wrapper).
