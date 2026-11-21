"""Zero-dependency local HTTP + SSE Workbench server for recomp-kit (`recomp ui`)."""
from __future__ import annotations

import collections
import csv
import json
import mimetypes
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from recomp_kit.arch import get_arch
from recomp_kit.config import ProjectConfig, load_project, write_project_toml
from recomp_kit.pipeline.builder import lift_project
from recomp_kit.pipeline.compile import build_project, run_native
from recomp_kit.pipeline.imports import inspect_pe
from recomp_kit.re.callgraph import (
    IMPLEMENTED_APIS,
    extract_strings,
    get_binary_map,
    get_binary_meta,
    get_callgraph,
)
from recomp_kit.re.inspect import get_function_detail, tag_function
from recomp_kit.re.queue import build_queue
from recomp_kit.re.tools import detect_toolchain, run_ghidra_headless, run_rea_inspect

HTML_PATH = Path(__file__).with_name("index.html")
STATIC_DIR = Path(__file__).with_name("static")
KIT_ROOT = Path(__file__).resolve().parents[2]

DLL_ELI5 = {
    "kernel32.dll": "Core Windows OS: memory, files, threads, timers, console I/O.",
    "user32.dll": "Windows UI: windows, message boxes, keyboard/mouse events.",
    "gdi32.dll": "2D graphics: fonts, bitmaps, classic Windows drawing.",
    "advapi32.dll": "Windows Registry & security settings.",
    "d3d9.dll": "Direct3D 9: 3D GPU graphics (maps to WebGL2 / WebGPU).",
    "d3d8.dll": "Direct3D 8: 3D GPU graphics (maps to WebGL2 / WebGPU).",
    "ddraw.dll": "DirectDraw: 2D framebuffer & surfaces (maps to HTML Canvas).",
    "dsound.dll": "DirectSound: 3D/2D audio mixing (maps to WebAudio).",
    "dinput8.dll": "DirectInput 8: keyboard, mouse & gamepad (maps to Browser Input API).",
    "winmm.dll": "Windows Multimedia: high-res timers & joystick/audio helpers.",
    "ws2_32.dll": "Winsock 2: networking sockets.",
    "wsock32.dll": "Winsock 1: legacy networking sockets.",
    "shell32.dll": "Windows Shell: folders, paths, shortcuts.",
    "ole32.dll": "COM objects (DirectX / Windows component plumbing).",
    "msvcrt.dll": "C Standard Library (malloc, printf, string math).",
}


