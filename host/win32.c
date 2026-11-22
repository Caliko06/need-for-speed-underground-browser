// kernel32/user32/advapi32/winmm... as documented by Microsoft. We present Windows XP SP2, one CPU,
// code page 1252, the game installed at C:\NFSU. Nothing here knows about the game.
#include <ctype.h>
#include <strings.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "host.h"
int sm1_roadrefl(void);   // host/sm1.c (RN_ROADREFL)

#define ERROR_FILE_NOT_FOUND 2
#define ERROR_PATH_NOT_FOUND 3
#define ERROR_INVALID_HANDLE 6
#define ERROR_NOT_ENOUGH_MEMORY 8
#define ERROR_NO_MORE_FILES 18
#define ERROR_ALREADY_EXISTS 183
#define INVALID_HANDLE 0xffffffffu

static const char *MODULE_PATH = "C:\\NFSU\\Speed.exe";
static const char *GAME_DIR = "C:\\NFSU";
void win32_set_root(const char *dir) { files_set_root(dir); }

void set_error(Ctx *c, uint32_t e) { st(c, c->fs + 0x34, e, 4); }
static uint32_t gstrlen(Ctx *c, uint32_t p) { return (uint32_t)strnlen(G(p), c->memsz - p); }
static void put_str(Ctx *c, uint32_t dst, const char *s) { memcpy(G(dst), s, strlen(s) + 1); }

Telem rn_telem;
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
EMSCRIPTEN_KEEPALIVE uint32_t rn_telem_addr(void) { return (uint32_t)(uintptr_t)&rn_telem; }
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

static struct timespec t0;
// RN_TURBO=k (native test runs only): every clock the game sees runs k times faster (QPC, ticks, Sleep, timers, the
// audio clock, RN_KEYS times), so a race that paces itself on QPC (0x585b40 spins to the frame period) ends sooner.
// RN_SECS stays real seconds. Default 1: play is untouched.
unsigned rn_turbo = 1;
#ifdef __EMSCRIPTEN__
// The same clock clock_gettime(CLOCK_MONOTONIC) reads on the web (emscripten_get_now, timeOrigin-based in every worker),
// without musl and the wasi i64 round trip: clock reads were ~10% of the game thread in a race (build/bench/b4_s10.prof.txt).
// Safari: performance.timeOrigin drifts during a page's life (WebKit bug 258572) and is rounded to 1 ms per worker, so
// timeOrigin + now() can step back a few ms within one thread; QPC and same-thread deltas (gpu_wait, GIL holds) then
// wrapped to ~1.8e19. Each thread's clock never goes back, and a read before t0_ms is 0 (the cast was undefined).
static double t0_ms;
uint64_t now_us(void) {
    static _Thread_local uint64_t last;
    double d = (emscripten_get_now() - t0_ms) * 1000.0;
    uint64_t v = d > 0 ? (uint64_t)d * rn_turbo : 0;
    return v > last ? (last = v) : last;
}
#else
uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    int64_t ns = (int64_t)(ts.tv_sec - t0.tv_sec) * 1000000000 + (ts.tv_nsec - t0.tv_nsec);   // signed: nsec may be below t0's
    return (uint64_t)ns / 1000 * rn_turbo;
}
#endif

// ---- guest heap: boundary tags, size-class free lists, coalescing ----------------------------
// Block: [size|used] header (8 bytes: size, prev size), payload 16-aligned. Sizes in bytes.
static uint32_t brk_ptr, vtop, heap_top;
#define NBIN 64
static uint32_t bins[NBIN];     // free list heads (guest addresses of blocks)
#define HDR 16u
#define B_SIZE(b) ld(c, (b), 4)
#define B_PREV(b) ld(c, (b) + 4, 4)
#define B_NEXTF(b) ld(c, (b) + 8, 4)
#define B_PREVF(b) ld(c, (b) + 12, 4)
static int bin_of(uint32_t sz) {
    int b = 0;
    sz >>= 5;
    while (sz > 1 && b < NBIN - 1) { sz = sz * 3 / 4 > 1 ? sz * 3 / 4 : 1; b++; }
    return b;
}
static void unlink_free(Ctx *c, uint32_t b) {
    uint32_t n = B_NEXTF(b), p = B_PREVF(b), sz = B_SIZE(b) & ~1u;
    if (p) st(c, p + 8, n, 4); else bins[bin_of(sz)] = n;
    if (n) st(c, n + 12, p, 4);
}
static void push_free(Ctx *c, uint32_t b, uint32_t sz) {
    int k = bin_of(sz);
    st(c, b, sz, 4);
    st(c, b + 8, bins[k], 4);
    st(c, b + 12, 0, 4);
    if (bins[k]) st(c, bins[k] + 12, b, 4);
    bins[k] = b;
    if (b + sz < brk_ptr) st(c, b + sz + 4, sz, 4);
}
static uint32_t heap_alloc(Ctx *c, uint32_t n) {
    uint32_t need = (n + HDR + 15) & ~15u;
    if (need < 32) need = 32;
    for (int k = bin_of(need); k < NBIN; k++) {
        for (uint32_t b = bins[k], tries = 0; b && tries < 64; b = B_NEXTF(b), tries++) {
            uint32_t sz = B_SIZE(b);
            if (sz < need) continue;
            unlink_free(c, b);
            if (sz - need >= 64) {
                push_free(c, b + need, sz - need);
                st(c, b + need + 4, need, 4);
                sz = need;
            }
            st(c, b, sz | 1, 4);
            return b + HDR;
        }
    }
    if (brk_ptr + need >= vtop) {
        rn_log("guest heap: request of %u bytes from %08x line %u", need, ld(c, 0x7349a8, 4), ld(c, 0x7349ac, 4));
        guest_mem_log("full");
        return 0;
    }
    uint32_t b = brk_ptr;
    st(c, b, need | 1, 4);
    st(c, b + 4, heap_top, 4);           // size of the previous block
    brk_ptr += need;
    heap_top = need;
    return b + HDR;
}
static uint32_t heap_size(Ctx *c, uint32_t p) { return (B_SIZE(p - HDR) & ~1u) - HDR; }
static void heap_free(Ctx *c, uint32_t p) {
#ifdef RN_STW
    crashwatch_free(c, p);
#endif
    uint32_t b = p - HDR, sz = B_SIZE(b) & ~1u;
    uint32_t nx = b + sz;
    if (nx < brk_ptr && !(B_SIZE(nx) & 1)) { unlink_free(c, nx); sz += B_SIZE(nx); }
    uint32_t pv = B_PREV(b);
    if (b > HEAP_LO && pv && !(B_SIZE(b - pv) & 1)) { b -= pv; unlink_free(c, b); sz += pv; }
    if (b + sz == brk_ptr) { brk_ptr = b; heap_top = B_PREV(b); return; }
    push_free(c, b, sz);
}
void guest_free(uint32_t p) { if (p) heap_free(g_ctx, p); }
uint32_t guest_alloc(uint32_t size) {
    Ctx *c = g_ctx;
    uint32_t p = heap_alloc(c, size);
    if (p) memset(G(p), 0, size);
    return p;
}

// ---- VirtualAlloc: 64 KB granularity, top down from the end of guest memory --------------------
typedef struct { uint32_t base, size, commit, protect; } Region;
static Region regions[4096];
static int nregions;
static Region *region_at(uint32_t a) {
    for (int k = 0; k < nregions; k++)
        if (a >= regions[k].base && a < regions[k].base + regions[k].size) return &regions[k];
    return NULL;
}

// ---- handles ---------------------------------------------------------------------------------
static Handle handles[512];
uint32_t new_handle(int kind) {
    for (int k = 1; k < 512; k++)
        if (handles[k].kind == H_FREE) { memset(&handles[k], 0, sizeof handles[k]); handles[k].kind = kind; return 0x100 + 4 * k; }
    static int warned;   // table full: callers fail the Windows way (CreateFile INVALID_HANDLE_VALUE, HeapCreate NULL...)
    if (!warned) { warned = 1; rn_log("handle table full (511 in use): new_handle(kind %d) fails", kind); }
    return 0;
}
Handle *get_handle(uint32_t h) {
    uint32_t k = (h - 0x100) / 4;
    if (!h || h < 0x100 || (h & 3) || k >= 512 || handles[k].kind == H_FREE) return NULL;
    return &handles[k];
}

// =================================== kernel32 ==================================================
static uint32_t GetVersion_(Ctx *c) { (void)c; return 0x0a280105u; }    // 5.1 build 2600
static uint32_t GetVersionExA_(Ctx *c) {
    uint32_t p = ARG(0), sz = ld(c, p, 4);
    if (sz != 148 && sz != 156) { set_error(c, 122); return 0; }
    memset(G(p + 4), 0, sz - 4);
    st(c, p + 4, 5, 4); st(c, p + 8, 1, 4); st(c, p + 12, 2600, 4); st(c, p + 16, 2, 4);
    put_str(c, p + 20, "Service Pack 2");
    if (sz == 156) st(c, p + 148, 2, 2);
    return 1;
}
static uint16_t to_wide(uint8_t b);
static uint32_t GetCommandLineA_(Ctx *c) { (void)c; return STR_ADDR; }
static uint32_t GetEnvironmentStrings_(Ctx *c) { (void)c; return STR_ADDR + 0x400; }
static uint32_t FreeEnvironmentStrings_(Ctx *c) { (void)c; return 1; }
static uint32_t GetEnvironmentStringsW_(Ctx *c) {
    uint32_t src = STR_ADDR + 0x400, n = 0;
    while (G(src)[n] || G(src)[n + 1]) n++;
    n += 2;
    uint32_t w = heap_alloc(c, 2 * n);
    for (uint32_t k = 0; k < n; k++) st(c, w + 2 * k, to_wide((uint8_t)G(src)[k]), 2);
    return w;
}
static uint32_t FreeEnvironmentStringsW_(Ctx *c) { heap_free(c, ARG(0)); return 1; }
static uint32_t GetModuleFileNameA_(Ctx *c) {
    uint32_t h = ARG(0), buf = ARG(1), n = ARG(2);
    if (h && h != IMAGE_BASE) { rn_halt(c, "GetModuleFileNameA of module %08x", h); return 0; }
    uint32_t len = (uint32_t)strlen(MODULE_PATH);
    if (!n) return 0;
    uint32_t w = len < n ? len : n - 1;
    memcpy(G(buf), MODULE_PATH, w); G(buf)[w] = 0;
    return w;
}
static uint32_t GetStartupInfoA_(Ctx *c) {
    uint32_t p = ARG(0);
    memset(G(p), 0, 68);
    st(c, p, 68, 4);
    return 0;
}
static uint32_t GetStdHandle_(Ctx *c) { (void)c; return 0; }   // a GUI process has no standard handles
static uint32_t SetStdHandle_(Ctx *c) { (void)c; return 1; }
static uint32_t GetFileType_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (h && h->kind == H_FILE) return 1;     // FILE_TYPE_DISK
    set_error(c, ERROR_INVALID_HANDLE);
    return 0;
}
static uint32_t SetHandleCount_(Ctx *c) { return ARG(0); }
static uint32_t GetACP_(Ctx *c) { (void)c; return 1252; }
static uint32_t GetOEMCP_(Ctx *c) { (void)c; return 437; }
static uint32_t IsValidCodePage_(Ctx *c) { uint32_t cp = ARG(0); return cp == 1252 || cp == 437 || cp == 20127; }
static uint32_t GetCPInfo_(Ctx *c) {
    uint32_t cp = ARG(0), p = ARG(1);
    if (cp != 0 && cp != 1 && cp != 1252 && cp != 437) { set_error(c, 87); return 0; }
    memset(G(p), 0, 20);
    st(c, p, 1, 4);            // MaxCharSize
    st(c, p + 4, '?', 1);      // DefaultChar
    return 1;
}

