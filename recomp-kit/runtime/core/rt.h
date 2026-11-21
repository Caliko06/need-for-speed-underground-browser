// Guest CPU state and helpers shared by the lifted code (build/gen) and the host layer.
#pragma once
#include <stdint.h>
#include <string.h>
#include <math.h>

enum { EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI };

typedef struct Ctx {
    uint32_t r[8];
    uint8_t *mem;               // guest address 0 = mem[0]; flat 32-bit space
    uint32_t memsz;
    uint32_t ret;               // return address popped by the last `ret`
    uint32_t halt, halt_at;     // halt != 0: stop everything, halt_at = guest address
    const char *why;
    uint32_t fs;                // TEB guest address
    int32_t cf, zf, sf, of, pf, df, af;
    uint32_t eflx;              // eflags bits we only store (AC, ID)
    uint32_t fcw, fsw, ftop, ftag;  // fsw keeps C0..C3 only; ftag bit i = physical st i in use
    double st[8];
    uint32_t mb;                // base of the live ABK code module the called lifted function belongs to
    uint64_t mm[8];             // MMX registers (kept apart from st[]: the game leaves MMX code with emms)
} Ctx;

// Guest pages below 64 KB are never mapped: a null pointer read is a loud fault.
#define LOW 0x10000u
// RN_NOCHK (web opt-in, tools/recomp/build.py): no guest bounds check; game thread work -16 % on the Pod A/B
// (2026-11-03), but a bad guest pointer then corrupts wasm memory instead of a clean "memory fault" halt.
#ifdef RN_NOCHK
#define CHK(a, n, at) do { } while (0)
#elif defined(RN_STW)
// RN_STW build (tools/recomp/build.py, off by default): c->halt_at always holds the guest address of the last memory access, so a
// watched store (host/crashwatch.c) can name the instruction that made it. A host API sets it to its entry address.
#define CHK(a, n, at) do { c->halt_at = (at); if ((uint32_t)((a) - LOW) > c->memsz - LOW - (n)) { c->why = "memory fault"; goto trap; } } while (0)
#else
#define CHK(a, n, at) do { if ((uint32_t)((a) - LOW) > c->memsz - LOW - (n)) { c->halt_at = (at); c->why = "memory fault"; goto trap; } } while (0)
#endif
#define TRAP(at, msg) do { c->halt_at = (at); c->why = (msg); goto trap; } while (0)

static inline uint32_t ld(Ctx *c, uint32_t a, int n) { uint32_t v = 0; memcpy(&v, c->mem + a, n); return v; }
#ifdef RN_STW
// One bit per 8 bytes of the first 64 MB above the guest heap start (0x800000), armed by host/crashwatch.c each Present.
extern uint8_t rn_stw_bm[1u << 20];
void rn_stw_hit(Ctx *c, uint32_t a, uint32_t v, int n);
static inline void st(Ctx *c, uint32_t a, uint32_t v, int n) {
    uint32_t o = a - 0x800000u;
    if (o < (64u << 20) && (rn_stw_bm[o >> 6] >> ((o >> 3) & 7) & 1)) rn_stw_hit(c, a, v, n);
    memcpy(c->mem + a, &v, n);
}
#else
static inline void st(Ctx *c, uint32_t a, uint32_t v, int n) { memcpy(c->mem + a, &v, n); }
#endif
static inline float ldf(Ctx *c, uint32_t a) { float v; memcpy(&v, c->mem + a, 4); return v; }
static inline double ldd(Ctx *c, uint32_t a) { double v; memcpy(&v, c->mem + a, 8); return v; }
static inline void stf(Ctx *c, uint32_t a, float v) { memcpy(c->mem + a, &v, 4); }
static inline void std_(Ctx *c, uint32_t a, double v) { memcpy(c->mem + a, &v, 8); }
static inline uint64_t ld64(Ctx *c, uint32_t a) { uint64_t v; memcpy(&v, c->mem + a, 8); return v; }
static inline void st64(Ctx *c, uint32_t a, uint64_t v) { memcpy(c->mem + a, &v, 8); }
static inline int par(uint32_t v) { return !__builtin_parity(v & 0xffu); }