class LiveStreamHub:
    """Thread-safe SSE broadcaster and background pipeline runner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: set[queue.Queue[dict[str, Any]]] = set()
        self._history: collections.deque[dict[str, Any]] = collections.deque(maxlen=220)
        self._seq = 0
        self.running = False
        self.stage = "idle"
        self.project = ""
        self.done = 0
        self.total = 0
        self.rate = 0.0
        self.started_at = 0.0
        self.batch_queue: list[dict[str, Any]] = []
        self.cancel_event = threading.Event()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "stage": self.stage,
                "project": self.project,
                "done": self.done,
                "total": self.total,
                "rate": self.rate,
                "batch_queue": list(self.batch_queue),
                "events": list(self._history),
            }

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subs.discard(q)

    def emit(
        self,
        kind: str,
        stage: str,
        msg: str,
        addr: str | None = None,
        done: int | None = None,
        total: int | None = None,
        rate: float | None = None,
        project: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            if done is not None:
                self.done = done
            if total is not None:
                self.total = total
            if rate is not None:
                self.rate = round(rate, 1)
            if project is not None:
                self.project = project
            self.stage = stage
            ev: dict[str, Any] = {
                "id": self._seq,
                "ts": time.strftime("%H:%M:%S"),
                "kind": kind,
                "stage": stage,
                "project": self.project,
                "msg": msg,
                "running": self.running,
                "done": self.done,
                "total": self.total,
                "rate": self.rate,
            }
            if addr:
                ev["addr"] = addr
            if extra:
                ev.update(extra)
            if kind not in ("progress", "heartbeat", "ping"):
                self._history.append(ev)
            for q in self._subs:
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(ev)
                    except (queue.Empty, queue.Full):
                        pass
            return ev


def _load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _discover_projects(current: ProjectConfig) -> list[dict[str, str]]:
    seen: dict[Path, dict[str, str]] = {}
    candidates = [current.root]
    ex_dir = KIT_ROOT / "examples"
    if ex_dir.is_dir():
        for p in sorted(ex_dir.iterdir()):
            if (p / "project.toml").exists():
                candidates.append(p.resolve())
    for c in candidates:
        if c not in seen and (c / "project.toml").exists():
            try:
                pc = load_project(c)
                seen[c] = {"name": pc.name, "path": str(c), "binary": pc.resolve_binary().name}
            except Exception:
                continue
    return list(seen.values())


def _audit_imports(cfg: ProjectConfig) -> dict[str, Any]:
    disc = _load_json(cfg.discovery_json)
    by_dll: dict[str, list[dict[str, Any]]] = {}
    imp_list = disc.get("imports", {}).get("list")
    if not imp_list:
        import pefile

        pe = pefile.PE(str(cfg.resolve_binary()), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        imp_list = []
        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for e in pe.DIRECTORY_ENTRY_IMPORT:
                dll = e.dll.decode("ascii", "replace")
                for i in e.imports:
                    nm = i.name.decode("ascii", "replace") if i.name else f"ord_{i.ordinal}"
                    imp_list.append({"dll": dll, "name": nm})

    total = 0
    impl_total = 0
    for item in imp_list:
        dll = item["dll"]
        nm = item["name"]
        ok = (dll.lower(), nm) in IMPLEMENTED_APIS
        total += 1
        if ok:
            impl_total += 1
        by_dll.setdefault(dll, []).append({"name": nm, "implemented": ok})

    dlls = []
    for dll, apis in sorted(by_dll.items(), key=lambda kv: -len(kv[1])):
        done = sum(1 for a in apis if a["implemented"])
        dlls.append({
            "dll": dll,
            "eli5": DLL_ELI5.get(dll.lower(), "External Windows library."),
            "total": len(apis),
            "implemented": done,
            "apis": apis,
        })
    return {"total": total, "implemented": impl_total, "dlls": dlls}


def _list_functions(cfg: ProjectConfig, flt: str, q: str, limit: int = 200) -> dict[str, Any]:
    lift = _load_json(cfg.lift_report_json)
    blocked = lift.get("blocked_functions", {})

    ran: set[int] = set()
    cov_p = cfg.census_dir / "cov" / "union.json"
    if cov_p.exists():
        ran = {int(x, 16) for x in _load_json(cov_p).get("addrs", [])}

    names: dict[int, dict[str, str]] = {}
    names_p = cfg.census_dir / "names.tsv"
    if names_p.exists():
        with names_p.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                try:
                    names[int(r["addr"], 16)] = dict(r)
                except (ValueError, KeyError):
                    continue

    rows: list[dict[str, Any]] = []
    ql = q.strip().lower()
    if cfg.functions_tsv.exists():
        for line in cfg.functions_tsv.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split()
            a = int(parts[0], 16)
            seed = parts[1] if len(parts) > 1 else "?"
            key = f"{a:08x}"
            traps = blocked.get(key, [])
            is_ran = a in ran
            nm = names.get(a, {})
            state = nm.get("confidence", "U")
            name = nm.get("name", "")
            system = nm.get("system", "")

            if flt == "t1" and not (is_ran and traps):
                continue
            if flt == "t2" and not (is_ran and not name and not traps):
                continue
            if flt == "traps" and not traps:
                continue
            if flt == "named" and not name:
                continue
            if flt == "ran" and not is_ran:
                continue

            if ql:
                hay = f"0x{key} {name} {system} {' '.join(traps)} {seed}".lower()
                if ql not in hay:
                    continue

            rows.append({
                "addr": f"0x{key}",
                "seed": seed,
                "ran": is_ran,
                "traps": traps,
                "name": name,
                "system": system,
                "state": state,
            })
            if len(rows) >= limit:
                break
    return {"count": len(rows), "limit": limit, "items": rows}


def _ledger_counts(cfg: ProjectConfig) -> dict[str, int]:
    counts = {"V": 0, "I": 0, "U": 0, "total_named": 0}
    names_p = cfg.census_dir / "names.tsv"
    if not names_p.exists():
        return counts
    with names_p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            counts["total_named"] += 1
            st = (r.get("confidence") or "U").strip().upper()
            if st in ("V", "I", "U"):
                counts[st] += 1
            else:
                counts["U"] += 1
    return counts


def _status_payload(cfg: ProjectConfig) -> dict[str, Any]:
    disc = _load_json(cfg.discovery_json)
    lift = _load_json(cfg.lift_report_json)
    diff = _load_json(cfg.census_dir / "difftest.json")
    q = build_queue(cfg, limit=15)
    meta = get_binary_meta(cfg)
    wasm_js = cfg.build_dir / "web" / f"{cfg.name}.js"
    wasm_bin = cfg.build_dir / "web" / f"{cfg.name}.wasm"
    native_bin = cfg.build_dir / "native" / cfg.name
    disc_clean = {k: v for k, v in disc.items() if k not in ("all_mnemonics", "unresolved_jmp_sites")}
    raw_funcs = disc_clean.get("functions", 0)
    disc_clean["functions_total"] = int(raw_funcs.get("total", 0)) if isinstance(raw_funcs, dict) else int(raw_funcs or 0)
    if "text_coverage_pct" not in disc_clean and isinstance(disc_clean.get("text_coverage"), (int, float)):
        disc_clean["text_coverage_pct"] = round(float(disc_clean["text_coverage"]) * 100.0, 1)

    diff_clean = {k: v for k, v in diff.items() if k not in ("compared_funcs",)}
    diff_clean["compared"] = int(diff_clean.get("functions_compared", diff_clean.get("compared", 0)) or 0)
    diff_clean["all_match"] = int(diff_clean.get("functions_all_match", diff_clean.get("compared", 0)) or 0)
    diff_clean["tested"] = int(diff_clean.get("functions_tested", diff_clean["compared"]) or 0)

    return {
        "project": cfg.name,
        "root": str(cfg.root),
        "binary": str(cfg.resolve_binary()),
        "binary_name": cfg.resolve_binary().name,
        "binary_md5": meta["md5"],
        "binary_size": meta["size"],
        "sections": meta["sections"],
        "ledger_counts": _ledger_counts(cfg),
        "arch": cfg.arch,
        "format": cfg.fmt,
        "subsystems": cfg.subsystems,
        "runtime_modules": cfg.runtime_modules,
        "projects": _discover_projects(cfg),
        "builds": {
            "native_ready": native_bin.exists(),
            "wasm_ready": wasm_js.exists() and wasm_bin.exists(),
            "wasm_js_url": f"/wasm/{cfg.name}.js",
            "wasm_exe_url": "/wasm/target.exe",
            "wasm_bytes": wasm_bin.stat().st_size if wasm_bin.exists() else 0,
        },
        "discovery": disc_clean,
        "lift": {k: v for k, v in lift.items() if k != "blocked_functions"},
        "difftest": diff_clean,
        "queue": q,
        "toolchain": detect_toolchain(),
    }


def _create_or_load_exe(binary_path: str, name_override: str = "") -> tuple[ProjectConfig, dict[str, Any]]:
    binary = Path(binary_path).expanduser().resolve()
    if not binary.exists():
        raise FileNotFoundError(f"Binary not found: {binary}")
    info = inspect_pe(binary)
    name = name_override.strip() or binary.stem.lower()
    out_dir = KIT_ROOT / "examples" / name
    write_project_toml(
        out_dir=out_dir,
        name=name,
        binary_path=binary,
        arch=info["arch"],
        fmt=info["format"],
        code_sections=info["code_sections"],
        runtime_modules=info["recommended_modules"],
    )
    return load_project(out_dir), info


def serve_ui(project_dir: str, host: str = "127.0.0.1", port: int = 5190) -> int:
    state: dict[str, Any] = {"cfg": load_project(project_dir)}
    hub = LiveStreamHub()
    hub.project = state["cfg"].name

    def _run_stage_on(cfg: ProjectConfig, action: str, payload: dict[str, Any]) -> None:
        pname = cfg.name
        if hub.cancel_event.is_set():
            raise InterruptedError("Cancelled")

        if action == "discover":
            hub.emit("stage", "discover", f"Scanning PE .text sections of {cfg.resolve_binary().name}...", done=0, total=1, project=pname)
            t0 = time.monotonic()
            last_log = 0.0

            def on_disc_prog(phase: str, n_funcs: int, n_insns: int, q_len: int) -> None:
                nonlocal last_log
                dt = max(0.01, time.monotonic() - t0)
                rate = n_funcs / dt
                msg = f"Discover [{phase}]: {n_funcs:,} funcs · {n_insns:,} insns · queue={q_len:,} ({dt:.1f}s)"
                hub.emit("progress", "discover", msg, done=n_funcs, total=max(n_funcs + q_len, 1), rate=rate, project=pname)
                now = time.monotonic()
                if now - last_log >= 1.5:
                    last_log = now
                    hub.emit("fn", "discover", msg, done=n_funcs, total=max(n_funcs + q_len, 1), rate=rate, project=pname)

            res = get_arch(cfg.arch).discover(cfg, on_progress=on_disc_prog, cancel_event=hub.cancel_event)
            dt = max(0.01, time.monotonic() - t0)
            raw_f = res.get("functions", 0)
            n = int(raw_f.get("total", 0)) if isinstance(raw_f, dict) else int(raw_f or 0)
            cov = res.get("text_coverage_pct")
            if cov is None and isinstance(res.get("text_coverage"), (int, float)):
                cov = round(float(res["text_coverage"]) * 100.0, 1)
            cov = cov or 0
            hub.emit("stage", "discover", f"Discovered {n:,} functions ({cov}% .text) in {dt:.2f}s", done=n, total=max(1, n), rate=n / dt, project=pname)
            hub.emit("refresh", "discover", "Binary map and index updated", project=pname)

        elif action == "lift":
            force = bool(payload.get("force", False))
            hub.emit("stage", "lift", f"Lifting x86-32 functions to portable C (force={force})...", done=0, total=1, project=pname)
            t0 = time.monotonic()
            last_fn_emit = 0.0

            def on_prog(done: int, total: int, entry: int, traps_seen: int) -> None:
                nonlocal last_fn_emit
                dt = max(0.01, time.monotonic() - t0)
                rate = done / dt
                addr_s = f"0x{entry:08x}"
                hub.emit(
                    "progress",
                    "lift",
                    f"Lifting {done:,} / {total:,} ({rate:.0f} fn/s) · traps: {traps_seen}",
                    addr=addr_s,
                    done=done,
                    total=total,
                    rate=rate,
                    project=pname,
                )
                now = time.monotonic()
                if now - last_fn_emit >= 0.55 or done == total:
                    last_fn_emit = now
                    hub.emit(
                        "fn",
                        "lift",
                        f"Lifted {addr_s} ({done:,}/{total:,}, {traps_seen} traps so far)",
                        addr=addr_s,
                        done=done,
                        total=total,
                        rate=rate,
                        project=pname,
                    )

            rep = lift_project(cfg, force=force, on_progress=on_prog, cancel_event=hub.cancel_event)
            dt = max(0.01, time.monotonic() - t0)
            n = int(rep.get("functions", 0))
            traps_n = int(rep.get("functions_with_a_real_trap", 0))
            cached = bool(rep.get("cached", False))
            hub.emit(
                "stage",
                "lift",
                f"Lift complete: {n:,} C functions ({traps_n} with traps){' [cached]' if cached else f' in {dt:.2f}s'}",
                done=n,
                total=max(1, n),
                rate=n / dt,
                project=pname,
            )
            blocked = rep.get("blocked_functions", {})
            for b_addr, reasons in list(blocked.items())[:6]:
                hub.emit("trap", "lift", f"Trap in 0x{b_addr}: {', '.join(reasons)}", addr=f"0x{b_addr}", project=pname)
            hub.emit("refresh", "lift", "Lift report synced", project=pname)

        elif action == "verify":
            addr = int(str(payload["addr"]), 16) if payload.get("addr") else None
            limit = int(payload["limit"]) if payload.get("limit") else (None if addr else 40)
            cases = int(payload.get("cases", 4))
            target_lbl = f"0x{addr:08x}" if addr else f"up to {limit} functions"
            hub.emit("stage", "verify", f"Running Unicorn x86↔C differential oracle on {target_lbl} ({cases} cases/fn)...", done=0, total=limit or 1, project=pname)
            t0 = time.monotonic()
            out = get_arch(cfg.arch).verify(cfg, cases=cases, only=addr, limit=limit)
            dt = max(0.01, time.monotonic() - t0)
            comp = int(out.get("functions_compared", out.get("compared", 0)) or 0)
            all_match = int(out.get("functions_all_match", comp) or 0)
            gate = out.get("gate", "unknown")
            mism = out.get("mismatches", [])
            for f_addr in (out.get("compared_funcs") or [])[:12]:
                hub.emit("unicorn", "verify", f"Unicorn bit-exact PASS on {f_addr}", addr=str(f_addr), project=pname)
            for mm in mism[:6]:
                m_addr = mm.get("addr") if isinstance(mm, dict) else None
                hub.emit("trap", "verify", f"Unicorn mismatch: {mm}", addr=m_addr, project=pname)
            hub.emit(
                "stage",
                "verify",
                f"Unicorn oracle gate={gate.upper()}: {comp} compared, {len(mism)} mismatches ({dt:.2f}s)",
                done=comp,
                total=max(1, comp),
                rate=comp / dt,
                project=pname,
            )
            hub.emit("refresh", "verify", "Verification gate synced", project=pname)

        elif action == "build":
            target = str(payload.get("target", "web"))
            hub.emit("stage", "build", f"Compiling {target.upper()} target with RN_COV telemetry...", done=0, total=1, project=pname)
            t0 = time.monotonic()
            res = build_project(cfg, target=target, cov=True)
            dt = max(0.01, time.monotonic() - t0)
            hub.emit(
                "stage",
                "build",
                f"Build ({target}) finished in {dt:.2f}s (ok={res.get('ok', True)})",
                done=1,
                total=1,
                project=pname,
            )
            hub.emit("refresh", "build", "Build artifacts ready", project=pname)

        elif action == "run-native":
            hub.emit("stage", "native", "Running native macOS build...", done=0, total=1, project=pname)
            res = run_native(cfg)
            hub.emit(
                "stage",
                "native",
                f"Native run finished: exit={res.get('exit_code')} why={res.get('halt_why')}",
                done=1,
                total=1,
                project=pname,
                extra={"native_result": res},
            )
            hub.emit("refresh", "native", "Native run complete", project=pname)

        elif action == "ghidra":
            hub.emit("stage", "ghidra", f"Launching Ghidra analyzeHeadless on {cfg.resolve_binary().name}...", done=0, total=1, project=pname)
            t0 = time.monotonic()
            line_n = 0

            def on_gh_line(ln: str) -> None:
                nonlocal line_n
                line_n += 1
                hub.emit("fn", "ghidra", ln[:180], done=line_n, total=max(line_n + 1, 10), project=pname)

            res = run_ghidra_headless(cfg, on_line=on_gh_line, cancel_event=hub.cancel_event)
            dt = max(0.01, time.monotonic() - t0)
            hub.emit("stage", "ghidra", f"Ghidra finished in {dt:.1f}s (ok={res.get('ok')}, rc={res.get('rc')})", done=1, total=1, project=pname)
            hub.emit("refresh", "ghidra", "Ghidra analysis updated", project=pname)

        elif action == "rea":
            hub.emit("stage", "rea", f"Running REA (morluto/rea) CLI check on {cfg.resolve_binary().name}...", done=0, total=1, project=pname)
            t0 = time.monotonic()
            line_n = 0

            def on_rea_line(ln: str) -> None:
                nonlocal line_n
                line_n += 1
                hub.emit("fn", "rea", ln[:180], done=line_n, total=max(line_n + 1, 10), project=pname)

            res = run_rea_inspect(cfg, on_line=on_rea_line, cancel_event=hub.cancel_event)
            dt = max(0.01, time.monotonic() - t0)
            hub.emit("stage", "rea", f"REA CLI finished in {dt:.1f}s (ok={res.get('ok')}, rc={res.get('rc')})", done=1, total=1, project=pname)
            hub.emit("refresh", "rea", "REA toolchain checked", project=pname)

        elif action == "pipeline":
            _run_stage_on(cfg, "discover", payload)
            _run_stage_on(cfg, "lift", payload)
            _run_stage_on(cfg, "verify", {"cases": int(payload.get("cases", 4)), "limit": int(payload.get("limit", 40))})
            if payload.get("with_wasm", False):
                _run_stage_on(cfg, "build", {"target": "web"})

    def _start_worker(fn_target) -> bool:
        with hub._lock:
            if hub.running:
                return False
            hub.running = True
            hub.cancel_event.clear()
            hub.started_at = time.monotonic()
            hub.done = 0
            hub.total = 0
            hub.rate = 0.0

        def heartbeat_loop() -> None:
            beat = 0
            while True:
                time.sleep(1.0)
                with hub._lock:
                    if not hub.running:
                        return
                    elapsed = round(time.monotonic() - hub.started_at, 1)
                    st = hub.stage
                    pr = hub.project
                    dn = hub.done
                    tt = hub.total
                    rt = hub.rate
                beat += 1
                hub.emit(
                    "heartbeat",
                    st,
                    f"{st} alive · {elapsed:.0f}s · hb #{beat}",
                    done=dn,
                    total=tt,
                    rate=rt,
                    project=pr,
                    extra={"elapsed_sec": elapsed, "beat": beat},
                )

        def runner() -> None:
            threading.Thread(target=heartbeat_loop, daemon=True).start()
            try:
                fn_target()
                hub.emit("done", "idle", "Stream finished cleanly.")
            except InterruptedError:
                hub.emit("stage", "idle", "Stream stopped by user.")
            except Exception as exc:
                hub.emit("error", "error", f"Error: {exc}")
            finally:
                with hub._lock:
                    hub.running = False
                    hub.stage = "idle"
                hub.emit("refresh", "idle", "Idle")

        threading.Thread(target=runner, daemon=True).start()
        return True

    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj: Any, status: int = 200) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body_json(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            cfg: ProjectConfig = state["cfg"]
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/api/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = hub.subscribe()
                try:
                    snap = json.dumps(hub.snapshot()).encode("utf-8")
                    self.wfile.write(b"event: snapshot\ndata: " + snap + b"\n\n")
                    self.wfile.flush()
                    ping_seq = 0
                    while True:
                        try:
                            ev = q.get(timeout=3.0)
                            payload = json.dumps(ev).encode("utf-8")
                            frame = f"id: {ev['id']}\nevent: {ev['kind']}\ndata: ".encode("utf-8") + payload + b"\n\n"
                            self.wfile.write(frame)
                            self.wfile.flush()
                        except queue.Empty:
                            ping_seq += 1
                            ping_data = json.dumps({"ts": time.strftime("%H:%M:%S"), "ping": ping_seq, "running": hub.running, "stage": hub.stage}).encode("utf-8")
                            self.wfile.write(b"event: ping\ndata: " + ping_data + b"\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    hub.unsubscribe(q)
                return

            if parsed.path in ("/", "/index.html"):
                html = HTML_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return

            if parsed.path.startswith("/static/"):
                rel = parsed.path[len("/static/"):]
                if not rel or "/" in rel or "\\" in rel or ".." in rel:
                    self._json({"error": "invalid path"}, 400)
                    return
                fp = STATIC_DIR / rel
                if not fp.is_file():
                    self._json({"error": f"not found: {rel}"}, 404)
                    return
                ext_types = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".svg": "image/svg+xml",
                }
                ctype = ext_types.get(fp.suffix.lower()) or mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
                data = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if parsed.path.startswith("/wasm/"):
                rel = parsed.path[len("/wasm/"):]
                if "/" in rel or ".." in rel:
                    self._json({"error": "invalid path"}, 400)
                    return
                fp = cfg.build_dir / "web" / rel
                if not fp.exists():
                    self._json({"error": f"not built yet: {rel}"}, 404)
                    return
                ctype = (
                    "application/wasm" if fp.suffix == ".wasm"
                    else "application/javascript; charset=utf-8" if fp.suffix == ".js"
                    else mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
                )
                data = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            try:
                if parsed.path == "/api/status":
                    self._json(_status_payload(cfg))
                elif parsed.path == "/api/stream/state":
                    self._json(hub.snapshot())
                elif parsed.path == "/api/imports":
                    self._json(_audit_imports(cfg))
                elif parsed.path == "/api/functions":
                    flt = qs.get("filter", ["all"])[0]
                    q = qs.get("q", [""])[0]
                    limit = int(qs.get("limit", ["200"])[0])
                    self._json(_list_functions(cfg, flt=flt, q=q, limit=limit))
                elif parsed.path == "/api/function":
                    addr = int(qs["addr"][0], 16)
                    self._json(get_function_detail(cfg, addr))
                elif parsed.path == "/api/binary-map":
                    buckets = int(qs.get("buckets", ["180"])[0])
                    self._json(get_binary_map(cfg, buckets=buckets))
                elif parsed.path == "/api/callgraph":
                    addr = int(qs["addr"][0], 16)
                    depth = int(qs.get("depth", ["1"])[0])
                    self._json(get_callgraph(cfg, addr, depth=depth))
                elif parsed.path == "/api/strings":
                    q = qs.get("q", [""])[0]
                    limit = int(qs.get("limit", ["80"])[0])
                    self._json(extract_strings(cfg, q=q, limit=limit))
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            cfg: ProjectConfig = state["cfg"]
            parsed = urllib.parse.urlparse(self.path)
            try:
                body = self._body_json()
                if parsed.path == "/api/switch":
                    state["cfg"] = load_project(str(body["path"]))
                    hub.project = state["cfg"].name
                    self._json(_status_payload(state["cfg"]))
                elif parsed.path == "/api/new-project":
                    new_cfg, info = _create_or_load_exe(str(body["binary"]), str(body.get("name", "")))
                    state["cfg"] = new_cfg
                    hub.project = new_cfg.name
                    hub.emit("stage", "inspect", f"Loaded PE {new_cfg.resolve_binary().name} ({info['arch']} {info['format']})", project=new_cfg.name)
                    self._json({"ok": True, "info": info, "status": _status_payload(new_cfg)})
                elif parsed.path == "/api/stream/run":
                    action = str(body.get("action", "pipeline"))
                    ok = _start_worker(lambda: _run_stage_on(state["cfg"], action, body))
                    if not ok:
                        self._json({"error": "Another live stream job is already running. Stop it first."}, 409)
                        return
                    self._json({"ok": True, "action": action, "project": state["cfg"].name})
                elif parsed.path == "/api/stream/batch":
                    raw_paths = [str(p).strip() for p in (body.get("binaries") or []) if str(p).strip()]
                    if not raw_paths:
                        self._json({"error": "Provide at least one .exe path."}, 400)
                        return
                    with_wasm = bool(body.get("with_wasm", False))

                    def run_batch() -> None:
                        q_items = [{"path": p, "name": Path(p).stem, "state": "queued"} for p in raw_paths]
                        with hub._lock:
                            hub.batch_queue = q_items
                        hub.emit("stage", "batch", f"Queued {len(q_items)} executable(s) for live analysis", extra={"batch_queue": q_items})
                        for idx, item in enumerate(q_items):
                            if hub.cancel_event.is_set():
                                raise InterruptedError("Batch cancelled")
                            item["state"] = "running"
                            hub.emit("stage", "inspect", f"[{idx + 1}/{len(q_items)}] Inspecting {item['name']}...", extra={"batch_queue": list(q_items)})
                            try:
                                b_cfg, info = _create_or_load_exe(item["path"])
                                state["cfg"] = b_cfg
                                hub.project = b_cfg.name
                                hub.emit("refresh", "inspect", f"Switched active project to {b_cfg.name}", project=b_cfg.name, extra={"batch_queue": list(q_items)})
                                _run_stage_on(b_cfg, "pipeline", {"with_wasm": with_wasm, "force": False, "cases": 4, "limit": 40})
                                item["state"] = "done"
                            except InterruptedError:
                                item["state"] = "stopped"
                                raise
                            except Exception as exc:
                                item["state"] = "error"
                                hub.emit("error", "batch", f"{item['name']}: {exc}", extra={"batch_queue": list(q_items)})
                        hub.emit("stage", "batch", f"Batch complete ({len(q_items)} executable(s)).", extra={"batch_queue": list(q_items)})

                    ok = _start_worker(run_batch)
                    if not ok:
                        self._json({"error": "Another live stream job is already running."}, 409)
                        return
                    self._json({"ok": True, "count": len(raw_paths)})
                elif parsed.path == "/api/stream/stop":
                    hub.cancel_event.set()
                    self._json({"ok": True})
                elif parsed.path == "/api/stream/ingest":
                    # External CLI process pushing real-time telemetry into the live SSE stream
                    kind = str(body.get("kind", "fn"))
                    stage = str(body.get("stage", "cli"))
                    msg = str(body.get("msg", ""))
                    ext_running = bool(body.get("running", False))
                    with hub._lock:
                        if not hub.running or body.get("source") == "cli":
                            hub.running = ext_running
                    extra = {
                        k: body[k]
                        for k in ("source", "pid", "cmd", "tool")
                        if k in body and body[k] is not None
                    }
                    ev = hub.emit(
                        kind,
                        stage,
                        msg,
                        addr=body.get("addr"),
                        done=body.get("done"),
                        total=body.get("total"),
                        rate=body.get("rate"),
                        project=body.get("project") or cfg.name,
                        extra=extra,
                    )
                    self._json({"ok": True, "id": ev["id"]})
                elif parsed.path == "/api/tag":
                    addr = int(str(body["addr"]), 16)
                    res = tag_function(
                        cfg,
                        addr=addr,
                        name=str(body["name"]),
                        system=str(body["system"]),
                        state=str(body.get("state", "V")),
                        evidence=str(body.get("evidence", "")),
                        tool="ui",
                    )
                    hub.emit("stage", "ledger", f"Tagged 0x{addr:08x} as {body['name']} ({body.get('state', 'V')})", addr=f"0x{addr:08x}", project=cfg.name)
                    self._json(res)
                elif parsed.path == "/api/save-cov":
                    addrs = body.get("addrs", [])
                    cov_dir = cfg.census_dir / "cov"
                    cov_dir.mkdir(parents=True, exist_ok=True)
                    cov_file = cov_dir / "union.json"
                    existing = set(_load_json(cov_file).get("addrs", []))
                    existing.update(addrs)
                    cov_file.write_text(json.dumps({"addrs": sorted(existing)}, indent=1), encoding="utf-8")
                    self._json({"ok": True, "total_ran": len(existing)})
                elif parsed.path == "/api/action/discover":
                    res = get_arch(cfg.arch).discover(cfg)
                    self._json({"ok": True, "functions": res["functions"]})
                elif parsed.path == "/api/action/lift":
                    rep = lift_project(cfg, force=bool(body.get("force", False)))
                    self._json({"ok": True, "functions": rep["functions"], "cached": rep.get("cached", False)})
                elif parsed.path == "/api/action/verify":
                    addr = int(str(body["addr"]), 16) if body.get("addr") else None
                    limit = int(body["limit"]) if body.get("limit") else (None if addr else 60)
                    out = get_arch(cfg.arch).verify(cfg, cases=int(body.get("cases", 4)), only=addr, limit=limit)
                    self._json(out)
                elif parsed.path == "/api/action/build":
                    target = str(body.get("target", "web"))
                    res = build_project(cfg, target=target, cov=True)
                    self._json(res)
                elif parsed.path == "/api/action/run-native":
                    res = run_native(cfg)
                    self._json(res)
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"recomp-kit Workbench for '{state['cfg'].name}' running at http://{host}:{port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