// Code page 1252: bytes 0x80..0x9f are not Latin-1.
static const uint16_t cp1252_hi[32] = {
    0x20ac, 0x0081, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160, 0x2039, 0x0152, 0x008d, 0x017d, 0x008f,
    0x0090, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x02dc, 0x2122, 0x0161, 0x203a, 0x0153, 0x009d, 0x017e, 0x0178};
static uint16_t to_wide(uint8_t b) { return b >= 0x80 && b < 0xa0 ? cp1252_hi[b - 0x80] : b; }
static int to_narrow(uint16_t w) {
    if (w < 0x80 || (w >= 0xa0 && w < 0x100)) return w;
    for (int k = 0; k < 32; k++) if (cp1252_hi[k] == w) return 0x80 + k;
    return -1;
}
static uint32_t MultiByteToWideChar_(Ctx *c) {
    uint32_t src = ARG(2), n = ARG(3), dst = ARG(4), dn = ARG(5);
    if ((int32_t)n == -1) n = gstrlen(c, src) + 1;
    if (!dn) return n;
    if (dn < n) { set_error(c, 122); return 0; }
    for (uint32_t k = 0; k < n; k++) st(c, dst + 2 * k, to_wide((uint8_t)G(src)[k]), 2);
    return n;
}
static uint32_t WideCharToMultiByte_(Ctx *c) {
    uint32_t src = ARG(2), n = ARG(3), dst = ARG(4), dn = ARG(5), used = ARG(7);
    if ((int32_t)n == -1) { n = 0; while (ld(c, src + 2 * n, 2)) n++; n++; }
    if (used) st(c, used, 0, 4);
    if (!dn) return n;
    if (dn < n) { set_error(c, 122); return 0; }
    for (uint32_t k = 0; k < n; k++) {
        int b = to_narrow((uint16_t)ld(c, src + 2 * k, 2));
        if (b < 0) { b = '?'; if (used) st(c, used, 1, 4); }
        G(dst)[k] = (char)b;
    }
    return n;
}
// CT_CTYPE1 for UTF-16 code units below 0x100 (Latin-1); others are reported as 0.
static uint16_t ctype1(uint32_t w) {
    uint16_t t = 0;
    if (w >= 0x100) return 0;
    if (w < 0x20 || w == 0x7f || (w >= 0x80 && w < 0xa0)) t |= 0x20;
    if (w == ' ' || w == '\t' || (w >= 0x0a && w <= 0x0d) || w == 0xa0) t |= 0x08;
    if (w == ' ' || w == '\t' || w == 0xa0) t |= 0x40;
    if (w >= '0' && w <= '9') t |= 0x04 | 0x80;
    if ((w >= 'a' && w <= 'f') || (w >= 'A' && w <= 'F')) t |= 0x80;
    if ((w >= 'A' && w <= 'Z') || (w >= 0xc0 && w <= 0xde && w != 0xd7)) t |= 0x01 | 0x100;
    if ((w >= 'a' && w <= 'z') || (w >= 0xdf && w <= 0xff && w != 0xf7) || w == 0xaa || w == 0xb5 || w == 0xba) t |= 0x02 | 0x100;
    if (((w >= 0x21 && w <= 0x2f) || (w >= 0x3a && w <= 0x40) || (w >= 0x5b && w <= 0x60) || (w >= 0x7b && w <= 0x7e) ||
         (w >= 0xa1 && w <= 0xbf && w != 0xaa && w != 0xb5 && w != 0xba) || w == 0xd7 || w == 0xf7)) t |= 0x10;
    return t;
}
static uint32_t GetStringTypeW_(Ctx *c) {
    uint32_t type = ARG(0), src = ARG(1), n = ARG(2), out = ARG(3);
    if (type != 1) { rn_halt(c, "GetStringTypeW type %u", type); return 0; }
    if ((int32_t)n == -1) { n = 0; while (ld(c, src + 2 * n, 2)) n++; n++; }
    for (uint32_t k = 0; k < n; k++) st(c, out + 2 * k, ctype1(ld(c, src + 2 * k, 2)), 2);
    return 1;
}
static uint32_t GetStringTypeA_(Ctx *c) {
    uint32_t type = ARG(1), src = ARG(2), n = ARG(3), out = ARG(4);
    if (type != 1) { rn_halt(c, "GetStringTypeA type %u", type); return 0; }
    if ((int32_t)n == -1) n = gstrlen(c, src) + 1;
    for (uint32_t k = 0; k < n; k++) st(c, out + 2 * k, ctype1(to_wide((uint8_t)G(src)[k])), 2);
    return 1;
}
static uint32_t case_map(uint32_t w, uint32_t flags) {
    if (flags & 0x100) {   // LCMAP_LOWERCASE
        if ((w >= 'A' && w <= 'Z') || (w >= 0xc0 && w <= 0xde && w != 0xd7)) return w + 0x20;
        if (w == 0x160 || w == 0x152 || w == 0x17d) return w + 1;
        if (w == 0x178) return 0xff;
    } else if (flags & 0x200) {
        if ((w >= 'a' && w <= 'z') || (w >= 0xe0 && w <= 0xfe && w != 0xf7)) return w - 0x20;
        if (w == 0x161 || w == 0x153 || w == 0x17e) return w - 1;
        if (w == 0xff) return 0x178;
    }
    return w;
}
static uint32_t LCMapStringW_(Ctx *c) {
    uint32_t flags = ARG(1), src = ARG(2), n = ARG(3), dst = ARG(4), dn = ARG(5);
    if (flags & ~0x300u) { rn_halt(c, "LCMapStringW flags %08x", flags); return 0; }
    if ((int32_t)n == -1) { n = 0; while (ld(c, src + 2 * n, 2)) n++; n++; }
    if (!dn) return n;
    if (dn < n) { set_error(c, 122); return 0; }
    for (uint32_t k = 0; k < n; k++) st(c, dst + 2 * k, case_map(ld(c, src + 2 * k, 2), flags), 2);
    return n;
}
static uint32_t LCMapStringA_(Ctx *c) {
    uint32_t flags = ARG(1), src = ARG(2), n = ARG(3), dst = ARG(4), dn = ARG(5);
    if (flags & ~0x300u) { rn_halt(c, "LCMapStringA flags %08x", flags); return 0; }
    if ((int32_t)n == -1) n = gstrlen(c, src) + 1;
    if (!dn) return n;
    if (dn < n) { set_error(c, 122); return 0; }
    for (uint32_t k = 0; k < n; k++) {
        int b = to_narrow((uint16_t)case_map(to_wide((uint8_t)G(src)[k]), flags));
        G(dst)[k] = (char)(b < 0 ? G(src)[k] : b);
    }
    return n;
}
static int cmp_units(uint32_t a, uint32_t b, uint32_t flags) {
    if (flags & 1) { a = case_map(a, 0x100); b = case_map(b, 0x100); }   // NORM_IGNORECASE
    return a < b ? -1 : a > b;
}
static uint32_t CompareStringA_(Ctx *c) {
    uint32_t flags = ARG(1), s1 = ARG(2), n1 = ARG(3), s2 = ARG(4), n2 = ARG(5);
    if (flags & ~1u) { rn_halt(c, "CompareStringA flags %08x", flags); return 0; }
    if ((int32_t)n1 < 0) n1 = gstrlen(c, s1);
    if ((int32_t)n2 < 0) n2 = gstrlen(c, s2);
    for (uint32_t k = 0; k < n1 && k < n2; k++) {
        int r = cmp_units(to_wide((uint8_t)G(s1)[k]), to_wide((uint8_t)G(s2)[k]), flags);
        if (r) return r < 0 ? 1 : 3;
    }
    return n1 < n2 ? 1 : n1 > n2 ? 3 : 2;
}
static uint32_t CompareStringW_(Ctx *c) {
    uint32_t flags = ARG(1), s1 = ARG(2), n1 = ARG(3), s2 = ARG(4), n2 = ARG(5);
    if (flags & ~1u) { rn_halt(c, "CompareStringW flags %08x", flags); return 0; }
    if ((int32_t)n1 < 0) { n1 = 0; while (ld(c, s1 + 2 * n1, 2)) n1++; }
    if ((int32_t)n2 < 0) { n2 = 0; while (ld(c, s2 + 2 * n2, 2)) n2++; }
    for (uint32_t k = 0; k < n1 && k < n2; k++) {
        int r = cmp_units(ld(c, s1 + 2 * k, 2), ld(c, s2 + 2 * k, 2), flags);
        if (r) return r < 0 ? 1 : 3;
    }
    return n1 < n2 ? 1 : n1 > n2 ? 3 : 2;
}
// lstrcmp(i)A = CompareStringA(LOCALE_USER_DEFAULT, 0 or NORM_IGNORECASE, s1, -1, s2, -1) - 2.
static uint32_t lstrcmp_any(Ctx *c, uint32_t s1, uint32_t s2, uint32_t flags) {
    uint32_t n1 = gstrlen(c, s1), n2 = gstrlen(c, s2);
    for (uint32_t k = 0; k < n1 && k < n2; k++) {
        int r = cmp_units(to_wide((uint8_t)G(s1)[k]), to_wide((uint8_t)G(s2)[k]), flags);
        if (r) return (uint32_t)r;
    }
    return n1 < n2 ? 0xffffffffu : n1 > n2;
}
static uint32_t lstrcmpiA_(Ctx *c) { return lstrcmp_any(c, ARG(0), ARG(1), 1); }
static uint32_t lstrcmpA_(Ctx *c) { return lstrcmp_any(c, ARG(0), ARG(1), 0); }
// Locale 0x0409 (English, United States).
static const char *locale_info(uint32_t type) {
    switch (type & 0xffff) {
    case 0x0001: return "0409";            // LOCALE_ILANGUAGE
    case 0x0003: return "ENU";             // LOCALE_SABBREVLANGNAME
    case 0x0006: return "United States";   // LOCALE_SCOUNTRY
    case 0x0007: return "USA";             // LOCALE_SABBREVCTRYNAME
    case 0x1001: return "English";         // LOCALE_SENGLANGUAGE
    case 0x1002: return "United States";   // LOCALE_SENGCOUNTRY
    case 0x0005: return "1";               // LOCALE_ICOUNTRY
    case 0x000b: return "437";             // LOCALE_IDEFAULTCODEPAGE
    case 0x1004: return "1252";            // LOCALE_IDEFAULTANSICODEPAGE
    case 0x000e: return ".";               // LOCALE_SDECIMAL
    case 0x000f: return ",";               // LOCALE_STHOUSAND
    case 0x0014: return "$";               // LOCALE_SCURRENCY
    case 0x0016: return ".";               // LOCALE_SMONDECIMALSEP
    case 0x0017: return ",";               // LOCALE_SMONTHOUSANDSEP
    case 0x001d: return "/";               // LOCALE_SDATE
    case 0x001e: return ":";               // LOCALE_STIME
    case 0x001f: return "M/d/yyyy";        // LOCALE_SSHORTDATE
    }
    return NULL;
}
static uint32_t GetLocaleInfoA_(Ctx *c) {
    uint32_t type = ARG(1), buf = ARG(2), n = ARG(3);
    const char *s = locale_info(type);
    if (!s) { rn_halt(c, "GetLocaleInfoA type %08x", type); return 0; }
    uint32_t len = (uint32_t)strlen(s) + 1;
    if (!n) return len;
    if (n < len) { set_error(c, 122); return 0; }
    memcpy(G(buf), s, len);
    return len;
}
static uint32_t GetLocaleInfoW_(Ctx *c) {
    uint32_t type = ARG(1), buf = ARG(2), n = ARG(3);
    const char *s = locale_info(type);
    if (!s) { rn_halt(c, "GetLocaleInfoW type %08x", type); return 0; }
    uint32_t len = (uint32_t)strlen(s) + 1;
    if (!n) return len;
    if (n < len) { set_error(c, 122); return 0; }
    for (uint32_t k = 0; k < len; k++) st(c, buf + 2 * k, (uint8_t)s[k], 2);
    return len;
}
static uint32_t GetUserDefaultLCID_(Ctx *c) { (void)c; return 0x0409; }
static uint32_t IsValidLocale_(Ctx *c) { return ARG(0) == 0x0409; }

