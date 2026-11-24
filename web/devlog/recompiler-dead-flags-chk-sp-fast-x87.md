# Static Recompiler Optimizations: Dead x86 Flag Pruning, CHK_SP Coalescing, and Fast x87

- Date: 2026-11-23
- Commits: 8444027, 69f51fb, fc8ef2e
- Live game: https://nfsu.cc/
- Repository: https://github.com/Caliko06/need-for-speed-underground-browser

Naive x86-to-C static recompilation spends most of its CPU budget updating EFLAGS nobody reads and bounds-checking ESP on every push and pop. Here is how tools/recomp/lift.py eliminates both while staying verified by difftest.py.

## The cost of faithful x86 lifting

`pc/Speed.exe` (3.18 MB, 2003 PC) contains **13,764 functions** lifted ahead of time into C by `tools/recomp/lift.py` and compiled to `web/out/speed.wasm` (42.31 MB uncompressed, ~11.1 MB brotli). In early builds, every arithmetic instruction computed `CF`, `ZF`, `SF`, `OF`, and `PF`, and every stack/memory access emitted a runtime bounds check.

## 1. Liveness-based dead guest flag pruning (`8444027`)

In x86 code, the vast majority of flag writes are overwritten by the next `add`, `sub`, `xor`, or `inc` before any conditional branch (`jcc`), `cmov`, `setcc`, or `adc`/`sbb` ever reads them.

- `tools/recomp/lift.py` and `tools/recomp/abk.py` now compute intra- and inter-procedural **flag liveness** (`FlagABI` argument and live-flag masks across direct `call_to(target)` edges).
- Instructions whose flag outputs are dead emit plain C integer math (`eax = eax + ecx;`) instead of flag-computing helper calls.
- Special control-flow edges (`popfd`, indirect calls, traps, and return boundaries) conservatively preserve live flag masks so semantics never drift.

## 2. `CHK_IMG` and straight-line `CHK_SP` coalescing (`69f51fb`, `fc8ef2e`)

Guest memory safety in `host/rt.h` prevents a bug in lifted x86 from corrupting the Emscripten host heap, but checking every individual stack slot inside a function prologue/epilogue is wasteful:

- **`CHK_IMG`**: Constant addresses known to lie inside the static PE image (`0x400000+`) bypass dynamic range checks.
- **`CHK_SP` coalescing**: Within any straight-line basic block (broken at loop targets and overlap-stream entries), `lift.py` tracks `esp` deltas (`sp_acc` / `sp_move`) and emits **one coalesced stack bounds check** covering the block's min/max stack excursion instead of one check per `push`/`pop`.
- **Cold trap path (`host/rt.h`)**: Bounds-check failure paths are marked cold so Clang/LLVM keeps the hot WebAssembly loop tight.

## 3. `RN_FAST_X87` verified against `RN_STRICT_X87` (`69f51fb`)

x87 floating-point stack emulation is a classic hotspot in 2003 PC racing physics (`physics.md`, `accel.md`). `host/rt.h` now splits x87 execution into:

- **`RN_FAST_X87`** for shipped game builds (fast native IEEE-754 doubles in WASM registers).
- **`RN_STRICT_X87`** for `tools/recomp/difftest.py` trace builds, allowing single-function differential verification (`RN_ONLY=<addr> tools/recomp/difftest.py`) against reference traces whenever a compiler pass changes.
