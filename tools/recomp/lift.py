#!/usr/bin/env python3
"""Lift x86-32 functions of pc/Speed.exe to C.

Each guest function becomes `void f_<addr>(Ctx *c)` (host/rt.h). Registers and flags are C locals.
Calls and exits write back registers and live flags to the Ctx. Indirect calls and jumps go
through rn_call (address -> function). An instruction the lifter does not know becomes a TRAP that
stops the game with its address and name when it runs. Nothing is guessed.
"""
import os
import re
import struct
import pefile
import patches
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET
from capstone import x86

REG32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
LO8 = {"al": "eax", "cl": "ecx", "dl": "edx", "bl": "ebx"}
HI8 = {"ah": "eax", "ch": "ecx", "dh": "edx", "bh": "ebx"}
R16 = {"ax": "eax", "cx": "ecx", "dx": "edx", "bx": "ebx", "sp": "esp", "bp": "ebp", "si": "esi", "di": "edi"}
FLAGS = ["cf", "zf", "sf", "of", "pf", "df", "af"]
FLAG_BIT = {f: 1 << k for k, f in enumerate(f for f in FLAGS if f != "df")}
CF, ZF, SF, OF, PF, AF = FLAG_BIT.values()
STATUS = CF | ZF | SF | OF | PF | AF
SAHF = STATUS & ~OF
SHIFTS = ("shl", "sal", "shr", "sar", "shld", "shrd")
ROTATES = ("rol", "ror", "rcl", "rcr")
STOPS = ("hlt", "int3", "ud2", "iretd", "retf", "int", "int1", "into")

COND = {"o": "of", "no": "!of", "b": "cf", "ae": "!cf", "e": "zf", "ne": "!zf", "be": "(cf||zf)",
        "a": "(!cf&&!zf)", "s": "sf", "ns": "!sf", "l": "(sf!=of)", "ge": "(sf==of)",
        "le": "(zf||sf!=of)", "g": "(!zf&&sf==of)", "p": "pf", "np": "!pf"}
COND_FLAGS = {m: sum(FLAG_BIT[f] for f in set(re.findall(r"[a-z]+", expr))) for m, expr in COND.items()}
PREFIXES = ("lock ", "rep ", "repe ", "repne ", "bnd ", "notrack ")
STRING_OPS = {0xa4: "movs", 0xa5: "movs", 0xa6: "cmps", 0xa7: "cmps", 0xaa: "stos", 0xab: "stos",
              0xac: "lods", 0xad: "lods", 0xae: "scas", 0xaf: "scas"}
FPU_CONST = {0xe8: "1.0", 0xe9: "3.321928094887362347870319429489390175864831393",
             0xea: "1.442695040888963407359924681001892137426645954", 0xeb: "3.141592653589793238462643383279502884197",
             0xec: "0.301029995663981195213738894724493026768189881", 0xed: "0.693147180559945309417232121458176568075500134",
             0xee: "0.0"}

PROLOGUE = '#include "rt.h"\n'
LOW = 0x10000       # host/rt.h: guest pages below never map
# Instructions that move esp by a constant the block tracks (sp_move); any other esp write ends the block.
SP_MOVES = {"push", "pop", "pushal", "popal", "pushfd", "popfd", "call", "ret", "add", "sub"}
# Functions with a native body in host/native.h (nat_<addr>): the same operations in the same order. Native vs lifted on
# random inputs: tools/recomp/natproof/run.sh (0x5c97cb, 0x5c85c1). RN_ONLY=<addr> difftest checks the lifted body only.
# The lifted body stays as f_<addr>_lift for inputs outside the fast case.
# 0x5d6f5d D3DXMatrixMultiply (x87): 5.8 % self of the race game thread (build/bench/spk2, 2026-11-01).
# 0x5c97cb D3DX effect state apply: 11.4 % of the race game thread, ~0.5 % of it device work (spk2, 2026-11-02).
# 0x5c85c1 D3DX parameter -> shader constants copy (float type): 2.4 % of the race game thread (spk2, 2026-11-02).
NATIVE = {0x5d6f5d, 0x5c97cb, 0x5c85c1}


class Unsupported(Exception):
    pass


class FlagABI:
    """Solve Ctx flag demand at guest calls, tail calls and returns over the loaded program."""

    def __init__(self, graphs):
        self.inputs = dict.fromkeys(graphs, 0)
        self.outputs = dict.fromkeys(graphs, 0)
        self.indirect_in = self.indirect_out = 0
        changed = True
        while changed:
            changed = False
            for entry, graph in graphs.items():
                live = self.liveness(entry, graph)
                need = live.get(entry, 0)
                if need != self.inputs[entry]:
                    self.inputs[entry] = need
                    self.indirect_in |= need
                    changed = True
                for addr, (_, _, succ, edge, target) in graph.items():
                    if edge not in ("call", "tail"):
                        continue
                    need = self.successors(live, succ) if edge == "call" else self.returns(entry)
                    if target in self.outputs:
                        if need & ~self.outputs[target]:
                            self.outputs[target] |= need
                            changed = True
                    elif need & ~self.indirect_out:
                        self.indirect_out |= need
                        changed = True
            # Host APIs can make successive guest callbacks on the same Ctx.
            if self.indirect_in & ~self.indirect_out:
                self.indirect_out |= self.indirect_in
                changed = True

    def returns(self, entry):
        return self.outputs[entry] | self.indirect_out

    def arguments(self, target, result):
        # rn_call can enter any lifted function or a host API that leaves flags untouched.
        return self.inputs[target] if target in self.inputs else self.indirect_in | result

    @staticmethod
    def successors(live, succ):
        need = 0
        for addr in succ:
            need |= live.get(addr, 0)   # a missing/decode-failed label traps
        return need

    def liveness(self, entry, graph):
        """Live-in masks. Back edges and overlapping decode streams converge by union."""
        live = {}
        result = self.returns(entry)
        changed = True
        while changed:
            changed = False
            for addr, (read, kill, succ, edge, target) in reversed(graph.items()):
                after = self.successors(live, succ)
                if edge == "ret":
                    after = result
                elif edge == "call":
                    after = self.arguments(target, after)
                elif edge == "tail":
                    after |= self.arguments(target, result)
                before = read | (after & ~kill)
                if before != live.get(addr, 0):
                    live[addr] = before
                    changed = True
        return live


