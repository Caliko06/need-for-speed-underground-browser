// Loads pc/Speed.exe into guest memory the way the Windows loader does, then runs its entry point.
// Usage: speed <Speed.exe> <game dir> [--shot frame.png]
// Native runs end after RN_SECS seconds (default 60, 0 = no limit), so no run is ever unbounded.
#include "host.h"
#include "gpu.h"
#include <pthread.h>
#include <unistd.h>

Ctx *g_ctx;
void dispatch_report(void);
void win32_set_root(const char *game_dir);
extern const uint32_t rn_patch_count, rn_patch_addr[];
extern const char *const rn_patch_hex[];

static uint8_t *read_file(const char *path, long *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *p = malloc(*size);
    if (fread(p, 1, *size, f) != (size_t)*size) { fclose(f); free(p); return NULL; }
    fclose(f);
    return p;
}

// Return addresses on the guest stack: values in .text that follow a call instruction.
static void backtrace(Ctx *c) {
    char line[256] = "";
    int n = 0;
    uint32_t hi = ld(c, c->fs + 4, 4);
    for (uint32_t a = c->r[ESP]; a + 4 <= hi && n < 12; a += 4) {
        uint32_t v = ld(c, a, 4);
        if (v < 0x401006 || v >= 0x697000) continue;
        const uint8_t *p = c->mem + v;
        if (p[-5] == 0xe8 || (p[-2] == 0xff && (p[-1] & 0x38) == 0x10) || (p[-6] == 0xff && (p[-5] & 0x38) == 0x10) ||
            (p[-3] == 0xff && (p[-2] & 0x38) == 0x10) || (p[-7] == 0xff && (p[-6] & 0x38) == 0x10)) {
            snprintf(line + strlen(line), sizeof line - strlen(line), " %08x", v);
            n++;
        }
    }
    rn_log("stack:%s", line);
}

#ifndef __EMSCRIPTEN__
static void *watchdog(void *arg) {
    unsigned secs = (unsigned)(uintptr_t)arg;
    sleep(secs);
    dispatch_report();
    rn_log("RN_SECS: stopped after %u s (no stop reached)", secs);
    _exit(0);
}

#endif

