"""Generate a genuine, valid 32-bit Windows PE32 executable (`hello_win32/hello.exe`)
for end-to-end live testing (Discover -> Lift -> Unicorn Verify -> Native & WASM Execution).

Layout:
  ImageBase = 0x00400000
  .text  RVA 0x1000 (file off 0x0200, size 0x0200) — 4 real x86-32 functions
  .rdata RVA 0x2000 (file off 0x0400, size 0x0200) — strings + real PE Import Directory (KERNEL32 + USER32)
"""
from __future__ import annotations

import struct
from pathlib import Path

BASE = 0x00400000
TEXT_RVA = 0x1000
RDATA_RVA = 0x2000


def _build_rdata() -> tuple[bytes, dict[str, int], int, int]:
    """Build .rdata with strings and a valid PE Import Directory for KERNEL32.dll & USER32.dll."""
    buf = bytearray(0x200)

    def put_str(off: int, s: bytes) -> int:
        buf[off : off + len(s) + 1] = s + b"\x00"
        return BASE + RDATA_RVA + off

    va_banner = put_str(0x00, b"=== Hello from a real Windows x86-32 .exe running inside WebAssembly! ===\n")
    va_done = put_str(0x50, b"x86-32 math & string loops completed cleanly via recomp-kit.\n")
    va_mb_title = put_str(0x90, b"recomp-kit Win32 Runtime")
    va_mb_text = put_str(0xB0, b"MessageBoxA() intercepted from Windows PE32 and rendered in your browser!")
    # 4-byte scratch slot for WriteFile's lpNumberOfBytesWritten
    va_written = BASE + RDATA_RVA + 0x100

    # Import Directory starts at RDATA + 0x110
    imp_off = 0x110
    imp_rva = RDATA_RVA + imp_off

    # Two IMAGE_IMPORT_DESCRIPTORs (20 bytes each) + 20-byte null terminator = 60 bytes (0x110..0x14C)
    # IATs & ILTs at 0x150..0x180
    k32_iat_off = 0x150  # 4 entries + null = 20 bytes
    u32_iat_off = 0x168  # 1 entry + null = 8 bytes

    # DLL & Hint/Name strings at 0x178..
    cur = 0x178

    def add_cstr(s: bytes) -> int:
        nonlocal cur
        rva = RDATA_RVA + cur
        buf[cur : cur + len(s) + 1] = s + b"\x00"
        cur += len(s) + 1
        if cur & 1:
            cur += 1
        return rva

    def add_hint_name(name: bytes) -> int:
        nonlocal cur
        rva = RDATA_RVA + cur
        struct.pack_into("<H", buf, cur, 0)
        cur += 2
        buf[cur : cur + len(name) + 1] = name + b"\x00"
        cur += len(name) + 1
        if cur & 1:
            cur += 1
        return rva

    k32_dll_rva = add_cstr(b"KERNEL32.dll")
    u32_dll_rva = add_cstr(b"USER32.dll")

    k32_names = [b"GetStdHandle", b"WriteFile", b"GetTickCount", b"ExitProcess"]
    u32_names = [b"MessageBoxA"]

    iat_vas: dict[str, int] = {}
    for i, nm in enumerate(k32_names):
        hn_rva = add_hint_name(nm)
        struct.pack_into("<I", buf, k32_iat_off + i * 4, hn_rva)
        iat_vas[nm.decode()] = BASE + RDATA_RVA + k32_iat_off + i * 4
    struct.pack_into("<I", buf, k32_iat_off + len(k32_names) * 4, 0)

    for i, nm in enumerate(u32_names):
        hn_rva = add_hint_name(nm)
        struct.pack_into("<I", buf, u32_iat_off + i * 4, hn_rva)
        iat_vas[nm.decode()] = BASE + RDATA_RVA + u32_iat_off + i * 4
    struct.pack_into("<I", buf, u32_iat_off + len(u32_names) * 4, 0)

    # Write IMAGE_IMPORT_DESCRIPTORs (OriginalFirstThunk=0, TimeDateStamp=0, Forwarder=0, Name, FirstThunk)
    struct.pack_into("<IIIII", buf, imp_off, 0, 0, 0, k32_dll_rva, RDATA_RVA + k32_iat_off)
    struct.pack_into("<IIIII", buf, imp_off + 20, 0, 0, 0, u32_dll_rva, RDATA_RVA + u32_iat_off)

    syms = {
        "banner": va_banner,
        "done": va_done,
        "mb_title": va_mb_title,
        "mb_text": va_mb_text,
        "written": va_written,
        **iat_vas,
    }
    return bytes(buf), syms, imp_rva, 60


def _call_rel32(from_va: int, target_va: int) -> bytes:
    rel = (target_va - (from_va + 5)) & 0xFFFFFFFF
    return b"\xE8" + struct.pack("<I", rel)


def _call_iat(iat_va: int) -> bytes:
    return b"\xFF\x15" + struct.pack("<I", iat_va)


