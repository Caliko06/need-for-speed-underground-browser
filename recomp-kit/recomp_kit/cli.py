"""Unified agent-native CLI for recomp-kit (Principle 8)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from recomp_kit.arch import get_arch
from recomp_kit.config import load_project, write_project_toml
from recomp_kit.live_bus import LiveEmitter
from recomp_kit.pipeline.builder import lift_project
from recomp_kit.pipeline.compile import build_project, run_native
from recomp_kit.pipeline.imports import inspect_pe, preflight_pe
from recomp_kit.re.ledger import merge_names
from recomp_kit.re.queue import build_queue
from recomp_kit.re.tools import detect_toolchain, run_ghidra_headless, run_rea_inspect


def _cli_cmd_str() -> str:
    return "recomp " + " ".join(sys.argv[1:])


def cmd_init(args: argparse.Namespace) -> int:
    binary = Path(args.binary).resolve()
    if not binary.exists():
        sys.exit(f"Binary not found: {binary}")
    info = inspect_pe(binary)
    name = args.name or binary.stem.lower()
    out_dir = Path(args.out).resolve() if args.out else Path.cwd() / name
    toml_path = write_project_toml(
        out_dir=out_dir,
        name=name,
        binary_path=binary,
        arch=info["arch"],
        fmt=info["format"],
        code_sections=info["code_sections"],
        runtime_modules=info["recommended_modules"],
    )
    print(f"Initialized project '{name}' -> {toml_path}")
    print(f"  arch={info['arch']} format={info['format']} base={info['image_base']} entry={info['entry_point']}")
    print(f"  code_sections={info['code_sections']} imports={info['imports_total']} ({info['imports_by_dll']})")
    print(f"  recommended_modules={info['recommended_modules']}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    backend = get_arch(cfg.arch)
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    bus.emit("stage", "discover", f"CLI discover started on {cfg.resolve_binary().name}", tool="capstone")

    def on_prog(phase: str, fn_n: int, ins_n: int, q_n: int) -> None:
        bus.emit(
            "progress",
            "discover",
            f"Discover [{phase}]: {fn_n:,} funcs · {ins_n:,} insns · queue={q_n:,}",
            done=fn_n,
            total=max(fn_n + q_n, 1),
            tool="capstone",
        )

    try:
        res = backend.discover(cfg, on_progress=on_prog)
        msg = (
            f"[{cfg.name}] discovered {res['functions']['total']} functions "
            f"(entry/call={res['functions']['from_entry_and_calls']}, data={res['functions']['from_data_pointers']}), "
            f"text_coverage={res['text_coverage']*100:.1f}%, jump_tables={res['jump_tables']['count']}, "
            f"imports={res['imports']['total']}"
        )
        print(msg)
        print(f"  wrote {cfg.discovery_json} and {cfg.functions_tsv}")
        bus.emit("refresh", "discover", msg, running=False, done=res["functions"]["total"], total=res["functions"]["total"], tool="capstone")
    finally:
        bus.close()
    return 0


def cmd_lift(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    bus.emit("stage", "lift", f"CLI lift started on {cfg.name}", tool="lifter")
    def _emit_lift_prog(*a: object, **kw: object) -> None:
        if len(a) == 1 and isinstance(a[0], dict):
            p = a[0]
            done, total, addr, rate = p.get("done", 0), p.get("total", 0), p.get("addr"), p.get("rate", 0.0)
        else:
            done = int(a[0]) if len(a) > 0 else 0
            total = int(a[1]) if len(a) > 1 else 0
            addr = str(a[2]) if len(a) > 2 and a[2] else None
            rate = 0.0
        bus.emit("progress", "lift", f"Lift: {done:,}/{total:,} funcs", done=done, total=total, rate=rate, addr=addr, tool="lifter")

    try:
        rep = lift_project(cfg, cov=args.cov, jobs=args.jobs, force=args.force, on_progress=_emit_lift_prog)
        if rep.get("cached"):
            print(f"[{cfg.name}] lift cached (unchanged inputs): {rep['functions']} functions")
            bus.emit("refresh", "lift", f"Lift cached: {rep['functions']} functions", running=False, tool="lifter")
            return 0
        msg = (
            f"[{cfg.name}] lifted {rep['functions']} functions "
            f"(dropped {rep['data_seeds_inside_instructions']} false data seeds, failed {len(rep['failed'])}, "
            f"real_trap_funcs={rep['functions_with_a_real_trap']}, int3_only={rep['functions_int3_only']})"
        )
        print(msg)
        top_traps = list(rep["trap_sites_by_reason"].items())[:10]
        if top_traps:
            print("  top traps:", ", ".join(f"{k}={v}" for k, v in top_traps))
        print(f"  wrote {cfg.lift_report_json}")
        bus.emit("refresh", "lift", msg, running=False, done=rep["functions"], total=rep["functions"], tool="lifter")
    finally:
        bus.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    backend = get_arch(cfg.arch)
    only = int(args.only, 16) if args.only else None
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    bus.emit("stage", "verify", f"CLI Unicorn difftest started on {cfg.name}", tool="unicorn")
    try:
        out = backend.verify(
            cfg,
            cases=args.cases,
            only=only,
            limit=args.limit,
            jobs=args.jobs,
            on_progress=lambda p: bus.emit(
                "unicorn",
                "verify",
                f"Unicorn {p.get('addr', '')}: {'MATCH' if p.get('ok') else 'MISMATCH'} ({p.get('done', 0)}/{p.get('total', 0)})",
                done=p.get("done", 0),
                total=p.get("total", 0),
                addr=p.get("addr"),
                tool="unicorn",
            ),
        )
        msg = (
            f"[{cfg.name}] verify gate={out['gate']} compared={out['functions_compared']}/{out['functions_tested']} "
            f"all_match={out['functions_all_match']} mismatch={out['functions_with_mismatch']} "
            f"cases={out['cases']}"
        )
        print(msg)
        if out["mismatch_funcs"]:
            print("  mismatches:", out["mismatch_funcs"][:15])
        bus.emit("refresh", "verify", msg, running=False, tool="unicorn")
    finally:
        bus.close()
    return 0 if out["gate"] == "pass" else 1


def cmd_build(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    res = build_project(cfg, target=args.target, cov=not args.no_cov, jobs=args.jobs)
    print(json.dumps(res, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    res = run_native(cfg)
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


def cmd_merge_names(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    res = merge_names(cfg)
    print(json.dumps(res, indent=2))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    q = build_queue(cfg, limit=args.limit)
    s = q["summary"]
    print(
        f"[{cfg.name}] queue: lifted={s['total_lifted']} ran={s['total_ran']} named={s['total_named']} "
        f"real_traps={s['total_real_trap_funcs']} | "
        f"T1(ran+trap)={s['tier1_ran_and_trapped']} T2(ran+unnamed)={s['tier2_ran_and_unnamed']} T3(static_trap)={s['tier3_static_trapped']}"
    )
    for item in q["tier1"][:5]:
        print(f"  T1 {item['addr']} traps={item['traps']}")
    if not q["tier1"] and q["tier3"]:
        for item in q["tier3"][:10]:
            print(f"  T3 {item['addr']} traps={item['traps']}")
    return 0


def _print_preflight(pf: dict) -> None:
    info = pf["info"]
    kb = pf["size_bytes"] / 1024.0
    print(
        f"[preflight] {Path(pf['binary']).name} ({kb:.1f} KB) · {info['arch']} {info['format']} · "
        f"entry={info['entry_point']} ({pf['entry_section']}) · "
        f"APIs ready: {pf['api_ready']['implemented']}/{pf['api_ready']['total']}"
    )
    for b in pf["blockers"]:
        print(f"  BLOCKER: {b}")
    for w in pf["warnings"]:
        print(f"  note: {w}")


def cmd_preflight(args: argparse.Namespace) -> int:
    binary = Path(args.binary).expanduser().resolve()
    if not binary.exists():
        sys.exit(f"Binary not found: {binary}")
    pf = preflight_pe(binary)
    if args.json:
        print(json.dumps(pf, indent=2))
    else:
        _print_preflight(pf)
    return 0 if pf["ok"] else 2


def cmd_wasm(args: argparse.Namespace) -> int:
    """One-shot fast path: preflight -> init -> discover -> lift -> verify -> build web (.wasm)."""
    import time

    t0 = time.monotonic()
    binary = Path(args.binary).expanduser().resolve()
    if not binary.exists():
        sys.exit(f"Binary not found: {binary}")

    # 1. Fast preflight (<1s)
    pf = preflight_pe(binary)
    _print_preflight(pf)
    if not pf["ok"] and not args.allow_packed:
        print("\nStopped at preflight (avoiding wasted lift on packed/unsupported binary).")
        print("  Fix: provide an unpacked/patched x86-32 PE32 exe, or re-run with --allow-packed.")
        return 2

    # 2. Init / reuse project
    info = pf["info"]
    name = args.name or binary.stem.lower()
    kit_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out).expanduser().resolve() if args.out else (kit_root / "examples" / name)
    write_project_toml(
        out_dir=out_dir,
        name=name,
        binary_path=binary,
        arch=info["arch"],
        fmt=info["format"],
        code_sections=info["code_sections"],
        runtime_modules=info["recommended_modules"],
    )
    cfg = load_project(out_dir)
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    try:
        # 3. Discover
        bus.emit("stage", "discover", f"CLI wasm: discovering {binary.name}...", tool="capstone")
        backend = get_arch(cfg.arch)
        disc = backend.discover(
            cfg,
            on_progress=lambda phase, fn_n, ins_n, q_n: bus.emit(
                "progress",
                "discover",
                f"Discover [{phase}]: {fn_n:,} funcs · {ins_n:,} insns · queue={q_n:,}",
                done=fn_n,
                total=max(fn_n + q_n, 1),
                tool="capstone",
            ),
        )
        print(
            f"[discover] {disc['functions']['total']:,} functions "
            f"({disc['text_coverage'] * 100:.1f}% .text, {disc['jump_tables']['count']} jump tables)"
        )
        bus.emit("stage", "discover", f"Discovered {disc['functions']['total']:,} functions", done=disc["functions"]["total"], total=disc["functions"]["total"], tool="capstone")

        # 4. Lift to C99
        bus.emit("stage", "lift", f"CLI wasm: lifting {cfg.name} to C99...", tool="lifter")

        def _wasm_lift_prog(*a: object, **kw: object) -> None:
            if len(a) == 1 and isinstance(a[0], dict):
                p = a[0]
                done, total, addr = p.get("done", 0), p.get("total", 0), p.get("addr")
            else:
                done = int(a[0]) if len(a) > 0 else 0
                total = int(a[1]) if len(a) > 1 else 0
                addr = str(a[2]) if len(a) > 2 and a[2] else None
            bus.emit("progress", "lift", f"Lift: {done:,}/{total:,} funcs", done=done, total=total, addr=addr, tool="lifter")

        rep = lift_project(
            cfg,
            cov=not args.no_cov,
            jobs=args.jobs,
            force=args.force,
            on_progress=_wasm_lift_prog,
        )
        traps_n = rep.get("functions_with_a_real_trap", 0)
        print(
            f"[lift] {rep['functions']:,} C functions "
            f"({'cached' if rep.get('cached') else 'fresh'}, real_traps={traps_n})"
        )

        # 5. Verify with Unicorn (fast smoke gate unless --skip-verify)
        if not args.skip_verify:
            bus.emit("stage", "verify", f"CLI wasm: Unicorn difftest ({args.cases} cases)...", tool="unicorn")
            ver = backend.verify(cfg, cases=args.cases, limit=args.verify_limit, jobs=args.jobs)
            print(
                f"[verify] Unicorn gate={ver['gate'].upper()} "
                f"({ver['functions_all_match']}/{ver['functions_compared']} match, "
                f"{ver['functions_with_mismatch']} mismatch)"
            )
            bus.emit("unicorn", "verify", f"Unicorn gate={ver['gate'].upper()} ({ver['functions_all_match']}/{ver['functions_compared']} match)", tool="unicorn")
            if ver["gate"] != "pass":
                print(f"  Unicorn mismatches: {ver['mismatch_funcs'][:10]}")
                print("  Pass those addresses to /reverse-engineer-anything (rea MCP) before trusting WASM output.")

        # 6. Build WebAssembly (.wasm + .js)
        bus.emit("stage", "build", f"CLI wasm: compiling WebAssembly via emcc...", tool="emcc")
        bld = build_project(cfg, target="web", cov=not args.no_cov, jobs=args.jobs)
        wasm_path = Path(bld.get("wasm") or bld.get("output") or (cfg.build_dir / "web" / f"{cfg.name}.wasm")).with_suffix(".wasm")
        wasm_kb = wasm_path.stat().st_size / 1024.0 if wasm_path.exists() else 0.0
        dt = time.monotonic() - t0
        print(f"[wasm] READY in {dt:.1f}s -> {wasm_path} ({wasm_kb:.1f} KB)")
        bus.emit("refresh", "build", f"WASM READY in {dt:.1f}s -> {wasm_path.name} ({wasm_kb:.1f} KB)", running=False, tool="emcc")
    finally:
        bus.close()

    # 7. REA handoff if real traps exist
    blocked = rep.get("blocked_functions", {})
    if blocked:
        addrs = [f"0x{a}" for a in list(blocked.keys())[:15]]
        print(f"\n[rea-handoff] {len(blocked)} function(s) have translation traps.")
        print(f"  Inspect in one /reverse-engineer-anything batch: {', '.join(addrs)}")
    else:
        print("[rea-handoff] Zero translation traps. Ready to run in browser.")
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    tc = detect_toolchain()
    for k, v in tc.items():
        status = "OK" if v["installed"] else "MISSING"
        print(f"  {v['name']:12s} [{status:7s}] {v['role']:28s} {v['path']}")
    return 0


def cmd_ghidra(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    bus.emit("stage", "ghidra", f"CLI Ghidra headless started on {cfg.resolve_binary().name}", tool="ghidra")

    def on_ln(ln: str) -> None:
        print(f"[ghidra] {ln}", flush=True)
        bus.emit("fn", "ghidra", f"[Ghidra] {ln[:220]}", tool="ghidra")

    try:
        res = run_ghidra_headless(cfg, on_line=on_ln)
        bus.emit("refresh", "ghidra", f"Ghidra finished rc={res.get('rc')} (pid={res.get('pid')})", running=False, tool="ghidra")
    finally:
        bus.close()
    return 0 if res.get("ok") else 1


def cmd_rea(args: argparse.Namespace) -> int:
    cfg = load_project(args.project)
    bus = LiveEmitter(cfg.root, cfg.name, _cli_cmd_str())
    bus.emit("stage", "rea", f"CLI REA check started on {cfg.resolve_binary().name}", tool="rea")

    def on_ln(ln: str) -> None:
        print(f"[rea] {ln}", flush=True)
        bus.emit("fn", "rea", f"[REA] {ln[:220]}", tool="rea")

    try:
        res = run_rea_inspect(cfg, on_line=on_ln)
        bus.emit("refresh", "rea", f"REA finished rc={res.get('rc')} (pid={res.get('pid')})", running=False, tool="rea")
    finally:
        bus.close()
    return 0 if res.get("ok") else 1


def cmd_ui(args: argparse.Namespace) -> int:
    from recomp_kit.ui.server import serve_ui
    return serve_ui(args.project, host=args.host, port=args.port)


def cmd_mcp(args: argparse.Namespace) -> int:
    from recomp_kit.mcp.server import serve_mcp
    return serve_mcp(args.project)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recomp", description="recomp-kit: Static Binary-to-WASM Recompilation & RE Engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Inspect a binary and scaffold a project.toml")
    p_init.add_argument("binary", help="Path to target binary (.exe)")
    p_init.add_argument("--name", help="Project name (defaults to binary stem)")
    p_init.add_argument("--out", help="Output project directory")
    p_init.set_defaults(func=cmd_init)

    p_pf = sub.add_parser("preflight", help="Fast (<1s) check for DRM/packers, arch, and Win32 API readiness")
    p_pf.add_argument("binary", help="Path to target binary (.exe)")
    p_pf.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    p_pf.set_defaults(func=cmd_preflight)

    p_wasm = sub.add_parser("wasm", help="One-shot fast path: preflight -> discover -> lift -> verify -> .wasm")
    p_wasm.add_argument("binary", help="Path to target x86-32 PE32 binary (.exe)")
    p_wasm.add_argument("--name", help="Project name (defaults to binary stem)")
    p_wasm.add_argument("--out", help="Output project directory")
    p_wasm.add_argument("--jobs", type=int, default=None, help="Parallel worker jobs")
    p_wasm.add_argument("--force", action="store_true", help="Ignore lift cache")
    p_wasm.add_argument("--no-cov", action="store_true", help="Disable RN_COV instrumentation")
    p_wasm.add_argument("--skip-verify", action="store_true", help="Skip Unicorn differential check")
    p_wasm.add_argument("--cases", type=int, default=4, help="Unicorn test cases per function")
    p_wasm.add_argument("--verify-limit", type=int, default=40, help="Max functions to verify in smoke gate")
    p_wasm.add_argument("--allow-packed", action="store_true", help="Proceed even if preflight detects DRM/packers")
    p_wasm.set_defaults(func=cmd_wasm)

    p_disc = sub.add_parser("discover", help="Discover functions, basic blocks, jump tables, and imports")
    p_disc.add_argument("project", help="Path to project directory containing project.toml")
    p_disc.set_defaults(func=cmd_discover)

    p_lift = sub.add_parser("lift", help="Lift discovered functions to chunked C + lift_report.json")
    p_lift.add_argument("project", help="Path to project directory")
    p_lift.add_argument("--cov", action="store_true", help="Emit RN_COV=1 coverage instrumentation")
    p_lift.add_argument("--jobs", type=int, default=None, help="Worker processes")
    p_lift.add_argument("--force", action="store_true", help="Ignore .seal cache")
    p_lift.set_defaults(func=cmd_lift)

    p_ver = sub.add_parser("verify", help="Bit-exact differential test against Unicorn reference CPU")
    p_ver.add_argument("project", help="Path to project directory")
    p_ver.add_argument("--cases", type=int, default=4, help="Random test cases per function")
    p_ver.add_argument("--only", help="Single function hex address to verify")
    p_ver.add_argument("--limit", type=int, default=None, help="Verify only first N functions (fast smoke test)")
    p_ver.add_argument("--jobs", type=int, default=None, help="Clang compile jobs")
    p_ver.set_defaults(func=cmd_verify)

    p_bld = sub.add_parser("build", help="Compile lifted C + runtime to native binary or WebAssembly")
    p_bld.add_argument("project", help="Path to project directory")
    p_bld.add_argument("--target", choices=("native", "web"), default="native", help="Build target")
    p_bld.add_argument("--no-cov", action="store_true", help="Disable RN_COV coverage instrumentation")
    p_bld.add_argument("--jobs", type=int, default=None, help="Parallel compile jobs")
    p_bld.set_defaults(func=cmd_build)

    p_run = sub.add_parser("run", help="Run the native compiled binary and capture RN_COV coverage")
    p_run.add_argument("project", help="Path to project directory")
    p_run.set_defaults(func=cmd_run)

    p_merge = sub.add_parser("merge-names", help="Merge census/names_*.tsv with V/I/U truth-state rules")
    p_merge.add_argument("project", help="Path to project directory")
    p_merge.set_defaults(func=cmd_merge_names)

    p_q = sub.add_parser("queue", help="Generate coverage-weighted RE & trap priority queue")
    p_q.add_argument("project", help="Path to project directory")
    p_q.add_argument("--limit", type=int, default=25, help="Max items per tier")
    p_q.set_defaults(func=cmd_queue)

    p_ui = sub.add_parser("ui", help="Launch local Web Workbench UI")
    p_ui.add_argument("project", help="Path to project directory")
    p_ui.add_argument("--host", default="127.0.0.1", help="Bind address")
    p_ui.add_argument("--port", type=int, default=5190, help="HTTP port (default: 5190)")
    p_ui.set_defaults(func=cmd_ui)

    p_tools = sub.add_parser("tools", help="Show detected local RE & build toolchain (REA, Ghidra, Hopper, Emscripten)")
    p_tools.set_defaults(func=cmd_tools)

    p_gh = sub.add_parser("ghidra", help="Run real Ghidra analyzeHeadless on a project binary")
    p_gh.add_argument("project", help="Path to project directory")
    p_gh.set_defaults(func=cmd_ghidra)

    p_rea = sub.add_parser("rea", help="Run real REA (reverse-engineer-anything) CLI check/inspect")
    p_rea.add_argument("project", help="Path to project directory")
    p_rea.set_defaults(func=cmd_rea)

    p_mcp = sub.add_parser("mcp", help="Run stdio JSON-RPC 2.0 MCP server for coding agents")
    p_mcp.add_argument("project", help="Path to project directory")
    p_mcp.set_defaults(func=cmd_mcp)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
