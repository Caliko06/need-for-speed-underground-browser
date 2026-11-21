// Target-agnostic runtime dispatch, PE32 loader, API registry, and telemetry for recomp-kit.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "rt.h"

typedef void (*RnApiFn)(Ctx *c);

// Register a host-implemented OS API (case-insensitive DLL match, exact proc name).
void rn_register_api(const char *dll, const char *name, RnApiFn fn);

// Guest memory / heap / output helpers shared by OS runtime modules.
uint32_t rn_heap_alloc(Ctx *c, uint32_t size, int zero);
void     rn_heap_free(Ctx *c, uint32_t ptr);
void     rn_stdout_append(const char *data, size_t len);
void     rn_stdout_puts(const char *s);
void     rn_msgbox_record(const char *title, const char *text, uint32_t flags);
void     rn_exit_process(Ctx *c, uint32_t code);

// Guest stack helpers (stdcall / cdecl).
static inline uint32_t rn_arg(Ctx *c, int idx) {
    return ld(c, c->r[ESP] + 4u * (uint32_t)(idx + 1), 4);
}
static inline void rn_stdcall_ret(Ctx *c, int nargs, uint32_t retval) {
    uint32_t ret = ld(c, c->r[ESP], 4);
    c->r[EAX] = retval;
    c->r[ESP] += 4u * (uint32_t)(nargs + 1);
    c->ret = ret;
}
static inline void rn_cdecl_ret(Ctx *c, uint32_t retval) {
    uint32_t ret = ld(c, c->r[ESP], 4);
    c->r[EAX] = retval;
    c->r[ESP] += 4u;
    c->ret = ret;
}

// Register minimal Win32 APIs (runtime/win32/win32_min.c).
void rn_register_win32_min(void);

// Load a PE32 binary from memory, resolve imports into synthetic thunk slots, and execute entry point.
// Returns 0 on clean exit (or normal return), non-zero on loader error.
int rn_run_pe_bytes(const uint8_t *pe, size_t pe_len, uint32_t mem_mb);

// Build a JSON summary of the last run (stdout, messageboxes, api_trace, coverage, halt info).
// Returned pointer is owned by runtime static buffer.
const char *rn_last_run_json(void);

// Accessors for native CLI runner.
const char *rn_get_stdout(void);
uint32_t    rn_get_exit_code(void);
int         rn_write_cov_json(const char *path);
