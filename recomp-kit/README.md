# recomp-kit

Reusable static binary-to-C-to-WebAssembly recompilation and reverse-engineering toolkit, extracted from `RE-NFSU`.

Read [`PRINCIPLES.md`](PRINCIPLES.md) for the architectural invariants.

## Quickstart

```sh
# 1. Initialize a target project from any PE32 x86 binary
.venv/bin/python recomp-kit/recomp init pc/ug2/SPEED2.EXE --out recomp-kit/examples/ug2

# 2. Discover functions, basic blocks, jump tables, and imports
.venv/bin/python recomp-kit/recomp discover recomp-kit/examples/ug2

# 3. Lift all functions to chunked C + emit lift_report.json
.venv/bin/python recomp-kit/recomp lift recomp-kit/examples/ug2

# 4. Inspect coverage-prioritized RE queue / trap hotspots
.venv/bin/python recomp-kit/recomp queue recomp-kit/examples/ug2

# 5. Run bit-exact Unicorn differential verification
.venv/bin/python recomp-kit/recomp verify recomp-kit/examples/ug2 --limit 100 --cases 2

# 6. Open the local Web Workbench UI (default http://127.0.0.1:5190)
.venv/bin/python recomp-kit/recomp ui recomp-kit/examples/ug2 --port 5190

# 7. Or expose the project to any coding agent via stdio MCP
.venv/bin/python recomp-kit/recomp mcp recomp-kit/examples/ug2
```

## Layout

| Path | Responsibility |
|---|---|
| `recomp_kit/config.py` | Declarative `project.toml` schema & loader |
| `recomp_kit/patcher.py` | Byte-verified binary patch engine + C loader table |
| `recomp_kit/arch/` | Pluggable `ArchBackend` interface (`x86_32` included) |
| `recomp_kit/pipeline/` | Chunked C builder, `.seal` cache, IAT auditor |
| `recomp_kit/re/` | `V/I/U` truth ledger, name merger, priority queue |
