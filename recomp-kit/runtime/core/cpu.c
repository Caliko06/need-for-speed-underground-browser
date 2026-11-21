// The CPU we present: a Pentium 4 (Northwood, 3.2 GHz, 2003) with an FPU, a TSC and MMX, no SSE/3DNow, so the
// game's CPU checks take its x87 code paths where it has them. MMX is reported because some game code has no other path:
// the movie library's YUV -> RGB 0x647cb0 returns at once when the MMX flag [0x70fdd8] is 0 (grey movie, title stuck). Its graphics preset reads the brand index: 0x41eff0 scores the
// machine as 0.8 min(cpu, gpu) + 0.2 max; 0x41e9b0 maps EBX & 0xf (table 0x41ea50) to a class, brand 0 = score 0
// and the lowest preset; brand 9 (Pentium 4) scores (MHz - 800) / 2400 with the MHz it times from rdtsc against
// QueryPerformanceCounter (0x41eae0), so rn_rdtsc runs at 3.2 GHz. difftest gives Unicorn the same answers.
#include "rt.h"

void rn_cpu_ident(uint32_t leaf, uint32_t out[4]) {   // eax, ebx, ecx, edx
    out[0] = out[1] = out[2] = out[3] = 0;
    if (leaf == 0) { out[0] = 1; out[1] = 0x756e6547; out[3] = 0x49656e69; out[2] = 0x6c65746e; }   // "GenuineIntel"
    if (leaf == 1) { out[0] = 0x0f29; out[1] = 0x09; out[3] = 0x00800111; }   // family 15 model 2; brand 9; FPU, TSC, CX8, MMX
}

void rn_cpuid(Ctx *c, uint32_t *a, uint32_t *b, uint32_t *cc, uint32_t *d) {
    uint32_t r[4];
    (void)c;
    rn_cpu_ident(*a, r);
    *a = r[0]; *b = r[1]; *cc = r[2]; *d = r[3];
}
