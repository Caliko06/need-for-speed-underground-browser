#!/bin/sh
# Create the private bucket (once) and deploy the crash Worker. Run ONLY with the OWNER's go (AGENTS.md: no upload without it).
set -e
cd "$(dirname "$0")"
set -a; . ~/.config/cloudflare/credentials.env; set +a
npx --yes wrangler@4 r2 bucket create nfsu-crash 2>&1 | grep -v 'already exists' || true
npx --yes wrangler@4 deploy
