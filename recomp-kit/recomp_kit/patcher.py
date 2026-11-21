"""Byte-verified binary patch engine (Principle 1: Fail-Loud)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Patch:
    addr: int
    old: bytes
    new: bytes
    why: str = ""
    entry: bool = False
    entries: tuple[int, ...] = ()
    enabled: bool = True


@dataclass
class PatchSet:
    patches: list[Patch] = field(default_factory=list)
    code_area: tuple[int, int] = (0, 0)

    def active(self) -> list[Patch]:
        return [p for p in self.patches if p.enabled]

    def extra_entries(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for p in self.active():
            if p.entry:
                out[p.addr] = "call"
            for a in p.entries:
                out[a] = "call"
        return out

    def apply(self, img: bytearray, base: int) -> None:
        """Apply every active patch after verifying original bytes match exactly."""
        for p in self.active():
            o = p.addr - base
            if o < 0:
                raise ValueError(f"PATCH {p.addr:#x}: below image base {base:#x}")
            if o >= len(img):
                if p.old.strip(b"\0"):
                    raise ValueError(f"PATCH {p.addr:#x}: .bss starts as zero")
                continue
            if len(p.old) != len(p.new):
                raise ValueError(f"PATCH {p.addr:#x}: old/new length mismatch ({len(p.old)} != {len(p.new)})")
            cur = bytes(img[o : o + len(p.old)])
            if cur != p.old:
                raise ValueError(
                    f"PATCH {p.addr:#x}: original bytes mismatch (expected {p.old.hex()}, got {cur.hex()})"
                )
            img[o : o + len(p.new)] = p.new

    def c_table(self) -> str:
        """C arrays the runtime loader applies after mapping PE sections."""
        ps = self.active()
        addrs = "".join(f"0x{p.addr:x}," for p in ps) + "0"
        hexes = "".join(f'"{p.new.hex()}",' for p in ps) + "0"
        return (
            f"const uint32_t rn_patch_count = {len(ps)};\n"
            f"const uint32_t rn_patch_addr[] = {{{addrs}}};\n"
            f"const char *const rn_patch_hex[] = {{{hexes}}};\n"
        )


def load_patches(path: Path | None, code_area: tuple[int, int] = (0, 0)) -> PatchSet:
    if path is None or not path.exists():
        return PatchSet(patches=[], code_area=code_area)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    ps: list[Patch] = []
    for item in data.get("patch", []):
        addr = int(item["addr"], 0) if isinstance(item["addr"], str) else int(item["addr"])
        entries = tuple(int(a, 0) if isinstance(a, str) else int(a) for a in item.get("entries", []))
        ps.append(
            Patch(
                addr=addr,
                old=bytes.fromhex(item["old"].replace(" ", "")),
                new=bytes.fromhex(item["new"].replace(" ", "")),
                why=item.get("why", ""),
                entry=bool(item.get("entry", False)),
                entries=entries,
                enabled=bool(item.get("enabled", True)),
            )
        )
    return PatchSet(patches=ps, code_area=code_area)