// A guest loop that polls for another thread's work without an API call (the movie decoder 0x645a77 waits for
// the tick the winmm timer callback 0x63eaa0 counts) never reaches gil_slice. A thread that waited a quantum for
// the GIL sets rn_preempt; the lifted code checks it at every backward jump (host/threads.c).
extern volatile int rn_preempt;
void gil_preempt(void);
#define PREEMPT() do { if (__builtin_expect(rn_preempt, 0)) gil_preempt(); } while (0)

// Calls any guest or host address. Defined in host/dispatch.c.
void rn_call(Ctx *c, uint32_t target);
// ABK code modules lifted ahead of time (tools/recomp/abk.py -> build/gen/abk.c). Defined in host/abk.c.
typedef struct { uint32_t id, size, nfn; const uint32_t *off; void (*const *fn)(Ctx *); } RnMod;
void (*rn_mod_find(Ctx *c, uint32_t target, uint32_t *mb))(Ctx *);
uint64_t rn_rdtsc(Ctx *c);
void rn_cpuid(Ctx *c, uint32_t *a, uint32_t *b, uint32_t *cc, uint32_t *d);

// ---- x87 ----------------------------------------------------------------
// Registers are doubles: precision control 24 bits rounds to float, 53 and 64 bits keep double.
#define FC0 0x100u
#define FC2 0x400u
#define FC3 0x4000u
static inline double *fr(Ctx *c, int i) { return &c->st[(c->ftop + i) & 7]; }
static inline double fround(Ctx *c, double v) { return ((c->fcw >> 8) & 3) == 0 ? (double)(float)v : v; }
// NaN results follow the x87 rules (Intel SDM table 4-7), not the host's: an invalid operation on
// non-NaN operands gives the "real indefinite" (-NaN); NaN operands propagate quieted, the larger
// significand wins and a tie takes the positive one.
static inline uint64_t dbits(double v) { uint64_t b; memcpy(&b, &v, 8); return b; }
static inline double bitsd(uint64_t b) { double v; memcpy(&v, &b, 8); return v; }
static inline double fnan2(double a, double b) {
    if (a == a) return bitsd(dbits(b) | 0x8000000000000ull);
    if (b == b) return bitsd(dbits(a) | 0x8000000000000ull);
    uint64_t x = dbits(a) | 0x8000000000000ull, y = dbits(b) | 0x8000000000000ull;
    uint64_t mx = x & 0xfffffffffffffull, my = y & 0xfffffffffffffull;
    if (mx != my) return bitsd(mx > my ? x : y);
    return bitsd(x < y ? x : y);     // same significand: the one without the sign bit
}
#ifdef RN_REF_QEMU5
#define FIE 0x00u     // difftest only: QEMU 5 (Unicorn) never raises IE; the SDM does
#else
#define FIE 0x01u     // invalid operation
#endif
#define FZE 0x04u     // zero divide
#define FSF 0x40u     // stack fault
// Results of x87 arithmetic: NaN rules above; an invalid operation on non-NaN operands also sets IE.
// The NaN path is a cold call of its own and the test stays inline: as one inline function wasm kept fx2 a call on every
// FADD/FMUL (3.3 % of the game thread, build/bench/b4_x87.prof.txt).
__attribute__((noinline, cold)) static double fx2_nan(Ctx *c, double a, double b) {
    if (a != a || b != b) return fnan2(a, b);
    c->fsw |= FIE;
    return bitsd(0xfff8000000000000ull);
}
__attribute__((noinline, cold)) static double fx1_nan(Ctx *c, double a) {
    if (a != a) return bitsd(dbits(a) | 0x8000000000000ull);
    c->fsw |= FIE;
    return bitsd(0xfff8000000000000ull);
}
__attribute__((always_inline)) static inline double fx2(Ctx *c, double a, double b, double r) { return r == r ? r : fx2_nan(c, a, b); }
__attribute__((always_inline)) static inline double fx1(Ctx *c, double a, double r) { return r == r ? r : fx1_nan(c, a); }
static inline double fdiv_(Ctx *c, double a, double b) {
#ifdef RN_REF_QEMU5
    if (b == 0) c->fsw |= FZE;      // difftest only: the reference CPU flags every x/0, and never IE
#else
    if (b == 0 && a == a && a != 0 && !isinf(a)) c->fsw |= FZE;     // finite non-zero / 0
#endif
    return fx2(c, a, b, a / b);
}
#define FADD(a, b) fx2(c, (a), (b), (a) + (b))
#define FSUB(a, b) fx2(c, (a), (b), (a) - (b))
#define FMUL(a, b) fx2(c, (a), (b), (a) * (b))
#define FDIV(a, b) fdiv_(c, (a), (b))

