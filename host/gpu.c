// The frame command list (see gpu.h) and its two backends.
// Web: Present hands the list to web/gpu.js through a mailbox in the shared heap; the page's thread
// runs it with WebGPU on its own event loop, so this worker never needs to yield to JavaScript.
// Native: a CPU backend runs the same list and writes the presented frame to a PNG (--shot).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gpu.h"

static uint32_t *list;
static uint32_t nlist, cap;

uint32_t *gpu_put_raw(int op, int n) {
    while (nlist + 1 + (uint32_t)n > cap) {
        cap = cap ? cap * 2 : 1u << 16;
        list = realloc(list, 4u * cap);
        if (!list) { fprintf(stderr, "gpu: out of memory\n"); exit(1); }
    }
    list[nlist++] = (uint32_t)op | (uint32_t)n << 8;
    uint32_t *w = list + nlist;
    nlist += (uint32_t)n;
    return w;
}
uint32_t *gpu_put(int op, int n) {
    uint32_t *w = gpu_put_raw(op, n);
    memset(w, 0, 4u * n);
    return w;
}
void gpu_cmd(int op, int n, const uint32_t *w) { memcpy(gpu_put_raw(op, n), w, 4u * n); }

uint32_t gpu_pending(void) { return nlist; }

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <emscripten/threading.h>

// seq = frames submitted, done = frames the page has run. Frame k lives in buf[k & 1]: the worker
// writes frame k+1 only after the page finished frame k-1, so one frame is in flight.
typedef struct { uint32_t seq, done, ptr[2], len[2]; } Mailbox;
static Mailbox box;
static uint32_t *buf[2], bufcap[2];

EMSCRIPTEN_KEEPALIVE uint32_t rn_gpu_mailbox(void) { return (uint32_t)(uintptr_t)&box; }

void gpu_set_shot(const char *path) { (void)path; }
void gpu_keep_frame(void) {}

void gpu_submit(void) {
    // The list itself becomes frame k (no copy); the next frame is written into the buffer of frame k-2, which the
    // page has finished (gpu_wait: done >= seq - 1 before this submit).
    uint32_t k = (box.seq + 1) & 1, *t = buf[k], tc = bufcap[k];
    buf[k] = list, bufcap[k] = cap, list = t, cap = tc;
    box.ptr[k] = (uint32_t)(uintptr_t)buf[k];
    box.len[k] = nlist;
    nlist = 0;
    __atomic_add_fetch(&box.seq, 1, __ATOMIC_SEQ_CST);
    emscripten_futex_wake(&box.seq, 1);     // web/gpu.js waits on seq (Atomics.waitAsync) to run the frame at once
}
void gpu_wait(void) {
    uint32_t n = __atomic_load_n(&box.seq, __ATOMIC_SEQ_CST);
    for (;;) {
        uint32_t d = __atomic_load_n(&box.done, __ATOMIC_SEQ_CST);
        if (d + 1 >= n) break;
        emscripten_futex_wait(&box.done, d, 100);
    }
}
#else

// ---- CPU backend ------------------------------------------------------------------------------
// A reference rasterizer for native shots: D3D9 rules (pixel centers at integer positions, top-left
// fill, clip to 0 <= z <= w), the shaders run in the sm1.c interpreter. Simple, not fast.
#include <math.h>
#include "sm1.h"

enum { IMG_COLOR, IMG_DEPTH, IMG_TEX, IMG_CUBE };
typedef struct {
    uint32_t w, h, kind, levels;
    uint32_t *color;            // color target: ARGB
    float *z; uint8_t *stencil;
    uint32_t *lv[14];           // texture levels: RGBA8 (bytes R G B A)
    uint32_t face0;             // cube: the id of its +X face; the six faces are color targets face0..face0+5
} Img;
static Img imgs[GPU_MAXID + 1];
static Sm1 *shaders[GPU_MAXID + 1];
static uint32_t *decls[GPU_MAXID + 1], ndecl[GPU_MAXID + 1];
static const char *shot;
static uint32_t draws, frames;

void gpu_set_shot(const char *path) { shot = path; }

static void png(const char *path, const uint32_t *argb, uint32_t w, uint32_t h);

static void img_free(Img *t) {
    free(t->color); free(t->z); free(t->stencil);
    for (int k = 0; k < 14; k++) free(t->lv[k]);
    memset(t, 0, sizeof *t);
}

