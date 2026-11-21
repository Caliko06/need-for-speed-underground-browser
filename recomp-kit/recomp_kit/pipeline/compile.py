"""Native (clang) & WebAssembly (emcc) compiler + runner for recomp-kit (Phase 1)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from recomp_kit.config import ProjectConfig
from recomp_kit.pipeline.builder import lift_project

RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
CORE_DIR = RUNTIME_DIR / "core"
WIN32_DIR = RUNTIME_DIR / "win32"


def _compile_one(cmd: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("EM_FROZEN_CACHE", "1")
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return p.returncode, (p.stderr or p.stdout).strip()


def build_project(
    cfg: ProjectConfig,
    target: str = "native",
    cov: bool = True,
    jobs: int | None = None,
) -> dict[str, Any]:
    """Compile lifted C + minimal runtime to either a native binary or a WebAssembly module."""
    t0 = time.time()
    if target not in ("native", "web"):
        raise ValueError(f"Unsupported target '{target}' (expected 'native' or 'web')")

    # Ensure lifted C exists (with RN_COV if requested)
    lift_project(cfg, cov=cov, jobs=jobs, force=False)
    gen_dir = (cfg.build_dir / "gen_cov") if cov else cfg.gen_dir

    cc = shutil.which("emcc") if target == "web" else shutil.which("clang")
    if not cc:
        raise RuntimeError(f"Compiler not found for target={target} ({'emcc' if target == 'web' else 'clang'})")

    out_dir = cfg.build_dir / target
    obj_dir = out_dir / "obj"
    obj_dir.mkdir(parents=True, exist_ok=True)

    c_sources: list[Path] = [
        CORE_DIR / "cpu.c",
        CORE_DIR / "dispatch.c",
        CORE_DIR / "main.c",
        WIN32_DIR / "win32_min.c",
        gen_dir / "table.c",
    ]
    c_sources.extend(sorted(gen_dir.glob("f*.c")))

    common_flags = [
        "-O1",
        f"-I{CORE_DIR}",
        f"-I{gen_dir}",
        "-Wno-unused-label",
        "-Wno-unused-variable",
        "-Wno-unused-but-set-variable",
        "-Wno-tautological-compare",
    ]

    # Compile changed .c -> .o in parallel
    tasks: list[tuple[Path, Path, list[str]]] = []
    objs: list[Path] = []
    for src in c_sources:
        tag = "rt_" if src.parent in (CORE_DIR, WIN32_DIR) else "gen_"
        obj = obj_dir / f"{tag}{src.stem}.o"
        objs.append(obj)
        if not obj.exists() or obj.stat().st_mtime < src.stat().st_mtime:
            tasks.append((src, obj, [cc, "-c", *common_flags, str(src), "-o", str(obj)]))

    njobs = jobs or int(os.environ.get("RN_JOBS") or 4)
    if tasks:
        with ThreadPoolExecutor(max_workers=njobs) as ex:
            results = list(ex.map(lambda t: _compile_one(t[2]), tasks))
        for (src, _, _), (rc, err) in zip(tasks, results):
            if rc != 0:
                raise RuntimeError(f"Compile failed for {src.name}:\n{err[:1500]}")

    if target == "native":
        out_bin = out_dir / cfg.name
        link_cmd = [cc, "-O1", *[str(o) for o in objs], "-lm", "-o", str(out_bin)]
        rc, err = _compile_one(link_cmd)
        if rc != 0:
            raise RuntimeError(f"Native link failed:\n{err[:1500]}")
        return {
            "ok": True,
            "target": "native",
            "cov": cov,
            "output": str(out_bin),
            "compiled_objects": len(tasks),
            "total_objects": len(objs),
            "elapsed_sec": round(time.time() - t0, 2),
        }

    # WebAssembly build via emcc
    out_js = out_dir / f"{cfg.name}.js"
    out_wasm = out_dir / f"{cfg.name}.wasm"
    link_cmd = [
        cc,
        "-O1",
        *[str(o) for o in objs],
        "-lm",
        "-sMODULARIZE=1",
        "-sEXPORT_NAME=RecompModule",
        "-sEXPORTED_FUNCTIONS=_rn_wasm_run,_malloc,_free",
        "-sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8",
        "-sINITIAL_MEMORY=134217728",
        "-sALLOW_MEMORY_GROWTH=1",
        "-sSTACK_SIZE=2097152",
        "-sENVIRONMENT=web",
        "-o",
        str(out_js),
    ]
    rc, err = _compile_one(link_cmd)
    if rc != 0:
        raise RuntimeError(f"WASM link failed:\n{err[:1500]}")

    # Copy target .exe alongside WASM so the browser runner can fetch it
    exe_dst = out_dir / "target.exe"
    shutil.copy2(cfg.resolve_binary(), exe_dst)

    return {
        "ok": True,
        "target": "web",
        "cov": cov,
        "js": str(out_js),
        "wasm": str(out_wasm),
        "wasm_bytes": out_wasm.stat().st_size if out_wasm.exists() else 0,
        "exe": str(exe_dst),
        "compiled_objects": len(tasks),
        "total_objects": len(objs),
        "elapsed_sec": round(time.time() - t0, 2),
    }


def run_native(cfg: ProjectConfig) -> dict[str, Any]:
    """Execute the built native binary, persist RN_COV coverage, and return the JSON run report."""
    out_bin = cfg.build_dir / "native" / cfg.name
    if not out_bin.exists():
        build_project(cfg, target="native", cov=True)
    cov_dir = cfg.census_dir / "cov"
    cov_dir.mkdir(parents=True, exist_ok=True)
    cov_out = cov_dir / "union.json"
    p = subprocess.run(
        [str(out_bin), str(cfg.resolve_binary()), "--json", "--cov-out", str(cov_out)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    raw = (p.stdout or "").strip()
    if not raw:
        return {"ok": False, "error": p.stderr.strip() or f"exit={p.returncode}"}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": raw[:500]}
