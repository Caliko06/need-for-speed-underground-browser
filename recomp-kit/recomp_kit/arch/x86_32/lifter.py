#!/usr/bin/env python3
"""Lift x86-32 functions of pc/Speed.exe to C.

Each guest function becomes `void f_<addr>(Ctx *c)` (host/rt.h). Registers and flags are C locals,
written back to the Ctx at calls and exits. Direct calls are C calls; indirect calls and jumps go
through rn_call (address -> function). An instruction the lifter does not know becomes a TRAP that
stops the game with its address and name when it runs. Nothing is guessed.
"""
import os
import re
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET
from capstone import x86
from recomp_kit.arch import UnsupportedInstruction as Unsupported
from recomp_kit.patcher import PatchSet

REG32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
LO8 = {"al": "eax", "cl": "ecx", "dl": "edx", "bl": "ebx"}
HI8 = {"ah": "eax", "ch": "ecx", "dh": "edx", "bh": "ebx"}
R16 = {"ax": "eax", "cx": "ecx", "dx": "edx", "bx": "ebx", "sp": "esp", "bp": "ebp", "si": "esi", "di": "edi"}
FLAGS = ["cf", "zf", "sf", "of", "pf", "df", "af"]

COND = {"o": "of", "no": "!of", "b": "cf", "ae": "!cf", "e": "zf", "ne": "!zf", "be": "(cf||zf)",
        "a": "(!cf&&!zf)", "s": "sf", "ns": "!sf", "l": "(sf!=of)", "ge": "(sf==of)",
        "le": "(zf||sf!=of)", "g": "(!zf&&sf==of)", "p": "pf", "np": "!pf"}
PREFIXES = ("lock ", "rep ", "repe ", "repne ", "bnd ", "notrack ")
STRING_OPS = {0xa4: "movs", 0xa5: "movs", 0xa6: "cmps", 0xa7: "cmps", 0xaa: "stos", 0xab: "stos",
              0xac: "lods", 0xad: "lods", 0xae: "scas", 0xaf: "scas"}
FPU_CONST = {0xe8: "1.0", 0xe9: "3.321928094887362347870319429489390175864831393",
             0xea: "1.442695040888963407359924681001892137426645954", 0xeb: "3.141592653589793238462643383279502884197",
             0xec: "0.301029995663981195213738894724493026768189881", 0xed: "0.693147180559945309417232121458176568075500134",
             0xee: "0.0"}

PROLOGUE = '#include "rt.h"\n'


