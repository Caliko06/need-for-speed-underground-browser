# System Design Principles (`recomp-kit`)

These 8 principles govern every module in `recomp-kit`. They are distilled from what actually succeeded in bringing `Speed.exe` (13,764 functions) to WebAssembly and proving the same lifter on `SPEED2.EXE` (23,522 functions).

## 1. Zero Guessing / Fail-Loud Execution
- Unknown instructions emit `TRAP(at, reason)` and halt with exact address and opcode.
- Unimplemented OS/API imports halt with `missing API dll!name (ret addr)`.
- Binary patches verify `old` bytes before writing `new`; a mismatch aborts the build.
- Never silently skip, approximate, or swallow unknown behavior.

## 2. Oracle-First Verification
- Every ISA backend ships with an independent reference CPU oracle (Unicorn).
- Differential testing (`recomp verify --only <addr>`) compares lifted C against the reference CPU bit-for-bit (registers, flags, FPU, dirty memory).
- The oracle never ships in the final binary; it is a build-time proof gate.

## 3. Strict Engine vs. Target Separation
- The engine core never imports or hardcodes target binary paths, image bases, patch caves, subsystem lists, or app-specific host hooks.
- Every target is defined declaratively by `project.toml`, optional `patches/`, optional `census/`, and optional `host_ext/`.
- Adding a new `.exe` must require **zero edits** to `recomp_kit/`.

## 4. Coverage-Driven Reverse Engineering
- Do not reverse-engineer dead code.
- Live execution coverage (`RN_COV=1` entry bitmap) defines the working set of functions that actually matter.
- Work queues prioritize functions that are both **reached** (`ran=true`) and **blocked/unnamed**.

## 5. Truth-State Ledger (`V / I / U`)
- Every symbol and subsystem tag carries an explicit evidence state:
  - **`V` (Verified):** read directly in the binary and cross-checked with two tools.
  - **`I` (Inferred):** propagated via call graph, string heuristic, or address neighborhood.
  - **`U` (Unknown):** unproven; nothing is built on it.
- Authority order: **Verified Name (`V`) > Manual Override > Automated Propagation (`I`)**.
- Clashes never delete information: `V` wins primary, alternatives stay in `aliases`.

## 6. Pluggable Boundaries
- **ISA (`ArchBackend`):** `discover()`, `lift()`, `oracle()` behind one interface (`x86_32` first; `x86_64`, `mips`, `ppc` later).
- **Binary Format:** PE32 first; PE64, ELF32/64, raw blobs pluggable.
- **RE Exporters:** Ghidra headless (`cp -c` parallel pool) + REA MCP as universal defaults; Hopper as optional macOS bulk accelerator.
- **Runtime SDK:** Modular C/JS libraries (`core`, `win32`, `d3d9`, `dsound`, `dinput8`, future `gdi`/`ddraw`/`d3d8`) linked only when imported by the target.

## 7. Deterministic, Incremental Builds
- Lifted C is partitioned by guest address into stable chunks (`f000.c`..`fNNN.c`).
- `write_if_changed` + content-hashed `.seal` caching ensures a single patch or cave only recompiles the affected chunk(s).

## 8. Agent-Native CLI + Structured Artifacts
- Every CLI command prints a concise human summary AND writes machine-readable JSON/TSV (`discovery.json`, `functions.tsv`, `lift_report.json`, `difftest.json`, `queue.json`, `scoreboard.json`) so coding agents can inspect, verify, and iterate autonomously.
