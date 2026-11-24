# Public pack: what the browser downloads

> Source: `docs/re/public_pack.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 0

# Public pack: what the browser downloads

The pack `tools/build_public.py` writes to `dist/` and `tools/upload_r2.sh` sends to R2: 2.04 GB, songs and movies kept (build log 2026-11-21).

## A cold first visit to the main menu
One visit to `https://nfsu.cc/?go=1` with `tools/loadcap.mjs`, fresh profile, 2026-11-21: **32.6 MB in 108 requests**.

| Kind | Data pieces | `speed.wasm` | `pc/Speed.exe` | `game/` by Range | Page and scripts |
|---|---|---|---|---|---|
| MB | 19.0 | 11.1 | 1.3 | 1.1 | 0.2 |
| Requests | 64 | 1 | 1 | 5 | 37 |
| How it is stored | brotli pieces, one per game read (`tools/data_chunks.py`, `host/files.c:119`) | brotli q11 of 70 MB (`tools/upload_r2.sh:29`) | brotli | plain bytes, read with Range | no-cache |

The 5 `game/` Range reads are the menu music (`SNDSTREAMS/STRM_Music_*.ast`), which keeps streaming while the menu is open.

## Left out of the pack
Files `Speed.exe` never opens: `census/public_pack.tsv` rows with `opened = no`, removed by `tools/build_public.py:79`.

| Group | Files | MB | What |
|---|---|---|---|
| Game root: setup.exe, AutoRun*, SECDRV.SYS, RunGame.exe, NFSU20MEG.bin, *.TMP, readme, file lists | 17 | 22.9 | installer leftovers |
| `game/Support/`, `3DSetup/`, `AutoRun/` | 30 | 5.7 | registration, uninstall, dictionaries |

How it is served: [hosting](hosting.md).