def _push_imm32(v: int) -> bytes:
    return b"\x68" + struct.pack("<I", v & 0xFFFFFFFF)


def _build_text(syms: dict[str, int]) -> bytes:
    """Assemble 4 real x86-32 functions into .text."""
    text = bytearray(b"\xCC" * 0x200)

    # Function 2: compute_sum_squares(uint32_t n) at 0x004010A0 (cdecl)
    #   eax = 0; ecx = 1; while (ecx <= n) { edx = ecx*ecx; eax += edx; ecx++; } return eax;
    fn_sum_off = 0xA0
    fn_sum_va = BASE + TEXT_RVA + fn_sum_off
    sum_code = bytearray()
    sum_code += b"\x55\x89\xE5"              # push ebp; mov ebp, esp
    sum_code += b"\x31\xC0"                  # xor eax, eax
    sum_code += b"\xB9\x01\x00\x00\x00"      # mov ecx, 1
    loop_top = len(sum_code)
    sum_code += b"\x3B\x4D\x08"              # cmp ecx, [ebp+8]
    sum_code += b"\x77\x0A"                  # ja +10 (past loop)
    sum_code += b"\x89\xCA"                  # mov edx, ecx
    sum_code += b"\x0F\xAF\xD1"              # imul edx, ecx
    sum_code += b"\x01\xD0"                  # add eax, edx
    sum_code += b"\x41"                      # inc ecx
    back_rel = (loop_top - (len(sum_code) + 2)) & 0xFF
    sum_code += b"\xEB" + bytes([back_rel])  # jmp loop_top
    sum_code += b"\x5D\xC3"                  # pop ebp; ret
    text[fn_sum_off : fn_sum_off + len(sum_code)] = sum_code

    # Function 3: xor_mix(uint32_t x) at 0x004010D0 (cdecl)
    #   eax = x; eax ^= (eax << 13); eax ^= (eax >> 17); eax *= 0x45d9f3b; return eax;
    fn_mix_off = 0xD0
    fn_mix_va = BASE + TEXT_RVA + fn_mix_off
    mix_code = bytearray()
    mix_code += b"\x8B\x44\x24\x04"          # mov eax, [esp+4]
    mix_code += b"\x89\xC2"                  # mov edx, eax
    mix_code += b"\xC1\xE2\x0D"              # shl edx, 13
    mix_code += b"\x31\xD0"                  # xor eax, edx
    mix_code += b"\x89\xC2"                  # mov edx, eax
    mix_code += b"\xC1\xEA\x11"              # shr edx, 17
    mix_code += b"\x31\xD0"                  # xor eax, edx
    mix_code += b"\x69\xC0\x3B\x9F\x5D\x04"  # imul eax, eax, 0x045d9f3b
    mix_code += b"\xC3"                      # ret
    text[fn_mix_off : fn_mix_off + len(mix_code)] = mix_code

    # Function 4: strlen_x86(const char *s) at 0x00401100 (cdecl)
    fn_len_off = 0x100
    fn_len_va = BASE + TEXT_RVA + fn_len_off
    len_code = bytearray()
    len_code += b"\x8B\x54\x24\x04"          # mov edx, [esp+4]
    len_code += b"\x31\xC0"                  # xor eax, eax
    ltop = len(len_code)
    len_code += b"\x80\x3C\x02\x00"          # cmp byte ptr [edx+eax], 0
    len_code += b"\x74\x03"                  # je +3
    len_code += b"\x40"                      # inc eax
    lback = (ltop - (len(len_code) + 2)) & 0xFF
    len_code += b"\xEB" + bytes([lback])     # jmp ltop
    len_code += b"\xC3"                      # ret
    text[fn_len_off : fn_len_off + len(len_code)] = len_code

    # Function 1: _start at 0x00401000
    entry = bytearray()
    entry += b"\x55\x89\xE5\x53\x56"         # push ebp; mov ebp, esp; push ebx; push esi
    # 1. hOut = GetStdHandle(STD_OUTPUT_HANDLE = -11)
    entry += b"\x6A\xF5"                     # push -11
    entry += _call_iat(syms["GetStdHandle"])
    entry += b"\x89\xC3"                     # mov ebx, eax (save hOut)

    # 2. len = strlen_x86(banner)
    entry += _push_imm32(syms["banner"])
    entry += _call_rel32(BASE + TEXT_RVA + len(entry), fn_len_va)
    entry += b"\x83\xC4\x04"                 # add esp, 4

    # 3. WriteFile(hOut, banner, len, &written, NULL)
    entry += b"\x6A\x00"                     # push 0
    entry += _push_imm32(syms["written"])
    entry += b"\x50"                         # push eax (len)
    entry += _push_imm32(syms["banner"])
    entry += b"\x53"                         # push ebx (hOut)
    entry += _call_iat(syms["WriteFile"])

    # 4. sum = compute_sum_squares(10) -> 385; hash = xor_mix(sum)
    entry += b"\x6A\x0A"                     # push 10
    entry += _call_rel32(BASE + TEXT_RVA + len(entry), fn_sum_va)
    entry += b"\x83\xC4\x04"
    entry += b"\x50"                         # push eax
    entry += _call_rel32(BASE + TEXT_RVA + len(entry), fn_mix_va)
    entry += b"\x83\xC4\x04"
    entry += b"\x89\xC6"                     # mov esi, eax

    # 5. GetTickCount()
    entry += _call_iat(syms["GetTickCount"])

    # 6. WriteFile(hOut, done, strlen_x86(done), &written, NULL)
    entry += _push_imm32(syms["done"])
    entry += _call_rel32(BASE + TEXT_RVA + len(entry), fn_len_va)
    entry += b"\x83\xC4\x04"
    entry += b"\x6A\x00"
    entry += _push_imm32(syms["written"])
    entry += b"\x50"
    entry += _push_imm32(syms["done"])
    entry += b"\x53"
    entry += _call_iat(syms["WriteFile"])

    # 7. MessageBoxA(NULL, mb_text, mb_title, 0)
    entry += b"\x6A\x00"
    entry += _push_imm32(syms["mb_title"])
    entry += _push_imm32(syms["mb_text"])
    entry += b"\x6A\x00"
    entry += _call_iat(syms["MessageBoxA"])

    # 8. ExitProcess(0)
    entry += b"\x6A\x00"
    entry += _call_iat(syms["ExitProcess"])
    entry += b"\x5E\x5B\x5D\xC3"

    assert len(entry) <= fn_sum_off, f"entry too large: {len(entry)}"
    text[0 : len(entry)] = entry
    return bytes(text)