static uint32_t HeapCreate_(Ctx *c) {
    uint32_t h = new_handle(H_HEAP);
    if (!h) set_error(c, ERROR_NOT_ENOUGH_MEMORY);       // NULL, as Windows
    return h;
}
static uint32_t HeapDestroy_(Ctx *c) { (void)c; return 1; }
static uint32_t HeapAlloc_(Ctx *c) {
    uint32_t flags = ARG(1), n = ARG(2);
    uint32_t p = heap_alloc(c, n ? n : 1);
    if (!p) { if (flags & 4) rn_halt(c, "HeapAlloc(%u) out of memory", n); return 0; }
    if (flags & 8) memset(G(p), 0, n);
    return p;
}
static uint32_t HeapFree_(Ctx *c) { if (ARG(2)) heap_free(c, ARG(2)); return 1; }
static uint32_t HeapSize_(Ctx *c) { return heap_size(c, ARG(2)); }
static uint32_t HeapReAlloc_(Ctx *c) {
    uint32_t flags = ARG(1), p = ARG(2), n = ARG(3);
    uint32_t old = heap_size(c, p);
    if (n <= old) return p;
    if (flags & 0x10) return 0;              // HEAP_REALLOC_IN_PLACE_ONLY
    uint32_t q = heap_alloc(c, n);
    if (!q) return 0;
    memmove(G(q), G(p), old);
    if (flags & 8) memset(G(q + old), 0, n - old);
    heap_free(c, p);
    return q;
}

// Released ranges (VirtualFree MEM_RELEASE), merged with their neighbours; VirtualAlloc takes them before new space, as
// Windows reuses released address space. Without it the space only went down (runs/career_trace stopped at event 11:
// the pool's malloc 0x67121a returned NULL, 0x565b60 -> int3 0x565cd2).
static Region vfree[4096];
static int nvfree;
static uint32_t vstat_alloc, vstat_release;   // bytes, for guest_mem_log
static void vfree_add(uint32_t base, uint32_t size) {
    for (int k = 0; k < nvfree; k++)
        if (vfree[k].base + vfree[k].size == base || base + size == vfree[k].base) {
            if (vfree[k].base < base) base = vfree[k].base;
            size += vfree[k].size;
            vfree[k--] = vfree[--nvfree];
        }
    if (base == vtop) vtop += size;
    else if (nvfree < 4096) vfree[nvfree++] = (Region){base, size, 0, 0};
}
static uint32_t vspace(Ctx *c, uint32_t sz) {   // first fit in the released ranges, else below vtop
    vstat_alloc += sz;
    for (int k = 0; k < nvfree; k++)
        if (vfree[k].size >= sz) {
            uint32_t b = vfree[k].base;
            vfree[k].base += sz, vfree[k].size -= sz;
            if (!vfree[k].size) vfree[k] = vfree[--nvfree];
            return b;
        }
    if (vtop - sz <= brk_ptr) return 0;
    return vtop -= sz;
}
// The page's memory line (web/index.html): 0 host heap end (sbrk), 1 guest heap, 2 guest VirtualAlloc'd, all in MB.
EMSCRIPTEN_KEEPALIVE uint32_t rn_mem_mb(int k) {
    return k == 0 ? (uint32_t)((uintptr_t)sbrk(0) >> 20) : k == 1 ? (brk_ptr - HEAP_LO) >> 20 : (g_ctx ? (g_ctx->memsz - vtop) >> 20 : 0);
}
void guest_mem_log(const char *why) {
    Ctx *c = g_ctx;
    uint32_t fb = 0, vf = 0;
    for (int k = 0; k < NBIN; k++) for (uint32_t b = bins[k]; b; b = B_NEXTF(b)) fb += B_SIZE(b);
    for (int k = 0; k < nvfree; k++) vf += vfree[k].size;
    uint32_t dd, dl;
    d3d9_mem(&dd, &dl);
    rn_log("guest memory %s: d3d9 locked memory %u MB live, %u MB dead", why, dl >> 20, dd >> 20);
    rn_log("guest memory %s: heap %u MB (%u MB free in bins), virtual %u MB in %d regions (%u MB released, reusable), "
           "VirtualAlloc %u MB / released %u MB in all, gap %u MB", why, (brk_ptr - HEAP_LO) >> 20, fb >> 20,
           (c->memsz - vtop) >> 20, nregions, vf >> 20, vstat_alloc >> 20, vstat_release >> 20, (vtop - brk_ptr) >> 20);
}
static uint32_t VirtualAlloc_(Ctx *c) {
    uint32_t addr = ARG(0), size = ARG(1), type = ARG(2), prot = ARG(3);
    if (addr) {
        Region *r = region_at(addr);
        if (r && (type & 0x1000) && addr + size <= r->base + r->size) {   // commit inside a reservation
            r->commit = 1;
            return addr & ~0xfffu;
        }
        set_error(c, 487);
        return 0;
    }
    uint32_t sz = (size + 0xffff) & ~0xffffu, b = nregions < 4096 ? vspace(c, sz) : 0;
    if (!b) { guest_mem_log("full"); set_error(c, ERROR_NOT_ENOUGH_MEMORY); return 0; }
    regions[nregions++] = (Region){b, sz, (type & 0x1000) != 0, prot};
    memset(G(b), 0, sz);
    return b;
}
uint32_t virtual_reserve(Ctx *c, uint32_t size) {
    uint32_t sz = (size + 0xffff) & ~0xffffu, b = nregions < 4096 ? vspace(c, sz) : 0;
    if (!b) { guest_mem_log("full"); return 0; }
    regions[nregions++] = (Region){b, sz, 1, 4};
    memset(G(b), 0, sz);
    return b;
}
static uint32_t VirtualFree_(Ctx *c) {
    uint32_t addr = ARG(0), type = ARG(2);
    Region *r = region_at(addr);
    if (!r) { set_error(c, 487); return 0; }
    if (type & 0x8000) {        // MEM_RELEASE (of the whole reservation, from its base): the space goes back
        if (addr != r->base) { set_error(c, 87); return 0; }
        vstat_release += r->size;
        vfree_add(r->base, r->size);
        *r = regions[--nregions];
    }
    return 1;
}
static uint32_t VirtualQuery_(Ctx *c) {
    uint32_t addr = ARG(0), p = ARG(1), n = ARG(2);
    if (n < 28) return 0;
    Region *r = region_at(addr);
    uint32_t base = addr & ~0xfffu, abase = base, size = 0x1000, state = 0x1000, prot = 4, type = 0x20000;
    if (r) { abase = r->base; size = r->base + r->size - base; prot = r->protect; }
    else if (addr >= IMAGE_BASE && addr < HEAP_LO) { abase = IMAGE_BASE; type = 0x1000000; prot = 0x20; }
    else if (addr >= STACK_LO && addr < STACK_HI) { abase = STACK_LO; size = STACK_HI - base; }
    st(c, p, base, 4); st(c, p + 4, abase, 4); st(c, p + 8, prot, 4); st(c, p + 12, size, 4);
    st(c, p + 16, state, 4); st(c, p + 20, prot, 4); st(c, p + 24, type, 4);
    return 28;
}
static uint32_t VirtualProtect_(Ctx *c) { if (ARG(3)) st(c, ARG(3), 4, 4); return 1; }