// ---- texture sampling ----
typedef struct { const Img *img; const uint32_t *st; } Stage;
static void texel(const Img *t, int level, int x, int y, float o[4]) {
    uint32_t w = t->w >> level ? t->w >> level : 1, v;
    if (t->kind == IMG_COLOR) { v = t->color[(uint32_t)y * t->w + (uint32_t)x]; o[0] = (v >> 16 & 255) / 255.f; o[1] = (v >> 8 & 255) / 255.f; o[2] = (v & 255) / 255.f; o[3] = (v >> 24) / 255.f; return; }
    if (!t->lv[level]) { o[0] = o[1] = o[2] = 0; o[3] = 1; return; }
    v = t->lv[level][(uint32_t)y * w + (uint32_t)x];
    o[0] = (v & 255) / 255.f; o[1] = (v >> 8 & 255) / 255.f; o[2] = (v >> 16 & 255) / 255.f; o[3] = (v >> 24) / 255.f;
}
static int address(int i, int n, uint32_t mode) {
    switch (mode) {
    case 2: { int p = 2 * n; i %= p; if (i < 0) i += p; return i < n ? i : p - 1 - i; }    // MIRROR
    case 3: return i < 0 ? 0 : i >= n ? n - 1 : i;                                         // CLAMP
    case 5: if (i < 0) i = -i - 1; return i >= n ? n - 1 : i;                              // MIRRORONCE
    default: i %= n; return i < 0 ? i + n : i;                                             // WRAP
    }
}
static void sample_level(const Img *t, const uint32_t *st, int level, int linear, const float uv[2], float o[4]) {
    int w = (int)(t->w >> level ? t->w >> level : 1), h = (int)(t->h >> level ? t->h >> level : 1);
    float x = uv[0] * (float)w, y = uv[1] * (float)h;
    if (!linear) { texel(t, level, address((int)floorf(x), w, st[T_AU]), address((int)floorf(y), h, st[T_AV]), o); return; }
    x -= 0.5f; y -= 0.5f;
    int x0 = (int)floorf(x), y0 = (int)floorf(y);
    float fx = x - (float)x0, fy = y - (float)y0, a[4], b[4], c[4], d[4];
    int xa = address(x0, w, st[T_AU]), xb = address(x0 + 1, w, st[T_AU]);
    int ya = address(y0, h, st[T_AV]), yb = address(y0 + 1, h, st[T_AV]);
    texel(t, level, xa, ya, a); texel(t, level, xb, ya, b); texel(t, level, xa, yb, c); texel(t, level, xb, yb, d);
    for (int k = 0; k < 4; k++) o[k] = (a[k] * (1 - fx) + b[k] * fx) * (1 - fy) + (c[k] * (1 - fx) + d[k] * fx) * fy;
}
// lod: log2 of the texel footprint of one pixel at level 0.
static void sample(const Img *t, const uint32_t *st, float lod, const float uv[2], float o[4]) {
    if (!t) { o[0] = o[1] = o[2] = 0; o[3] = 1; return; }
    int levels = t->kind == IMG_TEX ? (int)t->levels : 1;
    int mag = lod <= 0.f, filt = mag ? st[T_MAG] : st[T_MIN];
    int linear = filt >= 2;
    if (mag || !st[T_MIP] || levels == 1) { sample_level(t, st, 0, linear, uv, o); return; }
    float l = lod > (float)(levels - 1) ? (float)(levels - 1) : lod;
    if (st[T_MIP] == 1) { sample_level(t, st, (int)floorf(l + 0.5f), linear, uv, o); return; }
    int l0 = (int)floorf(l), l1 = l0 + 1 < levels ? l0 + 1 : l0;
    float f = l - (float)l0, a[4], b[4];
    sample_level(t, st, l0, linear, uv, a);
    sample_level(t, st, l1, linear, uv, b);
    for (int k = 0; k < 4; k++) o[k] = a[k] * (1 - f) + b[k] * f;
}

// ---- draws ----
// Screen position snapped to 1/16 pixel (X, Y: exact edge functions), z, 1/w, outputs.
#define SUB 16
typedef struct { float x, y, z, iw; int64_t X, Y; VsOut o; } Vert;
typedef struct {
    const uint32_t *h;
    const Sm1 *ps;
    const float (*pc)[4];
    Stage st[8];
    VsOut at, dx, dy;           // outputs at the pixel and their screen derivatives
    Img *rt, *ds;
} Draw;

