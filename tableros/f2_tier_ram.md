# F2: Quick Race RAM and WASM budgets

Scope: isolated Lite linker mode and Ultra-Lite range cache. No guest patches, asset removal, song removal, automatic tier selection or publishing. Units below are MiB (1,048,576 bytes), even when existing telemetry says MB.

## Configuration and allocation boundaries (FACT)

| Allocation / setting | Default | Lite | Ultra-Lite on Lite artifact |
|---|---:|---:|---:|
| Fixed shared WASM memory, initial = maximum | 896 | 640 | 640 |
| Flat guest allocation, inside WASM | 384 | 384 | 384 |
| Guest main stack, inside guest allocation | 1 | 1 | 1 |
| Guest child stack minimum + TEB, inside guest allocation | 1 + 0.00390625 each | same | same |
| Browser runtime stack (`STACK_SIZE`) | 4 | 4 | 4 |
| Proxy main pthread stack | 4 | 4 | 4 |
| Seven guest/timer host stacks, separate from guest stacks | 28 | 14 | 14 |
| Mixer default pthread stack | 4 | 2 | 2 |
| Prefetch stack per live worker | 4 | 2 | 2 |
| Prefetch concurrency (default) | 4 | 2 | 1 |
| Range cache configured capacity | 256 | 32 | at most 16 |
| Prewarmed pthread workers | 9 | 7 | 7 |

Sources: `host/host.h:11-28`, `host/main.c:182-190`, `host/win32.c` heap_alloc/virtual_reserve/rn_mem_mb, `host/threads.c` start_fn/new_thread, `host/files.c` cap/npre/blk_new, `host/dsound.c:279-286`, `tools/recomp/build.py` compile_web. Emscripten 6.0.11 installed `system/lib/libc/crt1_proxy_main.c:45` explicitly sets the proxy main's stack from STACK_SIZE, not DEFAULT_PTHREAD_STACK_SIZE.

The pool is a prewarm count, NOT a hard concurrency limit and NOT `pool * stack` reserved bytes. Pthread stacks are allocated for actual threads. Idle JS workers have engine overhead outside linear memory. Pool growth stays enabled: shrinking it to 7 does not remove necessary guest threads. Host pthread stack totals at maximum prefetch concurrency are 52 / 24 / 22 MiB (default / Lite / Ultra-Lite), plus the separate 4 MiB browser runtime stack and per-thread TLS/allocator metadata. The 384 MiB guest allocation includes its heap, VirtualAlloc regions, image and guest stacks; never add those metrics a second time.

The independent F5 inventory arrived after implementation (`/Users/angeldamian/RE-NFSU/tableros/f5_ram_threads_inventory.md`). Its historical trace omitted timer starts; the fresh seven-thread log here supersedes that five-thread count for this title-to-race route. Its emcc struct checks identify the largest fixed arrays: Obj[65536] 7,602,176 bytes, tex_key[65536] 524,288, Handle[512] 411,648, Blk[1024] 286,720, preq[1024] 278,528, hint_text 262,144, audio arrays 163,840, GFile[256] 145,408 and VirtualAlloc region arrays 131,072. These are part of linear memory, not additional browser allocations.

The WASM global stack pointer is 14,706,800 bytes in both artifacts, consistent with 10,512,496 bytes preceding the 4 MiB runtime stack. This is a layout boundary, not an RSS measurement. Guest address HEAP_LO = 8 MiB is an address inside guest memory, not the WASM heap base.

## Thread audit

Fresh Ultra-Lite diagnostic log (`RN_RAM_AUDIT=1`) records these seven secondary guest host threads:

| Guest ID | Start/callback | Role / source |
|---|---|---|
| 0x10, 0x1c, 0x20 | 0x6749ca | CRT wrapper, run dispatch in host/threads.c |
| 0x14, 0x18 | 0x63eaa0 | WinMM timer callbacks, run_timer/timeSetEvent_ |
| 0x24 | 0x668f00 | Guest thread, run/CreateThread_ |
| 0x28 | 0x654a90 | Loader thread, reused after finishing |

