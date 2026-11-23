// d3d9: Direct3DCreate9 and the COM objects behind it, as documented by Microsoft (DirectX 9.0b).
// We present one adapter: an ATI RADEON 9800 PRO (R350, 128 MB) HAL device on a 1920x1080 desktop,
// a DirectX 9 card of the game's time. Every query the game makes is logged with RN_TRACE so the
// answers can be checked against Wine. Objects live in guest memory: [vtable][host index]; every
// vtable slot is a host function "d3d9.dll!Interface::Method", so a method we lack stops loudly.
#include <strings.h>
#include "host.h"
#include "gpu.h"
#include "sm1.h"
#include "carsmooth.h"

#define D3D_OK 0u
#define D3DERR_NOTFOUND 0x88760866u
#define D3DERR_NOTAVAILABLE 0x8876086au
#define D3DERR_INVALIDCALL 0x8876086cu
#define D3DERR_OUTOFVIDEOMEMORY 0x8876017cu
#define D3DOK_NOAUTOGEN 0x0876086fu

#define TR(...) do { if (rn_trace()) rn_log("d3d9 " __VA_ARGS__); } while (0)

// Host-only render budget, exported by web/boot.js. Other tiers retain the existing path.
static int tier_ultralite(void) {
    static int on = -1;
    if (on < 0) { const char *tier = getenv("RN_TIER"); on = tier && !strcmp(tier, "ultralite"); }
    return on;
}

// ---- interfaces: vtable order of d3d9.h -----------------------------------------------------
enum { I_D3D9, I_DEVICE, I_SURFACE, I_TEXTURE, I_CUBE, I_VB, I_IB, I_SWAPCHAIN, I_DECL, I_VS, I_PS, I_SB, I_QUERY, I_N };
#define UNK "QueryInterface", "AddRef", "Release"
#define RES UNK, "GetDevice", "SetPrivateData", "GetPrivateData", "FreePrivateData", "SetPriority", "GetPriority", \
            "PreLoad", "GetType"
#define BASETEX RES, "SetLOD", "GetLOD", "GetLevelCount", "SetAutoGenFilterType", "GetAutoGenFilterType", \
            "GenerateMipSubLevels"
static const char *const m_d3d9[] = {UNK, "RegisterSoftwareDevice", "GetAdapterCount", "GetAdapterIdentifier",
    "GetAdapterModeCount", "EnumAdapterModes", "GetAdapterDisplayMode", "CheckDeviceType", "CheckDeviceFormat",
    "CheckDeviceMultiSampleType", "CheckDepthStencilMatch", "CheckDeviceFormatConversion", "GetDeviceCaps",
    "GetAdapterMonitor", "CreateDevice", 0};
static const char *const m_device[] = {UNK, "TestCooperativeLevel", "GetAvailableTextureMem",
    "EvictManagedResources", "GetDirect3D", "GetDeviceCaps", "GetDisplayMode", "GetCreationParameters",
    "SetCursorProperties", "SetCursorPosition", "ShowCursor", "CreateAdditionalSwapChain", "GetSwapChain",
    "GetNumberOfSwapChains", "Reset", "Present", "GetBackBuffer", "GetRasterStatus", "SetDialogBoxMode",
    "SetGammaRamp", "GetGammaRamp", "CreateTexture", "CreateVolumeTexture", "CreateCubeTexture",
    "CreateVertexBuffer", "CreateIndexBuffer", "CreateRenderTarget", "CreateDepthStencilSurface", "UpdateSurface",
    "UpdateTexture", "GetRenderTargetData", "GetFrontBufferData", "StretchRect", "ColorFill",
    "CreateOffscreenPlainSurface", "SetRenderTarget", "GetRenderTarget", "SetDepthStencilSurface",
    "GetDepthStencilSurface", "BeginScene", "EndScene", "Clear", "SetTransform", "GetTransform",
    "MultiplyTransform", "SetViewport", "GetViewport", "SetMaterial", "GetMaterial", "SetLight", "GetLight",
    "LightEnable", "GetLightEnable", "SetClipPlane", "GetClipPlane", "SetRenderState", "GetRenderState",
    "CreateStateBlock", "BeginStateBlock", "EndStateBlock", "SetClipStatus", "GetClipStatus", "GetTexture",
    "SetTexture", "GetTextureStageState", "SetTextureStageState", "GetSamplerState", "SetSamplerState",
    "ValidateDevice", "SetPaletteEntries", "GetPaletteEntries", "SetCurrentTexturePalette",
    "GetCurrentTexturePalette", "SetScissorRect", "GetScissorRect", "SetSoftwareVertexProcessing",
    "GetSoftwareVertexProcessing", "SetNPatchMode", "GetNPatchMode", "DrawPrimitive", "DrawIndexedPrimitive",
    "DrawPrimitiveUP", "DrawIndexedPrimitiveUP", "ProcessVertices", "CreateVertexDeclaration",
    "SetVertexDeclaration", "GetVertexDeclaration", "SetFVF", "GetFVF", "CreateVertexShader", "SetVertexShader",
    "GetVertexShader", "SetVertexShaderConstantF", "GetVertexShaderConstantF", "SetVertexShaderConstantI",
    "GetVertexShaderConstantI", "SetVertexShaderConstantB", "GetVertexShaderConstantB", "SetStreamSource",
    "GetStreamSource", "SetStreamSourceFreq", "GetStreamSourceFreq", "SetIndices", "GetIndices",
    "CreatePixelShader", "SetPixelShader", "GetPixelShader", "SetPixelShaderConstantF", "GetPixelShaderConstantF",
    "SetPixelShaderConstantI", "GetPixelShaderConstantI", "SetPixelShaderConstantB", "GetPixelShaderConstantB",
    "DrawRectPatch", "DrawTriPatch", "DeletePatch", "CreateQuery", 0};
static const char *const m_surface[] = {RES, "GetContainer", "GetDesc", "LockRect", "UnlockRect", "GetDC",
    "ReleaseDC", 0};
static const char *const m_texture[] = {BASETEX, "GetLevelDesc", "GetSurfaceLevel", "LockRect", "UnlockRect",
    "AddDirtyRect", 0};
static const char *const m_cube[] = {BASETEX, "GetLevelDesc", "GetCubeMapSurface", "LockRect", "UnlockRect",
    "AddDirtyRect", 0};
static const char *const m_vb[] = {RES, "Lock", "Unlock", "GetDesc", 0};
static const char *const m_swapchain[] = {UNK, "Present", "GetFrontBufferData", "GetBackBuffer",
    "GetRasterStatus", "GetDisplayMode", "GetDevice", "GetPresentParameters", 0};
static const char *const m_decl[] = {UNK, "GetDevice", "GetDeclaration", 0};
static const char *const m_shader[] = {UNK, "GetDevice", "GetFunction", 0};
static const char *const m_sb[] = {UNK, "GetDevice", "Capture", "Apply", 0};
static const char *const m_query[] = {UNK, "GetDevice", "GetType", "GetDataSize", "Issue", "GetData", 0};
static const char *const iface_name[I_N] = {"IDirect3D9", "IDirect3DDevice9", "IDirect3DSurface9",
    "IDirect3DTexture9", "IDirect3DCubeTexture9", "IDirect3DVertexBuffer9", "IDirect3DIndexBuffer9",
    "IDirect3DSwapChain9", "IDirect3DVertexDeclaration9", "IDirect3DVertexShader9", "IDirect3DPixelShader9",
    "IDirect3DStateBlock9", "IDirect3DQuery9"};
static const char *const *const iface_methods[I_N] = {m_d3d9, m_device, m_surface, m_texture, m_cube, m_vb, m_vb,
    m_swapchain, m_decl, m_shader, m_shader, m_sb, m_query};
static uint32_t vtables[I_N];

static uint32_t vtable(int i) {
    if (vtables[i]) return vtables[i];
    int n = 0;
    while (iface_methods[i][n]) n++;
    uint32_t v = guest_alloc(4u * n);
    for (int k = 0; k < n; k++) {
        char name[96];
        snprintf(name, sizeof name, "%s::%s", iface_name[i], iface_methods[i][k]);
        st(g_ctx, v + 4u * k, host_addr_of("d3d9.dll", name), 4);
    }
    return vtables[i] = v;
}

// ---- objects --------------------------------------------------------------------------------
enum { POOL_DEFAULT, POOL_MANAGED, POOL_SYSTEMMEM, POOL_SCRATCH };
typedef struct {
    int iface;
    uint32_t refs, guest;
    uint32_t w, h, fmt, usage, pool, type;  // type: D3DRESOURCETYPE
    uint32_t mem, pitch, size;              // guest memory behind Lock
    uint32_t container;                     // owning object index + 1 (surfaces of textures, back buffers)
    uint32_t gpu;                           // render target / depth id in the command list, 0 = none
    int locked, lockable;
    uint32_t levels, level0, fvf;           // textures: mip count, object index of level 0 (levels follow)
    uint32_t *blob, nblob;                  // shader tokens, vertex elements (host copy)
    Sm1 *sm;                                // shaders: decoded
    int hl;                                 // vertex shaders: SM1_HL_VS, it takes host/lights.c's projectors
    uint8_t refl;                           // pixel shaders: 1 = worldreflect ps (reflected sample on stage 1), 2 = worldheadlightreflect ps (stage 3)
    struct Rec *rec;                        // state blocks: the recorded Set calls
    uint32_t nrec;
    uint32_t dlo, dhi;                      // resident buffers: bytes written since the last upload
    uint32_t ver;                           // buffers: write locks so far (a cheap content key for static ones)
} Obj;
#define MAXOBJ GPU_MAXID
static Obj objs[MAXOBJ];
static uint64_t tex_key[MAXOBJ];   // textures: the pack key (FNV-1a 64 of level 0) of the last upload, 0 = none
static int nobjs;   // slots ever used; objs[top] is the newest object
static int top;
// Slots are reused once the table is full: every track load makes thousands of textures and the old ones die
// textures; RN_MAXOBJ=20000: each track load also leaves ~3000 dead VBs and IBs). Surfaces, textures and buffers come
// back (GPU_TARGET, GPU_TEXTURE, GPU_BUFFER replace an id; the smooth cache keys by the buffer's own memory); shaders and
// declarations keep their ids, which the GPU side caches by. A texture takes a run of 1 + levels slots (level0 follows it, GPU_CUBE ids face0..face0+5).
static int slot_free(int k), bound(int k);
static void drop_mem(Obj *o) { if (o->mem) guest_free(o->mem), o->mem = 0; }   // see free_dead
static int run_at, run_n, cursor;
static int find_run(int n) {
    static int lim;   // RN_MAXOBJ=N: a smaller table, so a short run already reuses slots (a test of this code)
    if (!lim) lim = getenv("RN_MAXOBJ") && atoi(getenv("RN_MAXOBJ")) > 0 && atoi(getenv("RN_MAXOBJ")) < MAXOBJ ? atoi(getenv("RN_MAXOBJ")) : MAXOBJ;
    if (nobjs + n <= lim) return nobjs;
    for (int tried = 0, at = cursor; tried < MAXOBJ; ) {
        int len = 0;
        while (len < n && at + len < nobjs && slot_free(at + len)) len++;
        if (len == n) { cursor = at + n; return at; }
        tried += len + 1, at += len + 1;
        if (at + n > nobjs) at = 0;
    }
    return -1;
}
static int reserve(int n) { run_at = find_run(n); run_n = run_at < 0 ? 0 : n; return run_at >= 0; }
static uint32_t new_obj(Ctx *c, int iface) {
    int k = run_n ? (run_n--, run_at++) : find_run(1);
    if (k < 0) {
        int live[I_N] = {0}, n = 0;
        for (int j = 0; j < nobjs; j++) if (!slot_free(j)) { live[objs[j].iface]++; n++; }
        rn_halt(c, "d3d9: too many objects (%d live: %d surfaces, %d textures, %d VBs, %d IBs)", n,
                live[I_SURFACE], live[I_TEXTURE], live[I_VB], live[I_IB]);
        return 0;
    }
    if (k < nobjs && (objs[k].iface == I_TEXTURE || objs[k].iface == I_CUBE))   // its levels outlive it as dead surfaces
        for (uint32_t l = 0; l < (objs[k].iface == I_CUBE ? 6u : objs[k].levels); l++)
            if (objs[objs[k].level0 + l].container == (uint32_t)k + 1)
                objs[objs[k].level0 + l].container = 0, objs[objs[k].level0 + l].refs = 0, drop_mem(&objs[objs[k].level0 + l]);
    if (k >= nobjs) nobjs = k + 1;
    Obj *o = &objs[k];
    drop_mem(o);
    memset(o, 0, sizeof *o);
    tex_key[k] = 0;
    o->iface = iface;
    o->refs = 1;
    o->guest = guest_alloc(16);   // a new pointer: a stale one stops in obj_of
    st(c, o->guest, vtable(iface), 4);
    st(c, o->guest + 4, (uint32_t)k + 1, 4);
    top = k;
    return o->guest;
}
static Obj *obj_of(Ctx *c, uint32_t p, int iface) {
    uint32_t k = p ? ld(c, p + 4, 4) - 1 : ~0u;
    if (k < (uint32_t)nobjs && objs[k].guest == p && (iface < 0 || objs[k].iface == iface)) return &objs[k];
    rn_halt(c, "d3d9: %08x is not a live %s", p, iface < 0 ? "object" : iface_name[iface]);
    return NULL;
}
#define SELF(iface) Obj *o = obj_of(c, ARG(0), iface); if (!o) return D3DERR_INVALIDCALL
static uint32_t idx(const Obj *o) { return (uint32_t)(o - objs); }

static uint32_t unk_QueryInterface(Ctx *c) {
    uint32_t g = ARG(1);
    rn_halt(c, "d3d9: QueryInterface for {%08x-%04x-%04x-...}", ld(c, g, 4), ld(c, g + 4, 2), ld(c, g + 6, 2));
    return 0x80004002u;     // E_NOINTERFACE
}
static uint32_t unk_AddRef(Ctx *c) { SELF(-1); return ++o->refs; }
// A dead object's Lock memory goes back to the guest heap once nothing binds it (else when its slot is reused): it
// stayed forever, ~60 MB a track load, and runs/career_trace ran the 1 GB guest space out at event 11 (the game's pool
// malloc 0x67121a -> NULL, int3 0x565cd2; guest_mem_log: dead 91 -> 157 -> 215 MB as the heap 146 -> 212 -> 266 MB).
static void free_dead(int k) {
    Obj *o = &objs[k];
    if (o->refs || bound(k)) return;
    if (o->iface == I_TEXTURE || o->iface == I_CUBE)
        for (uint32_t l = 0; l < (o->iface == I_CUBE ? 6u : o->levels); l++)
            if (objs[o->level0 + l].container == (uint32_t)k + 1) drop_mem(&objs[o->level0 + l]);
    drop_mem(o);
}
// A surface that belongs to a texture or a swap chain shares its container's count (d3d9 docs).
static uint32_t unk_Release(Ctx *c) {
    SELF(-1);
    if (o->container) {
        uint32_t n = --objs[o->container - 1].refs;
        if (!n) free_dead((int)o->container - 1);
        return n;
    }
    if (!o->refs) { rn_halt(c, "d3d9: Release of a dead %s", iface_name[o->iface]); return 0; }
    if (!--o->refs) { TR("%s %08x freed", iface_name[o->iface], o->guest); free_dead((int)(o - objs)); }
    return o->refs;
}

// ---- formats --------------------------------------------------------------------------------
enum {
    F_UNKNOWN = 0, F_R8G8B8 = 20, F_A8R8G8B8, F_X8R8G8B8, F_R5G6B5, F_X1R5G5B5, F_A1R5G5B5, F_A4R4G4B4, F_R3G3B2,
    F_A8, F_A8R3G3B2, F_X4R4G4B4, F_A2B10G10R10, F_A8B8G8R8, F_X8B8G8R8, F_G16R16, F_A2R10G10B10, F_A16B16G16R16,
    F_A8P8 = 40, F_P8, F_L8 = 50, F_A8L8, F_A4L4, F_V8U8 = 60, F_L6V5U5, F_X8L8V8U8, F_Q8W8V8U8, F_V16U16,
    F_D16_LOCKABLE = 70, F_D32, F_D15S1 = 73, F_D24S8 = 75, F_D24X8 = 77, F_D24X4S4 = 79, F_D16, F_L16,
    F_D32F_LOCKABLE, F_D24FS8, F_INDEX16 = 101, F_INDEX32, F_R16F = 111, F_G16R16F, F_A16B16G16R16F, F_R32F,
    F_G32R32F, F_A32B32G32R32F,
};
#define FOURCC(a, b, c_, d) ((uint32_t)(a) | (uint32_t)(b) << 8 | (uint32_t)(c_) << 16 | (uint32_t)(d) << 24)
#define F_DXT1 FOURCC('D', 'X', 'T', '1')
#define F_DXT2 FOURCC('D', 'X', 'T', '2')
#define F_DXT3 FOURCC('D', 'X', 'T', '3')
#define F_DXT4 FOURCC('D', 'X', 'T', '4')
#define F_DXT5 FOURCC('D', 'X', 'T', '5')

static int is_dxt(uint32_t f) { return f == F_DXT1 || f == F_DXT2 || f == F_DXT3 || f == F_DXT4 || f == F_DXT5; }
static int is_depth(uint32_t f) { return f >= F_D16_LOCKABLE && f <= F_D24FS8 && f != F_L16; }
// Bits per pixel (per texel for DXT: 4 or 8). 0 = a format this adapter does not know.
static int fmt_bits(uint32_t f) {
    switch (f) {
    case F_A8R8G8B8: case F_X8R8G8B8: case F_A8B8G8R8: case F_X8B8G8R8: case F_A2B10G10R10: case F_A2R10G10B10:
    case F_G16R16: case F_X8L8V8U8: case F_Q8W8V8U8: case F_V16U16: case F_D32: case F_D24S8: case F_D24X8:
    case F_D24X4S4: case F_D32F_LOCKABLE: case F_D24FS8: case F_G16R16F: case F_R32F: case F_INDEX32: return 32;
    case F_R8G8B8: return 24;
    case F_R5G6B5: case F_X1R5G5B5: case F_A1R5G5B5: case F_A4R4G4B4: case F_A8R3G3B2: case F_X4R4G4B4:
    case F_A8P8: case F_A8L8: case F_V8U8: case F_L6V5U5: case F_D16_LOCKABLE: case F_D15S1: case F_D16:
    case F_L16: case F_R16F: case F_INDEX16: return 16;
    case F_R3G3B2: case F_A8: case F_P8: case F_L8: case F_A4L4: return 8;
    case F_A16B16G16R16: case F_A16B16G16R16F: case F_G32R32F: return 64;
    case F_A32B32G32R32F: return 128;
    case F_DXT1: return 4;
    case F_DXT2: case F_DXT3: case F_DXT4: case F_DXT5: return 8;
    }
    return 0;
}
static uint32_t pitch_of(uint32_t f, uint32_t w) {
    if (is_dxt(f)) return ((w + 3) / 4) * (f == F_DXT1 ? 8 : 16);
    return (w * fmt_bits(f) / 8 + 3) & ~3u;
}
static uint32_t size_of(uint32_t f, uint32_t w, uint32_t h) { return pitch_of(f, w) * (is_dxt(f) ? (h + 3) / 4 : h); }

// ---- the adapter ----------------------------------------------------------------------------
#define DESK_W rn_screen_w
#define DESK_H rn_screen_h
#define VRAM (128u << 20)
// Largest texture side. The R350 had 2048, but this adapter offers desktop sizes past it, and the game makes
// render targets of the screen's size (0x40cc4b, LIGHTSTREAKS: [0x701034] x [0x701038]). WebGPU allows 8192.
#define MAXTEX 4096u
static const uint16_t modes[][2] = {{640, 480}, {720, 480}, {720, 576}, {800, 600}, {1024, 768}, {1152, 864},
    {1280, 720}, {1280, 768}, {1280, 800}, {1280, 960}, {1280, 1024}, {1360, 768}, {1366, 768}, {1400, 1050},
    {1440, 900}, {1600, 900}, {1680, 1050}, {1920, 1080}};
#define NSTATIC (int)(sizeof modes / sizeof modes[0])
// The list ends with the desktop size, so the game can pick the size of the window (PATCH 0x408760).
static int has_desk(void) { for (int k = 0; k < NSTATIC; k++) if (modes[k][0] == DESK_W && modes[k][1] == DESK_H) return 1; return 0; }
#define NMODES (NSTATIC + !has_desk())
static void mode_at(int k, uint32_t *w, uint32_t *h) { if (k < NSTATIC) { *w = modes[k][0]; *h = modes[k][1]; } else { *w = DESK_W; *h = DESK_H; } }
static int display_fmt(uint32_t f) { return f == F_X8R8G8B8 || f == F_R5G6B5; }
static uint32_t vram_used;

static uint32_t d3d9_obj;
static uint32_t Direct3DCreate9_(Ctx *c) {
    uint32_t v = ARG(0) & 0x7fffffffu;
    TR("Direct3DCreate9(%u)", ARG(0));
    if (v != 31 && v != 32) return 0;       // D3D_SDK_VERSION of DirectX 9.0b/9.0c
    if (!d3d9_obj) d3d9_obj = new_obj(c, I_D3D9);
    else objs[ld(c, d3d9_obj + 4, 4) - 1].refs++;
    return d3d9_obj;
}

// Undocumented export that D3DX asks for to validate the shaders it assembles. We have no
// validator: it returns NULL, and D3DX then skips validation (its code checks for NULL).
static uint32_t Direct3DShaderValidatorCreate9_(Ctx *c) { (void)c; rn_log("d3d9 Direct3DShaderValidatorCreate9 -> NULL"); return 0; }
// DebugSetMute(void) silences the debug runtime; the retail runtime has nothing to silence.
static uint32_t DebugSetMute_(Ctx *c) { (void)c; return 0; }

static uint32_t IDirect3D9_GetAdapterCount(Ctx *c) { (void)c; TR("GetAdapterCount -> 1"); return 1; }

static void put_str(Ctx *c, uint32_t p, const char *s) { memcpy(G(p), s, strlen(s) + 1); }
// D3DADAPTER_IDENTIFIER9: Driver[512], Description[512], DeviceName[32], DriverVersion, VendorId, DeviceId,
// SubSysId, Revision, DeviceIdentifier, WHQLLevel. Catalyst 3.10 (October 2003) driver version.
static uint32_t IDirect3D9_GetAdapterIdentifier(Ctx *c) {
    uint32_t ad = ARG(1), flags = ARG(2), p = ARG(3);
    TR("GetAdapterIdentifier(%u, flags %x)", ad, flags);
    if (ad != 0 || !p) return D3DERR_INVALIDCALL;
    memset(G(p), 0, 1100);
    put_str(c, p, "ati2dvag.dll");
    put_str(c, p + 512, "RADEON 9800 PRO");
    put_str(c, p + 1024, "\\\\.\\DISPLAY1");
    st(c, p + 1056, (10u << 16) | 6396, 4);   // 6.14.10.6396
    st(c, p + 1060, (6u << 16) | 14, 4);
    st(c, p + 1064, 0x1002, 4);               // ATI
    st(c, p + 1068, 0x4e48, 4);               // R350 RADEON 9800 PRO
    st(c, p + 1072, 0x00021002, 4);
    st(c, p + 1076, 0, 4);
    // DeviceIdentifier: a per-install GUID; this one is ours and fixed.
    static const uint8_t guid[16] = {0xd7, 0xb7, 0x1e, 0xe2, 0x0d, 0x08, 0xcf, 0x11, 0x8e, 0x46, 0x00, 0x52, 0x4e, 0x48, 0x10, 0x02};
    memcpy(G(p + 1080), guid, 16);
    st(c, p + 1096, (flags & 2) ? 1 : 0, 4);  // D3DENUM_WHQL_LEVEL: signed driver
    return D3D_OK;
}
static uint32_t IDirect3D9_GetAdapterModeCount(Ctx *c) {
    uint32_t ad = ARG(1), f = ARG(2);
    uint32_t n = ad == 0 && display_fmt(f) ? NMODES : 0;
    TR("GetAdapterModeCount(%u, fmt %u) -> %u", ad, f, n);
    return n;
}
static void put_mode(Ctx *c, uint32_t p, uint32_t w, uint32_t h, uint32_t f) {
    st(c, p, w, 4); st(c, p + 4, h, 4); st(c, p + 8, 60, 4); st(c, p + 12, f, 4);
}
static uint32_t IDirect3D9_EnumAdapterModes(Ctx *c) {
    uint32_t ad = ARG(1), f = ARG(2), k = ARG(3), p = ARG(4);
    TR("EnumAdapterModes(%u, fmt %u, %u)", ad, f, k);
    if (ad != 0 || !display_fmt(f) || k >= (uint32_t)NMODES || !p) return D3DERR_INVALIDCALL;
    uint32_t mw, mh;
    mode_at((int)k, &mw, &mh);
    put_mode(c, p, mw, mh, f);
    return D3D_OK;
}
static uint32_t IDirect3D9_GetAdapterDisplayMode(Ctx *c) {
    TR("GetAdapterDisplayMode(%u)", ARG(1));
    if (ARG(1) != 0 || !ARG(2)) return D3DERR_INVALIDCALL;
    put_mode(c, ARG(2), DESK_W, DESK_H, F_X8R8G8B8);
    return D3D_OK;
}
// Back buffer formats per display format (d3d9 "Presentation formats" table); UNKNOWN only windowed.
static int backbuffer_ok(uint32_t disp, uint32_t bb, int windowed) {
    if (bb == F_UNKNOWN) return windowed;
    if (disp == F_X8R8G8B8) return bb == F_X8R8G8B8 || bb == F_A8R8G8B8;
    if (disp == F_R5G6B5) return bb == F_R5G6B5;
    return 0;
}
static uint32_t IDirect3D9_CheckDeviceType(Ctx *c) {
    uint32_t ad = ARG(1), type = ARG(2), disp = ARG(3), bb = ARG(4), win = ARG(5);
    uint32_t r = ad == 0 && type == 1 && display_fmt(disp) && backbuffer_ok(disp, bb, win) ? D3D_OK : D3DERR_NOTAVAILABLE;
    if (ad != 0) r = D3DERR_INVALIDCALL;
    TR("CheckDeviceType(%u, type %u, disp %u, bb %u, windowed %u) -> %08x", ad, type, disp, bb, win, r);
    return r;
}
// Formats of an R300-class part. RTYPE: 1 surface, 3 texture, 4 volume texture, 5 cube texture.
static int tex_fmt(uint32_t f) {
    switch (f) {
    case F_A8R8G8B8: case F_X8R8G8B8: case F_R5G6B5: case F_X1R5G5B5: case F_A1R5G5B5: case F_A4R4G4B4:
    case F_A8: case F_L8: case F_A8L8: case F_V8U8: case F_L6V5U5: case F_X8L8V8U8: case F_Q8W8V8U8:
    case F_V16U16: case F_G16R16: case F_A2R10G10B10: case F_A16B16G16R16: case F_L16: case F_R16F:
    case F_G16R16F: case F_A16B16G16R16F: case F_R32F: case F_G32R32F: case F_A32B32G32R32F:
        return 1;
    }
    return is_dxt(f);
}
static int rt_fmt(uint32_t f) {
    switch (f) {
    case F_A8R8G8B8: case F_X8R8G8B8: case F_R5G6B5: case F_X1R5G5B5: case F_A1R5G5B5: case F_A4R4G4B4:
    case F_G16R16: case F_A2R10G10B10: case F_A16B16G16R16: case F_R16F: case F_G16R16F: case F_A16B16G16R16F:
    case F_R32F: case F_G32R32F: case F_A32B32G32R32F:
        return 1;
    }
    return 0;
}
static int ds_fmt(uint32_t f) { return f == F_D16 || f == F_D16_LOCKABLE || f == F_D24S8 || f == F_D24X8; }
static int float_fmt(uint32_t f) { return f >= F_R16F && f <= F_A32B32G32R32F; }