static uint32_t TlsAlloc_(Ctx *c) {
    uint32_t bits = ld(c, PEB_ADDR + 0x44, 4);
    for (int k = 0; k < 32; k++)
        if (!(bits & (1u << k))) { st(c, PEB_ADDR + 0x44, bits | (1u << k), 4); st(c, c->fs + 0xe10 + 4 * k, 0, 4); return k; }
    return 0xffffffffu;
}
static uint32_t TlsFree_(Ctx *c) { uint32_t k = ARG(0); st(c, PEB_ADDR + 0x44, ld(c, PEB_ADDR + 0x44, 4) & ~(1u << k), 4); return 1; }
static uint32_t TlsGetValue_(Ctx *c) { uint32_t k = ARG(0); set_error(c, 0); return k < 64 ? ld(c, c->fs + 0xe10 + 4 * k, 4) : 0; }
static uint32_t TlsSetValue_(Ctx *c) { uint32_t k = ARG(0); if (k >= 64) return 0; st(c, c->fs + 0xe10 + 4 * k, ARG(1), 4); return 1; }

// One thread runs at a time, so a critical section only counts recursion.
static uint32_t InterlockedExchange_(Ctx *c) { uint32_t p = ARG(0), old = ld(c, p, 4); st(c, p, ARG(1), 4); return old; }

static uint32_t GetCurrentProcess_(Ctx *c) { (void)c; return 0xffffffffu; }
static uint32_t GetCurrentThread_(Ctx *c) { (void)c; return 0xfffffffeu; }
static uint32_t GetCurrentProcessId_(Ctx *c) { return ld(c, c->fs + 0x20, 4); }
static uint32_t GetLastError_(Ctx *c) { return ld(c, c->fs + 0x34, 4); }
static uint32_t SetLastError_(Ctx *c) { set_error(c, ARG(0)); return 0; }
static uint32_t SetUnhandledExceptionFilter_(Ctx *c) {
    static uint32_t prev;
    uint32_t old = prev;
    prev = ARG(0);
    (void)c;
    return old;
}
static uint32_t SetErrorMode_(Ctx *c) { static uint32_t mode; uint32_t old = mode; mode = ARG(0); (void)c; return old; }
static int bad_range(Ctx *c, uint32_t p, uint32_t n) { return p < LOW || p > c->memsz || n > c->memsz - p; }
static uint32_t IsBadReadPtr_(Ctx *c) { return ARG(1) && bad_range(c, ARG(0), ARG(1)); }
static uint32_t IsBadCodePtr_(Ctx *c) { uint32_t p = ARG(0); return !(p >= HOST_BASE || (p >= IMAGE_BASE && p < c->memsz)); }
static uint32_t GetSystemInfo_(Ctx *c) {
    uint32_t p = ARG(0);
    memset(G(p), 0, 36);
    st(c, p + 4, 4096, 4); st(c, p + 8, LOW, 4); st(c, p + 12, GUEST_MEM - LOW - 1, 4);
    st(c, p + 16, 1, 4); st(c, p + 20, 1, 4); st(c, p + 24, 586, 4); st(c, p + 28, 0x10000, 4);
    st(c, p + 32, 6, 2); st(c, p + 34, 0x0101, 2);
    return 0;
}
// Same CPU as rn_cpuid: CX8 and RDTSC, no MMX/SSE/3DNow.
static uint32_t IsProcessorFeaturePresent_(Ctx *c) { uint32_t f = ARG(0); return f == 2 || f == 8; }
// RN_FIXEDCLOCK=1 (tests, tools/abbench.py): from the first race HUD on (host/d3d9.c), the game thread's clock reads count frames, not real
// time: 1/60 s per Present and 1 us per read (a loop that polls the clock still ends). The frame time the game derives from QPC
// (limiter 0x585b40) and the RNG are then the same in every run, so race frame N is the same moment. Other threads keep the real clock.
static uint64_t fixed_base;
static uint32_t fixed_presents;
void rn_fixedclock_start(Ctx *c) {
    if (!getenv("RN_FIXEDCLOCK")) return;
    fixed_base = now_us(), fixed_presents = rn_telem.presents;
    st(c, 0x6f227c, 0x12345678, 4);   // the game RNG (PATCH 0x4470f0): the frames before this one differ between runs
}
static uint64_t game_now_us(void) {
    static uint64_t reads;
    return fixed_base && rn_is_main_thread() ? fixed_base + (uint64_t)(rn_telem.presents - fixed_presents) * 16667 + ++reads : now_us();
}
// Spike probe (host/d3d9.c spike_log, race frames > 23 ms -> page log -> F10): the main thread's clock reads by call site
// (the return address), to name a busy wait that is not the limiter 0x585b40.
uint32_t rn_clk_site[8], rn_clk_n[8];
static void clk_site(Ctx *c) {
    if (!rn_is_main_thread()) return;
    uint32_t a = ld(c, c->r[ESP], 4);
    for (int k = 0; k < 8; k++)
        if (rn_clk_site[k] == a || !rn_clk_n[k]) { rn_clk_site[k] = a; rn_clk_n[k]++; return; }
}
static uint32_t GetTickCount_(Ctx *c) { rn_telem.clock_calls++; clk_site(c); gil_clock(); return (uint32_t)(game_now_us() / 1000); }
// The frame limiter 0x585b40 spins on QPC (call at 0x585bf5, return 0x585bf7) until (1 << [0x7349c8]) * (now >> sh - ebp)
// * [0x7301d0] >= the wait at [esp+0x1c] of its frame (esp = this call's esp + 8). The spin is ~25 % of the game thread's
// CPU in a race (profile spk2) and holds a core that a phone needs. Here the host sleeps without the GIL until 0.3 ms
// before that exit point and then lets the loop spin as before: the loop still exits at its first read past the
// deadline, so the frame times are the same. OFF by default (RN_LIMSLEEP=1 on): bench spk5 (Mac under load) gave p99
// 33.4 ms, 35 frames > 33 ms vs spk3 19.6 / 3; not yet separated from the load. Off under RN_FIXEDCLOCK.
// Wake margin: a sleep on the web comes back ~1.5-2.5 ms late (and the thread that took the turn meanwhile runs a 2 ms
// spin quantum); at 0.3 ms the race ran at p50 17.9-19.0 ms, 53-57 fps (headed A/B ls_on1/2, w1 2026-11-05).
#define LIM_WAKE_US 3000
static int lim_sleep = -1;
static void limiter_sleep(Ctx *c) {
    if (lim_sleep < 0) { const char *e = getenv("RN_LIMSLEEP"); lim_sleep = e && *e == '1'; }
    if (!lim_sleep || fixed_base || ld(c, c->r[ESP], 4) != 0x585bf7 || !rn_is_main_thread()) return;
    uint32_t sh = ld(c, 0x7349c8, 4) & 31, w = ld(c, c->r[ESP] + 8 + 0x1c, 4), p = ld(c, 0x7301d0, 4);
    float wait, per;
    memcpy(&wait, &w, 4), memcpy(&per, &p, 4);
    if (!(per > 0) || !(wait > 0)) return;
    int32_t el = (int32_t)((uint32_t)(now_us() >> sh) - c->r[EBP]);
    double left_us = wait / per - (double)(el < 0 ? 0 : el) * (1u << sh);   // ticks = us (QPF 1 MHz)
    if (left_us < LIM_WAKE_US + 500) return;
    gil_sleep_us((uint64_t)(left_us - LIM_WAKE_US));
}
// RN_FPS=30 (web ?fps=30, accepted degradation, OFF by default): the limiter's frame target [0x6f0890] (1/60, read
// only at 0x585b83) becomes 1/30. The limiter then adds the waited time to the frame dt (param_1 + wait = 1/30) and the
// game turns dt into 1/60 s simulation ticks with a carried remainder ([0x73456c]; dt is clamped by [0x6f0894] = 3): two ticks a
// frame, as on a PC that runs at 30 fps, so the game's speed and physics step stay the same. Set at the first clock read.
static void fps_init(Ctx *c) {
    static int done;
    if (done) return;
    done = 1;
    const char *e = getenv("RN_FPS");
    if (e && atoi(e) == 30) { st(c, 0x6f0890, 0x3d088889, 4); rn_log("RN_FPS=30: frame target [0x6f0890] = 1/30 s"); }
}
static uint32_t QueryPerformanceCounter_(Ctx *c) { rn_telem.clock_calls++; clk_site(c); fps_init(c); limiter_sleep(c); gil_clock(); st64(c, ARG(0), game_now_us()); return 1; }
static uint32_t QueryPerformanceFrequency_(Ctx *c) { st64(c, ARG(0), 1000000); return 1; }
// The PC's clock runs on UTC: time zone "Greenwich Standard Time" (bias 0, no daylight saving),
// so local time = system time. GetTimeZoneInformation then answers TIME_ZONE_ID_UNKNOWN.
static uint32_t GetTimeZoneInformation_(Ctx *c) {
    uint32_t p = ARG(0);
    memset(G(p), 0, 172);
    const char *name = "Greenwich Standard Time";
    for (int k = 0; name[k]; k++) { st(c, p + 4 + 2 * k, (uint8_t)name[k], 2); st(c, p + 88 + 2 * k, (uint8_t)name[k], 2); }
    return 0;
}
static uint32_t GetSystemTimeAsFileTime_(Ctx *c) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    st64(c, ARG(0), (uint64_t)ts.tv_sec * 10000000ull + ts.tv_nsec / 100 + 116444736000000000ull);
    return 0;
}
static uint32_t ExitProcess_(Ctx *c) { rn_halt(c, "ExitProcess(%u)", ARG(0)); return 0; }
static uint32_t OutputDebugStringA_(Ctx *c) { rn_log("debug: %s", G(ARG(0))); return 0; }