Each was created once in this route. Finished threads and timers park and keep their host stacks/workers. Additional sites: proxy main (Emscripten), mixer (`host/dsound.c:286`), prefetch (`host/files.c` pre_spawn), optional memory observer (`host/main.c:240`). Native watchdog (`host/main.c:177`) is excluded from WASM. No RN_WATCH/RN_CARPOS was enabled. Thus expected concurrent assigned worker demand is 13 / 11 / 10 at maximum prefetch concurrency. Prefetch helper threads can end when their queue drains; the hint worker stays alive. These totals derive from observed guest starts plus host creation sites; a full worker lifecycle high-water trace was not recorded.

Binary corroboration limitation: REA opened `pc/Speed.exe`, SHA256 c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7, but Hopper pseudocode timed out waiting for bridge readiness. Export `/tmp/nfsu-f2/rea-evidence.json` has zero records; no REA decompilation success is claimed. Existing Hopper export `census/hopper/decomp.c:1562372` shows CreateThread wrapper target 0x6749ca. No guest behavior was changed on the basis of unverified binary claims. REA close also reported incomplete authenticated cleanup, retaining `/tmp/rea-9jiWZz`.

## Implementation

`RN_LITE_WASM=1` changes only link-time host compilation and outputs `web/out/speed_lite.js` and `speed_lite.wasm`. Generated lifted objects are reused because their compilation flags are identical. Normal output paths and normal 896/4/9 settings remain unchanged. Explicit host stacks in start_fn must also change: changing DEFAULT_PTHREAD_STACK_SIZE alone would leave guest pthreads at 4 MiB.

`RN_TIER=ultralite` selects a cache default and ceiling of 16 MiB, including in-flight pieces, and one prefetch worker. A smaller positive RN_RANGEMB is respected. The old `!old` admission exception is disabled for this tier, preventing concurrent in-flight reads from exceeding the budget. Demand reads wait with the GIL released until pieces become evictable; oversized demand reads split at the cap. LRU eviction of ready blocks remains. Default and Lite keep their existing admission behavior. Whole-file threshold is cache/8: 2 MiB in Ultra-Lite versus 4 MiB in Lite. Songs still stream normally.

`RN_RAM_AUDIT=1` logs configured cache and guest host-thread starts; it is off by default. `web/boot.js` was inspected and left to the tier integration owner: it currently downloads `out/speed.js` and hardcodes `out/speed.wasm`, and phone ENV defaults can override Lite's cache to 32 MiB/2 prefetch workers. Integration must select BOTH Lite URLs. The Ultra-Lite host ceiling wins over those phone overrides.

## Fresh measurements (2026-11-22, FACT)

Three sequential headless muted Chrome runs on this Mac, same tools/webcheck.mjs --route at 1920x1080, fresh browser/save profile per run, title -> Quick Race Olympic Square. All reached HUD at ~59 s and continued 20 s: ROUTE PASS. Screenshots were inspected: build/f2-default.png, build/f2-lite.png, build/f2-ultralite.png.

| Build | Fixed WASM | Max WASM break | Guest reserve | Remaining allocated arena | Unused linear memory | Peak whole Chrome RSS | HTTP requests |
|---|---:|---:|---:|---:|---:|---:|---:|
| default | 896 | 715 | 384 | 331 | 181 | 1746 | 326 |
| lite | 640 | 575 | 384 | 191 | 65 | 1729 | 542 |
| ultralite | 640 | 559 | 384 | 175 | 81 | 1623 | 593 |

This partitions the fixed WASM memory at the measured peak into the 384 MiB guest reserve, the remaining allocated arena and unused headroom. WASM break metrics truncate to whole MiB; these are not byte-exact malloc live totals. The remaining arena contains host statics/stacks, fetched cache pieces, Emscripten FS/PE copies, GPU command buffers, audio, allocator fragmentation and other host allocations. Their exact individual live contributions were not instrumented. The cap is a budget, not proof that all cache bytes are allocated. Guest heap at 70 s was 109 MiB default / 111 MiB Lite; virtual 7 MiB. Ultra-Lite logged heap107/virtual7 at its last allocation change. These are subsets of guest memory, not extra RAM.

Measured WASM break falls by 140 MiB (Lite) / 156 MiB (Ultra-Lite); fixed linear memory falls by 256 MiB (28.6%). Lite has 65 MiB and Ultra-Lite 81 MiB of observed headroom on this route. This validates 640 MiB for this scenario, not 576 MiB or every track/race/restart. Late-route CDP Target discovery observed 11 simultaneous worker targets in Lite (`/tmp/nfsu-f2/lite-workers.json`), matching the code-derived Lite demand. It did not cover the complete boot lifecycle or measure a universal peak.

