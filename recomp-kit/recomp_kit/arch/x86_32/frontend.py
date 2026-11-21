"""Parameterized x86-32 PE32 recursive-descent function & block discoverer."""
from __future__ import annotations

import collections
import json
import struct
import time
from typing import Any, Callable

import pefile
from capstone import CS_ARCH_X86, CS_GRP_CALL, CS_GRP_JUMP, CS_GRP_RET, CS_MODE_32, Cs
from capstone import x86

from recomp_kit.config import ProjectConfig


def _mem_operand(ins):
    for op in ins.operands:
        if op.type == x86.X86_OP_MEM:
            return op.mem
    return None


def discover_pe32(
    cfg: ProjectConfig,
    on_progress: Callable[[str, int, int, int], None] | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    exe_path = cfg.resolve_binary()
    pe = pefile.PE(str(exe_path))
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()

    wanted = set(cfg.code_sections)
    code_secs = [s for s in pe.sections if s.Name.rstrip(b"\0").decode("latin1") in wanted]
    if not code_secs:
        # Fallback: any section marked IMAGE_SCN_MEM_EXECUTE (0x20000000)
        code_secs = [s for s in pe.sections if s.Characteristics & 0x20000000]
    if not code_secs:
        raise ValueError(f"No executable code section found in {exe_path}")

    code_ranges = [(base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize) for s in code_secs]
    t0 = min(lo for lo, _ in code_ranges)
    t1 = max(hi for _, hi in code_ranges)
    code_sec_objs = set(code_secs)
    data_secs = [s for s in pe.sections if s not in code_sec_objs]

    def in_text(a: int) -> bool:
        return any(lo <= a < hi for lo, hi in code_ranges)

    def u32(a: int) -> int:
        return struct.unpack_from("<I", img, a - base)[0]

    # Imports: IAT slot address -> "dll!name"
    iat: dict[int, str] = {}
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            dll = e.dll.decode("latin1").lower()
            for i in e.imports:
                nm = i.name.decode("latin1") if i.name else f"#{i.ordinal}"
                iat[i.address] = f"{dll}!{nm}"

    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True

    insn_at: dict[int, tuple[int, str]] = {}
    block_starts: set[int] = set()
    funcs: dict[int, str] = {}
    jump_tables: dict[int, list[int]] = {}
    indirect_jmp: list[int] = []
    indirect_call: collections.Counter[str] = collections.Counter()
    import_calls: collections.Counter[str] = collections.Counter()
    groups: collections.Counter[str] = collections.Counter()
    bad: list[int] = []

    sec_ranges = [(base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize) for s in pe.sections]

    def in_any_sec(a: int) -> bool:
        return any(lo <= a < hi for lo, hi in sec_ranges)

    def read_table(table: int) -> list[int]:
        out: list[int] = []
        a = table
        while len(out) < 4096 and in_any_sec(a) and a - base + 4 <= len(img):
            v = u32(a)
            if not in_text(v):
                break
            out.append(v)
            a += 4
        return out

    work: collections.deque[int] = collections.deque()
    imm_ptrs: set[int] = set()
    imm_seeds: list[int] = []

    def add_func(a: int, why: str) -> None:
        if in_text(a) and a not in funcs:
            funcs[a] = why
            work.append(a)

    def add_block(a: int) -> None:
        if in_text(a) and a not in block_starts:
            block_starts.add(a)
            work.append(a)

    def walk(a: int) -> None:
        steps = 0
        while in_text(a) and steps < 4096:
            steps += 1
            if a in insn_at:
                return
            off = a - base
            ins = next(md.disasm(bytes(img[off : off + 16]), a), None)
            if ins is None:
                bad.append(a)
                return
            insn_at[a] = (ins.size, ins.mnemonic)
            for g in ins.groups:
                groups[ins.group_name(g)] += 1
            nxt = a + ins.size
            m = ins.mnemonic
            if m in ("push", "mov"):
                for op_i in ins.operands:
                    if op_i.type == x86.X86_OP_IMM and op_i.size == 4:
                        v_i = op_i.imm & 0xFFFFFFFF
                        if in_text(v_i):
                            imm_ptrs.add(v_i)
                            if v_i not in funcs:
                                imm_seeds.append(v_i)
            op = ins.operands[0] if ins.operands else None
            if ins.group(CS_GRP_RET) or m in ("hlt", "ud2", "int3"):
                return
            if ins.group(CS_GRP_CALL):
                if op and op.type == x86.X86_OP_IMM:
                    add_func(op.imm & 0xFFFFFFFF, "call")
                elif op and op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp in iat:
                    name = iat[op.mem.disp]
                    import_calls[name] += 1
                    if name.endswith(("!ExitProcess", "!_exit", "!exit")):
                        return
                elif op:
                    indirect_call["reg" if op.type == x86.X86_OP_REG else "mem"] += 1
                a = nxt
                continue
            if ins.group(CS_GRP_JUMP):
                if op and op.type == x86.X86_OP_IMM:
                    tgt = op.imm & 0xFFFFFFFF
                    if m == "jmp":
                        if tgt in funcs:
                            return
                        add_block(tgt)
                        return
                    add_block(tgt)
                    add_block(nxt)
                    return
                mm = _mem_operand(ins)
                if mm is not None and mm.base == 0 and mm.index == 0 and mm.disp in iat:
                    import_calls[iat[mm.disp]] += 1
                    return
                if mm is not None and mm.index != 0 and mm.scale == 4 and mm.base == 0:
                    tgts = read_table(mm.disp & 0xFFFFFFFF)
                    jump_tables[a] = tgts
                    for t in tgts:
                        add_block(t)
                    return
                indirect_jmp.append(a)
                return
            a = nxt

    last_emit = 0.0

    def _tick(phase: str, force: bool = False) -> None:
        nonlocal last_emit
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Discovery cancelled")
        if on_progress is None:
            return
        now = time.monotonic()
        if force or (now - last_emit) >= 0.4:
            last_emit = now
            on_progress(phase, len(funcs), len(insn_at), len(work))

    def drain(phase: str) -> None:
        step = 0
        while work:
            walk(work.popleft())
            step += 1
            if (step & 63) == 0:
                _tick(phase)
        _tick(phase, force=True)

    add_func(base + pe.OPTIONAL_HEADER.AddressOfEntryPoint, "entry")
    drain("entry_calls")
    reached_before_data = sum(sz for sz, _ in insn_at.values())

    # Aligned code pointers in data sections (vtables, callbacks)
    _tick("scan_data_ptrs", force=True)
    data_ptrs: set[int] = set()
    for s in data_secs:
        raw = s.get_data()
        for o in range(0, len(raw) - 3, 4):
            v = struct.unpack_from("<I", raw, o)[0]
            if in_text(v):
                data_ptrs.add(v)
        _tick("scan_data_ptrs")
    for v in sorted(data_ptrs):
        if v not in insn_at:
            add_func(v, "data")
    drain("data_ptrs")

    # Unaligned packed tables (skip .rsrc/.reloc and skip on giant >20k-ptr binaries to keep discovery fast)
    unaligned = 0
    if len(data_ptrs) <= 20000:
        _tick("scan_unaligned", force=True)
        seen_unaligned: collections.Counter[int] = collections.Counter()
        for sec in data_secs:
            sn = sec.Name.rstrip(b"\0").decode("latin1").lower()
            if sn in (".rsrc", ".reloc", ".tls"):
                continue
            raw = sec.get_data()
            for o in range(len(raw) - 3):
                if o % 4:
                    v = struct.unpack_from("<I", raw, o)[0]
                    if in_text(v):
                        seen_unaligned[v] += 1
                if (o & 65535) == 0:
                    _tick("scan_unaligned")
        for v, n in sorted(seen_unaligned.items()):
            if v not in funcs and (v in insn_at or n >= 2):
                add_func(v, "data")
                unaligned += 1
        drain("unaligned_tables")

    # Drain immediate code pointers collected inline during walk() (zero second disassembly pass!)
    while imm_seeds:
        batch = list(imm_seeds)
        imm_seeds.clear()
        added = 0
        for v in batch:
            if v not in funcs:
                add_func(v, "data")
                added += 1
        if not added:
            break
        drain("imm_ptrs")

    starts = set(insn_at)
    mid = sum(1 for v in data_ptrs if v not in starts)
    covered = sum(sz for sz, _ in insn_at.values())
    text_bytes = sum(hi - lo for lo, hi in code_ranges)
    mn = collections.Counter(m for _, m in insn_at.values())
    fpu = sum(c for m, c in mn.items() if m.startswith("f"))
    by_dll = collections.Counter(n.split("!")[0] for n in iat.values())

    res = {
        "exe": str(exe_path),
        "image_base": hex(base),
        "text": [hex(t0), hex(t1)],
        "text_bytes": text_bytes,
        "imports": {"total": len(iat), "by_dll": dict(by_dll), "names": sorted(iat.values())},
        "functions": {
            "total": len(funcs),
            "from_entry_and_calls": sum(1 for w in funcs.values() if w != "data"),
            "from_data_pointers": sum(1 for w in funcs.values() if w == "data"),
        },
        "instructions": len(insn_at),
        "distinct_mnemonics": len(mn),
        "bytes_decoded": covered,
        "text_coverage": round(covered / max(1, text_bytes), 4),
        "bytes_decoded_before_data_seeds": reached_before_data,
        "jump_tables": {"count": len(jump_tables), "targets": sum(len(t) for t in jump_tables.values())},
        "indirect_jmp_unresolved": len(indirect_jmp),
        "indirect_call": dict(indirect_call),
        "import_call_sites": sum(import_calls.values()),
        "imports_called": len(import_calls),
        "imports_never_called": sorted(set(iat.values()) - set(import_calls)),
        "x87_instructions": fpu,
        "groups": dict(groups.most_common()),
        "decode_failures": len(bad),
        "data_pointers_into_text": len(data_ptrs),
        "data_pointers_mid_instruction": mid,
        "immediate_pointers_into_text": len(imm_ptrs),
        "unaligned_pointers_to_code": unaligned,
        "top_mnemonics": dict(mn.most_common(40)),
        "all_mnemonics": sorted(mn),
        "unresolved_jmp_sites": [hex(a) for a in indirect_jmp],
    }

    cfg.census_dir.mkdir(parents=True, exist_ok=True)
    cfg.discovery_json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    with cfg.functions_tsv.open("w", encoding="utf-8") as f:
        for a in sorted(funcs):
            f.write(f"{a:08x}\t{funcs[a]}\n")
    return res