static uint32_t module_handle(const char *name) {
    static const char *known[] = {"kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "winmm.dll", "d3d9.dll",
                                  "dinput8.dll", "dsound.dll", "ddraw.dll", "shell32.dll", "shfolder.dll", "ntdll.dll", NULL};
    char n[64];
    snprintf(n, sizeof n, "%s", name);
    if (!strchr(n, '.')) strncat(n, ".dll", sizeof n - strlen(n) - 1);
    for (int k = 0; known[k]; k++) if (!strcasecmp(n, known[k])) return 0x70000000u + 0x10000u * k;
    return 0;
}
static const char *module_name(uint32_t h) {
    static const char *known[] = {"kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "winmm.dll", "d3d9.dll",
                                  "dinput8.dll", "dsound.dll", "ddraw.dll", "shell32.dll", "shfolder.dll", "ntdll.dll"};
    uint32_t k = (h - 0x70000000u) / 0x10000u;
    return h >= 0x70000000u && k < 12 && !(h & 0xffff) ? known[k] : NULL;
}
static uint32_t GetModuleHandleA_(Ctx *c) {
    uint32_t p = ARG(0);
    if (!p) return IMAGE_BASE;
    uint32_t h = module_handle(G(p));
    if (!h) { rn_log("GetModuleHandleA(%s) -> not loaded", G(p)); set_error(c, 126); }
    return h;
}
static uint32_t LoadLibraryA_(Ctx *c) {
    uint32_t h = module_handle(G(ARG(0)));
    if (!h) { rn_halt(c, "LoadLibraryA(%s)", G(ARG(0))); return 0; }
    return h;
}
static uint32_t GetProcAddress_(Ctx *c) {
    uint32_t h = ARG(0), p = ARG(1);
    const char *dll = module_name(h);
    if (!dll) { rn_halt(c, "GetProcAddress on module %08x", h); return 0; }
    if (p < 0x10000) { rn_halt(c, "GetProcAddress(%s, #%u)", dll, p); return 0; }
    if (find_api(dll, G(p))) return host_addr_of(dll, G(p));
    rn_halt(c, "GetProcAddress(%s, %s): not in the layer", dll, G(p));
    return 0;
}

// ---- files -------------------------------------------------------------------------------------
// CreateFile{A,W}(name, access, share, security, disposition, flags, template).
static uint32_t create_file(Ctx *c, const char *name) {
    uint32_t access = ARG(1), disp = ARG(4);
    int id, existed = 0;
    if ((access & 0x40000000u) || (disp != 3 && gf_stat(name) != -2 && gf_stat(name) != 0)) {   // GENERIC_WRITE or create
        id = gf_create(name, (int)disp, &existed);
        static const uint32_t err[] = {0, ERROR_FILE_NOT_FOUND, 0, 5, 80, 5, ERROR_PATH_NOT_FOUND};
        if (id == -2) { rn_halt(c, "CreateFileA outside the game and save folders: %s", name); return INVALID_HANDLE; }
        if (id < 0) { set_error(c, err[-id]); return INVALID_HANDLE; }
        uint32_t h = new_handle(H_FILE);
        if (!h) { gf_close(id); set_error(c, ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE; }
        get_handle(h)->gf = id;
        snprintf(get_handle(h)->path, sizeof get_handle(h)->path, "%s", name);
        if (rn_trace()) rn_log("open for writing %s (disp %u) -> %x", name, disp, h);
        set_error(c, existed && (disp == 2 || disp == 4) ? ERROR_ALREADY_EXISTS : 0);
        return h;
    }
    id = gf_open(name);
    if (id == -2) { rn_halt(c, "CreateFileA outside the game folder: %s", name); return INVALID_HANDLE; }
    if (id < 0) {
        if (rn_trace()) rn_log("file missing: %s", name);
        set_error(c, id == -3 ? 5 : ERROR_FILE_NOT_FOUND);   // a directory: ERROR_ACCESS_DENIED
        return INVALID_HANDLE;
    }
    uint32_t h = new_handle(H_FILE);
    if (!h) { gf_close(id); set_error(c, ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE; }
    get_handle(h)->gf = id;
    snprintf(get_handle(h)->path, sizeof get_handle(h)->path, "%s", name);
    if (rn_trace()) rn_log("open %s -> %x", name, h);
    else {   // RN_FLOWLOG: the files a run read (completion.py names a run's row by them)
        static int fl = -1;
        if (fl < 0) fl = getenv("RN_FLOWLOG") != NULL;
        if (fl) rn_log("flow open %s", name);
    }
    set_error(c, 0);
    return h;
}
static uint32_t CreateFileA_(Ctx *c) { return create_file(c, G(ARG(0))); }
static uint32_t ReadFile_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    uint32_t buf = ARG(1), n = ARG(2), got = ARG(3);
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (ARG(4)) { rn_halt(c, "ReadFile with OVERLAPPED"); return 0; }
    if (bad_range(c, buf, n)) { rn_halt(c, "ReadFile buffer %08x+%u", buf, n); return 0; }
    int64_t r = gf_read(h->gf, h->pos, (uint8_t *)G(buf), n);
    if (r < 0) { rn_halt(c, "ReadFile I/O error on %s", h->path); return 0; }
    h->pos += (uint32_t)r;
    if (got) st(c, got, (uint32_t)r, 4);
    return 1;
}
static uint32_t WriteFile_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    uint32_t buf = ARG(1), n = ARG(2), put = ARG(3);
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (ARG(4)) { rn_halt(c, "WriteFile with OVERLAPPED"); return 0; }
    if (!gf_is_save(h->gf)) { set_error(c, 5); return 0; }        // opened for reading only
    if (bad_range(c, buf, n)) { rn_halt(c, "WriteFile buffer %08x+%u", buf, n); return 0; }
    if (gf_write(h->gf, h->pos, (const uint8_t *)G(buf), n) < 0) { set_error(c, 5); return 0; }
    h->pos += n;
    if (put) st(c, put, n, 4);
    return 1;
}
static uint32_t SetEndOfFile_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (gf_truncate(h->gf, h->pos)) { set_error(c, 5); return 0; }
    return 1;
}
static uint32_t FlushFileBuffers_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (gf_flush(h->gf)) { rn_halt(c, "FlushFileBuffers: cannot write %s", h->path); return 0; }
    return 1;
}
static uint32_t CreateDirectoryA_(Ctx *c) {
    const char *name = G(ARG(0));
    int r = gf_mkdir(name);
    if (r == -2) { rn_halt(c, "CreateDirectoryA outside the save folder: %s", name); return 0; }
    if (r) { set_error(c, r == 1 ? ERROR_ALREADY_EXISTS : ERROR_PATH_NOT_FOUND); return 0; }
    if (rn_trace()) rn_log("mkdir %s", name);
    return 1;
}
static uint32_t DeleteFileA_(Ctx *c) {
    const char *name = G(ARG(0));
    int r = gf_delete(name);
    if (r == -2) { set_error(c, 5); return 0; }                     // the game folder is read-only
    if (r) { set_error(c, ERROR_FILE_NOT_FOUND); return 0; }
    return 1;
}
// FindFirstFileA(pattern, WIN32_FIND_DATAA*): 320 bytes; attributes, 3 FILETIMEs, size hi/lo, 2 reserved,
// cFileName[260] at 44, cAlternateFileName[14] at 304. The game imports no FindNextFileA.
static uint32_t FindFirstFileA_(Ctx *c) {
    const char *pat = G(ARG(0));
    uint32_t fd = ARG(1);
    char name[260];
    int dir = 0;
    uint64_t size = 0;
    int r = gf_find(pat, name, sizeof name, &dir, &size);
    if (r == -2) { rn_halt(c, "FindFirstFileA outside the game and save folders: %s", pat); return INVALID_HANDLE; }
    if (rn_trace()) rn_log("find %s -> %s", pat, r ? "none" : name);
    if (r) { set_error(c, ERROR_FILE_NOT_FOUND); return INVALID_HANDLE; }
    uint32_t fh = new_handle(H_FIND);
    if (!fh) { set_error(c, ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE; }
    memset(G(fd), 0, 320);
    st(c, fd, dir ? 0x10 : 0x20, 4);                                 // FILE_ATTRIBUTE_DIRECTORY / ARCHIVE
    st(c, fd + 32, (uint32_t)size, 4);
    memcpy(G(fd + 44), name, strlen(name) + 1);
    return fh;
}
static uint32_t FindClose_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_FIND) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    h->kind = H_FREE;
    return 1;
}
// File mappings, read-only: the view is a private copy of the file in fresh guest memory.
static uint32_t CreateFileMappingA_(Ctx *c) {
    Handle *f = get_handle(ARG(0));
    uint32_t prot = ARG(2);
    if (!f || f->kind != H_FILE) { rn_halt(c, "CreateFileMappingA without a file (%08x)", ARG(0)); return 0; }
    if (prot != 2) { rn_halt(c, "CreateFileMappingA protect %#x (only PAGE_READONLY)", prot); return 0; }
    uint32_t h = new_handle(H_MAPPING);
    if (!h) { set_error(c, ERROR_NOT_ENOUGH_MEMORY); return 0; }
    get_handle(h)->gf = f->gf;
    return h;
}
static uint32_t MapViewOfFile_(Ctx *c) {
    Handle *m = get_handle(ARG(0));
    uint32_t off = ARG(3), n = ARG(4);
    if (!m || m->kind != H_MAPPING) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (ARG(2)) { rn_halt(c, "MapViewOfFile beyond 4 GB"); return 0; }
    uint64_t size = gf_size(m->gf);
    if (!n) n = (uint32_t)(size - off);
    uint32_t p = virtual_reserve(c, n);
    if (!p) { set_error(c, ERROR_NOT_ENOUGH_MEMORY); return 0; }
    if (gf_read(m->gf, off, (uint8_t *)G(p), n) < 0) { rn_halt(c, "MapViewOfFile: I/O error"); return 0; }
    return p;
}
static uint32_t UnmapViewOfFile_(Ctx *c) { (void)c; return 1; }   // address space is not reused (VirtualFree)

