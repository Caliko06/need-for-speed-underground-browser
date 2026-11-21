// Target-agnostic PE32 loader, dynamic API registry, indirect call dispatcher, and live trace/coverage.
#include "dispatch.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

extern const uint32_t rn_fn_count;
extern const uint32_t rn_fn_addr[];
extern void (*const rn_fn_ptr[])(Ctx *);

volatile int rn_preempt = 0;
void gil_preempt(void) { rn_preempt = 0; }

// Coverage map indexed by lifted function index (RN_COV=1).
uint8_t rn_cov_map[65536];

// ---- Registered OS APIs ----
#define MAX_APIS 512
typedef struct {
    char dll[48];
    char name[96];
    RnApiFn fn;
} ApiEntry;

static ApiEntry g_apis[MAX_APIS];
static int g_api_count = 0;

// ---- Synthetic IAT thunk table ----
// Thunk addresses live in [THUNK_BASE, THUNK_BASE + MAX_THUNKS * 4).
#define THUNK_BASE 0x0FF00000u
#define MAX_THUNKS 2048
typedef struct {
    char dll[48];
    char name[96];
    RnApiFn fn; // NULL if stubbed
} ThunkSlot;

static ThunkSlot g_thunks[MAX_THUNKS];
static int g_thunk_count = 0;

// ---- Live API call trace ----
#define MAX_TRACE 256
typedef struct {
    char dll[48];
    char name[96];
    uint32_t caller;
    uint32_t args[4];
    uint32_t retval;
    int implemented;
} TraceRec;

static TraceRec g_trace[MAX_TRACE];
static int g_trace_count = 0;

// ---- Captured stdout & MessageBox ----
static char g_stdout[65536];
static size_t g_stdout_len = 0;

#define MAX_MSGBOX 16
typedef struct {
    char title[128];
    char text[512];
    uint32_t flags;
} MsgBoxRec;
static MsgBoxRec g_msgboxes[MAX_MSGBOX];
static int g_msgbox_count = 0;

// ---- Guest bump heap ----
static uint32_t g_heap_base = 0x04000000u;
static uint32_t g_heap_cur  = 0x04000000u;
static uint32_t g_heap_end  = 0x0E000000u;

// ---- Run state ----
static uint32_t g_exit_code = 0;
static int      g_exited = 0;
static uint32_t g_halt = 0;
static uint32_t g_halt_at = 0;
static char     g_halt_why[128];
static uint32_t g_entry_va = 0;
static uint64_t g_call_count = 0;
static uint64_t g_rdtsc_val = 1000000;

static int strcasecmp_ascii(const char *a, const char *b) {
    while (*a && *b) {
        int ca = tolower((unsigned char)*a++);
        int cb = tolower((unsigned char)*b++);
        if (ca != cb) return ca - cb;
    }
    return tolower((unsigned char)*a) - tolower((unsigned char)*b);
}

void rn_register_api(const char *dll, const char *name, RnApiFn fn) {
    for (int i = 0; i < g_api_count; i++) {
        if (strcasecmp_ascii(g_apis[i].dll, dll) == 0 && strcmp(g_apis[i].name, name) == 0) {
            g_apis[i].fn = fn;
            return;
        }
    }
    if (g_api_count >= MAX_APIS) return;
    snprintf(g_apis[g_api_count].dll, sizeof(g_apis[0].dll), "%s", dll);
    snprintf(g_apis[g_api_count].name, sizeof(g_apis[0].name), "%s", name);
    g_apis[g_api_count].fn = fn;
    g_api_count++;
}

static RnApiFn find_api(const char *dll, const char *name) {
    for (int i = 0; i < g_api_count; i++) {
        if (strcasecmp_ascii(g_apis[i].dll, dll) == 0 && strcmp(g_apis[i].name, name) == 0)
            return g_apis[i].fn;
    }
    return NULL;
}

