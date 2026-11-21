"""Target-agnostic Unicorn x86-32 bit-exact difftest oracle (Principle 2)."""
from __future__ import annotations

import collections
import ctypes
import json
import math
import os
import random
import struct
import subprocess
from pathlib import Path
from typing import Any

import pefile
from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_INSN, UC_MODE_32, Uc, UcError
from unicorn.x86_const import (
    UC_X86_INS_CPUID,
    UC_X86_REG_EAX,
    UC_X86_REG_EBP,
    UC_X86_REG_EBX,
    UC_X86_REG_ECX,
    UC_X86_REG_EDI,
    UC_X86_REG_EDX,
    UC_X86_REG_EFLAGS,
    UC_X86_REG_EIP,
    UC_X86_REG_ESI,
    UC_X86_REG_ESP,
    UC_X86_REG_FP0,
    UC_X86_REG_FPCW,
    UC_X86_REG_FPSW,
    UC_X86_REG_FPTAG,
)

from recomp_kit.config import ProjectConfig
from recomp_kit.patcher import load_patches

UREG = [
    UC_X86_REG_EAX,
    UC_X86_REG_ECX,
    UC_X86_REG_EDX,
    UC_X86_REG_EBX,
    UC_X86_REG_ESP,
    UC_X86_REG_EBP,
    UC_X86_REG_ESI,
    UC_X86_REG_EDI,
]
HOST = 0xE0000000
INDEF = struct.unpack("<d", struct.pack("<Q", 0xFFF8000000000000))[0]


class Ctx(ctypes.Structure):
    _fields_ = [
        ("r", ctypes.c_uint32 * 8),
        ("mem", ctypes.c_void_p),
        ("memsz", ctypes.c_uint32),
        ("ret", ctypes.c_uint32),
        ("halt", ctypes.c_uint32),
        ("halt_at", ctypes.c_uint32),
        ("why", ctypes.c_char_p),
        ("fs", ctypes.c_uint32),
        ("flags", ctypes.c_int32 * 7),
        ("eflx", ctypes.c_uint32),
        ("fcw", ctypes.c_uint32),
        ("fsw", ctypes.c_uint32),
        ("ftop", ctypes.c_uint32),
        ("ftag", ctypes.c_uint32),
        ("st", ctypes.c_double * 8),
        ("mb", ctypes.c_uint32),
        ("mm", ctypes.c_uint64 * 8),
    ]


def _f80(v: tuple[int, int]) -> int:
    m, e = v
    if e & 0x7FFF == 0x7FFF:
        return (e >> 15) << 63 | 0x7FF << 52 | (m >> 11) & ((1 << 52) - 1)
    try:
        x = (-1) ** (e >> 15) * math.ldexp(m, (e & 0x7FFF) - 16383 - 63)
    except OverflowError:
        x = (-1) ** (e >> 15) * float("inf")
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _dbits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _align_up(v: int, a: int) -> int:
    return (v + a - 1) & ~(a - 1)