static uint32_t SetFilePointer_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    int32_t dist = (int32_t)ARG(1);
    uint32_t hi = ARG(2), how = ARG(3);
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return INVALID_HANDLE; }
    if (hi && ld(c, hi, 4) != 0 && ld(c, hi, 4) != 0xffffffffu) { rn_halt(c, "SetFilePointer beyond 4 GB"); return 0; }
    int64_t base = how == 0 ? 0 : how == 1 ? (int64_t)h->pos : (int64_t)gf_size(h->gf);
    int64_t to = base + dist;
    if (to < 0) { set_error(c, 131); return INVALID_HANDLE; }    // ERROR_NEGATIVE_SEEK
    h->pos = (uint32_t)to;
    if (hi) st(c, hi, 0, 4);
    return h->pos;
}
static uint32_t GetFileSize_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_FILE) { set_error(c, ERROR_INVALID_HANDLE); return INVALID_HANDLE; }
    if (ARG(1)) st(c, ARG(1), 0, 4);
    return (uint32_t)gf_size(h->gf);
}
static uint32_t CloseHandle_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (h->kind == H_FILE) gf_close(h->gf);    // a mapping shares the file id; the file handle owns it
    if (h->dir) closedir(h->dir);
    h->kind = H_FREE;
    return 1;
}
static uint32_t GetFullPathNameA_(Ctx *c) {
    const char *name = G(ARG(0));
    uint32_t n = ARG(1), buf = ARG(2), part = ARG(3);
    char full[600];
    if (name[0] && name[1] == ':') snprintf(full, sizeof full, "%s", name);
    else if (name[0] == '\\') snprintf(full, sizeof full, "C:%s", name);
    else snprintf(full, sizeof full, "%s\\%s", GAME_DIR, name[0] == '.' && name[1] == '\\' ? name + 2 : name);
    uint32_t len = (uint32_t)strlen(full);
    if (n <= len) return len + 1;
    memcpy(G(buf), full, len + 1);
    if (part) { char *s = strrchr(G(buf), '\\'); st(c, part, s ? buf + (uint32_t)(s - G(buf)) + 1 : buf, 4); }
    return len;
}
// Every name on this PC is already long; the path must exist. Same buffer in and out is allowed.
static uint32_t GetLongPathNameA_(Ctx *c) {
    uint32_t src = ARG(0), dst = ARG(1), n = ARG(2);
    char p[600];
    snprintf(p, sizeof p, "%s", G(src));
    int r = gf_stat(p);
    if (r == -2) { rn_halt(c, "GetLongPathNameA outside the game folder: %s", p); return 0; }
    if (r < 0) { set_error(c, ERROR_FILE_NOT_FOUND); return 0; }
    uint32_t len = (uint32_t)strlen(p);
    if (n <= len) return len + 1;
    memcpy(G(dst), p, len + 1);
    return len;
}

// Toolhelp: the process list holds this process only.
static uint32_t CreateToolhelp32Snapshot_(Ctx *c) {
    if (ARG(0) != 2) { rn_halt(c, "CreateToolhelp32Snapshot flags %08x", ARG(0)); return INVALID_HANDLE; }
    uint32_t h = new_handle(H_SNAPSHOT);
    if (!h) { set_error(c, ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE; }
    return h;
}
static uint32_t process_entry(Ctx *c, int first) {
    Handle *h = get_handle(ARG(0));
    uint32_t p = ARG(1);
    if (!h || h->kind != H_SNAPSHOT) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
    if (ld(c, p, 4) < 296) { set_error(c, 24); return 0; }
    if (first) h->signaled = 0;
    if (h->signaled++) { set_error(c, ERROR_NO_MORE_FILES); return 0; }
    memset(G(p + 4), 0, 292);
    st(c, p + 8, ld(c, c->fs + 0x20, 4), 4);      // th32ProcessID
    st(c, p + 20, 1, 4);                          // cntThreads
    st(c, p + 28, 8, 4);                          // pcPriClassBase: normal
    put_str(c, p + 36, "Speed.exe");
    return 1;
}
static uint32_t Process32First_(Ctx *c) { return process_entry(c, 1); }
static uint32_t Process32Next_(Ctx *c) { return process_entry(c, 0); }

static uint32_t GetProcessAffinityMask_(Ctx *c) { st(c, ARG(1), 1, 4); st(c, ARG(2), 1, 4); return 1; }
static uint32_t SetProcessAffinityMask_(Ctx *c) { (void)c; return 1; }
static uint32_t GetPriorityClass_(Ctx *c) { (void)c; return 0x20; }
static uint32_t SetPriorityClass_(Ctx *c) { (void)c; return 1; }
static uint32_t GetThreadPriority_(Ctx *c) { (void)c; return 0; }
static uint32_t SetThreadPriority_(Ctx *c) { (void)c; return 1; }

// =================================== winmm =====================================================
static uint32_t timeGetTime_(Ctx *c) { rn_telem.clock_calls++; clk_site(c); gil_clock(); return (uint32_t)(game_now_us() / 1000); }
static uint32_t timeBeginPeriod_(Ctx *c) { (void)c; return 0; }
static uint32_t timeEndPeriod_(Ctx *c) { (void)c; return 0; }
static uint32_t timeGetDevCaps_(Ctx *c) { st(c, ARG(0), 1, 4); st(c, ARG(0) + 4, 1000000, 4); return 0; }

// =================================== advapi32 ==================================================
// The registry of this PC: Windows XP with DirectX 9, the game installed at C:\NFSU from the disc in D:.
// Game values are the ones the installer on the disc (AutoRun.exe 0x40e9bb-0x40ec99, 0x40fbe5, 0x40fd85)
// writes for a full install, from AutoRun\autorun.cfg: Install Dir = GetShortPathName(dir) + "\",
// CD Drive = the source drive + "\", Language = the language name (NumLanguages=1: "English UK"),
// CacheSize/SwapSize = "%I64d" of bytes / 1024 (CacheFull=1296003, SwapSize=0). It never writes
// StreamingInstall. Speed.exe (SKU 0, 0x401190) opens "Need For Speed Underground", not the
// "NFS Underground" of autorun.cfg, so the values sit under the key Speed.exe opens.
// ~MHz is the CPU we present: rn_rdtsc counts at 1 GHz.
#define ERROR_MORE_DATA 234
#define HKLM 0x80000002u
typedef struct { const char *key, *name; uint32_t type; const char *sz; uint32_t dw; } RegValue;
static const RegValue registry[] = {
    {"Software\\EA Games\\Need For Speed Underground", "Install Dir", 1, "C:\\NFSU\\", 0},
    {"Software\\EA Games\\Need For Speed Underground", "CD Drive", 1, "D:\\", 0},
    {"Software\\EA Games\\Need For Speed Underground", "Language", 1, "English UK", 0},
    {"Software\\EA Games\\Need For Speed Underground", "CacheSize", 1, "1296003", 0},
    {"Software\\EA Games\\Need For Speed Underground", "SwapSize", 1, "0", 0},
    {"Software\\Microsoft\\Direct3D", NULL, 0, NULL, 0},
    {"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0", "~MHz", 4, NULL, 1000},
};
#define NREG (int)(sizeof registry / sizeof registry[0])

// HKLM\<path> exists when it is a listed key or a parent of one. Names match without case.
static int key_exists(const char *path) {
    size_t n = strlen(path);
    if (!n) return 1;
    for (int k = 0; k < NREG; k++) {
        const char *key = registry[k].key;
        if (!strncasecmp(key, path, n) && (!key[n] || key[n] == '\\')) return 1;
    }
    return 0;
}
static uint32_t open_key(Ctx *c, uint32_t parent, uint32_t sub, uint32_t out) {
    char path[512] = "";
    const char *name = sub ? G(sub) : "";
    if (parent != HKLM) {
        Handle *h = get_handle(parent);
        if (!h || h->kind != H_KEY) {
            if (parent < 0x80000000u || parent > 0x80000006u) return ERROR_INVALID_HANDLE;
            if (rn_trace()) rn_log("registry: open %08x\\%s -> not found", parent, name);
            return ERROR_FILE_NOT_FOUND;        // other hives hold nothing the game asks for
        }
        snprintf(path, sizeof path, "%s", h->path);
    }
    if (*name == '\\') name++;
    if (*name) snprintf(path + strlen(path), sizeof path - strlen(path), "%s%s", *path ? "\\" : "", name);
    if (!key_exists(path)) {
        if (rn_trace()) rn_log("registry: open HKLM\\%s -> not found", path);
        return ERROR_FILE_NOT_FOUND;
    }
    uint32_t h = new_handle(H_KEY);
    if (!h) { rn_halt(c, "out of handles"); return ERROR_NOT_ENOUGH_MEMORY; }
    snprintf(get_handle(h)->path, sizeof get_handle(h)->path, "%s", path);
    st(c, out, h, 4);
    return 0;
}
static uint32_t RegOpenKeyExA_(Ctx *c) { return open_key(c, ARG(0), ARG(1), ARG(4)); }
static uint32_t RegOpenKeyA_(Ctx *c) { return open_key(c, ARG(0), ARG(1), ARG(2)); }
static uint32_t RegQueryValueExA_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    uint32_t vname = ARG(1), ptype = ARG(3), data = ARG(4), psize = ARG(5);
    if (!h || h->kind != H_KEY) return ERROR_INVALID_HANDLE;
    const char *name = vname ? G(vname) : "";
    const RegValue *v = NULL;
    for (int k = 0; k < NREG && !v; k++)
        if (registry[k].name && !strcasecmp(registry[k].key, h->path) && !strcasecmp(registry[k].name, name)) v = &registry[k];
    if (rn_trace()) rn_log("registry: HKLM\\%s \"%s\" -> %s", h->path, name, v ? (v->sz ? v->sz : "dword") : "not found");
    if (!v) return ERROR_FILE_NOT_FOUND;
    uint32_t len = v->type == 4 ? 4 : (uint32_t)strlen(v->sz) + 1;
    if (ptype) st(c, ptype, v->type, 4);
    if (!psize) return data ? 87 : 0;           // ERROR_INVALID_PARAMETER: data without a size
    uint32_t room = ld(c, psize, 4);
    st(c, psize, len, 4);
    if (!data) return 0;
    if (room < len) return ERROR_MORE_DATA;
    if (v->type == 4) st(c, data, v->dw, 4);
    else memcpy(G(data), v->sz, len);
    return 0;
}
static uint32_t RegCloseKey_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (ARG(0) >= 0x80000000u) return 0;
    if (!h || h->kind != H_KEY) return ERROR_INVALID_HANDLE;
    h->kind = H_FREE;
    return 0;
}

// SHGetFolderPathA(hwnd, csidl, hToken, dwFlags, pszPath): the folders Windows XP gives a default install.
// Only the CSIDL the game asks for is answered; any other one stops loudly.
static uint32_t SHGetFolderPathA_(Ctx *c) {
    uint32_t csidl = ARG(1) & 0xff, out = ARG(4);     // high bits: CSIDL_FLAG_CREATE and friends
    if (csidl != 0x23) { rn_halt(c, "SHGetFolderPathA(CSIDL %#x)", csidl); return 0x80004005u; }
    put_str(c, out, "C:\\Documents and Settings\\All Users\\Application Data");   // CSIDL_COMMON_APPDATA
    return 0;                                           // S_OK
}

