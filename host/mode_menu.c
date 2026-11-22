// Speed.exe FEString virtual Clone 0x5009a0, base copy 0x4fec30, FEScript copy 0x502970.
// Verified with objdump + REA/Hopper/Ghidra. Prior art: NFSU2Unlimiter/FEPackage.h virtual cloning.
// Original's only permitted new menu item (OWNER 2026-11-14); Full keeps the existing menu.
#include "host.h"
#include <string.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#endif
#define MODE_HASH 0x5f524e4du
static uint32_t rd(Ctx *c, uint32_t a) { return ld(c, a, 4); }
static void shift_y(Ctx *c, uint32_t obj, float delta) {
    // Parameter slot 8 = Y. 0x4ff030 / 0x5001b0 resolve position tracks at slot 7.
    uint32_t params = rd(c, obj + 0x2c);
    float y; memcpy(&y, G(params + 32), 4); y += delta; memcpy(G(params + 32), &y, 4);
    for (uint32_t s = rd(c, obj + 0x4c); s; s = rd(c, s + 4)) {
        uint32_t frames = rd(c, s + 0x20), n = rd(c, s + 0x1c);
        for (uint32_t i = 0; i < n; i++) {
            uint32_t f = frames + i * 0x38;
            if (ld(c, f, 1) != 4 || ld(c, f + 7, 1) != 7) continue;
            // Shared key resources survive Clone(false); materialize the owning track before editing it.
            if (ld(c, f + 0x2c, 1)) {
                uint32_t owner = rd(c, f + 0x30);
                while (ld(c, owner + 4, 1)) owner = rd(c, owner + 8);
                uint8_t header[0x14]; memcpy(header, G(f), sizeof header);
                c->r[EAX] = owner - 0x28;
                call_guest_cdecl(c, 0x4fcb20, 1, &f);
                memcpy(G(f), header, sizeof header);
            }
            memcpy(&y, G(f + 0x1c), 4); y += delta; memcpy(G(f + 0x1c), &y, 4);
            // Deep Clone(false) owns its key list (0x4fcb20): node +0x14 is Y.
            for (uint32_t k = rd(c, f + 0x30); k; k = rd(c, k + 4)) {
                memcpy(&y, G(k + 0x14), 4); y += delta; memcpy(G(k + 0x14), &y, 4);
            }
        }
    }
}
uint32_t mode_menu(Ctx *c) {
    uint32_t saved[8]; memcpy(saved, c->r, sizeof saved);
    // The ctor runs before the active list is linked. Use the game's loaded-package registry (0x4f65d0).
    uint32_t package_name = guest_alloc(16); strcpy((char *)G(package_name), "MU_Main_PC.fng");
    c->r[EAX] = package_name;
    uint32_t pkg = call_guest(c, 0x4f65d0, 0, NULL);
    guest_free(package_name);
    if (!pkg) { rn_log("mode menu: main package missing"); goto out; }
    uint32_t n = rd(c, pkg + 0x88), old = rd(c, pkg + 0x84), src = 0, idx = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t obj = rd(c, old + 4 * i), hash = rd(c, obj + 0x10);
        if (hash == MODE_HASH) goto out; // The package may remain loaded when returning to this screen.
        if (hash == 0xf20e404a) { src = obj; idx = i; }
    }
    if (!src) { rn_log("mode menu: STATISTICS missing (%u buttons)", n); goto out; }
    c->r[ECX] = src;
    uint32_t deep = 0, obj = call_guest(c, 0x5009a0, 1, &deep);
    if (!obj) goto out;
    st(c, obj + 0x10, MODE_HASH, 4);
    uint32_t name = guest_alloc(16); strcpy((char *)G(name), "RN_MODE_SWITCH");
    guest_free(rd(c, obj + 0x14)); st(c, obj + 0x14, name, 4);
    // Copy the live values too: the base copy constructor initially zeros its parameter buffer.
    memcpy(G(rd(c, obj + 0x2c)), G(rd(c, src + 0x2c)), rd(c, src + 0x30));
    shift_y(c, obj, 42.0f);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t button = rd(c, old + i * 4), h = rd(c, button + 0x10);
        if (h == 0xa936c3a2 || h == 0x95ad096b || h == 0x70fbb1e4) shift_y(c, button, 42.0f);
    }
    // Insert under STATISTICS in both the draw list and the package's navigable-button array (0x5013a0/0x5017d0).
    uint32_t next = rd(c, src + 4);
    st(c, obj + 4, next, 4); st(c, obj + 8, src, 4); st(c, src + 4, obj, 4);
    if (next) st(c, next + 8, obj, 4); else st(c, pkg + 0x44, obj, 4);
    st(c, pkg + 0x3c, rd(c, pkg + 0x3c) + 1, 4);
    uint32_t buttons = guest_alloc((n + 1) * 4);
    memcpy(G(buttons), G(old), (idx + 1) * 4);
    st(c, buttons + (idx + 1) * 4, obj, 4);
    memcpy(G(buttons + (idx + 2) * 4), G(old + (idx + 1) * 4), (n - idx - 1) * 4);
    // Online (0x70fbb1e4, docs/re/frontend_menu.md) leaves the screen (WORLD retired 2026-11-17, attic/world/README.md; the shipped button
    // needs a network the page does not have): out of the navigable array, moved far below, and every button under it moves up into its place.
    uint32_t m = n + 1, online = 0;
    const char *tier = getenv("RN_TIER");
    int lite = tier && (!strcmp(tier, "lite") || !strcmp(tier, "ultralite"));
    const uint32_t hidden[] = {0x70fbb1e4, 0xd7ba6011, 0xa936c3a2, 0xf20e404a};
    for (unsigned k = 0; k < (lite ? 4u : 1u); k++) {
        uint32_t removed = 0;
        for (uint32_t i = 0; i < m; i++) if (rd(c, rd(c, buttons + 4 * i) + 0x10) == hidden[k]) {
            removed = rd(c, buttons + 4 * i);
            memmove(G(buttons + 4 * i), G(buttons + 4 * i + 4), (m - i - 1) * 4);
            m--; break;
        }
        if (!k) online = removed;
        if (!removed) continue;
        // Same removal as Online: keep the draw object alive, close its gap, exclude it from navigation.
        float oy, y, gap = 0; memcpy(&oy, G(rd(c, removed + 0x2c) + 32), 4);
        for (uint32_t i = 0; i < m; i++) { memcpy(&y, G(rd(c, rd(c, buttons + 4 * i) + 0x2c) + 32), 4); if (y > oy && (!gap || y - oy < gap)) gap = y - oy; }
        for (uint32_t i = 0; i < m; i++) { uint32_t b = rd(c, buttons + 4 * i); memcpy(&y, G(rd(c, b + 0x2c) + 32), 4); if (y > oy) shift_y(c, b, -gap); }
        shift_y(c, removed, 2000.0f);
    }
    st(c, pkg + 0x84, buttons, 4); st(c, pkg + 0x88, m, 4); guest_free(old);
    const char *mode = getenv("RN_MODE"), *label = mode && !strcmp(mode, "original") ? "MODO REMASTER" : "MODO ORIGINAL";
    uint32_t text = guest_alloc(32); strcpy((char *)G(text), label);
    c->r[EAX] = obj; call_guest_cdecl(c, 0x4f68a0, 1, &text); guest_free(text);
    rn_log("mode menu: added %s hash=%08x object=%08x buttons=%u, online %s", label, MODE_HASH, obj, m, online ? "hidden" : "missing");
out:
    memcpy(c->r, saved, sizeof saved); return saved[EAX];
}
uint32_t mode_switch(Ctx *c) {
    (void)c;
    rn_log("mode menu: accept -> rnSwitchMode");
#ifdef __EMSCRIPTEN__
    MAIN_THREAD_EM_ASM({ window.rnSwitchMode(); });
#endif
    return 0;
}
