// Shader model 1 (vs_1_1, ps_1_1..1_4) bytecode: one decoder, and from it a WGSL translation (web) and
// an interpreter (the CPU backend). Token formats and instruction semantics follow the DirectX 9 docs
// ("Shader Code Format", "Asm Shader Reference"). An instruction we do not know stops loudly.
#pragma once
#include <stdint.h>

// Register types (D3DSHADER_PARAM_REGISTER_TYPE).
enum { R_TEMP = 0, R_INPUT = 1, R_CONST = 2, R_ADDR = 3, R_TEXTURE = 3, R_RASTOUT = 4, R_ATTROUT = 5,
       R_TEXCRDOUT = 6, R_CONSTINT = 7, R_COLOROUT = 8, R_DEPTHOUT = 9, R_SAMPLER = 10 };
// Opcodes (D3DSHADER_INSTRUCTION_OPCODE_TYPE) this decoder knows.
enum { OP_NOP = 0, OP_MOV, OP_ADD, OP_SUB, OP_MAD, OP_MUL, OP_RCP, OP_RSQ, OP_DP3, OP_DP4, OP_MIN, OP_MAX, OP_SLT,
       OP_SGE, OP_EXP, OP_LOG, OP_LIT, OP_DST, OP_LRP, OP_FRC, OP_M4x4, OP_M4x3, OP_M3x4, OP_M3x3, OP_M3x2,
       OP_DCL = 31, OP_TEXCOORD = 64, OP_TEXKILL, OP_TEX, OP_EXPP = 78, OP_LOGP, OP_CND, OP_DEF, OP_CMP = 88,
       OP_PHASE = 0xfffd };

typedef struct { uint8_t type, mod, swz[4]; uint16_t num; uint8_t rel; } Src;     // mod: D3DSPSM_*
typedef struct { uint8_t type, mask, sat, shift; uint16_t num; } Dst;              // shift: signed 4 bits
typedef struct { uint16_t op; uint8_t nsrc, coissue; Dst d; Src s[3]; float def[4]; uint8_t usage, uidx; } Ins;

typedef struct {
    int ps, major, minor;
    Ins *ins;
    int n;
    // Vertex inputs: v register -> D3DDECLUSAGE and index (from dcl), mask of the ones declared.
    uint8_t in_usage[16], in_index[16];
    uint16_t inputs;
    uint32_t outputs;           // vs: 1 oPos, 2 oFog, 4 oPts, 8<<k oDk, 32<<k oTk; ps: textures sampled (bit k)
    int max_const;              // highest c register read (255 with relative addressing)
    uint16_t tex_used;          // ps: t registers declared by tex/texcoord
    uint8_t defd[256];          // def: constants the shader defines (they win over the device's)
    float defs[256][4];
} Sm1;

// 0 = decoded; else *err says why (an unknown opcode or token).
int sm1_decode(Sm1 *s, const uint32_t *tok, uint32_t n, char *err, int errn);
void sm1_free(Sm1 *s);
void sm1_disasm(const Sm1 *s, void (*out)(const char *line));

// WGSL source for a shader. Bindings and varyings are fixed: the web backend builds its pipelines
// against them. Returns a malloc'd string.
//   group 0 binding 0: uniform U (layout below, SM1_U_* byte offsets), both stages.
//   group 1 binding 2k / 2k+1: sampler / texture_2d of stage k (ps); binding 16+k: texture_cube of stage k. A ps_1_x
//   tex samples the one its stage's word in u.tt says (gpu.h T_CUBE): the type comes from the bound texture.
//   vs input v<n> at @location(n); varyings: 0 oD0, 1 oD1, 2+k oTk, 10 oFog.
enum { SM1_U_PC = 0, SM1_U_HP = 128, SM1_U_FOGC = 144, SM1_U_AF = 160, SM1_U_AR = 176,
       SM1_U_TT = 192, SM1_U_VC = 224, SM1_U_SIZE = 4320 };
// mode: 0 plain; SM1_CAR_VS / SM1_CAR_PS = the car body pair of PC Speed.exe (vs 0x4728b668 / ps 0xc27f3669, token FNV hash), per-pixel lighting.
// SM1_HL_VS / SM1_HL_PS = the headlight world pairs (worldheadlight vs 0x67da8f41 / ps 0x91d5deec, worldheadlightreflect
// vs 0x102e066d / ps 0x9bb3f7c7): SM1_HL_N more projectors (host/lights.c) in oT4..oT7, from VS c16..c31.
enum { SM1_PLAIN, SM1_CAR_VS, SM1_CAR_PS, SM1_HL_VS, SM1_HL_PS };
// OR-ed into mode for the two road reflection pixel shaders (worldreflect ps 0x92e7bdab, worldheadlightreflect ps 0x9bb3f7c7):
// their weight w = texture alpha x vertex alpha goes through sm1_roadrefl()'s curve.
#define SM1_REFL 0x100
// RN_ROADREFL / ?roadrefl=: 0 game (unset), 1 sq (w^2), 2 cube (w^3), 3 off (the game's own level 1, PATCH 0x410c1b: no mirrored draw).
int sm1_roadrefl(void);
#define SM1_HL_N 4
#define SM1_HL_GAIN 0.4   // another car's headlight against the player's own (1 = as bright); subtle (OWNER 2026-10-27)
#define SM1_HL_REACH 1.5  // and shorter: its ramp read at 1.5 x depth, full to ~32 m, gone by ~65 m (the player's: 48 / 98)
char *sm1_wgsl(const Sm1 *s, int mode);

// Interpreter. A vertex: 16 inputs in, outputs out (oPos, oD0, oD1, oT0..7, oFog). A pixel: the
// interpolated colors and texture coordinates in, r0 out; sample() reads texture stage k.
typedef struct { float pos[4], d[2][4], t[8][4], fog; } VsOut;
void sm1_run_vs(const Sm1 *s, const float (*c)[4], const float in[16][4], VsOut *o);
// tt[k]: D3DTSS_TEXTURETRANSFORMFLAGS of stage k (ps_1_1..1_3 honor D3DTTFF_PROJECTED).
typedef void (*Sm1Sample)(void *ctx, int stage, const float uv[2], float out[4]);
int sm1_run_ps(const Sm1 *s, const float (*c)[4], const VsOut *in, const uint32_t *tt, Sm1Sample sample, void *ctx,
               float out[4]);  // 0 = texkill