Chrome RSS includes browser/GPU/utility/renderer processes and is not additive to WASM memory. It remains ~1.6-1.7 GiB at desktop resolution; lower fixed linear memory is not a claim that a 2 GB phone can play. Physical 2-3 GB phones, mobile GPU memory, WebGL2, all tracks/modes, long sessions, repeated race loads and stack high-water safety margins remain UNKNOWN. No audio was listened to: the authorized runs were muted, with the music stream still requested.

Logs and metrics: /tmp/nfsu-f2/{default,lite,ultralite}-{run.log,web.log,measure.json}. The local harness serves Lite WASM uncompressed and normal WASM gzipped; network WASM-byte numbers are therefore not a compression comparison. Compiled WASM sizes are 70,449,951 bytes default and 70,449,949 Lite. No RN_COV pruning occurred and no code-size saving is claimed. Direct section decoding found shared fixed memory min=max=14,336 pages default, 10,240 Lite (64 KiB pages); generated glue independently states 939,524,096 / 671,088,640 bytes. At 70 s RN_M.HEAPU8.buffer.byteLength confirmed those values for default and Lite.

Artifact SHA256: default `4d7d4045b04b9fd5e1f9a8716f5d0cec6388a45bcff4f72b57ba136bcdd20192`; Lite `d9d1687e7c1a5ca4aa7fe66fc99aed5a61f1b44132487eebf8cd903a946920b0`.

## Reproduction

```sh
RN_LITE_WASM=1 RN_JOBS=4 EM_NODE_JS=/opt/homebrew/opt/node@24/bin/node .venv/bin/python tools/recomp/build.py web
# Omit RN_LITE_WASM for normal artifacts. Links were sequential.
```

Node 26 and Node 22 on this Mac fail to load missing simdjson dylibs. Existing Node 24 works; no global configuration or packages were changed. A first Lite rerun failed because the normal server gzip handler bypassed translate_path and returned the newly built default WASM. The validation-only server now disables that handler for Lite; the initial Ultra-Lite success occurred before default output existed and served the actual Lite WASM. Production integration should request speed_lite.wasm directly, which avoids the normal-only compression route.

The transient validation server `/tmp/nfsu-f2/serve.py` reuses tools/serve.py and maps BOTH normal artifact URLs to Lite only on port 5182; 5183 serves normal artifacts. Production boot code is unchanged.

## Pruning and no-SharedArrayBuffer spike

RN_COV pruning is plausible, unimplemented: historical `census/cov/circuit.json` and `docs/re/coverage_method.md:24-44` record 5,536 entered functions in circuit and 6,067 in the 22-scenario union, against the older 13,739 census. Current build lifts 13,764. Observed coverage is only a lower bound. A safe Quick Race set needs direct-call closure, indirect dispatch and ABK targets, boot/replay/menu/pause/restart/results paths and all supported Quick Race track/mode variants. `build.py` generates rn_fn_ptr references to every retained function; coverage-driven pruning must alter generation/table membership. Code-memory savings are UNKNOWN until linked and measured. It does not reduce the guest 384 MiB reserve.

A GIL-based no-SAB spike is a separate architecture experiment, not an implemented tier. `host/threads.c` serializes guest execution, but blocking APIs preserve recursive host C stacks in wait_change/run/run_timer. One worker therefore needs suspendable continuations/fibers or a stackless recompiler. It also needs replacements for GPU mailbox futex synchronization (`host/gpu.c`, `web/gpu.js`), input atomics, AudioWorklet shared audio ring and host/files.c retry Atomics.wait. boot.js explicitly requires isolation/SAB. Test one timer + file-worker + main wait/wakeup cycle with independent stacks first, then GPU/input/audio transport. Feasibility and cost are UNKNOWN; simply removing -pthread or the GIL cannot work.

References used: installed Emscripten pthread implementation and [settings reference](https://emscripten.org/docs/tools_reference/settings_reference.html), [pthreads guide](https://emscripten.org/docs/porting/pthreads.html). We retain PROXY_TO_PTHREAD because blocking the browser main thread is unsafe, and treat pool size as prewarming rather than a cap.
