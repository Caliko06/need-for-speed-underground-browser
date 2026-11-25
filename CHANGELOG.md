# Changelog

Notable engineering updates for **[nfsu.cc](https://nfsu.cc/)** (Need for Speed Underground 2003 static recompilation to WebAssembly + WebGPU/WebGL 2).
Long-form technical write-ups with commit links live in the [Engineering Devlog](https://nfsu.cc/devlog/index.html) ([Atom RSS](https://nfsu.cc/feed.xml)).

## 2026-11-25

- **Global Reverse Engineering Hub & Expanded Corpus (`/reverse-engineering/`)**: Published the global, English-first Reverse Engineering & Static Recompilation Field Guide (`/reverse-engineering/index.html` + `.md`) with dual ELI5 + Deep Technical explanations, auto-generated Binary Symbol Census (`/reverse-engineering/symbols.html`, 59 tables / 18,293 rows) and Modular Binary Patching catalog (`/reverse-engineering/patches.html`, 15 modules / 753 hex addresses), expanded `/re/` from 44 to 49 subsystems (`flare_re`, `night_re`, `re_audio_default`, `re_minimap`, `traffic_placement`), and upgraded `/llms.txt` and `/llms-full.txt` for LLM citation.
- **V8 WASM Code Cache, Mobile Boot & In-Place R2 Immutable (`653dc84`)**: Switched `web/boot.js` to direct `fetch()` -> `WebAssembly.instantiateStreaming(r, imports)` (preserving V8 WASM code caching, desktop `atRunMem` 58.08 -> 13.22 MiB, `-77.2%`) with `fetchWithRetry()`; gated the 20 MB 3D `launcher_b` curtain off mobile/low-tier (`first Present` 107.08 -> 76.62 s, `-28.4%`, mobile JS heap `-79.3%`); added `Cache-Control: public, max-age=31536000, immutable` on versioned `.js`/`.wasm` and updated all 419 `r2:nfsu/game/*` objects in-place via `tools/r2_set_immutable.py` (`CopyObject` `MetadataDirective=REPLACE`, zero re-upload); added desktop non-isolated CTA and anonymous `rn-funnel-1` beacon (`funnel/` prefix in `nfsu-crash`).

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