// RN_WATCH=70fe28,77a920: every 250 ms, log each listed dword of guest memory (read without the GIL; a counter
// needs no lock). The same addresses can be read in the Wine reference through /proc/PID/mem (tools/wine/memwatch.py).
// 7345d0>20 reads [[0x7345d0]+0x20] (a field of a heap object; 0 while the pointer is 0); 78a418>10+750*26 reads that
// field in 26 records 0x750 apart (the type of each race ride: list [0x78a418], count [0x78a41c]); 7602a0+454*27 reads
// 27 static records.
// RN_POKE=76778b=1,...: with RN_WATCH, also write each byte at every tick (a state a save cannot reach yet, such as a
// won magazine; the load overwrites it once, the next tick sets it again).
static void *memwatch(void *arg) {
    if (!arg) arg = "";
    uint32_t a[12], off[12], step[12], cnt[12], pa[12], pv[12]; int n = 0, np = 0;
    for (char *s = getenv("RN_POKE"); s && *s && np < 12; s += *s == ',') {
        pa[np] = (uint32_t)strtoul(s, &s, 16);
        if (*s == '=') pv[np++] = (uint32_t)strtoul(s + 1, &s, 16);
    }
    for (char *s = arg; *s && n < 12; s += *s == ',') {
        a[n] = (uint32_t)strtoul(s, &s, 16); off[n] = ~0u; step[n] = 0; cnt[n] = 1;
        if (*s == '>') off[n] = (uint32_t)strtoul(s + 1, &s, 16);
        if (*s == '+') { step[n] = (uint32_t)strtoul(s + 1, &s, 16); if (*s == '*') cnt[n] = (uint32_t)strtoul(s + 1, &s, 10); }
        n++;
    }
    uint64_t t0 = now_us();
    for (unsigned tick = 0;; tick++) {
        // RN_CARPOS=1: every 2 s, each car of the game's vehicle list L = [0x7361f8] (cars [L+0x28 + 4 i], i from L[9] to L[6], as
        // 0x41f680/0x41f690): index, kind ([[car+0x14]+4]: 1 player, 2 rival, 3 traffic), x y, and the driver V = car+0x2c flags
        // (+0x4d1 parked, +0x410 no path, +0x4d0). Where a traffic car sits when it stops (re_citygraph.md, step 3).
        if (getenv("RN_CARPOS") && tick % 8 == 0) {
            uint32_t L; memcpy(&L, g_ctx->mem + 0x7361f8, 4);
            if (L && L < GUEST_MEM - 0x2c) {
                uint32_t lo, hi; memcpy(&lo, g_ctx->mem + L + 0x24, 4); memcpy(&hi, g_ctx->mem + L + 0x18, 4);
                for (uint32_t i = lo; i < hi && i < lo + 64; i++) {
                    uint32_t r, e, v, kind = 0; float x, y;
                    memcpy(&r, g_ctx->mem + L + 0x28 + 4 * i, 4);
                    if (r < 0x10000 || r > GUEST_MEM - 0x900) continue;
                    memcpy(&e, g_ctx->mem + r + 0x14, 4); memcpy(&v, g_ctx->mem + r + 0x2c, 4);
                    if (e && e < GUEST_MEM - 8) memcpy(&kind, g_ctx->mem + e + 4, 4);
                    memcpy(&x, g_ctx->mem + r + 0x50, 4); memcpy(&y, g_ctx->mem + r + 0x54, 4);
                    rn_log("carpos %6.2f %u k%u %.1f %.1f%s%s%s", (now_us() - t0) / 1e6, i, kind, x, y,
                           v && v < GUEST_MEM - 0x4d2 && g_ctx->mem[v + 0x4d1] ? " P" : "", v && v < GUEST_MEM - 0x4d2 && g_ctx->mem[v + 0x410] ? " N" : "",
                           v && v < GUEST_MEM - 0x4d2 && g_ctx->mem[v + 0x4d0] ? " o" : "");
                }
            }
        }
        char line[1024]; int k = snprintf(line, sizeof line, "watch %6.2f", (now_us() - t0) / 1e6);
        if (!n && !np) { usleep(250000); continue; }
        for (int i = 0; i < n && k < (int)sizeof line - 64; i++) {
            uint32_t v, p; memcpy(&v, g_ctx->mem + a[i], 4); p = v;
            for (uint32_t j = 0; j < cnt[i]; j++) {
                if (off[i] != ~0u) { uint32_t q = p + off[i] + j * step[i]; v = 0; if (p && q < GUEST_MEM - 4) memcpy(&v, g_ctx->mem + q, 4); }
                else if (j) memcpy(&v, g_ctx->mem + a[i] + j * step[i], 4);   // 7602a0+454*27: 27 static records
                k += j ? snprintf(line + k, sizeof line - k, ",%u", v)
                   : off[i] == ~0u ? snprintf(line + k, sizeof line - k, " %x=%u", a[i], v)
                       : snprintf(line + k, sizeof line - k, " %x>%x=%u", a[i], off[i], v);
            }
        }
        rn_log("%s", line);
        for (int i = 0; i < np; i++) g_ctx->mem[pa[i]] = (uint8_t)pv[i];
        usleep(250000);
    }
}