uint32_t rn_heap_alloc(Ctx *c, uint32_t size, int zero) {
    if (size == 0) size = 16;
    uint32_t aligned = (size + 15u) & ~15u;
    if (g_heap_cur + aligned > g_heap_end || g_heap_cur + aligned > c->memsz)
        return 0;
    uint32_t ptr = g_heap_cur;
    g_heap_cur += aligned;
    if (zero) memset(c->mem + ptr, 0, aligned);
    return ptr;
}

void rn_heap_free(Ctx *c, uint32_t ptr) {
    (void)c; (void)ptr;
}

void rn_stdout_append(const char *data, size_t len) {
    if (!data || !len) return;
    size_t avail = sizeof(g_stdout) - 1 - g_stdout_len;
    if (len > avail) len = avail;
    memcpy(g_stdout + g_stdout_len, data, len);
    g_stdout_len += len;
    g_stdout[g_stdout_len] = '\0';
}

void rn_stdout_puts(const char *s) {
    if (!s) return;
    rn_stdout_append(s, strlen(s));
}

void rn_msgbox_record(const char *title, const char *text, uint32_t flags) {
    if (g_msgbox_count >= MAX_MSGBOX) return;
    MsgBoxRec *m = &g_msgboxes[g_msgbox_count++];
    snprintf(m->title, sizeof(m->title), "%s", title ? title : "");
    snprintf(m->text, sizeof(m->text), "%s", text ? text : "");
    m->flags = flags;
}

void rn_exit_process(Ctx *c, uint32_t code) {
    g_exit_code = code;
    g_exited = 1;
    c->halt = 1;
    c->why = "ExitProcess";
}

uint64_t rn_rdtsc(Ctx *c) {
    (void)c;
    g_rdtsc_val += 1000;
    return g_rdtsc_val;
}

void (*rn_mod_find(Ctx *c, uint32_t target, uint32_t *mb))(Ctx *) {
    (void)c; (void)target; (void)mb;
    return NULL;
}

static void (*find_lifted(uint32_t target))(Ctx *) {
    uint32_t lo = 0, hi = rn_fn_count;
    while (lo < hi) {
        uint32_t mid = lo + ((hi - lo) >> 1);
        uint32_t a = rn_fn_addr[mid];
        if (a == target) return rn_fn_ptr[mid];
        if (a < target) lo = mid + 1;
        else hi = mid;
    }
    return NULL;
}

void rn_call(Ctx *c, uint32_t target) {
    g_call_count++;
    if (g_call_count > 5000000ull) {
        c->halt = 1;
        c->halt_at = target;
        c->why = "step limit exceeded";
        return;
    }

    // 1. Check synthetic Win32 IAT thunk range
    if (target >= THUNK_BASE && target < THUNK_BASE + (uint32_t)g_thunk_count * 4u) {
        int idx = (int)((target - THUNK_BASE) >> 2);
        ThunkSlot *ts = &g_thunks[idx];
        uint32_t caller = ld(c, c->r[ESP], 4);
        uint32_t a0 = rn_arg(c, 0), a1 = rn_arg(c, 1), a2 = rn_arg(c, 2), a3 = rn_arg(c, 3);
        if (ts->fn) {
            ts->fn(c);
        } else {
            // Auto-stub: return 0 (cdecl-safe: pop return address only)
            rn_cdecl_ret(c, 0);
        }
        if (g_trace_count < MAX_TRACE) {
            TraceRec *tr = &g_trace[g_trace_count++];
            snprintf(tr->dll, sizeof(tr->dll), "%s", ts->dll);
            snprintf(tr->name, sizeof(tr->name), "%s", ts->name);
            tr->caller = caller;
            tr->args[0] = a0; tr->args[1] = a1; tr->args[2] = a2; tr->args[3] = a3;
            tr->retval = c->r[EAX];
            tr->implemented = ts->fn ? 1 : 0;
        }
        return;
    }

    // 2. Check lifted function table
    void (*fn)(Ctx *) = find_lifted(target);
    if (fn) {
        fn(c);
        return;
    }

    c->halt = 1;
    c->halt_at = target;
    c->why = "unmapped call target";
}

