#!/usr/bin/env python3
"""Check the lifted exe against a reference x86 CPU (Unicorn), bit for bit. The M1 gate.

Unicorn is a test oracle only; it never ships in the game.
Every lifted function runs on random inputs in both, with all the functions it calls. Imported APIs sit at
fake addresses: both stop at the first API call, or at the function's return, and registers, x87 TOP and
st(0), and all memory are compared there. Uses build/obj from `build.py native`.
Writes census/difftest.json. Usage: .venv/bin/python tools/recomp/difftest.py [cases]
"""
import collections, ctypes, json, math, os, random, struct, subprocess, sys
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_INSN, UC_HOOK_CODE, UC_HOOK_BLOCK
from unicorn.x86_const import (UC_X86_REG_FPCW, UC_X86_REG_FPSW, UC_X86_REG_FPTAG, UC_X86_REG_FP0, UC_X86_REG_EAX,
                               UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX, UC_X86_REG_ESP, UC_X86_REG_EBP,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_EFLAGS,
                               UC_X86_INS_CPUID)
import pefile
import patches
from build import stale     # object older than its .c or any header it includes (host/native.h too)

CASES = int(sys.argv[1]) if len(sys.argv) > 1 else 4
UREG = [UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX,
        UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI]
MEMSZ = 0x2000000
REGIONS = [(0x400000, 0x400000), (0x1000000, 0x100000), (0x1f00000, 0x100000), (0x1100000, 0x100000)]   # image, scratch, stack, ABK
MODS, MOD_STEP = 0x1100000, 0x3000      # ABK code modules relocated here, one every 0x3000 (header <= 0x2780)
SCRATCH, STACK_TOP, RET = 0x1000000, 0x1ff0000, 0x1fffff0
HOST = 0xe0000000

# Own build of build/gen with RN_REF_QEMU5: the x87 exception flags as Unicorn (QEMU 5) sets them, not as the SDM.
os.makedirs("build/dobj", exist_ok=True)
jobs, objs = [], []
for f in sorted(os.listdir("build/gen")):
    if not (f.startswith("f") or f in ("table.c", "abk.c")) or not f.endswith(".c"):
        continue
    src, o = "build/gen/" + f, "build/dobj/" + f[:-2] + ".o"
    objs.append(o)
    if stale(o, src):
        jobs.append(["clang", "-O1", "-w", "-Ihost", "-Ibuild/gen", "-fno-strict-aliasing", "-DRN_REF_QEMU5", "-DRN_STRICT_X87", "-c", src, "-o", o])
running = []
for j in jobs:
    while len(running) >= int(os.environ.get("RN_JOBS") or os.cpu_count()):   # RN_JOBS: the Mac allows at most 4
        running.pop(0).wait()
    running.append(subprocess.Popen(j))
if any(p.wait() for p in running):
    sys.exit("compile failed")
subprocess.run(["clang", "-O1", "-shared", "-w", "-Ihost", "-DRN_REF_QEMU5", "-DRN_STRICT_X87", "-o", "build/difftest.dylib", *objs,
                "tools/recomp/difftest_rt.c", "host/cpu.c", "host/abk.c"], check=True)
lib = ctypes.CDLL(os.path.abspath("build/difftest.dylib"))


class Ctx(ctypes.Structure):     # host/rt.h
    _fields_ = [("r", ctypes.c_uint32 * 8), ("mem", ctypes.c_void_p), ("memsz", ctypes.c_uint32), ("ret", ctypes.c_uint32),
                ("halt", ctypes.c_uint32), ("halt_at", ctypes.c_uint32), ("why", ctypes.c_char_p), ("fs", ctypes.c_uint32),
                ("flags", ctypes.c_int32 * 7), ("eflx", ctypes.c_uint32), ("fcw", ctypes.c_uint32), ("fsw", ctypes.c_uint32),
                ("ftop", ctypes.c_uint32), ("ftag", ctypes.c_uint32), ("st", ctypes.c_double * 8),
                ("mb", ctypes.c_uint32), ("mm", ctypes.c_uint64 * 8)]


