// Game file hooks that outlived WORLD (retired 2026-11-17, attic/world/README.md): split out of host/openworld.c.
// 1. The collision index loader every track uses (PATCH 0x441423, collision widened to u32, tools/recomp/patches_collision.py).
// 2. The Cars/TEXTURES.BIN overlay with DUMMY_SKIN5..12 / DUMMY_WHEEL5..12 render targets for the free mode's traffic racers (host/free.c).
// 3. The slots the main menu's MODE button jumps through (host/mode_menu.c, tools/recomp/patches_mode_menu.py).
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "host.h"

static int ci_eq(const char *a, const char *b, size_t n) {
    for (size_t k = 0; k < n; k++) if (tolower((unsigned char)a[k]) != tolower((unsigned char)b[k])) return 0;
    return 1;
}

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
// The size of a file the server has at "/<path>", -1 when it has none.
EM_JS(double, file_head, (const char *path), {
    var x = new XMLHttpRequest();
    x.open('HEAD', '/' + UTF8ToString(path), false);
    x.send();
    return x.status === 200 ? Number(x.getResponseHeader('Content-Length')) : -1;
});
#endif

int rn_tex_overlay;   // 1 once Cars/TEXTURES.BIN was served from the overlay with the DUMMY_SKIN5..12 targets (host/free.c checks it)

// Collision index of a TRACKB (PATCH 0x441423, cave 0x797620: push chunk, push mgr; call [SCREEN_ADDR+0xcc]), the 0x34133 branch of the
// loader 0x441380; CollectPolys 0x441660 now reads u32 entries. A chunk that starts with 0xffffffff is already u32 (the merged city,
// tools/ug2_collfile.py: more than 65,534 rows): used in place. Any other is u16 (the 16 shipped files): widened into a guest copy.
// Sets mgr+0x18 (entries) and +0x1c (count, read by nobody). The copy of the last load is freed at the next one.
uint32_t coll_widx(Ctx *c) {
    static uint32_t prev;
    uint32_t mgr = ARG(0), ch = ARG(1), size = ld(c, ch + 4, 4), data = ch + 8, ptr = data, n;
    if (prev) { guest_free(prev); prev = 0; }
    if (size >= 4 && ld(c, data, 4) == 0xffffffffu) { ptr = data + 4; n = (size - 4) / 4; }
    else {
        n = size / 2;
        ptr = prev = guest_alloc(n * 4 + 4);
        if (!ptr) { rn_log("WIDX: no memory for %u widx entries", n); n = 0; ptr = data; }
        for (uint32_t k = 0; k < n; k++) st(c, ptr + 4 * k, ld(c, data + 2 * k, 2), 4);
    }
    st(c, mgr + 0x18, ptr, 4); st(c, mgr + 0x1c, n, 4);
    return 0;
}

// The caves jump through these slots; filled on the first file open (before GLOBALB is read), so host/win32.c is untouched.
static void hooks_install(void) {
    static int done;
    if (done || !g_ctx) return;
    done = 1;
    // Quick Race builder 0x4b70c0: filter Drift before assigning the next Mode_%d slot.
    const char *tier = getenv("RN_TIER");
    st(g_ctx, SCREEN_ADDR + 0xdc, tier && (!strcmp(tier, "lite") || !strcmp(tier, "ultralite")), 1);
    extern int rn_nomusic(void);  // host/files.c; tested by the music-only stream-init cave.
    st(g_ctx, SCREEN_ADDR + 0xe4, rn_nomusic(), 1);
    st(g_ctx, SCREEN_ADDR + 0xcc, host_addr_of("rn", "coll_widx"), 4);
    st(g_ctx, SCREEN_ADDR + 0xd4, host_addr_of("rn", "mode_menu"), 4);
    st(g_ctx, SCREEN_ADDR + 0xd8, host_addr_of("rn", "mode_switch"), 4);
}

// One overlay file by its name, served from build/openworld (native) or /world/ (web, tools/serve.py). 1 = served.
static int overlay_file(const char *name, char *real, size_t n, uint64_t *size) {
#ifdef __EMSCRIPTEN__
    snprintf(real, n, "world/%s", name);
    static char hname[64]; static double hlen = -2;   // the HEAD answer is kept: every Cars/TEXTURES.BIN open used to repeat it
    double len;
    if (hlen != -2 && !strcmp(hname, name)) len = hlen;
    else { len = file_head(real); snprintf(hname, sizeof hname, "%s", name); hlen = len; }
    if (len < 0) { rn_log("OVERLAY: no file /%s, the original is used", real); return 0; }
    *size = (uint64_t)len;
#else
    const char *dir = getenv("RN_WORLD_DIR");
    snprintf(real, n, "%s/%s", dir && *dir ? dir : "build/openworld", name);
    struct stat sb;
    if (stat(real, &sb) || !S_ISREG(sb.st_mode)) { rn_log("OVERLAY: no file %s, the original is used", real); return 0; }
    *size = (uint64_t)sb.st_size;
#endif
    return 1;
}

// Cars/TEXTURES.BIN (any folder, any case): the overlay copy (tools/remaster/world_overlays.py) unless RN_FREE=0 (original mode keeps the
// shipped file). A missing overlay file leaves the original. 1 = served (real and size are set).
int rn_overlay_open(const char *gpath, char *real, size_t n, uint64_t *size) {
    hooks_install();
    const char *b = gpath;
    for (const char *p = gpath; *p; p++) if (*p == '/' || *p == '\\') b = p + 1;
    const char *par = b - 1;
    while (par > gpath && par[-1] != '/' && par[-1] != '\\') par--;
    const char *fe = getenv("RN_FREE");
    if ((fe && fe[0] == '0') || b == gpath || !ci_eq(b, "TEXTURES.BIN", 13) || !ci_eq(par, "CARS", 4) || (par[4] != '/' && par[4] != '\\')) return 0;
    if (!overlay_file("CARS_TEXTURES.BIN", real, n, size)) return 0;
    rn_tex_overlay = 1;
    rn_log("OVERLAY: %s -> %s (%llu bytes)", gpath, real, (unsigned long long)*size);
    return 1;
}
