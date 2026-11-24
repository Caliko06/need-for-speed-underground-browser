# Changelog

Notable engineering updates for **[nfsu.cc](https://nfsu.cc/)** (Need for Speed Underground 2003 static recompilation to WebAssembly + WebGPU/WebGL 2).
Long-form technical write-ups with commit links live in the [Engineering Devlog](https://nfsu.cc/devlog/index.html) ([Atom RSS](https://nfsu.cc/feed.xml)).

## 2026-11-24

- **Reverse Engineering Atlas, Engineering Devlog & GEO**: Published all 44 `docs/re/` subsystem notes as a searchable web atlas (`/re/index.html`), launched `/devlog/index.html` with Atom feed (`/feed.xml`), added `.md` mirrors (`<link rel="alternate" type="text/markdown">`) and `/llms-full.txt` for AI search/coding agents, and added `ARCHITECTURE.md` and `CHANGELOG.md`.
- **Cloudflare RUM & Site/Repo SEO (`9776828`, `52fdc3b`)**: Enabled Cloudflare Real User Monitoring (`/cdn-cgi/rum?` verified `204`), upgraded JSON-LD `@graph` (`WebSite`, `VideoGame`, `SoftwareSourceCode`, `FAQPage`), `hreflang="x-default"` sitemap entries, and `/llms.txt`.
- **50-Minute OOM Fix & 448 MB Mobile WASM (`511830f`)**: Freed CPU-side `SmoothEnt` vertex/index buffers after GPU upload on web, reduced `speed_lite.wasm` heap from 640 MB to 448 MB (`GUEST_MEM` 256 MB), lowered desktop `blk_cap` from 256 MB to 128 MB, and freed temporary PE image buffer after import resolution.
- **Production Crash Hardening (`921e827`)**: Hardened real failure modes reported in `r2:nfsu-crash` — WebGPU `unorm8x4-bgra` fallback, `tsBuf.unmap()` race guard, `Atomics.waitAsync` fallback, fetch/WASM retries, audio degrade-to-dim, `IndexedDB` timeout, and clean `ExitProcess(0)`.

## 2026-11-23

- **Static Recompiler Speedups (`fc8ef2e`, `8444027`, `69f51fb`)**: Added liveness-based dead guest x86 flag pruning (`FlagABI`), `CHK_IMG` static image bypass, straight-line `CHK_SP` stack-pointer coalescing, and `RN_FAST_X87` for shipped builds (keeping `RN_STRICT_X87` in `tools/recomp/difftest.py`).
- **Zero-Waste WebGPU Draw Pipeline (`deb8f28`)**: Compact dynamic UBO slicing, reduced redundant state writes, and post-process `bindGroup` caching across `host/d3d9.c`, `host/gpu.c`, `host/sm1.c`, and `web/gpu.js`.

## 2026-11-22

- **Native BC1/2/3 GPU Textures (`00e474c`)**: Added `RN_S3TC` so DXT1/3/5 textures stay compressed on WebGPU (`texture-compression-bc`) and WebGL 2 (`WEBGL_compressed_texture_s3tc`), cutting texture VRAM 4x-8x and removing CPU decode stalls.
- **Adaptive Frame-Time Quality Controller (`b9c9753`, `40e6aff`, `c8e94a4`, `9545ee5`)**: Added an always-on 256-frame `Present()` ring (`web/stats.js`), closed-loop quality scaling (`web/quality.js`: res > blur > fx > fps > tier), below-the-floor notice on `ultralite`, and guaranteed full 2003 soundtrack playback at every tier.
- **Dual Brotli WASM Shipping (`e19daa6`)**: Shipped Brotli-compressed `speed_lite.wasm` alongside `speed.wasm` on Cloudflare R2.