// A cube lookup (D3D9 "Cubic Environment Mapping"): the major axis picks the face, the other two give s, t.
static void cube_sample(const Img *t, const uint32_t *st, const float r[3], float out[4]) {
    float ax = fabsf(r[0]), ay = fabsf(r[1]), az = fabsf(r[2]), ma, sc, tc;
    int face;
    if (ax >= ay && ax >= az) { face = r[0] >= 0 ? 0 : 1; ma = ax; sc = r[0] >= 0 ? -r[2] : r[2]; tc = -r[1]; }
    else if (ay >= az) { face = r[1] >= 0 ? 2 : 3; ma = ay; sc = r[0]; tc = r[1] >= 0 ? r[2] : -r[2]; }
    else { face = r[2] >= 0 ? 4 : 5; ma = az; sc = r[2] >= 0 ? r[0] : -r[0]; tc = -r[1]; }
    if (!t || t->kind != IMG_CUBE || ma == 0) { out[0] = out[1] = out[2] = 0; out[3] = 1; return; }
    uint32_t cst[D_TEXN];
    memcpy(cst, st, sizeof cst);
    cst[T_AU] = cst[T_AV] = 3;                      // a face's edge texels: clamp
    float uv[2] = {(sc / ma + 1) * 0.5f, (tc / ma + 1) * 0.5f};
    sample(&imgs[t->face0 + (uint32_t)face], cst, 0, uv, out);
}
static void ps_sample(void *ctx, int k, const float uv[2], float out[4]) {
    Draw *d = ctx;
    const Img *t = d->st[k].img;
    if (d->st[k].st[T_TT] & T_CUBE) { cube_sample(t, d->st[k].st, d->at.t[k], out); return; }
    float lod = 0;
    if (t) {
        const float *a = d->at.t[k], *ddx = d->dx.t[k], *ddy = d->dy.t[k];
        uint32_t f = d->st[k].st[T_TT];
        float q = 1, qx = 1, qy = 1;
        if (f & 256) {
            uint32_t n = f & 7, c = n >= 2 && n <= 4 ? n - 1 : 3;
            q = a[c]; qx = a[c] + ddx[c]; qy = a[c] + ddy[c];
        }
        float ux = ((a[0] + ddx[0]) / qx - a[0] / q) * (float)t->w, vx = ((a[1] + ddx[1]) / qx - a[1] / q) * (float)t->h;
        float uy = ((a[0] + ddy[0]) / qy - a[0] / q) * (float)t->w, vy = ((a[1] + ddy[1]) / qy - a[1] / q) * (float)t->h;
        float m = fmaxf(ux * ux + vx * vx, uy * uy + vy * vy);
        lod = m > 0 ? 0.5f * log2f(m) : -16.f;
    }
    sample(t, d->st[k].st, lod, uv, out);
}
static int cmp(uint32_t f, float a, float b) {
    switch (f) {
    case 1: return 0; case 2: return a < b; case 3: return a == b; case 4: return a <= b;
    case 5: return a > b; case 6: return a != b; case 7: return a >= b;
    }
    return 1;
}
static void factor(uint32_t f, const float s[4], const float d[4], uint32_t bf, float o[4]) {
    float k[4] = {(bf >> 16 & 255) / 255.f, (bf >> 8 & 255) / 255.f, (bf & 255) / 255.f, (bf >> 24) / 255.f};
    for (int i = 0; i < 4; i++) {
        float v;
        switch (f) {
        case 1: v = 0; break;
        case 2: v = 1; break;
        case 3: v = s[i]; break;
        case 4: v = 1 - s[i]; break;
        case 5: v = s[3]; break;
        case 6: v = 1 - s[3]; break;
        case 7: v = d[3]; break;
        case 8: v = 1 - d[3]; break;
        case 9: v = d[i]; break;
        case 10: v = 1 - d[i]; break;
        case 11: v = i == 3 ? 1 : fminf(s[3], 1 - d[3]); break;
        case 14: v = k[i]; break;
        case 15: v = 1 - k[i]; break;
        default: v = 1;
        }
        o[i] = v;
    }
}
static float blend_op(uint32_t op, float s, float d) {
    switch (op) {
    case 2: return s - d;
    case 3: return d - s;
    case 4: return fminf(s, d);
    case 5: return fmaxf(s, d);
    }
    return s + d;
}
static float sat(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }

static void lerp_out(VsOut *o, const Vert *v[3], const float b[3]) {
    // b: perspective-correct weights (already divided by the interpolated 1/w)
    float *dst = (float *)o;
    const float *s0 = (const float *)&v[0]->o, *s1 = (const float *)&v[1]->o, *s2 = (const float *)&v[2]->o;
    for (size_t k = 0; k < sizeof(VsOut) / 4; k++) dst[k] = s0[k] * b[0] + s1[k] * b[1] + s2[k] * b[2];
}
static void persp(const Vert *v[3], float e0, float e1, float e2, float area, VsOut *o) {
    float l[3] = {e0 / area * v[0]->iw, e1 / area * v[1]->iw, e2 / area * v[2]->iw}, s = l[0] + l[1] + l[2];
    float b[3] = {l[0] / s, l[1] / s, l[2] / s};
    lerp_out(o, v, b);
}
static int64_t iedge(const Vert *a, const Vert *b, int64_t px, int64_t py) { return (b->X - a->X) * (py - a->Y) - (b->Y - a->Y) * (px - a->X); }
static float edge(const Vert *a, const Vert *b, float px, float py) { return (float)iedge(a, b, (int64_t)(px * SUB), (int64_t)(py * SUB)); }
static int top_left(const Vert *a, const Vert *b) { int64_t dy = b->Y - a->Y, dx = b->X - a->X; return dy < 0 || (dy == 0 && dx > 0); }

