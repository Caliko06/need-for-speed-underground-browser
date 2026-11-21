// Target-agnostic Unicorn difftest runtime for lifted x86-32 C code.
#include "rt.h"

extern const uint32_t rn_fn_count;
extern const uint32_t rn_fn_addr[];
extern void (*const rn_fn_ptr[])(Ctx *);

void rn_call(Ctx *c, uint32_t t) {
    if (t >= 0xe0000000u) { c->halt = 2; c->halt_at = t; c->why = "import"; return; }
    uint32_t lo = 0, hi = rn_fn_count;
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        if (rn_fn_addr[mid] < t) lo = mid + 1; else hi = mid;
    }
    if (lo < rn_fn_count && rn_fn_addr[lo] == t) { rn_fn_ptr[lo](c); return; }
    c->halt = 1; c->halt_at = t; c->why = "no lifted function";
}

volatile int rn_preempt;
void gil_preempt(void) {}
uint64_t rn_rdtsc(Ctx *c) { (void)c; return 0x123456789abcull; }

void rn_quiet_snans(uint8_t *p, uint32_t n) {
    for (uint32_t o = 0; o + 4 <= n; o += 4) {
        uint32_t v;
        memcpy(&v, p + o, 4);
        if ((v & 0x7f800000u) == 0x7f800000u && (v & 0x7fffffu) && !(v & 0x400000u)) p[o + 2] |= 0x40;
        if (o % 8 == 4) {
            uint64_t q;
            memcpy(&q, p + o - 4, 8);
            if ((q & 0x7ff0000000000000ull) == 0x7ff0000000000000ull && (q & 0xfffffffffffffull) && !(q & 0x8000000000000ull))
                p[o + 2] |= 0x08;
        }
    }
}