// MD5 (RFC 1321), used once at boot to check the exe is the pc/Speed.exe the recompiled code was lifted from.
static void md5_hex(const uint8_t *msg, size_t len, char out[33]) {
    static const uint32_t K[64] = {
        0xd76aa478,0xe8c7b756,0x242070db,0xc1bdceee,0xf57c0faf,0x4787c62a,0xa8304613,0xfd469501,0x698098d8,0x8b44f7af,0xffff5bb1,0x895cd7be,0x6b901122,0xfd987193,0xa679438e,0x49b40821,
        0xf61e2562,0xc040b340,0x265e5a51,0xe9b6c7aa,0xd62f105d,0x02441453,0xd8a1e681,0xe7d3fbc8,0x21e1cde6,0xc33707d6,0xf4d50d87,0x455a14ed,0xa9e3e905,0xfcefa3f8,0x676f02d9,0x8d2a4c8a,
        0xfffa3942,0x8771f681,0x6d9d6122,0xfde5380c,0xa4beea44,0x4bdecfa9,0xf6bb4b60,0xbebfbc70,0x289b7ec6,0xeaa127fa,0xd4ef3085,0x04881d05,0xd9d4d039,0xe6db99e5,0x1fa27cf8,0xc4ac5665,
        0xf4292244,0x432aff97,0xab9423a7,0xfc93a039,0x655b59c3,0x8f0ccc92,0xffeff47d,0x85845dd1,0x6fa87e4f,0xfe2ce6e0,0xa3014314,0x4e0811a1,0xf7537e82,0xbd3af235,0x2ad7d2bb,0xeb86d391};
    static const uint8_t S[64] = {7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22, 5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,
                                  4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23, 6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21};
    uint32_t a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    size_t total = (len + 8) / 64 * 64 + 64;                       // data, 0x80, zeros, 64-bit bit length
    for (size_t off = 0; off < total; off += 64) {
        uint8_t blk[64];
        if (off + 64 <= len) memcpy(blk, msg + off, 64);
        else {
            memset(blk, 0, 64);
            if (off < len) memcpy(blk, msg + off, len - off);
            if (len >= off && len - off < 64) blk[len - off] = 0x80;
            if (off + 64 == total) { uint64_t bits = (uint64_t)len * 8; memcpy(blk + 56, &bits, 8); }   // little-endian host
        }
        uint32_t M[16], A = a0, B = b0, C = c0, D = d0;
        memcpy(M, blk, 64);
        for (int i = 0; i < 64; i++) {
            uint32_t F; int g;
            if (i < 16) { F = (B & C) | (~B & D); g = i; }
            else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) & 15; }
            else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) & 15; }
            else { F = C ^ (B | ~D); g = (7 * i) & 15; }
            F += A + K[i] + M[g];
            A = D; D = C; C = B; B += (F << S[i]) | (F >> (32 - S[i]));
        }
        a0 += A; b0 += B; c0 += C; d0 += D;
    }
    uint32_t h[4] = {a0, b0, c0, d0};
    for (int i = 0; i < 16; i++) snprintf(out + 2 * i, 3, "%02x", (h[i / 4] >> (8 * (i % 4))) & 0xff);
}

static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static uint16_t rd16(const uint8_t *p) { uint16_t v; memcpy(&v, p, 2); return v; }

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: speed <Speed.exe> <game dir>\n"); return 2; }
    long fsize;
    uint8_t *pe = read_file(argv[1], &fsize);
    if (!pe) { fprintf(stderr, "cannot read %s\n", argv[1]); return 2; }
    {
        char md5[33];
        md5_hex(pe, (size_t)fsize, md5);
        if (strcmp(md5, "b6b9232c55376b3c38c56aac1f8a121d")) {
            rn_log("ERROR: %s is not the expected Speed.exe: md5 %s, expected b6b9232c55376b3c38c56aac1f8a121d", argv[1], md5);
            fprintf(stderr, "wrong Speed.exe: md5 %s\n", md5);
            return 2;
        }
    }
    win32_set_root(argv[2]);
    if (argc > 4 && !strcmp(argv[3], "--shot")) gpu_set_shot(argv[4]);
#ifndef __EMSCRIPTEN__
    if (getenv("RN_TURBO") && atoi(getenv("RN_TURBO")) > 1) rn_turbo = (unsigned)atoi(getenv("RN_TURBO"));
    const char *lim = getenv("RN_SECS");
    unsigned secs = lim ? (unsigned)atoi(lim) : 60;
    pthread_t wd;
    if (secs) { pthread_create(&wd, NULL, watchdog, (void *)(uintptr_t)secs); pthread_detach(wd); }
#endif

    static Ctx ctx;
    Ctx *c = g_ctx = &ctx;
    c->memsz = GUEST_MEM;
#ifdef __EMSCRIPTEN__
    // Web: fresh memory past the break is zero (wasm memory starts zeroed; emscripten's dlmalloc never trims), so take it
    // as is. calloc would memset the whole 1 GB (dlmalloc without mmap clears every calloc) and make it all resident:
    // on an iPhone that alone is most of the ~1.5 GB a Safari tab gets before iOS kills it.
    c->mem = sbrk(GUEST_MEM);
    if (c->mem == (void *)-1) c->mem = NULL;
#else
    c->mem = calloc(1, GUEST_MEM);
