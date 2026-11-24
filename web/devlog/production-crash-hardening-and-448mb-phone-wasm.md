# Hunting a 50-Minute Browser OOM and Shrinking Mobile WASM to 448 MB

- Date: 2026-11-24
- Commits: 511830f, 921e827
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Shipping a statically recompiled 2003 PC game to thousands of real browsers surfaces failure modes that desktop tests never hit. Here is what production telemetry caught and how two surgical patches fixed both long-session OOMs and low-RAM phone crashes.

## What real browsers broke in production

Once `nfsu.cc` went live, every unhandled browser crash reported a small JSON payload to our Cloudflare R2 crash bucket (`r2:nfsu-crash`). Auditing real user sessions revealed two distinct classes of failure:

1. **Memory exhaustion on phones and long desktop sessions**: `speed_lite.wasm` previously requested a 640 MB initial heap, which caused iOS Safari and 4 GB Android devices to fail WebAssembly instantiation (`could not allocate memory`), while long 50-minute desktop sessions slowly accumulated CPU-side geometry memory.
2. **Browser API edge cases**: GPUs without `unorm8x4-bgra` vertex format support, browsers missing `Atomics.waitAsync`, `tsBuf.unmap()` races on timestamp queries, transient network drops during chunk/WASM fetches, and `IndexedDB` hangs on save boot.

## Cutting the 50-minute OOM and dropping `speed_lite.wasm` to 448 MB (`511830f`)

Three concrete changes eliminated the memory pressure without touching original 2003 gameplay or audio:

- **Freeing CPU-side `SmoothEnt` buffers after GPU upload (`host/d3d9.c`)**: On web builds, once smoothed vertex and index buffers are uploaded to WebGPU/WebGL 2, keeping the host-side CPU shadow copy around caused linear memory growth across races. Freeing them immediately after upload stopped the 50-minute OOM.
- **Lowering `speed_lite.wasm` heap from 640 MB to 448 MB (`tools/recomp/build.py`, `host/host.h`)**: `GUEST_MEM` on the lite build was tightened to 256 MB and total WASM memory to 448 MB, letting budget Android phones and iPhones allocate the module cleanly.
- **Tightening transient host allocations (`host/files.c`, `host/main.c`)**: Desktop block cache cap (`blk_cap`) was reduced from 256 MB to 128 MB, and the temporary PE image buffer (`pe`) is now freed immediately after Win32 import resolution completes.

## Hardening the WebGPU, audio, and network host (`921e827`)

- **WebGPU `unorm8x4-bgra` software fallback (`web/gpu.js`)**: Devices that reject `unorm8x4-bgra` vertex attributes now fall back cleanly instead of throwing during pipeline creation.
- **Guarded timestamp query unmap (`web/gpu.js`)**: Prevented invalid-state throws when `tsBuf.unmap()` raced with device teardown.
- **`Atomics.waitAsync` fallback (`web/boot.js`)**: Older browser engines without `Atomics.waitAsync` no longer abort worker startup.
- **Network retries and clean shutdown (`web/boot.js`, `host/files.c`)**: Fetch and WASM download paths retry transient failures, `IndexedDB` open calls have bounded timeouts (`web/saves.js`), audio degrades gracefully instead of crashing when autoplay/context fails (`web/audio.js`), and `ExitProcess(0)` closes cleanly.

## Takeaway for browser static recompilation

Emulators usually cap memory tightly up front; static recompilations inherit the original PC executable's allocation assumptions plus a host GPU translation layer. Pairing a lightweight crash beacon with strict CPU-shadow freeing after GPU upload is what makes a 2003 Windows binary survive real mobile browsers.