static void raster(Draw *d, const Vert *v0, const Vert *v1, const Vert *v2) {
    const uint32_t *h = d->h;
    float area = (float)iedge(v0, v1, v2->X, v2->Y);
    if (area == 0) return;
    uint32_t cull = h[D_CULL];
    if ((cull == 2 && area > 0) || (cull == 3 && area < 0)) return;
    const Vert *v[3] = {v0, v1, v2};
    if (area < 0) { v[1] = v2; v[2] = v1; area = -area; }
    int x0 = (int)h[D_SC], y0 = (int)h[D_SC + 1], x1 = (int)h[D_SC + 2], y1 = (int)h[D_SC + 3];
    if ((int)h[D_VP] > x0) x0 = (int)h[D_VP];
    if ((int)h[D_VP + 1] > y0) y0 = (int)h[D_VP + 1];
    if ((int)(h[D_VP] + h[D_VP + 2]) < x1) x1 = (int)(h[D_VP] + h[D_VP + 2]);
    if ((int)(h[D_VP + 1] + h[D_VP + 3]) < y1) y1 = (int)(h[D_VP + 1] + h[D_VP + 3]);
    if (x1 > (int)d->rt->w) x1 = (int)d->rt->w;
    if (y1 > (int)d->rt->h) y1 = (int)d->rt->h;
    float fx0 = (float)fminf(v[0]->X, fminf(v[1]->X, v[2]->X)) / SUB, fx1 = (float)fmaxf(v[0]->X, fmaxf(v[1]->X, v[2]->X)) / SUB;
    float fy0 = (float)fminf(v[0]->Y, fminf(v[1]->Y, v[2]->Y)) / SUB, fy1 = (float)fmaxf(v[0]->Y, fmaxf(v[1]->Y, v[2]->Y)) / SUB;
    if (fx0 > (float)x0) x0 = (int)ceilf(fx0);
    if (fy0 > (float)y0) y0 = (int)ceilf(fy0);
    if (fx1 + 1 < (float)x1) x1 = (int)floorf(fx1) + 1;
    if (fy1 + 1 < (float)y1) y1 = (int)floorf(fy1) + 1;
    int tl0 = top_left(v[1], v[2]), tl1 = top_left(v[2], v[0]), tl2 = top_left(v[0], v[1]);
    float zs[3];
    for (int k = 0; k < 3; k++) zs[k] = v[k]->z;
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++) {
            float px = (float)x, py = (float)y;     // D3D9: the pixel's sample point is its integer position
            int64_t i0 = iedge(v[1], v[2], (int64_t)x * SUB, (int64_t)y * SUB), i1 = iedge(v[2], v[0], (int64_t)x * SUB, (int64_t)y * SUB);
            int64_t i2 = iedge(v[0], v[1], (int64_t)x * SUB, (int64_t)y * SUB);
            if (i0 < 0 || i1 < 0 || i2 < 0) continue;
            if ((i0 == 0 && !tl0) || (i1 == 0 && !tl1) || (i2 == 0 && !tl2)) continue;
            float e0 = (float)i0, e1 = (float)i1, e2 = (float)i2;
            float z = (e0 * zs[0] + e1 * zs[1] + e2 * zs[2]) / area;
            size_t pix = (size_t)y * d->rt->w + (size_t)x;
            if (d->ds && h[D_ZEN] && !cmp(h[D_ZFUNC], z, d->ds->z[(size_t)y * d->ds->w + (size_t)x])) continue;
            persp(v, e0, e1, e2, area, &d->at);
            VsOut ox, oy;
            persp(v, edge(v[1], v[2], px + 1, py), edge(v[2], v[0], px + 1, py), edge(v[0], v[1], px + 1, py), area, &ox);
            persp(v, edge(v[1], v[2], px, py + 1), edge(v[2], v[0], px, py + 1), edge(v[0], v[1], px, py + 1), area, &oy);
            for (int k = 0; k < 8; k++)
                for (int j = 0; j < 4; j++) { d->dx.t[k][j] = ox.t[k][j] - d->at.t[k][j]; d->dy.t[k][j] = oy.t[k][j] - d->at.t[k][j]; }
            uint32_t tt[8];
            for (int k = 0; k < 8; k++) tt[k] = h[D_TEX + D_TEXN * k + T_TT];
            float c[4];
            if (!sm1_run_ps(d->ps, d->pc, &d->at, tt, ps_sample, d, c)) continue;
            if (h[D_FOG]) {
                uint32_t fc = h[D_FOGC];
                float f = d->at.fog, fcol[3] = {(fc >> 16 & 255) / 255.f, (fc >> 8 & 255) / 255.f, (fc & 255) / 255.f};
                for (int k = 0; k < 3; k++) c[k] = fcol[k] + (c[k] - fcol[k]) * f;
            }
            for (int k = 0; k < 4; k++) c[k] = sat(c[k]);
            if (h[D_AFUNC] && !cmp(h[D_AFUNC], c[3], (float)h[D_AREF] / 255.f)) continue;
            uint32_t old = d->rt->color[pix];
            float dc[4] = {(old >> 16 & 255) / 255.f, (old >> 8 & 255) / 255.f, (old & 255) / 255.f, (old >> 24) / 255.f};
            if (h[D_BLEND]) {
                float fs[4], fd[4];
                factor(h[D_SRCB], c, dc, h[D_BFACTOR], fs);
                factor(h[D_DSTB], c, dc, h[D_BFACTOR], fd);
                if (h[D_SRCB] == 12) { for (int k = 0; k < 4; k++) { fs[k] = c[3]; fd[k] = 1 - c[3]; } }      // BOTHSRCALPHA
                if (h[D_SRCB] == 13) { for (int k = 0; k < 4; k++) { fs[k] = 1 - c[3]; fd[k] = c[3]; } }      // BOTHINVSRCALPHA
                for (int k = 0; k < 4; k++) c[k] = sat(blend_op(h[D_BOP], c[k] * fs[k], dc[k] * fd[k]));
            }
            uint32_t m = h[D_CWRITE], r = (uint32_t)lrintf(c[0] * 255), g = (uint32_t)lrintf(c[1] * 255);
            uint32_t b = (uint32_t)lrintf(c[2] * 255), a = (uint32_t)lrintf(c[3] * 255);
            uint32_t nv = (m & 1 ? r : old >> 16 & 255) << 16 | (m & 2 ? g : old >> 8 & 255) << 8 | (m & 4 ? b : old & 255) |
                          (m & 8 ? a : old >> 24) << 24;
            d->rt->color[pix] = nv;
            if (d->ds && h[D_ZEN] && h[D_ZWRITE]) d->ds->z[(size_t)y * d->ds->w + (size_t)x] = z;
        }
}

