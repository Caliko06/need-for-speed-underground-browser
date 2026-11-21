#!/bin/sh
# Upload dist/ (tools/build_public.py) to a Cloudflare R2 bucket. Run ONLY with the OWNER's go for this upload (AGENTS.md).
# Needs: rclone (brew install rclone) with a remote named "r2" (rclone config: type s3, provider Cloudflare, the R2 API token,
# endpoint https://<account id>.r2.cloudflarestorage.com). The headers R2 cannot set per bucket (COOP/COEP/CORP, "/" -> index.html)
# are Cloudflare rules on the domain: docs/re/hosting.md.
# Usage: tools/upload_r2.sh <bucket>
set -eu
B=${1:?usage: tools/upload_r2.sh <bucket>}
cd "$(dirname "$0")/.."
test -f dist/manifest.json || { echo "no dist/: run python3 tools/build_public.py"; exit 1; }
CACHE="Cache-Control: public, max-age=86400"
IMMUTABLE="Cache-Control: public, max-age=31536000, immutable"
# Publish immutable pieces before the index/page can name them. Never remove old pieces here.
rclone copy dist/data-chunks "r2:$B/data-chunks" --ignore-times --transfers 16 --s3-no-check-bucket \
  --header-upload "$IMMUTABLE" --header-upload "Content-Encoding: br" --header-upload "Content-Type: application/octet-stream"
# Static 2003 game data: read with Range (host/files.c), so they must stay unencoded, cached immutably.
rclone copy dist/game "r2:$B/game" --transfers 16 --checksum --s3-no-check-bucket \
  --header-upload "$IMMUTABLE" --progress
# Everything else except speed.wasm, Speed.exe, and manifest.json as is. The *.gz packs are NOT Content-Encoding: the page
# unpacks them itself (web/gpu.js:230).
rclone copy dist "r2:$B" --filter "- /data-chunks/**" --filter "- /game/**" --filter "- out/speed.wasm" --filter "- pc/Speed.exe" \
  --filter "- /manifest.json" --filter "- _headers" --filter "- /*.{html,js,json,webmanifest}" --transfers 16 \
  --checksum --s3-no-check-bucket --header-upload "$CACHE" --progress
# The page and its scripts change with each fix: no-cache, so browsers and Cloudflare's edge ask again (304 when unchanged).
# Sent every time (--ignore-times, ~50 small files) so the header reaches files whose bytes did not change.
# Exclude manifest.json (657 KB, build-time audit file unused by the browser).
rclone copy dist "r2:$B" --filter "- _headers" --filter "- /manifest.json" --filter "+ /*.{html,js,json,webmanifest}" --filter "- **" \
  --ignore-times --transfers 16 --s3-no-check-bucket --header-upload "Cache-Control: no-cache"
# speed.wasm 70 MB -> 11.1 MB and pc/Speed.exe 3.18 MB: stored as brotli q11 (2026-11-21: 32 % under gzip -9's 16.3 MB), sent with
# Content-Encoding: br, the browser unpacks them (fetched whole, no Range).
# --ignore-times: a same-size re-run otherwise only updates the mod time by a server-side copy, which drops Content-Encoding (2026-11-15:
# the live page then got raw gzip and stopped: "expected magic word 00 61 73 6d, found 1f 8b").
T=$(mktemp -d)
brotli -q 11 -w 24 -c dist/out/speed.wasm > "$T/speed.wasm"
rclone copyto "$T/speed.wasm" "r2:$B/out/speed.wasm" --ignore-times --s3-no-check-bucket --header-upload "Cache-Control: no-cache" \
  --header-upload "Content-Encoding: br" --header-upload "Content-Type: application/wasm"
brotli -q 11 -w 24 -c dist/pc/Speed.exe > "$T/Speed.exe"
rclone copyto "$T/Speed.exe" "r2:$B/pc/Speed.exe" --ignore-times --s3-no-check-bucket --header-upload "$IMMUTABLE" \
  --header-upload "Content-Encoding: br" --header-upload "Content-Type: application/octet-stream"
rm -rf "$T"
echo "uploaded dist/ to r2:$B ($(python3 -c 'import json;print(round(json.load(open("dist/manifest.json"))["bytes"]/1e9,2))') GB)"