class Lifter:
    def __init__(self, exe, funcs=None, patch_set: PatchSet | None = None,
                 native_overrides: set[int] | None = None, code_sections: list[str] | None = None):
        self.pe = pefile.PE(exe)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.img = bytearray(self.pe.get_memory_mapped_image())
        self.patch_set = patch_set or PatchSet()
        self.code_area = self.patch_set.code_area
        self.native_overrides = set(native_overrides or ())
        self.img += bytes(max(0, self.code_area[1] - self.base - len(self.img)))
        self.patch_set.apply(self.img, self.base)
        wanted = set(code_sections or [".text"])
        code_secs = [s for s in self.pe.sections if s.Name.rstrip(b"\0").decode("latin1") in wanted]
        if not code_secs:
            code_secs = [s for s in self.pe.sections if s.Characteristics & 0x20000000]
        self.t0 = min(self.base + s.VirtualAddress for s in code_secs)
        self.t1 = max(self.base + s.VirtualAddress + s.Misc_VirtualSize for s in code_secs)
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = True
        self.funcs = funcs or {}          # entry -> "call" | "data" | "entry"
        self.iat = set()
        if hasattr(self.pe, "DIRECTORY_ENTRY_IMPORT"):
            for e in self.pe.DIRECTORY_ENTRY_IMPORT:
                for i in e.imports:
                    self.iat.add(i.address)
        self._cache = {}
        self.trace = False
        # Address-taken code: dwords in the data sections that point into code (jump tables, vtables).
        self.addr_taken, self.addr_taken_aligned = set(), set()
        code_sec_objs = set(code_secs)
        for sec in self.pe.sections:
            if sec in code_sec_objs:
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
        self.addr_taken, self.addr_taken_aligned = set(), set()
        self.code_area, self.native_overrides = (0, 0), set()
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
        if not (self.t0 <= a < self.t1 or self.code_area[0] <= a < self.code_area[1]):
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
                if i.group(CS_GRP_RET) or m in ("hlt", "int3", "ud2", "iretd", "retf", "int", "int1", "into"):
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

    def addr(self, op):
        if op.size not in (1, 2, 4):
            raise Unsupported(f"{op.size}-byte operand")     # far pointers (m16:32), m64...
        self.out.append(f"ea={self.ea(op.mem)}; CHK(ea,{op.size},{self.at()});")

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

    @staticmethod
    def zsp(M, S):
        return f"zf=(res&0x{M:x}u)==0; sf=(res&0x{S:x}u)!=0; pf=par(res);"

    def arith(self, m, M, S):
        if m in ("add", "xadd"):
            return f"res=(t1+t2)&0x{M:x}u; af=((t1^t2^res)>>4)&1; cf=((uint64_t)t1+t2)>0x{M:x}u; of=((~(t1^t2))&(t1^res)&0x{S:x}u)!=0; " + self.zsp(M, S)
        if m == "adc":
            return f"res=(t1+t2+cf)&0x{M:x}u; af=((t1^t2^res)>>4)&1; cf=((uint64_t)t1+t2+cf)>0x{M:x}u; of=((~(t1^t2))&(t1^res)&0x{S:x}u)!=0; " + self.zsp(M, S)
        if m in ("sub", "cmp"):
            return f"res=(t1-t2)&0x{M:x}u; af=((t1^t2^res)>>4)&1; cf=t1<t2; of=((t1^t2)&(t1^res)&0x{S:x}u)!=0; " + self.zsp(M, S)
        if m == "sbb":
            return f"res=(t1-t2-cf)&0x{M:x}u; af=((t1^t2^res)>>4)&1; cf=(uint64_t)t1<(uint64_t)t2+cf; of=((t1^t2)&(t1^res)&0x{S:x}u)!=0; " + self.zsp(M, S)
        opc = {"and": "&", "test": "&", "or": "|", "xor": "^"}[m]
        return f"res=(t1{opc}t2)&0x{M:x}u; cf=0; of=0; af=0; " + self.zsp(M, S)

    # --- control transfer -------------------------------------------------
    def save(self):
        return " ".join(f"c->r[{k}]={r};" for k, r in enumerate(REG32)) + " " + " ".join(f"c->{f}={f};" for f in FLAGS)

    def load(self):
        return " ".join(f"{r}=c->r[{k}];" for k, r in enumerate(REG32)) + " " + " ".join(f"{f}=c->{f};" for f in FLAGS)

    def call_to(self, target_c, direct=None):
        """Call a guest/host address. target_c is a C expression already computed into t1 if indirect."""
        nxt = self.i.address + self.i.size
        o = self.out
        o.append(f"esp-=4; CHK(esp,4,{self.at()}); st(c,esp,0x{nxt:x}u,4); {self.save()}")
        o.append(f"f_{direct:x}(c);" if direct is not None else f"rn_call(c,{target_c});")
        o.append(f"{self.load()} if (c->halt) return; if (c->ret!=0x{nxt:x}u) TRAP({self.at()},\"return address changed\");")

    def tail(self, target_c, direct=None):
        call = f"f_{direct:x}(c);" if direct is not None else f"rn_call(c,{target_c});"
        return f"{{ {self.save()} {call} return; }}"

    def jump(self, t, cond=None):
        if t in self.labels:   # a backward jump closes a loop: a preemption point (rt.h PREEMPT)
            s = f"{{ PREEMPT(); goto L{t:x}; }}" if t <= self.i.address else f"goto L{t:x};"
        elif t in self.lifted:
            s = self.tail(None, t)
        else:
            s = self.tail(f"0x{t:x}u")
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
        ZSP = self.zsp(M, S)

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
            if m == "inc":
                o.append(f"res=(t1+1)&0x{M:x}u; of=res==0x{S:x}u; af=((t1^res)>>4)&1; {ZSP}")
            elif m == "dec":
                o.append(f"res=(t1-1)&0x{M:x}u; of=t1==0x{S:x}u; af=((t1^res)>>4)&1; {ZSP}")
            elif m == "neg":
                o.append(f"res=(0u-t1)&0x{M:x}u; cf=t1!=0; of=t1==0x{S:x}u; af=((t1^res)>>4)&1; {ZSP}")
            else:
                o.append(f"res=(~t1)&0x{M:x}u;")
            o.append(self.write(ops[0], "res"))
            return
        if m in ("shl", "sal", "shr", "sar", "rol", "ror", "rcl", "rcr"):
            n = self.read(ops[1]) if len(ops) > 1 else "1u"
            o.append(f"n=({n})&31u;")
            a = self.read(ops[0])
            o.append(f"t1={a};")
            bits = 8 * sz
            o.append("if (n) {")
            if m in ("shl", "sal"):
                o.append(f"res=(uint32_t)(((uint64_t)t1<<n)&0x{M:x}u); cf=n<={bits}?(int)((((uint64_t)t1)>>({bits}-n))&1):0; of=((res&0x{S:x}u)!=0)^cf; af=0; {ZSP}")
            elif m == "shr":
                o.append(f"res=(uint32_t)((uint64_t)t1>>n); cf=(int)(((uint64_t)t1>>(n-1))&1); of=(t1&0x{S:x}u)!=0; af=0; {ZSP}")
            elif m == "sar":
                o.append(f"res=(uint32_t)(((int64_t)(int{bits}_t)t1)>>n)&0x{M:x}u; cf=(int)((((int64_t)(int{bits}_t)t1)>>(n-1))&1); of=0; af=0; {ZSP}")
            elif m == "rol":
                o.append(f"k=n%{bits}; res=k?((t1<<k)|(t1>>({bits}-k)))&0x{M:x}u:t1; cf=res&1; of=((res&0x{S:x}u)!=0)^cf;")
            elif m == "ror":
                o.append(f"k=n%{bits}; res=k?((t1>>k)|(t1<<({bits}-k)))&0x{M:x}u:t1; cf=(res&0x{S:x}u)!=0; of=((res^(res<<1))&0x{S:x}u)!=0;")
            elif m == "rcl":
                o.append(f"res=t1; for (k=n%{bits + 1}; k; k--) {{ uint32_t hi=(res&0x{S:x}u)!=0; res=((res<<1)|cf)&0x{M:x}u; cf=hi; }} of=((res&0x{S:x}u)!=0)^cf;")
            else:
                o.append(f"of=((t1&0x{S:x}u)!=0)^cf; res=t1; for (k=n%{bits + 1}; k; k--) {{ uint32_t lo=res&1; res=(res>>1)|(cf?0x{S:x}u:0); cf=lo; }}")
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
                o.append(f"res=(t1<<n)|(t2>>(32-n)); cf=(t1>>(32-n))&1; of=((res^t1)&0x80000000u)!=0; {ZSP}")
            else:
                o.append(f"res=(t1>>n)|(t2<<(32-n)); cf=(t1>>(n-1))&1; of=((res^t1)&0x80000000u)!=0; {ZSP}")
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
            o.append("cf=(t1>>n)&1;")
            if m != "bt":
                expr = {"bts": "t1|(1u<<n)", "btr": "t1&~(1u<<n)", "btc": "t1^(1u<<n)"}[m]
                o.append(f"res={expr}; {dst}")
            return
        if m == "imul" and len(ops) >= 2:
            b = self.read(ops[2], sz) if len(ops) == 3 else self.read(ops[1])
            o.append(f"t2={b};")
            a = self.read(ops[1]) if len(ops) == 3 else self.read(ops[0])
            bits = 8 * sz
            o.append(f"w=(int64_t)(int{bits}_t)({a})*(int64_t)(int{bits}_t)t2; cf=of=(w!=(int64_t)(int{bits}_t)w);")
            o.append(self.write(ops[0], "(uint32_t)w"))
            return
        if m in ("mul", "imul", "div", "idiv"):
            v = self.read(ops[0])
            o.append(f"t1={v};")
            at = self.at()
            if sz == 4:
                o.append({
                    "mul": "u=(uint64_t)eax*t1; eax=(uint32_t)u; edx=(uint32_t)(u>>32); cf=of=edx!=0;",
                    "imul": "w=(int64_t)(int32_t)eax*(int32_t)t1; eax=(uint32_t)w; edx=(uint32_t)((uint64_t)w>>32); cf=of=(w!=(int64_t)(int32_t)w);",
                    "div": f"u=((uint64_t)edx<<32)|eax; if (!t1 || u/t1>0xffffffffu) TRAP({at},\"divide error\"); eax=(uint32_t)(u/t1); edx=(uint32_t)(u%t1);",
                    "idiv": f"w=(int64_t)(((uint64_t)edx<<32)|eax); if (!t1) TRAP({at},\"divide error\"); {{ int64_t q=w/(int32_t)t1; if (q!=(int32_t)q) TRAP({at},\"divide error\"); eax=(uint32_t)q; edx=(uint32_t)(w%(int32_t)t1); }}",
                }[m])
            elif sz == 2:
                o.append({
                    "mul": "u=(eax&0xffffu)*(uint64_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(u&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((u>>16)&0xffff); cf=of=(u>>16)!=0;",
                    "imul": "w=(int64_t)(int16_t)eax*(int16_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(w&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((w>>16)&0xffff); cf=of=(w!=(int16_t)w);",
                    "div": f"u=((edx&0xffffu)<<16)|(eax&0xffffu); if (!t1 || u/t1>0xffffu) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)(u/t1); edx=(edx&0xffff0000u)|(uint32_t)(u%t1);",
                    "idiv": f"w=(int32_t)(((edx&0xffffu)<<16)|(eax&0xffffu)); if (!t1) TRAP({at},\"divide error\"); {{ int64_t q=w/(int16_t)t1; if (q!=(int16_t)q) TRAP({at},\"divide error\"); eax=(eax&0xffff0000u)|(uint32_t)(q&0xffff); edx=(edx&0xffff0000u)|(uint32_t)((w%(int16_t)t1)&0xffff); }}",
                }[m])
            else:
                o.append({
                    "mul": "u=(eax&0xffu)*t1; eax=(eax&0xffff0000u)|(uint32_t)(u&0xffff); cf=of=(u>>8)!=0;",
                    "imul": "w=(int8_t)eax*(int8_t)t1; eax=(eax&0xffff0000u)|(uint32_t)(w&0xffff); cf=of=(w!=(int8_t)w);",
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
            o.append(f"t1={v}; esp-={n}; CHK(esp,{n},{self.at()}); st(c,esp,t1,{n});")
            return
        if m == "pop":
            n = ops[0].size
            o.append(f"CHK(esp,{n},{self.at()}); t1=ld(c,esp,{n}); esp+={n};")
            self.mem_dst(ops[0])
            o.append(self.write(ops[0], "t1"))
            return
        if m == "pushal":
            o.append(f"t1=esp; esp-=32; CHK(esp,32,{self.at()}); " +
                     " ".join(f"st(c,esp+{28 - 4 * k},{r if r != 'esp' else 't1'},4);" for k, r in enumerate(REG32)))
            return
        if m == "popal":
            o.append(f"CHK(esp,32,{self.at()}); " +
                     " ".join(f"{r}=ld(c,esp+{28 - 4 * k},4);" for k, r in enumerate(REG32) if r != "esp") + " esp+=32;")
            return
        if m == "pushfd":
            o.append(f"t1=(uint32_t)cf|2u|((uint32_t)pf<<2)|((uint32_t)af<<4)|((uint32_t)zf<<6)|((uint32_t)sf<<7)|0x200u|((uint32_t)df<<10)|((uint32_t)of<<11)|c->eflx; "
                     f"esp-=4; CHK(esp,4,{self.at()}); st(c,esp,t1,4);")
            return
        if m == "popfd":
            o.append(f"CHK(esp,4,{self.at()}); t1=ld(c,esp,4); esp+=4; cf=t1&1; pf=(t1>>2)&1; af=(t1>>4)&1; zf=(t1>>6)&1; sf=(t1>>7)&1; "
                     "df=(t1>>10)&1; of=(t1>>11)&1; c->eflx=t1&0x240000u;")
            return
        if m == "lahf":
            o.append("eax=(eax&0xffff00ffu)|(((uint32_t)sf<<7|(uint32_t)zf<<6|(uint32_t)af<<4|(uint32_t)pf<<2|2u|(uint32_t)cf)<<8);")
            return
        if m == "sahf":
            o.append("t1=(eax>>8)&0xffu; cf=t1&1; pf=(t1>>2)&1; af=(t1>>4)&1; zf=(t1>>6)&1; sf=(t1>>7)&1;")
            return
        if m in ("clc", "stc", "cmc", "cld", "std"):
            o.append({"clc": "cf=0;", "stc": "cf=1;", "cmc": "cf=!cf;", "cld": "df=0;", "std": "df=1;"}[m])
            return
        if m == "leave":
            o.append(f"esp=ebp; CHK(esp,4,{self.at()}); ebp=ld(c,esp,4); esp+=4;")
            return
        if m == "enter":
            if ops[1].imm != 0:
                raise Unsupported("enter nested")
            o.append(f"esp-=4; CHK(esp,4,{self.at()}); st(c,esp,ebp,4); ebp=esp; esp-=0x{ops[0].imm & 0xffff:x}u;")
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
            o.append(f"CHK(esp,4,{self.at()}); c->ret=ld(c,esp,4); esp+=4+{imm}; goto done;")
            return
        if m == "call":
            op = ops[0]
            nxt = i.address + i.size
            if op.type == x86.X86_OP_IMM:
                if op.imm == nxt:          # call $+5: pushes its own address
                    o.append(f"esp-=4; CHK(esp,4,{self.at()}); st(c,esp,0x{nxt:x}u,4);")
                elif op.imm in self.lifted:
                    self.call_to(None, op.imm)
                else:
                    self.call_to(f"0x{op.imm & 0xffffffff:x}u")
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
            step = f"CHK(esi,{n},{at}); CHK(edi,{n},{at}); t1=ld(c,esi,{n}); t2=ld(c,edi,{n}); esi+={d}; edi+={d}; " + self.arith("cmp", M, S)
        else:
            step = f"CHK(edi,{n},{at}); t1={acc}; t2=ld(c,edi,{n}); edi+={d}; " + self.arith("cmp", M, S)
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
            ck = lambda n: f"CHK(ea,{n},{at});"
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
            o.append(f"{{ double a=*fr(c,0), v=*fr(c,{k}); if (a!=a||v!=v) zf=pf=cf=1; else {{ zf=a==v; cf=a<v; pf=0; }} of=sf=0; }}" +
                     (" fpop(c);" if op == 0xdf else ""))
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
            if i.group(CS_GRP_JUMP) and i.operands and i.operands[0].type == x86.X86_OP_IMM:
                targets.add(i.operands[0].imm)
            targets.update(self.switches.get(a, []))
        self.labels = set(body) | bad
        self.all_cases = {t for tg in self.switches.values() for t in tg if t in self.labels} | (self.addr_taken & self.labels)
        self.info = {"calls": 0, "traps": [], "x87": 0}
        self.out = []
        order = sorted(self.labels)
        next_label = dict(zip(order, order[1:]))
        # RN_X87RUN=1: x87 runs (stack slots in locals). Opt-in: difftest-clean, but at load 11 they cut f_5d6f5d 4.7 -> 3.1 %
        # of the game thread, fx2 and the culling functions not at all, for +3.3 MB of wasm (build/bench/b4_x87.prof.txt).
        runs = not self.trace and os.environ.get("RN_X87RUN") == "1"
        self.fs, self.uses_fs = None, False
        entered = targets | self.all_cases       # labels a jump can reach: the run state must be in the Ctx there
        for a in order:
            i = body.get(a)
            if self.fs and a in entered:
                self.out.append(self.fs_end())
            self.out.append(f"L{a:x}:;")
            if self.trace:      # difftest RN_ONLY: report the state before every instruction
                self.out.append(f"{{ {self.save()} rn_trace_step(c,0x{a:x}u); }}")
            if i is None:
                self.out.append(self.fs_end() + f"TRAP(0x{a:x},\"cannot decode\");")
                self.info["traps"].append("decode")
                continue
            self.i = i
            tpl = self.fs_static(i) if runs and 0xd8 <= i.opcode[0] <= 0xdf else None
            if self.fs and (self.fs_barrier(i) or (0xd8 <= i.opcode[0] <= 0xdf and tpl is None)):
                self.out.append(self.fs_end())
            flush = self.fs_flush()
            mark = len(self.out)
            try:
                if tpl is not None:
                    self.x87_run(tpl)
                    flush = self.fs_pre
                else:
                    self.emit(i)
            except (Unsupported, KeyError, IndexError) as x:
                del self.out[mark:]
                name = (i.mnemonic + " " + i.op_str).strip().replace('"', "'")
                self.out.append(f"TRAP(0x{a:x},\"not lifted: {name}\");")
                self.info["traps"].append(str(x) if isinstance(x, Unsupported) else i.mnemonic)
            if self.fs:
                self.out[mark:] = self.fs_traps(self.out[mark:], flush)
            if i.group(CS_GRP_CALL):
                self.info["calls"] += 1
            nxt = a + i.size
            pre, m = self.mnem(i)
            ends = i.group(CS_GRP_RET) or m in ("jmp", "hlt", "int3", "ud2", "iretd", "retf", "int", "int1", "into")
            if not ends and nxt not in self.labels:
                self.out.append(self.fs_end() + f"TRAP(0x{nxt:x},\"ran off the decoded body\");")
            elif not ends and next_label.get(a) != nxt:
                self.out.append(self.fs_end() + f"goto L{nxt:x};")     # an overlapping decode stream starts in between
        if self.fs:
            self.out.append(self.fs_end())
        regs = " ".join(f"uint32_t {r}=c->r[{k}];" for k, r in enumerate(REG32))
        flags = " ".join(f"int {f}=c->{f};" for f in FLAGS)
        # restrict: guest memory (c->mem) never overlaps the Ctx, so a guest store does not make the compiler reload
        # c->mem, c->memsz, c->ftop and c->st[] (with -fno-strict-aliasing any byte store could alias them).
        if self.uses_fs:
            flags += " uint32_t ft0=0; double " + ",".join(f"fq{k}=0" for k in range(16)) + ";"
        nat = entry in self.native_overrides and not self.trace
        src = (f"{f'static void f_{entry:x}_lift' if nat else f'void f_{entry:x}'}(Ctx *restrict c) {{\n{regs} {flags}\n"
                "uint32_t ea=0,t1=0,t2=0,res=0,n=0,k=0; uint64_t u=0; int64_t w=0;\n"
                "(void)ea;(void)t1;(void)t2;(void)res;(void)n;(void)k;(void)u;(void)w;\n"
                # RN_COV build (build.py sets `cov`): one byte store per function ENTRY, direct calls and tail jumps included.
                + (f"RN_COV(RNI_{entry:x});\n" if getattr(self, "cov", False) else "") +
                f"goto L{entry:x};\n" + "\n".join(self.out) +
                f"\ndone: {self.save()} return;\ntrap: c->halt=1; {self.save()} return;\n}}\n")
        if nat:     # NATIVE: the native body first, the lifted one outside its fast case
            src += f'#include "native.h"\nvoid f_{entry:x}(Ctx *restrict c) {{ if (!nat_{entry:x}(c)) f_{entry:x}_lift(c); }}\n'
        return src