#endif
    if (!c->mem) { fprintf(stderr, "cannot allocate guest memory\n"); return 2; }

    const uint8_t *nt = pe + rd32(pe + 0x3c);
    const uint8_t *opt = nt + 24;
    uint32_t nsec = rd16(nt + 6), optsz = rd16(nt + 20);
    uint32_t base = rd32(opt + 28), image_size = rd32(opt + 56), hdr_size = rd32(opt + 60);
    uint32_t entry = base + rd32(opt + 16);
    if (base != IMAGE_BASE) { fprintf(stderr, "unexpected image base %08x\n", base); return 2; }
    memcpy(c->mem + base, pe, hdr_size);
    const uint8_t *sec = opt + optsz;
    for (uint32_t k = 0; k < nsec; k++, sec += 40) {
        uint32_t va = rd32(sec + 12), raw = rd32(sec + 16), off = rd32(sec + 20);
        memcpy(c->mem + base + va, pe + off, raw);
    }
    // PATCH table (tools/recomp/patches.py): the lifted code already has these bytes; the image must match.
    for (uint32_t k = 0; k < rn_patch_count; k++) {
        const char *h = rn_patch_hex[k];
        for (uint32_t n = 0; h[2 * n]; n++) {
            unsigned v;
            sscanf(h + 2 * n, "%2x", &v);
            c->mem[rn_patch_addr[k] + n] = (uint8_t)v;
        }
        rn_log("PATCH %08x active (tools/recomp/patches.py)", rn_patch_addr[k]);
    }

    // Imports: every IAT slot gets the fake address of its host function.
    uint32_t imp = rd32(opt + 104);
    for (uint8_t *d = c->mem + base + imp; rd32(d + 12); d += 20) {
        const char *dll = (const char *)c->mem + base + rd32(d + 12);
        uint32_t names = rd32(d) ? rd32(d) : rd32(d + 16), iat = rd32(d + 16);
        for (uint32_t k = 0;; k++) {
            uint32_t t = rd32(c->mem + base + names + 4 * k);
            if (!t) break;
            char ord[16];
            const char *name = ord;
            if (t & 0x80000000u) snprintf(ord, sizeof ord, "#%u", t & 0xffff);
            else name = (const char *)c->mem + base + t + 2;
            st(c, base + iat + 4 * k, host_addr_of(dll, name), 4);
        }
    }
    free(pe);

    win32_init(c, image_size);
    threads_init(c);
    finit(c);
    c->fcw = 0x27f;              // Windows starts threads with 53-bit precision, all exceptions masked
    c->r[ESP] = STACK_HI - 16;
    c->r[ESP] -= 4;
    st(c, c->r[ESP], host_addr_of("rn", "entry_returned"), 4);
    if (getenv("RN_WATCH") || getenv("RN_CARPOS")) { pthread_t mw; pthread_create(&mw, NULL, memwatch, getenv("RN_WATCH")); pthread_detach(mw); }
    rn_steerlog = getenv("RN_STEERLOG") != NULL;
    // RN_CARLOOK=2003 (car.efx as shipped) and 2 (host/sm1.c car_ps_sharp): the car's cube reflection at the game's 0.5,
    // not PATCH 0x40fbb7's 0.35 (the float it reads at 0x707fc4).
    const char *look = getenv("RN_CARLOOK");
    if (look && (atoi(look) == 2003 || atoi(look) == 2)) { float h = 0.5f; uint32_t w; memcpy(&w, &h, 4); st(c, 0x707fc4, w, 4); }
    rn_log("Speed.exe loaded: entry %08x, %u sections, guest memory %u MB", entry, nsec, GUEST_MEM >> 20);
    rn_call(c, entry);
    rn_stop(c);
    return 0;
}

// Called with the GIL held by the thread that stopped: report and end every thread.
void rn_stop(Ctx *c) {
    dispatch_report();
    rn_log("STOP in thread %x at %08x: %s", ld(c, c->fs + 0x24, 4), c->halt_at, c->why ? c->why : "(no reason)");
    rn_log("eax=%08x ecx=%08x edx=%08x ebx=%08x esp=%08x ebp=%08x esi=%08x edi=%08x",
           c->r[0], c->r[1], c->r[2], c->r[3], c->r[4], c->r[5], c->r[6], c->r[7]);
    backtrace(c);
    crashwatch_stop(c);
    exit(0);
}