def write_hello_win32_exe(path: Path) -> Path:
    """Write a complete, spec-compliant x86-32 PE32 binary to `path`."""
    rdata, syms, imp_rva, imp_size = _build_rdata()
    text = _build_text(syms)

    hdr = bytearray(0x200)
    # DOS header
    hdr[0:2] = b"MZ"
    struct.pack_into("<I", hdr, 0x3C, 0x80)  # e_lfanew = 0x80

    # PE Signature + COFF File Header at 0x80
    pe_off = 0x80
    hdr[pe_off : pe_off + 4] = b"PE\x00\x00"
    # Machine=0x014C (i386), NumberOfSections=2, SizeOfOptionalHeader=0xE0, Characteristics=0x010F
    struct.pack_into("<HHIIIHH", hdr, pe_off + 4, 0x014C, 2, 0, 0, 0, 0xE0, 0x010F)

    # Optional Header (PE32) at 0x98
    opt = pe_off + 24
    struct.pack_into("<H", hdr, opt + 0, 0x010B)        # Magic = PE32
    struct.pack_into("<I", hdr, opt + 4, 0x200)         # SizeOfCode
    struct.pack_into("<I", hdr, opt + 16, TEXT_RVA)     # AddressOfEntryPoint
    struct.pack_into("<I", hdr, opt + 20, TEXT_RVA)     # BaseOfCode
    struct.pack_into("<I", hdr, opt + 24, RDATA_RVA)    # BaseOfData
    struct.pack_into("<I", hdr, opt + 28, BASE)         # ImageBase
    struct.pack_into("<I", hdr, opt + 32, 0x1000)       # SectionAlignment
    struct.pack_into("<I", hdr, opt + 36, 0x200)        # FileAlignment
    struct.pack_into("<HH", hdr, opt + 40, 4, 0)        # OS Version 4.0
    struct.pack_into("<HH", hdr, opt + 48, 4, 0)        # Subsystem Version 4.0
    struct.pack_into("<I", hdr, opt + 56, 0x3000)       # SizeOfImage
    struct.pack_into("<I", hdr, opt + 60, 0x200)        # SizeOfHeaders
    struct.pack_into("<H", hdr, opt + 68, 3)            # Subsystem = CONSOLE
    struct.pack_into("<I", hdr, opt + 92, 16)           # NumberOfRvaAndSizes
    # DataDirectory[1] = Import Table
    struct.pack_into("<II", hdr, opt + 96 + 8, imp_rva, imp_size)

    # Section Headers at opt + 0xE0 = 0x178
    sec = opt + 0xE0
    # .text
    hdr[sec : sec + 8] = b".text\x00\x00\x00"
    struct.pack_into("<IIIIIIHHI", hdr, sec + 8, 0x200, TEXT_RVA, 0x200, 0x200, 0, 0, 0, 0, 0x60000020)
    # .rdata
    sec2 = sec + 40
    hdr[sec2 : sec2 + 8] = b".rdata\x00\x00"
    struct.pack_into("<IIIIIIHHI", hdr, sec2 + 8, 0x200, RDATA_RVA, 0x200, 0x400, 0, 0, 0, 0, 0x40000040)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(hdr) + text + rdata)
    return path