// Stack faults are masked on Windows: an empty register reads as the "real indefinite" (-NaN), and a push
// onto a full register loads it too. Keeping every empty slot at that value gives both for free.
static inline double findef(void) { uint64_t b = 0xfff8000000000000ull; double v; memcpy(&v, &b, 8); return v; }
static inline void fpush(Ctx *c, double v) {
    c->ftop = (c->ftop - 1) & 7;
    if (c->ftag & (1u << c->ftop)) { v = findef(); c->fsw |= FIE | FSF | 0x200u; }
    c->st[c->ftop] = v;
    c->ftag |= 1u << c->ftop;
}
static inline void fpop(Ctx *c) { c->st[c->ftop] = findef(); c->ftag &= ~(1u << c->ftop); c->ftop = (c->ftop + 1) & 7; }
static inline void ffree(Ctx *c, int i) { *fr(c, i) = findef(); c->ftag &= ~(1u << ((c->ftop + i) & 7)); }
static inline void finit(Ctx *c) {
    c->fcw = 0x37f; c->fsw = 0; c->ftop = 0; c->ftag = 0;
    for (int k = 0; k < 8; k++) c->st[k] = findef();
}
// x87 loads of float/double memory turn a signaling NaN into a quiet one (Intel SDM, FLD).
static inline double ldfx(Ctx *c, uint32_t a) {
    uint32_t b = ld(c, a, 4);
    float f;
    if ((b & 0x7f800000u) == 0x7f800000u && (b & 0x7fffffu) && !(b & 0x400000u)) { b |= 0x400000u; c->fsw |= FIE; }
    memcpy(&f, &b, 4);
    return f;
}
static inline double lddx(Ctx *c, uint32_t a) {
    uint64_t b = ld64(c, a);
    if ((b & 0x7ff0000000000000ull) == 0x7ff0000000000000ull && (b & 0xfffffffffffffull) && !(b & 0x8000000000000ull)) {
        b |= 0x8000000000000ull;
        c->fsw |= FIE;
    }
    return bitsd(b);
}
static inline void fset(Ctx *c, int i, double v) { *fr(c, i) = fround(c, v); }
static inline void fucom(Ctx *c, double a, double b) {
    c->fsw &= ~(FC0 | FC2 | FC3);
    if (a != a || b != b) c->fsw |= FC0 | FC2 | FC3;
    else if (a < b) c->fsw |= FC0;
    else if (a == b) c->fsw |= FC3;
}
static inline void fcom(Ctx *c, double a, double b) {
    c->fsw &= ~(FC0 | FC2 | FC3);
    if (a != a || b != b) c->fsw |= FC0 | FC2 | FC3 | FIE;
    else if (a < b) c->fsw |= FC0;
    else if (a == b) c->fsw |= FC3;
}
static inline uint16_t fstsw(Ctx *c) { return (uint16_t)((c->fsw & ~0x3800u) | (c->ftop << 11)); }
// x87 runs (tools/recomp/lift.py): fstsw with TOP known by the lifter, and a slot mask (bit = slot relative to the
// run's start TOP) turned into physical tag bits.
static inline uint16_t fstsw_t(Ctx *c, uint32_t top) { return (uint16_t)((c->fsw & ~0x3800u) | (top << 11)); }
static inline uint32_t frot(uint32_t m, uint32_t k) { k &= 7; return ((m << k) | (m >> ((8 - k) & 7))) & 0xffu; }
static inline double frnd(Ctx *c, double v) {
    switch ((c->fcw >> 10) & 3) {
    case 0: return nearbyint(v);
    case 1: return floor(v);
    case 2: return ceil(v);
    default: return trunc(v);
    }
}
// Integer store: out of range gives the "integer indefinite" value, like the FPU with IM masked.
static inline int64_t fist(Ctx *c, double v, int bits, int truncate) {
    double r = truncate ? trunc(v) : frnd(c, v);
    double lim = ldexp(1.0, bits - 1);
    if (!(r >= -lim && r < lim)) { c->fsw |= FIE; return (int64_t)((uint64_t)1 << (bits - 1)); }
    return (int64_t)r;
}
// FPREM/FPREM1 (Intel SDM): remainder of st0/st1 with the quotient truncated (FPREM) or rounded to
// nearest (FPREM1); C0, C3, C1 get quotient bits 2, 0, 1; C2 = 0 (the reduction is complete in one step:
// doubles never have the 64-bit exponent difference that makes the x87 stop early).
static inline void fprem(Ctx *c, int nearest) {
    double a = *fr(c, 0), b = *fr(c, 1), r;
    c->fsw &= ~(FC0 | 0x200u | FC2 | FC3);
    if (a != a || b != b || isinf(a) || b == 0) { *fr(c, 0) = fx2(c, a, b, NAN); return; }
    unsigned q;
    if (nearest) { int qi; r = remquo(a, b, &qi); q = (unsigned)(qi < 0 ? -qi : qi); }
    else {
        r = fmod(a, b);
        double r8 = fmod(a, 8 * fabs(b));
        q = (unsigned)nearbyint(fabs((r8 - r) / b));   // quotient mod 8
    }
    *fr(c, 0) = r;
    if (q & 4) c->fsw |= FC0;
    if (q & 1) c->fsw |= FC3;
    if (q & 2) c->fsw |= 0x200u;
}
static inline double ld80(Ctx *c, uint32_t a) {
    uint64_t m; uint16_t se;
    memcpy(&m, c->mem + a, 8); memcpy(&se, c->mem + a + 8, 2);
    int e = se & 0x7fff; double s = (se & 0x8000) ? -1.0 : 1.0;
    // Unsupported encodings (integer bit clear with a non-zero exponent: unnormal, pseudo-NaN/infinity)
    // make any x87 operation invalid (SDM 8.2.2): hold them as the real indefinite.
    if (e != 0 && !(m >> 63)) return findef();
    if (e == 0 && m == 0) return s * 0.0;
    if (e == 0x7fff) {
        if (!(m << 1)) return s * INFINITY;
        return bitsd((uint64_t)(se >> 15) << 63 | 0x7ff0000000000000ull | ((m >> 11) & 0xfffffffffffffull) | 0x8000000000000ull);
    }
    return s * ldexp((double)m, e - 16383 - 63);
}
static inline void st80(Ctx *c, uint32_t a, double v) {
    uint64_t m = 0; uint16_t se = signbit(v) ? 0x8000 : 0;
    if (isnan(v)) { se |= 0x7fff; m = 0xc000000000000000ull; }
    else if (isinf(v)) { se |= 0x7fff; m = 0x8000000000000000ull; }
    else if (v != 0) {
        int e; double f = frexp(fabs(v), &e);           // f in [0.5,1)
        m = (uint64_t)ldexp(f, 64); se |= (uint16_t)(e - 1 + 16383);
    }
    memcpy(c->mem + a, &m, 8); memcpy(c->mem + a + 8, &se, 2);
}
static inline void fxam(Ctx *c) {
    double v = *fr(c, 0);
    uint32_t s = signbit(v) ? 0x200u : 0;      // C1 = sign
    c->fsw &= ~(FC0 | 0x200u | FC2 | FC3);
    if (!(c->ftag & (1u << c->ftop))) c->fsw |= FC3 | FC0 | s;
    else if (isnan(v)) c->fsw |= FC0 | s;
    else if (isinf(v)) c->fsw |= FC2 | FC0 | s;
    else if (v == 0) c->fsw |= FC3 | s;
    else c->fsw |= FC2 | s;
}

