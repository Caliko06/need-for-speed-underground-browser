# Runtime: MSVC CRT, SEH/EH and the engine base layer (Speed.exe PC)

> Source: `docs/re/runtime.md` in `https://github.com/Caliko06/need-for-speed-underground-browser` · Live game: https://nfsu.cc/
> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: 108

# Runtime: MSVC CRT, SEH/EH and the engine base layer (Speed.exe PC)

Marks: V = read in bytes/code and a second tool agrees (Hopper H, Ghidra G incl. its Function-ID library match "FID", capstone C),
I = inferred, U = open. Names: census/names_runtime.tsv (126 rows: 90 V, 36 I). Same-address rows in other names_*.tsv were skipped.

## Answer
- The CRT is **Visual Studio 2003 (7.1) release, static**, in 0x670c6c..0x6849d0 (about 540 functions). It starts at `__amsg_exit 0x670c6c`
  (PE entry `0x670cb5` = WinMainCRTStartup) and ends with `__allshr/__allshl 0x6849a0/0x6849d0`. Ghidra's FID names 232 of them as "Single Match".
- **Most of the "runtime" tag is not CRT.** census/systems.tsv has 3,765 runtime functions: 1,228 of them are 6..10-byte SEH
  unwind funclets at 0x684a00..0x6896e0 (`Unwind@...`, `mov eax,FuncInfo; jmp ___CxxFrameHandler`), 608 are real CRT, 29 are the engine
  base library, 235 are the online/network stack (0x660000..0x670bd0), and 641+619 are game code tagged by address band.
  Funclets are not callable functions; count them apart when you compute "named %".
- The engine base layer is EA's `b*` library: allocator (`bMalloc` 0x565b60 over named pools, first one "Main Pool"), `SlotPool`
  (fixed-size slots, 0x30-byte header), circular lists, string hash x33, 16-bit-angle trig, vector/matrix helpers, own printf (`bPrintf`).
- Two float-to-int helpers exist: `__ftol 0x672fc8` (changes the control word, 38 callers) and **0x674898** (341 callers; `fld st0; fst; fistp; fild;
  fsub` then rounds by the remainder, no control-word write). census/names_blur.tsv names 0x674898 `_ftol`; the bytes say it is the
  CW-free variant (`__ftol2`-style). Not edited here (outside scope); the lifter treats both as float to int64.

## Address map (V unless marked)
| Range | What | Evidence |
|---|---|---|
| 0x401000..0x4010c0 | engine helpers: `bMalloc_NoSite` 0x401000, `ScratchAlloc16` 0x401010 (bump allocator [0x7355b4..0x7355b8]), `CallNTimes` 0x4010a0 | H+G |
| 0x564000..0x568800 | engine base lib "bLib": pools, lists, strings, math, printf (116 functions) | G strings: "Main Pool", "bPNode SlotPool", "bPrintf:invalid pointer" |
| 0x565b60..0x565d70 | allocator: `bMalloc`, `bInitMemoryPool`, `bMemoryPool_Alloc/Validate/TotalAllocated/LargestBlock`; pool table 0x7301d4 (index = flags&7), pool object: lists at +4/+0xc/+0x14, CRITICAL_SECTION at +0x3c | H+G |
| 0x566dc0..0x567270 | `SlotPool::Create/BuildFreeList/Grow/Alloc/Destroy`, `bList::AddTail` (list node = {next,prev}); pool header: +0x10 free head, +0x18 used, +0x1c high water, +0x24 slots, +0x28 stride, +0x14 flags | H+G |
| 0x564990, 0x5649f0 | `bList::Sort` (insertion sort with callback), `bPNode_SlotPool_Init` | H+G |
| 0x564b10..0x564db0 | `bSin`, `bATan`(0x564cd0, I), `bATan2` (angles are 16-bit, 0x4000 = 90 deg) | H+G |
| 0x565020..0x567450 | `bIdentityMatrix`, `bMatrixCopy`, `bNormalize2/3`, `bScaleToLength2/3`, `bDistance3` | H+G |
| 0x567c70 (0x4fd230 is named FEng::HashName in names_hud.tsv) | string hash `h=h*0x21+c` seed -1: case-sensitive (upper-folded twin at 0x4fd230) | H+G |
| 0x567cc0..0x567de0 | `bStrLen/bStrCpy/bStrCmp/bStrICmp/bStrCat2` | H+G |
| 0x565da0, 0x565df0 | `bSPrintf` (80 callers), `bVPrintf` core | H+G |
| 0x63f150..0x63f1a0, 0x64b580..0x64b5a0 | `CriticalSection` wrappers (obj+4), global mutex [0x713c50] | H+G |
| 0x642450..0x642540 | log/assert: `Log_Printf`, `Error_Printf` ("ERROR: %s", "FILE %s LINE %d") | G |
| 0x640000..0x64a000 | also holds the RCMP/AV decoder ("RCMP_ASSERT in %s at %d", rcmpbase.cpp, mad codec): not runtime | G strings |
| 0x660000..0x670bd0 | online/network stack ("GmUtil", "connecting to %08x:%d", TAPI): system online, tagged runtime by band | G strings |
| 0x670bd0..0x670c66 | 26 six-byte import thunks (`Ordinal_n` = wsock32, plus `WSAIoctl`) | G |
| 0x670c6c..0x6849d0 | **CRT** | below |
| 0x684a00..0x6896e0 | 2,700+ SEH unwind funclets (`Unwind@...`), 10-byte stubs into `___CxxFrameHandler 0x673078` | G names, H sizes |
| 0x6896e0..0x697000 | static initialisers and MFC bits (`afxGlobalUtils` 0x6961d0, CGlobalUtils at 0x648920): not CRT | G |