#define U_RENDERTARGET 0x1u
#define U_DEPTHSTENCIL 0x2u
#define U_DYNAMIC 0x200u
#define U_AUTOGENMIPMAP 0x400u
#define U_QUERY_MASK 0x000f8000u    // QUERY_LEGACYBUMPMAP .. QUERY_VERTEXTEXTURE, SRGBREAD/WRITE, FILTER
static uint32_t check_format(uint32_t disp, uint32_t usage, uint32_t rtype, uint32_t f) {
    if (!display_fmt(disp)) return D3DERR_NOTAVAILABLE;
    uint32_t q = usage & U_QUERY_MASK;
    if (rtype == 6) return f == 100 ? D3D_OK : D3DERR_NOTAVAILABLE;                    // D3DFMT_VERTEXDATA
    if (rtype == 7) return f == F_INDEX16 || f == F_INDEX32 ? D3D_OK : D3DERR_NOTAVAILABLE;
    int ok;
    if (usage & U_DEPTHSTENCIL) ok = rtype == 1 && ds_fmt(f);
    else if (usage & U_RENDERTARGET) ok = (rtype == 1 || rtype == 3 || rtype == 5) && rt_fmt(f);
    else ok = rtype == 1 ? tex_fmt(f) || f == F_UNKNOWN : (rtype == 3 || rtype == 5) ? tex_fmt(f)
            : rtype == 4 ? tex_fmt(f) && !is_dxt(f) : 0;
    if (!ok) return D3DERR_NOTAVAILABLE;
    if (q & 0x20000u) ok = !float_fmt(f);                               // QUERY_FILTER
    if (q & 0x80000u) ok = ok && !float_fmt(f);                         // QUERY_POSTPIXELSHADER_BLENDING
    if (q & 0x10000u) ok = 0;                                           // QUERY_SRGBREAD: not on R300
    if (q & 0x40000u) ok = 0;                                           // QUERY_SRGBWRITE
    if (q & 0x100000u) ok = 0;                                          // QUERY_VERTEXTEXTURE
    if (q & 0x8000u) ok = ok && (f == F_V8U8 || f == F_L6V5U5 || f == F_X8L8V8U8);   // QUERY_LEGACYBUMPMAP
    if (!ok) return D3DERR_NOTAVAILABLE;
    if ((usage & U_AUTOGENMIPMAP) && (float_fmt(f) || is_dxt(f) || fmt_bits(f) < 16)) return D3DOK_NOAUTOGEN;
    return D3D_OK;
}
static uint32_t IDirect3D9_CheckDeviceFormat(Ctx *c) {
    uint32_t ad = ARG(1), type = ARG(2), disp = ARG(3), usage = ARG(4), rtype = ARG(5), f = ARG(6);
    uint32_t r = ad != 0 ? D3DERR_INVALIDCALL : type != 1 ? D3DERR_NOTAVAILABLE : check_format(disp, usage, rtype, f);
    TR("CheckDeviceFormat(%u, type %u, disp %u, usage %x, rtype %u, fmt %u) -> %08x", ad, type, disp, usage, rtype, f, r);
    return r;
}
// Multisampling: 2, 4, 6 samples (and NONMASKABLE with 3 quality levels) on 8888/565 and the depth formats.
static uint32_t IDirect3D9_CheckDeviceMultiSampleType(Ctx *c) {
    uint32_t ad = ARG(1), type = ARG(2), f = ARG(3), win = ARG(4), ms = ARG(5), q = ARG(6);
    int fmt_ok = f == F_A8R8G8B8 || f == F_X8R8G8B8 || f == F_R5G6B5 || ds_fmt(f);
    uint32_t levels = ms == 0 ? 1 : ms == 1 ? 3 : (ms == 2 || ms == 4 || ms == 6) ? 1 : 0;
    uint32_t r = ad != 0 ? D3DERR_INVALIDCALL : type == 1 && levels && (ms == 0 || fmt_ok) ? D3D_OK : D3DERR_NOTAVAILABLE;
    if (q) st(c, q, r == D3D_OK ? levels : 0, 4);
    TR("CheckDeviceMultiSampleType(%u, type %u, fmt %u, windowed %u, ms %u) -> %08x", ad, type, f, win, ms, r);
    return r;
}
static uint32_t IDirect3D9_CheckDepthStencilMatch(Ctx *c) {
    uint32_t ad = ARG(1), disp = ARG(3), rt = ARG(4), ds = ARG(5);
    uint32_t r = ad != 0 ? D3DERR_INVALIDCALL : display_fmt(disp) && rt_fmt(rt) && ds_fmt(ds) ? D3D_OK : D3DERR_NOTAVAILABLE;
    TR("CheckDepthStencilMatch(%u, disp %u, rt %u, ds %u) -> %08x", ad, disp, rt, ds, r);
    return r;
}

// D3DCAPS9 of the R350 (values of the DirectX Caps Viewer dump for this class of part).
static void put_caps(Ctx *c, uint32_t p) {
    static const struct { uint16_t off; uint32_t v; } caps[] = {
        {0, 1}, {4, 0},                        // DeviceType HAL, AdapterOrdinal
        {8, 0x00020000}, {12, 0x60120000}, {16, 0x000003a0}, {20, 0x8000000f}, {24, 0x3},
        {28, 0x001bbef0},                      // DevCaps: HW T&L, pure device, video memory textures
        {32, 0x00144ff2}, {36, 0x0f732191}, {40, 0xff}, {44, 0x3fff}, {48, 0x3fff}, {52, 0xff},
        {56, 0x00084208}, {60, 0x0007ed07}, {64, 0x07030700}, {68, 0x07030700}, {72, 0x03030300},
        {76, 0x3f}, {80, 0x3f}, {84, 0x1f},
        {88, MAXTEX}, {92, MAXTEX}, {96, 2048}, {100, 2048}, {104, 2048}, {108, 16},
        {136, 0x1ff}, {140, 0x00100008}, {144, 0x03feffff}, {148, 8}, {152, 8}, {156, 0x17b},
        {160, 8}, {164, 6}, {168, 4}, {172, 37}, {180, 0xfffff}, {184, 0xffffff}, {188, 16}, {192, 508},
        {196, 0xfffe0200}, {200, 256}, {204, 0xffff0200}, {212, 0x51},
        {224, 0}, {228, 0}, {232, 1}, {236, 0x33e}, {240, 4}, {244, 0x03000300},
        {248, 0}, {252, 0}, {256, 12}, {260, 1},              // VS20Caps
        {264, 0}, {268, 0}, {272, 12}, {276, 0}, {280, 96},   // PS20Caps
        {284, 0}, {288, 65535}, {292, 96}, {296, 0}, {300, 0},
    };
    static const struct { uint16_t off; float v; } fcaps[] = {
        {112, 1e10f}, {116, -65536.f}, {120, -65536.f}, {124, 65536.f}, {128, 65536.f}, {132, 0.f},
        {176, 256.f}, {208, 8.f}, {216, 0.f},
    };
    memset(G(p), 0, 304);
    for (unsigned k = 0; k < sizeof caps / sizeof caps[0]; k++) st(c, p + caps[k].off, caps[k].v, 4);
    for (unsigned k = 0; k < sizeof fcaps / sizeof fcaps[0]; k++) stf(c, p + fcaps[k].off, fcaps[k].v);
}
static uint32_t IDirect3D9_GetDeviceCaps(Ctx *c) {
    TR("GetDeviceCaps(%u, type %u)", ARG(1), ARG(2));
    if (ARG(1) != 0 || !ARG(3)) return D3DERR_INVALIDCALL;
    if (ARG(2) != 1) return D3DERR_NOTAVAILABLE;
    put_caps(c, ARG(3));
    return D3D_OK;
}
static uint32_t IDirect3D9_GetAdapterMonitor(Ctx *c) { TR("GetAdapterMonitor(%u)", ARG(1)); return ARG(1) == 0 ? 0x10005 : 0; }

// ---- the device -----------------------------------------------------------------------------
// Render, texture stage and sampler state defaults of the d3d9 documentation.
#define F1 0x3f800000u
static const uint32_t rs_default[][2] = {
    {8, 3}, {9, 2}, {14, 1}, {15, 0}, {16, 1}, {19, 2}, {20, 1}, {22, 3}, {23, 4}, {24, 0}, {25, 8}, {26, 0},
    {27, 0}, {28, 0}, {29, 0}, {34, 0}, {35, 0}, {36, 0}, {37, F1}, {38, F1}, {48, 0}, {52, 0}, {53, 1}, {54, 1},
    {55, 1}, {56, 8}, {57, 0}, {58, 0xffffffff}, {59, 0xffffffff}, {60, 0xffffffff}, {136, 1}, {137, 1},
    {139, 0}, {140, 0}, {141, 1}, {142, 1}, {143, 0}, {145, 1}, {146, 2}, {147, 0}, {148, 0}, {151, 0},
    {152, 0}, {154, F1}, {155, F1}, {156, 0}, {157, 0}, {158, F1}, {159, 0}, {160, 0}, {161, 1},
    {162, 0xffffffff}, {163, 0}, {165, 0}, {166, 0x42800000}, {167, 0}, {168, 0xf}, {170, 0}, {171, 1},
    {172, 3}, {173, 1}, {174, 0}, {175, 0}, {176, 0}, {178, F1}, {179, F1}, {180, 0}, {181, 0}, {182, F1},
    {183, 0}, {184, 0}, {185, 0}, {186, 1}, {187, 1}, {188, 1}, {189, 8}, {190, 0xf}, {191, 0xf}, {192, 0xf},
    {193, 0xffffffff}, {194, 0}, {195, 0}, {206, 0}, {207, 2}, {208, 1}, {209, 1},
};
typedef struct { uint32_t x, y, w, h; float zmin, zmax; } Viewport;
static struct {
    uint32_t guest, flags, window;
    uint32_t pp[14];                    // D3DPRESENT_PARAMETERS as the game gave them, completed
    uint32_t backbuf, depth;            // object indexes + 1
    uint32_t rt[4], ds;
    uint32_t rs[256], tss[8][33], ss[16][14];
    float xf[512][16];
    Viewport vp;
    uint32_t scissor[4];
    int in_scene;
    uint32_t frames;
    uint32_t decl, fvf, vs, ps, ib, tex[16];    // object indexes + 1
    struct { uint32_t vb, off, stride, freq; } stream[16];
    float vsf[256][4], psf[32][4];
    int32_t vsi[16][4], psi[16][4];
    uint32_t vsb[16], psb[16];
    uint32_t material[17];
    uint32_t light[64][26], light_on[64], light_set[64];
    float clip[6][4];
    int cursor_shown;
    uint16_t gamma[3][256];
    int recording;                      // between BeginStateBlock and EndStateBlock
    struct Rec *rec;
    uint32_t nrec, caprec;
} dev;

// A recorded Set call: the handler, its arguments (a[0] = the device) and a guest copy of the data
// its pointer argument pointed to. While recording, Set calls are recorded and not applied.
typedef struct Rec { HostFn fn; uint32_t n, a[6]; int pidx; uint32_t bytes; } Rec;
static uint32_t record(Ctx *c, HostFn fn, uint32_t n, int pidx, uint32_t bytes) {
    if (dev.nrec == dev.caprec) {
        dev.caprec = dev.caprec ? 2 * dev.caprec : 64;
        dev.rec = realloc(dev.rec, sizeof(Rec) * dev.caprec);
    }
    Rec *r = &dev.rec[dev.nrec++];
    r->fn = fn; r->n = n; r->pidx = pidx; r->bytes = bytes;
    for (uint32_t k = 0; k < n; k++) r->a[k] = ARG(k);
    if (pidx >= 0) {
        if (!r->a[pidx]) return D3DERR_INVALIDCALL;
        uint32_t d = guest_alloc(bytes ? bytes : 4);
        memcpy(G(d), G(r->a[pidx]), bytes);
        r->a[pidx] = d;
    }
    return D3D_OK;
}
#define REC(fn, n, pidx, bytes) do { if (dev.recording) return record(c, fn, n, pidx, bytes); } while (0)

static Obj *obj_k(uint32_t k1) { return k1 ? &objs[k1 - 1] : NULL; }
// Dead and bound nowhere: a released surface, a released texture, or a level of a released texture.
static int bound(int k) {
    uint32_t k1 = (uint32_t)k + 1;
    if (k1 == dev.backbuf || k1 == dev.depth || k1 == dev.ds) return 1;
    for (int i = 0; i < 4; i++) if (dev.rt[i] == k1) return 1;
    for (int i = 0; i < 16; i++) if (dev.tex[i] == k1 || dev.stream[i].vb == k1) return 1;
    return k1 == dev.ib;
}
static int slot_free(int k) {
    const Obj *o = &objs[k];
    if (bound(k)) return 0;
    if (o->iface == I_TEXTURE || o->iface == I_CUBE || o->iface == I_VB || o->iface == I_IB) return !o->refs;
    if (o->iface != I_SURFACE) return 0;
    if (!o->container) return !o->refs;
    const Obj *t = &objs[o->container - 1];
    return (t->iface == I_TEXTURE || t->iface == I_CUBE) && !t->refs && !bound((int)o->container - 1);
}
// guest memory (lock_mem) held by dead objects and by live ones, bytes (host/win32.c guest_mem_log)
void d3d9_mem(uint32_t *dead, uint32_t *live) {
    *dead = *live = 0;
    for (int k = 0; k < nobjs; k++) if (objs[k].mem) *(slot_free(k) ? dead : live) += objs[k].size ? objs[k].size : 16;
}

static uint32_t new_surface(Ctx *c, uint32_t w, uint32_t h, uint32_t f, uint32_t usage, uint32_t pool, int lockable) {
    uint32_t g = new_obj(c, I_SURFACE);
    if (!g) return 0;
    Obj *o = &objs[top];
    o->w = w; o->h = h; o->fmt = f; o->usage = usage; o->pool = pool; o->type = 1; o->lockable = lockable;
    o->pitch = pitch_of(f, w);
    o->size = size_of(f, w, h);
    if (usage & (U_RENDERTARGET | U_DEPTHSTENCIL)) {
        o->gpu = idx(o) + 1;
        uint32_t t[4] = {o->gpu, w, h, (usage & U_DEPTHSTENCIL) ? 1u : 0u};
        gpu_cmd(GPU_TARGET, 4, t);
        if (pool == POOL_DEFAULT) vram_used += o->size;
    }
    return g;
}
static void reset_viewport(Obj *rt) {
    dev.vp = (Viewport){0, 0, rt->w, rt->h, 0.f, 1.f};
    dev.scissor[0] = 0; dev.scissor[1] = 0; dev.scissor[2] = rt->w; dev.scissor[3] = rt->h;
}
static void default_state(void) {
    memset(dev.rs, 0, sizeof dev.rs);
    for (unsigned k = 0; k < sizeof rs_default / sizeof rs_default[0]; k++) dev.rs[rs_default[k][0]] = rs_default[k][1];
    dev.rs[7] = dev.pp[9] ? 1 : 0;                  // ZENABLE: on with an automatic depth buffer
    for (int s = 0; s < 8; s++) {
        uint32_t *t = dev.tss[s];
        memset(t, 0, sizeof dev.tss[s]);
        t[1] = s ? 1 : 4; t[2] = 2; t[3] = 1; t[4] = s ? 1 : 2; t[5] = 2; t[6] = 1; t[11] = (uint32_t)s;
        t[26] = 1; t[27] = 1; t[28] = 1;
    }
    for (int s = 0; s < 16; s++) {
        uint32_t *t = dev.ss[s];
        memset(t, 0, sizeof dev.ss[s]);
        t[1] = t[2] = t[3] = 1; t[5] = t[6] = 1; t[10] = 1;
    }
    for (int m = 0; m < 512; m++) {
        memset(dev.xf[m], 0, sizeof dev.xf[m]);
        dev.xf[m][0] = dev.xf[m][5] = dev.xf[m][10] = dev.xf[m][15] = 1.f;
    }
}

// D3DPRESENT_PARAMETERS of CreateDevice and Reset: checked, completed and written back like the runtime does.
static uint32_t take_pp(Ctx *c, uint32_t pp, uint32_t window) {
    uint32_t *p = dev.pp;
    int windowed = p[8] != 0;
    if (!p[0] || !p[1]) {
        if (!windowed) return D3DERR_INVALIDCALL;
        rn_halt(c, "d3d9: windowed device sized from window %08x", window);
        return D3DERR_INVALIDCALL;
    }
    if (!windowed) {
        int found = 0;
        for (int k = 0; k < NMODES; k++) { uint32_t mw, mh; mode_at(k, &mw, &mh); found |= mw == p[0] && mh == p[1]; }
        if (!found || (!display_fmt(p[2]) && p[2] != F_A8R8G8B8)) return D3DERR_INVALIDCALL;
        if (p[12] && p[12] != 60) return D3DERR_INVALIDCALL;
    }
    if (p[2] == F_UNKNOWN) p[2] = F_X8R8G8B8;
    if (!backbuffer_ok(p[2] == F_A8R8G8B8 || p[2] == F_X8R8G8B8 ? F_X8R8G8B8 : p[2], p[2], windowed))
        return D3DERR_INVALIDCALL;
    if (p[3] == 0) p[3] = 1;
    if (p[3] > 3 || p[4] || (p[9] && !ds_fmt(p[10]))) {
        rn_halt(c, "d3d9: CreateDevice with %u back buffers, multisample %u, depth fmt %u", p[3], p[4], p[10]);
        return D3DERR_INVALIDCALL;
    }
    for (int k = 0; k < 14; k++) st(c, pp + 4 * k, p[k], 4);     // the runtime writes back what it chose
    return D3D_OK;
}
// The implicit swap chain: back buffer and automatic depth buffer from dev.pp, then the default state.
static void swap_chain(Ctx *c) {
    uint32_t *p = dev.pp;
    uint32_t bb = new_surface(c, p[0], p[1], p[2], U_RENDERTARGET, POOL_DEFAULT, (p[11] & 1) != 0);  // LOCKABLE_BACKBUFFER
    Obj *b = obj_of(c, bb, I_SURFACE);
    b->container = 0;
    memset(dev.rt, 0, sizeof dev.rt);
    dev.backbuf = dev.rt[0] = idx(b) + 1;
    dev.depth = dev.ds = 0;
    if (p[9]) {
        Obj *d = obj_of(c, new_surface(c, p[0], p[1], p[10], U_DEPTHSTENCIL, POOL_DEFAULT, p[10] == F_D16_LOCKABLE), I_SURFACE);
        dev.depth = dev.ds = idx(d) + 1;
    }
    default_state();
    reset_viewport(b);
}

static uint32_t IDirect3D9_CreateDevice(Ctx *c) {
    uint32_t ad = ARG(1), type = ARG(2), focus = ARG(3), flags = ARG(4), pp = ARG(5), out = ARG(6);
    if (ad != 0 || !out || !pp) return D3DERR_INVALIDCALL;
    for (int k = 0; k < 14; k++) dev.pp[k] = ld(c, pp + 4 * k, 4);
    uint32_t *p = dev.pp;
    rn_log("d3d9 CreateDevice(%u, type %u, focus %08x, flags %x): %ux%u fmt %u x%u ms %u/%u swap %u hwnd %08x "
           "windowed %u autodepth %u fmt %u flags %x %u Hz interval %x",
           ad, type, focus, flags, p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], p[11], p[12], p[13]);
    if (type != 1) return D3DERR_NOTAVAILABLE;
    if (dev.guest) { rn_halt(c, "d3d9: a second device"); return D3DERR_INVALIDCALL; }
    uint32_t window = p[7] ? p[7] : focus;
    uint32_t r = take_pp(c, pp, window);
    if (r != D3D_OK) return r;
    // Without D3DCREATE_FPU_PRESERVE the runtime sets the calling thread's FPU to single precision, round to nearest, and
    // masks every exception (Wine wined3d setup_fpu: cw = (cw & ~0xf3f) | 0x3f). The game's _controlfp(3, 0x8001f) at
    // 0x40884d leaves invalid/zero/overflow unmasked (0x232); on Windows CreateDevice masks them again, so a NaN into
    // pow 0x5443f0 gives a quiet NaN instead of c0000090 (docs/openworld/re_answers_0b.md Q6).
    if (!(flags & 2)) c->fcw = (c->fcw & ~0xf3fu) | 0x3f;
    dev.flags = flags;
    dev.window = window;
    dev.guest = new_obj(c, I_DEVICE);
    objs[ld(c, d3d9_obj + 4, 4) - 1].refs++;
    swap_chain(c);
    st(c, out, dev.guest, 4);
    return D3D_OK;
}

#define DEV() do { if (ARG(0) != dev.guest) { rn_halt(c, "d3d9: %08x is not the device", ARG(0)); return D3DERR_INVALIDCALL; } } while (0)