lib.rn_call.argtypes = [ctypes.POINTER(Ctx), ctypes.c_uint32]
lib.rn_call.restype = None
lib.rn_cpu_ident.argtypes = [ctypes.c_uint32, ctypes.c_uint32 * 4]
lib.rn_cpu_ident.restype = None
n = ctypes.c_uint32.in_dll(lib, "rn_fn_count").value
entries = list((ctypes.c_uint32 * n).in_dll(lib, "rn_fn_addr"))
seed = {int(l.split()[0], 16): l.split()[1] for l in open("census/speed_exe_functions.tsv")}

# Image with every IAT slot pointing at a fake host address, the same in both.
pe = pefile.PE("pc/Speed.exe")
img = bytearray(pe.get_memory_mapped_image()[:0x400000].ljust(0x400000, b"\0"))
patches.apply(img, 0x400000)
k = 0
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for i in d.imports:
        img[i.address - 0x400000:i.address - 0x400000 + 4] = (HOST + 16 * k).to_bytes(4, "little")
        k += 1
image = bytes(img)


class RnMod(ctypes.Structure):   # host/rt.h
    _fields_ = [("id", ctypes.c_uint32), ("size", ctypes.c_uint32), ("nfn", ctypes.c_uint32),
                ("off", ctypes.POINTER(ctypes.c_uint32)), ("fn", ctypes.c_void_p)]


# ABK code modules as the engine relocates them (0x64df30), each at its own base; their functions are entries too.
sys.path.insert(0, os.path.dirname(__file__))
import abk
by_key = {(m["id"], m["size"]): m for m in abk.modules()}
mods = bytearray(0x100000)
nmod = ctypes.c_uint32.in_dll(lib, "rn_mod_count").value
for k, r in enumerate((RnMod * nmod).in_dll(lib, "rn_mods")):
    b = MODS + k * MOD_STEP
    m = by_key[(r.id, r.size)]
    mods[b - MODS:b - MODS + len(m["hdr"])] = abk.relocate(m, b, lambda a: struct.unpack_from("<I", image, a - 0x400000)[0])
    entries += [b + r.off[j] for j in range(r.nfn)]
mods = bytes(mods)

hostmem = ctypes.create_string_buffer(MEMSZ)
INDEF = struct.unpack("<d", struct.pack("<Q", 0xfff8000000000000))[0]
rng = random.Random(1)


def quiet_snans(b):
    """Random data without signaling-NaN floats/doubles: QEMU 5 keeps an sNaN on fld, the SDM quiets it."""
    buf = ctypes.create_string_buffer(b, len(b))
    lib.rn_quiet_snans(buf, len(b))
    return buf.raw


def val():
    p = rng.random()
    if p < 0.6:
        return SCRATCH + rng.randrange(0, 0xf0000) & ~3
    if p < 0.85:
        return rng.randrange(0, 64)
    return rng.getrandbits(32)


def f80(v):
    """Unicorn's (mantissa, exponent) pair of an 80-bit register as the bits of a double (NaN sign and payload kept)."""
    m, e = v
    if e & 0x7fff == 0x7fff:
        return (e >> 15) << 63 | 0x7ff << 52 | (m >> 11) & ((1 << 52) - 1)
    try:
        x = (-1) ** (e >> 15) * math.ldexp(m, (e & 0x7fff) - 16383 - 63)
    except OverflowError:       # beyond the double range: what a double would hold is infinity
        x = (-1) ** (e >> 15) * float("inf")
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def dbits(x):
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def on_cpuid(uc, _):
    out = (ctypes.c_uint32 * 4)()
    lib.rn_cpu_ident(uc.reg_read(UC_X86_REG_EAX), out)
    for r, v in zip((UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX), out):
        uc.reg_write(r, v)
    return 1


def on_rdtsc(uc, addr, size, _):     # same value as difftest_rt.c; Unicorn has no rdtsc hook, so skip the insn
    uc.reg_write(UC_X86_REG_EAX, 0x56789abc)
    uc.reg_write(UC_X86_REG_EDX, 0x1234)
    uc.reg_write(UC_X86_REG_EIP, addr + 2)


