# Binary Symbol Census & Evidence-First Naming (59 Tables, 18,293 Rows)

> Open dataset and methodology for naming stripped x86 binaries without hallucinations.
> Source: `census/names*.tsv` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Hub: https://nfsu.cc/reverse-engineering/index.html

## ELI5: What is a Symbol Census?

When a C++ program is compiled for release, the compiler strips away all human-readable function names (`UpdateCarPhysics`, `DrawShadow`, `PlayEngineSound`). All that remains are raw memory addresses like `0x0043a001`. A **symbol census** is a giant shared dictionary mapping those raw addresses back to real names, with a strict trust badge on every row so nobody confuses a proven fact with a guess.

## Technical Methodology: `V / I / U` Confidence Tagging

Every entry across our **59 subsystem TSV tables** (`18,293` total rows, `7,886` verified `V`-tagged) carries a single-letter provenance tag:

- **`V` (Verified)**: Directly confirmed in disassembled/decompiled instructions, PE bytes, string xrefs, or runtime differential traces (`REA MCP`, `Ghidra`, `Hopper`).
- **`I` (Inferred)**: Strongly suggested by caller/callee context or struct layout, pending direct instruction-level verification.
- **`U` (Unknown / Open)**: Candidate address or placeholder awaiting proof; no downstream patch or compiler assumption may depend on a `U` row.

## Sample Verified (`V`) Binary Symbols

| Virtual Address | Symbol Name | Evidence / Role | Census Table |
|---|---|---|---|
| `0x401010` | `ScratchAlloc16` | runtime | `names.tsv` |
| `0x401110` | `GameFlow::InitMainPoolAndTimer` | runtime | `names.tsv` |
| `0x401190` | `Registry::ReadInstallSettings` | runtime | `names.tsv` |
| `0x4016e0` | `Render_PresentFrameAndPumpFE` | render | `names.tsv` |
| `0x401b30` | `GetSkuString` | runtime | `names.tsv` |
| `0x401c60` | `bMin` | runtime | `names.tsv` |
| `0x401c80` | `bClampF` | runtime | `names.tsv` |
| `0x401dc0` | `Node_SetNameAndHash` | runtime | `names.tsv` |
| `0x401e50` | `QuadBuffers_Create` | render | `names.tsv` |
| `0x401f30` | `Random_NextFloatSeeded` | runtime | `names.tsv` |
| `0x401f70` | `Matrix4_Determinant` | runtime | `names.tsv` |
| `0x402720` | `Acid::InitSlotPools` | traffic | `names.tsv` |
| `0x402820` | `Particle_Load` | assets | `names.tsv` |
| `0x4028f0` | `Particle_Unload` | assets | `names.tsv` |
| `0x4029a0` | `Particle_ResolveTextures` | render | `names.tsv` |
| `0x4049f0` | `List_DeleteAllNodes` | runtime | `names.tsv` |
| `0x404a70` | `List_ReleaseAllToPool` | runtime | `names.tsv` |
| `0x404ab0` | `bFatalError` | canon | `names.tsv` |

## Complete Index of All 59 Symbol Census Tables

