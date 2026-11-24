# One URL for Desktops and Phones: Frame-Time Quality Control and Dual WASM Builds

- Date: 2026-11-22
- Commits: 40e6aff, b9c9753, e19daa6, c8e94a4, 9545ee5
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Users open nfsu.cc on everything from M4 Macs and RTX desktops to budget Android phones. Instead of forcing manual tuning, the page measures its own frame times and adapts live.

## Always-on 256-frame present ring (`40e6aff`)

You cannot tune performance from guesswork. `host/d3d9.c` now maintains a lightweight ring buffer of the last **256 `Present()` intervals**, exposed to `web/stats.js`. Every windowed p50/p95 frame-time summary feeds both live diagnostics (`rnReport`) and crash telemetry lines so slow devices are immediately identifiable.

## Closed-loop frame-time quality controller (`b9c9753`, `c8e94a4`)

`web/quality.js` observes real measured frame times and steps down (or up) in a strict visual-preservation order:

`resolution -> motion blur -> post effects -> fps target -> quality tier`

- Measured tiers persist in `localStorage` (`rn_quality`) so repeat visits start smoothly.
- If a device stays above `p50 > 100 ms` across two windows even on `ultralite`, the UI surfaces a clean below-the-floor notice (`c8e94a4`) instead of silently freezing.
- On `ultralite`, **the full 2003 soundtrack is preserved** (`9545ee5`): cutting the music breaks the identity of Need for Speed Underground, so audio stays intact while pixels and post-FX scale.

## Shipping `speed_lite.wasm` alongside `speed.wasm` (`e19daa6`)

`tools/build_public.py` and `tools/upload_r2.sh` publish both `out/speed.wasm` (desktop) and `out/speed_lite.wasm` (phones/tablets) pre-compressed with **Brotli `-q 11 -w 24`** directly on Cloudflare R2, served with `Content-Encoding: br` and `Content-Type: application/wasm`. The browser downloads ~11 MB once and streams only the 2003 game chunks needed for the next screen.