// Clips a clip-space polygon to 0 <= z <= w (D3D9), then fans it to the rasterizer.
static void to_screen(const uint32_t *h, const VsOut *o, Vert *v) {
    float vx = (float)h[D_VP], vy = (float)h[D_VP + 1], vw = (float)h[D_VP + 2], vh = (float)h[D_VP + 3], zmin, zmax;
    memcpy(&zmin, &h[D_VP + 4], 4); memcpy(&zmax, &h[D_VP + 5], 4);
    float iw = 1.f / o->pos[3];
    v->x = vx + (o->pos[0] * iw + 1) * 0.5f * vw;
    v->y = vy + (1 - o->pos[1] * iw) * 0.5f * vh;
    v->z = zmin + o->pos[2] * iw * (zmax - zmin);
    float lim = (float)(1 << 22);
    v->X = (int64_t)lrintf(fmaxf(-lim, fminf(lim, v->x)) * SUB);
    v->Y = (int64_t)lrintf(fmaxf(-lim, fminf(lim, v->y)) * SUB);
    v->iw = iw;
    v->o = *o;
}
static void clip_tri(Draw *d, const VsOut *a, const VsOut *b, const VsOut *c) {
    VsOut in[9], out[9];
    int n = 3;
    in[0] = *a; in[1] = *b; in[2] = *c;
    for (int plane = 0; plane < 2; plane++) {
        int m = 0;
        for (int i = 0; i < n; i++) {
            const VsOut *p = &in[i], *q = &in[(i + 1) % n];
            float dp = plane ? p->pos[3] - p->pos[2] : p->pos[2], dq = plane ? q->pos[3] - q->pos[2] : q->pos[2];
            if (dp >= 0) out[m++] = *p;
            if ((dp >= 0) != (dq >= 0)) {
                float t = dp / (dp - dq);
                float *o = (float *)&out[m++];
                const float *fp = (const float *)p, *fq = (const float *)q;
                for (size_t k = 0; k < sizeof(VsOut) / 4; k++) o[k] = fp[k] + (fq[k] - fp[k]) * t;
            }
        }
        n = m;
        memcpy(in, out, sizeof(VsOut) * (size_t)n);
        if (n < 3) return;
    }
    Vert v[9];
    for (int i = 0; i < n; i++) to_screen(d->h, &in[i], &v[i]);
    for (int i = 1; i + 1 < n; i++) raster(d, &v[0], &v[i], &v[i + 1]);
}