// ---- MMX (host/cpu.c reports it): lane-wise integer ops on 64-bit values -------------------------
// An MMX instruction sets TOP = 0 and tags every x87 register valid; emms empties them (SDM vol. 1, 9.5).
#define MMX_ENTER() (c->ftop = 0, c->ftag = 0xffu)
enum { MX_ADD, MX_ADDS, MX_ADDUS, MX_SUB, MX_SUBS, MX_SUBUS, MX_CMPEQ, MX_CMPGT, MX_MULL, MX_MULH };
static inline int64_t mx_lane(uint64_t v, int bits, int k, int sgn) {
    uint64_t x = (v >> (k * bits)) & (bits == 64 ? ~0ull : (1ull << bits) - 1);
    return sgn && bits < 64 && (x >> (bits - 1)) ? (int64_t)(x | ~((1ull << bits) - 1)) : (int64_t)x;
}
static inline int64_t mx_sat(int64_t v, int64_t lo, int64_t hi) { return v < lo ? lo : v > hi ? hi : v; }
static inline uint64_t mx_op(uint64_t a, uint64_t b, int bits, int op) {
    uint64_t r = 0, m = bits == 64 ? ~0ull : (1ull << bits) - 1;
    int64_t smin = -(1ll << (bits - 1)), smax = (1ll << (bits - 1)) - 1, umax = (int64_t)m;
    for (int k = 0; k < 64 / bits; k++) {
        int sg = op == MX_ADDS || op == MX_SUBS || op == MX_CMPGT || op == MX_MULL || op == MX_MULH;
        int64_t x = mx_lane(a, bits, k, sg), y = mx_lane(b, bits, k, sg), v;
        switch (op) {
        case MX_ADD: v = x + y; break;
        case MX_ADDS: v = mx_sat(x + y, smin, smax); break;
        case MX_ADDUS: v = mx_sat(x + y, 0, umax); break;
        case MX_SUB: v = x - y; break;
        case MX_SUBS: v = mx_sat(x - y, smin, smax); break;
        case MX_SUBUS: v = mx_sat(x - y, 0, umax); break;
        case MX_CMPEQ: v = x == y ? -1 : 0; break;
        case MX_CMPGT: v = x > y ? -1 : 0; break;
        case MX_MULL: v = x * y; break;
        default: v = (x * y) >> bits; break;
        }
        r |= ((uint64_t)v & m) << (k * bits);
    }
    return r;
}
// Shifts: a count above the lane width gives 0, or the sign for psra.
static inline uint64_t mx_shift(uint64_t a, uint64_t n, int bits, int kind) {   // kind 0 sll, 1 srl, 2 sra
    uint64_t r = 0, m = bits == 64 ? ~0ull : (1ull << bits) - 1;
    for (int k = 0; k < 64 / bits; k++) {
        int64_t x = mx_lane(a, bits, k, kind == 2), v;
        if (kind == 2) v = x >> (n >= (uint64_t)bits ? bits - 1 : (int)n);
        else if (n >= (uint64_t)bits) v = 0;
        else v = kind == 0 ? (int64_t)((uint64_t)x << n) : (int64_t)((uint64_t)x >> n);
        r |= ((uint64_t)v & m) << (k * bits);
    }
    return r;
}
// punpckl/h: interleave the low (or high) halves, lanes of the destination first.
static inline uint64_t mx_unpack(uint64_t a, uint64_t b, int bits, int high) {
    uint64_t r = 0, m = bits == 64 ? ~0ull : (1ull << bits) - 1;
    int n = 32 / bits;
    for (int k = 0; k < n; k++) {
        r |= ((a >> ((k + high * n) * bits)) & m) << (2 * k * bits);
        r |= ((b >> ((k + high * n) * bits)) & m) << ((2 * k + 1) * bits);
    }
    return r;
}
// packsswb / packuswb (words -> bytes), packssdw (dwords -> words): the destination's lanes fill the low half.
static inline uint64_t mx_pack(uint64_t a, uint64_t b, int bits, int uns) {
    int h = bits / 2, n = 64 / bits;
    int64_t lo = uns ? 0 : -(1ll << (h - 1)), hi = uns ? (1ll << h) - 1 : (1ll << (h - 1)) - 1;
    uint64_t r = 0, m = (1ull << h) - 1;
    for (int k = 0; k < n; k++) {
        r |= ((uint64_t)mx_sat(mx_lane(a, bits, k, 1), lo, hi) & m) << (k * h);
        r |= ((uint64_t)mx_sat(mx_lane(b, bits, k, 1), lo, hi) & m) << ((k + n) * h);
    }
    return r;
}
static inline uint64_t mx_maddwd(uint64_t a, uint64_t b) {
    uint64_t r = 0;
    for (int k = 0; k < 2; k++) {
        int64_t v = mx_lane(a, 16, 2 * k, 1) * mx_lane(b, 16, 2 * k, 1) + mx_lane(a, 16, 2 * k + 1, 1) * mx_lane(b, 16, 2 * k + 1, 1);
        r |= ((uint64_t)v & 0xffffffffu) << (32 * k);
    }
    return r;
}
