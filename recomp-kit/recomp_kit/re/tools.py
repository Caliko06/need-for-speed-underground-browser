"""Real external RE & compilation toolchain detector and live CLI runners (REA, Ghidra, Hopper, Emscripten)."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from recomp_kit.config import ProjectConfig

KIT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = KIT_ROOT.parent


def _find_first(candidates: list[str | Path]) -> str | None:
    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def detect_toolchain() -> dict[str, dict[str, Any]]:
    """Probe real installed tools on this machine (no mocks)."""
    ghidra_bin = (
        os.environ.get("GHIDRA_HEADLESS")
        or shutil.which("analyzeHeadless")
        or _find_first([
            REPO_ROOT / "ref/ps2/ghidra/install/support/analyzeHeadless",
            "/opt/homebrew/bin/analyzeHeadless",
            "/Applications/ghidra/support/analyzeHeadless",
        ])
    )
    hopper_bin = (
        os.environ.get("HOPPER_LAUNCHER_PATH")
        or shutil.which("hopper")
        or _find_first([
            Path.home() / "Applications/Hopper Disassembler.app/Contents/MacOS/hopper",
            "/Applications/Hopper Disassembler.app/Contents/MacOS/hopper",
        ])
    )
    rea_repo = Path.home() / "rea"
    rea_script = rea_repo / "scripts" / "rea.mjs"
    rea_bin = str(rea_script) if rea_script.is_file() else shutil.which("rea")
    emcc_bin = shutil.which("emcc") or _find_first(["/opt/homebrew/bin/emcc"])
    node_bin = _find_first(["/opt/homebrew/bin/node", Path.home() / ".local/bin/node"]) or shutil.which("node")

    has_capstone = False
    has_unicorn = False
    try:
        import capstone  # noqa: F401
        has_capstone = True
    except Exception:
        pass
    try:
        import unicorn  # noqa: F401
        has_unicorn = True
    except Exception:
        pass

    return {
        "capstone": {"name": "Capstone", "installed": has_capstone, "path": "python:capstone", "role": "x86-32 disassembler"},
        "lifter": {"name": "Lifter", "installed": True, "path": "recomp_kit/arch/x86_32/lifter.py", "role": "x86-32 -> C99"},
        "unicorn": {"name": "Unicorn", "installed": has_unicorn, "path": "python:unicorn", "role": "Bit-exact x86 oracle"},
        "emcc": {"name": "Emscripten", "installed": bool(emcc_bin), "path": emcc_bin or "", "role": "C99 -> WebAssembly"},
        "rea": {"name": "REA", "installed": bool(rea_bin), "path": rea_bin or "", "role": "morluto/rea CLI & MCP", "node": node_bin or ""},
        "ghidra": {"name": "Ghidra", "installed": bool(ghidra_bin), "path": ghidra_bin or "", "role": "Headless decompiler"},
        "hopper": {"name": "Hopper", "installed": bool(hopper_bin), "path": hopper_bin or "", "role": "Interactive/CLI disassembler"},
    }


def _stream_subprocess(
    cmd: list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    on_line: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: int = 600,
) -> dict[str, Any]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=cwd,
    )
    if on_line:
        on_line(f"[pid={proc.pid}] $ {' '.join(cmd)}")
    lines: list[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                raise InterruptedError("Tool cancelled by user")
            ln = raw.rstrip("\r\n")
            if ln:
                lines.append(ln)
                if len(lines) > 400:
                    lines.pop(0)
                if on_line:
                    on_line(ln)
        rc = proc.wait(timeout=timeout_sec)
        return {"ok": rc == 0, "rc": rc, "pid": proc.pid, "cmd": cmd, "tail": lines[-25:]}
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"ok": False, "rc": -1, "pid": proc.pid, "cmd": cmd, "error": f"Timed out after {timeout_sec}s", "tail": lines[-25:]}
    except InterruptedError:
        try:
            proc.kill()
        except Exception:
            pass
        raise


def run_ghidra_headless(
    cfg: ProjectConfig,
    on_line: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run real Ghidra analyzeHeadless on the project's binary, streaming stdout live."""
    tc = detect_toolchain()
    ghidra = tc["ghidra"]["path"]
    if not ghidra:
        raise RuntimeError("Ghidra analyzeHeadless not found on this machine.")

    proj_dir = cfg.census_dir / "ghidra_proj"
    proj_dir.mkdir(parents=True, exist_ok=True)
    binary = cfg.resolve_binary()

    cmd = [
        ghidra,
        str(proj_dir),
        f"{cfg.name}_ghidra",
        "-import",
        str(binary),
        "-overwrite",
        "-analysisTimeoutPerFile",
        "180",
    ]
    return _stream_subprocess(cmd, on_line=on_line, cancel_event=cancel_event, timeout_sec=300)


def run_rea_inspect(
    cfg: ProjectConfig,
    on_line: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run real REA (reverse-engineer-anything) CLI check/inspect on the target binary."""
    tc = detect_toolchain()
    rea_path = tc["rea"]["path"]
    node_bin = tc["rea"].get("node") or shutil.which("node") or "node"
    hopper_path = tc["hopper"]["path"]

    env = dict(os.environ)
    if hopper_path:
        env["HOPPER_LAUNCHER_PATH"] = hopper_path

    # Prefer local /Users/angeldamian/rea repo if Node supports it, otherwise fall back to npx rea-agents@6.7.0
    if rea_path and rea_path.endswith(".mjs"):
        probe = subprocess.run([node_bin, rea_path, "--version"], capture_output=True, text=True, env=env)
        if probe.returncode == 0:
            cmd = [node_bin, rea_path, "doctor"]
        else:
            cmd = ["npx", "-y", "rea-agents@6.7.0", "doctor"]
    else:
        cmd = ["npx", "-y", "rea-agents@6.7.0", "doctor"]

    return _stream_subprocess(cmd, env=env, on_line=on_line, cancel_event=cancel_event, timeout_sec=120)