| Table in Repository | Total Rows | `V`-Verified Rows |
|---|---:|---:|
| [`census/names.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names.tsv) | 7,584 | 4,857 |
| [`census/names_aiplus.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_aiplus.tsv) | 12 | 0 |
| [`census/names_assets.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_assets.tsv) | 187 | 0 |
| [`census/names_audio_w4b.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_audio_w4b.tsv) | 49 | 27 |
| [`census/names_blur.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_blur.tsv) | 62 | 52 |
| [`census/names_camera.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_camera.tsv) | 304 | 46 |
| [`census/names_car.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_car.tsv) | 120 | 0 |
| [`census/names_carfx.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_carfx.tsv) | 42 | 37 |
| [`census/names_collision.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_collision.tsv) | 18 | 18 |
| [`census/names_core_w3.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_core_w3.tsv) | 238 | 149 |
| [`census/names_crash.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_crash.tsv) | 9 | 7 |
| [`census/names_duel.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_duel.tsv) | 8 | 8 |
| [`census/names_files.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_files.tsv) | 25 | 0 |
| [`census/names_frontend.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_frontend.tsv) | 30 | 21 |
| [`census/names_game_w1.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_game_w1.tsv) | 90 | 36 |
| [`census/names_game_w3.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_game_w3.tsv) | 28 | 14 |
| [`census/names_gameflow.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_gameflow.tsv) | 170 | 0 |
| [`census/names_gps.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_gps.tsv) | 19 | 19 |
| [`census/names_gpu_w5.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_gpu_w5.tsv) | 301 | 1 |
| [`census/names_hud.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_hud.tsv) | 445 | 0 |
| [`census/names_hudcar_w2.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_hudcar_w2.tsv) | 60 | 22 |
| [`census/names_input.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_input.tsv) | 50 | 0 |
| [`census/names_lib.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_lib.tsv) | 153 | 0 |
| [`census/names_misc.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_misc.tsv) | 73 | 0 |
| [`census/names_misc_w2.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_misc_w2.tsv) | 59 | 29 |
| [`census/names_online.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_online.tsv) | 21 | 0 |
| [`census/names_physics.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_physics.tsv) | 29 | 23 |
| [`census/names_props.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_props.tsv) | 28 | 0 |
| [`census/names_raceai.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_raceai.tsv) | 54 | 43 |
| [`census/names_racesetup.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_racesetup.tsv) | 54 | 51 |
| [`census/names_render.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_render.tsv) | 210 | 0 |
| [`census/names_render_w2.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_render_w2.tsv) | 226 | 220 |
| [`census/names_render_w3.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_render_w3.tsv) | 21 | 8 |
| [`census/names_render_w4b.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_render_w4b.tsv) | 51 | 42 |
| [`census/names_rivals.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_rivals.tsv) | 207 | 20 |
| [`census/names_roadid.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_roadid.tsv) | 392 | 387 |
| [`census/names_runtime.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_runtime.tsv) | 255 | 0 |
| [`census/names_runtime_w2.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_runtime_w2.tsv) | 59 | 39 |
| [`census/names_runtime_w4b.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_runtime_w4b.tsv) | 194 | 149 |
| [`census/names_save.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_save.tsv) | 5 | 5 |
| [`census/names_seed.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_seed.tsv) | 2,926 | 0 |
| [`census/names_sound.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_sound.tsv) | 399 | 1 |
| [`census/names_statemachines.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_statemachines.tsv) | 48 | 48 |
| [`census/names_tier_content.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_tier_content.tsv) | 4 | 4 |
| [`census/names_tier_ram.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_tier_ram.tsv) | 3 | 3 |
| [`census/names_track.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_track.tsv) | 120 | 0 |
| [`census/names_traffic.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_traffic.tsv) | 120 | 0 |
| [`census/names_traffic_w4.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_traffic_w4.tsv) | 22 | 15 |
| [`census/names_trafficpool.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_trafficpool.tsv) | 26 | 24 |
| [`census/names_trivial.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_trivial.tsv) | 1,742 | 1,254 |
| [`census/names_tuning.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_tuning.tsv) | 364 | 0 |
| [`census/names_unknown_w1.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_unknown_w1.tsv) | 94 | 59 |
| [`census/names_unlock.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_unlock.tsv) | 71 | 60 |
| [`census/names_view_w3.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_view_w3.tsv) | 47 | 20 |
| [`census/names_w4a.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_w4a.tsv) | 120 | 3 |
| [`census/names_w4b.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_w4b.tsv) | 120 | 10 |
| [`census/names_w4c.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_w4c.tsv) | 2 | 0 |
| [`census/names_w4e.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_w4e.tsv) | 79 | 15 |
| [`census/names_world.tsv`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/main/census/names_world.tsv) | 44 | 40 |
