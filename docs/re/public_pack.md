# Public pack: what the browser downloads
Run 1: `:5180/?play=1&pool=1&mode=remaster&mute=1`, cold headless Chrome, CDP Network log of page + workers (every sync XHR Range). Marks: exe loaded 0.5 s, first Present 1.6 s, front end ready 2.15 s, city ready 19.6 s, race HUD 23.6 s. Data: census/public_pack.tsv (1966 rows), census/names_files.tsv. Run 2 (menu route) died at 2.6 s: `STOP ... __syscall_mkdirat`, web/out was being rebuilt by another worker; not repeated (2-run limit). "Menu" below = front end ready before the WORLD jump (INFERENCE).
## Bytes on the wire (MB, uncompressed except speed.wasm = gzip 16.4 of 70.4)
| Phase | web/out+pc | game/ | web/remaster | web/ug2 | build/openworld | page js | Total | Reqs |
|---|---|---|---|---|---|---|---|---|
| link -> menu (0-2.15 s) | 18.8 | 15.3 | 7.7 | 0.0 | 0.5 | 0.3 | 42.5 | 415 |
| menu -> driving (2.15-23.6 s) | 0.0 | 135.1 | 27.0 | 199.7 | 17.4 | 0.1 | 379.3 | 2518 |
Link -> driving = 421.8 MB; the next 20 s of driving add 1.8 MB (SNDSTREAMS). Fetched bytes include host/files.c read-ahead (256 KB, doubling to 4 MB), so they are >= what the game reads.
## Top 10 per phase (MB)
| # | link -> menu | MB | menu -> driving | MB |
|---|---|---|---|---|
| 1 | out/speed.wasm (gz) | 15.7 | ug2/city.bin | 98.6 |
| 2 | remaster/bc/* (many) | 7.4 | ug2/tex/*.png (1489) | 57.0 |
| 3 | game/FrontEnd/Road_Segment.bin | 6.1 | game/Tracks/STREAML1RA.BUN (66 ranges) | 54.8 |
| 4 | game/FrontEnd/FrontB.lzc | 4.0 | ug2/city_tex.bin | 43.7 |
| 5 | pc/Speed.exe | 3.0 | remaster/bc/* (829 files) | 27.0 |
| 6 | game/Sound/FE/FE_MB.abk | 1.8 | world/CARS_TEXTURES.BIN | 10.6 |
| 7 | game/Languages/LanguageTextures.bin | 1.1 | game/Cars/SKYLINE/GEOMETRY.BIN | 6.8 |
| 8 | game/Global/GlobalB.lzc | 0.9 | world/TRACKB1010.lzc | 5.4 |
| 9 | world/DYNTEX.BIN | 0.25 | game/Cars/GOLF/GEOMETRY.BIN | 3.8 |
| 10 | game/Cars/WHEELS/GEOMETRY.BIN | 0.25 | game/Cars/LANCER/GEOMETRY.BIN | 3.7 |
## Never opened (no Speed.exe literal in census/game_files.json, no request in run 1): 56.1 MB
| Group | Files | MB | Note |
|---|---|---|---|
| game root: setup.exe, AutoRun*, SECDRV.SYS, RunGame.exe, NFSU20MEG.bin (20.2), 0000000*, *.TMP, readme, filelists, .DS_Store | 17 | 22.9 | installer leftovers |
| game/Support/ (25), 3DSetup/ (3), AutoRun/ (2) | 30 | 5.7 | EReg, uninstall, dicts |
| web/ug2/city_lod.bin | 1 | 27.5 | web/ug2/ug2world.js:91 fallback only when city.bin is absent |
Opened in run 1: game 118 files, ug2 1491, openworld 4. UNKNOWN (opener exists, WORLD never asked; needs the menu/Original run): Cars 47 files 177.7 MB, Tracks 98 files 200.0 MB, Movies 23 files 164.8 MB, SpeechStreams 1 (17.5), SNDSTREAMS 2 (14.4), Sound 91 (21.1), FrontEnd 3 (18.9), Languages 29 (3.4), Global 6 (8.3). No exe literal, UNKNOWN: FrontEnd/TSELECT.BIN 12.3, Global/Street.bin, CHARACTERSA.BIN, Languages/LANGUAGE_*.bin, Labels.bin, Largest.bin.
Opener chain (V = literal + xref, I = inferred): bOpenFile 0x594c60 / queue AsyncRead 0x58aba0 (I) -> EAFile_QueueOpen 0x63a5d0 -> device op 0x6391e0 (call 0x639246) -> EAFile::DeviceOpen 0x63d1c0 -> CreateFileA 0x63d333 / 0x63d37f (V); reads ReadFile 0x63d5b6 (V). Movies: _fopen 0x671541 -> CRT 0x680aa6 -> CreateFileA 0x680c83 (V).
| Family | Opening code (string ref) | When in run 1 | Whole or ranges |
|---|---|---|---|
| fx/*.efx | Effects_CreateAll 0x40e180, bOpenFile call 0x40e2ca | boot 0.5-0.9 s | whole (2-8 KB) |
| Global, Languages, FrontEnd | LoadGlobalA 0x448600, LoadGlobalB 0x448650 (.lzc 0x44865f; .BUN only names the slot 0x44867c), InGame 0x44933c, HUDTEX/DYNTEX table 0x7007b0; Language_LoadTextureBin 0x59f7c0 + table 0x6ee658 (English only); LoadingFrontEndPart1 0x448b10, Road_Segment 0x448adb | boot 1.0-1.9 s; InGameB 11.9 s | mostly whole, 256 KB steps |
| Cars | CarLoader::AllocateSkin 0x58bb50 (TEXTURES 0x58bbdf, VINYLS 0x58bc27); GEOMETRY path string is data in GLOBALB.BUN (offset 1678928); parts table 0x7007a0 | player SKYLINE 2.2-3.2 s; pool + traffic cars 12.0-14.0 s | ranges: GEOMETRY ~3.5 of 5.5 MB, VINYLS 0.3-2 of 16 MB, WHEELS shared pack by offset |
| Tracks | LoadingTrackSpecific 0x4491a0 (TRACKB 0x4497be, STREAM%s 0x44970d/0x44972c, TEX%dTRACK 0x44953e) | STREAML1RA.BUN 15.0-16.2 s (WORLD maps to base track; TRACKB1010 comes from /world/) | ranges: 48.1 of 88.1 MB |
| Sound/*.abk, EVT_SYS/*.csi | EAXAemsManager::Initialize 0x5212e0, SetCurrentBankPath 0x521c80, LoadAemsBank 0x522020 | FE banks 2.0 s; engine/skid/env banks 14.2-14.5 s | whole or near-whole |
| SNDSTREAMS/*.ast | SetCurrentBankPath 0x521c80 (SNDStreams\ 0x521e74, .ast 0x521e4c), probe 0x521b90 | Music_UG0 2.2, 10.4, 17.0, 25 s; AMB_Stereo 16.5, 24.5, 26-37 s | ranges of 256-512 KB: 3.0 of 241 MB |
| SpeechStreams, Movies | 0x521e8b SPEECHSTREAMS\ ; MoviePlayer::BuildPath 0x4f57a0 (ref 0x4f57af) | not requested | UNKNOWN |
| web/ug2 | web/ug2/ug2world.js:68 city.bin, :78 city_tex.bin, :91 bridge, :94 tex.json, :155 tex/*.png | city ready 19.6 s (loads only in WORLD) | whole files |
Not VERIFIED: the real menu path (title, profile, Quick Race), Original mode tracks, other languages, any non-localhost timing or compression ratio of the data files. REA MCP was not available in this session: second tool = Ghidra decomp + objdump (census/ghidra/, pc/Speed.exe).

## First-play reduction, slice/loadfast, 2026-11-14

FACT: cold browser contexts, headless and muted, same `:5181/?play=1&pool=1&mode=remaster&mute=1` before/after. CDP records page and workers, including in-flight `Network.dataReceived` bytes. Chrome applies 50 Mbit/s at the page context (worker XHRs are also slowed); no added RTT. Three paired runs: calibration, baseline, after. Two earlier CDP setup failures stopped before game startup. Each paired run is bounded to 295 s. `tools/loadfast.mjs` reproduces the capture; `tools/loadfast_report.py` places the milestones using the page log. Menu means the first `flow state 3/255` (front end active, before the automatic WORLD jump), not a manual main-menu route. Byte units below are decimal MB, not MiB; all totals are cumulative from the link.

| Case | Menu MB / requests / seconds | WORLD HUD MB / requests / seconds | HUD + Bayview drawn MB / requests / seconds |
|---|---:|---:|---:|
| Before, local | 40.8 / 326 / 1.70 | 441.4 / 2960 / 22.67 | 441.4 / 2960 / 22.67 |
| After, local | 37.1 / 97 / 3.31 | 286.6 / 590 / 24.33 | 286.6 / 590 / 24.33 |
| Before, 50 Mbit | 46.0 / 348 / 8.65 | 301.0 / 1599 / 58.19 | 471.7 / 3133 / 85.97 |
| After, 50 Mbit | 36.6 / 99 / 7.41 | 240.8 / 684 / 53.69 | 302.4 / 706 / 64.57 |

| Case | Menu -> HUD MB / requests / seconds |
|---|---:|
| Before, local | 400.6 / 2634 / 20.97 |
| After, local | 249.5 / 493 / 21.02 |
| Before, 50 Mbit | 255.0 / 1251 / 49.54 |
| After, 50 Mbit | 204.2 / 585 / 46.28 |

FACT: at 50 Mbit, the fully drawn WORLD costs 169.2 MB less (35.9%), 2427 fewer requests (77.5%), and arrives 21.4 s sooner (24.9%). The HUD alone does not mean Bayview is ready: the city already loaded asynchronously before this change. The local total time regressed 1.66 s; menu -> HUD stayed about 21 s. INFERENCE: the new build's first local request also regenerated the server's wasm gzip, whereas the baseline server already had it from calibration. This was not isolated in another run. Each case is one sample; the traffic pool and music selection vary.

Changes and exact paths:

- `host/files.c:web_read`: 64 MiB LRU of immutable fetched ranges per reading worker, reused across file handles. A request fully contained in a cached range avoids XHR. At 50 Mbit, CARS_TEXTURES went from 61 requests / 11.96 MB to 55 / 9.34 MB. **Remaining waste:** overlapping ranges are not merged, and workers do not share this cache. This is a partial reduction, not elimination of the repeated-file problem.
- `tools/pack_loadfast.py` + `web/ug2/ug2world.js:packed/textures/load`: explicit gzip streams and one indexed PNG payload, using browser-native `DecompressionStream`, `Blob.slice`, and `createImageBitmap`. City mesh 103.38 -> 39.40 MB; UV sidecar 45.78 -> 2.89 MB. Texture requests 1482 in these runs -> one 59.26 MB pack; every PNG byte is preserved. Both after logs report 1482 textures, 1483 draws, **0 failed**. This uses the current exports, whose texture count differs from the older 1489-file observation.
- `web/gpu.js` and `web/launcher_opts.js`: the texture pack requires explicit `?remaster=1`; mode `remaster` alone leaves it off. No Remaster texture asset transfers in either after case (a small off-list TSV remains). All music files and their range reads remain. No guest executable patch or change to Original's gameplay paths.

Prepare assets after every UG2 export, before serving or static packaging: `python3 tools/pack_loadfast.py`. The five generated `web/ug2/*.gz` files are required and ignored by git, like the source city exports. Upload them unchanged; decoding is explicit, so no Content-Encoding configuration is required. Do not configure a static host to automatically decode these `.gz` files. `tools/build_public.py` was not changed. The existing pack links the whole ug2 directory; its new pack-building lane must retain these five files. The host C build used `RN_JOBS=4 .venv/bin/python tools/recomp/build.py web`.

Evidence: `census/loadfast.json` (phase totals, hashes and file counts); raw page/worker CDP captures and timed logs in `build/loadfast/{baseline,after}/`; inspected screenshots `/plan/shots/loadfast_before50.png` and `/plan/shots/loadfast_after50.png`. Code-path census: `census/names_files.tsv`. Prior art consulted: [NFSU2Recomp](https://github.com/TalhaMudo/NFSU2Recomp), [nfsu2-sw performance notes](https://github.com/antoxa2584x/nfsu2-sw/blob/main/PERF_NOTES.md), and [CDP Network](https://chromedevtools.github.io/devtools-protocol/tot/Network/). The chosen implementation uses the browser's gzip decoder and existing game file ranges rather than another runtime library.

UNKNOWN / not verified: real WAN RTT or public hosting, other devices/browsers, manual menu navigation, Original tracks, explicit Remaster opt-in execution after the gate change, audible music (runs must be muted), and long-session memory. Whole-city spatial streaming and a new loading-progress UI were not implemented; row 4 is not fully VERIFIED by this slice.