CRT sub-map (V): heap `_free 0x671102` / `_malloc 0x67121a` / `__nh_malloc 0x6711ee` / `__heap_alloc 0x671173` / `_calloc 0x67906d` /
small-block heap 0x677404..0x677c2b, handle [0x79321c], heap type [0x793220]==3 (SBH) ; stdio `_iob` at 0x6eb1c0 (stride 0x20, stdout 0x6eb1e0),
`__lock_file 0x6718b6`, `_fwrite/_fread/_fclose/_fopen`; printf family `_printf 0x67147f`, `_sprintf 0x67101f`, `_vsprintf 0x671077`,
`_snprintf 0x673533`, `_vsnprintf 0x6734dd`, `_vfprintf 0x674839`, formatter `_output 0x67604e`; strings/mem 0x672630 (`_memmove`), 0x678d30 (`_memcpy`),
`_strlen 0x674c30`, `_strcmp 0x67efe0`, `_memset 0x67ef80`; threads `__getptd 0x6758cb` (TLS slot [0x6eb864], ptd 0x88 bytes: errno +8, doserrno +0xc,
locale info +0x64), locks `__lock 0x6773d3` / `__unlock 0x67733f` (table 0x6eb878); EH `___CxxFrameHandler 0x673078`, `__SEH_prolog 0x675b84`,
`__SEH_epilog 0x675bbf`, vector iterators 0x672188/0x6721e8; FPU `__control87 0x67236a`, `__controlfp 0x67239c`, `__ftol 0x672fc8`;
float to text `__cfltcvt 0x67a337` -> `_cftoe/_cftof/_cftog` 0x67a11f/0x67a22f/0x67a297; errors `__NMSG_WRITE 0x674f09` (table 0x6eb728, 18 messages incl. R6002
"floating point not loaded"), `__FF_MSGBANNER 0x675080`, /GS `__security_check_cookie 0x674ec2` (cookie [0x6eb720]).

## Re-derived with a second tool (result)
Method: I read the bytes with capstone (tools/recomp/asm.py) and wrote down what the function does, then compared with Ghidra's FID name.
Caveat: I had already seen Ghidra's name list for the CRT before reading the first 14 of these, so for them the independence is "the name was
confirmed against the code", not a blind guess. The last 6 have no FID hit or a wrong one, so they are fully from code (H + G decompile + capstone).

| Addr | My reading from bytes | Second tool | Result |
|---|---|---|---|
| 0x674c30 | 1 arg, dword zero-byte scan (0x7efefeff / 0x81010100) | G FID `_strlen` | match |
| 0x67efe0 | 2 args, per-dword byte compare, returns on first diff or NUL | G `_strcmp` | match |
| 0x67ef80 | (dst,c,n), replicate c into a dword, aligned fill | G `_memset` | match |
| 0x6849a0 | 64-bit arithmetic shift right by cl, 0x20/0x40 cases | G `__allshr` | match |
| 0x673c3b | locale-aware case-insensitive compare, ASCII fast path 0x67e180 | G `__stricmp` | match |
| 0x670f00 | find length, scan backwards with `std` | G `_strrchr` | match |
| 0x6716c8 | locale ctype lookup, mask 4 | G `_isdigit` | match |
| 0x6734a0 | page-by-page stack probe | G `__chkstk` | match |
| 0x6758cb | TLS per-thread block, calloc 0x88 on first use | G `__getptd` | match |
| 0x6773d3 | lock table at 0x6eb878, EnterCriticalSection | G `__lock` | match |
| 0x672fc8 | fnstcw / or 0xc00 / fistp / restore | G `__ftol` | match |
| 0x67f980 | (a,b,n) dword/byte compare | G `_memcmp` | match |
| 0x6723c0 | copy then zero-pad to n | G `_strncpy` | match |
| 0x674800 | length by scasb, compare with cmpsb | G `_strncmp` | match |
| 0x670efa | single `jmp 0x670e72` | G `_atol` (both) | partial: identical bytes, I name it `_atoi` |
| 0x67147f | locks stdout (0x6eb1e0), _stbuf, narrow `_output`, _ftbuf | G `FID_conflict:_wprintf` | **FID wrong**, it is `_printf` |
| 0x674839 | same with a FILE arg | G `FID_conflict:_vfwprintf` | **FID wrong**, it is `_vfprintf` |
| 0x67101f | FILE{0x42,cnt 0x7fffffff} on stack, `_output`, NUL | G decomp only (no FID name) | `_sprintf` (H same shape) |
| 0x677f42 | `__getptd()+8` | H + G decomp (no FID name) | `__errno` |
| 0x67733f | LeaveCriticalSection(table[n]) | H + G decomp (no FID name) | `__unlock` |
| 0x674f09 | table 0x6eb728 of 18 messages, console or MessageBox | G decomp (no FID name); strings R6002 etc. | `__NMSG_WRITE` |

Score: 14/14 FID matches, 2 FID conflicts resolved against FID, 1 partial, 4 names Ghidra does not have.

## Open
- 0x67c200 (46 callers) is an 80-bit x87 divide helper behind the stubs 0x67c35f..0x67c767; exact MSVC name unknown (row is low).
- 0x6896e0..0x697000 is a mix of static initialisers and MFC; no per-function names yet.
- Systems tagging: the 1,228 funclets and 235 net functions should leave "runtime" in census/systems.tsv (not edited here).

HANDOFF: names_runtime.tsv done (126 rows); next: tag funclets 0x684a00..0x6896e0 as `unwind_funclet` and name the 0x6896e0+ static initialisers by their owning class.