// ---- Minimal PE32 loader ----
static uint16_t rd16(const uint8_t *p) { uint16_t v; memcpy(&v, p, 2); return v; }
static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }

int rn_run_pe_bytes(const uint8_t *pe, size_t pe_len, uint32_t mem_mb) {
    // Reset run state
    memset(rn_cov_map, 0, sizeof(rn_cov_map));
    g_thunk_count = 0;
    g_trace_count = 0;
    g_stdout_len = 0;
    g_stdout[0] = '\0';
    g_msgbox_count = 0;
    g_exit_code = 0;
    g_exited = 0;
    g_halt = 0;
    g_halt_at = 0;
    g_halt_why[0] = '\0';
    g_call_count = 0;

    if (pe_len < 0x100 || pe[0] != 'M' || pe[1] != 'Z') {
        snprintf(g_halt_why, sizeof(g_halt_why), "invalid DOS header");
        return -1;
    }
    uint32_t pe_off = rd32(pe + 0x3c);
    if (pe_off + 24 + 96 > pe_len || memcmp(pe + pe_off, "PE\0\0", 4) != 0) {
        snprintf(g_halt_why, sizeof(g_halt_why), "invalid PE header");
        return -2;
    }
    uint16_t nsec = rd16(pe + pe_off + 6);
    uint16_t opt_sz = rd16(pe + pe_off + 20);
    const uint8_t *opt = pe + pe_off + 24;
    if (rd16(opt) != 0x010b) {
        snprintf(g_halt_why, sizeof(g_halt_why), "not PE32 (32-bit)");
        return -3;
    }
    uint32_t entry_rva = rd32(opt + 16);
    uint32_t image_base = rd32(opt + 28);
    uint32_t size_of_headers = rd32(opt + 60);
    uint32_t import_rva = rd32(opt + 96 + 8); // DataDirectory[1] = Import Table

    if (mem_mb < 64) mem_mb = 64;
    if (mem_mb > 384) mem_mb = 384;
    uint32_t memsz = mem_mb * 1024u * 1024u;
    uint8_t *mem = (uint8_t *)calloc(1, memsz);
    if (!mem) {
        snprintf(g_halt_why, sizeof(g_halt_why), "out of host memory");
        return -4;
    }

    // Copy PE headers
    if (image_base + size_of_headers < memsz && size_of_headers <= pe_len) {
        memcpy(mem + image_base, pe, size_of_headers);
    }

    // Map sections
    uint32_t max_va = image_base + size_of_headers;
    const uint8_t *sec = opt + opt_sz;
    for (uint16_t i = 0; i < nsec; i++, sec += 40) {
        if ((size_t)(sec - pe) + 40 > pe_len) break;
        uint32_t vsize = rd32(sec + 8);
        uint32_t vaddr = rd32(sec + 12);
        uint32_t rsize = rd32(sec + 16);
        uint32_t rptr  = rd32(sec + 20);
        uint32_t dst = image_base + vaddr;
        if (rsize > 0 && rptr + rsize <= pe_len && dst + rsize < memsz) {
            memcpy(mem + dst, pe + rptr, rsize);
        }
        uint32_t end_va = dst + (vsize > rsize ? vsize : rsize);
        if (end_va > max_va) max_va = end_va;
    }

    // Position heap & stack cleanly above image
    g_heap_base = (max_va + 0x00100000u) & ~0x000FFFFFu;
    if (g_heap_base < 0x01000000u) g_heap_base = 0x01000000u;
    g_heap_cur = g_heap_base;
    g_heap_end = memsz - 0x00400000u; // leave 4 MB at top for stack & TEB

    // Resolve PE Import Directory into synthetic IAT thunks
    if (import_rva != 0 && image_base + import_rva + 20 < memsz) {
        uint32_t desc_va = image_base + import_rva;
        for (int d = 0; d < 256; d++, desc_va += 20) {
            uint32_t orig_first = rd32(mem + desc_va);
            uint32_t name_rva   = rd32(mem + desc_va + 12);
            uint32_t first_thunk = rd32(mem + desc_va + 16);
            if (!orig_first && !name_rva && !first_thunk) break;
            if (!name_rva || !first_thunk) continue;
            const char *dll = (const char *)(mem + image_base + name_rva);
            uint32_t ilt_va = image_base + (orig_first ? orig_first : first_thunk);
            uint32_t iat_va = image_base + first_thunk;
            for (int k = 0; k < 1024; k++, ilt_va += 4, iat_va += 4) {
                if (ilt_va + 4 >= memsz || iat_va + 4 >= memsz) break;
                uint32_t entry = rd32(mem + ilt_va);
                if (!entry) break;
                char fn_name[96];
                if (entry & 0x80000000u) {
                    snprintf(fn_name, sizeof(fn_name), "ord_%u", entry & 0xffffu);
                } else {
                    const char *nm = (const char *)(mem + image_base + entry + 2);
                    snprintf(fn_name, sizeof(fn_name), "%s", nm);
                }
                if (g_thunk_count < MAX_THUNKS) {
                    int idx = g_thunk_count++;
                    snprintf(g_thunks[idx].dll, sizeof(g_thunks[0].dll), "%s", dll);
                    snprintf(g_thunks[idx].name, sizeof(g_thunks[0].name), "%s", fn_name);
                    g_thunks[idx].fn = find_api(dll, fn_name);
                    uint32_t thunk_va = THUNK_BASE + (uint32_t)idx * 4u;
                    memcpy(mem + iat_va, &thunk_va, 4);
                }
            }
        }
    }

    // Initialize CPU context
    Ctx ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.mem = mem;
    ctx.memsz = memsz;
    ctx.fcw = 0x037fu;
    uint32_t stack_top = memsz - 0x00020000u;
    ctx.fs = memsz - 0x00010000u; // minimal TEB page
    // Self-pointer at FS:[0x18]
    memcpy(mem + ctx.fs + 0x18, &ctx.fs, 4);
    // Sentinel return address on stack
    uint32_t sentinel = 0xDEADBEEFu;
    stack_top -= 4;
    memcpy(mem + stack_top, &sentinel, 4);
    ctx.r[ESP] = stack_top;

    g_entry_va = image_base + entry_rva;
    rn_call(&ctx, g_entry_va);

    g_halt = ctx.halt;
    g_halt_at = ctx.halt_at;
    if (ctx.why) snprintf(g_halt_why, sizeof(g_halt_why), "%s", ctx.why);
    free(mem);
    return 0;
}

