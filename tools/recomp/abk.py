"""ABK code modules: the x86 code the sound engine runs out of game/Sound/*.abk, lifted ahead of time.

The ABK header (file offset 0 .. u32 +0x18) holds patch descriptors (+0x1c, count u16 +0xa); a descriptor's
+0x28 is the offset of its code. The engine copies the header to the heap and relocates it (0x64df30):
  table at file +0x30: count, then offsets of call rel32 fields that hold an index into the function table
                       0x6e9ae8 of Speed.exe; the field becomes the rel32 to that function.
  table at file +0x34: count, then offsets of dwords that get the copy's base added.
Each distinct module is lifted once at its own canonical base CB. In the C every address inside the module is
written (mb+offset); mb (c->mb) is the base of the live copy, found by host/abk.c from the header.
"""
import hashlib, os, re, struct
from capstone import CS_GRP_CALL, CS_GRP_JUMP
from capstone import x86
from lift import Lifter

FN_TABLE = 0x6e9ae8
CB0, CB_STEP = 0xa0000000, 0x10000      # canonical bases; a header is at most 0x2780 bytes (all 106 files)


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def modules(root="game"):
    """Distinct modules: id, size, header bytes, both relocation tables, patch code offsets, files."""
    out = {}
    for r, _, fs in sorted(os.walk(root)):
        for f in sorted(fs):
            if not f.lower().endswith(".abk"):
                continue
            p = os.path.join(r, f)
            d = open(p, "rb").read()
            hdr = d[:u32(d, 0x18)]
            key = (u32(d, 0x10), u32(d, 0x14))
            if key in out:
                if out[key]["hdr"] != hdr:
                    raise SystemExit(f"ABK {p}: same id and size as {out[key]['files'][0]}, other header")
                out[key]["files"].append(p)
                continue
            t1, t2 = u32(d, 0x30), u32(d, 0x34)
            calls = [u32(d, t1 + 4 + 4 * k) for k in range(u32(d, t1))]
            based = [u32(d, t2 + 4 + 4 * k) for k in range(u32(d, t2))]
            seeds, o = [], u32(d, 0x1c)
            for _ in range(struct.unpack_from("<H", d, 0xa)[0]):
                seeds.append(u32(d, o + 0x28))
                o += 0x3c + 4 * (d[o + 0x24] + d[o + 0x27])
            out[key] = dict(id=key[0], size=key[1], hdr=hdr, calls=calls, based=based, seeds=seeds, files=[p])
    return list(out.values())


def relocate(m, base, exe_u32):
    """The header as 0x64df30 leaves it at base. exe_u32(a) reads a dword of Speed.exe."""
    d = bytearray(m["hdr"])
    for s in m["calls"]:
        struct.pack_into("<I", d, s, (exe_u32(FN_TABLE + 4 * u32(d, s)) - (base + s) - 4) & 0xffffffff)
    for s in m["based"]:
        struct.pack_into("<I", d, s, (u32(d, s) + base) & 0xffffffff)
    return d


def module_lifter(m, cb, funcs, exe_u32):
    blob = relocate(m, cb, exe_u32)
    end = cb + len(blob)
    entries, todo = set(), [cb + s for s in m["seeds"]]
    while todo:      # functions: patch code entries and every direct call target inside the module
        e = todo.pop()
        if e in entries:
            continue
        entries.add(e)
        body = Lifter.image(blob, cb, {**funcs, **{a: "call" for a in entries | {e}}}).body(e)[0]
        for i in body.values():
            if i.group(CS_GRP_CALL) and i.operands[0].type == x86.X86_OP_IMM and cb <= i.operands[0].imm < end:
                todo.append(i.operands[0].imm)
    return Lifter.image(blob, cb, {**funcs, **{a: "call" for a in entries}}), entries


