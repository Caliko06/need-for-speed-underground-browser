# Preserving V8 WebAssembly Code Cache, Cutting 30s Off Mobile Boot, and In-Place R2 Immutable Headers

- Date: 2026-11-25
- Commits: 653dc84
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Four production-measured browser engineering patterns that apply to any large WebAssembly app or Cloudflare R2 deployment, explained both in plain English (ELI5) and with real A/B Chrome benchmarks.

## ELI5: What changed and why it matters

If you build or ship heavy web apps (WebAssembly games, CAD tools, emulators, or AI runtimes), three invisible traps quietly slow down your users:

1. **Breaking the browser's shortcut memory (V8 WASM cache)**: Browsers like Chrome compile WebAssembly once and save the compiled machine code on disk so the next visit starts almost instantly. If your JavaScript intercepts the download stream to draw a progress bar (`new Response(new TransformStream(...))`), Chrome throws away the URL identity and **refuses to cache the compiled code**. Passing the raw `fetch()` response straight to `WebAssembly.instantiateStreaming()` restores the cache and cuts RAM spikes by 77%.
2. **Loading a 20 MB 3D menu on a phone that only wants to start**: Showing a 3D preview scene while the real app loads looks great on a desktop GPU, but on a phone it steals bandwidth, CPU, and 18 MB of JS heap before the first real frame renders. Skipping the 3D curtain on touch/low-tier devices shaved **30.5 seconds** off mobile boot time.
3. **Updating cloud cache headers without re-uploading gigabytes**: If you forgot `Cache-Control: immutable` on 1.32 GB of static assets in Cloudflare R2 or AWS S3, you do **not** have to re-upload them. A single S3 `CopyObject` request with `MetadataDirective=REPLACE` updates the header server-side in seconds with zero upload bandwidth.

---

## Technical Deep Dive: Measured Root Causes & Fixes (`653dc84`)

### 1. Restoring V8 WebAssembly Code Caching (`web/boot.js`)

Chromium's V8 engine only caches compiled WebAssembly (`WebAssembly.Module`) to HTTP cache / disk when `WebAssembly.instantiateStreaming(responsePromise, imports)` receives a genuine network `Response` backed by a cacheable URL. Wrapping `response.body` in a `TransformStream` or `ReadableStream` to count bytes creates a synthetic `Response` with `response.url === ""`, which silently disables V8 code caching and buffers extra copies in JS memory.

**Fix:** Replaced the `TransformStream` progress wrapper in `web/boot.js` with a direct `fetchWithRetry(url)` passed straight into `WebAssembly.instantiateStreaming(r, imports)`:

```js
// Reusable pattern: preserve V8 WASM code cache on repeat visits
const res = await fetchWithRetry(wasmUrl);
const { instance } = await WebAssembly.instantiateStreaming(res, imports);
```

**Measured A/B (desktop headless Chrome, `/?mute=1&go=1`):**

| Metric | Before (`TransformStream`) | After (Direct `instantiateStreaming`) | Delta |
|---|---:|---:|---:|
| JS memory at `run` (`atRunMem`) | 58.08 MiB | 13.22 MiB | **-77.2%** |
| Warm boot to `d3d9 first Present` | 715.59 ms | 674.46 ms | **-5.7%** |

### 2. Gating the 20 MB 3D Preview Curtain Off Mobile & Low-Tier (`web/index.html`)

On desktop, `launcher_b` mounts a PlayCanvas 3D street scene (`~19 MiB` of GLB/textures + WebGL context) as a visual curtain during `fast=1` boots. On coarse-pointer or low-tier devices (`RN_COARSE || RN_LOW_TIER`), that curtain competed directly with the 448 MB WASM module and asset streaming.

**Fix:** Gated the `<iframe>` mount behind `RN_Q.get('fast') === '1' && !RN_COARSE && !RN_LOW_TIER`. Desktop keeps the full 3D curtain untouched (`rnAbMs: 498 ms`, 0 JS errors).

**Measured A/B (mobile Chrome headless `844x390 dpr 2`, 4x CPU throttle, 5 Mbps / 100 ms RTT, `/?mute=1&fast=1&go=1`):**

| Metric | Before (3D Curtain Active) | After (Gated on Mobile) | Delta |
|---|---:|---:|---:|
| `launcher_b` transfer | 19.02 MiB | 0 B | **-100%** |
| Curtain block time (`RN_AB_MS`) | 1500 ms | 0 ms | **-100%** |
| `d3d9 first Present` | 107.08 s | 76.62 s | **-30.46 s (-28.4%)** |
| `atRunMem` | 70.32 MiB | 15.59 MiB | **-77.8%** |
| CDP `JSHeapUsedSize` | 22.29 MiB | 4.62 MiB | **-79.3%** |

### 3. Immutable Caching on Versioned Assets & Zero-Upload R2 Metadata Migration (`tools/upload_r2.sh`, `tools/r2_set_immutable.py`)

Previously, `*.js` and `/out/speed*.wasm` were uploaded with `no-cache`, forcing conditional `304` revalidation round-trips on every visit even though every URL already carries a content hash (`?v=RN_V`). Meanwhile, 419 static `game/*` files (1.32 GB) sat in `r2:nfsu` without `immutable`.

- **`tools/upload_r2.sh`**: Kept `no-cache` strictly on HTML/JSON/manifest entry points, and switched hashed `/*.js`, `/out/speed*.js`, and Brotli `-q 11` `/out/speed*.wasm` to `Cache-Control: public, max-age=31536000, immutable`.
- **`tools/r2_set_immutable.py`**: Wrote a zero-dependency Python stdlib AWS SigV4 script that lists `r2:nfsu/game/` and issues S3 `CopyObject` onto the same key with `x-amz-metadata-directive: REPLACE` and `Cache-Control: public, max-age=31536000, immutable`.
- **Production result**: `nfsu/game/: total=419 updated=419 skipped=0` in seconds with **0 bytes re-uploaded**.

### 4. Non-Isolated Desktop CTA & Anonymous Funnel Beacon (`web/app.js`, `tools/crash/worker.js`)

`SharedArrayBuffer` requires `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. When users open a WebAssembly app inside an in-app browser, iframe, or proxy that strips COOP/COEP, auto-reloading causes an infinite loop.

- **`web/app.js`**: When `crossOriginIsolated === false` on desktop, renders a clean direct-open + copy-link CTA instead of looping.
- **`tools/crash/worker.js` + `tools/crash/read_funnel.sh`**: Extended the Cloudflare Worker on `/crash` to accept a compact, allowlisted `rn-funnel-1` JSON event (<=1024 B, zero PII) written to a disjoint `funnel/YYYY-MM-DD/` R2 prefix so crash logs stay clean while conversion (`run` vs `stop`) and `load_ms` p50/p90 are measurable by OS and tier.
