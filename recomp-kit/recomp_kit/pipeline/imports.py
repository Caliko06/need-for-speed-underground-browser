"""PE IAT auditor: inspect imports and recommend runtime modules before lifting."""
from __future__ import annotations

import collections
import math
from pathlib import Path
from typing import Any

import pefile

PACKER_SECTIONS = {
    ".securom": "SecuROM DRM wrapper (entry/code encrypted on disk)",
    "securom": "SecuROM DRM wrapper",
    ".safedisc": "SafeDisc DRM wrapper",
    "stxt371": "SafeDisc DRM section",
    "stxt774": "SafeDisc DRM section",
    ".upx": "UPX packer (unpack with `upx -d` first)",
    "upx0": "UPX packer (unpack with `upx -d` first)",
    "upx1": "UPX packer (unpack with `upx -d` first)",
    ".aspack": "ASPack compressor",
    ".vmp0": "VMProtect obfuscation",
    ".vmp1": "VMProtect obfuscation",
    ".themida": "Themida/WinLicense protector",
    ".enigma": "Enigma protector",
    ".denuvo": "Denuvo anti-tamper",
}

DLL_TO_MODULE = {
    "kernel32.dll": "kernel32",
    "user32.dll": "user32",
    "gdi32.dll": "gdi32",
    "advapi32.dll": "win32_misc",
    "winmm.dll": "winmm",
    "ws2_32.dll": "net",
    "wsock32.dll": "net",
    "d3d9.dll": "d3d9",
    "d3d8.dll": "d3d8",
    "ddraw.dll": "ddraw",
    "opengl32.dll": "opengl",
    "dsound.dll": "dsound",
    "dinput8.dll": "dinput8",
    "dinput.dll": "dinput",
}