const char *rn_get_stdout(void) { return g_stdout; }
uint32_t rn_get_exit_code(void) { return g_exit_code; }

// ---- JSON escaping & reporting ----
static char g_json_buf[262144];

static size_t json_append(char *dst, size_t cap, size_t pos, const char *s) {
    while (*s && pos + 1 < cap) dst[pos++] = *s++;
    dst[pos] = '\0';
    return pos;
}

static size_t json_append_escaped(char *dst, size_t cap, size_t pos, const char *s) {
    if (pos + 1 < cap) dst[pos++] = '"';
    for (; s && *s && pos + 8 < cap; s++) {
        unsigned char ch = (unsigned char)*s;
        if (ch == '"' || ch == '\\') { dst[pos++] = '\\'; dst[pos++] = (char)ch; }
        else if (ch == '\n') { dst[pos++] = '\\'; dst[pos++] = 'n'; }
        else if (ch == '\r') { dst[pos++] = '\\'; dst[pos++] = 'r'; }
        else if (ch == '\t') { dst[pos++] = '\\'; dst[pos++] = 't'; }
        else if (ch < 0x20) { pos += (size_t)snprintf(dst + pos, cap - pos, "\\u%04x", ch); }
        else { dst[pos++] = (char)ch; }
    }
    if (pos + 1 < cap) dst[pos++] = '"';
    dst[pos] = '\0';
    return pos;
}