// ---- date and time text: English (United Kingdom), the language the install writes; the time zone is GMT ----
// SYSTEMTIME: wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute, wSecond, wMilliseconds (u16 each).
static void now_systemtime(uint16_t t[8]) {
    time_t now = time(NULL);
    struct tm g;
    gmtime_r(&now, &g);
    uint16_t v[8] = {(uint16_t)(g.tm_year + 1900), (uint16_t)(g.tm_mon + 1), (uint16_t)g.tm_wday, (uint16_t)g.tm_mday,
                     (uint16_t)g.tm_hour, (uint16_t)g.tm_min, (uint16_t)g.tm_sec, 0};
    memcpy(t, v, sizeof v);
}
// A date/time picture (d dd ddd dddd M MM MMM MMMM y yy yyyy h hh H HH m mm s ss t tt, 'quoted text').
static int picture(const char *f, const uint16_t t[8], char *out, int n) {
    static const char *mon[] = {"January", "February", "March", "April", "May", "June", "July", "August", "September",
                                "October", "November", "December"};
    static const char *day[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
    int o = 0;
    char tmp[32];
    while (*f && o < n - 1) {
        char ch = *f;
        int k = 1;
        if (ch == '\'') {
            for (f++; *f && *f != '\'' && o < n - 1; f++) out[o++] = *f;
            if (*f) f++;
            continue;
        }
        while (f[k] == ch) k++;
        tmp[0] = 0;
        int h12 = t[4] % 12 ? t[4] % 12 : 12;
        switch (ch) {
        case 'd': if (k <= 2) snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[3]);
                  else snprintf(tmp, sizeof tmp, "%.*s", k == 3 ? 3 : 20, day[t[2] % 7]); break;
        case 'M': if (k <= 2) snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[1]);
                  else snprintf(tmp, sizeof tmp, "%.*s", k == 3 ? 3 : 20, mon[(t[1] + 11) % 12]); break;
        case 'y': if (k <= 2) snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[0] % 100);
                  else snprintf(tmp, sizeof tmp, "%u", t[0]); break;
        case 'h': snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", h12); break;
        case 'H': snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[4]); break;
        case 'm': snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[5]); break;
        case 's': snprintf(tmp, sizeof tmp, k == 1 ? "%u" : "%02u", t[6]); break;
        case 't': snprintf(tmp, sizeof tmp, "%.*s", k == 1 ? 1 : 2, t[4] < 12 ? "AM" : "PM"); break;
        default: k = 1; tmp[0] = ch; tmp[1] = 0;
        }
        f += k;
        for (char *q = tmp; *q && o < n - 1; q++) out[o++] = *q;
    }
    out[o] = 0;
    return o;
}
// Get{Date,Time}FormatA(locale, flags, SYSTEMTIME*, format, out, size): chars written with the NUL, or the
// size needed when size is 0. DATE_LONGDATE = 2; TIME_NOSECONDS = 2, TIME_NOMINUTESORSECONDS = 1.
static uint32_t date_time_format(Ctx *c, int date) {
    uint32_t flags = ARG(1), tp = ARG(2), fmt = ARG(3), out = ARG(4), n = ARG(5);
    uint16_t t[8];
    if (tp) for (int k = 0; k < 8; k++) t[k] = (uint16_t)ld(c, tp + 2 * k, 2); else now_systemtime(t);
    const char *f = fmt ? G(fmt) : date ? (flags & 2 ? "dd MMMM yyyy" : "dd/MM/yyyy")
                                        : (flags & 1 ? "HH" : flags & 2 ? "HH:mm" : "HH:mm:ss");
    char buf[256];
    int len = picture(f, t, buf, sizeof buf) + 1;
    if (!n) return (uint32_t)len;
    if ((uint32_t)len > n) { set_error(c, 122); return 0; }      // ERROR_INSUFFICIENT_BUFFER
    memcpy(G(out), buf, (size_t)len);
    return (uint32_t)len;
}
static uint32_t GetDateFormatA_(Ctx *c) { return date_time_format(c, 1); }
static uint32_t GetTimeFormatA_(Ctx *c) { return date_time_format(c, 0); }

// ---- C runtime support ----------------------------------------------------------------------------
static uint32_t GetProcessHeap_(Ctx *c) {
    static uint32_t heap;
    if (!heap) { heap = new_handle(H_HEAP); st(c, PEB_ADDR + 0x18, heap, 4); }
    return heap;
}
static uint32_t SetEnvironmentVariableA_(Ctx *c) { (void)c; return 1; }      // nothing reads it back
// EnumSystemLocalesA(callback, flags): the one installed locale, English (United Kingdom).
static uint32_t EnumSystemLocalesA_(Ctx *c) {
    static uint32_t str;
    if (!str) { str = virtual_reserve(c, 16); put_str(c, str, "00000809"); }
    uint32_t fn = ARG(0);
    call_guest(c, fn, 1, &str);
    return 1;
}
// No console is attached to a GUI program.
static uint32_t no_console(Ctx *c) { set_error(c, ERROR_INVALID_HANDLE); return 0; }
static uint32_t RaiseException_(Ctx *c) {
    rn_halt(c, "RaiseException code %08x flags %x (%u args)", ARG(0), ARG(1), ARG(2));
    return 0;
}
static uint32_t RtlUnwind_(Ctx *c) { rn_halt(c, "RtlUnwind (exception unwinding)"); return 0; }
static uint32_t UnhandledExceptionFilter_(Ctx *c) { rn_halt(c, "UnhandledExceptionFilter"); return 0; }
static uint32_t TerminateProcess_(Ctx *c) { rn_halt(c, "TerminateProcess(%u): the game quit", ARG(1)); return 0; }
// CreateFileW: the UTF-16 name narrowed (game paths are ASCII).
static uint32_t CreateFileW_(Ctx *c) {
    uint32_t w = ARG(0), k = 0;
    char name[512];
    for (uint16_t ch; (ch = (uint16_t)ld(c, w + 2 * k, 2)) && k < sizeof name - 1; k++) {
        if (ch > 0x7f) { rn_halt(c, "CreateFileW with a non-ASCII name"); return INVALID_HANDLE; }
        name[k] = (char)ch;
    }
    name[k] = 0;
    return create_file(c, name);
}
// Serial ports and modems: this PC has none. Handles to them can never be opened.
static uint32_t no_comm(Ctx *c) { set_error(c, ERROR_INVALID_HANDLE); return 0; }

static uint32_t entry_returned(Ctx *c) { rn_halt(c, "entry point returned eax=%08x", c->r[EAX]); return 0; }

#define K(name, n) {"kernel32.dll", #name, n, name##_}
const Api win32_apis[] = {
    {"rn", "entry_returned", 0, entry_returned},
    K(GetVersion, 0), K(GetVersionExA, 1), K(GetCommandLineA, 0),
    {"kernel32.dll", "GetEnvironmentStrings", 0, GetEnvironmentStrings_},
    {"kernel32.dll", "GetEnvironmentStringsA", 0, GetEnvironmentStrings_},
    {"kernel32.dll", "FreeEnvironmentStringsA", 1, FreeEnvironmentStrings_},
    K(GetEnvironmentStringsW, 0), K(FreeEnvironmentStringsW, 1),
    K(GetModuleFileNameA, 3), K(GetStartupInfoA, 1), K(GetStdHandle, 1), K(SetStdHandle, 2), K(GetFileType, 1),
    K(SetHandleCount, 1), K(GetACP, 0), K(GetOEMCP, 0), K(IsValidCodePage, 1), K(GetCPInfo, 2),
    K(MultiByteToWideChar, 6), K(WideCharToMultiByte, 8), K(GetStringTypeW, 4), K(GetStringTypeA, 5),
    K(LCMapStringW, 6), K(LCMapStringA, 6), K(CompareStringA, 6), K(CompareStringW, 6), K(lstrcmpiA, 2), K(lstrcmpA, 2),
    K(GetLocaleInfoA, 4), K(GetLocaleInfoW, 4), K(GetUserDefaultLCID, 0), K(IsValidLocale, 2),
    K(HeapCreate, 3), K(HeapDestroy, 1), K(HeapAlloc, 3), K(HeapFree, 3), K(HeapSize, 3), K(HeapReAlloc, 4),
    K(VirtualAlloc, 4), K(VirtualFree, 3), K(VirtualQuery, 3), K(VirtualProtect, 4),
    K(TlsAlloc, 0), K(TlsFree, 1), K(TlsGetValue, 1), K(TlsSetValue, 2),
    K(InterlockedExchange, 2), K(GetCurrentProcess, 0), K(GetCurrentThread, 0), K(GetCurrentProcessId, 0),
    K(GetLastError, 0), K(SetLastError, 1), K(SetUnhandledExceptionFilter, 1),
    K(SetErrorMode, 1), K(IsBadReadPtr, 2), {"kernel32.dll", "IsBadWritePtr", 2, IsBadReadPtr_}, K(IsBadCodePtr, 1),
    K(GetSystemInfo, 1), K(IsProcessorFeaturePresent, 1), K(GetTickCount, 0), K(QueryPerformanceCounter, 1), K(QueryPerformanceFrequency, 1),
    K(GetSystemTimeAsFileTime, 1), K(GetTimeZoneInformation, 1), K(ExitProcess, 1), K(OutputDebugStringA, 1),
    K(GetModuleHandleA, 1), K(LoadLibraryA, 1), K(GetProcAddress, 2),
    K(CreateFileA, 7), K(ReadFile, 5), K(WriteFile, 5), K(SetEndOfFile, 1), K(FlushFileBuffers, 1),
    K(CreateDirectoryA, 2), K(DeleteFileA, 1), K(FindFirstFileA, 2), K(FindClose, 1),
    K(CreateFileMappingA, 6), K(MapViewOfFile, 5), K(UnmapViewOfFile, 1), K(SetFilePointer, 4), K(GetFileSize, 2), K(CloseHandle, 1), K(GetFullPathNameA, 4), K(GetLongPathNameA, 3),
    K(GetProcessAffinityMask, 3), K(SetProcessAffinityMask, 2), K(GetPriorityClass, 1), K(SetPriorityClass, 2),
    K(GetThreadPriority, 1), K(SetThreadPriority, 2),
    K(CreateToolhelp32Snapshot, 2), K(Process32First, 2), K(Process32Next, 2),
    {"winmm.dll", "timeGetTime", 0, timeGetTime_}, {"winmm.dll", "timeBeginPeriod", 1, timeBeginPeriod_},
    {"winmm.dll", "timeEndPeriod", 1, timeEndPeriod_}, {"winmm.dll", "timeGetDevCaps", 2, timeGetDevCaps_},
    {"advapi32.dll", "RegOpenKeyExA", 5, RegOpenKeyExA_}, {"advapi32.dll", "RegOpenKeyA", 3, RegOpenKeyA_},
    {"advapi32.dll", "RegQueryValueExA", 6, RegQueryValueExA_}, {"advapi32.dll", "RegCloseKey", 1, RegCloseKey_},
    {"shfolder.dll", "SHGetFolderPathA", 5, SHGetFolderPathA_},
    K(GetDateFormatA, 6), K(GetTimeFormatA, 6), K(GetProcessHeap, 0), K(SetEnvironmentVariableA, 2),
    K(EnumSystemLocalesA, 2), K(RaiseException, 4), K(RtlUnwind, 4), K(UnhandledExceptionFilter, 1),
    K(TerminateProcess, 2), K(CreateFileW, 7),
    {"kernel32.dll", "GetConsoleMode", 2, no_console}, {"kernel32.dll", "GetNumberOfConsoleInputEvents", 2, no_console},
    {"kernel32.dll", "PeekConsoleInputA", 4, no_console},
    {"kernel32.dll", "GetCommConfig", 3, no_comm}, {"kernel32.dll", "GetCommState", 2, no_comm},
    {"kernel32.dll", "SetCommConfig", 3, no_comm}, {"kernel32.dll", "SetCommState", 2, no_comm},
    {"kernel32.dll", "SetCommMask", 2, no_comm}, {"kernel32.dll", "SetCommTimeouts", 2, no_comm},
    {"kernel32.dll", "SetupComm", 3, no_comm}, {"kernel32.dll", "PurgeComm", 2, no_comm},
    {"kernel32.dll", "WaitCommEvent", 3, no_comm}, {"kernel32.dll", "GetOverlappedResult", 4, no_comm},
};
const int win32_api_count = sizeof win32_apis / sizeof win32_apis[0];