def inspect_pe(binary_path: Path) -> dict[str, Any]:
    pe = pefile.PE(str(binary_path))
    machine = pe.FILE_HEADER.Machine
    arch = "x86_32" if machine == 0x14C else "x86_64" if machine == 0x8664 else f"unknown_{machine:#x}"
    fmt = "pe32" if pe.OPTIONAL_HEADER.Magic == 0x10B else "pe64" if pe.OPTIONAL_HEADER.Magic == 0x20B else "pe"

    code_secs = []
    for s in pe.sections:
        if not (s.Characteristics & 0x20000000):
            continue
        sn = s.Name.rstrip(b"\0").decode("latin1")
        sl = sn.lower()
        # Skip known DRM/packer sections and data sections marked executable
        if sl in PACKER_SECTIONS or sl.endswith("data") or sl in ("srdata", "sdata"):
            continue
        raw = s.get_data()
        if raw:
            mid = len(raw) // 2
            if _shannon_entropy(raw[mid : mid + 65536]) >= 7.25:
                continue
        code_secs.append(sn)
    if not code_secs:
        code_secs = [
            s.Name.rstrip(b"\0").decode("latin1")
            for s in pe.sections
            if s.Characteristics & 0x20000000
        ] or [".text"]

    by_dll: dict[str, list[str]] = collections.defaultdict(list)
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            dll = e.dll.decode("latin1").lower()
            for i in e.imports:
                nm = i.name.decode("latin1") if i.name else f"#{i.ordinal}"
                by_dll[dll].append(nm)

    recommended_mods: list[str] = ["files_vfs"]
    for dll in sorted(by_dll):
        m = DLL_TO_MODULE.get(dll)
        if m and m not in recommended_mods:
            recommended_mods.append(m)

    return {
        "arch": arch,
        "format": fmt,
        "image_base": hex(pe.OPTIONAL_HEADER.ImageBase),
        "entry_point": hex(pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.AddressOfEntryPoint),
        "code_sections": code_secs,
        "imports_total": sum(len(v) for v in by_dll.values()),
        "imports_by_dll": {k: len(v) for k, v in sorted(by_dll.items())},
        "recommended_modules": recommended_mods,
    }


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = collections.Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def preflight_pe(binary_path: Path) -> dict[str, Any]:
    """Fast (<1s) preflight gate catching NFSU/MaxPayne/PES hurdles before lifting."""
    from recomp_kit.re.callgraph import IMPLEMENTED_APIS

    pe = pefile.PE(str(binary_path))
    info = inspect_pe(binary_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if info["arch"] != "x86_32":
        blockers.append(f"Unsupported architecture '{info['arch']}' ({info['format']}): recomp-kit currently lifts x86-32 PE32 only.")

    ep_rva = pe.OPTIONAL_HEADER.AddressOfEntryPoint
    ep_sec = None
    sections_summary: list[dict[str, Any]] = []
    for s in pe.sections:
        sname = s.Name.rstrip(b"\0").decode("latin1")
        slower = sname.lower()
        raw = s.get_data()
        if raw:
            mid = len(raw) // 2
            ent_head = round(_shannon_entropy(raw[:65536]), 2)
            ent_mid = round(_shannon_entropy(raw[mid : mid + 65536]), 2)
            ent = min(ent_head, ent_mid)
        else:
            ent_head = ent_mid = ent = 0.0
        va_start = s.VirtualAddress
        va_end = va_start + max(s.Misc_VirtualSize, s.SizeOfRawData)
        if va_start <= ep_rva < va_end:
            ep_sec = sname
        sections_summary.append({
            "name": sname,
            "va": hex(pe.OPTIONAL_HEADER.ImageBase + va_start),
            "size": s.SizeOfRawData,
            "exec": bool(s.Characteristics & 0x20000000),
            "entropy": ent,
            "entropy_head": ent_head,
            "entropy_mid": ent_mid,
        })
        if slower in PACKER_SECTIONS:
            warnings.append(f"DRM/Packer section '{sname}' present ({PACKER_SECTIONS[slower]}); static code outside encrypted slices can still be discovered.")
        elif slower == ".text" and ent_head >= 7.25 and ent_mid >= 7.25:
            warnings.append(f"Section '.text' has high entropy across both head ({ent_head}) and mid ({ent_mid}): likely encrypted/packed on disk.")
        elif slower == ".text" and ent_head >= 7.25 and ent_mid < 7.0:
            warnings.append(f"Section '.text' has high-entropy head ({ent_head}) but normal x86 body ({ent_mid} at mid).")

    if ep_sec and ep_sec.lower() not in (".text", "code", ".code", "text"):
        warnings.append(f"Entry point {info['entry_point']} is inside section '{ep_sec}' (not .text).")

    # Audit Windows API readiness against our minimal runtime
    impl_n = 0
    total_n = 0
    missing_by_dll: dict[str, int] = collections.defaultdict(int)
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for e in pe.DIRECTORY_ENTRY_IMPORT:
            dll = e.dll.decode("latin1").lower()
            for imp in e.imports:
                nm = imp.name.decode("latin1") if imp.name else f"#{imp.ordinal}"
                total_n += 1
                if (dll, nm) in IMPLEMENTED_APIS:
                    impl_n += 1
                else:
                    missing_by_dll[dll] += 1

    heavy_missing = [(d, c) for d, c in sorted(missing_by_dll.items(), key=lambda kv: -kv[1]) if c > 0]
    if heavy_missing:
        top_str = ", ".join(f"{d}({c})" for d, c in heavy_missing[:6])
        warnings.append(f"{total_n - impl_n}/{total_n} imported Win32 APIs will use auto-stubs initially: {top_str}")

    return {
        "ok": len(blockers) == 0,
        "binary": str(binary_path),
        "size_bytes": binary_path.stat().st_size,
        "entry_section": ep_sec or "unknown",
        "info": info,
        "sections": sections_summary,
        "api_ready": {
            "implemented": impl_n,
            "total": total_n,
            "missing_dlls": heavy_missing[:10],
        },
        "blockers": blockers,
        "warnings": warnings,
    }