const char *rn_last_run_json(void) {
    char tmp[512];
    size_t cap = sizeof(g_json_buf), p = 0;
    int ok = (g_exited || !g_halt) ? 1 : 0;
    snprintf(tmp, sizeof(tmp),
        "{\"ok\":%s,\"entry\":\"0x%08x\",\"exited\":%s,\"exit_code\":%u,\"halt\":%u,\"halt_at\":\"0x%08x\",\"calls\":%llu,\"halt_why\":",
        ok ? "true" : "false", g_entry_va, g_exited ? "true" : "false", g_exit_code,
        g_halt, g_halt_at, (unsigned long long)g_call_count);
    p = json_append(g_json_buf, cap, p, tmp);
    p = json_append_escaped(g_json_buf, cap, p, g_halt_why);

    p = json_append(g_json_buf, cap, p, ",\"stdout\":");
    p = json_append_escaped(g_json_buf, cap, p, g_stdout);

    p = json_append(g_json_buf, cap, p, ",\"messageboxes\":[");
    for (int i = 0; i < g_msgbox_count; i++) {
        if (i) p = json_append(g_json_buf, cap, p, ",");
        p = json_append(g_json_buf, cap, p, "{\"title\":");
        p = json_append_escaped(g_json_buf, cap, p, g_msgboxes[i].title);
        p = json_append(g_json_buf, cap, p, ",\"text\":");
        p = json_append_escaped(g_json_buf, cap, p, g_msgboxes[i].text);
        snprintf(tmp, sizeof(tmp), ",\"flags\":%u}", g_msgboxes[i].flags);
        p = json_append(g_json_buf, cap, p, tmp);
    }

    p = json_append(g_json_buf, cap, p, "],\"api_trace\":[");
    for (int i = 0; i < g_trace_count; i++) {
        TraceRec *t = &g_trace[i];
        if (i) p = json_append(g_json_buf, cap, p, ",");
        p = json_append(g_json_buf, cap, p, "{\"dll\":");
        p = json_append_escaped(g_json_buf, cap, p, t->dll);
        p = json_append(g_json_buf, cap, p, ",\"name\":");
        p = json_append_escaped(g_json_buf, cap, p, t->name);
        snprintf(tmp, sizeof(tmp),
            ",\"caller\":\"0x%08x\",\"args\":[\"0x%x\",\"0x%x\",\"0x%x\",\"0x%x\"],\"ret\":\"0x%x\",\"implemented\":%s}",
            t->caller, t->args[0], t->args[1], t->args[2], t->args[3], t->retval,
            t->implemented ? "true" : "false");
        p = json_append(g_json_buf, cap, p, tmp);
    }

    p = json_append(g_json_buf, cap, p, "],\"cov_addrs\":[");
    int first = 1;
    uint32_t limit = rn_fn_count < 65536u ? rn_fn_count : 65536u;
    for (uint32_t i = 0; i < limit; i++) {
        if (rn_cov_map[i]) {
            if (!first) p = json_append(g_json_buf, cap, p, ",");
            first = 0;
            snprintf(tmp, sizeof(tmp), "\"0x%08x\"", rn_fn_addr[i]);
            p = json_append(g_json_buf, cap, p, tmp);
        }
    }
    p = json_append(g_json_buf, cap, p, "]}");
    return g_json_buf;
}

int rn_write_cov_json(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fprintf(f, "{\"addrs\":[");
    int first = 1;
    uint32_t limit = rn_fn_count < 65536u ? rn_fn_count : 65536u;
    for (uint32_t i = 0; i < limit; i++) {
        if (rn_cov_map[i]) {
            if (!first) fputc(',', f);
            first = 0;
            fprintf(f, "\"0x%08x\"", rn_fn_addr[i]);
        }
    }
    fprintf(f, "]}\n");
    fclose(f);
    return 0;
}