// One vertex element (D3DDECLTYPE) to four floats; missing components are 0, 0, 0, 1.
static void fetch(const uint8_t *p, uint32_t type, float o[4]) {
    o[0] = o[1] = o[2] = 0; o[3] = 1;
    switch (type) {
    case 0: case 1: case 2: case 3: memcpy(o, p, 4u * (type + 1)); return;
    case 4: o[0] = p[2] / 255.f; o[1] = p[1] / 255.f; o[2] = p[0] / 255.f; o[3] = p[3] / 255.f; return;   // D3DCOLOR
    case 5: for (int k = 0; k < 4; k++) o[k] = p[k]; return;
    case 8: for (int k = 0; k < 4; k++) o[k] = p[k] / 255.f; return;
    case 6: case 7: for (int k = 0; k < (type == 6 ? 2 : 4); k++) { int16_t s; memcpy(&s, p + 2 * k, 2); o[k] = s; } return;
    }
    fprintf(stderr, "gpu: vertex element type %u\n", type);
    exit(1);
}

static void run_draw(const uint32_t *h) {
    Sm1 *vs = shaders[h[D_VS]], *ps = shaders[h[D_PS]];
    const uint32_t *el = decls[h[D_DECL]];
    uint32_t nel = ndecl[h[D_DECL]], nv = h[D_NVERT], ni = h[D_NIDX], stride = h[D_STRIDE];
    static float vc[256][4], pc[8][4];
    memset(vc, 0, sizeof vc);
    const uint32_t *p = h + D_HDR;
    memcpy(vc, p, 16u * h[D_NVC]); p += 4 * h[D_NVC];
    memcpy(pc, p, 16u * h[D_NPC]); p += 4 * h[D_NPC];
    const uint8_t *vb = (const uint8_t *)p;
    const uint32_t *ix = p + (nv * stride + 3) / 4;
    // shader input register -> element offset and type
    int off[16], type[16];
    for (int r = 0; r < 16; r++) {
        off[r] = -1;
        if (!(vs->inputs >> r & 1)) continue;
        for (uint32_t k = 0; k < nel; k++) {
            uint32_t a = el[2 * k], b = el[2 * k + 1];
            if ((a & 0xffff) == 0 && (b >> 16 & 255) == vs->in_usage[r] && (b >> 24) == vs->in_index[r]) { off[r] = (int)(a >> 16); type[r] = b & 255; }
        }
        if (off[r] < 0) { fprintf(stderr, "gpu: vs input v%d (usage %u/%u) not in the declaration\n", r, vs->in_usage[r], vs->in_index[r]); exit(1); }
    }
    VsOut *out = malloc(sizeof(VsOut) * (nv ? nv : 1));
    for (uint32_t i = 0; i < nv; i++) {
        float in[16][4] = {{0}};
        for (int r = 0; r < 16; r++) if (off[r] >= 0) fetch(vb + i * stride + (uint32_t)off[r], (uint32_t)type[r], in[r]);
        sm1_run_vs(vs, (const float (*)[4])vc, (const float (*)[4])in, &out[i]);
    }
    Draw d;
    memset(&d, 0, sizeof d);
    d.h = h; d.ps = ps; d.pc = (const float (*)[4])pc;
    d.rt = &imgs[h[D_RT]];
    d.ds = h[D_DS] ? &imgs[h[D_DS]] : NULL;
    for (int k = 0; k < 8; k++) {
        uint32_t id = h[D_TEX + D_TEXN * k + T_ID];
        d.st[k].img = id ? &imgs[id] : NULL;
        d.st[k].st = &h[D_TEX + D_TEXN * k];
    }
    uint32_t n = ni ? ni : nv, ntri = h[D_TOPO] == 4 ? n / 3 : n >= 2 ? n - 2 : 0;
    for (uint32_t t = 0; t < ntri; t++) {
        uint32_t a, b, c;
        if (h[D_TOPO] == 4) { a = 3 * t; b = a + 1; c = a + 2; }
        else if (t & 1) { a = t + 1; b = t; c = t + 2; }       // strip: odd triangles keep the winding
        else { a = t; b = t + 1; c = t + 2; }
        if (ni) { a = ix[a]; b = ix[b]; c = ix[c]; }
        if (a >= nv || b >= nv || c >= nv) continue;
        clip_tri(&d, &out[a], &out[b], &out[c]);
    }
    free(out);
}

