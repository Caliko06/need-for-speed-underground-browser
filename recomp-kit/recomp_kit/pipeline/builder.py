"""Target-agnostic chunked C lifter & .seal cache (Principle 7: Deterministic, Incremental Builds)."""
from __future__ import annotations

import bisect
import collections
import hashlib
import json
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Any, Callable

from recomp_kit.arch import UnsupportedInstruction, get_arch
from recomp_kit.config import ProjectConfig
from recomp_kit.patcher import PatchSet, load_patches

_WORKER_LIFTER = None
_WORKER_FUNCS: dict[int, str] = {}
_WORKER_FUNC_SET: set[int] = set()


def _worker_init(cfg: ProjectConfig, funcs: dict[int, str], patch_set: PatchSet, cov: bool) -> None:
    global _WORKER_LIFTER, _WORKER_FUNCS, _WORKER_FUNC_SET
    backend = get_arch(cfg.arch)
    _WORKER_LIFTER = backend.make_lifter(cfg, funcs, patch_set)
    _WORKER_LIFTER.cov = cov
    _WORKER_FUNCS = funcs
    _WORKER_FUNC_SET = set(funcs)


def _worker_lift(entry: int):
    try:
        src = _WORKER_LIFTER.lift(entry, _WORKER_FUNC_SET)
        cover = [(a, i.size) for a, i in _WORKER_LIFTER.body(entry)[0].items()] if _WORKER_FUNCS[entry] != "data" else []
        return entry, src, _WORKER_LIFTER.info, cover, None
    except UnsupportedInstruction as x:
        return entry, None, None, [], str(x)
    except Exception as x:
        return entry, None, None, [], f"{type(x).__name__}: {x}"