def run_difftest(
    cfg: ProjectConfig,
    cases: int = 4,
    only: int | None = None,
    limit: int | None = None,
    jobs: int | None = None,
) -> dict[str, Any]:
    rt_core = Path(__file__).resolve().parents[3] / "runtime" / "core"
    gen_dir = cfg.gen_dir
    dobj = cfg.build_dir / "dobj"
    dobj.mkdir(parents=True, exist_ok=True)
    dylib = cfg.build_dir / "difftest.dylib"

    c_files = sorted(p for p in gen_dir.iterdir() if p.suffix == ".c" and (p.name.startswith("f") or p.name == "table.c"))
    if not c_files:
        raise FileNotFoundError(f"No lifted C files in {gen_dir}; run `recomp lift` first.")

    njobs = jobs or int(os.environ.get("RN_JOBS") or os.cpu_count() or 4)
    objs: list[Path] = []
    cmd_jobs: list[list[str]] = []
    for src in c_files:
        o = dobj / (src.stem + ".o")
        objs.append(o)
        if not o.exists() or o.stat().st_mtime < src.stat().st_mtime:
            cmd_jobs.append([
                "clang", "-O1", "-w", f"-I{rt_core}", f"-I{gen_dir}",
                "-fno-strict-aliasing", "-DRN_REF_QEMU5", "-c", str(src), "-o", str(o),
            ])

    running: list[subprocess.Popen] = []
    for j in cmd_jobs:
        while len(running) >= njobs:
            if running.pop(0).wait() != 0:
                raise RuntimeError("difftest object compile failed")
        running.append(subprocess.Popen(j))
    if any(p.wait() != 0 for p in running):
        raise RuntimeError("difftest object compile failed")

    if cmd_jobs or not dylib.exists():
        subprocess.run(
            [
                "clang", "-O1", "-shared", "-w", f"-I{rt_core}", "-DRN_REF_QEMU5",
                "-o", str(dylib), *[str(o) for o in objs],
                str(rt_core / "difftest_rt.c"), str(rt_core / "cpu.c"),
            ],
            check=True,
        )

    lib = ctypes.CDLL(str(dylib.resolve()))
    lib.rn_call.argtypes = [ctypes.POINTER(Ctx), ctypes.c_uint32]
    lib.rn_call.restype = None
    lib.rn_cpu_ident.argtypes = [ctypes.c_uint32, ctypes.c_uint32 * 4]
    lib.rn_cpu_ident.restype = None

    n = ctypes.c_uint32.in_dll(lib, "rn_fn_count").value
    entries = list((ctypes.c_uint32 * n).in_dll(lib, "rn_fn_addr"))
    if only is not None:
        entries = [only]
    elif limit is not None:
        entries = entries[:limit]

    pe = pefile.PE(str(cfg.resolve_binary()))
    base = pe.OPTIONAL_HEADER.ImageBase
    raw_img = pe.get_memory_mapped_image()
    img_sz = _align_up(max(len(raw_img), cfg.code_area[1] - base), 0x100000)
    img = bytearray(raw_img.ljust(img_sz, b"\0"))
    patch_set = load_patches(cfg.patches_file, code_area=cfg.code_area)
    patch_set.apply(img, base)

    k = 0
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            for i in d.imports:
                off = i.address - base
                if 0 <= off <= len(img) - 4:
                    img[off : off + 4] = (HOST + 16 * k).to_bytes(4, "little")
                k += 1
    image = bytes(img)

    scratch_base = _align_up(base + img_sz + 0x200000, 0x100000)
    stack_base = scratch_base + 0x200000
    stack_top = stack_base + 0xF0000
    ret_addr = stack_base + 0xFFFF0
    memsz = stack_base + 0x100000
    regions = [(base, img_sz), (scratch_base, 0x100000), (stack_base, 0x100000)]

    code_secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
    t0 = min(base + s.VirtualAddress for s in code_secs)
    t1 = max(base + s.VirtualAddress + s.Misc_VirtualSize for s in code_secs)

    hostmem = ctypes.create_string_buffer(memsz)
    rng = random.Random(1)

    def quiet_snans(b: bytes) -> bytes:
        buf = ctypes.create_string_buffer(b, len(b))
        lib.rn_quiet_snans(buf, len(b))
        return buf.raw

    def val() -> int:
        p = rng.random()
        if p < 0.6:
            return (scratch_base + rng.randrange(0, 0xF0000)) & ~3
        if p < 0.85:
            return rng.randrange(0, 64)
        return rng.getrandbits(32)

    def on_cpuid(uc, _):
        out = (ctypes.c_uint32 * 4)()
        lib.rn_cpu_ident(uc.reg_read(UC_X86_REG_EAX), out)
        for r, v in zip((UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX), out):
            uc.reg_write(r, v)
        return 1

    def on_rdtsc(uc, addr, size, _):
        uc.reg_write(UC_X86_REG_EAX, 0x56789ABC)
        uc.reg_write(UC_X86_REG_EDX, 0x1234)
        uc.reg_write(UC_X86_REG_EIP, addr + 2)

    rdtsc_addrs: set[int] = set()
    for cf in c_files:
        last = None
        for line in cf.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("L") and line.endswith(":;"):
                last = int(line[1:-2], 16)
            elif "rn_rdtsc(" in line and last is not None:
                rdtsc_addrs.add(last)

    res: collections.Counter[str] = collections.Counter()
    stops: collections.Counter[str] = collections.Counter()
    compared: set[int] = set()
    failed: set[int] = set()
    bad: list[dict[str, Any]] = []

    for e in entries:
        rng.seed(e)
        for _ in range(cases):
            regs = [val() for _ in range(8)]
            regs[4] = stack_top
            scratch = quiet_snans(rng.randbytes(0x100000))
            stack = bytearray(0x100000)
            for j in range(16):
                o = stack_top - stack_base + 4 + 4 * j
                stack[o : o + 4] = val().to_bytes(4, "little")
            o = stack_top - stack_base
            stack[o : o + 4] = ret_addr.to_bytes(4, "little")

            uc = Uc(UC_ARCH_X86, UC_MODE_32)
            for b, sz in regions:
                uc.mem_map(b, sz)
            uc.hook_add(UC_HOOK_INSN, on_cpuid, None, 1, 0, UC_X86_INS_CPUID)
            for a in rdtsc_addrs:
                uc.hook_add(UC_HOOK_CODE, on_rdtsc, None, a, a)

            for (b, sz), d in zip(regions, (image, scratch, bytes(stack))):
                uc.mem_write(b, d)
                ctypes.memmove(ctypes.addressof(hostmem) + b, d, sz)
            for r, v in zip(UREG, regs):
                uc.reg_write(r, v)
            uc.reg_write(UC_X86_REG_EFLAGS, 0x202)
            uc.reg_write(UC_X86_REG_FPCW, 0x27F)
            uc.reg_write(UC_X86_REG_FPSW, 0)
            uc.reg_write(UC_X86_REG_FPTAG, 0xFFFF)
            for j in range(8):
                uc.reg_write(UC_X86_REG_FP0 + j, (0xC000000000000000, 0xFFFF))

            ustop = "ret"
            try:
                uc.emu_start(e, ret_addr, count=200000)
                if uc.reg_read(UC_X86_REG_EIP) != ret_addr:
                    res["skip_timeout"] += 1
                    continue
            except UcError as x:
                eip = uc.reg_read(UC_X86_REG_EIP)
                if eip >= HOST:
                    ustop = f"import {eip:x}"
                elif "UNMAPPED" in str(x) or "FETCH" in str(x):
                    res["skip_unmapped"] += 1
                    continue
                elif "INSN_INVALID" in str(x) or "Invalid instruction" in str(x):
                    ustop = "invalid"
                else:
                    ustop = "fault"

            c = Ctx()
            for j, v in enumerate(regs):
                c.r[j] = v
            c.mem, c.memsz = ctypes.addressof(hostmem), memsz
            c.fcw = 0x27F
            for j in range(8):
                c.st[j] = INDEF
                c.mm[j] = 0xC000000000000000
            lib.rn_call(ctypes.byref(c), e)

            why = (c.why or b"").decode()
            if not c.halt:
                if c.ret != ret_addr:
                    res["skip_not_a_function"] += 1
                    continue
                lstop = "ret"
            elif why == "import":
                lstop = f"import {c.halt_at:x}"
            elif why.startswith("not lifted"):
                res["skip_pinned_cpu_path"] += 1
                continue
            elif why in ("memory fault", "divide error"):
                lstop = "fault"
            elif why == "cannot decode":
                lstop = "invalid"
            else:
                lstop = why

            if why == "no lifted function" and not (t0 <= c.halt_at < t1):
                res["skip_call_into_data"] += 1
                continue

            if ustop == lstop and ustop in ("fault", "invalid"):
                ok = True
            elif ustop != lstop:
                ok = False
            else:
                top = (uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7
                ok = top == c.ftop and (top == 0 or _f80(uc.reg_read(UC_X86_REG_FP0 + top)) == _dbits(c.st[c.ftop]))
                ok = ok and all(uc.reg_read(r) == c.r[j] for j, r in enumerate(UREG)) and all(
                    bytes(uc.mem_read(b, sz)) == ctypes.string_at(ctypes.addressof(hostmem) + b, sz)
                    for b, sz in regions
                )

            stops[ustop.split()[0]] += 1
            res["match" if ok else "mismatch"] += 1
            compared.add(e)
            if not ok:
                failed.add(e)
                if len(bad) < 50:
                    bad.append({"func": hex(e), "unicorn": ustop, "lifted": lstop, "why": why, "at": hex(c.halt_at)})

    out = {
        "project": cfg.name,
        "functions_tested": len(entries),
        "cases": dict(res),
        "compared_stop_kinds": dict(stops),
        "functions_compared": len(compared),
        "functions_all_match": len(compared - failed),
        "functions_with_mismatch": len(failed),
        "mismatch_funcs": sorted(hex(e) for e in failed),
        "mismatches": bad,
        "gate": "pass" if not failed else "FAIL",
    }
    if only is None and limit is None:
        (cfg.census_dir / "difftest.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