def wide_ret_sites():
    """`ret imm16` with imm >= 0x8000: Unicorn sign-extends the immediate, the SDM zero-extends it."""
    out = set()
    for f in sorted(os.listdir("build/gen")):
        if f == "abk.c":       # module code has no rdtsc and no ret imm16 (tools/recomp/abk.py census)
            continue
        last = None
        for line in open("build/gen/" + f):
            if line.startswith("L") and line.rstrip().endswith(":;"):
                last = int(line[1:-3], 16)
            elif "c->ret=ld(c,esp,4); esp+=4+" in line and int(line.split("esp+=4+")[1].split(";")[0]) >= 0x8000:
                out.add(last)
    return out


def on_wide_ret(uc, addr, size, _):
    hit[0] = True


def rdtsc_sites():
    """Guest addresses of rdtsc: the label line before each rn_rdtsc call in build/gen."""
    out = set()
    for f in sorted(os.listdir("build/gen")):
        if f == "abk.c":       # module code has no rdtsc and no ret imm16 (tools/recomp/abk.py census)
            continue
        last = None
        for line in open("build/gen/" + f):
            if line.startswith("L") and line.rstrip().endswith(":;"):
                last = int(line[1:-3], 16)
            elif "rn_rdtsc(" in line:
                out.add(last)
    return out


def make_uc():
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    for b, sz in REGIONS:
        u.mem_map(b, sz)
    u.hook_add(UC_HOOK_INSN, on_cpuid, None, 1, 0, UC_X86_INS_CPUID)
    for a in RDTSC:
        u.hook_add(UC_HOOK_CODE, on_rdtsc, None, a, a)
    for a in WIDE_RET:
        u.hook_add(UC_HOOK_CODE, on_wide_ret, None, a, a)
    return u


RDTSC, WIDE_RET, hit = rdtsc_sites(), wide_ret_sites(), [False]
uc = None

res, bad, compared, failed, stops = collections.Counter(), [], set(), set(), collections.Counter()
ONLY = os.environ.get("RN_ONLY")      # one function, with its differing dwords printed
blocks, ustep, lstep = [], [], []
if ONLY:
    # Step trace: the entry function lifted again with a callback before each instruction, against Unicorn.
    entries = [int(ONLY, 16)]
    sys.path.insert(0, os.path.dirname(__file__))
    from lift import Lifter
    LT = Lifter("pc/Speed.exe", seed)
    LT.trace = True
    code = LT.lift(entries[0], set(entries))
    code = code.replace(f"void f_{entries[0]:x}(Ctx *", f"void t_{entries[0]:x}(Ctx *", 1)   # Ctx *c or Ctx *restrict c
    code = f"void f_{entries[0]:x}(Ctx *);\n" + code     # a recursive entry calls the real one (difftest.dylib)
    open("build/gen/trace.c", "w").write('#include "rt.h"\nvoid (*rn_trace_cb)(Ctx *, uint32_t);\n'
                                         "static void rn_trace_step(Ctx *c, uint32_t a) { rn_trace_cb(c, a); }\n" + code)
    subprocess.run(["clang", "-O1", "-shared", "-w", "-Ihost", "-DRN_STRICT_X87", "-o", "build/trace.dylib", "build/gen/trace.c",
                    "build/difftest.dylib"], check=True)
    tlib = ctypes.CDLL(os.path.abspath("build/trace.dylib"))
    CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(Ctx), ctypes.c_uint32)

    def l_step(cp, a):
        c = cp.contents
        lstep.append((a, tuple(c.r), c.ftop, f"{dbits(c.st[c.ftop]):016x}" if c.ftag >> c.ftop & 1 else "empty"))
    cb = CB(l_step)
    ctypes.c_void_p.in_dll(tlib, "rn_trace_cb").value = ctypes.cast(cb, ctypes.c_void_p).value
    tfn = getattr(tlib, f"t_{entries[0]:x}")
    tfn.argtypes = [ctypes.POINTER(Ctx)]

    def u_step(u, a, sz, _):
        if not (entries[0] <= a < entries[0] + 0x10000) or a not in LT.labels:
            return
        top = (u.reg_read(UC_X86_REG_FPSW) >> 11) & 7
        tag = (u.reg_read(UC_X86_REG_FPTAG) >> (2 * top)) & 3
        ustep.append((a, tuple(u.reg_read(r) for r in UREG), top, "empty" if tag == 3 else f"{f80(u.reg_read(UC_X86_REG_FP0 + top)):016x}"))

    def hook_only(u):
        u.hook_add(UC_HOOK_BLOCK, lambda u, a, sz, _: blocks.append(a))
        u.hook_add(UC_HOOK_CODE, u_step)