class Lifter:
    def __init__(self, exe, funcs=None):
        self.pe = pefile.PE(exe)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.img = bytearray(self.pe.get_memory_mapped_image())
        self.img += bytes(max(0, patches.CODE_AREA[1] - self.base - len(self.img)))   # zero RAM past the image holds the road-graph cave code
        patches.apply(self.img, self.base)
        t = next(s for s in self.pe.sections if s.Name.rstrip(b"\0") == b".text")
        self.t0, self.t1 = self.base + t.VirtualAddress, self.base + t.VirtualAddress + t.Misc_VirtualSize
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = True
        self.funcs = funcs or {}          # entry -> "call" | "data" | "entry"
        self.iat = set()
        for e in self.pe.DIRECTORY_ENTRY_IMPORT:
            for i in e.imports:
                self.iat.add(i.address)
        self._cache = {}
        self.trace = False
        self.flag_abi = None
        # Speed.exe's mapped image: a constant address inside it never faults (CHK_IMG, host/rt.h). None for ABK modules.
        self.img_end = self.base + self.pe.OPTIONAL_HEADER.SizeOfImage
        self.sp = None
        # Address-taken code: dwords in the data sections that point into .text (jump tables, vtables).
        self.addr_taken, self.addr_taken_aligned = set(), set()
        for sec in self.pe.sections:
            if sec.Name.rstrip(b"\0") == b".text":
                continue
            raw = sec.get_data()
            for o in range(len(raw) - 3):       # every offset: packed tables exist; labels filter the noise
                v = struct.unpack_from("<I", raw, o)[0]
                if self.t0 <= v < self.t1:
                    self.addr_taken.add(v)
                    if o % 4 == 0:
                        self.addr_taken_aligned.add(v)

    @classmethod
    def image(cls, img, base, funcs):
        """A lifter over raw code mapped at base (an ABK code module, tools/recomp/abk.py): no imports, and no
        code pointers in data (abk.py checks that)."""
        self = cls.__new__(cls)
        self.base, self.img, self.t0, self.t1 = base, bytearray(img), base, base + len(img)
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = True
        self.funcs, self.iat, self._cache, self.trace = funcs, set(), {}, False
        self.flag_abi = None
        self.img_end, self.sp = None, None     # relocated module: no CHK_IMG, and coalesce() decides the esp checks
        self.addr_taken, self.addr_taken_aligned = set(), set()
        return self

    def u32(self, a):
        return struct.unpack_from("<I", self.img, a - self.base)[0]

    def u8(self, a):
        return self.img[a - self.base]

    def in_image(self, a):
        return self.base <= a < self.base + len(self.img)

    def insn(self, a):
        if a in self._cache:
            return self._cache[a]
        if not (self.t0 <= a < self.t1 or patches.CODE_AREA[0] <= a < patches.CODE_AREA[1]):
            return None
        o = a - self.base
        i = next(self.md.disasm(bytes(self.img[o:o + 16]), a), None)
        if len(self._cache) > 400000:
            self._cache.clear()
        self._cache[a] = i
        return i

    def entries_after(self, a):
        """Real function entries above a, nearest first."""
        if not hasattr(self, "_real"):
            import bisect
            self._real = sorted(e for e, k in self.funcs.items() if k in ("call", "entry"))
            self._bisect = bisect.bisect_right
        k = self._bisect(self._real, a)
        return iter(self._real[k:k + 1])

    def is_func(self, a):
        """A real function entry: a jump there is a tail call, not a local branch."""
        return self.funcs.get(a) in ("call", "entry")

    # --- body discovery ---------------------------------------------------
    def body(self, entry, limit=60000):
        """Instructions of one function by local recursive descent. Returns (insns, switch_targets)."""
        seen, todo, switches, bad = {}, [entry], {}, set()
        while todo:
            a = todo.pop()
            last_cmp, negs = {}, set()   # negs: registers last written by `neg` (a table read backward, CRT memmove)
            while a not in seen and a not in bad:
                if len(seen) > limit:
                    raise Unsupported("function too big")
                i = self.insn(a)
                if i is None:
                    bad.add(a)
                    break
                seen[a] = i
                m = self.mnem(i)[1]
                op = i.operands[0] if i.operands else None
                # Jump table bounds: the largest index a register can hold when the jmp uses it.
                imm1 = len(i.operands) > 1 and i.operands[1].type == x86.X86_OP_IMM
                if m == "cmp" and op.type == x86.X86_OP_REG and imm1:
                    last_cmp[i.reg_name(op.reg)] = i.operands[1].imm
                elif m == "movzx" and op.type == x86.X86_OP_REG and i.operands[1].type == x86.X86_OP_MEM:
                    mm = i.operands[1].mem
                    src = i.reg_name(mm.base) if mm.base else None
                    last_cmp.pop(i.reg_name(op.reg), None)
                    if i.operands[1].size == 1 and src in last_cmp and not mm.index:
                        n = last_cmp[src] + 1
                        if self.in_image(mm.disp) and self.in_image(mm.disp + n):
                            last_cmp[i.reg_name(op.reg)] = max(self.u8(mm.disp + k) for k in range(n))
                elif m == "and" and op.type == x86.X86_OP_REG and imm1 and (i.operands[1].imm & (i.operands[1].imm + 1)) == 0:
                    last_cmp[i.reg_name(op.reg)] = i.operands[1].imm
                elif op is not None and op.type == x86.X86_OP_REG and m not in ("cmp", "test", "push") and not m.startswith("j"):
                    r = i.reg_name(op.reg)
                    last_cmp.pop({**LO8, **HI8, **R16}.get(r, r), None)
                if op is not None and op.type == x86.X86_OP_REG and m not in ("cmp", "test", "push") and not m.startswith("j"):
                    r = i.reg_name(op.reg)
                    (negs.add if m == "neg" else negs.discard)({**LO8, **HI8, **R16}.get(r, r))
                if m in ("call", "mul", "div", "imul", "idiv", "cdq", "lodsb", "lodsd"):
                    last_cmp.clear()
                if i.group(CS_GRP_RET) or m in STOPS:
                    break
                if i.group(CS_GRP_JUMP) or m in ("loop", "loope", "loopne", "jecxz"):
                    if op.type == x86.X86_OP_IMM:
                        t = op.imm
                        tail = t != entry and self.is_func(t)
                        if not tail:
                            todo.append(t)
                        if m == "jmp":
                            break
                    else:
                        mm = op.mem if op.type == x86.X86_OP_MEM else None
                        # Code pointers in data between this entry and the next real function are its labels.
                        nxt = next((f for f in self.entries_after(entry)), self.t1)
                        todo.extend(t for t in self.addr_taken_aligned if entry < t < nxt and not self.is_func(t))
                        if mm and not mm.base and mm.index and mm.scale == 4:
                            n = last_cmp.get(i.reg_name(mm.index))
                            tg = self.table(mm.disp, None if n is None else n + 1)
                            if i.reg_name(mm.index) in negs:
                                # `neg idx; jmp [idx*4+disp]` (0x6727f6, 0x678ef6): entries sit below disp. Read down while
                                # the dword points inside this function; the dword past the table (0x6728a8) does not.
                                k = 1
                                while self.in_image(mm.disp - 4 * k) and entry <= self.u32(mm.disp - 4 * k) < nxt:
                                    tg.append(self.u32(mm.disp - 4 * k))
                                    k += 1
                            switches[a] = tg
                            todo.extend(t for t in tg if not (t != entry and self.is_func(t)))
                        break
                a = i.address + i.size
        return seen, switches, bad

    def table(self, at, n):
        """Targets of a jump table. With a known bound, entries that are not code are skipped (a table base
        may overlap code when index 0 is never used); without one, read until the first non-code dword."""
        out = []
        for k in range(n if n is not None else 1024):
            if not self.in_image(at + 4 * k + 3):
                break
            v = self.u32(at + 4 * k)
            if self.t0 <= v < self.t1:
                out.append(v)
            elif n is None:
                break
        return out

    # --- operand helpers --------------------------------------------------
    @staticmethod
    def mnem(i):
        m, pre = i.mnemonic, ""
        for p in PREFIXES:
            if m.startswith(p):
                pre, m = p.strip(), m[len(p):]
        return pre, m

    @staticmethod
    def flag_effect(i, pre, m):
        """Reads and definite writes of the C templates. Undefined flags follow the existing lifter."""
        if m in ("adc", "sbb"):
            return CF, STATUS
        if m in ("add", "sub", "cmp", "test", "and", "or", "xor", "neg", "xadd", "popfd"):
            return 0, STATUS
        if m in ("inc", "dec"):
            return 0, STATUS & ~CF
        if m in SHIFTS or m in ROTATES:
            count = i.operands[-1] if len(i.operands) > 1 else None
            # A register count can be zero, leaving the previous flags live.
            writes = STATUS & ~AF if m in ("shld", "shrd") else STATUS if m in SHIFTS else CF | OF
            if count is not None and (count.type != x86.X86_OP_IMM or not count.imm & 31):
                writes = 0
            return (CF if m in ("rcl", "rcr") else 0), writes
        if m in ("imul", "mul"):
            return 0, CF | OF
        if m in ("clc", "stc", "bt", "bts", "btr", "btc"):
            return 0, CF
        if m == "cmc":
            return CF, CF
        if m == "pushfd":
            return STATUS, 0
        if m == "lahf":
            return SAHF, 0
        if m == "sahf":
            return 0, SAHF
        if m in ("fcomi", "fucomi", "fcomip", "fucomip"):
            return 0, STATUS & ~AF
        if i.opcode[0] in (0xa6, 0xa7, 0xae, 0xaf):
            return 0, 0 if pre else STATUS   # REP can execute zero iterations
        if m in ("loope", "loopne"):
            return ZF, 0
        if m.startswith("j"):
            return COND_FLAGS.get(m[1:], 0), 0
        if m.startswith("set"):
            return COND_FLAGS.get(m[3:], 0), 0
        return 0, 0

    def case_labels(self, switches, labels):
        return {t for tg in switches.values() for t in tg if t in labels} | (self.addr_taken & labels)

    def flag_graph(self, entry, body, switches, bad, compact=False):
        """Model the same edges as emit(), including the default tail of a computed jump."""
        labels = body.keys() | bad
        cases = self.case_labels(switches, labels)
        targets = cases | {entry}
        graph = {}
        for a, i in body.items():
            pre, m = self.mnem(i)
            read, kill = self.flag_effect(i, pre, m)
            nxt = a + i.size
            succ, edge, target = (nxt,), None, None
            if m == "ret":
                succ, edge = (), "ret"
            elif i.group(CS_GRP_RET) or m in STOPS:
                succ = ()
            elif m == "call":
                op = i.operands[0]
                if op.type != x86.X86_OP_IMM or op.imm != nxt:
                    edge = "call"
                    target = op.imm if op.type == x86.X86_OP_IMM else None
            elif m == "jmp" or m in ("loop", "loope", "loopne", "jecxz") or (m.startswith("j") and m[1:] in COND):
                op = i.operands[0]
                succ = () if m == "jmp" else succ
                if op.type != x86.X86_OP_IMM:
                    succ, edge = tuple(cases), "tail"
                elif op.imm in labels:
                    succ += (op.imm,)
                    targets.add(op.imm)
                else:
                    edge, target = "tail", op.imm
            graph[a] = (read, kill, succ, edge, target)
        if not compact:
            return graph
        # Keep one transfer per straight-line block for the whole-program fixpoint.
        blocks = {}
        start = None
        for a, (read, kill, succ, edge, target) in graph.items():
            if start is not None and a not in targets:
                r, k, prev, boundary, _ = blocks[start]
                if prev == (a,) and boundary is None:
                    blocks[start] = (r | (read & ~k), k | kill, succ, edge, target)
                    continue
            start = a
            blocks[start] = (read, kill, succ, edge, target)
        return blocks

    def ea(self, mem):
        parts = []
        if mem.segment == x86.X86_REG_FS:
            parts.append("c->fs")
        elif mem.segment not in (0, x86.X86_REG_DS, x86.X86_REG_SS, x86.X86_REG_ES, x86.X86_REG_CS):
            raise Unsupported(f"segment {self.i.reg_name(mem.segment)}")
        if mem.base:
            parts.append(self.r32(mem.base))
        if mem.index:
            parts.append(f"{self.r32(mem.index)}*{mem.scale}u")
        parts.append(f"0x{mem.disp & 0xffffffff:x}u")
        return "(uint32_t)(" + "+".join(parts) + ")"

    def r32(self, reg):
        n = self.i.reg_name(reg)
        if n not in REG32:
            raise Unsupported(f"reg {n}")
        return n

    def at(self):
        return f"0x{self.i.address:x}"

    def chk(self, mem, n):
        """The bounds check of a memory operand at ea: CHK_IMG for a constant address inside Speed.exe's image, the
        block's coalesced esp check for [esp+disp], else CHK."""
        if mem.segment != x86.X86_REG_FS and not mem.index:
            if not mem.base and self.img_end and LOW <= (mem.disp & 0xffffffff) and (mem.disp & 0xffffffff) + n <= self.img_end:
                return f"CHK_IMG(ea,{n},{self.at()});"
            if mem.base == x86.X86_REG_ESP and self.sp is not None:
                return self.sp_acc(mem.disp, n)
        return f"CHK(ea,{n},{self.at()});"

    # --- esp check coalescing -----------------------------------------------
    # In a straight-line block (no jump target, branch, call, ret, or esp write other than push/pop/add/sub imm), esp
    # moves by constants only, so every stack access is [base + const]: one CHK_SP of their span at the block's start
    # replaces the per-instruction checks (kept as CHK_STW for RN_STW builds, host/rt.h). A bad esp then faults at the
    # block's first instruction instead of the access itself.
    def sp_open(self):
        self.sp = {"d": 0, "lo": None, "hi": None, "at": None, "idx": len(self.out)}
        self.out.append("")

    def sp_close(self):
        sp, self.sp = self.sp, None
        if sp and sp["lo"] is not None:
            lo = sp["lo"] & 0xffffffff
            self.out[sp["idx"]] = f"CHK_SP((uint32_t)(esp+0x{lo:x}u),{sp['hi'] - sp['lo']},{sp['at']});"

    def sp_move(self, d):
        if self.sp is not None:
            self.sp["d"] += d

    def sp_acc(self, off, n):
        """Check of n bytes at esp+off (esp as it is now): recorded in the block, or a plain CHK outside one."""
        sp = self.sp
        if sp is None:
            return f"CHK((uint32_t)(esp+0x{off & 0xffffffff:x}u),{n},{self.at()});" if off else f"CHK(esp,{n},{self.at()});"
        a, b = sp["d"] + off, sp["d"] + off + n
        if sp["lo"] is None:
            sp["lo"], sp["hi"], sp["at"] = a, b, self.at()
        sp["lo"], sp["hi"] = min(sp["lo"], a), max(sp["hi"], b)
        e = f"(uint32_t)(esp+0x{off & 0xffffffff:x}u)" if off else "esp"
        return f"CHK_STW({e},{n},{self.at()});"

    def addr(self, op):
        if op.size not in (1, 2, 4):
            raise Unsupported(f"{op.size}-byte operand")     # far pointers (m16:32), m64...
        self.out.append(f"ea={self.ea(op.mem)}; {self.chk(op.mem, op.size)}")

    def read(self, op, size=None):
        if op.type == x86.X86_OP_IMM:
            s = size or op.size
            return f"0x{op.imm & ((1 << (8 * s)) - 1):x}u"
        if op.type == x86.X86_OP_REG:
            n = self.i.reg_name(op.reg)
            if n in REG32:
                return n
            if n in R16:
                return f"({R16[n]}&0xffffu)"
            if n in LO8:
                return f"({LO8[n]}&0xffu)"
            if n in HI8:
                return f"(({HI8[n]}>>8)&0xffu)"
            raise Unsupported(f"reg {n}")
        self.addr(op)
        return f"ld(c,ea,{op.size})"

    def write(self, op, v):
        if op.type == x86.X86_OP_REG:
            n = self.i.reg_name(op.reg)
            if n in REG32:
                return f"{n}=(uint32_t)({v});"
            if n in R16:
                r = R16[n]
                return f"{r}=({r}&0xffff0000u)|(({v})&0xffffu);"
            if n in LO8:
                r = LO8[n]
                return f"{r}=({r}&0xffffff00u)|(({v})&0xffu);"
            if n in HI8:
                r = HI8[n]
                return f"{r}=({r}&0xffff00ffu)|((({v})&0xffu)<<8);"
            raise Unsupported(f"reg {n}")
        return f"st(c,ea,(uint32_t)({v}),{op.size});"      # ea from the matching read() or addr()

    def mem_dst(self, op):
        if op.type == x86.X86_OP_MEM:
            self.addr(op)

    def flag_assign(self, **values):
        return "".join(f"{f}={v}; " for f, v in values.items() if self.live_flags & FLAG_BIT[f])

    def mul_flags(self, expr):
        return "".join(f"{f}=" for f in ("cf", "of") if self.live_flags & FLAG_BIT[f]) + expr + ";" \
            if self.live_flags & (CF | OF) else ""

    def zsp(self, M, S, repeat=False):
        # Repeated CMPS/SCAS use the newly computed ZF for loop termination.
        zf = f"zf=(res&0x{M:x}u)==0; " if repeat or self.live_flags & ZF else ""
        return zf + self.flag_assign(sf=f"(res&0x{S:x}u)!=0", pf="par(res)")

    def arith(self, m, M, S, repeat=False):
        if m in ("add", "xadd", "adc"):
            rhs = "t2+cf" if m == "adc" else "t2"
            code = f"res=(t1+{rhs})&0x{M:x}u; "
            code += self.flag_assign(af="((t1^t2^res)>>4)&1", cf=f"((uint64_t)t1+{rhs})>0x{M:x}u",
                                     of=f"((~(t1^t2))&(t1^res)&0x{S:x}u)!=0")
        elif m in ("sub", "cmp", "sbb"):
            rhs = "t2-cf" if m == "sbb" else "t2"
            code = f"res=(t1-{rhs})&0x{M:x}u; "
            code += self.flag_assign(af="((t1^t2^res)>>4)&1",
                                     cf="(uint64_t)t1<(uint64_t)t2+cf" if m == "sbb" else "t1<t2",
                                     of=f"((t1^t2)&(t1^res)&0x{S:x}u)!=0")
        else:
            opc = {"and": "&", "test": "&", "or": "|", "xor": "^"}[m]
            code = f"res=(t1{opc}t2)&0x{M:x}u; " + self.flag_assign(cf=0, of=0, af=0)
        return code + self.zsp(M, S, repeat)

    # --- control transfer -------------------------------------------------
    @staticmethod
    def ctx_flags(mask):
        return (f for f in FLAGS if f == "df" or mask & FLAG_BIT[f])

    def save(self, mask=STATUS):
        return " ".join(f"c->r[{k}]={r};" for k, r in enumerate(REG32)) + " " + " ".join(f"c->{f}={f};" for f in self.ctx_flags(mask))

    def load(self, mask):
        return " ".join(f"{r}=c->r[{k}];" for k, r in enumerate(REG32)) + " " + " ".join(f"{f}=c->{f};" for f in self.ctx_flags(mask))

    def call_to(self, target_c, target=None):
        """Call a guest/host address. target_c is a C expression already computed into t1 if indirect."""
        nxt = self.i.address + self.i.size
        o = self.out
        inputs = STATUS if self.strict_flags else self.flag_abi.arguments(target, self.live_flags)
        self.sp_move(-4)
        o.append(f"esp-=4; {self.sp_acc(0, 4)} st(c,esp,0x{nxt:x}u,4); {self.save(inputs)}")
        o.append(f"f_{target:x}(c);" if target in self.lifted else f"rn_call(c,{target_c});")
        o.append(f"{self.load(self.live_flags)} if (c->halt) return; if (c->ret!=0x{nxt:x}u) TRAP({self.at()},\"return address changed\");")

    def tail(self, target_c, target=None):
        inputs = STATUS if self.strict_flags else self.flag_abi.arguments(target, self.return_flags)
        call = f"f_{target:x}(c);" if target in self.lifted else f"rn_call(c,{target_c});"
        return f"{{ {self.save(inputs)} {call} return; }}"

    def jump(self, t, cond=None):
        if t in self.labels:   # a backward jump closes a loop: a preemption point (rt.h PREEMPT)
            s = f"{{ PREEMPT(); goto L{t:x}; }}" if t <= self.i.address else f"goto L{t:x};"
        else:
            s = self.tail(f"0x{t:x}u", t)
        return f"if ({cond}) {s}" if cond else s

    # --- one instruction --------------------------------------------------
    def emit(self, i):
        self.i = i
        pre, m = self.mnem(i)
        ops = i.operands
        o = self.out
        op0 = i.opcode[0]
        if 0xd8 <= op0 <= 0xdf:
            return self.x87(i)
        if m == "emms" or any(x.type == x86.X86_OP_REG and i.reg_name(x.reg).startswith("mm") for x in ops):
            return self.mmx(i, m)
        if m in ("wait", "nop", "fwait") or (m == "pause"):
            return
        sz = ops[0].size if ops else 4
        M = (1 << (8 * sz)) - 1
        S = 1 << (8 * sz - 1)

        if op0 in STRING_OPS and len(i.opcode) and i.opcode[1] == 0:
            return self.string(i, pre, STRING_OPS[op0], 1 if op0 & 1 == 0 else (2 if i.prefix[2] == 0x66 else 4))
        if m in ("mov", "movzx"):
            for x in ops:
                if x.type == x86.X86_OP_REG and i.reg_name(x.reg) not in (*REG32, *R16, *LO8, *HI8):
                    raise Unsupported(f"mov {i.reg_name(x.reg)}")
            v = self.read(ops[1], sz)
            self.mem_dst(ops[0])
            o.append(self.write(ops[0], v))
            return
        if m == "movsx":
            s2 = ops[1].size
            v = self.read(ops[1])
            o.append(self.write(ops[0], f"(uint32_t)(int32_t)(int{8*s2}_t)({v})"))
            return
        if m == "lea":
            o.append(self.write(ops[0], self.ea(ops[1].mem)))
            return
        if m in ("add", "sub") and ops[0].type == x86.X86_OP_REG and i.reg_name(ops[0].reg) == "esp" and ops[1].type == x86.X86_OP_IMM:
            imm = ((ops[1].imm & 0xffffffff) ^ 0x80000000) - 0x80000000     # signed: `add esp,-8`
            self.sp_move(imm if m == "add" else -imm)
        if m in ("add", "sub", "adc", "sbb", "and", "or", "xor", "cmp", "test"):
            b = self.read(ops[1], sz)
            o.append(f"t2={b};")
            a = self.read(ops[0])
            o.append(f"t1={a}; " + self.arith(m, M, S))
            if m not in ("cmp", "test"):
                o.append(self.write(ops[0], "res"))
            return
        if m in ("inc", "dec", "neg", "not"):
            a = self.read(ops[0])
            o.append(f"t1={a};")
            expr = {"inc": "t1+1", "dec": "t1-1", "neg": "0u-t1", "not": "~t1"}[m]
            o.append(f"res=({expr})&0x{M:x}u;")
            if m == "neg":
                o.append(self.flag_assign(cf="t1!=0"))
            if m != "not":
                ov = "res" if m == "inc" else "t1"
                o.append(self.flag_assign(of=f"{ov}==0x{S:x}u", af="((t1^res)>>4)&1") + self.zsp(M, S))
            o.append(self.write(ops[0], "res"))
            return
        if m in ("shl", "sal", "shr", "sar") or m in ROTATES:
            n = self.read(ops[1]) if len(ops) > 1 else "1u"
            o.append(f"n=({n})&31u;")
            a = self.read(ops[0])
            o.append(f"t1={a};")
            bits = 8 * sz
            o.append("if (n) {")
            if m in ("shl", "sal"):
                carry = f"n<={bits}?(int)((((uint64_t)t1)>>({bits}-n))&1):0"
                of_carry = "cf" if self.live_flags & CF else f"({carry})"
                o.append(f"res=(uint32_t)(((uint64_t)t1<<n)&0x{M:x}u); " +
                         self.flag_assign(cf=carry, of=f"((res&0x{S:x}u)!=0)^{of_carry}", af=0))
            elif m == "shr":
                o.append("res=(uint32_t)((uint64_t)t1>>n); " +
                         self.flag_assign(cf="(int)(((uint64_t)t1>>(n-1))&1)", of=f"(t1&0x{S:x}u)!=0", af=0))
            elif m == "sar":
                o.append(f"res=(uint32_t)(((int64_t)(int{bits}_t)t1)>>n)&0x{M:x}u; " +
                         self.flag_assign(cf=f"(int)((((int64_t)(int{bits}_t)t1)>>(n-1))&1)", of=0, af=0))
            elif m == "rol":
                o.append(f"k=n%{bits}; res=k?((t1<<k)|(t1>>({bits}-k)))&0x{M:x}u:t1; " +
                         self.flag_assign(cf="res&1", of=f"((res&0x{S:x}u)!=0)^(res&1)"))
            elif m == "ror":
                o.append(f"k=n%{bits}; res=k?((t1>>k)|(t1<<({bits}-k)))&0x{M:x}u:t1; " +
                         self.flag_assign(cf=f"(res&0x{S:x}u)!=0", of=f"((res^(res<<1))&0x{S:x}u)!=0"))
            else:
                # Carry is part of the rotated value even when the final CF is dead.
                if m == "rcl":
                    o.append(f"t2=cf; res=t1; for (k=n%{bits + 1}; k; k--) {{ uint32_t hi=(res&0x{S:x}u)!=0; res=((res<<1)|t2)&0x{M:x}u; t2=hi; }}")
                    o.append(self.flag_assign(of=f"((res&0x{S:x}u)!=0)^t2", cf="t2"))
                else:
                    o.append(self.flag_assign(of=f"((t1&0x{S:x}u)!=0)^cf"))
                    o.append(f"t2=cf; res=t1; for (k=n%{bits + 1}; k; k--) {{ uint32_t lo=res&1; res=(res>>1)|(t2?0x{S:x}u:0); t2=lo; }}")
                    o.append(self.flag_assign(cf="t2"))
            if m in SHIFTS:
                o.append(self.zsp(M, S))
            o.append(self.write(ops[0], "res"))
            o.append("}")
            return
        if m in ("shld", "shrd"):
            if sz != 4:
                raise Unsupported(f"{m}16")
            n = self.read(ops[2])
            o.append(f"n=({n})&31u; t2={self.read(ops[1])};")
            a = self.read(ops[0])
            o.append(f"t1={a}; if (n) {{")
            if m == "shld":
                o.append("res=(t1<<n)|(t2>>(32-n)); " + self.flag_assign(cf="(t1>>(32-n))&1"))
            else:
                o.append("res=(t1>>n)|(t2<<(32-n)); " + self.flag_assign(cf="(t1>>(n-1))&1"))
            o.append(self.flag_assign(of="((res^t1)&0x80000000u)!=0") + self.zsp(M, S))
            o.append(self.write(ops[0], "res"))
            o.append("}")
            return
        if m in ("bt", "bts", "btr", "btc"):
            bits = 8 * sz
            if ops[0].type == x86.X86_OP_MEM and ops[1].type == x86.X86_OP_REG:
                o.append(f"t2={self.read(ops[1])}; ea={self.ea(ops[0].mem)}+(uint32_t)(((int32_t)t2>>5)*4); CHK(ea,4,{self.at()}); t1=ld(c,ea,4); n=t2&31u;")
                dst = f"st(c,ea,res,4);"
            else:
                o.append(f"n=({self.read(ops[1])})&{bits - 1}u;")
                o.append(f"t1={self.read(ops[0])};")
                dst = self.write(ops[0], "res")
            o.append(self.flag_assign(cf="(t1>>n)&1"))
            if m != "bt":
                expr = {"bts": "t1|(1u<<n)", "btr": "t1&~(1u<<n)", "btc": "t1^(1u<<n)"}[m]
                o.append(f"res={expr}; {dst}")
            return
        if m == "imul" and len(ops) >= 2:
            b = self.read(ops[2], sz) if len(ops) == 3 else self.read(ops[1])
            o.append(f"t2={b};")
            a = self.read(ops[1]) if len(ops) == 3 else self.read(ops[0])
            bits = 8 * sz
            o.append(f"w=(int64_t)(int{bits}_t)({a})*(int64_t)(int{bits}_t)t2; " +
                     self.mul_flags(f"(w!=(int64_t)(int{bits}_t)w)"))
            o.append(self.write(ops[0], "(uint32_t)w"))
            return
        if m in ("mul", "imul", "div", "idiv"):
            v = self.read(ops[0])
            o.append(f"t1={v};")
            at = self.at()
            if sz == 4:
                o.append({
                    "mul": "u=(uint64_t)eax*t1; eax=(uint32_t)u; edx=(uint32_t)(u>>32); " + self.mul_flags("edx!=0"),
                    "imul": "w=(int64_t)(int32_t)eax*(int32_t)t1; eax=(uint32_t)w; edx=(uint32_t)((uint64_t)w>>32); " + self.mul_flags("(w!=(int64_t)(int32_t)w)"),
                    "div": f"u=((uint64_t)edx<<32)|eax; if (!t1 || u/t1>0xffffffffu) TRAP({at},\"divide error\"); eax=(uint32_t)(u/t1); edx=(uint32_t)(u%t1);",
                    "idiv": f"w=(int64_t)(((uint64_t)edx<<32)|eax); if (!t1) TRAP({at},\"divide error\"); {{ int64_t q=w/(int32_t)t1; if (q!=(int32_t)q) TRAP({at},\"divide error\"); eax=(uint32_t)q; edx=(uint32_t)(w%(int32_t)t1); }}",
                }[m])
            elif sz == 2:
                o.append({
                    "mul": "u=(eax&0xffffu)*(uint64_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(u&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((u>>16)&0xffff); " + self.mul_flags("(u>>16)!=0"),
                    "imul": "w=(int64_t)(int16_t)eax*(int16_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(w&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((w>>16)&0xffff); " + self.mul_flags("(w!=(int16_t)w)"),
                    "div": f"u=((edx&0xffffu)<<16)|(eax&0xffffu); if (!t1 || u/t1>0xffffu) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)(u/t1); edx=(edx&0xffff0000u)|(uint32_t)(u%t1);",
                    "idiv": f"w=(int32_t)(((edx&0xffffu)<<16)|(eax&0xffffu)); if (!t1) TRAP({at},\"divide error\"); {{ int64_t q=w/(int16_t)t1; if (q!=(int16_t)q) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)(q&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((w%(int16_t)t1)&0xffff); }}",
                }[m])
            else:
                o.append({
                    "mul": "u=(eax&0xffu)*t1; eax=(eax&0xffff0000u)|(uint32_t)(u&0xffff); " + self.mul_flags("(u>>8)!=0"),
                    "imul": "w=(int8_t)eax*(int8_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(w&0xffff); " + self.mul_flags("(w!=(int8_t)w)"),
                    "div": f"u=eax&0xffffu; if (!t1 || u/t1>0xffu) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)((u%t1)<<8)|(uint32_t)(u/t1);",
                    "idiv": f"w=(int16_t)eax; if (!t1) TRAP({at},\"divide error\"); {{ int64_t q=w/(int8_t)t1; if (q!=(int8_t)q) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)(((w%(int8_t)t1)&0xff)<<8)|(uint32_t)(q&0xff); }}",
                }[m])
            return
        if m == "push":
            if ops[0].type == x86.X86_OP_IMM:
                n = 2 if i.prefix[2] == 0x66 else 4
                v = f"0x{ops[0].imm & ((1 << (8 * n)) - 1):x}u"
            else:
                n = ops[0].size
                v = self.read(ops[0])
            self.sp_move(-n)
            o.append(f"t1={v}; esp-={n}; {self.sp_acc(0, n)} st(c,esp,t1,{n});")
            return
        if m == "pop":
            n = ops[0].size
            o.append(f"{self.sp_acc(0, n)} t1=ld(c,esp,{n}); esp+={n};")
            self.sp_move(n)
            self.mem_dst(ops[0])
            o.append(self.write(ops[0], "t1"))
            return
        if m == "pushal":
            self.sp_move(-32)
            o.append(f"t1=esp; esp-=32; {self.sp_acc(0, 32)} " +
                     " ".join(f"st(c,esp+{28 - 4 * k},{r if r != 'esp' else 't1'},4);" for k, r in enumerate(REG32)))
            return
        if m == "popal":
            o.append(f"{self.sp_acc(0, 32)} " +
                     " ".join(f"{r}=ld(c,esp+{28 - 4 * k},4);" for k, r in enumerate(REG32) if r != "esp") + " esp+=32;")
            self.sp_move(32)
            return
        if m == "pushfd":
            self.sp_move(-4)
            o.append(f"t1=(uint32_t)cf|2u|((uint32_t)pf<<2)|((uint32_t)af<<4)|((uint32_t)zf<<6)|((uint32_t)sf<<7)|0x200u|((uint32_t)df<<10)|((uint32_t)of<<11)|c->eflx; "
                     f"esp-=4; {self.sp_acc(0, 4)} st(c,esp,t1,4);")
            return
        if m == "popfd":
            o.append(f"{self.sp_acc(0, 4)} t1=ld(c,esp,4); esp+=4; " +
                     self.flag_assign(cf="t1&1", pf="(t1>>2)&1", af="(t1>>4)&1", zf="(t1>>6)&1",
                                      sf="(t1>>7)&1", of="(t1>>11)&1") + "df=(t1>>10)&1; c->eflx=t1&0x240000u;")
            self.sp_move(4)
            return
        if m == "lahf":
            o.append("eax=(eax&0xffff00ffu)|(((uint32_t)sf<<7|(uint32_t)zf<<6|(uint32_t)af<<4|(uint32_t)pf<<2|2u|(uint32_t)cf)<<8);")
            return
        if m == "sahf":
            o.append("t1=(eax>>8)&0xffu; " +
                     self.flag_assign(cf="t1&1", pf="(t1>>2)&1", af="(t1>>4)&1", zf="(t1>>6)&1", sf="(t1>>7)&1"))
            return
        if m in ("clc", "stc", "cmc", "cld", "std"):
            if m in ("cld", "std"):
                o.append("df=1;" if m == "std" else "df=0;")
            else:
                o.append(self.flag_assign(cf={"clc": "0", "stc": "1", "cmc": "!cf"}[m]))
            return
        if m == "leave":
            o.append(f"esp=ebp; CHK(esp,4,{self.at()}); ebp=ld(c,esp,4); esp+=4;")
            return
        if m == "enter":
            if ops[1].imm != 0:
                raise Unsupported("enter nested")
            o.append(f"esp-=4; CHK(esp,4,{self.at()}); st(c,esp,ebp,4); ebp=esp; esp-=0x{ops[0].imm:x}u;")
            return
        if m == "xchg":
            a = self.read(ops[0])
            o.append(f"t1={a};")
            b = self.read(ops[1])
            o.append(f"t2={b};")
            o.append(self.write(ops[1], "t1"))
            o.append(self.write(ops[0], "t2"))
            return
        if m == "xadd":
            b = self.read(ops[1])
            o.append(f"t2={b};")
            a = self.read(ops[0])
            o.append(f"t1={a}; " + self.arith("add", M, S))
            o.append(self.write(ops[1], "t1"))
            o.append(self.write(ops[0], "res"))
            return
        if m == "bswap":
            r = self.r32(ops[0].reg)
            o.append(f"{r}=__builtin_bswap32({r});")
            return
        if m in ("cdq", "cwde", "cbw", "cwd"):
            o.append({"cdq": "edx=(uint32_t)((int32_t)eax>>31);",
                      "cwde": "eax=(uint32_t)(int32_t)(int16_t)(eax&0xffffu);",
                      "cbw": "eax=(eax&0xffff0000u)|((uint32_t)(int16_t)(int8_t)(eax&0xffu)&0xffffu);",
                      "cwd": "edx=(edx&0xffff0000u)|(((int16_t)eax<0)?0xffffu:0u);"}[m])
            return
        if m == "xlatb":
            o.append(f"ea=ebx+(eax&0xffu); CHK(ea,1,{self.at()}); eax=(eax&0xffffff00u)|ld(c,ea,1);")
            return
        if m.startswith("set") and m[3:] in COND:
            self.mem_dst(ops[0])
            o.append(self.write(ops[0], f"({COND[m[3:]]})?1u:0u"))
            return
        if m == "rdtsc":
            o.append("u=rn_rdtsc(c); eax=(uint32_t)u; edx=(uint32_t)(u>>32);")
            return
        if m == "cpuid":
            o.append("rn_cpuid(c,&eax,&ebx,&ecx,&edx);")
            return
        if m == "ret":
            imm = ops[0].imm if ops else 0
            o.append(f"{self.sp_acc(0, 4)} c->ret=ld(c,esp,4); esp+=4+{imm}; goto done;")
            return
        if m == "call":
            op = ops[0]
            nxt = i.address + i.size
            if op.type == x86.X86_OP_IMM:
                if op.imm == nxt:          # call $+5: pushes its own address
                    self.sp_move(-4)
                    o.append(f"esp-=4; {self.sp_acc(0, 4)} st(c,esp,0x{nxt:x}u,4);")
                else:
                    self.call_to(f"0x{op.imm:x}u", op.imm)
                return
            o.append(f"t1={self.read(op)};")
            self.call_to("t1")
            return
        if m == "jmp":
            op = ops[0]
            if op.type == x86.X86_OP_IMM:
                o.append(self.jump(op.imm))
                return
            o.append(f"t1={self.read(op)};")
            # Any address-taken label of this function can be the target, not only the table we bounded:
            # the targets of all its tables (they may sit in .text) and code pointers in data.
            cases = self.all_cases
            if cases:
                o.append("switch (t1) { " + " ".join(f"case 0x{t:x}u: {self.jump(t)}" for t in sorted(set(cases))) + " }")
            o.append(self.tail("t1"))
            return
        if m in ("loop", "loope", "loopne", "jecxz"):
            t = ops[0].imm
            cond = {"loop": "ecx", "loope": "ecx&&zf", "loopne": "ecx&&!zf", "jecxz": "!ecx"}[m]
            if m != "jecxz":
                o.append("ecx--;")
            o.append(self.jump(t, cond))
            return
        if m.startswith("j") and m[1:] in COND:
            o.append(self.jump(ops[0].imm, COND[m[1:]]))
            return
        raise Unsupported(f"{m}")

    def string(self, i, pre, kind, n):
        o = self.out
        at = self.at()
        d = f"(df?-{n}:{n})"
        M = (1 << (8 * n)) - 1
        S = 1 << (8 * n - 1)
        acc = {1: "(eax&0xffu)", 2: "(eax&0xffffu)", 4: "eax"}[n]
        wacc = {1: "eax=(eax&0xffffff00u)|t1;", 2: "eax=(eax&0xffff0000u)|t1;", 4: "eax=t1;"}[n]
        if kind == "movs":
            step = f"CHK(esi,{n},{at}); CHK(edi,{n},{at}); st(c,edi,ld(c,esi,{n}),{n}); esi+={d}; edi+={d};"
        elif kind == "stos":
            step = f"CHK(edi,{n},{at}); st(c,edi,eax,{n}); edi+={d};"
        elif kind == "lods":
            step = f"CHK(esi,{n},{at}); t1=ld(c,esi,{n}); {wacc} esi+={d};"
        elif kind == "cmps":
            step = f"CHK(esi,{n},{at}); CHK(edi,{n},{at}); t1=ld(c,esi,{n}); t2=ld(c,edi,{n}); esi+={d}; edi+={d}; " + self.arith("cmp", M, S, repeat=bool(pre))
        else:
            step = f"CHK(edi,{n},{at}); t1={acc}; t2=ld(c,edi,{n}); edi+={d}; " + self.arith("cmp", M, S, repeat=bool(pre))
        if not pre:
            o.append(step)
        elif kind in ("movs", "stos", "lods"):
            if kind == "movs" and n == 4:   # bulk path for the common forward copy that does not overlap
                o.append(f"if (!df && ecx && esi>=LOW && edi>=LOW && esi<=c->memsz && edi<=c->memsz "
                         f"&& (uint64_t)ecx*4<=c->memsz-esi && (uint64_t)ecx*4<=c->memsz-edi "
                         f"&& (edi+ecx*4<=esi || esi+ecx*4<=edi)) {{ memcpy(c->mem+edi,c->mem+esi,ecx*4); esi+=ecx*4; edi+=ecx*4; ecx=0; }}")
            o.append(f"while (ecx) {{ {step} ecx--; }}")
        else:
            stop = "if (!zf) break;" if pre == "repe" else "if (zf) break;"
            o.append(f"while (ecx) {{ {step} ecx--; {stop} }}")

    # --- MMX (host/cpu.c reports it; the SSE forms of these mnemonics stay traps) ----------------------
    MX_ARITH = {"paddb": ("MX_ADD", 8), "paddw": ("MX_ADD", 16), "paddd": ("MX_ADD", 32), "paddsb": ("MX_ADDS", 8),
                "paddsw": ("MX_ADDS", 16), "paddusb": ("MX_ADDUS", 8), "paddusw": ("MX_ADDUS", 16), "psubb": ("MX_SUB", 8),
                "psubw": ("MX_SUB", 16), "psubd": ("MX_SUB", 32), "psubsb": ("MX_SUBS", 8), "psubsw": ("MX_SUBS", 16),
                "psubusb": ("MX_SUBUS", 8), "psubusw": ("MX_SUBUS", 16), "pcmpeqb": ("MX_CMPEQ", 8), "pcmpeqw": ("MX_CMPEQ", 16),
                "pcmpeqd": ("MX_CMPEQ", 32), "pcmpgtb": ("MX_CMPGT", 8), "pcmpgtw": ("MX_CMPGT", 16), "pcmpgtd": ("MX_CMPGT", 32),
                "pmullw": ("MX_MULL", 16), "pmulhw": ("MX_MULH", 16)}
    MX_SHIFT = {"psllw": (16, 0), "pslld": (32, 0), "psllq": (64, 0), "psrlw": (16, 1), "psrld": (32, 1), "psrlq": (64, 1),
                "psraw": (16, 2), "psrad": (32, 2)}
    MX_LOGIC = {"pand": "{d}&{s}", "pandn": "~{d}&{s}", "por": "{d}|{s}", "pxor": "{d}^{s}"}

    def mx(self, op):
        """An MMX source as a uint64_t expression: mm register, or memory of the operand's size (4 or 8 bytes)."""
        if op.type == x86.X86_OP_REG:
            n = self.i.reg_name(op.reg)
            if not n.startswith("mm"):
                raise Unsupported(f"reg {n}")
            return f"c->mm[{n[2]}]"
        if op.type == x86.X86_OP_IMM:
            return f"0x{op.imm & 0xff:x}ull"
        if op.size not in (4, 8):
            raise Unsupported(f"{op.size}-byte operand")
        self.out.append(f"ea={self.ea(op.mem)}; CHK(ea,{op.size},{self.at()});")
        return "ld64(c,ea)" if op.size == 8 else "(uint64_t)ld(c,ea,4)"

    def mmx(self, i, m):
        o, ops = self.out, i.operands
        if m == "emms":
            o.append("c->ftag=0;")
            return
        d = ops[0]
        dn = i.reg_name(d.reg) if d.type == x86.X86_OP_REG else None
        if m in ("movd", "movq") and (d.type == x86.X86_OP_MEM or dn in REG32):
            s = self.mx(ops[1])
            if d.type == x86.X86_OP_MEM:
                self.out.append(f"ea={self.ea(d.mem)}; CHK(ea,{d.size},{self.at()});")
                o.append(f"MMX_ENTER(); " + (f"st64(c,ea,{s});" if m == "movq" else f"st(c,ea,(uint32_t){s},4);"))
            else:
                o.append(f"MMX_ENTER(); {dn}=(uint32_t){s};")
            return
        if dn is None or not dn.startswith("mm"):
            raise Unsupported(m)
        D = f"c->mm[{dn[2]}]"
        src = ops[1]
        if m == "movd":
            s = self.read(src) if src.type == x86.X86_OP_REG else self.mx(src)
            v = f"(uint64_t)(uint32_t)({s})"
        elif m == "movq":
            v = self.mx(src)
        elif m in self.MX_ARITH:
            f, b = self.MX_ARITH[m]
            v = f"mx_op({D},{self.mx(src)},{b},{f})"
        elif m in self.MX_SHIFT:
            b, k = self.MX_SHIFT[m]
            v = f"mx_shift({D},{self.mx(src)},{b},{k})"
        elif m in self.MX_LOGIC:
            v = "(" + self.MX_LOGIC[m].format(d=D, s=f"({self.mx(src)})") + ")"
        elif m.startswith("punpck"):
            b = {"bw": 8, "wd": 16, "dq": 32}[m[-2:]]
            v = f"mx_unpack({D},{self.mx(src)},{b},{int(m[6] == 'h')})"
        elif m in ("packsswb", "packuswb", "packssdw"):
            v = f"mx_pack({D},{self.mx(src)},{32 if m == 'packssdw' else 16},{int(m == 'packuswb')})"
        elif m == "pmaddwd":
            v = f"mx_maddwd({D},{self.mx(src)})"
        else:
            raise Unsupported(m)
        o.append(f"MMX_ENTER(); u={v}; {D}=u;")

    # --- x87, decoded from the opcode bytes (capstone's operand order is ambiguous) ---------------
    def x87(self, i):
        o = self.out
        at = self.at()
        b = list(i.opcode)
        op, modrm = b[0], i.modrm
        mod, reg, rm = modrm >> 6, (modrm >> 3) & 7, modrm & 7
        if op < 0xd8 or op > 0xdf:
            raise Unsupported(i.mnemonic)
        mem = next((x for x in i.operands if x.type == x86.X86_OP_MEM), None)
        ar = ["fset(c,0,FADD(*fr(c,0),v));", "fset(c,0,FMUL(*fr(c,0),v));", "fcom(c,*fr(c,0),v);", "fcom(c,*fr(c,0),v); fpop(c);",
              "fset(c,0,FSUB(*fr(c,0),v));", "fset(c,0,FSUB(v,*fr(c,0)));", "fset(c,0,FDIV(*fr(c,0),v));", "fset(c,0,FDIV(v,*fr(c,0)));"]
        if mod != 3:
            o.append(f"ea={self.ea(mem.mem)};")
            ck = lambda n: self.chk(mem.mem, n)
            if op in (0xd8, 0xdc):
                n = 4 if op == 0xd8 else 8
                o.append(f"{ck(n)} {{ double v={'ldfx' if n == 4 else 'lddx'}(c,ea); {ar[reg]} }}")
                return
            if op in (0xda, 0xde):
                n = 4 if op == 0xda else 2
                o.append(f"{ck(n)} {{ double v=(int{8*n}_t)ld(c,ea,{n}); {ar[reg]} }}")
                return
            if op == 0xd9:
                s = {0: f"{ck(4)} fpush(c,ldfx(c,ea));", 2: f"{ck(4)} stf(c,ea,(float)*fr(c,0));",
                     3: f"{ck(4)} stf(c,ea,(float)*fr(c,0)); fpop(c);", 5: f"{ck(2)} c->fcw=ld(c,ea,2);",
                     7: f"{ck(2)} st(c,ea,c->fcw,2);"}.get(reg)
            elif op == 0xdb:
                s = {0: f"{ck(4)} fpush(c,(int32_t)ld(c,ea,4));", 1: f"{ck(4)} st(c,ea,(uint32_t)fist(c,*fr(c,0),32,1),4); fpop(c);",
                     2: f"{ck(4)} st(c,ea,(uint32_t)fist(c,*fr(c,0),32,0),4);", 3: f"{ck(4)} st(c,ea,(uint32_t)fist(c,*fr(c,0),32,0),4); fpop(c);",
                     5: f"{ck(10)} fpush(c,ld80(c,ea));", 7: f"{ck(10)} st80(c,ea,*fr(c,0)); fpop(c);"}.get(reg)
            elif op == 0xdd:
                s = {0: f"{ck(8)} fpush(c,lddx(c,ea));", 1: f"{ck(8)} st64(c,ea,(uint64_t)fist(c,*fr(c,0),64,1)); fpop(c);",
                     2: f"{ck(8)} std_(c,ea,*fr(c,0));", 3: f"{ck(8)} std_(c,ea,*fr(c,0)); fpop(c);",
                     7: f"{ck(2)} st(c,ea,fstsw(c),2);"}.get(reg)
            else:  # 0xdf
                s = {0: f"{ck(2)} fpush(c,(int16_t)ld(c,ea,2));", 1: f"{ck(2)} st(c,ea,(uint32_t)fist(c,*fr(c,0),16,1),2); fpop(c);",
                     2: f"{ck(2)} st(c,ea,(uint32_t)fist(c,*fr(c,0),16,0),2);", 3: f"{ck(2)} st(c,ea,(uint32_t)fist(c,*fr(c,0),16,0),2); fpop(c);",
                     5: f"{ck(8)} fpush(c,(double)(int64_t)ld64(c,ea));", 7: f"{ck(8)} st64(c,ea,(uint64_t)fist(c,*fr(c,0),64,0)); fpop(c);"}.get(reg)
            if s is None:
                raise Unsupported(i.mnemonic)
            o.append(s)
            return
        k = rm
        if op == 0xd8:
            o.append(f"{{ double v=*fr(c,{k}); {ar[reg]} }}")
            return
        if op in (0xdc, 0xde):
            # dest st(i), src st(0); for 4..7 the direction is swapped relative to d8 (Intel SDM).
            if op == 0xde and reg == 3:
                if k != 1:
                    raise Unsupported(i.mnemonic)
                o.append("fcom(c,*fr(c,0),*fr(c,1)); fpop(c); fpop(c);")
                return
            ex = {0: f"FADD(*fr(c,{k}),*fr(c,0))", 1: f"FMUL(*fr(c,{k}),*fr(c,0))", 4: f"FSUB(*fr(c,0),*fr(c,{k}))",
                  5: f"FSUB(*fr(c,{k}),*fr(c,0))", 6: f"FDIV(*fr(c,0),*fr(c,{k}))", 7: f"FDIV(*fr(c,{k}),*fr(c,0))"}.get(reg)
            if ex is None:
                if reg in (2, 3) and op == 0xdc:
                    o.append(f"fcom(c,*fr(c,0),*fr(c,{k}));" + (" fpop(c);" if reg == 3 else ""))
                    return
                raise Unsupported(i.mnemonic)
            o.append(f"fset(c,{k},{ex});" + (" fpop(c);" if op == 0xde else ""))
            return
        if op == 0xd9:
            if reg == 0:
                o.append(f"{{ double v=*fr(c,{k}); fpush(c,v); }}")
                return
            if reg == 1:
                o.append(f"{{ double v=*fr(c,0); *fr(c,0)=*fr(c,{k}); *fr(c,{k})=v; }}")
                return
            x = modrm
            if x in FPU_CONST:
                o.append(f"fpush(c,{FPU_CONST[x]});")
                return
            s = {0xd0: "", 0xe0: "*fr(c,0)=-*fr(c,0);", 0xe1: "*fr(c,0)=fabs(*fr(c,0));", 0xe4: "fcom(c,*fr(c,0),0.0);",
                 0xe5: "fxam(c);", 0xf0: "fset(c,0,fx1(c,*fr(c,0),exp2(*fr(c,0))-1.0));", 0xf1: "if (*fr(c,0)==0 && *fr(c,1)==*fr(c,1) && *fr(c,1)!=0) c->fsw|=FZE; fset(c,1,fx2(c,*fr(c,0),*fr(c,1),*fr(c,1)*log2(*fr(c,0)))); fpop(c);",
                 0xf2: "if (fabs(*fr(c,0))>=9223372036854775808.0) c->fsw|=FC2; else { fset(c,0,fx1(c,*fr(c,0),tan(*fr(c,0)))); fpush(c,1.0); c->fsw&=~FC2; }",
                 0xf3: "fset(c,1,fx2(c,*fr(c,1),*fr(c,0),atan2(*fr(c,1),*fr(c,0)))); fpop(c);",
                 0xf8: "fprem(c,0);",
                 0xf5: "fprem(c,1);",
                 0xf7: "c->ftop=(c->ftop+1)&7;", 0xf6: "c->ftop=(c->ftop-1)&7;",
                 0xf9: "fset(c,1,fx2(c,*fr(c,0),*fr(c,1),*fr(c,1)*log2(*fr(c,0)+1.0))); fpop(c);",
                 0xfa: "fset(c,0,fx1(c,*fr(c,0),sqrt(*fr(c,0))));",
                 0xfb: "if (fabs(*fr(c,0))>=9223372036854775808.0) c->fsw|=FC2; else { double v=*fr(c,0); fset(c,0,fx1(c,v,sin(v))); fpush(c,fx1(c,v,cos(v))); c->fsw&=~FC2; }",
                 0xfc: "fset(c,0,fx1(c,*fr(c,0),frnd(c,*fr(c,0))));", 0xfd: "fset(c,0,fx2(c,*fr(c,0),*fr(c,1),ldexp(*fr(c,0),(int)trunc(*fr(c,1)))));",
                 0xfe: "if (fabs(*fr(c,0))>=9223372036854775808.0) c->fsw|=FC2; else { fset(c,0,fx1(c,*fr(c,0),sin(*fr(c,0)))); c->fsw&=~FC2; }", 0xff: "if (fabs(*fr(c,0))>=9223372036854775808.0) c->fsw|=FC2; else { fset(c,0,fx1(c,*fr(c,0),cos(*fr(c,0)))); c->fsw&=~FC2; }"}.get(x)
            if s is None:
                raise Unsupported(i.mnemonic)
            o.append(s)
            return
        if op == 0xdd:
            s = {0: f"ffree(c,{k});", 2: f"*fr(c,{k})=*fr(c,0);", 3: f"*fr(c,{k})=*fr(c,0); fpop(c);",
                 4: f"fucom(c,*fr(c,0),*fr(c,{k}));", 5: f"fucom(c,*fr(c,0),*fr(c,{k})); fpop(c);"}.get(reg)
            if s is None:
                raise Unsupported(i.mnemonic)
            o.append(s)
            return
        if op == 0xda and modrm == 0xe9:
            o.append("fucom(c,*fr(c,0),*fr(c,1)); fpop(c); fpop(c);")
            return
        if op == 0xdb and modrm in (0xe2, 0xe3):
            o.append("c->fsw&=~0x80ffu;" if modrm == 0xe2 else "finit(c);")
            return
        if op == 0xdb and reg in (5, 6) or op == 0xdf and reg in (5, 6):    # fucomi/fcomi(p): ZF PF CF
            if self.live_flags & (ZF | PF | CF):
                ordered = self.flag_assign(zf="a==v", cf="a<v", pf=0)
                unordered = self.flag_assign(zf=1, pf=1, cf=1)
                o.append(f"{{ double a=*fr(c,0), v=*fr(c,{k}); if (a!=a||v!=v) {{ {unordered}}} else {{ {ordered}}} }}")
            o.append(self.flag_assign(of=0, sf=0))
            if op == 0xdf:
                o.append("fpop(c);")
            return
        if op == 0xdf and modrm == 0xe0:
            o.append("eax=(eax&0xffff0000u)|fstsw(c);")
            return
        raise Unsupported(i.mnemonic)

    # --- x87 runs: the register stack in C locals ---------------------------
    # Inside a run of x87 instructions with no jump, call or jump target between them, the stack depth relative to
    # the run's start is known at every instruction, so st(i) is a C local (fq<rel+8>, rel = slot relative to the
    # start TOP ft0) that clang keeps in a register. c->st/ftop/ftag are written back (flush) before anything that
    # can see them: a jump target, a branch, a call, a non-run x87 or MMX instruction, a memory fault or trap.
    # Same results as the per-instruction helpers: a push onto a tagged slot still loads the indefinite and sets
    # IE/SF/C1, empty slots still hold the indefinite (rt.h fpush/fpop).
    X87_REWRITE = re.compile(r"\*fr\(c,(\d)\)\s*=(?!=)|\*fr\(c,(\d)\)|fset\(c,(\d),|fpush\(c,|fpop\(c\);|ffree\(c,(\d)\);|fstsw\(c\)")

    def fs_start(self):
        self.fs = {"d": 0, "slot": {}, "lo": 0, "hi": 0}
        self.uses_fs = True
        return "ft0=c->ftop;"

    def fs_flush(self):
        """C that writes the run back to the Ctx (the run stays usable: the state it describes is now in memory)."""
        fs = self.fs
        if not fs:
            return ""
        out, setm, clrm = [], 0, 0
        for r, sl in sorted(fs["slot"].items()):
            if sl["dirty"]:
                out.append(f"c->st[(ft0+({r}))&7]=fq{r + 8};")
            if sl["tag"] == "set":
                setm |= 1 << (r & 7)
            elif sl["tag"] == "clear":
                clrm |= 1 << (r & 7)
        if setm or clrm:
            out.append(f"c->ftag=(c->ftag|frot(0x{setm:x}u,ft0))&~frot(0x{clrm:x}u,ft0);")
        if fs["d"]:
            out.append(f"c->ftop=(ft0-({fs['d']}))&7;")
        return " ".join(out)

    def fs_end(self):
        t = self.fs_flush()
        self.fs = None
        return t

    def fs_slot(self, rel, loads, write=False):
        """The local of slot rel; a slot the run has not touched is loaded from c->st first."""
        fs = self.fs
        fs["lo"], fs["hi"] = min(fs["lo"], rel), max(fs["hi"], rel)
        if fs["hi"] - fs["lo"] > 7:     # rel and rel+8 are one register: leave this to a new run
            raise Unsupported("x87 run window")
        sl = fs["slot"].get(rel)
        if sl is None:
            sl = fs["slot"][rel] = {"dirty": False, "tag": "orig"}
            loads.append(f"fq{rel + 8}=c->st[(ft0+({rel}))&7];")
        if write:
            sl["dirty"] = True
        return f"fq{rel + 8}"

    def fs_xform(self, text, loads):
        """Rewrite one x87 template (x87()) from c->st helpers to the run's locals, left to right."""
        out, pos = [], 0
        while True:
            m = self.X87_REWRITE.search(text, pos)
            if not m:
                out.append(text[pos:])
                return "".join(out)
            out.append(text[pos:m.start()])
            pos = m.end()
            g, d = m.group(0), self.fs["d"]
            if m.group(1) is not None:          # *fr(c,k)= : a plain store to st(k)
                out.append(self.fs_slot(int(m.group(1)) - d, loads, True) + "=")
            elif m.group(2) is not None:        # *fr(c,k) : a read of st(k)
                out.append(self.fs_slot(int(m.group(2)) - d, loads))
            elif m.group(3) is not None:        # fset(c,k,E) : st(k) = fround(E); the ")" of fset closes fround
                out.append(self.fs_slot(int(m.group(3)) - d, loads, True) + "=fround(c,")
            elif g.startswith("fpush"):
                depth, k = 1, pos
                while depth:
                    depth += {"(": 1, ")": -1}.get(text[k], 0)
                    k += 1
                expr = self.fs_xform(text[pos:k - 1], loads)
                pos = k + (text[k:k + 1] == ";")
                rel = -(d + 1)
                if rel < self.fs["lo"] and rel + 8 <= self.fs["hi"]:
                    raise Unsupported("x87 run window")
                had = self.fs["slot"].get(rel)
                tag = had["tag"] if had else "orig"
                if had is None:
                    self.fs["slot"][rel] = {"dirty": True, "tag": "set"}
                    self.fs["lo"] = min(self.fs["lo"], rel)
                v = f"fq{rel + 8}"
                if tag == "clear":
                    out.append(f"{v}=({expr});")
                elif tag == "set":
                    out.append(f"{{ (void)({expr}); c->fsw|=FIE|FSF|0x200u; {v}=findef(); }}")
                else:
                    out.append(f"if (c->ftag&frot(1u<<({rel}&7),ft0)) {{ c->fsw|=FIE|FSF|0x200u; {v}=findef(); }} else {v}=({expr});")
                self.fs["slot"][rel].update(dirty=True, tag="set")
                self.fs["d"] = d + 1
            elif g.startswith("fpop"):
                v = self.fs_slot(-d, loads, True)
                self.fs["slot"][-d]["tag"] = "clear"
                out.append(f"{v}=findef();")
                self.fs["d"] = d - 1
            elif g.startswith("ffree"):
                rel = int(m.group(4)) - d
                v = self.fs_slot(rel, loads, True)
                self.fs["slot"][rel]["tag"] = "clear"
                out.append(f"{v}=findef();")
            else:                               # fstsw(c): TOP is known here
                out.append(f"fstsw_t(c,(ft0-({d}))&7)")

    def fs_static(self, i):
        """The template of an x87 instruction a run can take, or None (it needs the Ctx: a barrier)."""
        save, self.out = self.out, []
        try:
            self.x87(i)
            t = " ".join(self.out)
        except (Unsupported, KeyError, IndexError):
            return None
        finally:
            self.out = save
        if any(x in t for x in ("fxam(", "fprem(", "c->ftop", "finit(", "c->ftag", "fr(c,(")):
            return None
        if ("if (" in t or "else" in t) and ("fpush" in t or "fpop" in t):
            return None     # a push or pop on one branch only: the depth after it is not static
        return t

    def x87_run(self, tpl):
        """Emit one x87 instruction inside a run (a new run when none is open or its 8-slot window is full)."""
        import copy
        for attempt in (0, 1):
            pre = []
            if self.fs is None:
                pre.append(self.fs_start())
            keep, loads = copy.deepcopy(self.fs), []
            self.fs_pre = self.fs_flush()     # the state a fault in this instruction leaves (before its effect)
            try:
                body = self.fs_xform(tpl, loads)
            except Unsupported:
                self.fs = keep
                if attempt:
                    raise
                self.out.append(self.fs_end())
                continue
            self.out.append(" ".join(pre + loads + [body]))
            return

    def fs_barrier(self, i):
        pre, m = self.mnem(i)
        if i.group(CS_GRP_JUMP) or i.group(CS_GRP_CALL) or i.group(CS_GRP_RET):
            return True
        if m in ("hlt", "int3", "ud2", "iretd", "retf", "int", "int1", "into", "loop", "loope", "loopne", "jecxz", "jcxz"):
            return True
        if m == "emms" or m == "femms" or any(x.type == x86.X86_OP_REG and i.reg_name(x.reg).startswith("mm") for x in i.operands):
            return True
        return False

    TRAP_RE = re.compile(r'CHK\(([^,()]+),(\d+),(0x[0-9a-f]+)\);?|TRAP\((0x[0-9a-f]+),("(?:[^"\\]|\\.)*")\);?')

    def fs_traps(self, lines, flush):
        """In a run, a memory fault or trap leaves through the flush, so the Ctx shows the x87 state at the fault."""
        if not flush:
            return lines
        def sub(m):
            if m.group(1) is not None:
                return (f"if ((uint32_t)(({m.group(1)})-LOW)>c->memsz-LOW-({m.group(2)})) {{ {flush} c->halt_at=({m.group(3)}); "
                        f"c->why=\"memory fault\"; goto trap; }}")
            return f"{{ {flush} c->halt_at=({m.group(4)}); c->why=({m.group(5)}); goto trap; }}"
        return [self.TRAP_RE.sub(sub, l) for l in lines]

    # --- whole function ---------------------------------------------------
    def lift(self, entry, lifted=None):
        """C source for one function. `lifted` = set of entries that exist as C functions."""
        self.lifted = lifted if lifted is not None else {entry}
        body, self.switches, bad = self.body(entry)
        targets = {entry}
        for a, i in body.items():
            # loop/loope/loopne are not CS_GRP_JUMP in capstone; an overlapping decode stream is entered by `goto L<nxt>`.
            if (i.group(CS_GRP_JUMP) or self.mnem(i)[1] in ("loop", "loope", "loopne")) and i.operands and i.operands[0].type == x86.X86_OP_IMM:
                targets.add(i.operands[0].imm)
            targets.update(self.switches.get(a, []))
        self.labels = set(body) | bad
        self.all_cases = self.case_labels(self.switches, self.labels)
        self.strict_flags = self.trace or os.environ.get("RN_STRICT_FLAGS") == "1" or self.flag_abi is None
        self.live_flags = self.return_flags = STATUS
        entry_flags, live_out = STATUS, {}
        if not self.strict_flags:
            graph = self.flag_graph(entry, body, self.switches, bad)
            live = self.flag_abi.liveness(entry, graph)
            entry_flags = live.get(entry, 0)
            self.return_flags = self.flag_abi.returns(entry)
            live_out = {a: self.flag_abi.successors(live, succ) for a, (_, _, succ, _, _) in graph.items()}
        self.info = {"calls": 0, "traps": [], "x87": 0}
        self.out = []
        order = sorted(self.labels)
        next_label = dict(zip(order, order[1:]))
        # RN_X87RUN=1: x87 runs (stack slots in locals). Opt-in: difftest-clean, but at load 11 they cut f_5d6f5d 4.7 -> 3.1 %
        # of the game thread, fx2 and the culling functions not at all, for +3.3 MB of wasm (build/bench/b4_x87.prof.txt).
        runs = not self.trace and os.environ.get("RN_X87RUN") == "1"
        # esp check coalescing (sp_open): not in a trace build (exact state per step) nor with x87 runs (fs_traps flushes
        # the run only at checks inside the instruction it rewrites).
        coal = not self.trace and not runs
        self.fs, self.uses_fs, self.sp = None, False, None
        entered = targets | self.all_cases       # labels a jump can reach: the run state must be in the Ctx there
        entered |= {a + i.size for a, i in body.items() if a + i.size in self.labels and next_label.get(a) != a + i.size}
        for a in order:
            i = body.get(a)
            if self.fs and a in entered:
                self.out.append(self.fs_end())
            if a in entered:
                self.sp_close()
            self.out.append(f"L{a:x}:;")
            if self.trace:      # difftest RN_ONLY: report the state before every instruction
                self.out.append(f"{{ {self.save()} rn_trace_step(c,0x{a:x}u); }}")
            if i is None:
                self.sp_close()
                self.out.append(self.fs_end() + f"TRAP(0x{a:x},\"cannot decode\");")
                self.info["traps"].append("decode")
                continue
            self.i = i
            if not self.strict_flags:
                self.live_flags = live_out[a]
            tpl = self.fs_static(i) if runs and 0xd8 <= i.opcode[0] <= 0xdf else None
            if self.fs and (self.fs_barrier(i) or (0xd8 <= i.opcode[0] <= 0xdf and tpl is None)):
                self.out.append(self.fs_end())
            flush = self.fs_flush()
            pre, m = self.mnem(i)
            # Ends the block before it: esp set to a value the lifter does not know (mov/lea/and esp, leave, pop esp...).
            _, wr = i.regs_access()
            sp_ok = coal and x86.X86_REG_SP not in wr and (x86.X86_REG_ESP not in wr or m in SP_MOVES and not (
                m == "pop" and i.operands[0].type == x86.X86_OP_REG and i.reg_name(i.operands[0].reg) == "esp") and not (
                m in ("add", "sub") and i.operands[1].type != x86.X86_OP_IMM))
            if not sp_ok:
                self.sp_close()
            elif self.sp is None:
                self.sp_open()
            sp_keep = dict(self.sp) if self.sp else None
            mark = len(self.out)
            try:
                if tpl is not None:
                    self.x87_run(tpl)
                    flush = self.fs_pre
                else:
                    self.emit(i)
            except (Unsupported, KeyError, IndexError) as x:
                del self.out[mark:]
                self.sp = sp_keep
                self.sp_close()
                name = (i.mnemonic + " " + i.op_str).strip().replace('"', "'")
                self.out.append(f"TRAP(0x{a:x},\"not lifted: {name}\");")
                self.info["traps"].append(str(x) if isinstance(x, Unsupported) else i.mnemonic)
            if self.fs:
                self.out[mark:] = self.fs_traps(self.out[mark:], flush)
            if i.group(CS_GRP_CALL):
                self.info["calls"] += 1
            nxt = a + i.size
            ends = i.group(CS_GRP_RET) or m == "jmp" or m in STOPS
            # A branch, call, ret, loop or trap ends the block: the check must not cover a path not taken.
            if not sp_ok or self.fs_barrier(i) or m in ("leave", "enter"):
                self.sp_close()
            if not ends and nxt not in self.labels:
                self.out.append(self.fs_end() + f"TRAP(0x{nxt:x},\"ran off the decoded body\");")
            elif not ends and next_label.get(a) != nxt:
                self.out.append(self.fs_end() + f"goto L{nxt:x};")     # an overlapping decode stream starts in between
            if not ends and next_label.get(a) != nxt or nxt not in self.labels:
                self.sp_close()
        self.sp_close()
        if self.fs:
            self.out.append(self.fs_end())
        regs = " ".join(f"uint32_t {r}=c->r[{k}];" for k, r in enumerate(REG32))
        entry_fields = set(self.ctx_flags(entry_flags))
        flags = " ".join(f"int {f}=c->{f};" if f in entry_fields else f"int {f};" for f in FLAGS)
        # restrict: guest memory (c->mem) never overlaps the Ctx, so a guest store does not make the compiler reload
        # c->mem, c->memsz, c->ftop and c->st[] (with -fno-strict-aliasing any byte store could alias them).
        if self.uses_fs:
            flags += " uint32_t ft0=0; double " + ",".join(f"fq{k}=0" for k in range(16)) + ";"
        nat = entry in NATIVE and not self.trace
        src = (f"{f'static void f_{entry:x}_lift' if nat else f'void f_{entry:x}'}(Ctx *restrict c) {{\n{regs} {flags}\n"
                "uint32_t ea=0,t1=0,t2=0,res=0,n=0,k=0; uint64_t u=0; int64_t w=0;\n"
                "(void)ea;(void)t1;(void)t2;(void)res;(void)n;(void)k;(void)u;(void)w;\n"
                # RN_COV build (build.py sets `cov`): one byte store per function ENTRY, direct calls and tail jumps included.
                + (f"RN_COV(RNI_{entry:x});\n" if getattr(self, "cov", False) else "") +
                f"goto L{entry:x};\n" + "\n".join(x for x in self.out if x) +
                f"\ndone: {self.save(self.return_flags)} return;\n"
                f"trap: c->halt=1; {self.save(STATUS if self.strict_flags else 0)} return;\n}}\n")
        if nat:     # NATIVE: the native body first, the lifted one outside its fast case
            src += f'#include "native.h"\nvoid f_{entry:x}(Ctx *restrict c) {{ if (!nat_{entry:x}(c)) f_{entry:x}_lift(c); }}\n'
        return src