uint64_t now_us(void);
static uint64_t run_us, wall0;
// RN_RASTER=N: rasterize only every Nth frame and the frames gpu_keep_frame() asks for (resources still load every
// frame). The game never reads a frame back (on the web it cannot), so this changes only the PNGs and the speed.
static int every = -1, keep;
void gpu_keep_frame(void) { keep = 1; }
void gpu_run(const uint32_t *w, uint32_t n) {
    static int keep_every = -1;   // RN_KEEP=N: also keep every Nth frame as <shot>.<frame>.png (a menu path, step by step)
    if (every < 0) { const char *e = getenv("RN_RASTER"); every = e && atoi(e) > 1 ? atoi(e) : 1; }
    if (keep_every < 0) { const char *e = getenv("RN_KEEP"); keep_every = e ? atoi(e) : 0; }
    if (keep_every > 0 && frames % (uint32_t)keep_every == 0) keep = 1;
    for (uint32_t i = 0; i < n;) {
        int raster = every == 1 || frames % (uint32_t)every == 0 || keep;
        uint32_t op = w[i] & 0xff, len = w[i] >> 8;
        const uint32_t *a = w + i + 1;
        i += 1 + len;
        if (op == GPU_TARGET) {
            Img *t = &imgs[a[0]];
            img_free(t);
            *t = (Img){a[1], a[2], a[3] ? IMG_DEPTH : IMG_COLOR, 1, NULL, NULL, NULL, {0}};
            if (a[3] == 0) t->color = calloc((size_t)a[1] * a[2], 4);
            else { t->z = calloc((size_t)a[1] * a[2], 4); t->stencil = calloc((size_t)a[1] * a[2], 1); }
        } else if (op == GPU_CLEAR) {
            if (!raster) continue;
            Img *rt = a[0] ? &imgs[a[0]] : NULL, *ds = a[1] ? &imgs[a[1]] : NULL;
            float z;
            memcpy(&z, &a[4], 4);
            for (uint32_t y = a[7]; y < a[9]; y++)
                for (uint32_t x = a[6]; x < a[8]; x++) {
                    if (rt && (a[2] & 1)) rt->color[y * rt->w + x] = a[3];
                    if (ds && (a[2] & 2)) ds->z[y * ds->w + x] = z;
                    if (ds && (a[2] & 4)) ds->stencil[y * ds->w + x] = (uint8_t)a[5];
                }
        } else if (op == GPU_SHADER) {
            Sm1 *s = calloc(1, sizeof *s);
            char err[128];
            if (sm1_decode(s, a + 21, a[2], err, sizeof err)) { fprintf(stderr, "gpu: %s\n", err); exit(1); }
            if (shaders[a[0]]) { sm1_free(shaders[a[0]]); free(shaders[a[0]]); }
            shaders[a[0]] = s;
        } else if (op == GPU_DECL) {
            free(decls[a[0]]);
            decls[a[0]] = malloc(8u * a[1] + 4);
            memcpy(decls[a[0]], a + 2, 8u * a[1]);
            ndecl[a[0]] = a[1];
        } else if (op == GPU_TEXTURE) {
            Img *t = &imgs[a[0]];
            img_free(t);
            *t = (Img){a[1], a[2], IMG_TEX, a[3], NULL, NULL, NULL, {0}};
        } else if (op == GPU_TEXDATA) {
            Img *t = &imgs[a[0]];
            if (a[1] < 14) {
                free(t->lv[a[1]]);
                t->lv[a[1]] = malloc(4u * a[2] * a[3]);
                memcpy(t->lv[a[1]], a + 4, 4u * a[2] * a[3]);
            }
        } else if (op == GPU_CUBE) {
            Img *t = &imgs[a[0]];
            img_free(t);
            *t = (Img){a[1], a[1], IMG_CUBE, 1, NULL, NULL, NULL, {0}, a[2]};
        } else if (op == GPU_FXAA || op == GPU_LIVERY || op == GPU_SKIN || op == GPU_BUFFER || op == GPU_BUFDATA) {
            // web only (web/gpu.js)
        } else if (op == GPU_TEXKEY) {
            // the remaster pack is web only (web/gpu.js)
        } else if (op == GPU_DRAW) {
            if (!raster) continue;
            run_draw(a);
            draws++;
        } else if (op == GPU_PRESENT) {
            if (shot && raster) png(shot, imgs[a[0]].color, a[1], a[2]);
            if (shot && keep) {
                char path[600];
                snprintf(path, sizeof path, "%s.%u.png", shot, frames);
                png(path, imgs[a[0]].color, a[1], a[2]);
            }
            keep = 0;
            // RN_SHOT_FRAMES=a-b: also keep frames a..b as <shot>.<frame>.png (debug).
            static int lo = -1, hi = -1;
            if (lo == -1) { const char *e = getenv("RN_SHOT_FRAMES"); lo = -2; if (e && sscanf(e, "%d-%d", &lo, &hi) != 2) lo = -2; }
            if (shot && (int)frames >= lo && (int)frames <= hi) {
                char path[600];
                snprintf(path, sizeof path, "%s.%u.png", shot, frames);
                png(path, imgs[a[0]].color, a[1], a[2]);
            }
            // how much of the wall time the CPU backend takes (it is not the game: a slow native run is often this)
            if (frames < 3 || frames % 100 == 0) {
                uint64_t now = now_us();
                fprintf(stderr, "gpu: frame %u: %u draws, raster %llu of %llu ms\n", frames, draws, (unsigned long long)run_us / 1000, (unsigned long long)(now - wall0) / 1000);
                run_us = 0, wall0 = now;
            }
            frames++;
            draws = 0;
        } else {
            fprintf(stderr, "gpu: unknown command %u\n", op);
            exit(1);
        }
    }
}

