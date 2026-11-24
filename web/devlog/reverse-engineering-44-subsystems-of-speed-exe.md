# Opening the Complete Reverse Engineering Atlas of Speed.exe (44 Subsystems)

- Date: 2026-11-24
- Commits: 9776828
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Recompiling a 2003 binary without source code requires understanding how the game actually works inside. Today we are publishing all 44 reverse-engineering system notes from docs/re/ directly on nfsu.cc/re/.

## Why publish the full binary atlas

Most retro web ports are black boxes. `RE-NFSU` was built on an evidence-first rule: every claim about `Speed.exe` (md5 `b6b9232c55376b3c38c56aac1f8a121d`, base `0x400000`, 3.18 MB) must cite the exact address or bytes read in the binary, tagged **V** (verified in code/bytes), **I** (inferred), or **U** (open).

Across the repository, that effort produced:

- **44 subsystem monographs** in [`docs/re/`](https://nfsu.cc/re/index.html): car physics, acceleration curves, tuning math, chase/speed/jump/crash cameras, rival rubber-banding and AI stuck detection, traffic pools and reactions, track splines and Road IDs, DirectX 8/9 render pipeline, motion blur, sound banks, garage/career gameflow, and asset pack formats.
- **57 symbol census tables** (`census/names_*.tsv`) naming thousands of `Speed.exe` functions across every subsystem.
- **14 surgical patch modules** (`tools/recomp/patches_*.py`), where every patch cites the exact `Speed.exe` address it modifies while leaving **Original 2003** mode untouched.

## Built for humans and AI coding/search agents

Every page in the [Reverse Engineering Atlas](https://nfsu.cc/re/index.html) and [Engineering Devlog](https://nfsu.cc/devlog/index.html) is served both as semantic HTML (`TechArticle` JSON-LD) and as a clean **`.md` sibling** (`<link rel="alternate" type="text/markdown">`), indexed in [`/llms.txt`](https://nfsu.cc/llms.txt), [`/llms-full.txt`](https://nfsu.cc/llms-full.txt), and [`/feed.xml`](https://nfsu.cc/feed.xml).

Whether you are researching static recompilation (alongside projects like N64Recomp, XenonRecomp, and NFSU2Recomp), digging into Black Box's 2003 racing physics, or querying an AI assistant about how a 2003 x86 `.exe` runs on WebGPU, you can inspect the primary evidence directly.
