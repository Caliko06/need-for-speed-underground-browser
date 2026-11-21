---
name: exe-to-wasm
description: Fast, low-friction workflow to translate a Windows x86-32 .exe into WebAssembly using recomp-kit + /reverse-engineer-anything (REA), avoiding hurdles already solved in NFSU and Max Payne.
---

# exe-to-wasm: Fast PE32 -> WASM with REA

Use this skill when the user gives you a Windows x86-32 `.exe` and wants it translated to WebAssembly fast, without rebuilding a mega-pipeline or repeating NFSU / Max Payne mistakes.

Pairs directly with `/reverse-engineer-anything` (`rea` MCP) and `~/.claude/re-ladder.md`.

## Short Path (One Command)

```bash
./recomp-kit/recomp wasm /path/to/target.exe
```

What it does automatically:
1. **Preflight (< 1 s)**: checks PE32 `x86_32`, detects DRM/packers (`.securom`, SafeDisc, UPX, high-entropy `.text`), and audits imported Win32 DLLs. Stops immediately on blockers instead of wasting time.
2. **Discover**: recursive descent + data pointers + jump tables.
3. **Lift**: translates x86-32 to chunked portable C99 with `RN_COV` instrumentation.
4. **Verify**: Unicorn bit-exact x86 <-> C differential check.
5. **Build WASM**: Emscripten `.wasm` + `.js` linked with the minimal Win32 runtime.
6. **REA Handoff**: prints exact trap addresses (`0x...`) ready for one batch call in `/reverse-engineer-anything`.

## Hurdles Already Solved (Never Repeat These)

1. **DRM / Packed retail exes (PES 2014, retail PC DVDs)**:
   - Run `recomp preflight <exe>` first to inspect section entropies (head + mid) and entry section. Only unsupported architectures (`x86_64`) are hard blockers; DRM sections like `.securom` or partial encrypted headers are warnings — readable `.text` body code can still be discovered and lifted.
2. **Never reverse-engineer dead code**:
   - Always run the compiled binary with `RN_COV=1` first (native or browser).
   - Run `recomp queue <project>` and ONLY open `T1` (ran + trapped) and `T2` (ran + unnamed) in `/reverse-engineer-anything`.
3. **One batch to REA, not 50 tiny calls**:
   - Follow `~/.claude/re-ladder.md`: pass all needed `T1`/`T2` addresses to `rea` MCP in a single batch, record names + binary evidence (`V` / `I` / `U`) in `census/names.tsv`.
4. **False data seeds mid-instruction**:
   - Already filtered automatically by `lift_project`; never manually hand-edit `functions.tsv` to chase mid-instruction pointers.
5. **Unicorn gate before trusting any lifter patch**:
   - Every time you add an x86/x87/SSE instruction or flag fix in `recomp_kit/arch/x86_32/lifter.py`, verify immediately with:
     ```bash
     ./recomp-kit/recomp verify <project> --only 0x<addr>
     ```
6. **Minimal Win32/DirectX shims**:
   - Unimplemented Win32 imports auto-stub cleanly at link time. Only implement the exact APIs hit at runtime (visible in `api_trace`), starting with `kernel32` file/memory/time, then `d3d9`/`dsound`/`dinput8`.

## Quick Reference Commands

- Fast check only: `./recomp-kit/recomp preflight /path/to/game.exe`
- Full one-shot to WASM: `./recomp-kit/recomp wasm /path/to/game.exe`
- Priority trap queue after running: `./recomp-kit/recomp queue <project_dir>`
- Verify single function after lifter fix: `./recomp-kit/recomp verify <project_dir> --only 0x401000`
- Optional browser runner/UI: `./recomp-kit/recomp ui <project_dir> --port 5195`