int rn_screen_w = 1920, rn_screen_h = 1080;

void win32_init(Ctx *c, uint32_t image_size) {
    int sw, sh;
    const char *scr = getenv("RN_SCREEN");
    if (scr && sscanf(scr, "%dx%d", &sw, &sh) == 2 && sw >= 400 && sh >= 240 && sw <= 7680 && sh <= 4320) {
        rn_screen_w = sw & ~1; rn_screen_h = sh & ~1;
    }
    st(c, SCREEN_ADDR, rn_screen_w, 4); st(c, SCREEN_ADDR + 4, rn_screen_h, 4);
    float s43 = 4.f * (float)rn_screen_h / (3.f * (float)rn_screen_w);
    if (s43 > 1.f) s43 = 1.f;
    float k[2] = {s43 / 320.f, s43};
    memcpy(G(SCREEN_ADDR + 8), k, sizeof k);
    const char *seed = getenv("RN_SEED");     // PATCH 0x4470f0: test-only fixed RNG seed (A/B vs Wine); 0 = the clock
    st(c, SCREEN_ADDR + 16, seed ? (uint32_t)strtoul(seed, NULL, 0) : 0, 4);
    st(c, SCREEN_ADDR + 20, getenv("RN_AUTOPILOT") != NULL, 4);   // PATCH 0x42d4b0: test-only, the AI drives the player
    st(c, SCREEN_ADDR + 24, getenv("RN_AUTOPILOT") ? 4 : 3, 4);  // PATCH 0x42d4a9: drag player mode, 4 = autopilot, 3 = drag (original)
    const char *tr = getenv("RN_TRAFFIC");     // PATCH 0x57d060 (cave 0x63b270): 1 = full traffic pool, 0 = original
    st(c, SCREEN_ADDR + 28, !(tr && tr[0] == '0'), 4);
    st(c, SCREEN_ADDR + 0x60, host_addr_of("rn", "rival_ride"), 4);   // PATCH 0x4b4321: rivals (RN_RIVALS=0 = original)
    st(c, SCREEN_ADDR + 0x64, host_addr_of("rn", "car_draw"), 4);     // PATCH 0x57119a: racers at LOD A (RN_CARLOD=0 = original)
    st(c, SCREEN_ADDR + 0x68, host_addr_of("rn", "free_setup"), 4);   // PATCH 0x4b528d: free mode rivals (RN_FREE=0 = original)
    st(c, SCREEN_ADDR + 0x6c, host_addr_of("rn", "free_traffic"), 4); // PATCH 0x4b3c2f: free mode tuned traffic
    st(c, SCREEN_ADDR + 0x7c, host_addr_of("rn", "free_place"), 4);   // PATCH 0x422b36: the traffic placer, logged
    st(c, SCREEN_ADDR + 0x80, host_addr_of("rn", "free_spacing"), 4); // PATCH 0x598774: free mode traffic spacing
    st(c, SCREEN_ADDR + 0x84, host_addr_of("rn", "free_nopath"), 4);  // PATCH 0x5833eb: free mode retries no-path traffic
    st(c, SCREEN_ADDR + 0x88, host_addr_of("rn", "free_tnode"), 4);   // PATCH 0x59a5cf, 0x59a669: free mode traffic on every node
    st(c, SCREEN_ADDR + 0x8c, host_addr_of("rn", "free_recycle"), 4); // PATCH 0x5987f6: free mode moves cars that drove far away
    st(c, SCREEN_ADDR + 0x90, host_addr_of("rn", "free_hud"), 4);     // PATCH 0x430dbd: free mode HUD without WRONG WAY and the gap
    st(c, SCREEN_ADDR + 0x94, host_addr_of("rn", "free_jumpcam"), 4); // PATCH 0x426dd7, 0x4662e0: free mode picks a jump-camera eye with a clear view, or keeps the chase camera
    st(c, SCREEN_ADDR + 0x98, host_addr_of("rn", "traffic_behind"), 4); // PATCH 0x45399f: a traffic car sees the player closing from behind (RN_TRAFYIELD=0 = original)
    st(c, SCREEN_ADDR + 0xb0, host_addr_of("rn", "persona_step"), 4);  // PATCH 0x44c573: rival personalities with ?pool=1 or RN_AI=2 (RN_AI=0 = original)
    st(c, SCREEN_ADDR + 0xb4, host_addr_of("rn", "persona_clear"), 4); // PATCH 0x45c8c2: clean rivals pass wide (personalities on)
    st(c, SCREEN_ADDR + 0xb8, host_addr_of("rn", "neon_pass"), 4);     // PATCH 0x56f21e: neon puddle (?pool=1)
    st(c, SCREEN_ADDR + 0xa4, host_addr_of("rn", "horn_start"), 4);   // PATCH 0x52536a: traffic horn probe/fix (RN_HORNLOG / RN_HORNFIX, off)

    lights_init(c);                            // host/lights.c: live brake lights (RN_LIGHTS=0 = original)
    const char *steer = getenv("RN_STEER");    // PATCH 0x460a80: 1 = the keys steer through the game's gamepad model
    st(c, SCREEN_ADDR + 32, steer && !strcmp(steer, "pad"), 4);
    // PATCH 0x63b370 (the 22 reads of the career-beaten flag) and PATCH 0x735ec1 (debug byte): 1 = everything open (the
    // default, OWNER 2026-10-20), RN_UNLOCK=0 = the normal Underground, locks and money as shipped (OWNER 2026-10-27).
    const char *un = getenv("RN_UNLOCK");
    int unlock = !(un && un[0] == '0');
    st(c, SCREEN_ADDR + 36, unlock, 4);
    st(c, 0x735ec1, unlock, 1);
    // FEEL C1 + C3 (OWNER 2026-11-04: feel changes in remaster only; RN_FEEL=0 in original mode, web/mode.js): the second blur pass
    // scale [0x707fd0] (PATCH 0x40cfb9.., shipped 4.0) becomes 1.0, and the chase FOV table 0x6fbdf4 POV 0/1/4 goes 0x32dc -> 0x2ee0.
    const char *feel = getenv("RN_FEEL");
    if (!(feel && feel[0] == '0')) {
        st(c, 0x707fd0, 0, 4); st(c, 0x707fd4, 0x3ff00000, 4);
        st(c, 0x6fbdf4, 0x2ee0, 2); st(c, 0x6fbdf6, 0x2ee0, 2); st(c, 0x6fbdfc, 0x2ee0, 2);
    }
    // REMASTER wall feel: 0x46bae0 uses [0x6b7254] only when 0x46c620 identifies a grazing wall contact; zero removes e=0.05 rebound.
    const char *wallsoften = getenv("RN_WALLSOFTEN");
    if (wallsoften && wallsoften[0] != '0') st(c, 0x6b7254, 0, 4);
    // PATCH 0x410c1b (cave 0x63b3ad): the cap of ROADREFLECTION [0x70105c] is at most this word (2 = as shipped; 1 with
    // RN_ROADREFL=off / ?roadrefl=off: the game's own level 1, the mirrored world is not drawn). sq / cube: host/sm1.c.
    st(c, SCREEN_ADDR + 0x70, sm1_roadrefl() == 3 ? 1 : 2, 4);
    clock_gettime(CLOCK_MONOTONIC, &t0);
#ifdef __EMSCRIPTEN__
    t0_ms = emscripten_get_now();
#endif
    brk_ptr = HEAP_LO;
    vtop = c->memsz;
    (void)image_size;
    st(c, PEB_ADDR + 0x08, IMAGE_BASE, 4);
    st(c, PEB_ADDR + 0x18, 0, 4);             // process heap: set by HeapCreate users
    char cmd[300];
    snprintf(cmd, sizeof cmd, "\"%s\"", MODULE_PATH);
    put_str(c, STR_ADDR, cmd);
    // Environment block: "name=value\0...\0\0".
    static const char env[] = "PATH=C:\\WINDOWS\\system32;C:\\WINDOWS\0SystemRoot=C:\\WINDOWS\0windir=C:\\WINDOWS\0\0";
    memcpy(G(STR_ADDR + 0x400), env, sizeof env);
}