void gpu_submit(void) {
    uint64_t t = now_us();
    gpu_run(list, nlist);
    run_us += now_us() - t;
    nlist = 0;
}
void gpu_wait(void) {}

// PNG with stored (uncompressed) deflate blocks: no zlib needed.
static uint32_t crc_tab[256];
static uint32_t crc(uint32_t c, const uint8_t *p, size_t n) {
    if (!crc_tab[1])
        for (uint32_t k = 0; k < 256; k++) {
            uint32_t v = k;
            for (int j = 0; j < 8; j++) v = v & 1 ? 0xedb88320u ^ (v >> 1) : v >> 1;
            crc_tab[k] = v;
        }
    c = ~c;
    while (n--) c = crc_tab[(c ^ *p++) & 0xff] ^ (c >> 8);
    return ~c;
}
static void be32(uint8_t *p, uint32_t v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v; }
static void chunk(FILE *f, const char *type, const uint8_t *d, uint32_t n) {
    uint8_t h[8];
    be32(h, n);
    memcpy(h + 4, type, 4);
    fwrite(h, 1, 8, f);
    fwrite(d, 1, n, f);
    uint32_t v = crc(crc(0, h + 4, 4), d, n);
    be32(h, v);
    fwrite(h, 1, 4, f);
}
static void png(const char *path, const uint32_t *argb, uint32_t w, uint32_t h) {
    size_t row = 1 + 3 * (size_t)w, raw_n = row * h;
    uint8_t *raw = malloc(raw_n);
    for (uint32_t y = 0; y < h; y++) {
        uint8_t *r = raw + y * row;
        r[0] = 0;
        for (uint32_t x = 0; x < w; x++) {
            uint32_t v = argb[y * w + x];
            r[1 + 3 * x] = v >> 16; r[2 + 3 * x] = v >> 8; r[3 + 3 * x] = v;
        }
    }
    size_t nblk = (raw_n + 65534) / 65535, zn = 2 + raw_n + 5 * nblk + 4;
    uint8_t *z = malloc(zn), *q = z;
    *q++ = 0x78; *q++ = 0x01;
    uint32_t a = 1, b = 0;
    for (size_t off = 0; off < raw_n; off += 65535) {
        uint32_t n = raw_n - off < 65535 ? (uint32_t)(raw_n - off) : 65535;
        *q++ = off + n == raw_n;
        *q++ = n; *q++ = n >> 8; *q++ = ~n; *q++ = (~n) >> 8;
        memcpy(q, raw + off, n);
        q += n;
        for (uint32_t k = 0; k < n; k++) { a = (a + raw[off + k]) % 65521; b = (b + a) % 65521; }
    }
    be32(q, b << 16 | a);
    q += 4;
    FILE *f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "gpu: cannot write %s\n", path); exit(1); }
    fwrite("\x89PNG\r\n\x1a\n", 1, 8, f);
    uint8_t ihdr[13];
    be32(ihdr, w); be32(ihdr + 4, h);
    ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = ihdr[11] = ihdr[12] = 0;
    chunk(f, "IHDR", ihdr, 13);
    chunk(f, "IDAT", z, (uint32_t)(q - z));
    chunk(f, "IEND", NULL, 0);
    fclose(f);
    free(raw);
    free(z);
}
#endif