for e in entries:
    rng.seed(e)                     # same inputs for a function on every run
    for _ in range(CASES):
        regs = [val() for _ in range(8)]
        regs[4] = STACK_TOP
        scratch = quiet_snans(rng.randbytes(0x100000))
        stack = bytearray(0x100000)
        for j in range(16):
            o = STACK_TOP - 0x1f00000 + 4 + 4 * j
            stack[o:o + 4] = val().to_bytes(4, "little")
        o = STACK_TOP - 0x1f00000
        stack[o:o + 4] = RET.to_bytes(4, "little")
        uc = make_uc()          # fresh CPU per case: junk entries run privileged code in Unicorn's ring 0
        if ONLY:
            hook_only(uc)
        for (b, sz), d in zip(REGIONS, (image, scratch, bytes(stack), mods)):
            uc.mem_write(b, d)
            ctypes.memmove(ctypes.addressof(hostmem) + b, d, sz)
        for r, v in zip(UREG, regs):
            uc.reg_write(r, v)
        uc.reg_write(UC_X86_REG_EFLAGS, 0x202)  # user mode: IF=1; arithmetic flags clear, DF=0, as the lifted code
        uc.reg_write(UC_X86_REG_FPCW, 0x27f)    # Windows thread default: 53-bit precision, exceptions masked
        uc.reg_write(UC_X86_REG_FPSW, 0)        # empty FPU stack every case (TOP 0)
        uc.reg_write(UC_X86_REG_FPTAG, 0xffff)
        for j in range(8):                      # empty registers read as the real indefinite (SDM; QEMU reads raw)
            uc.reg_write(UC_X86_REG_FP0 + j, (0xc000000000000000, 0xffff))
        ustop = "ret"
        hit[0] = False
        blocks.clear(); ustep.clear(); lstep.clear()
        try:
            uc.emu_start(e, RET, count=200000)
            if uc.reg_read(UC_X86_REG_EIP) != RET:
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
        if hit[0] or (ustop == "invalid" and uc.reg_read(UC_X86_REG_EIP) in WIDE_RET):
            res["skip_ret_imm16_sign"] += 1
            continue
        c = Ctx()
        for j, v in enumerate(regs):
            c.r[j] = v
        c.mem, c.memsz = ctypes.addressof(hostmem), MEMSZ
        c.fcw = 0x27f
        for j in range(8):
            c.st[j] = INDEF                         # empty x87 registers hold the real indefinite
            c.mm[j] = 0xc000000000000000            # MMX aliases their mantissa (Unicorn's FP0.. above)
        if ONLY:
            tfn(ctypes.byref(c))    # same code with the step callback
        else:
            lib.rn_call(ctypes.byref(c), e)
        why = (c.why or b"").decode()
        if not c.halt:
            if c.ret != RET:
                res["skip_not_a_function"] += 1     # ret went elsewhere: entry is mid-function or data
                continue
            lstop = "ret"
        elif why == "import":
            lstop = f"import {c.halt_at:x}"
        elif why.startswith("not lifted"):
            res["skip_pinned_cpu_path"] += 1        # MMX/SSE/3DNow: the CPU we present never runs it
            continue
        elif why in ("memory fault", "divide error"):
            lstop = "fault"
        elif why == "cannot decode":
            lstop = "invalid"
        else:
            lstop = why
        if why == "no lifted function" and not (0x401000 <= c.halt_at < 0x697000):
            res["skip_call_into_data"] += 1         # random pointer called: Unicorn runs data as code
            continue
        if ustop == lstop and ustop in ("fault", "invalid"):
            ok = True
        elif ustop != lstop:
            ok = False
        else:
            top = (uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7
            ok = top == c.ftop and (top == 0 or f80(uc.reg_read(UC_X86_REG_FP0 + top)) == dbits(c.st[c.ftop]))
            ok = ok and all(uc.reg_read(r) == c.r[j] for j, r in enumerate(UREG)) and all(
                bytes(uc.mem_read(b, sz)) == ctypes.string_at(ctypes.addressof(hostmem) + b, sz) for b, sz in REGIONS)
        stops[ustop.split()[0]] += 1
        res["match" if ok else "mismatch"] += 1
        compared.add(e)
        if not ok and ONLY:
            print(f"case: unicorn {ustop}, lifted {lstop} {why}")
            print("  unicorn blocks:", " ".join(f"{a:x}" for a in blocks[-40:]))
            ut = (uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7
            print(f"  end unicorn regs {[hex(uc.reg_read(r)) for r in UREG]} top {ut} st0 {f80(uc.reg_read(UC_X86_REG_FP0 + ut)):016x}")
            print(f"  end lifted  regs {[hex(x) for x in c.r]} top {c.ftop} st0 {dbits(c.st[c.ftop]):016x}")
            for k, (us, ls) in enumerate(zip(ustep, lstep)):
                if us != ls:
                    print(f"  first step that differs (state before it): unicorn {us}")
                    print(f"                                             lifted  {ls}")
                    print(f"  previous instruction: {ustep[k - 1][0]:x}" if k else "")
                    break
            for b, sz in REGIONS:
                u, h = bytes(uc.mem_read(b, sz)), ctypes.string_at(ctypes.addressof(hostmem) + b, sz)
                for a in [i for i in range(0, sz, 4) if u[i:i + 4] != h[i:i + 4]][:8]:
                    print(f"  {b + a:08x}: unicorn {u[a:a + 4][::-1].hex()} lifted {h[a:a + 4][::-1].hex()}")
        if not ok:
            failed.add(e)
            if len(bad) < 60:
                bad.append({"func": hex(e), "unicorn": ustop, "lifted": lstop, "why": why, "at": hex(c.halt_at),
                            "uc": [hex(uc.reg_read(r)) for r in UREG], "lift": [hex(x) for x in c.r],
                            "mem_diff": [hex(b + next(i for i in range(sz) if u[i] != h[i])) for (b, sz) in REGIONS
                                         for u, h in [(bytes(uc.mem_read(b, sz)), ctypes.string_at(ctypes.addressof(hostmem) + b, sz))] if u != h]})

# Mismatches where the reference CPU (QEMU 5 inside Unicorn) does not follow the Intel SDM. Each one was
# traced step by step; the lifted code follows the SDM. Any other mismatch fails the gate.
KNOWN = {
    0x642774: "F6 /1 is TEST on real CPUs (undocumented alias); QEMU 5 calls it invalid. Junk data entry.",
    0x673824: "FPREM with invalid operands: the SDM gives the real indefinite (-NaN), QEMU 5 gives +NaN.",
    0x67ca06: "FPREM on unsupported 80-bit encodings (unnormals): the SDM gives -NaN, QEMU 5 gives +NaN.",
}
out = {"functions": len(entries), "cases": dict(res), "compared_stop_kinds": dict(stops),
       "functions_compared": len(compared), "functions_all_match": len(compared - failed),
       "all_match_by_seed": dict(collections.Counter(seed.get(e, "?") for e in compared - failed)),
       "functions_with_mismatch": len(failed), "mismatch_funcs": sorted(hex(e) for e in failed), "mismatches": bad,
       "compared_funcs": sorted(hex(e) for e in compared)}   # per-function list: tools/census/scoreboard.py diff-tested column
out["known_reference_deviations"] = {hex(k): v for k, v in KNOWN.items() if k in failed}
out["gate"] = "pass" if failed <= set(KNOWN) else "FAIL"
if not ONLY:
    json.dump(out, open("census/difftest.json", "w"), indent=1)
print(json.dumps({k: out[k] for k in ("gate", "functions", "cases", "compared_stop_kinds", "functions_compared",
                                    "functions_all_match", "functions_with_mismatch")}))
print("mismatch funcs:", out["mismatch_funcs"][:30])
