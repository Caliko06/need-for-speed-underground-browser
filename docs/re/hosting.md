# Hosting: Cloudflare R2 behind nfsu.cc
Nothing below runs without the OWNER's go for that upload.
| Step | Who | What |
|---|---|---|
| 1 Account + domain | OWNER | Cloudflare account; buy the domain (Cloudflare Registrar sells at cost) so its DNS is already on Cloudflare |
| 2 Bucket | OWNER or us with his token | R2 bucket, e.g. `nfsu`; Settings > Custom Domains > `play.<domain>` (a test address first, row 6) |
| 3 Token | OWNER | R2 > Manage API tokens > Object Read & Write on that bucket; `rclone config` remote `r2` (provider Cloudflare) |
| 4 Upload | us, after his go | `python3 tools/build_public.py && tools/upload_r2.sh nfsu` (~1.95 GB, speed.wasm sent gzipped 70 -> ~16 MB) |
| 5 Rules on the zone | us or OWNER | below |
| 6 Check | us | `crossOriginIsolated` true, WORLD reached from the domain, Range answers 206 on game/Tracks/STREAML1RA.BUN |
## Zone rules (dashboard > Rules)
| Rule | Match | Action | Why |
|---|---|---|---|
| Response header transform | hostname eq play.<domain> | set `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, `Cross-Origin-Resource-Policy: same-origin` | SharedArrayBuffer (game threads); same three as tools/static_server.py and dist/_headers |
| URL rewrite | path eq `/` | rewrite to `/index.html` | R2 serves no index page |
| Cache rule | hostname eq play.<domain> | eligible for cache, edge TTL 1 day | fewer R2 reads (Class B: 10 M/month free, then $0.36/M; a WORLD visit ~2,900 requests, docs/re/public_pack.md) |
## Cost (third-party guides, 2026; confirm on Cloudflare's page)
Storage $0.015/GB-month, 10 GB free; egress free; so ~2 GB fits the free tier. Unknown until live: Range through the cache, Safari/iOS.
| Redirect rule (live 2026-11-15) | host eq www.nfsu.cc | 301 to concat("https://nfsu.cc", path), query kept | www gave 525 |
