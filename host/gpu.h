// The renderer behind the D3D9 device. d3d9.c records one command list per frame; at Present a
// backend runs it: web/gpu.js (WebGPU on the page's thread) or the CPU backend in gpu.c for native
// off-screen shots. The list is the only contract between them; web/gpu.js mirrors these numbers.
#pragma once
#include <stdint.h>

// Command: [op | nwords << 8] then nwords payload words. Ids are d3d9 object indexes + 1; render
// targets and textures share the id space.
#define GPU_MAXID 65536     // d3d9 objects; a race keeps about 7,300 alive
enum {
    GPU_TARGET = 1,     // id, width, height, kind (0 color, 1 depth/stencil)
    GPU_CLEAR = 2,      // color id (0 none), depth id (0 none), D3DCLEAR flags, ARGB, z (float bits), stencil, x0, y0, x1, y1
    GPU_PRESENT = 3,    // color id, width, height
    GPU_DRAW = 4,       // D_* header, then vs constants, ps constants, vertex bytes, u32 indices
    GPU_SHADER = 5,     // id, 0 vs / 1 ps, token count n, WGSL byte count m, 16 inputs, tex mask, n tokens, WGSL text
                        // (m bytes, zero padded). Input k: 0 = v<k> not read, else 1 << 31 | usage << 8 | usage index.
    GPU_DECL = 6,       // id, element count n, n D3DVERTEXELEMENT9 (2 words each)
    GPU_TEXTURE = 7,    // id, width, height, levels
    GPU_TEXDATA = 8,    // id, level, width, height, RGBA8 texels (one word each, bytes R G B A)
    GPU_TEXKEY = 9,     // id, key low word, key high word: FNV-1a 64 of a DXT level 0 (web/gpu.js remaster pack)
    GPU_FXAA = 11,      // color id: FXAA over that target's current contents (web/gpu.js; sent at the start of the HUD, so the HUD stays crisp)
    GPU_CUBE = 10,      // id, edge, id of face 0: the six face targets (ids face0..face0+5, D3DCUBEMAP_FACES order
                        // +X -X +Y -Y +Z -Z, sent before as GPU_TARGET) become the layers of one cube texture
    GPU_BUFFER = 13,    // id, bytes: a vertex or index buffer that lives on the GPU (web only; static buffers)
    GPU_BUFDATA = 14,   // id, byte offset, byte count n, n bytes (zero padded): its contents from that Unlock on
    GPU_LIVERY = 15,    // skin id, car, art number: the pool livery over the HD skin (web/gpu.js livery)
    GPU_SKIN = 12,      // skin id, fill ARGB, layer count n, n x (layer id, mask id, recolour, 4 ARGB colours), 4 marker ARGB,
                        // marker count m, m x (texel index, colour 0-3): the HD replay of the skin composite (d3d9.c skin_bridge)
};

// GPU_DRAW header (word offsets). Render states keep their D3D9 values.
enum {
    D_TOPO = 0,         // D3DPRIMITIVETYPE; fans arrive as lists
    D_NVERT, D_NIDX,    // vertices in the payload; indices (0 = draw the vertices in order)
    D_STRIDE, D_VS, D_PS, D_DECL, D_RT, D_DS,
    D_VP = 9,           // x, y, w, h, zmin, zmax (floats)
    D_SC = 15,          // scissor x0, y0, x1, y1 (resolved: the render target when the scissor test is off)
    D_ZEN = 19, D_ZWRITE, D_ZFUNC, D_CULL,
    D_BLEND = 23, D_SRCB, D_DSTB, D_BOP, D_SEPA, D_SRCBA, D_DSTBA, D_BOPA, D_BFACTOR,
    D_CWRITE = 32, D_AFUNC, D_AREF, D_FOG, D_FOGC,   // D_AFUNC 0 = alpha test off
    D_TEX = 37,         // 8 stages x D_TEXN words
    D_NVC = 37 + 8 * 8, D_NPC,
    D_RVB, D_RVOFF,     // resident draw (web): vertex buffer id (0 = vertices in the payload) and its byte offset
    D_RIB, D_RIFMT,     // index buffer id (0 = indices in the payload, u32) and its index size (2 or 4)
    D_RFIRST, D_RBASEV, // first index (or first vertex) and base vertex (signed) of a resident draw
    D_HDR,
};
// Per stage: texture id (0 none), ADDRESSU, ADDRESSV, MAGFILTER, MINFILTER, MIPFILTER, TEXTURETRANSFORMFLAGS, MAXANISOTROPY.
// T_TT also carries T_CUBE: the stage's texture is a cube (ps_1_x samples by the bound texture's type).
enum { T_ID = 0, T_AU, T_AV, T_MAG, T_MIN, T_MIP, T_TT, T_ANISO, D_TEXN };
#define T_CUBE 0x10000u

void gpu_cmd(int op, int n, const uint32_t *w);
uint32_t *gpu_put(int op, int n);          // n zeroed words in the list for the caller to fill (valid until the next command)
uint32_t *gpu_put_raw(int op, int n);      // n uninitialized words in the list (caller fills every word)
void gpu_submit(void);                  // run or hand off the list, then start a new one (a frame or a part of one)
void gpu_wait(void);                    // web: wait until the page is at most one part behind (call without the GIL)
uint32_t gpu_pending(void);             // words in the list not handed off yet
void gpu_set_shot(const char *path);    // native: write every presented frame to this PNG
void gpu_keep_frame(void);              // native: rasterize this frame and also keep it as <shot>.<frame>.png

// Backend side: the frame's words.
void gpu_run(const uint32_t *w, uint32_t n);