static uint32_t IDirect3DDevice9_TestCooperativeLevel(Ctx *c) { DEV(); return D3D_OK; }
// Reset (d3d9 docs): fails unless every D3DPOOL_DEFAULT resource but the implicit back buffer and depth buffer
// is released; makes a new swap chain from the new parameters and puts all device state back to its defaults.
static uint32_t IDirect3DDevice9_Reset(Ctx *c) {
    DEV();
    uint32_t pp = ARG(1);
    if (!pp) return D3DERR_INVALIDCALL;
    if (dev.recording) { rn_halt(c, "d3d9: Reset while recording a state block"); return D3DERR_INVALIDCALL; }
    for (int k = 0; k < nobjs; k++) {
        Obj *o = &objs[k];
        int implicit = (uint32_t)k + 1 == dev.backbuf || (uint32_t)k + 1 == dev.depth;
        int resource = o->iface == I_SURFACE || o->iface == I_TEXTURE || o->iface == I_CUBE || o->iface == I_VB || o->iface == I_IB;
        if (resource && !o->container && o->pool == POOL_DEFAULT && o->refs > (implicit ? 1u : 0u)) {
            rn_halt(c, "d3d9: Reset with a live D3DPOOL_DEFAULT %s %08x (%u refs)", iface_name[o->iface], o->guest, o->refs);
            return D3DERR_INVALIDCALL;
        }
    }
    rn_screen_apply(c, pp);   // a page screen request lands here (host/win32.c rn_request_screen)
    uint32_t old[14];
    memcpy(old, dev.pp, sizeof old);
    for (int k = 0; k < 14; k++) dev.pp[k] = ld(c, pp + 4 * k, 4);
    uint32_t *p = dev.pp;
    rn_log("d3d9 Reset: %ux%u fmt %u x%u ms %u/%u swap %u hwnd %08x windowed %u autodepth %u fmt %u flags %x %u Hz interval %x",
           p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], p[11], p[12], p[13]);
    uint32_t r = take_pp(c, pp, p[7] ? p[7] : dev.window);
    if (r != D3D_OK) { memcpy(dev.pp, old, sizeof old); return r; }
    for (uint32_t k1 = dev.backbuf, j = 0; j < 2; k1 = dev.depth, j++) {
        Obj *o = obj_k(k1);
        if (o) { o->refs = 0; vram_used -= o->size; }
    }
    dev.decl = dev.fvf = dev.vs = dev.ps = dev.ib = 0;
    memset(dev.tex, 0, sizeof dev.tex);
    memset(dev.stream, 0, sizeof dev.stream);
    memset(dev.vsf, 0, sizeof dev.vsf); memset(dev.psf, 0, sizeof dev.psf);
    memset(dev.vsi, 0, sizeof dev.vsi); memset(dev.psi, 0, sizeof dev.psi);
    memset(dev.vsb, 0, sizeof dev.vsb); memset(dev.psb, 0, sizeof dev.psb);
    memset(dev.material, 0, sizeof dev.material);
    memset(dev.light, 0, sizeof dev.light); memset(dev.light_on, 0, sizeof dev.light_on);
    memset(dev.light_set, 0, sizeof dev.light_set);
    memset(dev.clip, 0, sizeof dev.clip);
    swap_chain(c);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetAvailableTextureMem(Ctx *c) {
    DEV();
    uint32_t m = (VRAM - vram_used + (1u << 19)) & ~((1u << 20) - 1);     // rounded to the nearest MB
    TR("GetAvailableTextureMem -> %u", m);
    return m;
}
static uint32_t IDirect3DDevice9_GetDirect3D(Ctx *c) {
    DEV();
    objs[ld(c, d3d9_obj + 4, 4) - 1].refs++;
    st(c, ARG(1), d3d9_obj, 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetDeviceCaps(Ctx *c) { DEV(); TR("Device GetDeviceCaps"); put_caps(c, ARG(1)); return D3D_OK; }
static uint32_t IDirect3DDevice9_GetDisplayMode(Ctx *c) {
    DEV();
    if (ARG(1) != 0) return D3DERR_INVALIDCALL;
    if (dev.pp[8]) put_mode(c, ARG(2), DESK_W, DESK_H, F_X8R8G8B8);
    else put_mode(c, ARG(2), dev.pp[0], dev.pp[1], dev.pp[2] == F_A8R8G8B8 ? F_X8R8G8B8 : dev.pp[2]);
    return D3D_OK;
}
static uint32_t ref_out(Ctx *c, uint32_t out, uint32_t k1) {
    Obj *o = obj_k(k1);
    if (!o) { st(c, out, 0, 4); return D3DERR_NOTFOUND; }
    if (o->container) objs[o->container - 1].refs++; else o->refs++;
    st(c, out, o->guest, 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetBackBuffer(Ctx *c) {
    DEV();
    if (ARG(1) != 0 || ARG(2) >= dev.pp[3] || !ARG(4)) return D3DERR_INVALIDCALL;
    if (ARG(2) != 0) { rn_halt(c, "d3d9: GetBackBuffer(%u)", ARG(2)); return D3DERR_INVALIDCALL; }
    return ref_out(c, ARG(4), dev.backbuf);
}
static uint32_t IDirect3DDevice9_GetRenderTarget(Ctx *c) {
    DEV();
    if (ARG(1) >= 4 || !ARG(2)) return D3DERR_INVALIDCALL;
    return ref_out(c, ARG(2), dev.rt[ARG(1)]);
}
static uint32_t IDirect3DDevice9_GetDepthStencilSurface(Ctx *c) { DEV(); return ref_out(c, ARG(1), dev.ds); }

static uint32_t IDirect3DDevice9_BeginScene(Ctx *c) {
    DEV();
    if (dev.in_scene) return D3DERR_INVALIDCALL;
    dev.in_scene = 1;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_EndScene(Ctx *c) {
    DEV();
    if (!dev.in_scene) return D3DERR_INVALIDCALL;
    dev.in_scene = 0;
    return D3D_OK;
}

// Clear: each rectangle, clipped to the viewport (and the scissor rectangle when the scissor test is on).
static uint32_t IDirect3DDevice9_Clear(Ctx *c) {
    DEV();
    uint32_t n = ARG(1), rects = ARG(2), flags = ARG(3), color = ARG(4), z = ARG(5), stencil = ARG(6);
    Obj *rt = obj_k(dev.rt[0]), *ds = obj_k(dev.ds);
    TR("Clear(%u rects, flags %x, color %08x, z %g, stencil %u)", n, flags, color, (double)ldf(c, c->r[ESP] + 24), stencil);
    if ((n && !rects) || (flags & ~7u) || !flags) return D3DERR_INVALIDCALL;
    if ((flags & 6) && !ds) return D3DERR_INVALIDCALL;
    if ((flags & 4) && ds->fmt != F_D24S8 && ds->fmt != F_D15S1 && ds->fmt != F_D24X4S4 && ds->fmt != F_D24FS8)
        return D3DERR_INVALIDCALL;
    int x0 = (int)dev.vp.x, y0 = (int)dev.vp.y, x1 = x0 + (int)dev.vp.w, y1 = y0 + (int)dev.vp.h;
    if (dev.rs[174]) {
        if ((int)dev.scissor[0] > x0) x0 = (int)dev.scissor[0];
        if ((int)dev.scissor[1] > y0) y0 = (int)dev.scissor[1];
        if ((int)dev.scissor[2] < x1) x1 = (int)dev.scissor[2];
        if ((int)dev.scissor[3] < y1) y1 = (int)dev.scissor[3];
    }
    for (uint32_t k = 0; k < (n ? n : 1); k++) {
        int a0 = x0, b0 = y0, a1 = x1, b1 = y1;
        if (n) {
            int32_t r[4];
            for (int i = 0; i < 4; i++) r[i] = (int32_t)ld(c, rects + 16 * k + 4 * i, 4);
            if (r[0] > a0) a0 = r[0];
            if (r[1] > b0) b0 = r[1];
            if (r[2] < a1) a1 = r[2];
            if (r[3] < b1) b1 = r[3];
        }
        if (a0 >= a1 || b0 >= b1) continue;
        uint32_t w[10] = {(flags & 1) ? rt->gpu : 0, (flags & 6) ? ds->gpu : 0, flags, color, z, stencil,
                          (uint32_t)a0, (uint32_t)b0, (uint32_t)a1, (uint32_t)b1};
        gpu_cmd(GPU_CLEAR, 10, w);
    }
    return D3D_OK;
}

// ?pace=vsync (web/gpu.js, OFF by default; th0mk/nfsu2-web framerate.c grid()/pace()): in a race the game makes one frame
// per display slot instead of spinning on QPC. The page writes pace_box at each animation frame: [0] the refresh time (ms,
// timeOrigin based = emscripten_get_now), [1] the measured refresh period (ms; 0 = pacing off). Present plans the end of
// this frame's slot: k refreshes per frame (1 at 60 Hz, 2 at 120 Hz; no pacing when k refreshes are not ~1/60 s, e.g.
// 144 Hz), boundaries half a refresh after a vsync, a frame longer than its slot takes the next boundary (nfsu2 "missed").
// hand_off then sleeps to it without the GIL. The limiter 0x585b40 skips its race wait (bit 6 of the PATCH 0x585b94 load
// mask [0x707fc8]); its QPC dt stays the real elapsed time, so physics steps the same 1/60 s. Menus and loads unchanged.
static double pace_box[2], pace_next, pace_due;
#ifdef __EMSCRIPTEN__
#include <math.h>
#include <emscripten.h>
#include <emscripten/threading.h>
static void pace_plan(Ctx *c) {
    static double nr_next;
    pace_due = 0;
    double per = pace_box[1];
    if (per >= 4 && per <= 50) {
        // The game's frame target [0x6f0890] (1/60 s; 1/30 with RN_FPS=30, host/win32.c): k refreshes per game frame.
        double tgt = 1000.0 * ldf(c, 0x6f0890);
        if (tgt < 10 || tgt > 50) tgt = 1000.0 / 60;
        int k = (int)(tgt / per + 0.5);
        if (k < 1) k = 1;
        int on = fabs(k * per - tgt) <= 1.5;                    // else the limiter keeps its race wait
        uint32_t m = ld(c, 0x707fc8, 4), rs = ld(c, 0x7361f0, 4);
        if (!!(m & 0x40) != on) st(c, 0x707fc8, on ? m | 0x40 : m & ~0x40u, 4);
        if (on && rn_racing() && rs && ld(c, rs, 4) != 1) {
            nr_next = 0;
            double now = emscripten_get_now(), b = pace_box[0] + per / 2;
            double next = pace_next ? pace_next + k * per : now;
            if (next < now) next = now;                         // missed its slot: the next boundary
            pace_next = pace_due = b + ceil((next - b) / per - 0.25) * per;   // onto the refresh grid
            return;
        }
    }
    pace_next = 0;
    // Cap any uncapped Present() loop (e.g. PC_Loading.fng, even while HUD_SingleRace.fng is mounted)
    // to <= 60 fps (16.67 ms) without holding the GIL; frames already paced <= 60 fps pay zero wait.
    double now = emscripten_get_now();
    if (nr_next > now) pace_due = nr_next;
    nr_next = (nr_next > now ? nr_next : now) + (1000.0 / 60.0);
}
static void pace_sleep(void) {
    static uint32_t z;
    double ms;
    while (pace_due && (ms = pace_due - emscripten_get_now()) > 0.05) emscripten_futex_wait(&z, 0, ms);
    pace_due = 0;
}
#else
static void pace_plan(Ctx *c) { (void)c; }
static void pace_sleep(void) {}
#endif

// Spike probe for the OWNER's F10 (OWNER log 2026-11-01 03:37: 47 race frames > 22 ms, no pipeline or texture work in them).
// A race frame longer than 23 ms (Present to Present) logs its clock reads by call site (host/win32.c clk_site) and its file
// reads: a long busy wait names its loop, a frame with few clock reads is the game's own work.
extern uint32_t rn_clk_site[8], rn_clk_n[8];
static RnStab rn_stab;
static int rn_hud_on;   // the race HUD is up this frame (set where "d3d9 race HUD" is logged): the window the OWNER drives in
#ifdef __EMSCRIPTEN__
EMSCRIPTEN_KEEPALIVE uint32_t rn_stab_addr(void) { return (uint32_t)(uintptr_t)&rn_stab; }
#endif
static void spike_log(Ctx *c) {
    static uint64_t t0;
    static uint32_t clk0, reads0, kb0, race0;
    static double ms0;
    uint64_t t = now_us();
    float hold_ms = gil_frame_hold_ms(), wait_ms, other_ms;
    uint32_t other_who;
    gil_frame_detail(&wait_ms, &other_ms, &other_who);
    // Counted only while the HUD is up: the grid's load (model lookups, sound banks) and the pause menu stay out
    // (build/stab_route.out: 3 of 4 frames > 23 ms came before "d3d9 race HUD"). A new rn_race starts a new race_id.
    uint32_t racing = rn_racing() && rn_hud_on;
    if (racing && (!rn_stab.race_id || race0 != rn_race)) {
        uint32_t id = rn_stab.race_id + 1;
        rn_stab = (RnStab){.race_id = id};
        race0 = rn_race;
    }
    rn_stab.racing = racing;
    if (t0 && t - t0 > 23000 && racing) {
        rn_stab.spikes++;
        rn_stab.last_frame = rn_telem.presents;
        rn_stab.last_ms = (float)((t - t0) / 1000.0);
        rn_stab.last_reads = rn_telem.reads - reads0;
        rn_stab.last_read_kb = rn_telem.read_kb - kb0;
        rn_stab.last_read_ms = (float)(rn_telem.read_ms - ms0);
        rn_stab.last_hold_ms = hold_ms;
        memset(rn_stab.site, 0, sizeof rn_stab.site);
        memset(rn_stab.site_n, 0, sizeof rn_stab.site_n);
        char top[160] = "";
        for (int n = 0, k; n < 3; n++) {
            int b = -1;
            for (k = 0; k < 8; k++) if (rn_clk_n[k] && (b < 0 || rn_clk_n[k] > rn_clk_n[b])) b = k;
            if (b < 0) break;
            rn_stab.site[n] = rn_clk_site[b];
            rn_stab.site_n[n] = rn_clk_n[b];
            snprintf(top + strlen(top), sizeof top - strlen(top), " 0x%x x%u", rn_clk_site[b], rn_clk_n[b]);
            rn_clk_n[b] = 0;
        }
        static int sxy = -1;   // RN_SPIKEXY=1 (off by default; Block 3, spikes at (1846,-727)): the player's xy on each spike line
        if (sxy < 0) sxy = getenv("RN_SPIKEXY") != NULL;
        char pxy[48] = "";
        if (sxy) {
            uint32_t ct = ld(c, 0x7361bc, 4), car = ct && ct < GUEST_MEM - 0x900 ? ld(c, ct + 4, 4) : 0;
            if (car && car < GUEST_MEM - 0x900) {
                float x, y;
                memcpy(&x, c->mem + car + 0x60, 4), memcpy(&y, c->mem + car + 0x64, 4);
                snprintf(pxy, sizeof pxy, ", pxy %.0f,%.0f", x, y);
            }
        }
        rn_log("spike: frame %u %.1f ms, clock %u:%s, reads %u (%u KB, %.1f ms), main waited %.1f ms, other hold %.1f ms by 0x%x%s", rn_telem.presents, (t - t0) / 1000.0,
               rn_telem.clock_calls - clk0, top, rn_telem.reads - reads0, rn_telem.read_kb - kb0, rn_telem.read_ms - ms0, wait_ms, other_ms, other_who, pxy);
    }
    memset(rn_clk_n, 0, sizeof rn_clk_n);
    t0 = t, clk0 = rn_telem.clock_calls, reads0 = rn_telem.reads, kb0 = rn_telem.read_kb, ms0 = rn_telem.read_ms;
}

// The list goes to the renderer in parts of at most 16 MB: a load can upload hundreds of MB of
// texels in one frame, more than the web build's heap holds at once. Commands keep their order.
// The list is handed off under the GIL; the wait for the page is without it.
static void hand_off(void) {
    gpu_submit(); gil_release();
    uint64_t t0 = now_us();
    gpu_wait();
    rn_telem.gpu_wait_ms += (double)(now_us() - t0) / 1000;   // written before the GIL is back: only this thread presents
    pace_sleep();
    gil_acquire();
}
static void flush_big(void) { if (gpu_pending() > (4u << 20)) hand_off(); }

// RN_DRAWS=<min frame>: census of the indexed draws of the first frame at or after it that has >= 300 of them (a race frame):
// who calls, which shaders/declaration/textures. Logged at its Present.
static struct { uint32_t caller, vs, ps, decl, stride, tex0, tex1, rtw, n, prims; } cen[256];
static int ncen, cen_on = -1;
static uint32_t cen_frame, cen_total;
static void census_draw(Ctx *c, uint32_t prims) {
    Obj *rt = obj_k(dev.rt[0]);
    uint32_t k[8] = {ld(c, c->r[ESP], 4), dev.vs, dev.ps, dev.decl, dev.stream[0].stride, dev.tex[0], dev.tex[1], rt ? rt->w : 0};
    int i = 0;
    while (i < ncen && memcmp(&cen[i], k, sizeof k)) i++;
    if (i == ncen) { if (ncen == 256) return; memset(&cen[ncen], 0, sizeof cen[0]); memcpy(&cen[ncen++], k, sizeof k); }
    cen[i].n++; cen[i].prims += prims; cen_total++;
}
static void disasm_line(const char *l);
static const Obj *car_vs_obj[8];   // the car body vertex shader objects (token hash 0x4728b668); dev.vs is an internal index, not the game's handle
static int ncar_vs;
static const Obj *bone_vs_obj[8];  // fx\worldbone.efx's vertex shader (token hash 0x95d99bf8): the skinned NIS people (flag girl, crowd)
static int nbone_vs;
// Content hash of a shader's tokens: stable across runs, unlike the object id.
static uint32_t shader_hash(const Obj *o) {
    uint32_t h = 2166136261u;
    for (uint32_t k = 0; k < o->nblob; k++) h = (h ^ ((const uint32_t *)o->blob)[k]) * 16777619u;
    return h;
}
static void census_dump(void) {
    for (int a = 0; a < ncen; a++) for (int b = a + 1; b < ncen; b++) if (cen[b].prims > cen[a].prims) { __typeof__(cen[0]) t = cen[a]; cen[a] = cen[b]; cen[b] = t; }
    rn_log("DRAWS frame %u: %u draws, %d groups", dev.frames, cen_total, ncen);
    for (int i = 0; i < ncen; i++)
        { const Obj *t1 = obj_k(cen[i].tex1);
        rn_log("DRAWS caller=%08x vs=%x ps=%x decl=%x stride=%u tex0=%x tex1=%x rt=%u draws=%u prims=%u tex1dim=%ux%u fmt=%u", cen[i].caller, cen[i].vs, cen[i].ps,
               cen[i].decl, cen[i].stride, cen[i].tex0, cen[i].tex1, cen[i].rtw, cen[i].n, cen[i].prims, t1 ? t1->w : 0, t1 ? t1->h : 0, t1 ? t1->fmt : 0); }
    // The code of every distinct vs/ps pair of the frame, once.
    for (int i = 0; i < ncen; i++) {
        int seen = 0;
        for (int j = 0; j < i; j++) if (cen[j].vs == cen[i].vs && cen[j].ps == cen[i].ps) seen = 1;
        if (seen) continue;
        Obj *v = obj_k(cen[i].vs), *p = obj_k(cen[i].ps);
        rn_log("DRAWS SHADER vs=%x hash=%08x", cen[i].vs, v ? shader_hash(v) : 0); if (v && v->sm) sm1_disasm(v->sm, disasm_line);
        rn_log("DRAWS SHADER ps=%x hash=%08x", cen[i].ps, p ? shader_hash(p) : 0); if (p && p->sm) sm1_disasm(p->sm, disasm_line);
    }
}
// Blur bank (web/tune.js: ?blur=, F6/F7). The motion blur 0x40cd40 reads only these .data floats (V, Hopper xrefs
// 2026-10-24): ramp start/end in m/s at 0x702a38/0x702a3c (40ce6e), the cap of t at 0x702a40 (40ced4, 40cee1; composite
// TEXTUREFACTOR alpha = min(1.5 t, 1)), streak length per t at 0x702a44 (40cf2c). A 5th word is the light-trail colour
// at 0x707fcc (PATCH 0x409bdb: the add weight of the flare buffer, D3DCOLOR). The page writes the 5 words, then bumps
// seq; Present copies them into the game's .data when seq changed.
static uint32_t tune[11];     // seq, then the 4 floats as bits, then the trail colour, the speed-FOV gain (degrees, float bits), the chase-camera switch, the nitro-camera switch, the widescreen scale k (float bits, 0 = shipped), the light-trail decay BLENDFACTOR (0 = shipped 0x008296b4)
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
EMSCRIPTEN_KEEPALIVE uint32_t rn_tune_addr(void) { return (uint32_t)(uintptr_t)tune; }
#endif
static void tune_apply(Ctx *c) {
    static uint32_t seen;
    uint32_t s = __atomic_load_n(&tune[0], __ATOMIC_ACQUIRE);
    if (s == seen) return;
    seen = s;
    for (int k = 0; k < 4; k++) st(c, 0x702a38 + 4 * k, tune[1 + k], 4);
    if (tune[5]) st(c, 0x707fcc, tune[5], 4);
    float f[4];
    memcpy(f, &tune[1], sizeof f);
    rn_log("d3d9 blur bank: ramp %.2f-%.2f m/s, cap %.3f, streak %.5f, trails %08x decay %06x", f[0], f[1], f[2], f[3], tune[5], tune[10]);
}
// Speed FOV (web/tune.js ?speedfov=, word 6 of tune[]): the chase camera mover (type 0x11, update 0x48bcb0) reads the s16 FOV table
// 0x6fbdf4 every frame (0x48bbed; POV 0, 1, 4 at +0, +2, +8, 0x32dc = 71.5 deg, 65536 = 360 deg), smooths it into camera+0xc4 (measured:
// under 1 s behind) and the projection builder 0x40dd00 reads that, so frustum and focal stay one. Hood, bumper and special cameras do not read these entries. Present writes the three entries from the camera's speed
// ([0x740500]+0x1e0, m/s): 0 at 25 m/s (90 km/h), the full gain at 75 m/s, smoothstep, then a ~1 s low pass (it also absorbs a
// camera teleport). The base is the table as boot left it (0x2ee0 with RN_FEEL, host/win32.c; 0x32dc in original mode). Gain 0 is the
// native default: nothing is touched, and a gain back to 0 restores the base once. RN_FOVLOG=1 logs.
static void fov_frame(Ctx *c) {
    static int lg = -1, wrote;
    static uint32_t base;
    static float deg;
    if (lg < 0) lg = getenv("RN_FOVLOG") != NULL, base = ld(c, 0x6fbdf4, 2);
    float gain; uint32_t gb = __atomic_load_n(&tune[6], __ATOMIC_RELAXED);
    memcpy(&gain, &gb, 4);
    if (gain == 0 && !wrote) return;
    uint32_t cam = ld(c, 0x740500, 4);
    if (!cam || cam >= GUEST_MEM - 0x200) return;
    float v[3] = {ldf(c, cam + 0x1e0), ldf(c, cam + 0x1e4), ldf(c, cam + 0x1e8)};
    float sp = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    float t = (sp - 25) / 50; t = t < 0 ? 0 : t > 1 ? 1 : t; t = t * t * (3 - 2 * t);
    deg += (gain * t - deg) * (1.0f / 60);
    if (gain == 0 && fabsf(deg) < 0.01f) deg = 0, wrote = 0;
    else wrote = 1;
    uint32_t e = base + (int)lroundf(deg * 65536 / 360);
    for (int k = 0; k < 3; k++) st(c, 0x6fbdf4 + (k == 2 ? 8 : 2 * k), e, 2);
    if (lg && dev.frames % 60 == 0)
        rn_log("FOV f%u speed %.1f gain %.1f deg %.2f table %04x cam+c4 %04x", (unsigned)dev.frames, sp, gain, deg, e, ld(c, cam + 0xc4, 2));
}
// Chase framing (web/tune.js ?chasecam=, word 7 of tune[], 1 = on): the default race camera (type 0x11) reads distance +4, height +8
// and lateral +0xc of the car's camera row (SetDesired 0x48b8c0 at 0x48ba2a; rows id 0, 1, 4 = far, close and high chase) from
// CarTypeInfo [[car+0xc]+0xb50]: +0x10 + 16 k (normal set) and +0x60 + 16 k (the [0x7364a0] == 3 set, 0x47d680). Present rewrites those
// rows of the player's car from its speed (same 25..75 m/s smoothstep and ~1 s low pass as the FOV): the camera sits up to CHASE_BACK
// farther and CHASE_LOW lower, relative to the row of that car (per-car data stays per car). Rows go back to the file values when
// the switch is off or the player's car changes. The mover smooths the target itself, so the change glides.
#define CHASE_BACK 0.0f    // distance x (1 + this * t); was 0.12, OWNER 2026-10-31: the camera must not go farther
#define CHASE_LOW  0.0f    // height   x (1 - this * t); was 0.10, OWNER 2026-10-31: lower at speed felt like chasing the car
#define CHASE_TILT 8.0f    // rows 0 and 1 (far, close chase) while on: the eye turns this many degrees up around the car at the same
                           // distance (far 16.3 -> 24.3 deg: -5.80/1.70 m -> -5.51/2.49 m), OWNER 2026-10-31: a steeper angle, not farther
// Nitro camera (?nitrocam=, word 8 of tune[]): while the player's nitrous burns (car+0x3bc, the start stamp 0x4654f0 writes and 0x465530
// clears when 0x465430 sees the shot end; 0 or 0x7fffffff = off) the same rows go NITRO_BACK farther and NITRO_LOW lower, ~0.5 s low pass.
#define NITRO_BACK 0.10f
#define NITRO_LOW  0.05f
// Horizontal FOV (web/tune.js ?hfov=, word 9 of tune[]): k at 0x707fc0 is the widescreen caves' scale (P[0] = k / tan(F/2) * H'/W, PATCH 0x40debb); the web
// page turns the wanted horizontal degrees at 16:9 into k. Written in races only (rn_racing(), the same test as the caves' 16:9 cap), so the garage keeps
// the shipped k = 512/448. Word 0: the shipped k.
static void hfov_frame(Ctx *c) {
    uint32_t k = __atomic_load_n(&tune[9], __ATOMIC_RELAXED);
    st(c, 0x707fc0, k && rn_racing() ? k : 0x3f924925, 4);
}
void ai_tel(Ctx *c);
void feel_tel(Ctx *c);
static void chase_frame(Ctx *c) {
    static uint32_t info, rows[2][3];
    static float orig[2][3][2], sm, nsm;
    static int nlast;
    uint32_t on = __atomic_load_n(&tune[7], __ATOMIC_RELAXED), non = __atomic_load_n(&tune[8], __ATOMIC_RELAXED), car = 0;
    uint32_t h = ld(c, 0x7361f8, 4);
    if (h && h < GUEST_MEM - 0x1000)
        for (uint32_t r = ld(c, h, 4), k = 0; r && r != h && r < GUEST_MEM - 0x1000 && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (e && e < GUEST_MEM - 16 && ld(c, e + 4, 4) == 1) { car = r; break; }
        }
    uint32_t ni = car ? ld(c, car + 0xc, 4) : 0;
    if (ni >= GUEST_MEM - 0xc00) ni = 0;
    if (info && ni != info) {   // another car (garage, next race): put the old rows back
        for (int s = 0; s < 2; s++) for (int k = 0; k < 3; k++) if (rows[s][k]) {
            stf(c, rows[s][k] + 4, orig[s][k][0]); stf(c, rows[s][k] + 8, orig[s][k][1]);
        }
        info = 0; sm = nsm = 0;
    }
    if (!on && !non && !info) return;
    if (!ni) return;
    if (!info) {
        static const int ids[3] = {0, 1, 4};
        for (int s = 0; s < 2; s++) for (int k = 0; k < 3; k++) {
            rows[s][k] = 0;
            for (int i = 0; i < 5; i++) {
                uint32_t a = ni + 0xb50 + (s ? 0x60 : 0x10) + 16 * i;
                if ((int16_t)ld(c, a, 2) == ids[k]) { rows[s][k] = a; orig[s][k][0] = ldf(c, a + 4); orig[s][k][1] = ldf(c, a + 8); break; }
            }
        }
        info = ni;
        rn_log("CHASE car %08x info %08x rows %08x %08x %08x: dist %.2f %.2f %.2f height %.2f %.2f %.2f", car, ni, rows[0][0], rows[0][1], rows[0][2],
               orig[0][0][0], orig[0][1][0], orig[0][2][0], orig[0][0][1], orig[0][1][1], orig[0][2][1]);
    }
    uint32_t cam = ld(c, 0x740500, 4);
    float t = 0;
    if (cam && cam < GUEST_MEM - 0x200) {
        float v[3] = {ldf(c, cam + 0x1e0), ldf(c, cam + 0x1e4), ldf(c, cam + 0x1e8)};
        t = (sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) - 25) / 50; t = t < 0 ? 0 : t > 1 ? 1 : t; t = t * t * (3 - 2 * t);
    }
    uint32_t ns = ld(c, car + 0x3bc, 4);
    int burn = non && ns != 0 && ns != 0x7fffffff;
    if (burn != nlast) { nlast = burn; rn_log("CHASE nitro %s (car+0x3bc %08x)", burn ? "on" : "off", ns); }
    sm += ((on ? t : 0) - sm) * (1.0f / 60);
    nsm += ((burn ? 1.0f : 0) - nsm) * (1.0f / 30);
    if (!on && sm < 0.001f) sm = 0;
    if (!burn && nsm < 0.001f) nsm = 0;
    float kb = 1 + CHASE_BACK * sm + NITRO_BACK * nsm, kl = 1 - CHASE_LOW * sm - NITRO_LOW * nsm;
    for (int s = 0; s < 2; s++) for (int k = 0; k < 3; k++) if (rows[s][k]) {
        float d = orig[s][k][0], h = orig[s][k][1];
        if (on && k < 2) {
            float r = hypotf(d, h), a = atan2f(h, fabsf(d)) + CHASE_TILT * 3.14159265f / 180;
            d = copysignf(r * cosf(a), d), h = r * sinf(a);
        }
        stf(c, rows[s][k] + 4, d * kb); stf(c, rows[s][k] + 8, h * kl);
    }
    if (!on && !non && sm == 0 && nsm == 0) info = 0;
}
// PS2-style depth speed blur (web/gpu.js psblur): out[0..2] = the view-1 camera's velocity [0x740500]+0x1e0 (camera 0x78d270; what the game's own blur 0x40cd40
// reads) in camera space, normalised, out[3] = its length (m/s); float bits, 0 when there is no camera. out[4] = nitrous on ([0x73654c],
// written by 0x4010e0 for the player's view), out[5..6] = the projection's _33 and _43 (block +0x40; z_ndc = _33 + _43 / z_view, so the
// page can turn the depth buffer into metres). Sent with GPU_FXAA.
// The camera block of the player's view (table 0x740460 + 0x60, +0 pointer; block +0 = View, rows 0..2 = the axes)
// maps world to camera: v_cam = v * R (D3D row vectors). RN_PSLOG=1 logs it each 60 frames.
static void psblur_vel(Ctx *c, uint32_t *out) {
    static int lg = -1;
    if (lg < 0) lg = getenv("RN_PSLOG") != NULL;
    out[0] = out[1] = out[2] = out[3] = out[4] = out[5] = out[6] = 0;
    uint32_t car = ld(c, 0x740500, 4), blk = ld(c, 0x7404c0, 4), blk0 = ld(c, 0x740460, 4);
    if (!car || !blk || car >= GUEST_MEM - 0x200 || blk >= GUEST_MEM - 0x80) return;
    float v[3] = {ldf(c, car + 0x1e0), ldf(c, car + 0x1e4), ldf(c, car + 0x1e8)}, m[32];
    for (int k = 0; k < 32; k++) m[k] = ldf(c, blk + 4 * k);
    out[4] = ld(c, 0x73654c, 4) != 0;
    memcpy(&out[5], &m[26], 4); memcpy(&out[6], &m[30], 4);
    float s = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]), r[3];
    for (int j = 0; j < 3; j++) r[j] = v[0] * m[j] + v[1] * m[4 + j] + v[2] * m[8 + j];
    if (lg && dev.frames % 60 == 0) {
        float n[16] = {0};
        if (blk0 && blk0 < GUEST_MEM - 0x40) for (int k = 0; k < 16; k++) n[k] = ldf(c, blk0 + 4 * k);
        float q[3];
        for (int j = 0; j < 3; j++) q[j] = v[0] * n[j] + v[1] * n[4 + j] + v[2] * n[8 + j];
        float t[3];   // the transposed reading (R * v)
        for (int j = 0; j < 3; j++) t[j] = m[4 * j] * v[0] + m[4 * j + 1] * v[1] + m[4 * j + 2] * v[2];
        // The car's own speed, the HUD's (+0x3d4 x 2.237 = mph, 0x6cc9f0; read so by 0x4286a0, 0x52b760): the player's node in the race
        // list [0x7361f8] (host/openworld.c player_node), next to the camera's (above).
        // Also the cars in the list by entrant kind (+0x14 -> +4: 1 player, 3 traffic; PATCH 0x598c4b).
        uint32_t h = ld(c, 0x7361f8, 4), pn = 0, kinds[5] = {0};
        if (h && h < GUEST_MEM - 0x1000)
            for (uint32_t r = ld(c, h, 4), k = 0; r && r != h && r < GUEST_MEM - 0x1000 && k < 200; r = ld(c, r, 4), k++) {
                uint32_t e = ld(c, r + 0x14, 4), kd = e && e < GUEST_MEM - 16 ? ld(c, e + 4, 4) : 4;
                kinds[kd < 4 ? kd : 4]++;
                if (kd == 1 && !pn) pn = r;
            }
        if (pn) rn_log("PSBLUR frame %u car %08x +0x3d4 %.2f m/s (%.1f mph) | list kinds 0:%u 1:%u 2:%u 3:%u other:%u", dev.frames, pn,
                       ldf(c, pn + 0x3d4), ldf(c, pn + 0x3d4) * 2.237f, kinds[0], kinds[1], kinds[2], kinds[3], kinds[4]);
        rn_log("PSBLUR frame %u speed %.2f v %.2f %.2f %.2f | view1 v*R %.2f %.2f %.2f R*v %.2f %.2f %.2f | view0 v*R %.2f %.2f %.2f | nitro %u P %.4f %.4f %.4f %.4f P33 %.5f P43 %.5f",
               dev.frames, s, v[0], v[1], v[2], r[0], r[1], r[2], t[0], t[1], t[2], q[0], q[1], q[2],
               out[4], m[16], m[21], m[26], m[27], m[26], m[30]);
    }
    if (s < 1e-3f) return;
    for (int j = 0; j < 3; j++) { r[j] /= s; memcpy(&out[j], &r[j], 4); }
    memcpy(&out[3], &s, 4);
}
// RN_RNGLOG: how many steps the game RNG [0x6f227c] took since the last Present (step inlined ~60 times, e.g. 0x41f81d:
// u = x ^ 0x1d872b41, v = u ^ u >> 5, x' = v ^ v << 27 ^ u). A frame with steps makes key timing matter in frames.
static void rng_log(Ctx *c, uint32_t frame) {
    static int on = -1;
    static uint32_t prev, total;
    if (on < 0) on = getenv("RN_RNGLOG") != NULL;
    if (!on) return;
    uint32_t x = ld(c, 0x6f227c, 4), n = 0;
    if (frame && x != prev) {
        for (uint32_t y = prev; n < 100000 && y != x; n++) { uint32_t u = y ^ 0x1d872b41, v = u ^ u >> 5; y = v ^ v << 27 ^ u; }
        total += n;
        rn_log("RNG frame %u: %d steps (total %u)", frame, n < 100000 ? (int)n : -1, total);
    } else if (!frame) rn_log("RNG seed %08x", x);
    prev = x;
}
// RN_FLOWLOG: each new game-flow label [0x77a90c] (a string in .rdata, e.g. 0x6c9c3c "EndGameFlowLoadingTrackSpecific")
// at the Present that first sees it: the bounds of the loads (tools/bench.py). Also each new game-flow state [0x77a920]
// (written at 0x448b11 .. 0x449a15: 1 loading FE, 2 unloading FE, 3 FE, 4/5 loading track, 6 race, 7 unloading track).
const char *rn_screen = "", *rn_fe = "";
// The front end's active packages: FEngine = [[0x73578c]+8], list head [+0xe4], node next +4, .fng name +0xc
// (cFEng::FindPackage 0x4f6600..0x4f661d walks it with 0x4fd1e0). The guest addresses of the names, at most 16.
static int fe_packages(Ctx *c, uint32_t np[16]) {
    uint32_t fg = ld(c, 0x73578c, 4), en = fg ? ld(c, fg + 8, 4) : 0, nd = en ? ld(c, en + 0xe4, 4) : 0;
    int n = 0;
    for (int i = 0; nd && nd < c->memsz && i < 16; i++, nd = ld(c, nd + 4, 4)) {
        uint32_t p = ld(c, nd + 0xc, 4);
        if (p && p < c->memsz) np[n++] = p;
    }
    return n;
}
// REA/Hopper: 0x5a05b0 calculates the 0..5 car reputation from RideInfo B at 0x745720 using
// the thresholds in 0x6ee3d8 and the part-point tables rooted at 0x733f78. Cash is career+0x1374
// ([0x76026c], read by 0x5a1520). Keep this read-only mirror in sync with that shipped calculation.
static int career_rating(Ctx *c, float *rating) {
    const uint32_t rows = 0x6ee3d8, ride = 0x745720, data_ptrs = 0x733f78;
    double a = 0, b = 0, d = 0, score = 0;
    int ended = 0;
    for (uint32_t i = 0; i < 32; i++) {
        uint32_t row = rows + i * 12, type = ld(c, row, 4);
        if (type == ~0u) { ended = 1; break; }
        if (type >= 32) continue;
        uint32_t table = ld(c, data_ptrs + type * 4, 4);
        if (table < LOW || table > c->memsz - 0x20) return 0;
        uint32_t flags = ld(c, row + 8, 4);
        if (flags & 1) a += (int32_t)ld(c, table + 0x10, 4);
        if (flags & 2) b += (int32_t)ld(c, table + 0x14, 4);
        if (flags & 4) d += (int32_t)ld(c, table + 0x18, 4);
    }
    if (!ended || a <= 0 || b <= a || d <= b || ride > c->memsz - 0x700) return 0;
    for (uint32_t i = 0; i < 32; i++) {
        uint32_t row = rows + i * 12, type = ld(c, row, 4);
        if (type == ~0u) break;
        if (type >= 32) continue;
        uint32_t table = ld(c, data_ptrs + type * 4, 4), level = 0;
        if (table < LOW || table > c->memsz - 0x20) return 0;
        if (type == 7) {
            for (uint32_t j = 0; j < 4; j++) {
                uint32_t part = ld(c, ride + 0x4c8 + j * 4, 4);
                if (!part) continue;
                if (part > c->memsz - 0x12) return 0;
                uint32_t n = ld(c, part + 0x11, 1);
                if (level < n) level = n;
            }
        } else if (type == 1) {
            static const struct { uint32_t first, last, level; } groups[] = {{0x3b, 0x40, 3}, {0x53, 0x70, 2}, {0x43, 0x50, 1}};
            for (uint32_t g = 0; g < sizeof groups / sizeof groups[0] && !level; g++)
                for (uint32_t slot = groups[g].first; slot <= groups[g].last; slot++)
                    if (ld(c, ride + 0x44c + slot * 4, 4)) { level = groups[g].level; break; }
        } else {
            uint32_t slot = ld(c, row + 4, 4);
            if (slot >= 0x78) return 0;
            uint32_t part = ld(c, ride + 0x44c + slot * 4, 4);
            if (part) {
                if (part > c->memsz - 0x12) return 0;
                level = ld(c, part + 0x11, 1);
            }
        }
        if (level >= 1 && level <= 4) score += (int32_t)ld(c, table + 0x0c + level * 4, 4);
    }
    double value = score < a ? 2.0 * score / a : score < b ? 2.0 + 2.0 * (score - a) / (b - a)
                                                               : 4.0 + (score - b) / (d - b);
    if (value > 5.0) value = 5.0;
    *rating = (float)value;
    return 1;
}
static void flow_log(Ctx *c) {
    static int on = -1;
    static uint32_t prev, prev_st;
    if (on < 0) on = getenv("RN_FLOWLOG") != NULL || getenv("RN_JUMP") != NULL || getenv("RN_CAREER") != NULL;   // RN_JUMP, RN_CAREER read rn_fe
    if (!on) return;
    uint32_t lb = ld(c, 0x77a90c, 4), st = rn_flow;   // host/phase.c read it at this Present
    if (lb != prev && lb >= 0x697000 && lb < 0x6d4000) rn_log("flow %.64s (frame %u)", G(lb), dev.frames);
    // [[0x7361f0]]: the race's own state; 0x447600 and the draws read state 6 with it == 1 as "not racing yet"
    if (st != prev_st) { rn_log("flow state %u/%d (frame %u)", st >> 8, st & 0xff, dev.frames); gpu_keep_frame(); }
    // The post-race screens: [0x735ed0] queues PostRaceResults, StyleAnimator, RewardPopup, PostRaceMenu (0x49e100, a
    // variable count); +0xc is the node shown, +8 of a node its .fng name (0x49dfd0 steps it: esi = [cur+8] leaves,
    // edi = [next+8] comes in).
    uint32_t pr = ld(c, 0x735ed0, 4), node = pr ? ld(c, pr + 0xc, 4) : 0, nm = node ? ld(c, node + 8, 4) : 0;
    const char *scr = nm >= 0x697000 && nm < 0x6d4000 ? G(nm) : "";
    if (strcmp(scr, rn_screen)) { rn_log("flow screen %.32s (frame %u)", *scr ? scr : "-", dev.frames); gpu_keep_frame(); }
    static char fe[256], pfe[256];
    uint32_t np[16];
    int n = fe_packages(c, np);
    size_t fl = 0;
    fe[0] = 0;
    for (int i = 0; i < n; i++)
        if (fl < sizeof fe - 40) fl += (size_t)snprintf(fe + fl, sizeof fe - fl, "%s%.32s", fl ? "," : "", G(np[i]));
    if (strcmp(fe, pfe)) { rn_log("flow fe %s (frame %u)", fe, dev.frames); memcpy(pfe, fe, sizeof fe); }
    rn_fe = pfe;
    // The race's transmission: 0x78a387, copied from the Car Setup option 0x758954 by 0x4b47a0; the mode setup 0x4b55b0 writes 1
    // itself (I: the drag race, which is always shifted by hand, so 1 = manual). web/touch.js shows the shift buttons on it.
    static int pman = -1;
    int man = ld(c, 0x78a387, 1) == 1;
    if (man != pman) { rn_log("flow manual %d (frame %u)", man, dev.frames); pman = man; }
    // Read only. [0x777cc8] = the Quick Race mode the Accept switch takes (0x4b5c00: 0..6 -> 0x4b49e0..0x4b59b0); the
    // mode list 0x4b70c0 adds Circuit 0, Sprint 1, Drag 5, Drift 6, then 2, 3 (asm: ebx before each call 0x4b6fe0),
    // each only if its flag is set. The setup copies the track to [0x78a2f0] and a race kind to [0x78a31c].
    // [0x735dc8] = the career event under the cursor (0x4c4f00 writes it; 0x4e8180 reads the table 0x733ff8 with it).
    static uint32_t pm = ~0u, pt = ~0u, pe = ~0u;
    uint32_t m = ld(c, 0x777cc8, 4) | ld(c, 0x777b4c, 4) << 8, t = ld(c, 0x78a2f0, 4) | ld(c, 0x78a31c, 4) << 16;
    uint32_t e = ld(c, 0x735dc8, 4);
    if (m != pm || t != pt) rn_log("flow mode %u gametype %u track %u kind %u (frame %u)", m & 0xff, m >> 8, t & 0xffff, t >> 16, dev.frames);
    if (e != pe) rn_log("flow event %u (frame %u)", e, dev.frames);
    // Career progress: one status byte per event id at career 0x75eef8 + 0x34c (0x5a0ce0 writes 3 when the event's race
    // starts; Hopper evbrief.txt). The count after a profile load shows what the save brought back (game.save_reload).
    static int pcar = -1;
    static uint32_t phash, pcash = ~0u, prating_bits = ~0u;
    static int prating_valid = -1;
    int car = 0;
    uint32_t hash = 2166136261u;   // FNV-1a of the 256 status bytes: a reload must bring back the same ones
    for (uint32_t k = 0; k < 0x100; k++) { uint32_t b = ld(c, 0x75eef8 + 0x34c + k, 1); car += b != 0; hash = (hash ^ b) * 16777619u; }
    uint32_t cash = ld(c, 0x76026c, 4), rating_bits = 0;
    float rating = 0;
    int rating_valid = career_rating(c, &rating);
    memcpy(&rating_bits, &rating, sizeof rating_bits);
    if (car != pcar || hash != phash || cash != pcash || rating_valid != prating_valid || (rating_valid && rating_bits != prating_bits)) {
        if (rating_valid) rn_log("flow career %d status %08x cash %d rating %.2f (frame %u)", car, hash, (int32_t)cash, rating, dev.frames);
        else rn_log("flow career %d status %08x cash %d rating n/a (frame %u)", car, hash, (int32_t)cash, dev.frames);
    }
    phash = hash, pcash = cash, prating_valid = rating_valid;
    if (rating_valid) prating_bits = rating_bits;
    pm = m, pt = t, pe = e, pcar = car;
    input_jump(c);
    input_finish(c);
    input_unstick(c);
    input_open(c);
    input_next(c);
    input_call(c);
    input_career(c);
    prev = lb, prev_st = st, rn_screen = scr;
}
// RN_JCLOG (test-only): what the jump camera (docs/openworld/re_jumpcam.md) reads for player 1, during a race. ctrl
// [0x7361bc] (the player array), car [ctrl+4], driver [car+0x2c]; 0x42c4b0 takes the route from driver vtable slot 0x20
// (AI driver 0x44a310 = [driver+0x3e4], human driver 0x59bfb0 = [driver+0x44]): +4 node count, +8 node pointers, node+0x58
// its route distance. One line a second, and one per airborne sample (car+0x3cc wheels on the ground == 0) or camera mode
// change (ctrl+0x60). cam/span = the route clone and node indices 0x42c4b0 chose (ctrl+0x5c4, 0x5c8/0x5cc). During modes 6 and 7
// they read 0 and -1: 0x42dd11 calls 0x42c640, which frees them right after the mover copied what it needs, so that is normal and
// not a failed call. eye = ctrl+0x560..0x568, the fixed eye of the shot; fov = the word at [[ctrl+0x27c]+0x1c]+0xc4 (ctrl+0x27c
// is the active mover, 0x42c6bd; mover+0x1c its camera view; 0x485ff1 writes it, 16 bits); rp = car+0x810, which 0x42cb34
// copies into the mover: these tell whether the view degenerated. Without RN_JCLOG only the camera mode changes are logged
// (always on, so the OWNER's own play shows in build/web.log each jump camera they got).
static void jumpcam_log(Ctx *c) {
    static int on = -1; static uint32_t last, mode = ~0u, air, race;
    if (on < 0) on = getenv("RN_JCLOG") != NULL ? 2 : 1;
    if (!rn_racing() || !ld(c, 0x7361bc, 4)) return;
    if (rn_new_race(&race)) last = 0, mode = ~0u, air = 0;   // the first camera mode of each race is logged
    uint32_t ctrl = ld(c, 0x7361bc, 4), car = ctrl ? ld(c, ctrl + 4, 4) : 0, drv = car ? ld(c, car + 0x2c, 4) : 0;
    if (!drv) return;
    uint32_t slot = ld(c, ld(c, drv, 4) + 0x20, 4), route = ld(c, drv + (slot == 0x59bfb0 ? 0x44 : 0x3e4), 4), n = route ? ld(c, route + 4, 4) : 0;
    uint32_t m = ld(c, ctrl + 0x60, 4), wheels = ld(c, car + 0x3cc, 4), now = rn_telem.presents;
    uint32_t mover = ld(c, ctrl + 0x27c, 4), view = mover ? ld(c, mover + 0x1c, 4) : 0;
    int airborne = on == 2 && wheels == 0 && now >= air + 8;
    if ((on < 2 || now < last + 60) && m == mode && !airborne) return;
    if (airborne) air = now;
    last = now, mode = m;
    rn_log("JC f%u mode %u wheels %u speed %.1f pos %.0f,%.0f,%.0f yaw %d drv %08x vt %08x slot20 %08x route %08x nodes %u last %.0f m "
           "cam %08x span %d..%d 7361e8 %u 78a3fa %u eye %.0f,%.0f,%.0f fov %d rp %.2f", now, m, wheels, ldf(c, car + 0x3d4), ldf(c, car + 0x60), ldf(c, car + 0x64), ldf(c, car + 0x68), (int16_t)ld(c, car + 0x3b4, 2), drv,
           ld(c, drv, 4), slot, route, n, n && n < 4096 ? ldf(c, ld(c, route + 8 + (n - 1) * 4, 4) + 0x58) : 0.0f,
           ld(c, ctrl + 0x5c4, 4), (int)ld(c, ctrl + 0x5c8, 4), (int)ld(c, ctrl + 0x5cc, 4), ld(c, 0x7361e8, 4), ld(c, 0x78a3fa, 1),
           ldf(c, ctrl + 0x560), ldf(c, ctrl + 0x564), ldf(c, ctrl + 0x568), view ? (int)ld(c, view + 0xc4, 2) : -1, ldf(c, car + 0x810));
}
// Probe for walls crossed at speed (exit: delete when that bug is decided). Silent caps can drop a wall: the car's polygon cache 0x4407b0 holds
// 0xa0 (car+0x7e0 total, +0x7e4 ground, +0x7e8 walls, +0x7ec rest; 0x441660 drops by cell order, not distance) and the shared pools
// [0x72cbf4] polygon bodies (0xa0) and [0x72cc00] witnesses (0x100) (+0x18 used, +0x1c peak, +0x2c size). One line when one of them
// is full, at most every 30 frames, at 40 m/s or more; a crossing with no WALLCAP line near it clears the caps.
static void wallcap_log(Ctx *c) {
    static uint32_t last;
    uint32_t ctrl = rn_racing() ? ld(c, 0x7361bc, 4) : 0, car = ctrl ? ld(c, ctrl + 4, 4) : 0, now = rn_telem.presents;
    uint32_t pb = ld(c, 0x72cbf4, 4), pw = ld(c, 0x72cc00, 4);
    if (!car || !pb || !pw || now < last + 30 || ldf(c, car + 0x3d4) < 40.0f) return;
    uint32_t n = ld(c, car + 0x7e0, 4), bu = ld(c, pb + 0x18, 4), wu = ld(c, pw + 0x18, 4);
    if (n < 0xa0 && bu < ld(c, pb + 0x2c, 4) && wu < ld(c, pw + 0x2c, 4)) return;
    last = now;
    rn_log("WALLCAP f%u speed %.1f pos %.0f,%.0f,%.0f vz %.1f cache %u ground %u walls %u rest %u bodies %u peak %u witness %u peak %u", now, ldf(c, car + 0x3d4),
           ldf(c, car + 0x60), ldf(c, car + 0x64), ldf(c, car + 0x68), ldf(c, car + 0x78), n, ld(c, car + 0x7e4, 4), ld(c, car + 0x7e8, 4), ld(c, car + 0x7ec, 4),
           bu, ld(c, pb + 0x1c, 4), wu, ld(c, pw + 0x1c, 4));
}
static void roadrefl_frame(void);
static uint32_t IDirect3DDevice9_Present(Ctx *c) {
    DEV();
    rn_phase_tick(c);    // host/phase.c: rn_flow and the race edges, before anything reads them
    gf_track_poll();     // host/files.c: the Quick Race track highlighted in the menu starts its prefetch
    jumpcam_log(c);
    wallcap_log(c);
    tune_apply(c);
    fov_frame(c);
    hfov_frame(c);
    chase_frame(c);
    rng_log(c, dev.frames);
    flow_log(c);
    free_tick(c);
    crashwatch_present(c);
    traffic_tick(c);
    ai_tel(c);           // host/aitel.c: AI telemetry lines for the F10 (RN_AILOG)
    horn_tick(c);        // host/horn.c: recycle stamps for the horn hook (RN_HORNLOG / RN_HORNFIX)
    reset_tel(c);        // host/aitel.c: the game's reset 0x427c50 + 120 frames after (RN_RESETLOG)
    feel_tel(c);         // host/feellog.c: speed, chase row, FOV and 0-60 / 0-100 (RN_FEELLOG)
    if (rn_steerlog) steer_frame(c);
    if (ARG(1) || ARG(2) || ARG(3) || ARG(4)) {
        rn_halt(c, "d3d9: Present with rects/window (%08x %08x %08x %08x)", ARG(1), ARG(2), ARG(3), ARG(4));
        return D3DERR_INVALIDCALL;
    }
    if (dev.in_scene) TR("Present inside BeginScene/EndScene");
    Obj *b = obj_k(dev.backbuf);
    uint32_t w[4] = {b->gpu, b->w, b->h, (uint32_t)(uintptr_t)pace_box};   // word 3: ?pace=vsync (pace_plan)
    gpu_cmd(GPU_PRESENT, 4, w);
    if (cen_on < 0) { const char *e = getenv("RN_DRAWS"); cen_on = e != NULL; cen_frame = e ? (uint32_t)atoi(e) : 0; }
    if (cen_on > 0 && dev.frames >= cen_frame && cen_total >= 300) { census_dump(); cen_on = 0; }
    ncen = 0; cen_total = 0;
    roadrefl_frame();
    dev.frames++;
    rn_telem.presents++;
    if (dev.frames == 1) rn_log("d3d9 first Present: %ux%u", b->w, b->h);
    spike_log(c);
    pace_plan(c);
    hand_off();             // may wait for the display
    return D3D_OK;
}

// ---- state ----------------------------------------------------------------------------------
static uint32_t IDirect3DDevice9_SetRenderState(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetRenderState, 3, -1, 0);
    uint32_t s = ARG(1), v = ARG(2);
    if (s >= 256) return D3DERR_INVALIDCALL;
    TR("SetRenderState(%u, %08x)", s, v);
    if (s == 193 && v == 0x008296b4 && tune[10]) v = tune[10];   // light-trail decay (0x409bca), word 10 of tune[]
    dev.rs[s] = v;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetRenderState(Ctx *c) {
    DEV();
    if (ARG(1) >= 256 || !ARG(2)) return D3DERR_INVALIDCALL;
    st(c, ARG(2), dev.rs[ARG(1)], 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetTextureStageState(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetTextureStageState, 4, -1, 0);
    uint32_t s = ARG(1), t = ARG(2), v = ARG(3);
    if (s >= 8 || t >= 33) return D3DERR_INVALIDCALL;
    TR("SetTextureStageState(%u, %u, %08x)", s, t, v);
    dev.tss[s][t] = v;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetTextureStageState(Ctx *c) {
    DEV();
    if (ARG(1) >= 8 || ARG(2) >= 33 || !ARG(3)) return D3DERR_INVALIDCALL;
    st(c, ARG(3), dev.tss[ARG(1)][ARG(2)], 4);
    return D3D_OK;
}
// Samplers 0-15, D3DDMAPSAMPLER (256) and D3DVERTEXTEXTURESAMPLER0-3 (257-260) are not on this part.
static uint32_t IDirect3DDevice9_SetSamplerState(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetSamplerState, 4, -1, 0);
    uint32_t s = ARG(1), t = ARG(2), v = ARG(3);
    if (s >= 16 || t >= 14) return D3DERR_INVALIDCALL;
    TR("SetSamplerState(%u, %u, %08x)", s, t, v);
    dev.ss[s][t] = v;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetSamplerState(Ctx *c) {
    DEV();
    if (ARG(1) >= 16 || ARG(2) >= 14 || !ARG(3)) return D3DERR_INVALIDCALL;
    st(c, ARG(3), dev.ss[ARG(1)][ARG(2)], 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetTransform(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetTransform, 3, 2, 64);
    uint32_t s = ARG(1), m = ARG(2);
    if (s >= 512 || !m) return D3DERR_INVALIDCALL;
    for (int k = 0; k < 16; k++) dev.xf[s][k] = ldf(c, m + 4 * k);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetTransform(Ctx *c) {
    DEV();
    uint32_t s = ARG(1), m = ARG(2);
    if (s >= 512 || !m) return D3DERR_INVALIDCALL;
    for (int k = 0; k < 16; k++) stf(c, m + 4 * k, dev.xf[s][k]);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetViewport(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetViewport, 2, 1, 24);
    uint32_t p = ARG(1);
    Obj *rt = obj_k(dev.rt[0]);
    Viewport v = {ld(c, p, 4), ld(c, p + 4, 4), ld(c, p + 8, 4), ld(c, p + 12, 4), ldf(c, p + 16), ldf(c, p + 20)};
    TR("SetViewport(%u, %u, %ux%u, %g..%g)", v.x, v.y, v.w, v.h, (double)v.zmin, (double)v.zmax);
    {   // RN_VP=1: each new viewport once (bounded), to see how the game lays out 3D and 2D
        static int on = -1, seen, n;
        static uint32_t keys[64][4];
        if (on < 0) on = getenv("RN_VP") != NULL;
        uint32_t k[4] = {v.x, v.y, v.w, v.h};
        if (on && n < 64) {
            for (seen = 0; seen < n && memcmp(keys[seen], k, sizeof k); seen++) {}
            if (seen == n) { memcpy(keys[n++], k, sizeof k); rn_log("d3d9 viewport %u,%u %ux%u (rt %ux%u)", v.x, v.y, v.w, v.h, rt->w, rt->h); }
        }
    }
    if (!v.w || !v.h || v.x + v.w > rt->w || v.y + v.h > rt->h) return D3DERR_INVALIDCALL;
    dev.vp = v;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetViewport(Ctx *c) {
    DEV();
    uint32_t p = ARG(1);
    st(c, p, dev.vp.x, 4); st(c, p + 4, dev.vp.y, 4); st(c, p + 8, dev.vp.w, 4); st(c, p + 12, dev.vp.h, 4);
    stf(c, p + 16, dev.vp.zmin); stf(c, p + 20, dev.vp.zmax);
    return D3D_OK;
}


// ---- resources ------------------------------------------------------------------------------
static int pow2(uint32_t v) { return v && !(v & (v - 1)); }
static uint32_t mip_count(uint32_t w, uint32_t h) {
    uint32_t n = 1;
    while (w > 1 || h > 1) { w = w > 1 ? w / 2 : 1; h = h > 1 ? h / 2 : 1; n++; }
    return n;
}
static int bad_pool(uint32_t usage, uint32_t pool) {
    if (pool > POOL_SCRATCH) return 1;
    if ((usage & (U_RENDERTARGET | U_DEPTHSTENCIL)) && pool != POOL_DEFAULT) return 1;
    if ((usage & U_DYNAMIC) && pool == POOL_MANAGED) return 1;
    return 0;
}
static uint32_t lock_mem(Obj *o) {
    if (!o->mem) o->mem = guest_alloc(o->size ? o->size : 16);
    return o->mem;
}

static uint32_t IDirect3DDevice9_CreateTexture(Ctx *c) {
    DEV();
    uint32_t w = ARG(1), h = ARG(2), levels = ARG(3), usage = ARG(4), f = ARG(5), pool = ARG(6), out = ARG(7);
    TR("CreateTexture(%ux%u, %u levels, usage %x, fmt %u, pool %u)", w, h, levels, usage, f, pool);
    if (getenv("RN_RTLOG")) rn_log("RTLOG CreateTexture %ux%u levels %u usage %x fmt %u pool %u caller %08x frame %u", w, h, levels, usage, f, pool, ld(c, c->r[ESP], 4), dev.frames);
    if (!w || !h || !out || ARG(8) || bad_pool(usage, pool)) return D3DERR_INVALIDCALL;
    if (w > MAXTEX || h > MAXTEX || (pool != POOL_SCRATCH && check_format(F_X8R8G8B8, usage & ~U_QUERY_MASK, 3, f) >= 0x80000000u))
        return D3DERR_INVALIDCALL;
    uint32_t full = mip_count(w, h);
    if (usage & U_AUTOGENMIPMAP) { rn_halt(c, "d3d9: CreateTexture with AUTOGENMIPMAP"); return D3DERR_INVALIDCALL; }
    if (!levels) levels = full;
    if (levels > full) return D3DERR_INVALIDCALL;
    if ((!pow2(w) || !pow2(h)) && levels != 1 && pool != POOL_SCRATCH) return D3DERR_INVALIDCALL;   // NONPOW2CONDITIONAL
    if (!reserve(1 + (int)levels)) {
        if (out) st(c, out, 0, 4);
        return D3DERR_OUTOFVIDEOMEMORY;
    }
    uint32_t g = new_obj(c, I_TEXTURE);
    if (!g) { if (out) st(c, out, 0, 4); return D3DERR_OUTOFVIDEOMEMORY; }
    Obj *t = &objs[top];
    t->w = w; t->h = h; t->fmt = f; t->usage = usage; t->pool = pool; t->type = 3; t->levels = levels;
    uint32_t tk = idx(t) + 1;
    t->level0 = (uint32_t)top + 1;
    for (uint32_t l = 0; l < levels; l++) {
        uint32_t lw = w >> l ? w >> l : 1, lh = h >> l ? h >> l : 1;
        new_surface(c, lw, lh, f, usage, pool, !(usage & (U_RENDERTARGET | U_DEPTHSTENCIL)));
        objs[top].container = tk;
        if (pool == POOL_DEFAULT || pool == POOL_MANAGED) vram_used += objs[top].size;
    }
    if (!(usage & U_RENDERTARGET)) { uint32_t w4[4] = {tk, w, h, levels}; gpu_cmd(GPU_TEXTURE, 4, w4); }
    st(c, out, g, 4);
    return D3D_OK;
}
static Obj *level_of(Ctx *c, Obj *t, uint32_t l) {
    if (l >= t->levels) return NULL;
    (void)c;
    return &objs[t->level0 + l];
}
static uint32_t IDirect3DTexture9_GetLevelCount(Ctx *c) { SELF(I_TEXTURE); return o->levels; }
static void surface_desc(Ctx *c, Obj *o, uint32_t p) {
    uint32_t d[8] = {o->fmt, 1, o->usage, o->pool, 0, 0, o->w, o->h};
    if (dev.backbuf && o == obj_k(dev.backbuf)) { d[4] = dev.pp[4]; d[5] = dev.pp[5]; }
    for (int k = 0; k < 8; k++) st(c, p + 4 * k, d[k], 4);
}
static uint32_t IDirect3DTexture9_GetLevelDesc(Ctx *c) {
    SELF(I_TEXTURE);
    Obj *l = level_of(c, o, ARG(1));
    if (!l || !ARG(2)) return D3DERR_INVALIDCALL;
    surface_desc(c, l, ARG(2));
    return D3D_OK;
}
static uint32_t IDirect3DTexture9_GetSurfaceLevel(Ctx *c) {
    SELF(I_TEXTURE);
    Obj *l = level_of(c, o, ARG(1));
    if (!l || !ARG(2)) return D3DERR_INVALIDCALL;
    o->refs++;
    st(c, ARG(2), l->guest, 4);
    return D3D_OK;
}
// D3DLOCKED_RECT {Pitch, pBits}. Default-pool resources lock only when dynamic (or a lockable target).
static uint32_t lock_rect(Ctx *c, Obj *s, uint32_t out, uint32_t rect, uint32_t flags) {
    if (!out) return D3DERR_INVALIDCALL;
    if (s->locked) return D3DERR_INVALIDCALL;
    if (s->pool == POOL_DEFAULT && !(s->usage & U_DYNAMIC) && !s->lockable) return D3DERR_INVALIDCALL;
    if (s->gpu) { rn_halt(c, "d3d9: LockRect of a render target / depth buffer (needs readback)"); return D3DERR_INVALIDCALL; }
    uint32_t off = 0;
    if (rect) {
        uint32_t x = ld(c, rect, 4), y = ld(c, rect + 4, 4);
        off = is_dxt(s->fmt) ? (y / 4) * s->pitch + (x / 4) * (s->fmt == F_DXT1 ? 8 : 16) : y * s->pitch + x * (fmt_bits(s->fmt) / 8);
    }
    s->locked = 1;
    st(c, out, s->pitch, 4);
    st(c, out + 4, lock_mem(s) + off, 4);
    (void)flags;
    return D3D_OK;
}
// ---- texel decoding: every format the game creates becomes RGBA8 (bytes R G B A) for both backends.
static uint32_t rgba(uint32_t r, uint32_t g, uint32_t b, uint32_t a) { return r | g << 8 | b << 16 | a << 24; }
static uint32_t x5(uint32_t v) { return (v << 3) | (v >> 2); }
static uint32_t x6(uint32_t v) { return (v << 2) | (v >> 4); }
static uint32_t x4(uint32_t v) { return v << 4 | v; }
// DXT color block: two R5G6B5 ends and 2-bit indices. Four colors, or three and transparent black
// when c0 <= c1 (DXT1 only; DXT2-5 always use four).
static void dxt_color(const uint8_t *b, int dxt1, uint32_t out[16]) {
    uint32_t c0 = b[0] | b[1] << 8, c1 = b[2] | b[3] << 8, bits = b[4] | b[5] << 8 | b[6] << 16 | (uint32_t)b[7] << 24;
    uint32_t r[4], g[4], bl[4], a[4] = {255, 255, 255, 255};
    r[0] = x5(c0 >> 11); g[0] = x6((c0 >> 5) & 63); bl[0] = x5(c0 & 31);
    r[1] = x5(c1 >> 11); g[1] = x6((c1 >> 5) & 63); bl[1] = x5(c1 & 31);
    if (c0 > c1 || !dxt1) {
        r[2] = (2 * r[0] + r[1] + 1) / 3; g[2] = (2 * g[0] + g[1] + 1) / 3; bl[2] = (2 * bl[0] + bl[1] + 1) / 3;
        r[3] = (r[0] + 2 * r[1] + 1) / 3; g[3] = (g[0] + 2 * g[1] + 1) / 3; bl[3] = (bl[0] + 2 * bl[1] + 1) / 3;
    } else {
        r[2] = (r[0] + r[1]) / 2; g[2] = (g[0] + g[1]) / 2; bl[2] = (bl[0] + bl[1]) / 2;
        r[3] = g[3] = bl[3] = a[3] = 0;
    }
    for (int k = 0; k < 16; k++) { uint32_t i = bits >> (2 * k) & 3; out[k] = rgba(r[i], g[i], bl[i], a[i]); }
}
static void dxt_alpha5(const uint8_t *b, uint32_t out[16]) {
    uint32_t a[8] = {b[0], b[1]};
    if (a[0] > a[1]) for (int k = 1; k < 7; k++) a[k + 1] = ((7 - k) * a[0] + k * a[1] + 3) / 7;
    else { for (int k = 1; k < 5; k++) a[k + 1] = ((5 - k) * a[0] + k * a[1] + 2) / 5; a[6] = 0; a[7] = 255; }
    uint64_t bits = 0;
    for (int k = 0; k < 6; k++) bits |= (uint64_t)b[2 + k] << (8 * k);
    for (int k = 0; k < 16; k++) out[k] = (out[k] & 0x00ffffffu) | a[bits >> (3 * k) & 7] << 24;
}
static int decode_texels(uint32_t f, const uint8_t *src, uint32_t pitch, uint32_t w, uint32_t h, uint32_t *dst) {
    if (is_dxt(f)) {
        int bs = f == F_DXT1 ? 8 : 16;
        for (uint32_t by = 0; by < (h + 3) / 4; by++)
            for (uint32_t bx = 0; bx < (w + 3) / 4; bx++) {
                const uint8_t *b = src + by * pitch + bx * (uint32_t)bs;
                uint32_t px[16];
                dxt_color(b + bs - 8, f == F_DXT1, px);
                if (f == F_DXT2 || f == F_DXT3)
                    for (int k = 0; k < 16; k++) px[k] = (px[k] & 0x00ffffffu) | x4(b[k / 2] >> (4 * (k & 1)) & 15) << 24;
                if (f == F_DXT4 || f == F_DXT5) dxt_alpha5(b, px);
                for (int k = 0; k < 16; k++) {
                    uint32_t x = bx * 4 + (k & 3), y = by * 4 + (k >> 2);
                    if (x < w && y < h) dst[y * w + x] = px[k];
                }
            }
        return 1;
    }
    for (uint32_t y = 0; y < h; y++) {
        const uint8_t *r = src + y * pitch;
        for (uint32_t x = 0; x < w; x++) {
            uint32_t v, o;
            switch (f) {
            case F_A8R8G8B8: case F_X8R8G8B8:
                v = r[4 * x] | r[4 * x + 1] << 8 | r[4 * x + 2] << 16 | (uint32_t)r[4 * x + 3] << 24;
                o = rgba(v >> 16 & 255, v >> 8 & 255, v & 255, f == F_X8R8G8B8 ? 255 : v >> 24);
                break;
            case F_R5G6B5: v = r[2 * x] | r[2 * x + 1] << 8; o = rgba(x5(v >> 11), x6(v >> 5 & 63), x5(v & 31), 255); break;
            case F_X1R5G5B5: case F_A1R5G5B5:
                v = r[2 * x] | r[2 * x + 1] << 8;
                o = rgba(x5(v >> 10 & 31), x5(v >> 5 & 31), x5(v & 31), f == F_X1R5G5B5 || (v >> 15) ? 255 : 0);
                break;
            case F_A4R4G4B4: v = r[2 * x] | r[2 * x + 1] << 8; o = rgba(x4(v >> 8 & 15), x4(v >> 4 & 15), x4(v & 15), x4(v >> 12)); break;
            case F_A8: o = rgba(0, 0, 0, r[x]); break;
            case F_L8: o = rgba(r[x], r[x], r[x], 255); break;
            case F_A8L8: o = rgba(r[2 * x], r[2 * x], r[2 * x], r[2 * x + 1]); break;
            default: return 0;
            }
            dst[y * w + x] = o;
        }
    }
    return 1;
}
// A texture level's contents count from its unlock: send the whole level to the renderer.
static void upload_level(Ctx *c, Obj *s) {
    Obj *t = obj_k(s->container);
    if (!t || t->iface != I_TEXTURE || (t->usage & U_RENDERTARGET)) return;
    uint32_t level = idx(s) - t->level0, n = s->w * s->h;
    uint32_t *w = malloc(4u * (4 + n));
    w[0] = s->container; w[1] = level; w[2] = s->w; w[3] = s->h;
    if (!decode_texels(s->fmt, (const uint8_t *)G(lock_mem(s)), s->pitch, s->w, s->h, w + 4)) {
        rn_halt(c, "d3d9: texture format %u has no decoder", s->fmt);
        free(w);
        return;
    }
    static uint32_t seen[8];
    for (int k = 0; k < 8; k++) {
        if (seen[k] == s->fmt) break;
        if (!seen[k]) { seen[k] = s->fmt; rn_log("d3d9 first texture of format %u (%ux%u)", s->fmt, s->w, s->h); break; }
    }
    gpu_cmd(GPU_TEXDATA, (int)(4 + n), w);
    free(w);
    flush_big();
    // 32-bit textures too (rims, decals); a dynamic one is relocked each frame, so it is never a pack texture.
    if (level == 0 && (is_dxt(s->fmt) || ((s->fmt == F_A8R8G8B8 || s->fmt == F_X8R8G8B8) && !(t->usage & U_DYNAMIC)))) {
        // FNV-1a 64 of the level-0 blocks: the key of tools/remaster/index.py.
        const uint8_t *p = (const uint8_t *)G(lock_mem(s));
        uint64_t h = 0xcbf29ce484222325ull;
        for (uint32_t k = 0, m = s->pitch * (is_dxt(s->fmt) ? (s->h + 3) / 4 : s->h); k < m; k++) h = (h ^ p[k]) * 0x100000001b3ull;
        static int log = -1;
        if (log < 0) log = getenv("RN_TEXHASH") != NULL;
        if (log) rn_log("d3d9 texhash %016llx %ux%u fmt %08x id %x", (unsigned long long)h, s->w, s->h, s->fmt, s->container);
        uint32_t k3[3] = {s->container, (uint32_t)h, (uint32_t)(h >> 32)};
        gpu_cmd(GPU_TEXKEY, 3, k3);
        if (s->container) tex_key[s->container - 1] = h;
        // RN_TEXDUMP=1: each level-0 content once to save/texdump/<key>.bin (w, h, fmt, pitch, then the locked bytes), for the
        // remaster pack: the exact texels the game uploads, whatever container they came from (tools/remaster/texdump.py).
        static int dump = -1;
        if (dump < 0) { dump = getenv("RN_TEXDUMP") != NULL; if (dump) gf_mkdir("C:/Documents and Settings/All Users/Application Data/NFS Underground/texdump"); }
        static uint64_t dumped[16384]; static uint32_t ndumped;
        if (dump && ndumped < 16384) {
            uint32_t k = 0;
            while (k < ndumped && dumped[k] != h) k++;
            if (k == ndumped) {
                dumped[ndumped++] = h;
                uint32_t m = s->pitch * (is_dxt(s->fmt) ? (s->h + 3) / 4 : s->h), hd[4] = {s->w, s->h, s->fmt, s->pitch};
                uint8_t *b = malloc(16 + m);
                memcpy(b, hd, 16); memcpy(b + 16, p, m);
                char name[64];
                snprintf(name, sizeof name, "texdump/%016llx.bin", (unsigned long long)h);
                layer_store(name, b, (int)(16 + m));
                free(b);
            }
        }
    }
}
// BRIDGE: HD car skins, 0x5a8a50, OWNER 2026-10-23 (remaster scope). The game composites DUMMY_SKINn on the CPU at 512 from
// 512 layers (base _HOOD/_SPOILER, up to 4 vinyls, decal; each + "<name>_MASK", 0x5a9ce0), so its masks step on the car.
// At that composite's own UnlockRect (return address 0x5a8e7d) the spec is var_1C - 8 = [esp+0x44] - 8 (0x5a8a74 keeps spec+8 there;
// the arg_0 slot is reused as a pointer by then, 0x5a8e2e). The
// renderer replays the same per-texel rules on the same layer textures at 4x (web/gpu.js GPU_SKIN); the game's 512 result
// stays the texture's own contents (?skinhd=0, and the oracle of ?skinhd=check). Spec (V, Hopper 0x5a8a50/0x5a8640):
// +0 skin, +4 fill ARGB with R/B swapped, +8 four marker colours (swapped in place), +0x18 layers of 0x34: +0 name hash
// (0 = off), +0xc layer bits, +0x14 mask bits, +0x20 recolour flag, +0x24 four colours (swapped in place); +0x1b8 count.
// Markers: counts at 0x733f50 (4), texel indexes at 0x733e28 (4 x 16).
static uint32_t tex_of_bits(uint32_t bits) {
    for (int k = 0; k < nobjs; k++)
        if (objs[k].iface == I_SURFACE && objs[k].mem == bits && objs[k].container) return objs[k].container;
    return 0;
}
int rn_pool_livery(uint32_t skin, int *car, int *n);   // host/rivals.c
static void skin_bridge(Ctx *c, Obj *s) {
    if (ld(c, c->r[ESP], 4) != 0x5a8e7d) return;
    uint32_t p = ld(c, c->r[ESP] + 0x44, 4) - 8, n = ld(c, p + 0x1b8, 4), fill = ld(c, p + 4, 4);
    if (getenv("RN_SKINLOG")) {
        rn_log("skin_bridge esp %08x spec %08x n %u fill %08x skin %08x", c->r[ESP], p, n, fill, ld(c, p, 4));
        for (uint32_t i = 0; i < 8; i++) rn_log("  layer %u: %08x bits %08x mask %08x rc %u", i, ld(c, p + 0x18 + 0x34 * i, 4),
            ld(c, p + 0x24 + 0x34 * i, 4), ld(c, p + 0x2c + 0x34 * i, 4), ld(c, p + 0x38 + 0x34 * i, 4));
    }
    uint32_t w[3 + 8 * 7 + 4 + 1 + 2 * 64], k = 0;
    w[k++] = s->container; w[k++] = (fill & 0xff00ff00u) | (fill >> 16 & 0xff) | (fill & 0xff) << 16; w[k++] = 0;
    for (uint32_t i = 0; i < n && i < 8; i++) {
        uint32_t b = p + 0x18 + 0x34 * i;
        if (!ld(c, b, 4)) continue;
        uint32_t lt = tex_of_bits(ld(c, b + 0xc, 4)), mt = tex_of_bits(ld(c, b + 0x14, 4));
        if (!lt || !mt) return;
        w[k++] = lt; w[k++] = mt; w[k++] = ld(c, b + 0x20, 4) != 0;
        for (int j = 0; j < 4; j++) w[k++] = ld(c, b + 0x24 + 4 * j, 4);
        w[2]++;
    }
    for (int j = 0; j < 4; j++) w[k++] = ld(c, p + 8 + 4 * j, 4);
    uint32_t nm = k++;
    w[nm] = 0;
    for (uint32_t j = 0; j < 4; j++)
        for (uint32_t i = 0, cnt = ld(c, 0x733f50 + 4 * j, 4); i < cnt && i < 16; i++) { w[k++] = ld(c, 0x733e28 + 4 * (16 * j + i), 4); w[k++] = j; w[nm]++; }
    gpu_cmd(GPU_SKIN, (int)k, w);
    int lcar, ln;   // spec +0 = the skin's texture record (0x5a8a50 reads its pixel code at +0x4a), its hash at +0x24 (docs/re/assets.md)
    if (rn_pool_livery(ld(c, ld(c, p, 4) + 0x24, 4), &lcar, &ln)) { uint32_t lw[3] = {s->container, (uint32_t)lcar, (uint32_t)ln}; gpu_cmd(GPU_LIVERY, 3, lw); }
}
static uint32_t unlock_rect(Ctx *c, Obj *s) {
    if (!s->locked) return D3DERR_INVALIDCALL;
    s->locked = 0;
    upload_level(c, s);
    skin_bridge(c, s);
    return D3D_OK;
}
static uint32_t IDirect3DTexture9_LockRect(Ctx *c) {
    SELF(I_TEXTURE);
    Obj *l = level_of(c, o, ARG(1));
    if (!l) return D3DERR_INVALIDCALL;
    return lock_rect(c, l, ARG(2), ARG(3), ARG(4));
}
static uint32_t IDirect3DTexture9_UnlockRect(Ctx *c) {
    SELF(I_TEXTURE);
    Obj *l = level_of(c, o, ARG(1));
    return l ? unlock_rect(c, l) : D3DERR_INVALIDCALL;
}
// Cube textures: one-level render targets only, what the game makes for the car reflection (0x40b340: 128,
// A8R8G8B8, its six faces drawn each frame with their own depth buffers). Faces are surfaces level0..level0+5
// in D3DCUBEMAP_FACES order; the renderer keeps them as the layers of one texture (GPU_CUBE).
static uint32_t IDirect3DDevice9_CreateCubeTexture(Ctx *c) {
    DEV();
    uint32_t e = ARG(1), levels = ARG(2), usage = ARG(3), f = ARG(4), pool = ARG(5), out = ARG(6);
    TR("CreateCubeTexture(%u, %u levels, usage %x, fmt %u, pool %u)", e, levels, usage, f, pool);
    if (!e || !out || ARG(7) || bad_pool(usage, pool) || e > MAXTEX) return D3DERR_INVALIDCALL;
    if (pool != POOL_SCRATCH && check_format(F_X8R8G8B8, usage & ~U_QUERY_MASK, 5, f) >= 0x80000000u) return D3DERR_INVALIDCALL;
    if (!(usage & U_RENDERTARGET) || levels != 1) {
        rn_halt(c, "d3d9: cube texture that is not a one-level render target (usage %x, %u levels)", usage, levels);
        return D3DERR_INVALIDCALL;
    }
    if (!reserve(7)) {
        if (out) st(c, out, 0, 4);
        return D3DERR_OUTOFVIDEOMEMORY;
    }
    uint32_t g = new_obj(c, I_CUBE);
    if (!g) { if (out) st(c, out, 0, 4); return D3DERR_OUTOFVIDEOMEMORY; }
    Obj *t = &objs[top];
    t->w = e; t->h = e; t->fmt = f; t->usage = usage; t->pool = pool; t->type = 5; t->levels = 1;
    uint32_t tk = idx(t) + 1;
    t->level0 = (uint32_t)top + 1;
    for (int k = 0; k < 6; k++) {
        new_surface(c, e, e, f, usage, pool, 0);
        objs[top].container = tk;
    }
    uint32_t w3[3] = {tk, e, objs[t->level0].gpu};
    gpu_cmd(GPU_CUBE, 3, w3);
    st(c, out, g, 4);
    return D3D_OK;
}
static Obj *face_of(Obj *t, uint32_t face, uint32_t l) { return face < 6 && l < t->levels ? &objs[t->level0 + face] : NULL; }
static uint32_t IDirect3DCubeTexture9_GetLevelCount(Ctx *c) { SELF(I_CUBE); return o->levels; }
static uint32_t IDirect3DCubeTexture9_GetLevelDesc(Ctx *c) {
    SELF(I_CUBE);
    Obj *l = face_of(o, 0, ARG(1));
    if (!l || !ARG(2)) return D3DERR_INVALIDCALL;
    surface_desc(c, l, ARG(2));
    return D3D_OK;
}
static uint32_t IDirect3DCubeTexture9_GetCubeMapSurface(Ctx *c) {
    SELF(I_CUBE);
    Obj *l = face_of(o, ARG(1), ARG(2));
    if (!l || !ARG(3)) return D3DERR_INVALIDCALL;
    o->refs++;
    st(c, ARG(3), l->guest, 4);
    return D3D_OK;
}
static uint32_t IDirect3DCubeTexture9_LockRect(Ctx *c) {
    SELF(I_CUBE);
    Obj *l = face_of(o, ARG(1), ARG(2));
    return l ? lock_rect(c, l, ARG(3), ARG(4), ARG(5)) : D3DERR_INVALIDCALL;
}
static uint32_t IDirect3DCubeTexture9_UnlockRect(Ctx *c) {
    SELF(I_CUBE);
    Obj *l = face_of(o, ARG(1), ARG(2));
    return l ? unlock_rect(c, l) : D3DERR_INVALIDCALL;
}
static uint32_t IDirect3DCubeTexture9_GetType(Ctx *c) { SELF(I_CUBE); return 5; }
static uint32_t IDirect3DCubeTexture9_PreLoad(Ctx *c) { SELF(I_CUBE); return 0; }
static uint32_t IDirect3DTexture9_GetType(Ctx *c) { SELF(I_TEXTURE); return 3; }
static uint32_t IDirect3DTexture9_PreLoad(Ctx *c) { SELF(I_TEXTURE); return 0; }
static uint32_t IDirect3DSurface9_LockRect(Ctx *c) { SELF(I_SURFACE); return lock_rect(c, o, ARG(1), ARG(2), ARG(3)); }
static uint32_t IDirect3DSurface9_UnlockRect(Ctx *c) { SELF(I_SURFACE); return unlock_rect(c, o); }

// Static vertex and index buffers live on the GPU (web): their bytes go once per Unlock (GPU_BUFDATA), and a draw names
// the buffer instead of copying its vertices and indices into every frame (OWNER 2026-10-23, 60 fps: the per-draw copies
// were ~40% of the game thread). Dynamic buffers are refilled inside a frame, so they keep the per-draw copy: a GPU-side
// write would land before earlier draws of the same frame ran. RN_INLINE=1 copies everything as before (A/B).
static int resident_on(void) {
#ifdef __EMSCRIPTEN__
    static int off = -1;
    if (off < 0) off = getenv("RN_INLINE") != NULL;
    return !off;
#else
    return 0;
#endif
}
static int resident(const Obj *o) { return o && resident_on() && !(o->usage & U_DYNAMIC); }
static void buffer_upload(Ctx *c, Obj *o) {
    uint32_t lo = o->dlo & ~3u, hi = (o->dhi + 3) & ~3u, n = hi - lo;
    o->dlo = o->dhi = 0;
    if (!n) return;
    uint32_t *w = calloc(3 + n / 4, 4);
    w[0] = idx(o) + 1; w[1] = lo; w[2] = n;
    memcpy(w + 3, G(lock_mem(o) + lo), hi <= o->size ? n : o->size - lo);
    gpu_cmd(GPU_BUFDATA, (int)(3 + n / 4), w);
    free(w);
    flush_big();
    (void)c;
}
static uint32_t new_buffer(Ctx *c, int iface, uint32_t len, uint32_t usage, uint32_t f, uint32_t pool, uint32_t out) {
    if (!len || !out || bad_pool(usage, pool) || (usage & (U_RENDERTARGET | U_DEPTHSTENCIL))) return D3DERR_INVALIDCALL;
    uint32_t g = new_obj(c, iface);
    if (!g) return D3DERR_OUTOFVIDEOMEMORY;
    Obj *o = &objs[top];
    o->size = len; o->usage = usage; o->pool = pool;
    if (iface == I_VB) { o->fvf = f; o->fmt = 100; o->type = 6; } else { o->fmt = f; o->type = 7; }
    if (pool == POOL_DEFAULT) vram_used += len;
    if (resident(o)) { uint32_t w2[2] = {idx(o) + 1, (len + 3) & ~3u}; gpu_cmd(GPU_BUFFER, 2, w2); }
    st(c, out, g, 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_CreateVertexBuffer(Ctx *c) {
    DEV();
    TR("CreateVertexBuffer(%u bytes, usage %x, fvf %x, pool %u)", ARG(1), ARG(2), ARG(3), ARG(4));
    if (ARG(6)) return D3DERR_INVALIDCALL;
    return new_buffer(c, I_VB, ARG(1), ARG(2), ARG(3), ARG(4), ARG(5));
}
static uint32_t IDirect3DDevice9_CreateIndexBuffer(Ctx *c) {
    DEV();
    TR("CreateIndexBuffer(%u bytes, usage %x, fmt %u, pool %u)", ARG(1), ARG(2), ARG(3), ARG(4));
    if (ARG(6) || (ARG(3) != F_INDEX16 && ARG(3) != F_INDEX32)) return D3DERR_INVALIDCALL;
    return new_buffer(c, I_IB, ARG(1), ARG(2), ARG(3), ARG(4), ARG(5));
}
// Lock(OffsetToLock, SizeToLock, ppbData, Flags): size 0 = to the end. Nested locks are allowed.
static uint32_t buffer_lock(Ctx *c, Obj *o) {
    uint32_t off = ARG(1), size = ARG(2), out = ARG(3);
    if (!out || off > o->size || (size && off + size > o->size)) return D3DERR_INVALIDCALL;
    o->locked++;
    st(c, out, lock_mem(o) + off, 4);
    static uint32_t ver_clock;   // one clock for every buffer: a reused slot at a reused address never repeats a smooth key
    if (!(ARG(4) & 0x10)) o->ver = ++ver_clock;
    if (resident(o) && !(ARG(4) & 0x10)) {     // D3DLOCK_READONLY writes nothing
        uint32_t hi = size ? off + size : o->size;
        if (o->dhi <= o->dlo) { o->dlo = off; o->dhi = hi; }
        else { if (off < o->dlo) o->dlo = off; if (hi > o->dhi) o->dhi = hi; }
    }
    return D3D_OK;
}
static uint32_t buffer_unlock(Ctx *c, Obj *o) {
    if (!o->locked) return D3DERR_INVALIDCALL;
    o->locked--;
    if (!o->locked && resident(o)) buffer_upload(c, o);
    return D3D_OK;
}
static uint32_t IDirect3DVertexBuffer9_Lock(Ctx *c) { SELF(I_VB); return buffer_lock(c, o); }
static uint32_t IDirect3DVertexBuffer9_Unlock(Ctx *c) { SELF(I_VB); return buffer_unlock(c, o); }
static uint32_t IDirect3DIndexBuffer9_Lock(Ctx *c) { SELF(I_IB); return buffer_lock(c, o); }
static uint32_t IDirect3DIndexBuffer9_Unlock(Ctx *c) { SELF(I_IB); return buffer_unlock(c, o); }
static uint32_t IDirect3DVertexBuffer9_GetDesc(Ctx *c) {
    SELF(I_VB);
    uint32_t d[6] = {100, 6, o->usage, o->pool, o->size, o->fvf}, p = ARG(1);
    for (int k = 0; k < 6; k++) st(c, p + 4 * k, d[k], 4);
    return D3D_OK;
}
static uint32_t IDirect3DIndexBuffer9_GetDesc(Ctx *c) {
    SELF(I_IB);
    uint32_t d[5] = {o->fmt, 7, o->usage, o->pool, o->size}, p = ARG(1);
    for (int k = 0; k < 5; k++) st(c, p + 4 * k, d[k], 4);
    return D3D_OK;
}

static uint32_t IDirect3DDevice9_CreateRenderTarget(Ctx *c) {
    DEV();
    uint32_t w = ARG(1), h = ARG(2), f = ARG(3), ms = ARG(4), lockable = ARG(6), out = ARG(7);
    TR("CreateRenderTarget(%ux%u, fmt %u, ms %u, lockable %u)", w, h, f, ms, lockable);
    if (!w || !h || !out || ARG(8) || !rt_fmt(f)) return D3DERR_INVALIDCALL;
    if (ms) { rn_halt(c, "d3d9: multisampled render target"); return D3DERR_INVALIDCALL; }
    st(c, out, new_surface(c, w, h, f, U_RENDERTARGET, POOL_DEFAULT, lockable != 0), 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_CreateDepthStencilSurface(Ctx *c) {
    DEV();
    uint32_t w = ARG(1), h = ARG(2), f = ARG(3), ms = ARG(4), out = ARG(7);
    TR("CreateDepthStencilSurface(%ux%u, fmt %u, ms %u, discard %u)", w, h, f, ms, ARG(6));
    if (!w || !h || !out || ARG(8) || !ds_fmt(f)) return D3DERR_INVALIDCALL;
    if (ms) { rn_halt(c, "d3d9: multisampled depth buffer"); return D3DERR_INVALIDCALL; }
    st(c, out, new_surface(c, w, h, f, U_DEPTHSTENCIL, POOL_DEFAULT, f == F_D16_LOCKABLE), 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_CreateOffscreenPlainSurface(Ctx *c) {
    DEV();
    uint32_t w = ARG(1), h = ARG(2), f = ARG(3), pool = ARG(4), out = ARG(5);
    TR("CreateOffscreenPlainSurface(%ux%u, fmt %u, pool %u)", w, h, f, pool);
    if (!w || !h || !out || ARG(6) || pool == POOL_MANAGED || pool > POOL_SCRATCH) return D3DERR_INVALIDCALL;
    if (pool != POOL_SCRATCH && !tex_fmt(f)) return D3DERR_INVALIDCALL;
    st(c, out, new_surface(c, w, h, f, 0, pool, 1), 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetRenderTarget(Ctx *c) {
    DEV();
    uint32_t i = ARG(1), p = ARG(2);
    if (i >= 4 || (i == 0 && !p)) return D3DERR_INVALIDCALL;
    Obj *s = p ? obj_of(c, p, I_SURFACE) : NULL;
    if (p && (!s || !(s->usage & U_RENDERTARGET))) return D3DERR_INVALIDCALL;
    TR("SetRenderTarget(%u, %08x)", i, p);
    dev.rt[i] = s ? idx(s) + 1 : 0;
    if (i == 0) reset_viewport(s);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetDepthStencilSurface(Ctx *c) {
    DEV();
    uint32_t p = ARG(1);
    Obj *s = p ? obj_of(c, p, I_SURFACE) : NULL;
    if (p && (!s || !(s->usage & U_DEPTHSTENCIL))) return D3DERR_INVALIDCALL;
    TR("SetDepthStencilSurface(%08x)", p);
    dev.ds = s ? idx(s) + 1 : 0;
    return D3D_OK;
}

// ---- declarations and shaders -----------------------------------------------------------------
// D3DVERTEXELEMENT9 {WORD Stream, Offset; BYTE Type, Method, Usage, UsageIndex}, ended by stream 0xff.
// A declaration object from n elements (8 bytes each, then the D3DDECL_END element); returns its index + 1.
static uint32_t make_decl(Ctx *c, const void *el, uint32_t n) {
    if (!new_obj(c, I_DECL)) return 0;
    Obj *o = &objs[top];
    o->nblob = 2 * (n + 1);
    o->blob = malloc(4u * o->nblob);
    memcpy(o->blob, el, 8u * (n + 1));
    uint32_t *w = calloc(2 + 2 * n, 4);
    w[0] = idx(o) + 1; w[1] = n;
    memcpy(w + 2, o->blob, 8u * n);
    gpu_cmd(GPU_DECL, (int)(2 + 2 * n), w);
    free(w);
    if (rn_trace())
        for (uint32_t k = 0; k < n; k++) {
            const uint8_t *e = (const uint8_t *)el + 8 * k;
            rn_log("d3d9   element stream %u off %u type %u method %u usage %u/%u", e[0] | e[1] << 8, e[2] | e[3] << 8,
                   e[4], e[5], e[6], e[7]);
        }
    return idx(o) + 1;
}
static uint32_t IDirect3DDevice9_CreateVertexDeclaration(Ctx *c) {
    DEV();
    uint32_t p = ARG(1), out = ARG(2), n = 0;
    if (!p || !out) return D3DERR_INVALIDCALL;
    while (ld(c, p + 8 * n, 2) != 0xff) if (++n > 64) return D3DERR_INVALIDCALL;
    uint32_t k1 = make_decl(c, G(p), n);
    if (!k1) return D3DERR_INVALIDCALL;
    st(c, out, objs[k1 - 1].guest, 4);
    return D3D_OK;
}
// SetFVF with a vertex shader: the runtime draws through the declaration the FVF describes (d3d9 docs,
// "Mapping FVF Codes to a Directx 9 Declaration"). One declaration per FVF, made on first use.
static uint32_t fvf_decl(Ctx *c, uint32_t fvf) {
    static uint32_t key[64], val[64], n;
    for (uint32_t k = 0; k < n; k++) if (key[k] == fvf) return val[k];
    uint8_t el[8 * 16];
    uint32_t ne = 0, off = 0;
    #define EL(type, usage, ui, size) do { uint8_t *e = el + 8 * ne++; e[0] = 0; e[1] = 0; e[2] = (uint8_t)off; \
        e[3] = (uint8_t)(off >> 8); e[4] = (type); e[5] = 0; e[6] = (usage); e[7] = (ui); off += (size); } while (0)
    uint32_t pos = fvf & 0x400e;
    if (pos == 0x2) EL(2, 0, 0, 12);                    // XYZ: FLOAT3 POSITION
    else if (pos == 0x4) EL(3, 9, 0, 16);               // XYZRHW: FLOAT4 POSITIONT
    else if (pos == 0x4002) EL(3, 0, 0, 16);            // XYZW: FLOAT4 POSITION
    else if (pos) { rn_halt(c, "d3d9: FVF %x with blend weights", fvf); return 0; }
    if (fvf & 0x10) EL(2, 3, 0, 12);                    // NORMAL
    if (fvf & 0x20) EL(0, 4, 0, 4);                     // PSIZE
    if (fvf & 0x40) EL(4, 10, 0, 4);                    // DIFFUSE: D3DCOLOR COLOR0
    if (fvf & 0x80) EL(4, 10, 1, 4);                    // SPECULAR: D3DCOLOR COLOR1
    static const uint8_t tc_type[4] = {1, 2, 3, 0}, tc_size[4] = {8, 12, 16, 4};
    for (uint32_t t = 0; t < ((fvf >> 8) & 0xf); t++) {
        uint32_t f = (fvf >> (16 + 2 * t)) & 3;
        EL(tc_type[f], 5, t, tc_size[f]);
    }
    #undef EL
    uint8_t *e = el + 8 * ne;                           // D3DDECL_END
    e[0] = 0xff; e[1] = 0; e[2] = e[3] = 0; e[4] = 17; e[5] = e[6] = e[7] = 0;
    uint32_t k1 = make_decl(c, el, ne);
    if (k1 && n < 64) { key[n] = fvf; val[n++] = k1; }
    TR("FVF %x -> declaration %u (%u elements, %u bytes)", fvf, k1, ne, off);
    return k1;
}
static uint32_t IDirect3DVertexDeclaration9_GetDeclaration(Ctx *c) {
    SELF(I_DECL);
    if (ARG(2)) st(c, ARG(2), o->nblob / 2, 4);
    if (ARG(1)) memcpy(G(ARG(1)), o->blob, 4u * o->nblob);
    return D3D_OK;
}
static void disasm_line(const char *l) { rn_log("d3d9   %s", l); }
// Shader tokens: version, instructions, D3DSIO_END (0x0000ffff).
static uint32_t new_shader(Ctx *c, int iface, uint32_t p, uint32_t out) {
    if (!p || !out) return D3DERR_INVALIDCALL;
    uint32_t ver = ld(c, p, 4), n = 1;
    if (iface == I_VS ? (ver >> 16 != 0xfffe || (ver & 0xffff) > 0x200) : (ver >> 16 != 0xffff || (ver & 0xffff) > 0x200))
        return D3DERR_INVALIDCALL;
    while (ld(c, p + 4 * (n - 1), 4) != 0x0000ffffu) if (++n > 65536) return D3DERR_INVALIDCALL;
    Sm1 *sm = calloc(1, sizeof *sm);
    char err[128];
    if (sm1_decode(sm, (const uint32_t *)G(p), n, err, sizeof err)) { rn_halt(c, "d3d9: shader: %s", err); return D3DERR_INVALIDCALL; }
    uint32_t g = new_obj(c, iface);
    Obj *o = &objs[top];
    o->nblob = n;
    o->blob = malloc(4u * n);
    memcpy(o->blob, G(p), 4u * n);
    o->sm = sm;
    TR("Create%sShader %s_%u_%u, %u tokens -> %08x", iface == I_VS ? "Vertex" : "Pixel", iface == I_VS ? "vs" : "ps",
       (ver >> 8) & 0xff, ver & 0xff, n, g);
    if (rn_trace() || getenv("RN_VS")) { TR(""); rn_log("d3d9 shader %08x %s_%u_%u", g, iface == I_VS ? "vs" : "ps", (ver >> 8) & 0xff, ver & 0xff); sm1_disasm(sm, disasm_line); }
    static int perpixel = -1;   // RN_NOPERPIXEL=1: the plain per-vertex car shader (the before of an A/B)
    if (perpixel < 0) perpixel = getenv("RN_NOPERPIXEL") == NULL;
    uint32_t h = shader_hash(o);
    int mode = !perpixel ? SM1_PLAIN : iface == I_VS && h == 0x4728b668u ? SM1_CAR_VS : iface == I_PS && h == 0xc27f3669u ? SM1_CAR_PS : SM1_PLAIN;
    // The headlight world pairs (worldheadlight, worldheadlightreflect): other cars' headlights, host/lights.c.
    if (iface == I_VS && (h == 0x67da8f41u || h == 0x102e066du)) mode = SM1_HL_VS;
    if (iface == I_PS && (h == 0x91d5deecu || h == 0x9bb3f7c7u)) mode = SM1_HL_PS;
    o->hl = mode == SM1_HL_VS;
    // The road reflection weight (sm1.c sm1_roadrefl, ?roadrefl=): worldreflect.efx ps 0x92e7bdab, worldheadlightreflect.efx ps 0x9bb3f7c7.
    if (iface == I_PS && (h == 0x92e7bdabu || h == 0x9bb3f7c7u)) {
        o->refl = h == 0x92e7bdabu ? 1 : 2;
        if (sm1_roadrefl() == 1 || sm1_roadrefl() == 2) mode |= SM1_REFL;
    }
    if (getenv("RN_SMOOTH_LOG")) rn_log("SMOOTH shader %s id %x hash %08x mode %d", iface == I_VS ? "vs" : "ps", g, h, mode);
    if (mode == SM1_CAR_VS && ncar_vs < 8) car_vs_obj[ncar_vs++] = o;
    if (iface == I_VS && h == 0x95d99bf8u && nbone_vs < 8) bone_vs_obj[nbone_vs++] = o;
    char *wgsl = sm1_wgsl(sm, mode);
    uint32_t m = (uint32_t)strlen(wgsl), nw = 21 + n + (m + 4) / 4;
    uint32_t *w = calloc(nw, 4);
    w[0] = idx(o) + 1; w[1] = iface == I_PS; w[2] = n; w[3] = m;
    for (int k = 0; k < 16; k++) if (sm->inputs >> k & 1) w[4 + k] = 1u << 31 | (uint32_t)sm->in_usage[k] << 8 | sm->in_index[k];
    w[20] = sm->tex_used;
    memcpy(w + 21, o->blob, 4u * n);
    memcpy(w + 21 + n, wgsl, m);
    gpu_cmd(GPU_SHADER, (int)nw, w);
    free(w);
    free(wgsl);
    st(c, out, g, 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_CreateVertexShader(Ctx *c) { DEV(); return new_shader(c, I_VS, ARG(1), ARG(2)); }
static uint32_t IDirect3DDevice9_CreatePixelShader(Ctx *c) { DEV(); return new_shader(c, I_PS, ARG(1), ARG(2)); }
static uint32_t shader_function(Ctx *c, Obj *o) {
    if (ARG(2)) st(c, ARG(2), 4 * o->nblob, 4);
    if (ARG(1)) memcpy(G(ARG(1)), o->blob, 4u * o->nblob);
    return D3D_OK;
}
static uint32_t IDirect3DVertexShader9_GetFunction(Ctx *c) { SELF(I_VS); return shader_function(c, o); }
static uint32_t IDirect3DPixelShader9_GetFunction(Ctx *c) { SELF(I_PS); return shader_function(c, o); }

// Bindings hold no reference in this layer's bookkeeping beyond the index (d3d9 AddRefs bound objects;
// the game cannot observe it except through Release return values).
static uint32_t bind(Ctx *c, uint32_t *slot, uint32_t p, int iface) {
    Obj *o = p ? obj_of(c, p, iface) : NULL;
    if (p && !o) return D3DERR_INVALIDCALL;
    *slot = o ? idx(o) + 1 : 0;
    return D3D_OK;
}
static uint32_t get_bound(Ctx *c, uint32_t out, uint32_t k1) {
    if (!out) return D3DERR_INVALIDCALL;
    if (!k1) { st(c, out, 0, 4); return D3D_OK; }
    return ref_out(c, out, k1);
}
static uint32_t IDirect3DDevice9_SetVertexDeclaration(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetVertexDeclaration, 2, -1, 0); dev.fvf = 0; return bind(c, &dev.decl, ARG(1), I_DECL); }
static uint32_t IDirect3DDevice9_GetVertexDeclaration(Ctx *c) { DEV(); return get_bound(c, ARG(1), dev.decl); }
static uint32_t IDirect3DDevice9_SetFVF(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetFVF, 2, -1, 0); TR("SetFVF(%x)", ARG(1)); dev.fvf = ARG(1); dev.decl = dev.fvf ? fvf_decl(c, dev.fvf) : 0; return D3D_OK; }
static uint32_t IDirect3DDevice9_GetFVF(Ctx *c) { DEV(); st(c, ARG(1), dev.fvf, 4); return D3D_OK; }
static uint32_t IDirect3DDevice9_SetVertexShader(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetVertexShader, 2, -1, 0); return bind(c, &dev.vs, ARG(1), I_VS); }
static uint32_t IDirect3DDevice9_GetVertexShader(Ctx *c) { DEV(); return get_bound(c, ARG(1), dev.vs); }
static uint32_t IDirect3DDevice9_SetPixelShader(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetPixelShader, 2, -1, 0); return bind(c, &dev.ps, ARG(1), I_PS); }
static uint32_t IDirect3DDevice9_GetPixelShader(Ctx *c) { DEV(); return get_bound(c, ARG(1), dev.ps); }
static uint32_t IDirect3DDevice9_SetIndices(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetIndices, 2, -1, 0); return bind(c, &dev.ib, ARG(1), I_IB); }
static uint32_t IDirect3DDevice9_GetIndices(Ctx *c) { DEV(); return get_bound(c, ARG(1), dev.ib); }
static uint32_t IDirect3DDevice9_SetTexture(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetTexture, 3, -1, 0);
    uint32_t s = ARG(1), p = ARG(2);
    if (s >= 16) return D3DERR_INVALIDCALL;
    Obj *o = p ? obj_of(c, p, -1) : NULL;
    if (p && (!o || (o->iface != I_TEXTURE && o->iface != I_CUBE))) return D3DERR_INVALIDCALL;
    dev.tex[s] = o ? idx(o) + 1 : 0;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetTexture(Ctx *c) { DEV(); if (ARG(1) >= 16) return D3DERR_INVALIDCALL; return get_bound(c, ARG(2), dev.tex[ARG(1)]); }
static uint32_t IDirect3DDevice9_SetStreamSource(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetStreamSource, 5, -1, 0);
    uint32_t s = ARG(1);
    if (s >= 16) return D3DERR_INVALIDCALL;
    uint32_t r = bind(c, &dev.stream[s].vb, ARG(2), I_VB);
    dev.stream[s].off = ARG(3);
    dev.stream[s].stride = ARG(4);
    return r;
}
static uint32_t IDirect3DDevice9_GetStreamSource(Ctx *c) {
    DEV();
    uint32_t s = ARG(1);
    if (s >= 16) return D3DERR_INVALIDCALL;
    if (ARG(3)) st(c, ARG(3), dev.stream[s].off, 4);
    if (ARG(4)) st(c, ARG(4), dev.stream[s].stride, 4);
    return get_bound(c, ARG(2), dev.stream[s].vb);
}
// Instancing is a shader model 3 feature: this part takes only the default frequency 1.
static uint32_t IDirect3DDevice9_SetStreamSourceFreq(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetStreamSourceFreq, 3, -1, 0);
    if (ARG(1) >= 16 || ARG(2) != 1) return D3DERR_INVALIDCALL;
    dev.stream[ARG(1)].freq = 1;
    return D3D_OK;
}

static uint32_t set_consts(Ctx *c, void *dst, uint32_t nregs, uint32_t words) {
    uint32_t start = ARG(1), p = ARG(2), n = ARG(3);
    if (!p || start + n > nregs) return D3DERR_INVALIDCALL;
    memcpy((char *)dst + 4u * words * start, G(p), 4u * words * n);
    return D3D_OK;
}
static uint32_t get_consts(Ctx *c, const void *src, uint32_t nregs, uint32_t words) {
    uint32_t start = ARG(1), p = ARG(2), n = ARG(3);
    if (!p || start + n > nregs) return D3DERR_INVALIDCALL;
    memcpy(G(p), (const char *)src + 4u * words * start, 4u * words * n);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetVertexShaderConstantF(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetVertexShaderConstantF, 4, 2, 16 * ARG(3)); return set_consts(c, dev.vsf, 256, 4); }
static uint32_t IDirect3DDevice9_GetVertexShaderConstantF(Ctx *c) { DEV(); return get_consts(c, dev.vsf, 256, 4); }
static uint32_t IDirect3DDevice9_SetVertexShaderConstantI(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetVertexShaderConstantI, 4, 2, 16 * ARG(3)); return set_consts(c, dev.vsi, 16, 4); }
static uint32_t IDirect3DDevice9_SetVertexShaderConstantB(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetVertexShaderConstantB, 4, 2, 4 * ARG(3)); return set_consts(c, dev.vsb, 16, 1); }
static uint32_t IDirect3DDevice9_SetPixelShaderConstantF(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetPixelShaderConstantF, 4, 2, 16 * ARG(3)); return set_consts(c, dev.psf, 32, 4); }
static uint32_t IDirect3DDevice9_GetPixelShaderConstantF(Ctx *c) { DEV(); return get_consts(c, dev.psf, 32, 4); }
static uint32_t IDirect3DDevice9_SetPixelShaderConstantI(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetPixelShaderConstantI, 4, 2, 16 * ARG(3)); return set_consts(c, dev.psi, 16, 4); }
static uint32_t IDirect3DDevice9_SetPixelShaderConstantB(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetPixelShaderConstantB, 4, 2, 4 * ARG(3)); return set_consts(c, dev.psb, 16, 1); }

// ---- fixed function state -----------------------------------------------------------------------
static uint32_t IDirect3DDevice9_SetMaterial(Ctx *c) { DEV(); REC(IDirect3DDevice9_SetMaterial, 2, 1, 68); if (!ARG(1)) return D3DERR_INVALIDCALL; memcpy(dev.material, G(ARG(1)), 68); return D3D_OK; }
static uint32_t IDirect3DDevice9_GetMaterial(Ctx *c) { DEV(); if (!ARG(1)) return D3DERR_INVALIDCALL; memcpy(G(ARG(1)), dev.material, 68); return D3D_OK; }
// D3DLIGHT9 is 104 bytes. Lights are indexed by any DWORD; this layer keeps 64 slots.
static uint32_t IDirect3DDevice9_SetLight(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetLight, 3, 2, 104);
    uint32_t i = ARG(1);
    if (!ARG(2)) return D3DERR_INVALIDCALL;
    if (i >= 64) { rn_halt(c, "d3d9: light index %u", i); return D3DERR_INVALIDCALL; }
    memcpy(dev.light[i], G(ARG(2)), 104);
    dev.light_set[i] = 1;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetLight(Ctx *c) {
    DEV();
    uint32_t i = ARG(1);
    if (i >= 64 || !dev.light_set[i] || !ARG(2)) return D3DERR_INVALIDCALL;
    memcpy(G(ARG(2)), dev.light[i], 104);
    return D3D_OK;
}
// LightEnable on a light never set defines it with the default light: white directional along +z.
static uint32_t IDirect3DDevice9_LightEnable(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_LightEnable, 3, -1, 0);
    uint32_t i = ARG(1);
    if (i >= 64) { rn_halt(c, "d3d9: light index %u", i); return D3DERR_INVALIDCALL; }
    if (!dev.light_set[i]) {
        memset(dev.light[i], 0, 104);
        dev.light[i][0] = 3;                                     // D3DLIGHT_DIRECTIONAL
        dev.light[i][1] = dev.light[i][2] = dev.light[i][3] = F1; // Diffuse 1,1,1,0
        dev.light[i][18] = F1;                                   // Direction 0,0,1
        dev.light_set[i] = 1;
    }
    dev.light_on[i] = ARG(2) != 0;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetLightEnable(Ctx *c) {
    DEV();
    uint32_t i = ARG(1);
    if (i >= 64 || !dev.light_set[i] || !ARG(2)) return D3DERR_INVALIDCALL;
    st(c, ARG(2), dev.light_on[i] ? 128 : 0, 4);     // TRUE as d3d9 reports it: a nonzero value
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetClipPlane(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetClipPlane, 3, 2, 16);
    if (ARG(1) >= 6 || !ARG(2)) return D3DERR_INVALIDCALL;
    memcpy(dev.clip[ARG(1)], G(ARG(2)), 16);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetClipPlane(Ctx *c) {
    DEV();
    if (ARG(1) >= 6 || !ARG(2)) return D3DERR_INVALIDCALL;
    memcpy(G(ARG(2)), dev.clip[ARG(1)], 16);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_SetScissorRect(Ctx *c) {
    DEV(); REC(IDirect3DDevice9_SetScissorRect, 2, 1, 16);
    if (!ARG(1)) return D3DERR_INVALIDCALL;
    for (int k = 0; k < 4; k++) dev.scissor[k] = ld(c, ARG(1) + 4 * k, 4);
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_GetScissorRect(Ctx *c) {
    DEV();
    if (!ARG(1)) return D3DERR_INVALIDCALL;
    for (int k = 0; k < 4; k++) st(c, ARG(1) + 4 * k, dev.scissor[k], 4);
    return D3D_OK;
}
// ValidateDevice: one pass for whatever is bound; the renderer takes any state this part takes.
static uint32_t IDirect3DDevice9_ValidateDevice(Ctx *c) { DEV(); if (ARG(1)) st(c, ARG(1), 1, 4); TR("ValidateDevice -> 1 pass"); return D3D_OK; }
static uint32_t IDirect3DDevice9_EvictManagedResources(Ctx *c) { DEV(); return D3D_OK; }
static uint32_t IDirect3DDevice9_ShowCursor(Ctx *c) { DEV(); int was = dev.cursor_shown; dev.cursor_shown = ARG(1) != 0; return (uint32_t)was; }
static uint32_t IDirect3DDevice9_SetCursorPosition(Ctx *c) { DEV(); return 0; }
// D3DGAMMARAMP: 3 x 256 WORDs. The ramp is kept; the renderer applies it at present (not yet).
static uint32_t IDirect3DDevice9_SetGammaRamp(Ctx *c) {
    DEV();
    if (ARG(1) != 0 || !ARG(3)) return 0;
    memcpy(dev.gamma, G(ARG(3)), sizeof dev.gamma);
    TR("SetGammaRamp(flags %x): r[128]=%u", ARG(2), dev.gamma[0][128]);
    return 0;
}
static uint32_t IDirect3DDevice9_GetGammaRamp(Ctx *c) {
    DEV();
    if (ARG(1) != 0 || !ARG(2)) return 0;
    memcpy(G(ARG(2)), dev.gamma, sizeof dev.gamma);
    return 0;
}

// ---- draws --------------------------------------------------------------------------------------
// A draw goes to the list with everything the renderer needs: the states, the constants and a copy of
// the vertices and indices it uses (so later locks cannot change it). Fans become lists here.
static uint32_t prim_ok(uint32_t type, uint32_t count) {
    return type >= 1 && type <= 6 && count && count <= 0xfffff && dev.in_scene;
}
static uint32_t verts_of(uint32_t type, uint32_t n) {
    switch (type) {
    case 1: return n;
    case 2: return 2 * n;
    case 3: return n + 1;
    case 4: return 3 * n;
    }
    return n + 2;
}
// States this renderer does not draw yet stop loudly (each one is a feature to add, not to guess).
static int draw_supported(Ctx *c, const Sm1 *ps) {
    const char *why = NULL;
    if (!dev.vs || !dev.ps) why = "fixed-function draw (no vertex or pixel shader)";
    else if (!dev.decl) why = "draw without a vertex declaration";
    else if (dev.rs[8] != 3) why = "FILLMODE not solid";
    else if (dev.rs[9] != 2) why = "SHADEMODE not Gouraud";
    else if (dev.rs[52]) why = "stencil test";
    else if (dev.rs[152]) why = "user clip planes";
    else if (dev.rs[195] || dev.rs[176]) why = "depth bias";
    else if (dev.rs[194]) why = "SRGBWRITEENABLE";
    else if (dev.rs[28] && dev.rs[35]) why = "table (pixel) fog";
    else if (dev.rs[206] && (dev.rs[207] != dev.rs[19] || dev.rs[208] != dev.rs[20] || dev.rs[209] != dev.rs[171]))
        why = "separate alpha blend";
    for (int k = 0; k < 8 && !why; k++) {
        if (!(ps->tex_used >> k & 1)) continue;
        const uint32_t *ss = dev.ss[k];
        if (ss[1] == 4 || ss[2] == 4) why = "BORDER texture address";
        else if (ss[8]) why = "MIPMAPLODBIAS";
        else if (ss[9]) why = "MAXMIPLEVEL";
        else if (ss[11]) why = "SRGBTEXTURE";
    }
    if (why) rn_halt(c, "d3d9: draw needs %s", why);
    return !why;
}
// vbase: guest address of vertex 0 of the draw; idx: guest indices (0 = none) of nidx, 16 or 32 bits,
// rebased by -vmin. Vertices [vmin, vmin + nvert) are copied.
// A draw whose vertices and indices are host-made (the smoothed car): draw_cmd takes them instead of the guest's.
static struct { const void *vb; uint32_t nvert; const uint16_t *idx; uint32_t nidx; } xdraw;
// A resident draw (see resident()): set by the draw call, read by draw_cmd. vb = 0: not resident.
static struct { uint32_t vb, voff, ib, isize, first; int32_t basev; } rdraw;
// ROADREFL evidence (RN_ROADREFL_LOG=1): the reflection RT is the texture that the reflect pixel shaders bind on their reflected
// stage (1 for worldreflect, 3 for worldheadlightreflect), checked to be a 320x240 render target, as sub_40a890 creates it
// (CreateTexture 0x140 x 0xf0, RENDERTARGET, into [0x71aa28]). Per frame: draws that sample it (with the curve when the pixel
// shader carries SM1_REFL) and draws into it (the mirrored world, sub_570950, only while ROADREFLECTION [0x700e90] > 1).
static struct { uint32_t tex, sample, curve, mirror; } rr;
static void roadrefl_note(const Obj *ps) {
    if (ps && ps->refl) {
        uint32_t k = dev.tex[ps->refl == 1 ? 1 : 3];
        const Obj *t = obj_k(k);
        if (t && (t->usage & U_RENDERTARGET) && t->w == 320 && t->h == 240) {
            rr.tex = k; rr.sample++;
            if (sm1_roadrefl() == 1 || sm1_roadrefl() == 2) rr.curve++;
        }
    }
    const Obj *s = obj_k(dev.rt[0]);
    if (rr.tex && s && s->container == rr.tex) rr.mirror++;
}
static void roadrefl_frame(void) {
    static int on = -1;
    if (on < 0) on = getenv("RN_ROADREFL_LOG") != NULL;
    if (on && (rr.sample || rr.mirror) && dev.frames % 60 == 0)
        rn_log("ROADREFL %s frame %u: RT tex %u 320x240, %u reflect draws sample it (%u with the curve), %u draws into it (mirrored world)",
               (const char *[]){"game", "sq", "cube", "off"}[sm1_roadrefl()], dev.frames, rr.tex, rr.sample, rr.curve, rr.mirror);
    rr.sample = rr.curve = rr.mirror = 0;
}
static void draw_cmd(Ctx *c, uint32_t type, uint32_t count, uint32_t vbase, uint32_t stride, uint32_t vmin, uint32_t nvert,
                     uint32_t ib, int i32, int32_t ibias) {
    TR("draw %u x%u vs %u ps %u decl %u tex %u %u %u %u blend %u %u/%u atest %u z %u/%u cull %u fog %u", type, count,
       dev.vs, dev.ps, dev.decl, dev.tex[0], dev.tex[1], dev.tex[2], dev.tex[3], dev.rs[27], dev.rs[19], dev.rs[20],
       dev.rs[15], dev.rs[7], dev.rs[14], dev.rs[22], dev.rs[28]);
    Obj *vs = obj_k(dev.vs), *ps = obj_k(dev.ps);
    if (!draw_supported(c, ps ? ps->sm : NULL)) return;
    roadrefl_note(ps);
    if (type <= 3) { rn_halt(c, "d3d9: point and line draws are not drawn yet"); return; }
    // Index list: given, or made for fans.
    uint32_t nidx = 0, *ix = NULL, n = verts_of(type, count);
    if (rdraw.vb) {
        nidx = rdraw.ib ? n : 0; nvert = rdraw.ib ? 0 : n;
    } else if (xdraw.vb) {
        nidx = xdraw.nidx; nvert = xdraw.nvert; ix = malloc(4u * nidx);
        for (uint32_t k = 0; k < nidx; k++) ix[k] = xdraw.idx[k];
        type = 4;
    } else if (ib || type == 6) {
        nidx = type == 6 ? 3 * count : n;
        ix = malloc(4u * nidx);
        for (uint32_t k = 0; k < nidx; k++) {
            uint32_t src = type == 6 ? (k % 3 == 0 ? 0 : k / 3 + k % 3) : k;
            uint32_t v = ib ? ld(c, ib + (i32 ? 4 : 2) * src, i32 ? 4 : 2) : src;
            ix[k] = (uint32_t)((int32_t)v + ibias) - vmin;
        }
        if (type == 6) type = 4;
    }
    if (!ib && !xdraw.vb && !rdraw.vb) nvert = n;
    Obj *rt = obj_k(dev.rt[0]), *ds = obj_k(dev.ds);
    uint32_t nvc = vs->hl ? 16 + 4 * SM1_HL_N : (uint32_t)(vs->sm->max_const + 1), npc = 8, vbytes = rdraw.vb ? 0 : nvert * stride, ni = rdraw.vb ? 0 : nidx;
    uint32_t total = D_HDR + 4 * nvc + 4 * npc + (vbytes + 3) / 4 + ni;
    uint32_t *w = gpu_put(GPU_DRAW, (int)total);   // straight into the frame list: no calloc, copy and free per draw
    w[D_TOPO] = type; w[D_NVERT] = nvert; w[D_NIDX] = nidx; w[D_STRIDE] = stride;
    w[D_VS] = dev.vs; w[D_PS] = dev.ps; w[D_DECL] = dev.decl;
    w[D_RT] = rt->gpu; w[D_DS] = ds && dev.rs[7] ? ds->gpu : 0;
    w[D_VP] = dev.vp.x; w[D_VP + 1] = dev.vp.y; w[D_VP + 2] = dev.vp.w; w[D_VP + 3] = dev.vp.h;
    memcpy(&w[D_VP + 4], &dev.vp.zmin, 4); memcpy(&w[D_VP + 5], &dev.vp.zmax, 4);
    uint32_t sc[4] = {0, 0, rt->w, rt->h};
    if (dev.rs[174]) {
        for (int k = 0; k < 2; k++) if (dev.scissor[k] > sc[k]) sc[k] = dev.scissor[k];
        for (int k = 2; k < 4; k++) if (dev.scissor[k] < sc[k]) sc[k] = dev.scissor[k];
    }
    memcpy(&w[D_SC], sc, 16);
    w[D_ZEN] = dev.rs[7]; w[D_ZWRITE] = dev.rs[14]; w[D_ZFUNC] = dev.rs[23]; w[D_CULL] = dev.rs[22];
    w[D_BLEND] = dev.rs[27]; w[D_SRCB] = dev.rs[19]; w[D_DSTB] = dev.rs[20]; w[D_BOP] = dev.rs[171];
    w[D_SEPA] = dev.rs[206]; w[D_SRCBA] = dev.rs[207]; w[D_DSTBA] = dev.rs[208]; w[D_BOPA] = dev.rs[209];
    w[D_BFACTOR] = dev.rs[193]; w[D_CWRITE] = dev.rs[168];
    w[D_AFUNC] = dev.rs[15] ? dev.rs[25] : 0; w[D_AREF] = dev.rs[24] & 0xff;
    w[D_FOG] = dev.rs[28]; w[D_FOGC] = dev.rs[34];
    for (int k = 0; k < 8; k++) {
        if (!(ps->sm->tex_used >> k & 1)) continue;
        uint32_t *t = &w[D_TEX + D_TEXN * k];
        Obj *tx = obj_k(dev.tex[k]);
        int cube = tx && tx->iface == I_CUBE;
        t[T_ID] = !tx ? 0 : cube ? dev.tex[k] : (tx->usage & U_RENDERTARGET) ? objs[tx->level0].gpu : dev.tex[k];
        t[T_AU] = dev.ss[k][1]; t[T_AV] = dev.ss[k][2]; t[T_MAG] = dev.ss[k][5]; t[T_MIN] = dev.ss[k][6];
        t[T_MIP] = tx && tx->levels > 1 ? dev.ss[k][7] : 0; t[T_TT] = dev.tss[k][24] | (cube ? T_CUBE : 0);
        t[T_ANISO] = dev.ss[k][10];
    }
    w[D_NVC] = nvc; w[D_NPC] = npc;
    w[D_RVB] = rdraw.vb; w[D_RVOFF] = rdraw.voff; w[D_RIB] = rdraw.ib; w[D_RIFMT] = rdraw.isize;
    w[D_RFIRST] = rdraw.first; w[D_RBASEV] = (uint32_t)rdraw.basev;
    uint32_t *p = w + D_HDR;
    memcpy(p, dev.vsf, 16u * nvc);
    if (vs->hl) memcpy(p + 4 * 16, lights_hl(c), 16u * 4 * SM1_HL_N);
    p += 4 * nvc;
    memcpy(p, dev.psf, 16u * npc); p += 4 * npc;
    if (vbytes) memcpy(p, xdraw.vb ? xdraw.vb : G(vbase + vmin * stride), vbytes);
    p += (vbytes + 3) / 4;
    if (ni) memcpy(p, ix, 4u * ni);
    free(ix);
    // RN_DRAWSTAT=1: words per frame by kind of draw (resident, smoothed car, indexed copy, plain copy), every 300 frames.
    static int dstat = -1;
    if (dstat < 0) dstat = getenv("RN_DRAWSTAT") != NULL;
    if (dstat) {
        static uint64_t sw[4], sn[4], hw, cw; static uint32_t f0;
        int k = rdraw.vb ? 0 : xdraw.vb ? 1 : ib ? 2 : 3;
        sw[k] += total; sn[k]++; hw += D_HDR; cw += 4 * nvc + 4 * npc;
        if (dev.frames - f0 >= 300) {
            uint32_t nf = dev.frames - f0 ? dev.frames - f0 : 1;
            rn_log("DRAWSTAT per frame: resident %llu draws %llukw, smooth %llu %llukw, indexed copy %llu %llukw, plain copy %llu %llukw; header %llukw, constants %llukw",
                   sn[0] / nf, sw[0] / nf / 1024, sn[1] / nf, sw[1] / nf / 1024, sn[2] / nf, sw[2] / nf / 1024, sn[3] / nf, sw[3] / nf / 1024, hw / nf / 1024, cw / nf / 1024);
            memset(sw, 0, sizeof sw); memset(sn, 0, sizeof sn); hw = cw = 0; f0 = dev.frames;
        }
    }
    flush_big();
}
static uint32_t stream0(Ctx *c) {
    Obj *vb = obj_k(dev.stream[0].vb);
    for (uint32_t k = 1; k < 16; k++) if (dev.stream[k].vb) { rn_halt(c, "d3d9: draw with stream %u", k); return 0; }
    return lock_mem(vb) + dev.stream[0].off;
}
static uint32_t IDirect3DDevice9_DrawPrimitive(Ctx *c) {
    DEV();
    if (!prim_ok(ARG(1), ARG(3)) || !dev.stream[0].vb) return D3DERR_INVALIDCALL;
    uint32_t base = stream0(c), stride = dev.stream[0].stride;
    Obj *vb = obj_k(dev.stream[0].vb);
    if (base && resident(vb) && (ARG(1) == 4 || ARG(1) == 5)) {
        rdraw.vb = dev.stream[0].vb; rdraw.voff = dev.stream[0].off; rdraw.ib = 0; rdraw.isize = 0; rdraw.first = ARG(2); rdraw.basev = 0;
        draw_cmd(c, ARG(1), ARG(3), base, stride, 0, 0, 0, 0, 0);
        rdraw.vb = 0;
        return D3D_OK;
    }
    if (base) draw_cmd(c, ARG(1), ARG(3), base + ARG(2) * stride, stride, 0, 0, 0, 0, 0);
    return D3D_OK;
}

// BRIDGE: PN smoothing of the car body draws (OWNER 2026-10-20 car remaster; host/carsmooth.c), and of the NIS people (worldbone.efx,
// OWNER 2026-10-27: skin weights carried by skin_blend). The original draws the 2003 low-poly
// meshes as authored; here a draw of the car shader (vs token hash 0x4728b668) with >= 40 triangles is curved and subdivided before
// it goes to the GPU. Vertex offsets come from the bound declaration; results are cached by content. RN_SMOOTH=<level> (default 3, 0 = off).
static int is_car_vs(uint32_t id) { const Obj *o = obj_k(id); for (int k = 0; k < ncar_vs; k++) if (o && car_vs_obj[k] == o) return 1; return 0; }
static int is_bone_vs(uint32_t id) { const Obj *o = obj_k(id); for (int k = 0; k < nbone_vs; k++) if (o && bone_vs_obj[k] == o) return 1; return 0; }
// fail: cs_smooth said no for this key (drawn as authored, not retried every frame). On the web an entry's vertices and
// indices are resident GPU buffers SMOOTH_GPU + 2 * slot (+1), uploaded once when the entry is made.
typedef struct { uint64_t key; uint8_t *vb; uint32_t nvert; uint16_t *idx; uint32_t nidx; int fail; } SmoothEnt;
#define SMOOTH_GPU 0x40000000u
#define SMOOTH_N 1024  // the cars' draws plus the NIS people's; WORLD's 30 cars passed 700, and with 256 a part in use was evicted and smoothed again
#define SMOOTH_PROBE 8 // an entry lives within 8 slots of key % SMOOTH_N, so a car draw looks at 8 entries, not all
static SmoothEnt smooth_cache[SMOOTH_N];
static uint32_t smooth_next;
static uint64_t fnv64b(uint64_t h, const void *p, size_t n) {
    const uint8_t *b = p;
    for (size_t k = 0; k < n; k++) h = (h ^ b[k]) * 0x100000001b3ull;
    return h;
}
// Offsets of POSITION (float3), NORMAL (float3) and TEXCOORD0 (float2) in stream 0 of the bound declaration; 0 when it is not that shape.
// sk (may be NULL) gets COLOR0 (D3DCOLOR), BLENDWEIGHT (float3) and BLENDINDICES (float3), -1 when absent: worldbone.efx's VS_INPUT.
static int decl_offsets(int *po, int *no, int *to, int *sk) {
    Obj *d = obj_k(dev.decl);
    *po = *no = *to = -1;
    if (sk) sk[0] = sk[1] = sk[2] = -1;
    if (!d || !d->blob) return 0;
    const uint8_t *e = (const uint8_t *)d->blob;
    for (uint32_t k = 0; k + 1 < d->nblob / 2; k++, e += 8) {
        uint16_t stream = (uint16_t)(e[0] | e[1] << 8), off = (uint16_t)(e[2] | e[3] << 8);
        if (stream == 0xff) break;
        if (stream != 0) return 0;
        if (e[6] == 0 && e[7] == 0 && e[4] == 2) *po = off;        // POSITION0, D3DDECLTYPE_FLOAT3
        else if (e[6] == 3 && e[7] == 0 && e[4] == 2) *no = off;   // NORMAL0
        else if (e[6] == 5 && e[7] == 0 && e[4] == 1) *to = off;   // TEXCOORD0, FLOAT2
        else if (sk && e[6] == 10 && e[7] == 0 && e[4] == 4) sk[0] = off;   // COLOR0, D3DCOLOR
        else if (sk && e[6] == 1 && e[7] == 0 && e[4] == 2) sk[1] = off;    // BLENDWEIGHT, FLOAT3
        else if (sk && e[6] == 2 && e[7] == 0 && e[4] == 2) sk[2] = off;    // BLENDINDICES, FLOAT3
    }
    return *po >= 0 && *no >= 0 && *to >= 0;
}
// Skin data of one smoothed vertex of a worldbone draw: the corners' bones weighted by the barycentrics, the 3 heaviest kept
// (renormalised to the same total) heaviest first, since the shader turns the normal by index.x alone; colour interpolated.
// Positions stay in the bind pose, so the game's own vertex shader still poses the curved mesh each frame.
static void skin_blend(uint8_t *d, const uint8_t *const cv[3], const float *b, const int *sk) {
    float bone[9], wt[9], total = 0, col[4] = {0, 0, 0, 0};
    int n = 0;
    for (int c = 0; c < 3; c++) {
        float ww[3], ii[3];
        memcpy(ww, cv[c] + sk[1], 12); memcpy(ii, cv[c] + sk[2], 12);
        for (int s = 0; s < 3; s++) {
            float w = ww[s] * b[c];
            if (w <= 0) continue;
            int j = 0;
            while (j < n && bone[j] != ii[s]) j++;
            if (j == n) { bone[n] = ii[s]; wt[n++] = 0; }
            wt[j] += w; total += w;
        }
        for (int k = 0; k < 4; k++) col[k] += cv[c][sk[0] + k] * b[c];
    }
    for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++)
        if (wt[j] > wt[i]) { float t = wt[i]; wt[i] = wt[j]; wt[j] = t; t = bone[i]; bone[i] = bone[j]; bone[j] = t; }
    float kept = 0, w3[3] = {0, 0, 0}, i3[3] = {0, 0, 0};
    for (int i = 0; i < n && i < 3; i++) kept += wt[i];
    for (int i = 0; i < n && i < 3; i++) { w3[i] = wt[i] * total / kept; i3[i] = bone[i]; }
    if (n) { memcpy(d + sk[1], w3, 12); memcpy(d + sk[2], i3, 12); }
    for (int k = 0; k < 4; k++) d[sk[0] + k] = (uint8_t)lrintf(col[k] < 0 ? 0 : col[k] > 255 ? 255 : col[k]);
}
// Tries to draw the indexed triangle list smoothed; 1 = drawn.
static int smooth_draw(Ctx *c, uint32_t base, uint32_t stride, uint32_t vmin, uint32_t nvert, uint32_t ibp, uint32_t count) {
    // Keep the authored car/NPC mesh; avoid smoothing allocations and extra triangles on Ultra-Lite.
    if (tier_ultralite()) return 0;
    static int level = -1;
    if (level < 0) { const char *e = getenv("RN_SMOOTH"); level = e ? atoi(e) : 3; }
    static int slog = -1, nlog;   // RN_SMOOTH_LOG=1: why a car draw is not smoothed (first 40 draws)
    if (slog < 0) slog = getenv("RN_SMOOTH_LOG") != NULL;
    static int npc_level = -1;   // RN_NPCSMOOTH=<level>: the same for the skinned NIS people (default 3, 0 = off)
    if (npc_level < 0) { const char *e = getenv("RN_NPCSMOOTH"); npc_level = e ? atoi(e) : 3; }
    int skin = npc_level && is_bone_vs(dev.vs), lv = skin ? npc_level : level;
    if (!skin && (!level || !is_car_vs(dev.vs))) return 0;
    int po, no, to, sk[3];
    int dok = decl_offsets(&po, &no, &to, sk) && (!skin || (sk[0] >= 0 && sk[1] >= 0 && sk[2] >= 0));
    if (slog && nlog < 40) {
        nlog++;
        rn_log("SMOOTH draw tris %u nverts %u stride %u decl_ok %d offsets %d %d %d", count, nvert, stride, dok, po, no, to);
        Obj *d = obj_k(dev.decl);
        if (d && nlog <= 2) for (uint32_t k = 0; k + 1 < d->nblob / 2; k++) {
            const uint8_t *e = (const uint8_t *)d->blob + 8 * k;
            rn_log("SMOOTH   elem stream %u off %u type %u usage %u idx %u", e[0] | e[1] << 8, e[2] | e[3] << 8, e[4], e[6], e[7]);
            if ((e[0] | e[1] << 8) == 0xff) break;
        }
    }
    if (count < (skin ? 16u : 40u) || nvert < 3 || nvert > 60000 || stride < 32 || stride > 64 || !dok) return 0;
    const uint8_t *vsrc = G(base + vmin * stride), *isrc = G(ibp);
    // Key: static buffers are named by (id, write count) and the draw's ranges, so a frame does not hash ~7 MB of car
    // vertices; dynamic ones by content.
    Obj *svb = obj_k(dev.stream[0].vb), *sib = obj_k(dev.ib);
    uint64_t key;
    if (svb && sib && !(svb->usage & U_DYNAMIC) && !(sib->usage & U_DYNAMIC)) {
        uint32_t t[9] = {dev.stream[0].vb, svb->ver, dev.ib, sib->ver, base, vmin, nvert, ibp, count};
        key = fnv64b(1469598103934665603ull, t, sizeof t);
    } else {
        key = fnv64b(fnv64b(1469598103934665603ull, vsrc, (size_t)nvert * stride), isrc, (size_t)count * 6);
    }
    key = fnv64b(key, &lv, sizeof lv) ^ ((uint64_t)vmin << 32 | stride);
    SmoothEnt *ent = NULL;
    for (int k = 0; k < SMOOTH_PROBE; k++) { SmoothEnt *e = &smooth_cache[(key + (uint64_t)k) % SMOOTH_N]; if (e->key == key && (e->vb || e->fail)) { ent = e; break; } }
    if (ent && ent->fail) return 0;
    if (!ent) {
        float *v5 = malloc((size_t)nvert * 5 * sizeof *v5);
        uint16_t *ix = malloc((size_t)count * 6);
        for (uint32_t k = 0; k < nvert; k++) {
            const uint8_t *s = vsrc + (size_t)k * stride;
            memcpy(&v5[5 * k], s + po, 12); memcpy(&v5[5 * k + 3], s + to, 8);
        }
        int bad = 0;
        for (uint32_t k = 0; k < count * 3; k++) {
            uint32_t v = (uint32_t)(isrc[2 * k] | isrc[2 * k + 1] << 8);
            if (v < vmin || v - vmin >= nvert) { bad = 1; break; }
            ix[k] = (uint16_t)(v - vmin);
        }
        float *nr = skin ? malloc((size_t)nvert * 3 * sizeof *nr) : NULL;   // the people keep their authored normals (smoothing groups)
        for (uint32_t k = 0; nr && k < nvert; k++) {
            float *n = nr + 3 * k;
            memcpy(n, vsrc + (size_t)k * stride + no, 12);
            float l = sqrtf(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
            for (int a = 0; a < 3; a++) n[a] = l > 1e-12f ? n[a] / l : 0;
        }
        uint64_t t_us = now_us();
        CsIn in = {v5, (int)nvert, ix, (int)count * 3, skin, nr};
        CsOut out;
        int ok = !bad && cs_smooth(&in, &out, lv);
        free(v5); free(nr);
        ent = &smooth_cache[(key + (uint64_t)(smooth_next % SMOOTH_PROBE)) % SMOOTH_N];
        for (int k = 0; k < SMOOTH_PROBE; k++) { SmoothEnt *e = &smooth_cache[(key + (uint64_t)k) % SMOOTH_N]; if (!e->vb && !e->fail) { ent = e; break; } }
        smooth_next++;
        free(ent->vb); free(ent->idx);
        ent->vb = NULL; ent->idx = NULL; ent->key = key; ent->fail = !ok;
        if (!ok) { free(ix); return 0; }
        ent->vb = malloc((size_t)out.nverts * stride);
        for (int k = 0; k < out.nverts; k++) {
            uint8_t *d = ent->vb + (size_t)k * stride;
            memcpy(d, vsrc, stride);                                   // the bytes the car shader does not read (tail) come from vertex 0
            memcpy(d + po, &out.verts[5 * k], 12);
            memcpy(d + no, &out.verts[(size_t)out.nverts * 5 + 3 * k], 12);
            memcpy(d + to, &out.verts[5 * k + 3], 8);
            if (skin) {
                const uint16_t *t3 = ix + 3 * out.tri[k];
                const uint8_t *cv[3] = {vsrc + (size_t)t3[0] * stride, vsrc + (size_t)t3[1] * stride, vsrc + (size_t)t3[2] * stride};
                skin_blend(d, cv, &out.bary[3 * k], sk);
            }
        }
        free(ix); free(out.tri); free(out.bary);
        if (skin && getenv("RN_NPCLOG")) rn_log("NPC smooth entry %u: %u tris -> %d, %d verts, %.2f ms", smooth_next, count, out.nidx / 3,
                                                out.nverts, (double)(now_us() - t_us) / 1000);
        ent->key = key; ent->nvert = (uint32_t)out.nverts; ent->idx = out.idx; ent->nidx = (uint32_t)out.nidx;
        free(out.verts);
        if (resident_on()) {
            uint32_t slot = (uint32_t)(ent - smooth_cache), gv = SMOOTH_GPU + 2 * slot, nb[2] = {ent->nvert * stride, ent->nidx * 2};
            const void *src[2] = {ent->vb, ent->idx};
            for (int b = 0; b < 2; b++) {
                uint32_t n4 = (nb[b] + 3) & ~3u, w2[2] = {gv + (uint32_t)b, n4 ? n4 : 4};
                gpu_cmd(GPU_BUFFER, 2, w2);
                uint32_t *w = calloc(3 + n4 / 4, 4);
                w[0] = gv + (uint32_t)b; w[1] = 0; w[2] = n4;
                memcpy(w + 3, src[b], nb[b]);
                gpu_cmd(GPU_BUFDATA, (int)(3 + n4 / 4), w);
                free(w);
            }
            flush_big();
        }
    }
    if (resident_on()) {
        uint32_t gv = SMOOTH_GPU + 2 * (uint32_t)(ent - smooth_cache);
        rdraw.vb = gv; rdraw.voff = 0; rdraw.ib = gv + 1; rdraw.isize = 2; rdraw.first = 0; rdraw.basev = 0;
        draw_cmd(c, 4, ent->nidx / 3, base, stride, vmin, nvert, 0, 0, 0);
        rdraw.vb = 0;
        return 1;
    }
    xdraw.vb = ent->vb; xdraw.nvert = ent->nvert; xdraw.idx = ent->idx; xdraw.nidx = ent->nidx;
    draw_cmd(c, 4, ent->nidx / 3, base, stride, vmin, nvert, 0, 0, 0);
    xdraw.vb = NULL;
    return 1;
}
// DrawIndexedPrimitive(Type, BaseVertexIndex, MinVertexIndex, NumVertices, StartIndex, PrimitiveCount)
static uint32_t dip_frame, dip_n;   // indexed draws so far in this frame (the race HUD bridge: is there a 3D scene under the quads?)
static uint32_t IDirect3DDevice9_DrawIndexedPrimitive(Ctx *c) {
    DEV();
    if (dip_frame != dev.frames) { dip_frame = dev.frames; dip_n = 0; }
    dip_n++;
    if (!prim_ok(ARG(1), ARG(6)) || !dev.stream[0].vb || !dev.ib) return D3DERR_INVALIDCALL;
    if (cen_on > 0) census_draw(c, ARG(6));
    static long skip_vs = -2;   // RN_SKIPVS=<hex id>: drop every indexed draw of that vertex shader (find which family is the car)
    if (skip_vs == -2) { const char *e = getenv("RN_SKIPVS"); skip_vs = e ? strtol(e, NULL, 16) : -1; }
    if (skip_vs >= 0 && dev.vs == (uint32_t)skip_vs) return D3D_OK;
    Obj *ib = obj_k(dev.ib);
    int i32 = ib->fmt == F_INDEX32;
    uint32_t base = stream0(c), stride = dev.stream[0].stride;
    int32_t bv = (int32_t)ARG(2);
    static int smlog = -1;
    if (smlog < 0) smlog = getenv("RN_SMOOTH_LOG") != NULL;
    if (base && smlog && is_car_vs(dev.vs)) { static int nl; if (nl++ < 6) rn_log("SMOOTH call type %u i32 %d prims %u", ARG(1), i32, ARG(6)); }
    static int carlog = -1;   // RN_CARLOG=1: every car body draw of each 600th frame (eye c17 tells the cars apart, paint c18/c19, blend state)
    if (carlog < 0) carlog = getenv("RN_CARLOG") != NULL;
    if (carlog && dev.frames % 600 == 0 && is_car_vs(dev.vs))
        rn_log("CAR f%u eye %.1f %.1f %.1f c18 %.2f %.2f %.2f %.2f c19 %.2f %.2f %.2f %.2f ab %u %u/%u at %u ref %u ps %x t0 %x t1 %x prims %u",
               dev.frames, dev.vsf[17][0], dev.vsf[17][1], dev.vsf[17][2], dev.vsf[18][0], dev.vsf[18][1], dev.vsf[18][2], dev.vsf[18][3],
               dev.vsf[19][0], dev.vsf[19][1], dev.vsf[19][2], dev.vsf[19][3], dev.rs[27], dev.rs[19], dev.rs[20], dev.rs[15], dev.rs[24],
               dev.ps, dev.tex[0], dev.tex[1], ARG(6));
    static int npclog = -1;   // RN_NPCLOG=1: each distinct skinned draw (declaration with BLENDINDICES: fx\worldbone.efx, the NIS people)
    if (npclog < 0) npclog = getenv("RN_NPCLOG") != NULL;
    if (npclog) {
        Obj *d = obj_k(dev.decl), *t = obj_k(dev.tex[0]);
        int skin = 0;
        if (d && d->blob) for (uint32_t k = 0; k + 1 < d->nblob / 2; k++) {
            const uint8_t *e = (const uint8_t *)d->blob + 8 * k;
            if ((e[0] | e[1] << 8) == 0xff) break;
            if (e[6] == 2) skin = 1;
        }
        static uint64_t seen[512]; static int nseen;
        uint64_t key = (uint64_t)dev.stream[0].vb << 40 ^ (uint64_t)ARG(5) << 20 ^ ARG(6);
        int k = 0;
        while (k < nseen && seen[k] != key) k++;
        if (skin && k == nseen && nseen < 512) {
            seen[nseen++] = key;
            rn_log("NPC frame %u vs %x hash %08x decl %x stride %u nvert %u prims %u type %u tex %x %ux%u fmt %x",
                   dev.frames, dev.vs, obj_k(dev.vs) ? shader_hash(obj_k(dev.vs)) : 0, dev.decl, stride, ARG(4), ARG(6), ARG(1),
                   dev.tex[0], t ? t->w : 0, t ? t->h : 0, t ? t->fmt : 0);
            if (nseen == 1 && d) for (uint32_t j = 0; j + 1 < d->nblob / 2; j++) {
                const uint8_t *e = (const uint8_t *)d->blob + 8 * j;
                if ((e[0] | e[1] << 8) == 0xff) break;
                rn_log("NPC   elem off %u type %u usage %u idx %u", e[2] | e[3] << 8, e[4], e[6], e[7]);
            }
        }
    }
    if (base && ARG(1) == 4 && !i32 && smooth_draw(c, base + (uint32_t)bv * stride, stride, ARG(3), ARG(4), lock_mem(ib) + ARG(5) * 2, ARG(6)))
        return D3D_OK;
    if (base && (ARG(1) == 4 || ARG(1) == 5) && resident(obj_k(dev.stream[0].vb)) && resident(ib)) {
        rdraw.vb = dev.stream[0].vb; rdraw.voff = dev.stream[0].off; rdraw.ib = dev.ib; rdraw.isize = i32 ? 4 : 2;
        rdraw.first = ARG(5); rdraw.basev = bv;
        draw_cmd(c, ARG(1), ARG(6), base, stride, 0, 0, 0, 0, 0);
        rdraw.vb = 0;
        return D3D_OK;
    }
    if (base) draw_cmd(c, ARG(1), ARG(6), base + (uint32_t)bv * stride, stride, ARG(3), ARG(4),
                       lock_mem(ib) + ARG(5) * (i32 ? 4 : 2), i32, 0);
    return D3D_OK;
}
// BRIDGE: the FEng tree of the race's screens, for the widescreen layout below. PATCH 0x4f2f13 leaves the FEObject that is
// drawing in SCREEN_ADDR+0x40 (0 outside 0x4f2cb0). An active package (fe_packages' list node) holds its children at +0x40, a
// group (type +0x18 == 5) at +0x60, siblings at +4 (FEPackage::ForAllObjects 0x4ffb00, 0x4ffab0). Once per frame each object
// gets its package and kind (1 = HUD: HUD_*, drag_HUD*); each draw grows its package's box (x in the 640 screen),
// and a frame lays out with the boxes of the frame before (a package's first frame stays in place).
typedef struct { uint32_t obj, pkg; uint8_t hud; } FeNode;
typedef struct { uint32_t obj, f, pf; float x0, x1, px0, px1; } FeBox;
static FeNode fe_node[4096];
static FeBox fe_box[4096];
static uint32_t fe_node_frame = ~0u;
static uint32_t fe_hash(uint32_t a) { return (a >> 2) * 0x9e3779b1u >> 20; }   // 12 bits
static FeNode *fe_node_at(uint32_t obj) {
    for (uint32_t h = fe_hash(obj), k = 0; k < 4096; k++, h = (h + 1) & 4095) {
        if (fe_node[h].obj == obj) return &fe_node[h];
        if (!fe_node[h].obj) return NULL;
    }
    return NULL;
}
static void fe_tree(Ctx *c, uint32_t first, uint32_t pkg, uint8_t hud, int depth, int *budget) {
    for (uint32_t o = first; o && o < c->memsz && depth < 16 && (*budget)-- > 0; o = ld(c, o + 4, 4)) {
        uint32_t h = fe_hash(o);
        while (fe_node[h].obj && fe_node[h].obj != o) h = (h + 1) & 4095;
        fe_node[h] = (FeNode){o, pkg, hud};
        if (ld(c, o + 0x18, 4) == 5) fe_tree(c, ld(c, o + 0x60, 4), pkg, hud, depth + 1, budget);
    }
}
static void fe_tree_frame(Ctx *c) {
    if (fe_node_frame == dev.frames) return;
    fe_node_frame = dev.frames;
    memset(fe_node, 0, sizeof fe_node);
    uint32_t fg = ld(c, 0x73578c, 4), en = fg ? ld(c, fg + 8, 4) : 0, nd = en ? ld(c, en + 0xe4, 4) : 0;
    int budget = 3000;   // 3/4 of the table at most: lookups always meet an empty slot
    for (int i = 0; nd && nd < c->memsz && i < 16; i++, nd = ld(c, nd + 4, 4)) {
        uint32_t p = ld(c, nd + 0xc, 4);
        if (!p || p >= c->memsz) continue;
        const char *s = (const char *)G(p);
        uint8_t hud = !strncmp(s, "HUD_", 4) || !strncmp(s, "drag_HUD", 8);
        fe_tree(c, ld(c, nd + 0x40, 4), nd, hud, 0, &budget);
    }
}
static int fe_side(uint32_t pkg);
static int fe_last(uint32_t obj, float *x0, float *x1);
// RN_FELOG=1: 30 frames after the package set changes (rn_fe), each package of a race screen: its box in the 640 screen
// and side (fe_side), to check the layout against what the screen shows.
static uint32_t fe_log_at = ~0u;
static void fe_log(Ctx *c) {
    static int on = -1;
    static char last[256];
    static uint32_t again = ~0u;
    if (on < 0) on = getenv("RN_FELOG") != NULL;
    if (!on) return;
    if (strcmp(last, rn_fe)) { snprintf(last, sizeof last, "%s", rn_fe); fe_log_at = dev.frames + 30; again = dev.frames + 150; }
    if (dev.frames == again) fe_log_at = dev.frames;   // once more 150 frames in, when the slide-ins are done
    static uint32_t done = ~0u;
    if (dev.frames != fe_log_at || done == dev.frames) return;
    done = dev.frames;
    rn_log("FELOG frame %u packages %s", dev.frames, last);
    uint32_t seen[16];
    int ns = 0;
    for (int h = 0; h < 4096 && ns < 16; h++) {
        FeNode *n = &fe_node[h];
        int dup = 0;
        for (int k = 0; k < ns; k++) dup |= seen[k] == n->pkg;
        if (!n->obj || dup) continue;
        seen[ns++] = n->pkg;
        float x0 = 0, x1 = 0;
        int ok = fe_last(n->pkg, &x0, &x1);
        rn_log("FELOG  %.32s hud %u box %s%.0f..%.0f side %d", G(ld(c, n->pkg + 0xc, 4)), n->hud, ok ? "" : "(none) ", x0, x1, fe_side(n->pkg));
    }
}
static FeBox *fe_box_at(uint32_t obj, int make) {
    uint32_t h = fe_hash(obj);
    for (uint32_t k = 0; k < 4096; k++, h = (h + 1) & 4095) {
        FeBox *b = &fe_box[h];
        if (b->obj == obj) return b;
        if (!b->obj || (make && dev.frames - b->f > 2)) break;   // empty, or an object not drawn for 3 frames: reuse
    }
    if (!make) return NULL;
    fe_box[h] = (FeBox){obj, ~0u, ~0u, 0, 0, 0, 0};
    return &fe_box[h];
}
static void fe_grow(uint32_t key, float u0, float u1) {
    FeBox *b = fe_box_at(key, 1);
    if (b->f != dev.frames) { b->pf = b->f; b->px0 = b->x0; b->px1 = b->x1; b->f = dev.frames; b->x0 = u0; b->x1 = u1; }
    else { if (u0 < b->x0) b->x0 = u0; if (u1 > b->x1) b->x1 = u1; }
}
// The box of obj as the frame before drew it: 0 = none.
static int fe_last(uint32_t obj, float *x0, float *x1) {
    FeBox *b = fe_box_at(obj, 0);
    if (!b) return 0;
    if (b->f == dev.frames && b->pf == dev.frames - 1) { *x0 = b->px0; *x1 = b->px1; return 1; }
    if (b->f == dev.frames - 1) { *x0 = b->x0; *x1 = b->x1; return 1; }
    return 0;
}
// Where a race screen goes: -1 the left window edge, +1 the right one, 0 stays. The package moves as one piece: one whose
// drawn box (layers across the whole 640 screen left out) reaches only the left outer band (x < 190) goes left, only the
// right band (x > 450) right (the standings, the post-race menu, the song banner); one that reaches neither or both (Race
// Style Points, the Leave Race dialog) stays whole in the centre. A package has no anchors (FEng places by 640 x 480
// position only), and moving its groups apart split centred tables into labels and values (run 2026-10-26, shots 14-19).
static int fe_side(uint32_t pkg) {
    float x0, x1;
    if (!fe_last(pkg, &x0, &x1)) return 0;
    int l = x0 < 190.f, r = x1 > 450.f;
    return l != r ? r - l : 0;
}
// The UP draws leave stream 0 (and the index buffer for the indexed one) unset, as documented.
static uint32_t IDirect3DDevice9_DrawPrimitiveUP(Ctx *c) {
    DEV();
    if (!prim_ok(ARG(1), ARG(2)) || !ARG(3) || !ARG(4)) return D3DERR_INVALIDCALL;
    // BRIDGE: widescreen 2D, PC Speed.exe 0x40c2d0 / 0x40c4a2: the front-end sprite quad is one fan of 2 triangles, stride 32.
    // The PATCH at 0x40bf09 lays the 640x480 screen in a centred 4:3 island; the original cut what lies outside 0..640 at the
    // window edge (items parked off screen, slide-ins), so the island is the scissor of these draws.
    // In a race ([0x77a90c] = "EndGameFlowLoadingTrackSpecific" 0x6c9c3c, set once when the track is loaded) the HUD groups sit at the
    // window edges: a quad whose centre is in the left (x < 190) or right (x > 430) part of the 640 screen moves by the free margin.
    // Whole quads move, never single glyphs of a string, because the centre zone (190..430) is empty in the HUD; no scissor then.
    Obj *rt = obj_k(dev.rt[0]);
    int isl = ARG(1) == 6 && ARG(2) == 2 && ARG(4) == 32 && rt && (int)rt->w == rn_screen_w && (int)rt->h == rn_screen_h
              && 3 * rn_screen_w > 4 * rn_screen_h;
    int moved = 0;
    static int racing;   // 0x77a90c is a transient label: latch the track-loaded one until a front-end label follows
    if (isl) {
        uint32_t lb = ld(c, 0x77a90c, 4);
        if (lb == 0x6c9c3c) racing = 1;
        else if (lb == 0x6c9cf0 || lb == 0x6c9de8 || lb == 0x6c9e8c || lb == 0x6c9ea0) racing = 0;
    }
    // BRIDGE: FXAA (web/gpu.js) over the 3D scene, once per race frame, before the first HUD quad (the HUD is drawn last into the same target).
    static uint32_t fxaa_frame = ~0u;
    // The label is set when the track starts loading, so the loading screen is not a race frame: a race frame drew its 3D
    // scene (indexed draws) before the HUD; a loading screen has none (its text was split to the window edges, 2026-10-23).
    int race = isl && racing && dip_frame == dev.frames && dip_n > 0;
    // The race's own screens (PreRaceStats, PostRaceResults, StyleAnimator, RewardPopup, PostRaceMenu, MU_Pause_PC, ...) are
    // FEng packages drawn over the same 3D scene. A per-quad move split their words ("Race St | yle Points", OWNER shot
    // 2026-10-26 7.12 p.m.), and keeping the whole frame in the 4:3 island while one is up made the HUD jump (OWNER 2026-10-26
    // 11.16 p.m.: "the HUD turns 4:3 after the race and on pause"). Now each quad knows its FEng object (PATCH 0x4f2f13):
    // the HUD packages (HUD_SingleRace, HUD_Drift, drag_HUD_test) always go to the edges as before, quad by quad (their centre
    // zone is empty); in the others (the song banner Chyron too: its bar crosses 190) the whole package goes to its side (fe_side)
    // and a layer across the whole 640 screen (the dim behind the results) covers the window. Quads drawn outside the FEng
    // render keep the old rule.
    static uint32_t menu_frame = ~0u;
    static int menu;
    if (race && menu_frame != dev.frames) {
        menu_frame = dev.frames; menu = 0;
        uint32_t np[16];
        for (int i = 0, n = fe_packages(c, np); i < n; i++) {
            const char *s = (const char *)G(np[i]);
            if (strncmp(s, "HUD_", 4) && strncmp(s, "drag_HUD", 8) && strncmp(s, "Chyron.", 7)) menu = 1;
        }
    }
    uint32_t feo = race ? ld(c, SCREEN_ADDR + 0x40, 4) : 0;
    FeNode *fen = NULL;
    if (feo) { fe_tree_frame(c); fen = fe_node_at(feo); fe_log(c); }
    int hud = race && (fen ? fen->hud : !menu), screen = race && fen && !fen->hud;
    rn_hud_on = hud;
    static int hud_seen;
    if (hud && !hud_seen) { hud_seen = 1; rn_log("d3d9 race HUD %ux%u (track loaded, 0x77a90c = 0x6c9c3c, 3D scene drawn)", rt->w, rt->h); rn_fixedclock_start(c); }
    // GPU_FXAA dispatches the bridge's bloom, depth blur and FXAA passes (web/gpu.js).
    if (!tier_ultralite() && race && fxaa_frame != dev.frames) { fxaa_frame = dev.frames; uint32_t w1[8] = {rt->gpu}; psblur_vel(c, w1 + 1); gpu_cmd(GPU_FXAA, 8, w1); }
    // OWNER A/B for the 16:9 decision (build/evidence/1_hud.md): RN_HUD=edges (default) | 169 (the side groups stop at a centred
    // 16:9 box) | 43 (the original 4:3 places); RN_FE=stretch widens the front-end island to the whole window (default: black bars).
    // input_hud_inset (web/touch.js, phones, live): the side groups stop that far from the picture's edge, so the notch and the
    // rounded corners do not cover them (OWNER 2026-11-15: the game's HUD spread over the wide phone screen).
    static int hud_mode = -1, fe_stretch = -1;
    // RN_FESIDE=0 (web/boot.js, phones): the in-race screens (pause, pre-race, results) stay in the centred 4:3 island like every other
    // menu, so the touch buttons in the margins never cover them (the pause list went under the up / down buttons, shot 2026-11-15).
    static int fe_side_on;
    if (hud_mode < 0) { const char *e = getenv("RN_HUD"), *fs = getenv("RN_FESIDE"); hud_mode = !e ? 0 : !strcmp(e, "169") ? 1 : !strcmp(e, "43") ? 2 : 0; fe_side_on = !(fs && *fs == '0'); }
    float hud_in = 2.f * (float)input_hud_inset() / 1000.f;
    if (fe_stretch < 0) { const char *e = getenv("RN_FE"); fe_stretch = e && !strcmp(e, "stretch"); }
    if (isl && !race && fe_stretch) {
        float S = 4.f * rn_screen_h / (3.f * rn_screen_w);
        for (int k = 0; k < 4; k++) { uint32_t b = ld(c, ARG(3) + 32 * k, 4); float y; memcpy(&y, &b, 4); y /= S; memcpy(&b, &y, 4); st(c, ARG(3) + 32 * k, b, 4); }
        moved = 1;
    }
    if ((hud || (screen && fe_side_on)) && hud_mode != 2) {
        float S = 4.f * rn_screen_h / (3.f * rn_screen_w), x[4], cx = 0, B = hud_mode == 1 && S * 4 / 3 < 1 ? S * 4 / 3 : 1;
        float u0 = 1e9f, u1 = -1e9f;
        for (int k = 0; k < 4; k++) {
            uint32_t b = ld(c, ARG(3) + 32 * k, 4); memcpy(&x[k], &b, 4); cx += x[k] / 4;
            float u = (x[k] + S) / (2 * S) * 640.f; if (u < u0) u0 = u; if (u > u1) u1 = u;
        }
        int full = u0 <= 1.f && u1 >= 639.f;
        // Items parked off screen (the menu's unused strings at x < 0) were cut by the original's scissor: not part of the box.
        if (fen && !full && u1 > 0 && u0 < 640) fe_grow(fen->pkg, u0 < 0 ? 0 : u0, u1 > 640 ? 640 : u1);
        if (fen && dev.frames == fe_log_at && !fen->hud)
            rn_log("FELOG   quad obj %08x pkg %.24s %.0f..%.0f%s", feo, G(ld(c, fen->pkg + 0xc, 4)), u0, u1, full ? " full" : "");
        float u = (cx + S) / (2 * S) * 640.f, d = 0, m = 1;
        float Bi = B - hud_in > S ? B - hud_in : S;   // where the side groups stop; a full layer still covers the window (B)
        if (hud) d = u < 0 || u > 640 ? 0 : u < 190 ? -(Bi - S) : u > 430 ? Bi - S : 0;
        else if (full) m = B / S;
        else if (u1 <= 0 || u0 >= 640) d = -4;   // parked off the 640 screen: moving the package would bring it into view, so cut it
        else d = (float)fe_side(fen->pkg) * (Bi - S);
        if (d != 0 || m != 1) {
            for (int k = 0; k < 4; k++) { float y = x[k] * m + d; uint32_t b; memcpy(&b, &y, 4); st(c, ARG(3) + 32 * k, b, 4); }
            moved = 1;
        }
    }
    uint32_t s_rs = dev.rs[174], s_sc[4];
    memcpy(s_sc, dev.scissor, 16);
    // A 2D-only frame (no indexed draw yet: loading and title screens) has nothing under the margins of the 4:3 island, so they
    // kept the last 3D frame (the garage behind the loading screen). The original at 4:3 has no margins: they are black.
    static uint32_t margin_frame = ~0u;
    if (isl && !hud && !(dip_frame == dev.frames && dip_n > 0) && margin_frame != dev.frames) {
        margin_frame = dev.frames;
        uint32_t iw = (uint32_t)rn_screen_h * 4 / 3, x0 = ((uint32_t)rn_screen_w - iw) / 2;
        uint32_t m[2][4] = {{0, 0, x0, (uint32_t)rn_screen_h}, {x0 + iw, 0, (uint32_t)rn_screen_w, (uint32_t)rn_screen_h}};
        for (int k = 0; k < 2; k++) {
            uint32_t w[10] = {rt->gpu, 0, 1, 0xff000000u, 0, 0, m[k][0], m[k][1], m[k][2], m[k][3]};
            gpu_cmd(GPU_CLEAR, 10, w);
        }
    }
    if (isl && !moved) {
        uint32_t iw = (uint32_t)rn_screen_h * 4 / 3, x0 = ((uint32_t)rn_screen_w - iw) / 2;
        dev.rs[174] = 1; dev.scissor[0] = x0; dev.scissor[1] = 0; dev.scissor[2] = x0 + iw; dev.scissor[3] = (uint32_t)rn_screen_h;
    }
    draw_cmd(c, ARG(1), ARG(2), ARG(3), ARG(4), 0, 0, 0, 0, 0);
    if (isl && !moved) { dev.rs[174] = s_rs; memcpy(dev.scissor, s_sc, 16); }
    dev.stream[0].vb = 0; dev.stream[0].off = 0; dev.stream[0].stride = 0;
    return D3D_OK;
}
// DrawIndexedPrimitiveUP(Type, MinVertexIndex, NumVertices, PrimitiveCount, pIndexData, IndexDataFormat,
// pVertexStreamZeroData, VertexStreamZeroStride)
static uint32_t IDirect3DDevice9_DrawIndexedPrimitiveUP(Ctx *c) {
    DEV();
    if (!prim_ok(ARG(1), ARG(4)) || !ARG(5) || !ARG(7) || !ARG(8) || (ARG(6) != F_INDEX16 && ARG(6) != F_INDEX32))
        return D3DERR_INVALIDCALL;
    draw_cmd(c, ARG(1), ARG(4), ARG(7), ARG(8), ARG(2), ARG(3), ARG(5), ARG(6) == F_INDEX32, 0);
    dev.stream[0].vb = 0; dev.stream[0].off = 0; dev.stream[0].stride = 0;
    dev.ib = 0;
    return D3D_OK;
}

// ---- state blocks ---------------------------------------------------------------------------------
static uint32_t guest_of(uint32_t k1) { return k1 ? objs[k1 - 1].guest : 0; }
static uint32_t IDirect3DDevice9_BeginStateBlock(Ctx *c) {
    DEV();
    if (dev.recording) return D3DERR_INVALIDCALL;
    dev.recording = 1;
    dev.nrec = 0;
    return D3D_OK;
}
static uint32_t IDirect3DDevice9_EndStateBlock(Ctx *c) {
    DEV();
    if (!dev.recording || !ARG(1)) return D3DERR_INVALIDCALL;
    dev.recording = 0;
    uint32_t g = new_obj(c, I_SB);
    Obj *o = &objs[top];
    o->rec = malloc(sizeof(Rec) * (dev.nrec ? dev.nrec : 1));
    memcpy(o->rec, dev.rec, sizeof(Rec) * dev.nrec);
    o->nrec = dev.nrec;
    TR("EndStateBlock: %u calls -> %08x", dev.nrec, g);
    st(c, ARG(1), g, 4);
    return D3D_OK;
}
// Apply replays the recorded calls through their handlers on a scratch frame below the stack.
static uint32_t IDirect3DStateBlock9_Apply(Ctx *c) {
    SELF(I_SB);
    if (dev.recording) return D3DERR_INVALIDCALL;
    uint32_t sp = c->r[ESP];
    for (uint32_t k = 0; k < o->nrec && !c->halt; k++) {
        Rec *r = &o->rec[k];
        c->r[ESP] = sp - 64;
        for (uint32_t i = 0; i < r->n; i++) st(c, c->r[ESP] + 4 + 4 * i, r->a[i], 4);
        r->fn(c);
    }
    c->r[ESP] = sp;
    return D3D_OK;
}
// Capture refreshes the recorded values from the device's current state.
static uint32_t IDirect3DStateBlock9_Capture(Ctx *c) {
    SELF(I_SB);
    if (dev.recording) return D3DERR_INVALIDCALL;
    for (uint32_t k = 0; k < o->nrec; k++) {
        Rec *r = &o->rec[k];
        uint32_t *a = r->a, d = r->pidx >= 0 ? a[r->pidx] : 0;
        if (r->fn == IDirect3DDevice9_SetRenderState) a[2] = dev.rs[a[1]];
        else if (r->fn == IDirect3DDevice9_SetTextureStageState) a[3] = dev.tss[a[1]][a[2]];
        else if (r->fn == IDirect3DDevice9_SetSamplerState) a[3] = dev.ss[a[1]][a[2]];
        else if (r->fn == IDirect3DDevice9_SetTransform) memcpy(G(d), dev.xf[a[1]], 64);
        else if (r->fn == IDirect3DDevice9_SetViewport) memcpy(G(d), &dev.vp, 24);
        else if (r->fn == IDirect3DDevice9_SetVertexDeclaration) a[1] = guest_of(dev.decl);
        else if (r->fn == IDirect3DDevice9_SetFVF) a[1] = dev.fvf;
        else if (r->fn == IDirect3DDevice9_SetVertexShader) a[1] = guest_of(dev.vs);
        else if (r->fn == IDirect3DDevice9_SetPixelShader) a[1] = guest_of(dev.ps);
        else if (r->fn == IDirect3DDevice9_SetIndices) a[1] = guest_of(dev.ib);
        else if (r->fn == IDirect3DDevice9_SetTexture) a[2] = guest_of(dev.tex[a[1]]);
        else if (r->fn == IDirect3DDevice9_SetStreamSource) {
            a[2] = guest_of(dev.stream[a[1]].vb); a[3] = dev.stream[a[1]].off; a[4] = dev.stream[a[1]].stride;
        }
        else if (r->fn == IDirect3DDevice9_SetVertexShaderConstantF) memcpy(G(d), dev.vsf[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetVertexShaderConstantI) memcpy(G(d), dev.vsi[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetVertexShaderConstantB) memcpy(G(d), &dev.vsb[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetPixelShaderConstantF) memcpy(G(d), dev.psf[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetPixelShaderConstantI) memcpy(G(d), dev.psi[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetPixelShaderConstantB) memcpy(G(d), &dev.psb[a[1]], r->bytes);
        else if (r->fn == IDirect3DDevice9_SetMaterial) memcpy(G(d), dev.material, 68);
        else if (r->fn == IDirect3DDevice9_SetLight) memcpy(G(d), dev.light[a[1]], 104);
        else if (r->fn == IDirect3DDevice9_LightEnable) a[2] = dev.light_on[a[1]];
        else if (r->fn == IDirect3DDevice9_SetClipPlane) memcpy(G(d), dev.clip[a[1]], 16);
        else if (r->fn == IDirect3DDevice9_SetScissorRect) memcpy(G(d), dev.scissor, 16);
        else if (r->fn != IDirect3DDevice9_SetStreamSourceFreq) { rn_halt(c, "d3d9: StateBlock Capture of a call it cannot read back"); return D3DERR_INVALIDCALL; }
    }
    return D3D_OK;
}

// ---- queries ----------------------------------------------------------------------------------
// R300: event (8) and occlusion (9) queries.
static uint32_t IDirect3DDevice9_CreateQuery(Ctx *c) {
    DEV();
    uint32_t type = ARG(1), out = ARG(2);
    uint32_t r = type == 8 || type == 9 ? D3D_OK : D3DERR_NOTAVAILABLE;
    TR("CreateQuery(%u) -> %08x", type, r);
    if (r || !out) return r;
    uint32_t g = new_obj(c, I_QUERY);
    objs[top].type = type;
    st(c, out, g, 4);
    return D3D_OK;
}

// ---- surfaces -------------------------------------------------------------------------------
static uint32_t IDirect3DSurface9_GetDesc(Ctx *c) { SELF(I_SURFACE); surface_desc(c, o, ARG(1)); return D3D_OK; }

#define DEV_ENTRY(name, n) {"d3d9.dll", "IDirect3DDevice9::" #name, n, IDirect3DDevice9_##name}
#define D3D_ENTRY(name, n) {"d3d9.dll", "IDirect3D9::" #name, n, IDirect3D9_##name}
#define UNK_ENTRIES(iface) {"d3d9.dll", iface "::QueryInterface", 3, unk_QueryInterface}, \
    {"d3d9.dll", iface "::AddRef", 1, unk_AddRef}, {"d3d9.dll", iface "::Release", 1, unk_Release}
const Api d3d9_apis[] = {
    {"d3d9.dll", "Direct3DCreate9", 1, Direct3DCreate9_},
    {"d3d9.dll", "Direct3DShaderValidatorCreate9", 0, Direct3DShaderValidatorCreate9_},
    {"d3d9.dll", "DebugSetMute", 0, DebugSetMute_},
    UNK_ENTRIES("IDirect3D9"), UNK_ENTRIES("IDirect3DDevice9"), UNK_ENTRIES("IDirect3DSurface9"),
    UNK_ENTRIES("IDirect3DTexture9"), UNK_ENTRIES("IDirect3DCubeTexture9"), UNK_ENTRIES("IDirect3DVertexBuffer9"),
    UNK_ENTRIES("IDirect3DIndexBuffer9"), UNK_ENTRIES("IDirect3DSwapChain9"),
    D3D_ENTRY(GetAdapterCount, 1), D3D_ENTRY(GetAdapterIdentifier, 4), D3D_ENTRY(GetAdapterModeCount, 3),
    D3D_ENTRY(EnumAdapterModes, 5), D3D_ENTRY(GetAdapterDisplayMode, 3), D3D_ENTRY(CheckDeviceType, 6),
    D3D_ENTRY(CheckDeviceFormat, 7), D3D_ENTRY(CheckDeviceMultiSampleType, 7), D3D_ENTRY(CheckDepthStencilMatch, 6),
    D3D_ENTRY(GetDeviceCaps, 4), D3D_ENTRY(GetAdapterMonitor, 2), D3D_ENTRY(CreateDevice, 7),
    DEV_ENTRY(TestCooperativeLevel, 1), DEV_ENTRY(Reset, 2), DEV_ENTRY(GetAvailableTextureMem, 1), DEV_ENTRY(GetDirect3D, 2),
    DEV_ENTRY(GetDeviceCaps, 2), DEV_ENTRY(GetDisplayMode, 3), DEV_ENTRY(GetBackBuffer, 5),
    DEV_ENTRY(GetRenderTarget, 3), DEV_ENTRY(GetDepthStencilSurface, 2), DEV_ENTRY(BeginScene, 1),
    DEV_ENTRY(EndScene, 1), DEV_ENTRY(Clear, 7), DEV_ENTRY(Present, 5), DEV_ENTRY(SetRenderState, 3),
    DEV_ENTRY(GetRenderState, 3), DEV_ENTRY(SetTextureStageState, 4), DEV_ENTRY(GetTextureStageState, 4),
    DEV_ENTRY(SetSamplerState, 4), DEV_ENTRY(GetSamplerState, 4), DEV_ENTRY(SetTransform, 3),
    DEV_ENTRY(GetTransform, 3), DEV_ENTRY(SetViewport, 2), DEV_ENTRY(GetViewport, 2),
    DEV_ENTRY(CreateTexture, 9), DEV_ENTRY(CreateCubeTexture, 8), DEV_ENTRY(CreateVertexBuffer, 7), DEV_ENTRY(CreateIndexBuffer, 7),
    DEV_ENTRY(CreateRenderTarget, 9), DEV_ENTRY(CreateDepthStencilSurface, 9), DEV_ENTRY(CreateOffscreenPlainSurface, 7),
    DEV_ENTRY(SetRenderTarget, 3), DEV_ENTRY(SetDepthStencilSurface, 2), DEV_ENTRY(CreateVertexDeclaration, 3),
    DEV_ENTRY(CreateVertexShader, 3), DEV_ENTRY(CreatePixelShader, 3), DEV_ENTRY(SetVertexDeclaration, 2),
    DEV_ENTRY(GetVertexDeclaration, 2), DEV_ENTRY(SetFVF, 2), DEV_ENTRY(GetFVF, 2), DEV_ENTRY(SetVertexShader, 2),
    DEV_ENTRY(GetVertexShader, 2), DEV_ENTRY(SetPixelShader, 2), DEV_ENTRY(GetPixelShader, 2), DEV_ENTRY(SetIndices, 2),
    DEV_ENTRY(GetIndices, 2), DEV_ENTRY(SetTexture, 3), DEV_ENTRY(GetTexture, 3), DEV_ENTRY(SetStreamSource, 5),
    DEV_ENTRY(GetStreamSource, 5), DEV_ENTRY(SetStreamSourceFreq, 3), DEV_ENTRY(SetVertexShaderConstantF, 4),
    DEV_ENTRY(GetVertexShaderConstantF, 4), DEV_ENTRY(SetVertexShaderConstantI, 4), DEV_ENTRY(SetVertexShaderConstantB, 4),
    DEV_ENTRY(SetPixelShaderConstantF, 4), DEV_ENTRY(GetPixelShaderConstantF, 4), DEV_ENTRY(SetPixelShaderConstantI, 4),
    DEV_ENTRY(SetPixelShaderConstantB, 4), DEV_ENTRY(SetMaterial, 2), DEV_ENTRY(GetMaterial, 2), DEV_ENTRY(SetLight, 3),
    DEV_ENTRY(GetLight, 3), DEV_ENTRY(LightEnable, 3), DEV_ENTRY(GetLightEnable, 3), DEV_ENTRY(SetClipPlane, 3),
    DEV_ENTRY(GetClipPlane, 3), DEV_ENTRY(SetScissorRect, 2), DEV_ENTRY(GetScissorRect, 2), DEV_ENTRY(ValidateDevice, 2),
    DEV_ENTRY(EvictManagedResources, 1), DEV_ENTRY(ShowCursor, 2), DEV_ENTRY(SetCursorPosition, 4),
    DEV_ENTRY(SetGammaRamp, 4), DEV_ENTRY(GetGammaRamp, 3), DEV_ENTRY(CreateQuery, 3),
    DEV_ENTRY(BeginStateBlock, 1), DEV_ENTRY(EndStateBlock, 2), DEV_ENTRY(DrawPrimitive, 4),
    DEV_ENTRY(DrawIndexedPrimitive, 7), DEV_ENTRY(DrawPrimitiveUP, 5), DEV_ENTRY(DrawIndexedPrimitiveUP, 9),
    {"d3d9.dll", "IDirect3DStateBlock9::Apply", 1, IDirect3DStateBlock9_Apply},
    {"d3d9.dll", "IDirect3DStateBlock9::Capture", 1, IDirect3DStateBlock9_Capture},
    {"d3d9.dll", "IDirect3DSurface9::GetDesc", 2, IDirect3DSurface9_GetDesc},
    {"d3d9.dll", "IDirect3DSurface9::LockRect", 4, IDirect3DSurface9_LockRect},
    {"d3d9.dll", "IDirect3DSurface9::UnlockRect", 1, IDirect3DSurface9_UnlockRect},
    {"d3d9.dll", "IDirect3DTexture9::GetLevelCount", 1, IDirect3DTexture9_GetLevelCount},
    {"d3d9.dll", "IDirect3DTexture9::GetLevelDesc", 3, IDirect3DTexture9_GetLevelDesc},
    {"d3d9.dll", "IDirect3DTexture9::GetSurfaceLevel", 3, IDirect3DTexture9_GetSurfaceLevel},
    {"d3d9.dll", "IDirect3DTexture9::LockRect", 5, IDirect3DTexture9_LockRect},
    {"d3d9.dll", "IDirect3DTexture9::UnlockRect", 2, IDirect3DTexture9_UnlockRect},
    {"d3d9.dll", "IDirect3DTexture9::GetType", 1, IDirect3DTexture9_GetType},
    {"d3d9.dll", "IDirect3DTexture9::PreLoad", 1, IDirect3DTexture9_PreLoad},
    {"d3d9.dll", "IDirect3DCubeTexture9::GetLevelCount", 1, IDirect3DCubeTexture9_GetLevelCount},
    {"d3d9.dll", "IDirect3DCubeTexture9::GetLevelDesc", 3, IDirect3DCubeTexture9_GetLevelDesc},
    {"d3d9.dll", "IDirect3DCubeTexture9::GetCubeMapSurface", 4, IDirect3DCubeTexture9_GetCubeMapSurface},
    {"d3d9.dll", "IDirect3DCubeTexture9::LockRect", 6, IDirect3DCubeTexture9_LockRect},
    {"d3d9.dll", "IDirect3DCubeTexture9::UnlockRect", 3, IDirect3DCubeTexture9_UnlockRect},
    {"d3d9.dll", "IDirect3DCubeTexture9::GetType", 1, IDirect3DCubeTexture9_GetType},
    {"d3d9.dll", "IDirect3DCubeTexture9::PreLoad", 1, IDirect3DCubeTexture9_PreLoad},
    {"d3d9.dll", "IDirect3DVertexBuffer9::Lock", 5, IDirect3DVertexBuffer9_Lock},
    {"d3d9.dll", "IDirect3DVertexBuffer9::Unlock", 1, IDirect3DVertexBuffer9_Unlock},
    {"d3d9.dll", "IDirect3DVertexBuffer9::GetDesc", 2, IDirect3DVertexBuffer9_GetDesc},
    {"d3d9.dll", "IDirect3DIndexBuffer9::Lock", 5, IDirect3DIndexBuffer9_Lock},
    {"d3d9.dll", "IDirect3DIndexBuffer9::Unlock", 1, IDirect3DIndexBuffer9_Unlock},
    {"d3d9.dll", "IDirect3DIndexBuffer9::GetDesc", 2, IDirect3DIndexBuffer9_GetDesc},
    {"d3d9.dll", "IDirect3DVertexDeclaration9::GetDeclaration", 3, IDirect3DVertexDeclaration9_GetDeclaration},
    {"d3d9.dll", "IDirect3DVertexShader9::GetFunction", 3, IDirect3DVertexShader9_GetFunction},
    {"d3d9.dll", "IDirect3DPixelShader9::GetFunction", 3, IDirect3DPixelShader9_GetFunction},
    UNK_ENTRIES("IDirect3DVertexDeclaration9"), UNK_ENTRIES("IDirect3DVertexShader9"),
    UNK_ENTRIES("IDirect3DPixelShader9"), UNK_ENTRIES("IDirect3DStateBlock9"), UNK_ENTRIES("IDirect3DQuery9"),
};
const int d3d9_api_count = sizeof d3d9_apis / sizeof d3d9_apis[0];
