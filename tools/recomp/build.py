#!/usr/bin/env python3
"""Lift every function of pc/Speed.exe to C in build/gen, then compile.

build/gen/fNNN.c   lifted functions, in chunks
build/gen/funcs.h  prototypes
build/gen/table.c  sorted guest address -> function table for rn_call
census/lift_report.json  counts: functions, traps by reason
Usage: .venv/bin/python tools/recomp/build.py [native|web|lift]   (default: native)
"""
import bisect, collections, glob, hashlib, json, multiprocessing as mp, os, re, struct, subprocess, sys
import pefile
sys.path.insert(0, os.path.dirname(__file__))
from lift import Lifter, Unsupported
import abk, patches

CHUNKS = 160
# RN_COV=1: a coverage build (docs/re/coverage_method.md). Every lifted function stores one byte at its ENTRY, so direct
# calls count. It lives apart (build/gen_cov, build/obj_cov, build/speed_cov): the normal build and its files are untouched.
COV = os.environ.get("RN_COV") == "1"
GEN = "build/gen_cov" if COV else "build/gen"
FUNCS = {int(l.split()[0], 16): l.split()[1] for l in open("census/speed_exe_functions.tsv")}
# A function's chunk comes from its address: the census (the unpatched exe, it rarely changes) cuts the address space into
# CHUNKS equal-count ranges, so a cave or a dropped seed only rewrites the chunk that holds it.
_census = sorted(FUNCS)
BOUNDS = [_census[k * len(_census) // CHUNKS] for k in range(1, CHUNKS)]
# The census reads the unpatched exe: a PATCH cave reached by a call is a function entry of its own.
FUNCS.update({p["addr"]: "call" for p in patches.active() if p.get("entry")})
FUNCS.update({a: "call" for p in patches.active() for a in p.get("entries", ())})   # calls into a multi-entry cave
L = None
# RN_JOBS caps both pools: a pod quota is smaller than os.cpu_count() and freezes the container when exceeded.
JOBS = int(os.environ.get("RN_JOBS") or os.cpu_count())


def init():
    global L
    L = Lifter("pc/Speed.exe", FUNCS)
    L.cov = COV


def work(e):
    try:
        src = L.lift(e, set(FUNCS))
        cover = [(a, i.size) for a, i in L.body(e)[0].items()] if FUNCS[e] != "data" else []
        return e, src, L.info, cover, None
    except Unsupported as x:
        return e, None, None, [], str(x)


def write_if_changed(path, text):
    if os.path.exists(path) and open(path).read() == text:
        return
    open(path, "w").write(text)


def seal():
    """Hash of everything the lift reads: the exe, the census, the lifter and patch sources, the ABK files (by size and time)."""
    h = hashlib.sha256(f"cov={COV} x87run={os.environ.get('RN_X87RUN')}".encode())
    for f in ["pc/Speed.exe", "census/speed_exe_functions.tsv",
              *sorted(glob.glob("tools/recomp/**/*.py", recursive=True) + glob.glob("tools/recomp/caves/*.s"))]:
        h.update(f.encode() + b"\0" + open(f, "rb").read())
    for r, _, fs in sorted(os.walk("game")):
        for f in sorted(fs):
            if f.lower().endswith(".abk"):
                st = os.stat(os.path.join(r, f))
                h.update(f"{r}/{f} {st.st_size} {st.st_mtime_ns}".encode())
    return h.hexdigest()


def lift_all():
    os.makedirs(GEN, exist_ok=True)
    sig, sealf = seal(), f"{GEN}/.seal"
    if os.path.exists(sealf) and open(sealf).read() == sig and all(
            os.path.exists(f"{GEN}/{n}") for n in ["funcs.h", "table.c", "abk.c"] + [f"f{k:03d}.c" for k in range(CHUNKS)]):
        print(f"lift skipped: inputs unchanged (seal {sig[:12]}, delete {sealf} to force)")
        return
    with mp.Pool(JOBS, initializer=init) as pool:
        res = pool.map(work, sorted(FUNCS), chunksize=64)
    # A data pointer that lands inside an instruction of real code is not a code start.
    inside = set()
    for e, src, info, cover, err in res:
        for a, n in cover:
            inside.update(range(a + 1, a + n))
    traps, failed, dropped, out = collections.Counter(), {}, 0, []
    for e, src, info, cover, err in res:
        if err:
            failed[hex(e)] = err
            continue
        if FUNCS[e] == "data" and e in inside:
            dropped += 1
            continue
        out.append((e, src))
        for t in info["traps"]:
            traps[t.split(" 0x")[0]] += 1
    protos = "".join(f"void f_{e:x}(Ctx *c);\n" for e, _ in out)
    if COV:     # RNI_<addr> = position in the sorted table (rn_fn_addr); RN_COV(k) marks it (host/cov.c)
        protos += ("extern uint8_t rn_cov_map[];\n#define RN_COV(k) (rn_cov_map[k] = 1)\nenum {"
                   + ",".join(f"RNI_{e:x}={k}" for k, (e, _) in enumerate(out)) + "};\n")
    write_if_changed(f"{GEN}/funcs.h", '#pragma once\n#include "rt.h"\n' + protos)
    parts = [[] for _ in range(CHUNKS)]
    for e, s in out:
        parts[bisect.bisect_right(BOUNDS, e)].append(s)
    for k, part in enumerate(parts):
        write_if_changed(f"{GEN}/f{k:03d}.c", '#include "funcs.h"\n' + "\n".join(part))
    write_if_changed(f"{GEN}/table.c", '#include "funcs.h"\n'
                     f"const uint32_t rn_fn_count = {len(out)};\n"
                     "const uint32_t rn_fn_addr[] = {" + ",".join(f"0x{e:x}" for e, _ in out) + "};\n"
                     "void (*const rn_fn_ptr[])(Ctx *) = {" + ",".join(f"f_{e:x}" for e, _ in out) + "};\n"
                     + patches.c_table())
    pe = pefile.PE("pc/Speed.exe")
    img, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    src, _, mods = abk.c_source(FUNCS, {e for e, _ in out}, lambda a: struct.unpack_from("<I", img, a - base)[0])
    write_if_changed(f"{GEN}/abk.c", src)
    rep = {"functions": len(out), **mods, "patches": [f"{p['addr']:#x}" for p in patches.active()], "data_seeds_inside_instructions": dropped, "failed": failed,
           "trap_sites_by_reason": dict(traps.most_common())}
    if not COV:     # a coverage build lifts the same functions: it leaves the report alone
        json.dump(rep, open("census/lift_report.json", "w"), indent=1)
    print(f"patches active: {len(patches.active())}")
    print(f"lifted {len(out)} functions, dropped {dropped} false data seeds, failed {len(failed)}, "
          f"trap sites {sum(traps.values())}")
    print(f"ABK code modules: {mods}")
    print("top trap reasons:", dict(traps.most_common(15)))
    open(sealf, "w").write(sig)


def stale(o, src, gen=GEN):
    """True when object o is missing or older than src or any header src includes (host/ or gen/, followed recursively).
    funcs.h only counts in a coverage build: elsewhere it holds prototypes of one shape, and every new function changes it."""
    if not os.path.exists(o):
        return True
    seen, todo = {src}, [src]
    while todo:
        for m in re.findall(r'#include "([^"]+)"', open(todo.pop()).read()):
            if m == "funcs.h" and not COV:
                continue
            p = next((f"{d}/{m}" for d in ("host", gen) if os.path.exists(f"{d}/{m}")), None)
            if p and p not in seen:
                seen.add(p)
                todo.append(p)
    return os.path.getmtime(o) < max(map(os.path.getmtime, seen))


HOST = ["host/main.c", "host/dispatch.c", "host/win32.c", "host/user32.c", "host/threads.c", "host/net.c", "host/cpu.c",
        "host/d3d9.c", "host/sm1.c", "host/gpu.c", "host/dinput8.c", "host/dsound.c", "host/files.c", "host/input.c", "host/abk.c", "host/bridge.c", "host/carsmooth.c", "host/rivals.c", "host/free.c", "host/aitel.c", "host/lights.c", "host/trackfiles.c", "host/mode_menu.c", "host/cov.c", "host/horn.c", "host/feellog.c", "host/phase.c", "host/crashwatch.c"]


def compile_native():
    srcs = [f"{GEN}/f{k:03d}.c" for k in range(CHUNKS)] + [f"{GEN}/table.c", f"{GEN}/abk.c"]
    obj = "build/obj_cov" if COV else "build/obj"
    os.makedirs(obj, exist_ok=True)
    flags = ["-O2", "-w", "-Ihost", f"-I{GEN}", "-fno-strict-aliasing"]
    jobs = []
    for s in srcs:
        o = obj + "/" + os.path.basename(s)[:-2] + ".o"
        if stale(o, s):
            jobs.append(["clang", *flags, "-c", s, "-o", o])
    run_jobs(jobs)
    objs = [obj + "/" + os.path.basename(s)[:-2] + ".o" for s in srcs]
    out = "build/speed_cov" if COV else "build/speed"
    subprocess.run(["clang", "-O2", "-g", "-Wall", "-Wno-unused-function", "-Ihost", f"-I{GEN}", *(["-DRN_COV"] if COV else []), *HOST, *objs,
                    "-lm", "-o", out], check=True)
    print("built " + out)


def compile_web():
    lite = os.environ.get("RN_LITE_WASM") == "1"
    output = "speed_lite" if lite else "speed"
    srcs = [f"{GEN}/f{k:03d}.c" for k in range(CHUNKS)] + [f"{GEN}/table.c", f"{GEN}/abk.c"]
    # RN_NOCHK=1: guest bounds checks off (host/rt.h), objects in their own folder. Off by default.
    nochk = os.environ.get("RN_NOCHK") == "1"
    # RN_STW=1: the store-watch build (host/rt.h, host/crashwatch.c): last-access address in halt_at, watched stores call rn_stw_hit. Off by default.
    stw = os.environ.get("RN_STW") == "1"
    wobj = "build/wobj-nochk/" if nochk else "build/wobj-stw/" if stw else "build/wobj/"
    os.makedirs(wobj, exist_ok=True)
    flags = ["-O2", "-w", "-Ihost", f"-I{GEN}", "-fno-strict-aliasing", "-pthread", *(["-DRN_NOCHK"] if nochk else []), *(["-DRN_STW"] if stw else [])]
    jobs = []
    for s in srcs:
        o = wobj + os.path.basename(s)[:-2] + ".o"
        if stale(o, s):
            jobs.append(["emcc", *flags, "-c", s, "-o", o])
    run_jobs(jobs)
    objs = [wobj + os.path.basename(s)[:-2] + ".o" for s in srcs]
    os.makedirs("web/out", exist_ok=True)
    # main() runs in a worker (PROXY_TO_PTHREAD) so guest threads and waits may block.
    subprocess.run(["emcc", "-O2", "-pthread", "-Ihost", f"-I{GEN}", *(["-DRN_STW"] if stw else []),
                    *(["-DRN_LITE_WASM"] if lite else []), *HOST, *objs, "-o", f"web/out/{output}.js",
                    f"-sINITIAL_MEMORY={640 if lite else 896}MB", "-sSTACK_SIZE=4MB",
                    f"-sDEFAULT_PTHREAD_STACK_SIZE={2 if lite else 4}MB",
                    "-sPROXY_TO_PTHREAD=1", f"-sPTHREAD_POOL_SIZE={7 if lite else 9}", "-sEXIT_RUNTIME=1",
                    "-sMODULARIZE=1", "-sEXPORT_NAME=Speed", "-sEXPORTED_RUNTIME_METHODS=FS,ENV,HEAPU8,HEAP32,HEAPU32,HEAPF64",
                    "-sEXPORTED_FUNCTIONS=_main,_rn_gpu_mailbox,_rn_input_ring,_rn_audio_ring,_rn_telem_addr,_rn_stab_addr,_rn_tune_addr,_rn_mem_mb,_rn_load_addr",
                    "-sFORCE_FILESYSTEM=1", "-sENVIRONMENT=web,worker",
                    # RN_PROF=1: keep function names for a CPU profile (tools/webcheck.mjs RN_PROFILE); same code.
                    *(["--profiling-funcs"] if os.environ.get("RN_PROF") else [])], check=True)
    print(f"built web/out/{output}.js + {output}.wasm")


def run_jobs(jobs):
    running, bad = [], 0
    for j in jobs:
        while len(running) >= JOBS:
            bad += running.pop(0).wait() != 0
        running.append(subprocess.Popen(j))
    bad += sum(p.wait() != 0 for p in running)
    if bad:
        sys.exit("compile failed")
    if jobs:
        print(f"compiled {len(jobs)} files")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "native"
    if COV and what == "web":
        sys.exit("RN_COV=1 is a native-only build")
    lift_all()
    if what == "native":
        compile_native()
    elif what == "web":
        compile_web()