def write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def compute_seal(cfg: ProjectConfig, cov: bool) -> str:
    h = hashlib.sha256(f"arch={cfg.arch} chunks={cfg.chunks} cov={cov}".encode())
    for p in [cfg.resolve_binary(), cfg.functions_tsv, cfg.root / "project.toml", cfg.patches_file]:
        if p and p.exists():
            h.update(str(p).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def lift_project(
    cfg: ProjectConfig,
    cov: bool = False,
    jobs: int | None = None,
    force: bool = False,
    on_progress: Callable[[int, int, int, int], None] | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    if not cfg.functions_tsv.exists():
        raise FileNotFoundError(f"Missing {cfg.functions_tsv}; run `recomp discover` first.")

    gen_dir = (cfg.build_dir / "gen_cov") if cov else cfg.gen_dir
    gen_dir.mkdir(parents=True, exist_ok=True)

    sig = compute_seal(cfg, cov)
    sealf = gen_dir / ".seal"
    expected_files = ["funcs.h", "table.c"] + [f"f{k:03d}.c" for k in range(cfg.chunks)]
    if not force and sealf.exists() and sealf.read_text().strip() == sig and all((gen_dir / n).exists() for n in expected_files):
        if cfg.lift_report_json.exists():
            rep = json.loads(cfg.lift_report_json.read_text(encoding="utf-8"))
            rep["cached"] = True
            return rep

    funcs = {int(l.split()[0], 16): l.split()[1] for l in cfg.functions_tsv.read_text(encoding="utf-8").splitlines() if l.strip()}
    census_sorted = sorted(funcs)
    bounds = [census_sorted[k * len(census_sorted) // cfg.chunks] for k in range(1, cfg.chunks)] if len(census_sorted) >= cfg.chunks else []

    patch_set = load_patches(cfg.patches_file, code_area=cfg.code_area)
    funcs.update(patch_set.extra_entries())

    sorted_entries = sorted(funcs)
    total_entries = len(sorted_entries)
    njobs = jobs or int(os.environ.get("RN_JOBS") or os.cpu_count() or 4)
    res = []
    traps_seen = 0
    last_emit = 0.0
    with mp.Pool(njobs, initializer=_worker_init, initargs=(cfg, funcs, patch_set, cov)) as pool:
        if on_progress is None and cancel_event is None:
            res = pool.map(_worker_lift, sorted_entries, chunksize=64)
        else:
            for idx, item in enumerate(pool.imap(_worker_lift, sorted_entries, chunksize=32), start=1):
                if cancel_event is not None and cancel_event.is_set():
                    pool.terminate()
                    raise InterruptedError("Lift cancelled by user")
                res.append(item)
                e, _, info, _, err = item
                if err or (info and info.get("traps")):
                    traps_seen += 1
                now = time.monotonic()
                if on_progress and (idx == total_entries or idx == 1 or (now - last_emit) >= 0.14):
                    last_emit = now
                    on_progress(idx, total_entries, e, traps_seen)

    # Drop data seeds that land inside an instruction of real code
    inside: set[int] = set()
    for _, _, _, cover, _ in res:
        for a, n in cover:
            inside.update(range(a + 1, a + n))

    traps: collections.Counter[str] = collections.Counter()
    failed: dict[str, str] = {}
    blocked: dict[str, list[str]] = {}
    dropped = with_trap = real_trap = int3_only = 0
    out: list[tuple[int, str]] = []

    for e, src, info, _, err in res:
        if err:
            failed[hex(e)] = err
            continue
        if funcs[e] == "data" and e in inside:
            dropped += 1
            continue
        out.append((e, src))
        reasons = {t.split(" 0x")[0] for t in info["traps"]}
        for t in info["traps"]:
            traps[t.split(" 0x")[0]] += 1
        if reasons:
            with_trap += 1
            real = sorted(reasons - {"int3"})
            if real:
                real_trap += 1
                blocked[f"{e:08x}"] = real
            else:
                int3_only += 1

    protos = "".join(f"void f_{e:x}(Ctx *c);\n" for e, _ in out)
    if cov:
        protos += (
            "extern uint8_t rn_cov_map[];\n"
            "#define RN_COV(k) (rn_cov_map[k] = 1)\n"
            "enum {" + ",".join(f"RNI_{e:x}={k}" for k, (e, _) in enumerate(out)) + "};\n"
        )
    write_if_changed(gen_dir / "funcs.h", '#pragma once\n#include "rt.h"\n' + protos)

    n_chunks = len(bounds) + 1
    parts: list[list[str]] = [[] for _ in range(n_chunks)]
    for e, s in out:
        idx = bisect.bisect_right(bounds, e) if bounds else 0
        parts[idx].append(s)
    changed_chunks = 0
    for k, part in enumerate(parts):
        if write_if_changed(gen_dir / f"f{k:03d}.c", '#include "funcs.h"\n' + "\n".join(part)):
            changed_chunks += 1

    table_c = (
        '#include "funcs.h"\n'
        f"const uint32_t rn_fn_count = {len(out)};\n"
        "const uint32_t rn_fn_addr[] = {" + ",".join(f"0x{e:x}" for e, _ in out) + "};\n"
        "void (*const rn_fn_ptr[])(Ctx *) = {" + ",".join(f"f_{e:x}" for e, _ in out) + "};\n"
        + patch_set.c_table()
    )
    write_if_changed(gen_dir / "table.c", table_c)
    sealf.write_text(sig, encoding="utf-8")

    rep = {
        "project": cfg.name,
        "exe": str(cfg.resolve_binary()),
        "arch": cfg.arch,
        "functions": len(out),
        "data_seeds_inside_instructions": dropped,
        "patches": [f"{p.addr:#x}" for p in patch_set.active()],
        "failed": failed,
        "functions_with_a_trap": with_trap,
        "functions_with_a_real_trap": real_trap,
        "functions_int3_only": int3_only,
        "trap_sites_by_reason": dict(traps.most_common()),
        "blocked_functions": blocked,
        "chunks_written": changed_chunks,
        "cached": False,
    }
    if not cov:
        cfg.lift_report_json.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep
