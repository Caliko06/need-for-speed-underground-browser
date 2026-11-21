// Dual-target entrypoint (Native CLI & WebAssembly Emscripten) for recomp-kit.
#include "dispatch.h"
#include <stdio.h>
#include <stdlib.h>

#ifdef __EMSCRIPTEN__
#include <emscripten.h>

EMSCRIPTEN_KEEPALIVE
const char *rn_wasm_run(const uint8_t *pe_bytes, uint32_t pe_len, uint32_t mem_mb) {
    rn_register_win32_min();
    rn_run_pe_bytes(pe_bytes, (size_t)pe_len, mem_mb ? mem_mb : 64u);
    return rn_last_run_json();
}
#else
int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <target.exe> [--json] [--cov-out cov.json]\n", argv[0]);
        return 2;
    }
    const char *exe_path = argv[1];
    int json_mode = 0;
    const char *cov_out = getenv("RN_COV_OUT");
    for (int i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--json") == 0) json_mode = 1;
        else if (strcmp(argv[i], "--cov-out") == 0 && i + 1 < argc) cov_out = argv[++i];
    }

    FILE *f = fopen(exe_path, "rb");
    if (!f) { perror(exe_path); return 1; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = (uint8_t *)malloc((size_t)sz);
    if (!buf || fread(buf, 1, (size_t)sz, f) != (size_t)sz) {
        fclose(f); free(buf);
        fprintf(stderr, "Failed reading %s\n", exe_path);
        return 1;
    }
    fclose(f);

    rn_register_win32_min();
    rn_run_pe_bytes(buf, (size_t)sz, 64u);
    free(buf);

    if (cov_out && *cov_out) {
        rn_write_cov_json(cov_out);
    }
    if (json_mode) {
        puts(rn_last_run_json());
    } else {
        fputs(rn_get_stdout(), stdout);
    }
    return (int)rn_get_exit_code();
}
#endif