def lift_module(m, cb, funcs, lifted, exe_u32, flag_abi=None):
    """C for one module at canonical base cb: (key, offsets of its functions, C text with names m<key>_<off>)."""
    L, entries = module_lifter(m, cb, funcs, exe_u32)
    L.flag_abi = flag_abi
    end = cb + len(L.img)
    based = {cb + s for s in m["based"]}
    src = []
    for e in sorted(entries):
        body, switches, _ = L.body(e)
        for i in body.values():
            # A literal that looks like a module address must be one: a relocated dword inside the instruction.
            # Branch targets are relative, so they move with the code.
            if i.group(CS_GRP_CALL) or i.group(CS_GRP_JUMP):
                continue
            vals = [op.imm & 0xffffffff for op in i.operands if op.type == x86.X86_OP_IMM]
            vals += [op.mem.disp & 0xffffffff for op in i.operands if op.type == x86.X86_OP_MEM]
            if any(cb <= v < end for v in vals) and not any(i.address <= s < i.address + i.size for s in based):
                raise SystemExit(f"ABK {m['files'][0]} +{i.address - cb:x}: literal in the module range is not relocated")
        if switches or L.addr_taken:
            raise SystemExit(f"ABK {m['files'][0]} +{e - cb:x}: jump table in module code")
        src.append(L.lift(e, lifted | entries))
    text = "\n".join(src)
    text = re.sub(r"0x([0-9a-f]+)u?\b", lambda x: f"(mb+0x{int(x[1], 16) - cb:x}u)" if cb <= int(x[1], 16) < end else x[0], text)
    text = re.sub(r"\bL([0-9a-f]+)\b", lambda x: f"Lo{int(x[1], 16) - cb:x}" if cb <= int(x[1], 16) < end else x[0], text)
    text = re.sub(r"\bf_([0-9a-f]+)\(c\)", lambda x: f"(c->mb=mb, M_{int(x[1], 16) - cb:x}(c))" if cb <= int(x[1], 16) < end else x[0], text)
    text = re.sub(r"void f_([0-9a-f]+)\(Ctx \*restrict c\) \{\n", lambda x: f"void M_{int(x[1], 16) - cb:x}(Ctx *restrict c) {{\nuint32_t mb=c->mb;\n", text)
    key = hashlib.sha1(text.encode()).hexdigest()[:10]       # same code, same C: lifted once
    return key, sorted(e - cb for e in entries), text.replace("M_", f"m{key}_")


def c_source(funcs, lifted, exe_u32, root="game", flag_abi=None, mods=None):
    """build/gen/abk.c: every distinct module's functions and the table host/abk.c searches."""
    if mods is None:
        mods = modules(root)
    bodies, rows, nfn = {}, [], 0
    for k, m in enumerate(mods):
        key, offs, text = lift_module(m, CB0 + k * CB_STEP, funcs, lifted, exe_u32, flag_abi)
        bodies.setdefault(key, (offs, text))
        rows.append((m, key, offs))
    out = ['#include "funcs.h"']
    for key, (offs, text) in bodies.items():
        out += [f"void m{key}_{o:x}(Ctx *c);" for o in offs] + [text]
        out.append(f"static const uint32_t off_{key}[] = {{{','.join(f'0x{o:x}' for o in offs)}}};")
        out.append(f"static void (*const fn_{key}[])(Ctx *) = {{{','.join(f'm{key}_{o:x}' for o in offs)}}};")
        nfn += len(offs)
    out.append(f"const uint32_t rn_mod_count = {len(rows)};")
    out.append("const RnMod rn_mods[] = {" + ",".join(f"{{0x{m['id']:x},0x{m['size']:x},{len(o)},off_{k},fn_{k}}}"
                                                     for m, k, o in rows) + "};")
    rep = {"abk_files": sum(len(m["files"]) for m in mods), "abk_modules": len(mods), "abk_distinct_code": len(bodies),
           "abk_functions": nfn}
    return "\n".join(out) + "\n", rows, rep
