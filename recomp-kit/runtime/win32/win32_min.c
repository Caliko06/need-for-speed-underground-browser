// Minimal reusable Win32 runtime (kernel32 + user32 + msvcrt) for recomp-kit.
#include "../core/dispatch.h"
#include <stdio.h>
#include <string.h>

static uint32_t g_last_error = 0;
static uint32_t g_tick = 1000;
static uint32_t g_tls[64];
static uint32_t g_tls_next = 1;
static uint32_t g_cmdline_va = 0;

static const char *guest_cstr(Ctx *c, uint32_t va) {
    if (va < LOW || va >= c->memsz) return "";
    return (const char *)(c->mem + va);
}

// ---- KERNEL32 ----
static void api_GetStdHandle(Ctx *c) {
    uint32_t which = rn_arg(c, 0);
    // STD_OUTPUT_HANDLE = -11 (0xFFFFFFF5), STD_ERROR_HANDLE = -12 (0xFFFFFFF4)
    rn_stdcall_ret(c, 1, which == 0xFFFFFFF5u ? 0x101u : (which == 0xFFFFFFF4u ? 0x102u : 0x100u));
}

static void api_WriteFile(Ctx *c) {
    uint32_t h = rn_arg(c, 0);
    uint32_t buf = rn_arg(c, 1);
    uint32_t len = rn_arg(c, 2);
    uint32_t written_va = rn_arg(c, 3);
    (void)h;
    if (buf >= LOW && buf + len <= c->memsz) {
        rn_stdout_append((const char *)(c->mem + buf), len);
        if (written_va >= LOW && written_va + 4 <= c->memsz) {
            st(c, written_va, len, 4);
        }
        rn_stdcall_ret(c, 5, 1);
    } else {
        rn_stdcall_ret(c, 5, 0);
    }
}

static void api_WriteConsoleA(Ctx *c) {
    api_WriteFile(c);
}

static void api_ExitProcess(Ctx *c) {
    uint32_t code = rn_arg(c, 0);
    rn_exit_process(c, code);
    rn_stdcall_ret(c, 1, 0);
}

static void api_GetProcessHeap(Ctx *c) { rn_stdcall_ret(c, 0, 0x00CAFE01u); }

static void api_HeapAlloc(Ctx *c) {
    uint32_t flags = rn_arg(c, 1);
    uint32_t sz = rn_arg(c, 2);
    uint32_t ptr = rn_heap_alloc(c, sz, (flags & 8u) != 0);
    rn_stdcall_ret(c, 3, ptr);
}

static void api_HeapFree(Ctx *c) {
    rn_heap_free(c, rn_arg(c, 2));
    rn_stdcall_ret(c, 3, 1);
}

static void api_VirtualAlloc(Ctx *c) {
    uint32_t sz = rn_arg(c, 1);
    uint32_t ptr = rn_heap_alloc(c, sz, 1);
    rn_stdcall_ret(c, 4, ptr);
}

static void api_VirtualFree(Ctx *c) { rn_stdcall_ret(c, 3, 1); }

static void api_GetLastError(Ctx *c) { rn_stdcall_ret(c, 0, g_last_error); }
static void api_SetLastError(Ctx *c) { g_last_error = rn_arg(c, 0); rn_stdcall_ret(c, 1, 0); }

static void api_GetTickCount(Ctx *c) { g_tick += 16; rn_stdcall_ret(c, 0, g_tick); }

static void api_QueryPerformanceFrequency(Ctx *c) {
    uint32_t va = rn_arg(c, 0);
    if (va >= LOW && va + 8 <= c->memsz) st64(c, va, 1000000ull);
    rn_stdcall_ret(c, 1, 1);
}

static void api_QueryPerformanceCounter(Ctx *c) {
    uint32_t va = rn_arg(c, 0);
    g_tick += 100;
    if (va >= LOW && va + 8 <= c->memsz) st64(c, va, (uint64_t)g_tick * 1000ull);
    rn_stdcall_ret(c, 1, 1);
}

static void api_GetCurrentProcessId(Ctx *c) { rn_stdcall_ret(c, 0, 1337u); }
static void api_GetCurrentThreadId(Ctx *c)  { rn_stdcall_ret(c, 0, 1u); }
static void api_GetVersion(Ctx *c)          { rn_stdcall_ret(c, 0, 0x0A280105u); } // WinXP SP2

static void api_GetCommandLineA(Ctx *c) {
    if (!g_cmdline_va) {
        g_cmdline_va = rn_heap_alloc(c, 64, 1);
        if (g_cmdline_va) strcpy((char *)(c->mem + g_cmdline_va), "app.exe");
    }
    rn_stdcall_ret(c, 0, g_cmdline_va);
}

static void api_GetModuleHandleA(Ctx *c) {
    uint32_t nm = rn_arg(c, 0);
    rn_stdcall_ret(c, 1, nm == 0 ? 0x00400000u : 0x10000000u);
}

static void api_OutputDebugStringA(Ctx *c) {
    rn_stdout_puts(guest_cstr(c, rn_arg(c, 0)));
    rn_stdcall_ret(c, 1, 0);
}

static void api_lstrlenA(Ctx *c) {
    rn_stdcall_ret(c, 1, (uint32_t)strlen(guest_cstr(c, rn_arg(c, 0))));
}

static void api_TlsAlloc(Ctx *c) {
    uint32_t idx = (g_tls_next < 64) ? g_tls_next++ : 0xFFFFFFFFu;
    rn_stdcall_ret(c, 0, idx);
}
static void api_TlsGetValue(Ctx *c) {
    uint32_t idx = rn_arg(c, 0);
    rn_stdcall_ret(c, 1, idx < 64 ? g_tls[idx] : 0);
}
static void api_TlsSetValue(Ctx *c) {
    uint32_t idx = rn_arg(c, 0), val = rn_arg(c, 1);
    if (idx < 64) g_tls[idx] = val;
    rn_stdcall_ret(c, 2, idx < 64 ? 1 : 0);
}
static void api_InitializeCriticalSection(Ctx *c) { rn_stdcall_ret(c, 1, 0); }
static void api_EnterCriticalSection(Ctx *c)      { rn_stdcall_ret(c, 1, 0); }
static void api_LeaveCriticalSection(Ctx *c)      { rn_stdcall_ret(c, 1, 0); }
static void api_DeleteCriticalSection(Ctx *c)     { rn_stdcall_ret(c, 1, 0); }

// ---- USER32 ----
static void api_MessageBoxA(Ctx *c) {
    uint32_t text_va = rn_arg(c, 1);
    uint32_t title_va = rn_arg(c, 2);
    uint32_t flags = rn_arg(c, 3);
    rn_msgbox_record(guest_cstr(c, title_va), guest_cstr(c, text_va), flags);
    rn_stdcall_ret(c, 4, 1u); // IDOK
}

// ---- MSVCRT (cdecl) ----
static void api_puts(Ctx *c) {
    rn_stdout_puts(guest_cstr(c, rn_arg(c, 0)));
    rn_stdout_puts("\n");
    rn_cdecl_ret(c, 0);
}
static void api_malloc(Ctx *c) { rn_cdecl_ret(c, rn_heap_alloc(c, rn_arg(c, 0), 0)); }
static void api_free(Ctx *c)   { rn_heap_free(c, rn_arg(c, 0)); rn_cdecl_ret(c, 0); }
static void api_exit(Ctx *c)   { rn_exit_process(c, rn_arg(c, 0)); rn_cdecl_ret(c, 0); }

void rn_register_win32_min(void) {
    rn_register_api("kernel32.dll", "GetStdHandle", api_GetStdHandle);
    rn_register_api("kernel32.dll", "WriteFile", api_WriteFile);
    rn_register_api("kernel32.dll", "WriteConsoleA", api_WriteConsoleA);
    rn_register_api("kernel32.dll", "ExitProcess", api_ExitProcess);
    rn_register_api("kernel32.dll", "GetProcessHeap", api_GetProcessHeap);
    rn_register_api("kernel32.dll", "HeapAlloc", api_HeapAlloc);
    rn_register_api("kernel32.dll", "HeapFree", api_HeapFree);
    rn_register_api("kernel32.dll", "VirtualAlloc", api_VirtualAlloc);
    rn_register_api("kernel32.dll", "VirtualFree", api_VirtualFree);
    rn_register_api("kernel32.dll", "GetLastError", api_GetLastError);
    rn_register_api("kernel32.dll", "SetLastError", api_SetLastError);
    rn_register_api("kernel32.dll", "GetTickCount", api_GetTickCount);
    rn_register_api("kernel32.dll", "QueryPerformanceFrequency", api_QueryPerformanceFrequency);
    rn_register_api("kernel32.dll", "QueryPerformanceCounter", api_QueryPerformanceCounter);
    rn_register_api("kernel32.dll", "GetCurrentProcessId", api_GetCurrentProcessId);
    rn_register_api("kernel32.dll", "GetCurrentThreadId", api_GetCurrentThreadId);
    rn_register_api("kernel32.dll", "GetVersion", api_GetVersion);
    rn_register_api("kernel32.dll", "GetCommandLineA", api_GetCommandLineA);
    rn_register_api("kernel32.dll", "GetModuleHandleA", api_GetModuleHandleA);
    rn_register_api("kernel32.dll", "OutputDebugStringA", api_OutputDebugStringA);
    rn_register_api("kernel32.dll", "lstrlenA", api_lstrlenA);
    rn_register_api("kernel32.dll", "TlsAlloc", api_TlsAlloc);
    rn_register_api("kernel32.dll", "TlsGetValue", api_TlsGetValue);
    rn_register_api("kernel32.dll", "TlsSetValue", api_TlsSetValue);
    rn_register_api("kernel32.dll", "InitializeCriticalSection", api_InitializeCriticalSection);
    rn_register_api("kernel32.dll", "EnterCriticalSection", api_EnterCriticalSection);
    rn_register_api("kernel32.dll", "LeaveCriticalSection", api_LeaveCriticalSection);
    rn_register_api("kernel32.dll", "DeleteCriticalSection", api_DeleteCriticalSection);
    rn_register_api("user32.dll",   "MessageBoxA", api_MessageBoxA);
    rn_register_api("msvcrt.dll",   "puts", api_puts);
    rn_register_api("msvcrt.dll",   "malloc", api_malloc);
    rn_register_api("msvcrt.dll",   "free", api_free);
    rn_register_api("msvcrt.dll",   "exit", api_exit);
}
