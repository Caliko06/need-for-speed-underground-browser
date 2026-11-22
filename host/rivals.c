// BRIDGE: rivals with a soul in Quick Race (OWNER 2026-10-27), not in the original. The game builds each opponent in 0x4b4040:
// in the career ([0x78a33c] != 0) it takes the event's fixed preset (0x4b26f0, list 0x748844, FrontB.lzc chunk 0x30220: 184
// presets of 0x408 bytes) or, past the event's records, a stock car with a random paint (0x4b3c60); quick race always the
// latter. Then it matches the opponent's rating to the player's (0x57f700 / 0x57f970) and registers it with 0x5809c0.
// PATCH 0x4b4321 sends that call here first (cave 0x6736b1: jmp [SCREEN_ADDR+0x60]).
//
// The Underground career keeps the game's own rivals, always (OWNER 2026-10-27: the canon is the real cars). In Quick Race
// every opponent becomes one of POOL procedural personas (name, car, archetype, seed) with a build of its tier made of the
// game's own parts (GLOBALB 0x80034602, read live from the list at 0x73ad40): kit, widebody, hood, roof scoop, wing,
// lights, exhaust, brakes, rims, paint, vinyl layers and their colours, sponsor decals, tint, neon. The build goes into a
// preset record of our own, and the game's preset code 0x4b26f0 applies it. 0x57f700 then matches the new car to the
// rating the game chose, and the archetype moves one tuning category per group by +-1 (its driving). RN_RIVALS=0: the
// original in Quick Race too.
#include "host.h"
#include <string.h>
#include <math.h>
#include <stdlib.h>

#define POOL 300
#define NSYN 8                  // synthetic preset records: one per opponent slot of a race
#define RIDE_SIZE 0x720         // RideInfo: 0x57d160 clears up to +0x71c
enum { CLEAN, SHOW, DRIFT, SLEEPER, STREET, BOSO, VIP, TRACK, NARCH };

int rn_pool(void) { static int on = -1; if (on < 0) on = getenv("RN_POOL") != NULL; return on; }   // ?pool=1, OWNER 2026-11-03: the car pool, off until approved
// Liveries of the pool: skin hash (ride +0x444) -> car and art number, web/remaster/liv/<CAR>/<n>.webp (tools/art/compose.py). host/d3d9.c skin_bridge asks here.
static struct { uint32_t skin; uint8_t car, n; } liv[32];
static void livery_set(uint32_t skin, int car, int n) {
    int k = 0;
    while (k < 31 && liv[k].skin && liv[k].skin != skin) k++;
    liv[k].skin = n >= 0 ? skin : 0; liv[k].car = (uint8_t)car; liv[k].n = (uint8_t)n;
}
int rn_pool_livery(uint32_t skin, int *car, int *n) {
    for (int k = 0; k < 32; k++) if (skin && liv[k].skin == skin) { *car = liv[k].car; *n = liv[k].n; return 1; }
    return 0;
}
static uint32_t neon_ride[NSYN];       // skin hash (ride +0x444) of the SHOW and BOSO rivals: neon_pass animates them
static const char *CARS[20] = {"GOLF", "FOCUS", "MIATA", "NEON", "CIVIC", "PEUGOT", "CELICA", "ECLIPSE", "RX7", "SUPRA",
    "S2000", "RSX", "IMPREZA", "LANCER", "INTEGRA", "TIBURON", "350Z", "SENTRA", "240SX", "SKYLINE"};
// The pool picks its cars before the game loads them one after another: their files start coming at once (host/files.c, web only).
static void car_prefetch(const char *car) {
    static const char *F[] = {"GEOMETRY.BIN", "TEXTURES.BIN", "VINYLS.BIN"};
    char p[96];
    for (int k = 0; k < 3; k++) { snprintf(p, sizeof p, "CARS\\%s\\%s", car, F[k]); gf_prefetch(p); }
}

// The race's whole car list is known before its first car file opens: 0x448f70 walks the entrants [0x78a418] (count [0x78a41c], 0x750
// each, car type = dword at +0x10) and calls 0x58c3b0 for each; 0x58bb50 prints "CARS\%s\TEXTURES.BIN" with the name at [0x734588] + 0xc90 * type + 0.
// Called from gf_open (host/files.c): once per change of the list, every folder's files start coming at once (web only).
void cars_hook(Ctx *c) {
    // Ultra-Lite loads only the entrants the game actually opens, without speculative car requests.
    const char *tier = getenv("RN_TIER");
    if (tier && !strcmp(tier, "ultralite")) return;
    static uint32_t last;
    uint32_t tab = ld(c, 0x78a418, 4), n = ld(c, 0x78a41c, 4), ct = ld(c, 0x734588, 4);
    if (!tab || !ct || n == 0 || n > 64) return;
    uint32_t h = n;
    for (uint32_t i = 0; i < n; i++) h = h * 31 + ld(c, tab + 0x750 * i + 0x10, 4);
    if (h == last) return;
    last = h;
    uint32_t seen = 0; int folders = 0;
    const char *rm = getenv("RN_RANGEMB");
    int cap = rm && atoi(rm) > 0 && atoi(rm) <= 96 ? 5 : 64;   // phone cache: the first entrant (the player) + 4 unique rivals, the rest load on demand
    for (uint32_t i = 0; i < n && folders < cap; i++) {
        uint32_t t = ld(c, tab + 0x750 * i + 0x10, 4);
        if (t >= 35 || (seen >> t & 1)) continue;
        seen |= 1u << t;
        const char *nm = (const char *)c->mem + ct + 0xc90 * t;
        int k = 0;
        while (k < 16 && nm[k] >= 0x21 && nm[k] < 0x7f) k++;
        if (k == 0 || k >= 16 || nm[k]) continue;
        car_prefetch(nm);
        folders++;
    }
    rn_log("rivals: prefetch cars: %d folders", folders);
}

typedef struct {
    const char *name;
    uint8_t kit, wide, hood, scoop, wing, lights, exhaust;   // % at tier 3 (tier t: x t/3)
    uint8_t vinyl, layers, decals, neon, tint;               // % vinyl, max layers, decals per door, % neon, tint 0..2
    int8_t power, grip, accel;                               // driving: +-1 on one category of each group
    uint32_t paint[8];                                        // body colours (0xRRGGBB), 0 ends
    const char *wings, *rims, *vinyls, *brands;               // '|' lists of name prefixes; "" = any
    uint32_t rimcol[3];                                       // rim paint
    uint8_t cars[12];                                         // car ids it likes, 0xff ends
} Arch;

static const Arch ARCH[NARCH] = {
    [CLEAN] = {"jdm-clean", 55, 0, 25, 0, 45, 30, 50, 25, 1, 1, 0, 0, -1, 1, 0,
               {0xf2f2ee, 0xc0c4c8, 0x18181c, 0x5a5f66, 0xb0121b, 0x1a3f9a, 0xe8c400},
               "FLYTE|TOURING|AEROMAX|CARBON X|TRIVO", "ENKEI|BBS|RACING", "STRIPE|BODY",
               "HKS|GREDDY|APEX|ENKEI|BBS|SKUNK2|JSP|5ZIGEN", {0x8c6a3a, 0xf0f0f0, 0xc8a040},
               {4, 11, 14, 10, 9, 19, 8, 12, 2, 0xff}},
    [SHOW] = {"show", 100, 45, 60, 40, 80, 90, 80, 100, 3, 3, 90, 1, -1, 0, 1,
              {0x6a1fb0, 0x2bd12b, 0x0e7fe0, 0xff6a00, 0xe0e0f0, 0xc0107a, 0x00b5b0},
              "SUPERNOVA|INFERNO|MAKO|BACKDRAFT|KATANA|DUOTEK|BOOMERANG", "MOMO|KONIG|NINJA|SIX|CYCLONE|FIVE",
              "TRIBAL|SPLASH|WILD|MODERN|LIGHTNING|TEAR", "KENWOOD|ALPINE|AUDIOBAHN|PLASMAGLOW|STREET GLOW|NOS|NITROUS",
              {0xc0c0c0, 0xc8a040, 0x141414}, {7, 6, 4, 3, 15, 11, 14, 16, 1, 0xff}},
    [DRIFT] = {"drift", 85, 25, 70, 10, 85, 40, 70, 75, 2, 2, 20, 1, 1, -1, 0,
               {0xff5a00, 0xf2f2ee, 0x101012, 0x7fd000, 0xe0b000, 0x2050c0, 0xc81e1e},
               "ALUMINUM GT|DUAL GT|KATANA|WARHAWK|DOWNFORCE", "KONIG|ENKEI|RACING", "TEAR|STRIPE|SPLASH|WILD",
               "GREDDY|HKS|TOYO|YOKOHAMA|KUMHO|APEX|BILSTEIN|SPARCO", {0x8c6a3a, 0x141414, 0xf0f0f0},
               {18, 8, 19, 16, 10, 9, 2, 6, 0xff}},
    [SLEEPER] = {"sleeper", 10, 0, 10, 0, 5, 10, 40, 0, 0, 0, 0, 2, 1, 0, 0,
                 {0x18181c, 0x2e3238, 0x1c2a44, 0x5a1418, 0x6e7276, 0xb8b8b0},
                 "FLYTE", "ENKEI|O.Z.", "", "", {0x141414, 0x404448, 0x404448}, {17, 13, 12, 1, 0, 4, 14, 5, 0xff}},
    [STREET] = {"street", 90, 20, 50, 45, 80, 60, 70, 85, 2, 3, 55, 1, 0, -1, 1,
                {0x1060e0, 0xc81e1e, 0xf0f0f0, 0x101012, 0xffc000, 0x20a040, 0x8a2be2, 0x00a0d0},
                "", "", "TRIBAL|FLAME|STRIPE|LIGHTNING|MODERN|BODY", "NOS|NITROUS|AEM|INJEN|HKS|GREDDY|SPARCO|MOMO|NEUSPEED",
                {0xc0c0c0, 0x141414, 0xc8a040}, {0xff}},
    [BOSO] = {"bosozoku", 95, 40, 60, 80, 100, 70, 90, 95, 3, 2, 70, 1, 1, -1, 0,
              {0xc000c0, 0xffd000, 0xe01010, 0x10a040, 0xff8000, 0xf0f0f0, 0x2040ff},
              "HAMMERHEAD|BOOMERANG|SUPERNOVA|WARHAWK|INFERNO|DUOTEK", "SIX|NINJA|CYCLONE|KONIG",
              "FLAME|LIGHTNING|WILD|TRIBAL|FLAG", "", {0xc8a040, 0xf0f0f0, 0x141414}, {9, 19, 4, 18, 6, 8, 14, 0xff}},
    [VIP] = {"vip", 50, 0, 0, 0, 25, 40, 50, 0, 0, 0, 10, 2, 0, 1, -1,
             {0x0e0e10, 0xd8ccb0, 0x4a1018, 0x2a2e36, 0xe8e8e4, 0x1a2238},
             "FLYTE|GRIFTER", "BBS|LIVIA|SPLIT|FIVE", "", "BBS", {0xc0c0c0, 0xc8a040, 0x141414},
             {13, 17, 12, 9, 19, 16, 0xff}},
    [TRACK] = {"time-attack", 75, 15, 80, 0, 95, 30, 60, 60, 1, 4, 0, 1, 0, 1, 0,
               {0xf2f2ee, 0xc0c4c8, 0xd01818, 0x1a3f9a, 0xf0c000, 0x101012},
               "DOWNFORCE|ALUMINUM GT|DUAL GT|CARBON X|TRIVO", "ENKEI|O.Z.|BBS", "STRIPE|FLAG",
               "SPARCO|BREMBO|TOYO|YOKOHAMA|KUMHO|AEM|MOMO|HKS|EIBACH|KONI|WILWOOD|ACT", {0xf0f0f0, 0x8c6a3a, 0xc8a040},
               {10, 8, 12, 13, 2, 14, 11, 4, 19, 0xff}},
};
static const uint8_t ARCH_W[NARCH] = {15, 15, 13, 9, 20, 9, 9, 10};

static const char *NAMES[] = {"Kaze", "Ryu", "Nova", "Vex", "Jinx", "Slick", "Torque", "Apex", "Blitz", "Rook", "Haze", "Zero",
    "Kenji", "Mika", "Dante", "Rico", "Luz", "Nico", "Yuki", "Taz", "Juno", "Rex", "Ivy", "Kai", "Sable", "Ghost", "Rhino",
    "Viper", "Echo", "Neko", "Dash", "Ozzy", "Kilo", "Remy", "Sasha", "Bix", "Cruz", "Drex", "Flint", "Gio", "Hex", "Inez",
    "Jett", "Koda", "Lux", "Moxie", "Nash", "Omar", "Pike", "Quinn", "Raze", "Sly", "Tank", "Ume", "Vega", "Wolf", "Xan",
    "Yoshi", "Zed", "Akira", "Benji", "Coco", "Deuce", "Ezra", "Fang", "Gunz", "Hiro", "Iggy", "Jade", "Knox", "Lobo", "Mars",
    "Nyx", "Onyx", "Pixie", "Ruby", "Stix", "Toshi", "Vince", "Wren", "Xeno", "Yara", "Zoey", "Ace", "Bolt", "Cyra", "Diaz",
    "Ember", "Fizz", "Gator", "Holly", "Ink", "Jolt", "Kobe", "Lefty", "Mako", "Nitro", "Odie", "Pablo", "Rascal", "Shin",
    "Tito", "Uri", "Vida", "Wiz", "Yuri", "Zuri", "Maya", "Tre", "Lalo", "Kat", "Spike", "Rocco", "Chula", "Mondo"};
#define NNAMES (int)(sizeof NAMES / sizeof *NAMES)

typedef struct { char name[8]; uint8_t car, arch; uint32_t seed; } Persona;
typedef struct { uint32_t rec, car, key, name; uint8_t slot, lvl, rgb[3], kind; } Part;   // kind: paint family
enum { K_NONE, K_GLOSS, K_METAL, K_PEARL, K_CUSTOM, K_VINYL, K_RIMS, K_CALIPERS, K_MUFFLERS };

static Persona pool[POOL];
static Part *parts;
static int nparts, ready, on;
static uint32_t syn[NSYN], used[NSYN], nused;
static uint32_t carhash[20];

static uint32_t hash(const char *s) { uint32_t h = 0xffffffffu; while (*s) h = h * 33 + (uint8_t)*s++; return h; }
static uint32_t ghash(Ctx *c, uint32_t p) { uint32_t h = 0xffffffffu; for (uint8_t b; (b = c->mem[p]); p++) h = h * 33 + b; return h; }
static uint32_t rnd(uint32_t *s) { uint32_t x = *s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return *s = x ? x : 0x9e3779b9u; }
static int roll(uint32_t *s, int pct) { return (int)(rnd(s) % 100) < pct; }
static int prefixed(const char *name, const char *list) {         // name starts with one of "A|B|C"; "" = any
    if (!*list) return 1;
    for (const char *p = list; *p;) {
        const char *e = strchr(p, '|'); size_t n = e ? (size_t)(e - p) : strlen(p);
        if (!strncmp(name, p, n)) return 1;
        p += n + (e != NULL);
    }
    return 0;
}

// The parts list the game loaded (0x57c927): node +0xc records, +0x10 count; record 0x30: +0 name, +4 car (or the shared
// group of the slot), +8 key, +0x10 slot, +0x11 unlock level, +0x14 attributes (key, value) x [+0x1c].
static void catalog(Ctx *c) {
    uint32_t hR = hash("RED"), hG = hash("GREEN"), hB = hash("BLUE");
    int cap = 0;
    for (uint32_t n = ld(c, 0x73ad40, 4); n && n != 0x73ad40; n = ld(c, n, 4)) cap += ld(c, n + 0x10, 4);
    parts = calloc(cap, sizeof *parts);
    for (uint32_t n = ld(c, 0x73ad40, 4); n && n != 0x73ad40; n = ld(c, n, 4))
        for (uint32_t r = ld(c, n + 0xc, 4), e = r + 0x30 * ld(c, n + 0x10, 4); r < e && nparts < cap; r += 0x30) {
            Part *p = &parts[nparts++];
            p->rec = r; p->name = ld(c, r, 4); p->car = ld(c, r + 4, 4); p->key = ld(c, r + 8, 4);
            p->slot = c->mem[r + 0x10]; p->lvl = c->mem[r + 0x11];
            for (uint32_t a = ld(c, r + 0x14, 4), k = 0, na = ld(c, r + 0x1c, 2); a && k < na; k++) {
                uint32_t key = ld(c, a + 8 * k, 4), v = ld(c, a + 8 * k + 4, 4);
                if (key == hR) p->rgb[0] = v; else if (key == hG) p->rgb[1] = v; else if (key == hB) p->rgb[2] = v;
            }
            const char *s = G(p->name);
            p->kind = !strncmp(s, "GLOSS", 5) ? K_GLOSS : !strncmp(s, "METAL", 5) ? K_METAL : !strncmp(s, "PEARL", 5) ? K_PEARL
                    : !strncmp(s, "CUSTOMPAINT", 11) ? K_CUSTOM : !strncmp(s, "VINYL_", 6) ? K_VINYL : !strncmp(s, "RIMS_", 5) ? K_RIMS
                    : !strncmp(s, "CALIPERS_", 9) ? K_CALIPERS : !strncmp(s, "MUFFLERS_", 9) ? K_MUFFLERS : K_NONE;
        }
    for (int k = 0; k < 20; k++) carhash[k] = hash(CARS[k]);
    // The pool: the same personas for every save (a fixed seed), so a rival keeps its name, car and style.
    uint32_t s = 0x0dd0c0deu;
    for (int i = 0; i < POOL; i++) {
        Persona *p = &pool[i];
        int w = rnd(&s) % 100, a = 0;
        while (a < NARCH - 1 && w >= ARCH_W[a]) w -= ARCH_W[a++];
        const uint8_t *cl = ARCH[a].cars;
        int n = 0;
        while (n < 12 && cl[n] != 0xff) n++;
        p->arch = a; p->car = n ? cl[rnd(&s) % n] : rnd(&s) % 20; p->seed = rnd(&s);
        if (i < NNAMES) snprintf(p->name, sizeof p->name, "%s", NAMES[i]);
        else {                                                    // a street handle of two syllables, not taken yet
            static const char *SY[] = {"Ka", "Ze", "Ri", "No", "To", "Mi", "Ra", "Vo", "Xi", "Lu", "Ba", "De", "Jo", "Ky", "Sa",
                                       "Re", "Zu", "Ta", "Ni", "Go", "Ma", "Ko", "Su", "Ve", "Da", "Ro", "Ji", "Fe"};
            static const char *EN[] = {"", "x", "n", "k", "z", "r", "o", "a"};
            for (int dup = 1; dup;) {
                char lo[3]; const char *s2 = SY[rnd(&s) % 28];
                lo[0] = (char)(s2[0] | 0x20); lo[1] = s2[1]; lo[2] = 0;
                snprintf(p->name, sizeof p->name, "%s%s%s", SY[rnd(&s) % 28], lo, EN[rnd(&s) % 8]);
                dup = 0;
                for (int j = 0; j < i; j++) dup |= !strcmp(pool[j].name, p->name);
            }
        }
    }
    for (int k = 0; k < NSYN; k++) syn[k] = guest_alloc(0x408);
    ready = 1;
}

static uint32_t find_preset(Ctx *c, uint32_t h) {
    for (uint32_t p = ld(c, 0x748844, 4); p && p != 0x748844; p = ld(c, p, 4))
        if (ghash(c, p + 0x28) == h) return p;
    return 0;
}
// Our preset record k, linked at the front of the game's preset list (0x4b2640 finds presets by name) if it is not there.
static void link(Ctx *c, uint32_t r, const char *name) {
    snprintf(G(r + 0x28), 32, "%s", name);
    if (find_preset(c, hash(name)) == r) return;
    uint32_t head = 0x748844, first = ld(c, head, 4);
    st(c, r, first, 4); st(c, r + 4, head, 4); st(c, first + 4, r, 4); st(c, head, r, 4);
}
// A persona not yet in this race, from index i on.
static Persona *fresh(int i) {
    for (int tries = 0; tries < POOL; tries++, i = (i + 1) % POOL) {
        int dup = 0;
        for (uint32_t u = 0; u < nused && u < NSYN; u++) dup |= used[u] == (uint32_t)i;
        if (!dup) break;
    }
    used[nused++ % NSYN] = i;
    return &pool[i];
}

// A random part of a slot for this car (or shared), unlock level <= lvl, name in the list; 0 = none fits.
static const Part *pick(uint32_t *s, int car, int slot, int lvl, const char *list, int stock) {
    Ctx *c = g_ctx;
    const Part *cand[256]; int n = 0;
    for (int k = 0; k < nparts && n < 256; k++) {
        const Part *p = &parts[k];
        if (p->slot != slot || p->lvl > lvl || (!stock && p->lvl == 0)) continue;
        if (slot != 0x1f && slot != 0x11 && slot != 0x3a && slot != 0x73 && slot != 0x74 && p->car != carhash[car]) continue;
        if (!prefixed(G(p->name), list)) continue;
        cand[n++] = p;
    }
    return n ? cand[rnd(s) % n] : NULL;
}
static const Part *named(int car, int slot, const char *name) {
    Ctx *c = g_ctx;
    for (int k = 0; k < nparts; k++)
        if (parts[k].slot == slot && parts[k].car == carhash[car] && !strcmp(G(parts[k].name), name)) return &parts[k];
    return NULL;
}
// The paint of a family nearest a colour; a little spread between the three nearest so two rivals rarely match.
static const Part *paint(uint32_t *s, uint32_t rgb, uint32_t kinds) {
    const Part *best[3] = {0}; int d[3] = {1 << 30, 1 << 30, 1 << 30};
    int r = rgb >> 16 & 255, g = rgb >> 8 & 255, b = rgb & 255;
    for (int k = 0; k < nparts; k++) {
        const Part *p = &parts[k];
        if (p->slot != 0x1e || !(kinds >> p->kind & 1)) continue;
        int dr = p->rgb[0] - r, dg = p->rgb[1] - g, db = p->rgb[2] - b, e = 2 * dr * dr + 4 * dg * dg + 3 * db * db;
        for (int j = 0; j < 3; j++)
            if (e < d[j]) { for (int m = 2; m > j; m--) { d[m] = d[m - 1]; best[m] = best[m - 1]; } d[j] = e; best[j] = p; break; }
    }
    int j = rnd(s) % 3;
    return best[j] ? best[j] : best[0];
}

static void set(Ctx *c, uint32_t rec, int slot, const Part *p) { if (p) { st(c, rec + 0x48 + 8 * slot, slot, 4); st(c, rec + 0x4c + 8 * slot, p->key, 4); } }

// The build of persona p at tier t (1..3) into preset record rec.
static void build(Ctx *c, uint32_t rec, const Persona *pe, int t) {
    const Arch *a = &ARCH[pe->arch];
    int car = pe->car, lv = t == 1 ? 1 : t == 2 ? 2 : 4;
    uint32_t s = pe->seed ^ (uint32_t)t * 0x9e3779b9u;           // the same build each time it meets you at this tier
    const char *cn = CARS[car];
    char base[32]; snprintf(base, sizeof base, "%s_BASE", car == 5 ? "206" : cn);
    uint32_t b = find_preset(c, hash(base));
    memset(G(rec + 8), 0, 0x20);
    memset(G(rec + 0x48), 0, 0x408 - 0x48);
    snprintf(G(rec + 8), 32, "%s", cn);
    if (b) memcpy(G(rec + 0x48), G(b + 0x48), 0x408 - 0x48);
    #define P(x) ((x) * t / 3)
    int wide = t == 3 && roll(&s, a->wide);
    if (wide) set(c, rec, 6, pick(&s, car, 6, 4, "", 0));
    else if (roll(&s, P(a->kit) + (t > 1 ? 15 : 0))) {           // one kit: front, rear and skirts of the same name
        const Part *k = pick(&s, car, 1, lv, "", 0);
        if (k) { set(c, rec, 1, k); set(c, rec, 2, named(car, 2, G(k->name))); set(c, rec, 0xa, named(car, 0xa, G(k->name))); }
    }
    if (roll(&s, P(a->hood))) set(c, rec, 7, pick(&s, car, 7, lv, "", 0));
    if (roll(&s, P(a->scoop))) set(c, rec, 8, pick(&s, car, 8, lv, "", 0));
    if (roll(&s, P(a->wing) + 10)) { const Part *w = pick(&s, car, 0xb, lv, a->wings, 0); set(c, rec, 0xb, w ? w : pick(&s, car, 0xb, lv, "", 0)); }
    if (roll(&s, P(a->lights))) { set(c, rec, 0xd, pick(&s, car, 0xd, 4, "", 0)); set(c, rec, 0xe, pick(&s, car, 0xe, 4, "", 0)); }
    int exh = roll(&s, P(a->exhaust) + 10);
    if (exh) set(c, rec, 0xf, pick(&s, car, 0xf, lv, "", 0));
    int brk = t > 1 || pe->arch == TRACK;
    if (brk) set(c, rec, 0x10, pick(&s, car, 0x10, t, "", 0));
    // Rims: the archetype's brands; bigger with the tier.
    const Part *rim = pick(&s, car, 0x11, lv, a->rims, 0);
    if (!rim) rim = pick(&s, car, 0x11, lv, "", 0);
    if (pe->arch == SLEEPER && t == 1) rim = NULL;
    set(c, rec, 0x11, rim);
    // Paint: body from the archetype's colours; spoiler in body colour; rims, calipers, tips in the archetype's.
    int np = 0; while (np < 8 && a->paint[np]) np++;
    uint32_t body = a->paint[rnd(&s) % np], accent = a->paint[rnd(&s) % np];
    if (accent == body) accent = a->paint[(rnd(&s) + 1) % np];
    int lum = (int)(body >> 16 & 255) * 3 + (int)(body >> 8 & 255) * 6 + (int)(body & 255);
    uint32_t neutral = lum > 1500 ? 0x141414 : 0xf0f0f0;
    uint32_t fam = pe->arch == SHOW || pe->arch == VIP ? 1u << K_PEARL | 1u << K_METAL | 1u << K_CUSTOM
                 : pe->arch == SLEEPER ? 1u << K_METAL | 1u << K_GLOSS : 1u << K_GLOSS | 1u << K_METAL | (t == 3 ? 1u << K_PEARL : 0);
    const Part *bp = paint(&s, body, fam);
    set(c, rec, 0x1e, bp); set(c, rec, 0x26, bp);
    if (brk) set(c, rec, 0x27, paint(&s, roll(&s, 60) ? 0xc01010 : roll(&s, 50) ? 0xf0c000 : accent, 1u << K_CALIPERS));
    if (exh) set(c, rec, 0x28, paint(&s, 0x808080, 1u << K_MUFFLERS));
    if (rim) set(c, rec, 0x29, paint(&s, a->rimcol[rnd(&s) % 3], 1u << K_RIMS));
    // Vinyls: up to the archetype's layers (1 at tier 1); colours from the accent and a neutral against the body.
    int layers = 0;
    if (rn_pool()) {
        // ?pool=1: one design per car, the game's own vinyl in colours that read on the body (two unrelated layers looked like a collage, OWNER "wonky").
        static const uint8_t VINP[NARCH] = {[CLEAN] = 40, [SHOW] = 100, [DRIFT] = 85, [STREET] = 90, [BOSO] = 90, [VIP] = 15, [TRACK] = 70};
        layers = a->vinyl && roll(&s, VINP[pe->arch]);
        for (int k = 0; k < np; k++) {
            int dr = (int)(accent >> 16 & 255) - (int)(body >> 16 & 255), dg = (int)(accent >> 8 & 255) - (int)(body >> 8 & 255), db = (int)(accent & 255) - (int)(body & 255);
            if (accent != body && 2 * dr * dr + 4 * dg * dg + 3 * db * db > 40000) break;
            accent = a->paint[k];
        }
    } else if (a->vinyl && roll(&s, P(a->vinyl) + 10)) layers = 1 + (int)(rnd(&s) % (a->layers < t ? a->layers : t));
    for (int l = 0; l < layers; l++) {
        const Part *v = pick(&s, car, 0x1f, l ? 3 : lv, a->vinyls, 0);
        if (!v) continue;
        set(c, rec, 0x1f + l, v);
        for (int j = 0; j < 4; j++) set(c, rec, 0x2a + 4 * l + j, paint(&s, (j + l) & 1 ? neutral : accent, 1u << K_VINYL));
    }
    // Sponsor decals: the same brands on both doors, one on each window; layouts from the car (wide ones with a widebody).
    int nd = P(a->decals) + (a->decals && t == 1);
    if (nd) {
        const char *rect[7] = {"HOOD RECT MEDIUM", "FRONT WINDOW RECT MEDIUM", "REAR WINDOW RECT MEDIUM", "L DOOR RECT MEDIUM",
                               "R DOOR RECT MEDIUM", "L PANEL RECT MEDIUM", "R PANEL RECT MEDIUM"};
        for (int k = 1; k < 7; k++) set(c, rec, 0x13 + k, named(car, 0x13 + k, rect[k]));
        if (wide) {
            const char *w[4] = {"WIDE2_DECAL_LEFT_DOOR_RECT_MEDIUM", "WIDE2_DECAL_RIGHT_DOOR_RECT_MEDIUM",
                                "WIDE2_DECAL_LEFT_QUARTER_RECT_MEDIUM", "WIDE2_DECAL_RIGHT_QUARTER_RECT_MEDIUM"};
            for (int k = 0; k < 4; k++) set(c, rec, 0x1a + k, named(car, 0x1a + k, w[k]));
        }
        set(c, rec, 0x43, pick(&s, car, 0x3a, 4, a->brands, 1));
        set(c, rec, 0x4b, pick(&s, car, 0x3a, 4, a->brands, 1));
        for (int k = 0; k < nd && k < 4; k++) {
            const Part *d = pick(&s, car, 0x3a, 4, a->brands, 1);
            set(c, rec, 0x53 + k, d); set(c, rec, 0x5b + k, d);
        }
    }
    // Glass and underglow.
    const char *tints[3] = {"LIGHT TINT BLACK", "MEDIUM TINT BLACK", "DARK TINT BLACK"};
    if (pe->arch != STREET || roll(&s, 70)) set(c, rec, 0x73, pick(&s, car, 0x73, 4, tints[a->tint < t ? a->tint : t - 1], 0));
    int neonp = a->neon;
    if (rn_pool() && (pe->arch == CLEAN || pe->arch == DRIFT || pe->arch == STREET || pe->arch == BOSO || pe->arch == SHOW)) neonp = neonp > 80 ? neonp : 80;
    if ((t > 1 || rn_pool()) && roll(&s, neonp)) {
        const Part *best = NULL; int bd = 1 << 30;
        int ar = accent >> 16 & 255, ag = accent >> 8 & 255, ab = accent & 255;
        for (int k = 0; k < nparts; k++) {
            const Part *p = &parts[k];
            if (p->slot != 0x74 || !p->lvl) continue;
            const char *nm = G(p->name);
            if ((pe->arch != SHOW && pe->arch != BOSO) && strlen(nm) > 4 && strcmp(nm + strlen(nm) - 4, "Neon")) continue;
            int e = 0, m = 1 + (p->rgb[0] > p->rgb[1] ? p->rgb[0] : p->rgb[1]); m = m > p->rgb[2] ? m : p->rgb[2] + 1;
            e += (p->rgb[0] * 255 / m - ar) * (p->rgb[0] * 255 / m - ar) + (p->rgb[1] * 255 / m - ag) * (p->rgb[1] * 255 / m - ag)
               + (p->rgb[2] * 255 / m - ab) * (p->rgb[2] * 255 / m - ab) + (int)(rnd(&s) % 4000);
            if (e < bd) { bd = e; best = p; }
        }
        set(c, rec, 0x74, best);
    }
    #undef P
}

// Its driving: +-1 on one category of each group (power: engine 2, ECU 5, turbo 3; grip: suspension 1, tires 7,
// brakes 8; launch: transmission 6, nitrous 4, weight 0; index order from the tuner screens, 0x50a070).
static void personality(Ctx *c, uint32_t ride, const Persona *pe) {
    static const uint8_t grp[3][3] = {{2, 5, 3}, {1, 7, 8}, {6, 4, 0}};
    const Arch *a = &ARCH[pe->arch];
    int d[3] = {a->power, a->grip, a->accel};
    for (int g = 0; g < 3; g++) {
        if (!d[g]) continue;
        uint32_t f = ride + 8 + 4 * grp[g][(pe->seed >> (4 * g)) % 3];
        int v = (int)ld(c, f, 4) + d[g];
        st(c, f, v < 0 ? 0 : v > 3 ? 3 : v, 4);
    }
    c->mem[ride + 0x424] = 0xff;                                  // the rating is computed again (0x57f2b0)
}

// Builds persona pe into preset record rec, lets the game apply it to the ride (0x4b26f0 keeps DUMMY_SKIN/WHEEL) and
// matches the rating of tmp (the ride the game made, *r0 once 0x57f700 computed it) within 5.0; returns how far it stayed.
// 12 sticker sets per car (tools/art/compose.py): 0..3 clean, 4..7 show, 8..11 street.
static int livery_of(int arch, uint32_t *s) {
    int base = arch == CLEAN || arch == TRACK || arch == VIP ? 0 : arch == SHOW || arch == BOSO ? 4 : 8;
    return base + (int)(rnd(s) % 4);
}
// Free mode: a tuned traffic car (host/free.c free_traffic): half wear a neon, most a livery.
void rn_pool_traffic(Ctx *c, uint32_t ride, uint32_t seed) {
    if (!rn_pool() || c->mem[0x78a33c]) return;
    if (!ready) catalog(c);
    uint32_t s = seed * 0x9e3779b1u + ride;
    if (!ld(c, ride + 0x61c, 4) && roll(&s, 50)) {
        int cand[64], n = 0;
        for (int k = 0; k < nparts && n < 64; k++) if (parts[k].slot == 0x74 && parts[k].lvl) cand[n++] = k;
        if (n) { st(c, ride + 0x61c, parts[cand[rnd(&s) % n]].rec, 4); c->mem[ride + 0x62c + 0x74]++; }
    }
    int car = (int)ld(c, ride, 4), arch = (int)(rnd(&s) % NARCH);
    if (car < 20 && ld(c, ride + 0x444, 4)) livery_set(ld(c, ride + 0x444, 4), car, roll(&s, 70) ? livery_of(arch, &s) : -1);
}

static float apply(Ctx *c, uint32_t ride, uint32_t tmp, uint32_t rec, const char *nm, const Persona *pe, int tier, float *r0) {
    build(c, rec, pe, tier);
    link(c, rec, nm);
    uint32_t one = ride, m[6] = {ride, tmp, 0, 0xffffffffu, 0, 0x40a00000u};
    c->r[EAX] = hash(nm);
    call_guest_cdecl(c, 0x4b26f0, 1, &one);
    call_guest(c, 0x57f700, 6, m);
    float r1; memcpy(r0, G(tmp + 0x428), 4); memcpy(&r1, G(ride + 0x428), 4);
    return r1 > *r0 ? r1 - *r0 : *r0 - r1;
}

// Personalities (built for WORLD, retired 2026-11-17): ?pool=1 in a non-career race; RN_AI=2 forces them, for tests; ?ai=0 / RN_AI=0 off.
// docs/openworld/re_rival_personality.md, docs/re/race_ai.md. Free mode gives each rival its own skill level (host/free.c RN_FREESKILL
// 2,5,9,4,7,3,...), so a per-level style is a per-rival style: 2,1 nervous, 5,3 clean, 4,6 blocker, 9,7,8 aggressive; level 0 as shipped.
// Records 0x779ff8 + 0x54 * level (rival_tables), and per step persona_step below.
// Nervous: accepts 35 % of Pass/Avoid targets (+0x0c, 0x4627ac), route speed 6 % lower (+0x14, 0x44c72b), its speed lookup wanders twice
//   as far (+0x50, 0x44c667), reads it 2 nodes further on (brakes early), nitro cooldown x0.7 (+0x34/+0x38, 0x462ca8) and lifts 12 % while
//   its nitro burns (panic).
// Clean: shipped records; passes wide (side line + 1.5 m, persona_clear); in Draft (type 4) it holds the lead car's speed and stays in the tow (car+0x47c) instead of the shipped
//   "lead - (20 - gap)" back-off (0x450480), so the Pass finder slings it out after.
// Aggressive: route speed 4 % higher, Block ceiling 400 (style 2, 0x44dbd0: it beats Avoid and Pass), nitro cooldown x0.5, reads the
//   route speed 2 nodes earlier (brakes late), and IJustGotHit (type 0xc, 0x4522a0, a back-off to culprit - 6 m/s) becomes revenge:
//   culprit + 4 m/s.
enum { NORMAL, NERVOUS, TIDY, AGGRESSIVE, BLOCKER };   // TIDY = clean (CLEAN is an archetype above)
static const uint8_t PERSONA[10] = {NORMAL, NERVOUS, NERVOUS, TIDY, BLOCKER, TIDY, BLOCKER, AGGRESSIVE, AGGRESSIVE, AGGRESSIVE};
static const char *PNAME[5] = {"normal", "nervous", "clean", "aggressive", "blocker"};
static int free_race;                  // this race is free mode (rival_ride's rn_free_now)
static int persona_on;                 // this race's rivals have personalities (set at its first opponent)
static int rivalai(void) {             // 0 off, 1 with ?pool=1, 2 forced
    int ai = rn_env("RN_AI", 1);
    return ai == 0 ? 0 : ai == 2 ? 2 : 1;
}
static int rival_style(uint32_t skill, uint32_t style) { return persona_on && skill <= 9 && (PERSONA[skill] == AGGRESSIVE || PERSONA[skill] == BLOCKER) ? 2 : (int)style; }

// Every traffic model, RN_TRAFMODELS=1 (?trafmodels=1, ?pool=1; built for WORLD, OWNER 2026-11-04). The cave 0x63b270 weighs a usage 2 row 1.0 if any district weight +0xc60..+0xc70 is set: AMBULANCE, FIRETRUCK and BUS
// have none, so they never come out of 0x57d000. A weight here brings them in, once, before AddTrafficCars 0x4b3ac0 (it runs after 0x4b4040, this hook's caller).
static const uint8_t TT_ROWS[3] = {22, 26, 30};
static uint32_t tt_tab, tt_keep[3];    // the weights traffic_types changed (the car table outlives the race), put back by rivals_frontend
static void traffic_types(Ctx *c) {
    const char *e = getenv("RN_TRAFMODELS");
    uint32_t tab = ld(c, 0x734588, 4);
    if (!tab || !e || e[0] != '1') return;
    if (!tt_tab) for (int k = 0; k < 3; k++) tt_keep[k] = ld(c, tab + 0xc90 * TT_ROWS[k] + 0xc60, 4);
    tt_tab = tab;
    for (int k = 0; k < 3; k++) stf(c, tab + 0xc90 * TT_ROWS[k] + 0xc60, 1.0f);
}

// The spacing of the placer (0x59aa60, trackinfo +0xd4/+0xd8, one per direction, 31 m on 520 nodes: 19..21 cars fit, docs/traffic_placement.md) is 20 m in free mode, RN_FREETRAFFIC's
// 22 cars fit. Trackinfo row: 0x441fe0(esi = track), as free_setup. Back to the game's value in any other race (the table outlives the race).
static float ts_keep[2];
static uint32_t ts_row;                // the trackinfo row traffic_spacing changed, put back at the next race's first opponent or by rivals_frontend
static void traffic_spacing_back(Ctx *c) { if (ts_row) stf(c, ts_row + 0xd4, ts_keep[0]), stf(c, ts_row + 0xd8, ts_keep[1]), ts_row = 0; }
static void traffic_spacing(Ctx *c) {
    uint32_t esi = c->r[ESI];
    traffic_spacing_back(c);
    // By value, not presence: 31 m fits 19..21 cars (the default FREE_TRAFFIC 13 x1.5), more need 20 m (docs/traffic_placement.md)
    const char *ft = getenv("RN_FREETRAFFIC");
    if (!free_race || (ft ? atoi(ft) : FREE_TRAFFIC) <= FREE_TRAFFIC) return;
    c->r[ESI] = ld(c, 0x78a2f0, 4);
    uint32_t row = call_guest(c, 0x441fe0, 0, NULL);
    c->r[ESI] = esi, ts_row = row;
    ts_keep[0] = ldf(c, row + 0xd4), ts_keep[1] = ldf(c, row + 0xd8);
    stf(c, row + 0xd4, 20.0f), stf(c, row + 0xd8, 20.0f);
}

// Records 0x779ff8 + 0x54 * level (0x462070 copies them from GLOBALB): shipped, then the personas of this race.
static void rival_tables(Ctx *c, int personas) {
    static uint8_t shipped[10 * 0x54];
    static int saved;
    if (!saved++) memcpy(shipped, G(0x779ff8), sizeof shipped);
    memcpy(G(0x779ff8), shipped, sizeof shipped);
    if (!personas) return;
    char b[512];
    int n = 0;
    for (int lv = 1; lv <= 9; lv++) {
        uint32_t r = 0x779ff8 + 0x54 * lv;
        float accept = ldf(c, r + 0x0c), speed = ldf(c, r + 0x14), nitro = 1;
        if (PERSONA[lv] == NERVOUS) accept = 0.35f, speed *= 0.94f, c->mem[r + 0x50] = c->mem[r + 0x50] > 63 ? 127 : c->mem[r + 0x50] * 2, nitro = 0.7f;
        if (PERSONA[lv] == AGGRESSIVE) speed *= 1.04f, nitro = 0.5f;
        if (PERSONA[lv] == BLOCKER) accept = 1.0f, speed *= 0.98f, c->mem[r + 0x50] /= 2;   // Block ceiling 400 via style 2 (0x44dbd0), a steadier speed lookup, a little slower: it stays in front
        stf(c, r + 0x0c, accept), stf(c, r + 0x14, speed), stf(c, r + 0x34, ldf(c, r + 0x34) * nitro), stf(c, r + 0x38, ldf(c, r + 0x38) * nitro);
        n += snprintf(b + n, sizeof b - n, " L%d %c %.2f %.3f %u %.0fs", lv, PNAME[PERSONA[lv]][0], ldf(c, r + 0x0c), ldf(c, r + 0x14), c->mem[r + 0x50], ldf(c, r + 0x34));
    }
    if (getenv("RN_RIVALLOG") || getenv("RN_FREELOG")) rn_log("rivalai accept speed look nitro:%s", b);
}

// Back in the front end (host/phase.c): the shared tables this file changed for the event get the game's values back. The game resets
// only its race block 0x78a2f0..0x78a427 there (0x431df0); the car table [0x734588], the trackinfo rows and the records 0x779ff8 outlive
// every race (docs/re/gameflow.md), so a race after a WORLD one had its traffic spacing, its BUS/AMBULANCE/FIRETRUCK weights and personas.
void rivals_frontend(Ctx *c) {
    traffic_spacing_back(c);
    if (tt_tab && ld(c, 0x734588, 4) == tt_tab) for (int k = 0; k < 3; k++)   // the table is chunk 0x34600 (0x57c850 sets, 0x57cb7e clears it) st(c, tt_tab + 0xc90 * TT_ROWS[k] + 0xc60, tt_keep[k], 4);
    tt_tab = 0;
    rival_tables(c, 0);
}

// 0x5809c0(id, 2, ride, record, skill, style, index) with esi = the ride slot: stdcall, 7 arguments.
static uint32_t rival_ride(Ctx *c) {
    uint32_t a[7];
    for (int k = 0; k < 7; k++) a[k] = ARG(k);
    if (a[6] <= 1) {
        free_race = rn_free_now != 0;
        persona_on = !c->mem[0x78a33c] && (rivalai() == 2 || (rivalai() && rn_pool()));
        rn_player_car(c), rival_tables(c, persona_on), traffic_types(c), traffic_spacing(c);
    }
    if (rn_free_now) {                                           // host/free.c: free mode's career rivals
        uint32_t e = free_rival(c, a);                           // 0x5809c0 returns the entrant; free_rival picks the level at +0x735
        c->mem[e + 0x736] = (uint8_t)rival_style(c->mem[e + 0x735], c->mem[e + 0x736]);
        if (getenv("RN_FREELOG")) rn_log("rivalai %s level %d style %d", G(e + 0x73c), (int8_t)c->mem[e + 0x735], (int8_t)c->mem[e + 0x736]);
        return e;
    }
    if (!on) { const char *e = getenv("RN_RIVALS"); on = e && e[0] == '0' ? -1 : 1; }
    if (on > 0 && !c->mem[0x78a33c]) {
        if (!ready) catalog(c);
        uint32_t ride = a[2], k = a[6] % NSYN, rec = syn[k];
        if (a[6] <= 1) nused = 0;                                  // the first opponent of a race
        uint32_t tmp = guest_alloc(RIDE_SIZE), skin0 = ld(c, ride + 0x444, 4);
        memcpy(G(tmp), G(ride), RIDE_SIZE);
        // A persona from the game's random stream; its tier from the tuning the game gave this rival.
        int lv = 0; for (int i = 0; i < 9; i++) lv += ld(c, ride + 8 + 4 * i, 4);
        int tier = lv >= 18 ? 3 : lv >= 7 ? 2 : 1;
        if (rn_pool() && tier < 2) tier = 2;                       // ?pool=1: the early rivals are visibly tuned too
        uint32_t s = ld(c, 0x6f227c, 4) ^ (a[6] * 0x85ebca6bu);
        Persona *pick_p = fresh(rnd(&s) % POOL);
        // The persona's car must reach the rating the game chose (0x57f700 can only move levels 0..3): up to 12 personas,
        // the nearest kept.
        char nm[32]; snprintf(nm, sizeof nm, "RN_RIVAL_%u", k);
        float r0 = 0;
        Persona *best = pick_p; float bd = 1e9f;
        for (int tries = 0; tries < 12; tries++) {
            if (tries) { nused--; pick_p = fresh((int)(pick_p - pool + 1 + rnd(&s) % 37) % POOL); }   // one slot per rival
            float d = apply(c, ride, tmp, rec, nm, pick_p, tier, &r0);
            if (d < bd) { bd = d; best = pick_p; }
            if (d <= 12.f) break;
        }
        if (best != pick_p) { apply(c, ride, tmp, rec, nm, pick_p = best, tier, &r0); used[(nused - 1) % NSYN] = (uint32_t)(best - pool); }
        personality(c, ride, pick_p);
        uint32_t skin = ld(c, ride + 0x444, 4) ? ld(c, ride + 0x444, 4) : skin0;
        neon_ride[k] = pick_p->arch == SHOW || pick_p->arch == BOSO ? skin : 0;
        if (rn_pool()) {
            // The driving follows the build: PERSONA is per skill level, so each archetype takes the nearest level of its style (Quick Race gives all rivals one level).
            static const uint8_t STYLE[NARCH] = {[CLEAN] = TIDY, [SHOW] = NERVOUS, [DRIFT] = AGGRESSIVE, [SLEEPER] = TIDY, [STREET] = NERVOUS, [BOSO] = AGGRESSIVE, [VIP] = TIDY, [TRACK] = TIDY};
            int best_lv = (int)a[4], bdl = 99;
            if (a[4] <= 9) for (int l = 1; l <= 9; l++) { int dl = abs(l - (int)a[4]); if (PERSONA[l] == STYLE[pick_p->arch] && dl < bdl) bdl = dl, best_lv = l; }
            a[4] = (uint32_t)best_lv;
            static const uint8_t LIVP[NARCH] = {[CLEAN] = 40, [SHOW] = 100, [DRIFT] = 85, [SLEEPER] = 0, [STREET] = 90, [BOSO] = 90, [VIP] = 15, [TRACK] = 70};
            uint32_t ls = pick_p->seed ^ 0x51ed270bu;
            livery_set(skin, pick_p->car, roll(&ls, LIVP[pick_p->arch]) ? livery_of(pick_p->arch, &ls) : -1);
        }
        car_prefetch(CARS[pick_p->car]);
        if (getenv("RN_RIVALLOG")) {
            float r1; memcpy(&r1, G(ride + 0x428), 4);
            rn_log("rival %u: %s %s %s tier %d rating %.1f -> %.1f", a[6], pick_p->name, CARS[pick_p->car], ARCH[pick_p->arch].name,
                   tier, r0, r1);
            for (int sl = 0; sl < 0x78; sl++) {
                uint32_t key = ld(c, rec + 0x4c + 8 * sl, 4);
                for (int q = 0; key && q < nparts; q++)
                    if (parts[q].key == key && (parts[q].slot == sl || (sl >= 0x26 && sl <= 0x39 && parts[q].slot == 0x1e) ||
                        (sl >= 0x1f && sl <= 0x22 && parts[q].slot == 0x1f) || (sl >= 0x3b && sl <= 0x72 && parts[q].slot == 0x3a))) {
                        if (sl != 3 && sl != 4 && sl != 5 && sl != 0 && sl != 9 && sl != 0x12 && sl != 0x77) rn_log("  %02x %s", sl, G(parts[q].name));
                        break;
                    }
            }
        }
        guest_free(tmp);
        a[5] = rival_style(a[4], a[5]);
    }
    return call_guest(c, 0x5809c0, 7, a);
}

static int n_refill, n_refail, n_rf[5];
static int n_react[3];                 // traffic_behind: yields; traffic_tick: dodges, glued honks
static uint32_t n_tr[5];               // ai_log, car-frames within 60 m: game avoid action, braking, horn; contacts under 2.6 m; flash dark phase (+0x83e set, +0x855 clear)
// RN_AILOG=1: test-only race log (tools/ailog.py sums it up). Every 60 frames, each racer: name, kind, route metres car+0x814, speed car+0x3d0,
// rank (record +0xa), mean |slip angle| in degrees; at once, each change of a racer's action type [[drv+0x3f8]+0x1f8] and each nitro start (CarState car+0x40, +0x3bc, 0x4654f0).
// Guest pointers ai_log follows: a racer list read at the race load can hold stale or half-built links (native SIGSEGV in
// ai_log at the first race frame, ghost run cjump_7 2026-10-31), so every one is checked before it is read.
#define AP(x) ((x) && (x) < GUEST_MEM - 0x1000)
static void ai_log(Ctx *c) {
    static int on = -1;
    static struct { uint32_t car, act, nos, n; float slip; } st_[16];
    if (on < 0) on = getenv("RN_AILOG") != NULL;
    if (!on || !rn_racing()) return;
    static uint32_t draft, race;          // racer-seconds in the game's slipstream this race: car+0x47c (0x426450) above 0.1
    static uint32_t hitcar[32];           // traffic cars in contact with the player (n_tr[3] counts each once)
    if (rn_new_race(&race)) memset(st_, 0, sizeof st_), memset(hitcar, 0, sizeof hitcar), draft = 0;
    uint32_t h = ld(c, 0x7361f8, 4), sec = rn_telem.presents % 60 == 0;
    if (!AP(h)) return;
    char b[640];
    int n = 0, i = 0;
    for (uint32_t r = ld(c, h, 4), k = 0; AP(r) && r != h && k < 200 && i < 16; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), kind = AP(e) ? ld(c, e + 4, 4) : 0, v = ld(c, r + 0x2c, 4), rec = ld(c, r + 0x1c, 4);
        if (kind != 1 && kind != 2) continue;
        uint32_t a = AP(v) ? ld(c, v + 0x3f8, 4) : 0, type = AP(a) ? ld(c, a + 0x1f8, 4) : 99, nos = ld(c, r + 0x3fc, 4);
        if (st_[i].car == r && st_[i].act != type) rn_log("AIEV %u %s act %u", rn_telem.presents, G(e + 0x73c), type);
        if (st_[i].car == r && st_[i].nos != nos && nos && nos != 0x7fffffff) rn_log("AIEV %u %s nos", rn_telem.presents, G(e + 0x73c));
        st_[i].car = r, st_[i].act = type, st_[i].nos = nos;
        draft += sec && ldf(c, r + 0x47c) > 0.1f;
        if (rn_telem.presents % 6 == 0 && ldf(c, r + 0x3d0) > 10) {   // slip angle: 0x464ed0 (esi = CarState, radians on the FPU), as 0x479350 reads it
            uint32_t esi = c->r[ESI], ft = c->ftop;
            c->r[ESI] = r + 0x40, call_guest(c, 0x464ed0, 0, NULL), c->r[ESI] = esi;
            double a2 = c->st[c->ftop];
            fpop(c), c->ftop = ft;
            st_[i].slip += (float)fabs(a2) * 57.296f, st_[i].n++;
        }
        if (sec && n < 560) {
            n += snprintf(b + n, sizeof b - n, " %s:%u:%.0f:%.1f:%d:%.1f", kind == 1 ? "ME" : G(e + 0x73c), kind, ldf(c, r + 0x814), ldf(c, r + 0x3d0), AP(rec) ? c->mem[rec + 0xa] : -1, st_[i].n ? st_[i].slip / st_[i].n : 0);
            st_[i].slip = 0, st_[i].n = 0;
        }
        i++;
    }
    if (n) rn_log("AILOG %u draft %u%s", rn_telem.presents, draft, b);
    {   // traffic reaction, per frame, cars within 60 m of the player: in the game's avoid action (type 3), braking (driver [car+0x30]+0x1e4, written by 0x45e970), horn flag +0x83f; hits = first frame under 2.6 m of the player
        uint32_t me = 0;
        for (uint32_t r = ld(c, h, 4), k = 0; AP(r) && r != h && k < 200 && !me; r = ld(c, r, 4), k++) { uint32_t e = ld(c, r + 0x14, 4); if (AP(e) && ld(c, e + 4, 4) == 1) me = r; }
        for (uint32_t r = ld(c, h, 4), k = 0; me && AP(r) && r != h && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4), d = ld(c, r + 0x30, 4);
            if (!AP(e) || ld(c, e + 4, 4) != 3 || !AP(v) || c->mem[v + 0x4d1]) continue;
            float dist = hypotf(ldf(c, r + 0x50) - ldf(c, me + 0x50), ldf(c, r + 0x54) - ldf(c, me + 0x54));
            uint32_t a = ld(c, v + 0x3f8, 4);
            if (dist < 60) {
                n_tr[0] += AP(a) && ld(c, a + 0x1f8, 4) == 3, n_tr[1] += AP(d) && ldf(c, d + 0x1e4) > 0.3f, n_tr[2] += c->mem[r + 0x83f] != 0, n_tr[4] += c->mem[r + 0x83e] != 0 && c->mem[r + 0x855] == 0;
            }
            int s = 0;
            while (s < 31 && hitcar[s] && hitcar[s] != r) s++;
            if (dist < 2.6f && hitcar[s] != r) hitcar[s] = r, n_tr[3]++;
            else if (dist > 8 && hitcar[s] == r) hitcar[s] = 0;
        }
    }
    if (rn_telem.presents % 300 == 0) {            // traffic: how many, how near, how many models near (entrant ride +0: car type, row name in [0x734588])
        uint32_t tab = ld(c, 0x734588, 4), me = 0, seen[36] = {0};
        int total = 0, parked = 0, near = 0, close = 0, kinds = 0, all = 0;
        for (uint32_t r = ld(c, h, 4), k = 0; AP(r) && r != h && k < 200 && !me; r = ld(c, r, 4), k++) { uint32_t e = ld(c, r + 0x14, 4); if (AP(e) && ld(c, e + 4, 4) == 1) me = r; }
        char names[512], u2s[480] = "";
        int m = 0, u2[4] = {0}, u2m = 0;
        for (uint32_t r = ld(c, h, 4), k = 0; me && AP(r) && r != h && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
            if (!AP(e) || ld(c, e + 4, 4) != 3) continue;
            float d = hypotf(ldf(c, r + 0x50) - ldf(c, me + 0x50), ldf(c, r + 0x54) - ldf(c, me + 0x54));
            uint32_t type = ld(c, e + 0x10, 4);
            total++, parked += AP(v) && c->mem[v + 0x4d1], near += d < 250, close += d < 100;
            {   // UG2 side of the net (census/ug2/roads.md section 8): connector stub x 110..230 y 380..499, bridge x 110..135 y 499..589, UG2 = west of x 135 north of y 589, s28 = section 28 south of the anchor 28:3 x 205..240 y 300..392
                float x = ldf(c, r + 0x50), y = ldf(c, r + 0x54);
                int k2 = x > 110 && x < 230 && y > 380 && y < 499 ? 0 : x > 110 && x < 135 && y >= 499 && y < 589 ? 1 : x < 135 && y >= 589 && y < 3000 ? 2 : x > 205 && x < 240 && y > 300 && y < 392 ? 3 : -1;
                if (k2 >= 0) { u2[k2]++; if (u2m < 440) u2m += snprintf(u2s + u2m, sizeof u2s - u2m, " %d:%.0f,%.0f h%.0f v%.1f", k2, x, y, atan2f(ldf(c, r + 0x94), ldf(c, r + 0x90)) * 57.3f, ldf(c, r + 0x3d4)); }
            }
            if (type < 36 && !(seen[type] & 1)) { seen[type] |= 1, all++; if (m < 480) m += snprintf(names + m, sizeof names - m, " %s", G(tab + 0xc90 * type)); }
            if (type < 36 && d < 250 && !(seen[type] & 2)) seen[type] |= 2, kinds++;
        }
        // Probe (exit: delete when the reset/walls bug is decided): wall body pool [0x72cbf4] and witness pool [0x72cc00] (+0x18 used, +0x1c peak), next body id [[0x736070]+8] (id space 0x840,
        // PATCH 0x466b01), bodies of type 3 with no witness (+0x1a == 0: they free only with their last witness, so each is a leak), the first one's id, |normal z| and distance from the
        // player, and the player's CarCollisionBody [car+0x3c]: +0x1d awake, +0x1b disable count, +0x1a witnesses, car+0x28 mode, cache count car+0x7e0.
        if (me) {
            uint32_t pw = ld(c, 0x72cbf4, 4), pv = ld(c, 0x72cc00, 4), al = ld(c, 0x736070, 4), b = ld(c, me + 0x3c, 4), oid = 0;
            int orph = 0, oflat = 0, n = 0; float onz = 0, od = 0;
            for (uint32_t o = ld(c, 0x779c70, 4); AP(o) && o != 0x779c70 && n < 8192; o = ld(c, o, 4), n++) {
                uint32_t q = o - 4;
                if (c->mem[q + 0x15] != 3 || c->mem[q + 0x1a]) continue;
                uint32_t pl = ld(c, q + 0x60, 4);
                float nz = AP(pl) ? fabsf(ldf(c, pl + 0x78)) : -1;
                if (!orph++) {          // od: metres from the first orphan's box corner to the nearest car (racers and traffic); near 0 = a car still on it, far = left behind
                    oid = ld(c, q + 0x18, 2), onz = nz, od = 1e9f;
                    for (uint32_t r = ld(c, h, 4), k = 0; AP(r) && r != h && k < 200; r = ld(c, r, 4), k++) { float e = hypotf(ldf(c, q + 0x24) - ldf(c, r + 0x50), ldf(c, q + 0x28) - ldf(c, r + 0x54)); if (e < od) od = e; }
                }
                oflat += nz >= 0.7f;
            }
            rn_log("COLLOG %u walls %u peak %u witness %u peak %u nextid %u bodies %d orphans %d flat %d first id %u nz %.2f d %.0f | me awake %u off %u wit %u mode %u cache %u pos %.0f,%.0f,%.0f sp %.1f reset %u", rn_telem.presents, AP(pw) ? ld(c, pw + 0x18, 4) : 0, AP(pw) ? ld(c, pw + 0x1c, 4) : 0,
                   AP(pv) ? ld(c, pv + 0x18, 4) : 0, AP(pv) ? ld(c, pv + 0x1c, 4) : 0, AP(al) ? ld(c, al + 8, 4) : 0, n, orph, oflat, oid, onz, od, AP(b) ? c->mem[b + 0x1d] : 0, AP(b) ? c->mem[b + 0x1b] : 0, AP(b) ? c->mem[b + 0x1a] : 0, ld(c, me + 0x28, 4), ld(c, me + 0x7e0, 4), ldf(c, me + 0x60), ldf(c, me + 0x64), ldf(c, me + 0x68), ldf(c, me + 0x3d4), ld(c, me + 0x884, 4));
        }
        uint32_t bodies = ld(c, 0x736184, 4);       // TrackPolygonSlotPool 0x4412b0: slots in use, high-water mark, cap (docs/openworld/re_coll_pool.md)
        rn_log("REFILLWHY early %d walk %d spacing %d lane %d", n_rf[0], n_rf[1], n_rf[2], n_rf[3]);
        rn_log("TRAFUG2 stub %d bridge %d ug2 %d s28 %d |%s", u2[0], u2[1], u2[2], u2[3], u2s);
        rn_log("TRAFLOG %u cars %d parked %d near250 %d near100 %d models %d models250 %d refill %d fail %d yield %d dodge %d glued %d polys %u polymax %u polycap %u avoidf %u brakef %u honkf %u hits %u flashf %u%s", rn_telem.presents, total, parked, near, close, all, kinds,
               n_refill, n_refail, n_react[0], n_react[1], n_react[2], AP(bodies) ? ld(c, bodies + 0x18, 4) : 0, AP(bodies) ? ld(c, bodies + 0x1c, 4) : 0, AP(bodies) ? ld(c, bodies + 0x2c, 4) : 0, n_tr[0], n_tr[1], n_tr[2], n_tr[3], n_tr[4], rn_telem.presents % 3000 == 0 ? names : "");
    }
}

// Handling (RN_HANDLING=0 / ?handling=0: as shipped; docs/re/physics.md). The OWNER's "rigid": outside drift events 0x4774a0 gives the rear wheels extra grip as the
// slip angle grows (0x4773f0: min(0.35, 2.5 * v/30 * slip), V from all 35 cars' physics +0x284), so at 30 m/s the cap holds from 4 degrees on and the tail will not step out.
// Cap 0x6ffdd4 (.data, its only reader 0x477473..) goes to HANDLING_REAR, for every car. Yaw damping 0x479350 runs in drift events only: not touched.
#define HANDLING_REAR 0.18f
static void handling_data(Ctx *c) {
    static int done;
    if (done++) return;
    const char *e = getenv("RN_HANDLING");
    if (e && e[0] == '0') return;
    float rear = HANDLING_REAR;
    memcpy(G(0x6ffdd4), &rear, 4);
}

// Traffic near the player in free mode (RN_TRAFREFILL=1 / ?trafrefill=1: on, and the page turns host/free.c free_tmove off with RN_FREETMOVE=0; off until measured on the Mac). 0x598600 parks a car
// each time a move fails, and free_tmove tries one spot a second: a node with no lane (0x5995e0 = -1) or next to another car and it gives up, so 17 of 19 cars stood parked with
// none within 250 m (autopilot on 1001, frames 3900..4800). Here, every 12 frames while fewer than REFILL_NEAR cars are within 250 m, the car that is parked, past 450 m, or
// behind and past 160 m tries up to 8 nodes 150..650 m + 1 s of speed ahead on the road (0x4563d0), at least 150 m from the player, 18 m from every car that drives; then the
// Free Run move's own tail, as free_tmove: lane 0x5995e0, speed 0x42adf0, 0x59a7c0 on the teleporter [[0x7361f8]+0x2f0] (ecx at 0x420c77).
#define REFILL_NEAR 14
#define REFILL_MIN 150   // m from the player for a refill spot
// Frozen traffic (w_h, 240 s: 21% of traffic samples did not move, a queue of 10 cars for up to 176 s, 57 cars braking to 6.1 m/s at one spot): the refill below only picks
// parked, far (>450 m) or behind-the-player cars, and counts a frozen car as "near", so it was never recycled. Speed [car+0x3d4] stays 6.1 on a blocked car (w_i), so it is the
// position that counts: a car that stays within 3 m of where it was seen for STUCK_PRESENTS presents (about 10 s, this runs every 12) and is 200 m or more from the player (as free.c KEEP_M: never vanish on screen) is
// picked like a parked one; a pick that cannot be placed starts its timer again (frozen_clear), so it cannot hold the refill.
#define STUCK_PRESENTS 600
static uint32_t still_r[64], still_t[64];
static float still_x[64], still_y[64];
static int frozen_car(uint32_t r, float x, float y) {
    int free_i = -1;
    for (int i = 0; i < 64; i++) {
        if (still_r[i] == r) {
            if (hypotf(x - still_x[i], y - still_y[i]) >= 3.0f) { still_x[i] = x, still_y[i] = y, still_t[i] = rn_telem.presents; return 0; }
            return rn_telem.presents - still_t[i] >= STUCK_PRESENTS;
        }
        if (!still_r[i] && free_i < 0) free_i = i;
    }
    if (free_i >= 0) still_r[free_i] = r, still_x[free_i] = x, still_y[free_i] = y, still_t[free_i] = rn_telem.presents;
    return 0;
}
static void frozen_clear(uint32_t r) { for (int i = 0; i < 64; i++) if (still_r[i] == r) still_r[i] = 0; }
static void traffic_refill(Ctx *c, uint32_t h, uint32_t me) {
    static int off = -1;
    static uint32_t pair, seed = 0x2f11e0d5;
    if (off < 0) { const char *e = getenv("RN_TRAFREFILL"); off = !e || e[0] != '1'; }   // RN_TRAFREFILL=1 (?trafrefill=1, ?pool=1); built for WORLD (OWNER 2026-11-03)
    uint32_t tele = ld(c, h + 0x2f0, 4);
    if (off > 0 || !free_race || rn_telem.presents % 12 || !tele) return;
    float px = ldf(c, me + 0x50), py = ldf(c, me + 0x54), vx = ldf(c, me + 0x70), vy = ldf(c, me + 0x74), sp = hypotf(vx, vy);
    uint32_t pick = 0;
    int prio = 0, near = 0;
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
        if (!e || ld(c, e + 4, 4) != 3 || !v) continue;
        float dx = ldf(c, r + 0x50) - px, dy = ldf(c, r + 0x54) - py, d = hypotf(dx, dy);
        int parked = c->mem[v + 0x4d1];
        if (parked) frozen_clear(r);   // parked time is not standing-still time (a car un-parked later would be recycled at once)
        int frozen = !parked && frozen_car(r, ldf(c, r + 0x50), ldf(c, r + 0x54)) && d >= 200;
        near += d < 250 && !parked && !frozen;
        int p = parked || frozen ? 3 : d > 450 ? 2 : sp > 2 && dx * vx + dy * vy < 0 && d > 160 ? 1 : 0;
        if (p > prio) prio = p, pick = r;
    }
    if (!pick || (near >= REFILL_NEAR && prio < 3)) return;   // a parked car always goes back on the road
    if (!pair) pair = guest_alloc(8);
    uint32_t zero = 0, ft = c->ftop;
    c->r[EAX] = me; uint32_t sec = call_guest(c, 0x428150, 1, &zero);
    c->r[EAX] = me; uint32_t node = call_guest(c, 0x428160, 1, &zero);
    st(c, pair, sec, 4), st(c, pair + 4, node, 4);
    c->r[EAX] = pair;
    if (!sec || !node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { c->ftop = ft; n_refail++; n_rf[0]++; frozen_clear(pick); return; }
    int along = ldf(c, node + 0xc) * vx + ldf(c, node + 0x10) * vy >= 0;
    for (int t = 0; t < 8; t++) {              // farther each try (a stretch can lack lanes for 1 km); the last two behind the player
        float m = REFILL_MIN + 80.0f * (t % 6) + (float)(rnd(&seed) % 100) + (t < 6 ? sp : 0);
        uint32_t a[5] = {pair, 1, 0, (uint32_t)(t < 6 ? along : !along), 0};
        memcpy(&a[2], &m, 4);
        st(c, pair, sec, 4), st(c, pair + 4, node, 4);
        c->r[ECX] = sec, c->r[EAX] = node;
        call_guest_cdecl(c, 0x4563d0, 5, a);
        uint32_t n2 = ld(c, pair + 4, 4);
        c->r[EAX] = pair;
        if (n2 == node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { n_rf[1]++; continue; }
        float nx = ldf(c, n2), ny = ldf(c, n2 + 4);
        int ok = hypotf(nx - px, ny - py) >= REFILL_MIN;
        for (uint32_t o = ld(c, h, 4), j = 0; o != h && j < 200 && ok; o = ld(c, o, 4), j++) {
            uint32_t v = ld(c, o + 0x2c, 4);
            float od = hypotf(ldf(c, o + 0x50) - nx, ldf(c, o + 0x54) - ny);
            ok = o == pick || (v && ld(c, ld(c, o + 0x14, 4) + 4, 4) == 3 && c->mem[v + 0x4d1]) || od >= 18;
        }
        if (!ok) { n_rf[2]++; continue; }
        c->r[ECX] = tele;
        uint32_t side = call_guest(c, 0x59aea0, 0, NULL) & 0xff, la[2] = {n2, side};
        c->r[ECX] = tele;
        int lane = (int)call_guest(c, 0x5995e0, 2, la);
        if (lane == -1) { n_rf[3]++; continue; }
        c->r[EAX] = n2, c->r[ECX] = (uint32_t)lane;
        call_guest(c, 0x42adf0, 0, NULL);
        float v = (float)c->st[c->ftop];
        fpop(c);                               // a pop, not ftop = ft: see free_tmove
        uint32_t p[7] = {pick, n2, 0, (uint32_t)lane, 0x41c4b127, 0, 0};
        memcpy(&p[5], &v, 4);
        c->r[ECX] = tele;
        call_guest(c, 0x59a7c0, 7, p);
        c->ftop = ft, n_refill++;
        frozen_clear(pick);
        return;
    }
    c->ftop = ft, n_refail++;
    frozen_clear(pick);
}

// Traffic that reacts (RN_TRAFYIELD=0 / ?trafyield=0: as shipped; docs/re/traffic_limits.md). Traffic only ever looks ahead: its finder 0x453920 takes the nearest car ahead in
// its lane, so a player closing from behind is never seen (that case is traffic_behind below) and a head-on is seen at the last moment. The neighbour list (0x57a910) is empty
// between AI updates, so this reads positions and velocities: a traffic car with the player on its line (under 2 m aside), head-on 0.6..3 s from impact at 10 m/s or more, takes
// a neighbour lane with no car beside it, as its own avoid update does (0x453c60: lane test 0x5a7700, ctx+0x394, route state ctx+0x398 = 1); glued behind it (under 12 m,
// closing under 5 m/s, above 8 m/s) it stays. Both sound the horn with the light flag (0x429100, thiscall on the car). Outside the career, as the personas; each car once in YIELD_WAIT frames.
#define YIELD_WAIT 240
static int trafyield_off(void) {
    static int off = -1;
    if (off < 0) { const char *e = getenv("RN_TRAFYIELD"); off = e && e[0] == '0'; }
    return off;
}
// PATCH 0x45399f (cave 0x44dd21: jmp [SCREEN_ADDR+0x98]): the finder 0x453920 asks 0x44f470 for the nearest car ahead in its lane (thiscall ecx = ctx, cdecl lane, lateral, range, &out0,
// &out1). When that finds nothing, a traffic car (driver kind 3) in a lane 11..16 looks at the rows BEHIND it in the neighbour list (own+1 .. [ctx+4]-1; row = ctx + 8 + i * 0x38,
// +4 speed difference along the route (other - own), +8 lateral half-extent, +0xc longitudinal half-extent, +0x10 route position, +0x18 + 4 * (lane - 11) lateral offset in each
// lane, +0x34 node). The player closing at 5 m/s or more (0x6cc954, the avoid action's own "pulling away" limit) and 0.6..2.5 s from impact, in the car's lane (the
// lateral rule of 0x44f470, 0x44f50a..0x44f51d), makes it take lane +-1 (random first): 0x5a7700 allows it as in 0x453ba0, 0x44f470 finds nothing ahead there within act+0x208 (30 m,
// [0x6b76e0]) as 0x453bfc asks, and no row behind overlaps that lane within 10 m. The lane goes to ctx+0x394 and the route state ctx+0x398 = 1 as 0x453e21..0x453e4b does, then the
// horn with the light flag (0x429100). It returns 0 in every case, so the finder takes no action and the Avoid action (which ends at once for a car behind, 0x453a60) never sees it.
// The out values are put back as the first call left them. RN_TRAFYIELD=0: the original call only.
static float row_lat(Ctx *c, uint32_t row, int lane) { return ldf(c, row + lane * 4 - 0x14); }
static int row_overlaps(Ctx *c, uint32_t own, uint32_t row, int lane, float lat) {
    return fabsf(row_lat(c, row, lane) - lat) <= ldf(c, 0x6b7604) + ldf(c, own + 8) + ldf(c, row + 8);
}
static float row_gap_behind(Ctx *c, uint32_t own, uint32_t row) {
    return ldf(c, own + 0x10) - ldf(c, own + 0xc) - ldf(c, row + 0x10) - ldf(c, row + 0xc);
}
static int node_is_player(Ctx *c, uint32_t node) {   // 0x57a6b0: the body node is a car (kind 6) whose driver kind is 1
    uint32_t ent = node ? ld(c, node + 0x1d4, 4) : 0, car = ent ? ld(c, ent + 0x90, 4) : 0, e = car ? ld(c, car + 0x14, 4) : 0;
    return e && ld(c, ent + 0x1c + 8, 4) == 6 && ld(c, e + 4, 4) == 1;   // 0x647b70: ecx = ent + 0x1c (embedded, not a pointer), returns [ecx + 8]
}
static uint32_t traffic_behind(Ctx *c) {
    static uint32_t seed = 0x7b3d19c5;
    uint32_t a[5], ctx = c->r[ECX], ft = c->ftop;
    for (int k = 0; k < 5; k++) a[k] = ARG(k);
    uint32_t hit = call_guest_cdecl(c, 0x44f470, 5, a);
    c->ftop = ft;
    if (hit || trafyield_off()) return hit;
    // ld() does not bound its address: a race 4 ghost (2026-11-06, p1x6) died here on a car whose pointers were not guest memory.
    uint32_t car = AP(ctx) ? ld(c, ctx, 4) : 0, drv = AP(car) ? ld(c, car + 0x14, 4) : 0;
    if (!AP(drv)) return 0;
    int own = (int8_t)c->mem[ctx + 0x388], n = (int)ld(c, ctx + 4, 4), lane = (int)a[0];
    if ( ld(c, drv + 4, 4) != 3 || lane < 11 || lane > 16 || own < 0 || n > 16 || own + 1 >= n) return 0;
    uint32_t orow = ctx + 8 + own * 0x38;
    float lat;
    memcpy(&lat, &a[1], 4);
    int hitrow = 0;
    float gap = 0, rel = 0;
    for (int i = own + 1; i < n && !hitrow; i++) {
        uint32_t row = ctx + 8 + i * 0x38;
        gap = row_gap_behind(c, orow, row), rel = ldf(c, row + 4);
        hitrow = node_is_player(c, ld(c, row + 0x34, 4)) && row_overlaps(c, orow, row, lane, lat) && rel >= ldf(c, 0x6cc954) && gap > 0 && gap / rel >= 0.6f && gap / rel <= 2.5f;
    }
    if (!hitrow) return 0;
    uint32_t path = ld(c, ctx + 0x3a8, 4), seg = ld(c, orow + 0x30, 4), elem = path && seg < ld(c, path + 4, 4) ? ld(c, path + 8 + 4 * seg, 4) : 0;
    uint32_t o0 = ld(c, a[3], 4), o1 = ld(c, a[4], 4), to = 0, dir = rnd(&seed) & 2, ecx = c->r[ECX];
    for (int t = 0; t < 2 && !to && elem; t++, dir ^= 2) {
        int want = lane + (int)dir - 1;
        if (want < 11 || want > 16) continue;
        uint32_t one[2] = {(uint32_t)lane, car};
        c->r[EAX] = (uint32_t)want, c->r[ECX] = elem;
        int ok = call_guest(c, 0x5a7700, 2, one) & 0xff;   // 0x453ba0: eax = the lane, ecx = the route element of the car's segment, stack: current lane, car
        c->r[ECX] = ctx;
        uint32_t probe[5] = {(uint32_t)want, 0, ld(c, 0x6b76e0, 4), a[3], a[4]};
        ok = ok && !call_guest_cdecl(c, 0x44f470, 5, probe);   // nothing ahead in that lane within 30 m
        st(c, a[3], o0, 4), st(c, a[4], o1, 4);
        c->ftop = ft;
        for (int i = own + 1; ok && i < n; i++) {
            uint32_t row = ctx + 8 + i * 0x38;
            ok = !(row_overlaps(c, orow, row, want, 0.0f) && row_gap_behind(c, orow, row) < 10);
        }
        if (ok) to = (uint32_t)want;
    }
    c->r[ECX] = ecx;
    if (!to) return 0;
    st(c, ctx + 0x394, to, 4), st(c, ctx + 0x398, 1, 4), st(c, ctx + 0x39c, 0, 4), st(c, ctx + 0x3a0, 0, 4), c->mem[ctx + 0x3a4] = 0;
    uint32_t honk[6] = {0x3e99999a, 0x3e19999a, 0x3e99999a, 1, 1, 1};              // 0.3, 0.15, 0.3 s; lights, horn, gap
    c->r[ECX] = car, call_guest(c, 0x429100, 6, honk);
    c->r[ECX] = ecx, c->ftop = ft;
    n_react[0]++;
    if (getenv("RN_FREELOG") || getenv("RN_RIVALLOG"))
        rn_log("trafreact yield %08x: lane %d -> %u, gap %.1f m, rel %.1f m/s, frame %u", car, lane, to, gap, rel, rn_telem.presents);
    return 0;
}

// Rival stuck test (docs/re/ai_stuck.md, lalo): the finders 0x451b00.. call a rival stuck after [0x6b7680] = 0.4 s under [0x6b7684] = 5.0 m/s and then
// reverse at prio 500; 27-38 % of the entries happen above 5 m/s. Data floats read only by the stuck finders (3 timer reads, 5 speed reads in the exe).
// RN_AI_STUCK=1 (?aistuck=1): 1.5 s and 3.0 m/s (WORLD's default 2026-11-05, retired); else the factory 0.4 s / 5.0 m/s, written every present.
static void ai_tune(Ctx *c) {
    static int stuck = -1;
    if (stuck < 0) stuck = getenv("RN_AI_STUCK") ? atoi(getenv("RN_AI_STUCK")) : 0;
    int on = stuck == 1;
    st(c, 0x6b7680, on ? 0x3fc00000 : 0x3ecccccd, 4), st(c, 0x6b7684, on ? 0x40400000 : 0x40a00000, 4);
}

// RN_AILOG: per driver profile, cars and mean speed of those moving; lane changes per 600 presents, all and in front of the player within 40 m.
int traffic_profile(uint32_t ai);   // host/free.c
// RN_AILOG probe: every 600 presents, the cars that moved under 3 m since the last one: what holds each (nearest car in a 3 m wide corridor 20 m ahead of its nose), how far it sits from its road's line.
static void traffic_jam_log(Ctx *c, uint32_t h, uint32_t me) {
    static struct { uint32_t r; float x, y; } was[64];
    static uint32_t race;
    if (rn_new_race(&race)) memset(was, 0, sizeof was);
    int frozen = 0, heads = 0, fol = 0, mutual = 0, side = 0, byp = 0, byr = 0, wr = 0, shown = 0, wn = 0;
    uint32_t cars[80], lead[80]; int isf[80]; float X[80], Y[80], FX[80], FY[80];
    int n = 0;
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200 && n < 80; r = ld(c, r, 4), k++) {
        if (!ld(c, r + 0x14, 4)) continue;
        cars[n] = r, X[n] = ldf(c, r + 0x50), Y[n] = ldf(c, r + 0x54), FX[n] = ldf(c, r + 0x90), FY[n] = ldf(c, r + 0x94), lead[n] = 0, isf[n] = 0, n++;
    }
    for (int i = 0; i < n; i++) {
        uint32_t r = cars[i], e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
        if (ld(c, e + 4, 4) != 3 || !v || c->mem[v + 0x4d1]) continue;
        int j = 0;
        while (j < 64 && was[j].r != r) j++;
        if (j < 64 && hypotf(X[i] - was[j].x, Y[i] - was[j].y) < 3) isf[i] = 1;
        float best = 20;
        for (int o = 0; o < n; o++) {
            if (o == i) continue;
            float dx = X[o] - X[i], dy = Y[o] - Y[i], al = dx * FX[i] + dy * FY[i], la = fabsf(dx * FY[i] - dy * FX[i]);
            if (al > 0 && al < best && la < 3) best = al, lead[i] = cars[o];
        }
    }
    for (int i = 0; i < n; i++) {
        if (!isf[i]) continue;
        frozen++;
        uint32_t r = cars[i], v = ld(c, r + 0x2c, 4), a = ld(c, v + 0x3f8, 4), ft = c->ftop, zero = 0;
        c->r[EAX] = r; uint32_t node = call_guest(c, 0x428160, 1, &zero);
        c->ftop = ft;
        float co = node ? fabsf(ldf(c, node + 0xc) * FX[i] + ldf(c, node + 0x10) * FY[i]) / fmaxf(1e-3f, hypotf(ldf(c, node + 0xc), ldf(c, node + 0x10))) : -1;
        side += co >= 0 && co < 0.85f;
        if (!lead[i]) {
            heads++;
            uint32_t ob = a && ld(c, a + 0x1f8, 4) == 3 ? ld(c, a + 0x200, 4) : 0, ob2 = ob && ob < GUEST_MEM - 0x200 ? ld(c, ob + 0x1d4, 4) : 0, orc = ob2 && ob2 < GUEST_MEM - 0x100 ? ld(c, ob2 + 0x90, 4) : 0;
            int ok = orc && orc < GUEST_MEM - 0x400, live = 0;
            for (int o = 0; ok && o < n; o++) live |= cars[o] == orc;
            float odx = ok ? ldf(c, orc + 0x50) - X[i] : 0, ody = ok ? ldf(c, orc + 0x54) - Y[i] : 0;
            uint32_t oe = ok ? ld(c, orc + 0x14, 4) : 0;
            if (shown++ < 6) rn_log("TRAFHEAD %.0f %.0f cos %.2f act %u target %.1f gain %.1f owner %d me %.0f m obstacle %08x rec %08x live %d kind %d dist %.1f along %.1f aside %.1f facing %.2f speed %.1f", X[i], Y[i], co, a ? ld(c, a + 0x1f8, 4) : 0, a ? ldf(c, a + 0x1e4) : 0, a ? ldf(c, a + 0x1ec) : 0, a ? c->mem[a + 0x1f0] : -1, hypotf(X[i] - ldf(c, me + 0x50), Y[i] - ldf(c, me + 0x54)), ob, ok ? orc : 0, live, oe && oe < GUEST_MEM - 8 ? (int)ld(c, oe + 4, 4) : -1, hypotf(odx, ody), odx * FX[i] + ody * FY[i], odx * FY[i] - ody * FX[i], ok ? ldf(c, orc + 0x90) * FX[i] + ldf(c, orc + 0x94) * FY[i] : 0, ok ? ldf(c, orc + 0x3d4) : 0);
            continue;
        }
        fol++;
        uint32_t le = ld(c, lead[i] + 0x14, 4);
        int kind = le ? ld(c, le + 4, 4) : 0;
        byp += kind == 1, byr += kind == 2;
        for (int o = 0; o < n; o++) if (cars[o] == lead[i]) mutual += lead[o] == r, wr += FX[o] * FX[i] + FY[o] * FY[i] < -0.5f;
    }
    for (int i = 0; i < n && wn < 64; i++) if (ld(c, ld(c, cars[i] + 0x14, 4) + 4, 4) == 3) was[wn].r = cars[i], was[wn].x = X[i], was[wn].y = Y[i], wn++;
    rn_log("TRAFJAM frozen %d heads %d follow %d mutual %d facing %d off-line %d behind-player %d behind-rival %d", frozen, heads, fol, mutual, wr, side, byp, byr);
}
static void traffic_prof_log(Ctx *c, uint32_t h, uint32_t me) {
    static int on = -1, lc, cuts;
    static uint32_t car[64], was[64], t;
    if (on < 0) on = getenv("RN_AILOG") != NULL;
    if (!on) return;
    static int hist[6], act3, seen_cars;
    static uint32_t race;   // every count here is this race's
    if (rn_new_race(&race)) lc = cuts = act3 = seen_cars = 0, t = 0, memset(car, 0, sizeof car), memset(was, 0, sizeof was), memset(hist, 0, sizeof hist);
    int n[5] = {0}; float sum[5] = {0}, mx = ldf(c, me + 0x50), my = ldf(c, me + 0x54), mvx = ldf(c, me + 0x70), mvy = ldf(c, me + 0x74), ms = hypotf(mvx, mvy);
    int i = 0;
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200 && i < 64; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
        if (!e || ld(c, e + 4, 4) != 3 || !v || c->mem[v + 0x4d1]) continue;
        uint32_t lane = ld(c, v + 0x2c + 0x394, 4);
        float dx = ldf(c, r + 0x50) - mx, dy = ldf(c, r + 0x54) - my, along = ms > 1 ? (dx * mvx + dy * mvy) / ms : -1;
        if (car[i] == r && was[i] != lane) lc++, cuts += along > 0 && hypotf(dx, dy) < 40;
        car[i] = r, was[i] = lane, i++;
        int p = traffic_profile(v) + 1;
        float sp = hypotf(ldf(c, r + 0x70), ldf(c, r + 0x74));
        n[p]++, sum[p] += sp;
        hist[sp < 2 ? 0 : sp < 6.5f ? 1 : sp < 12 ? 2 : sp < 20 ? 3 : sp < 27 ? 4 : 5]++, seen_cars++;
        uint32_t a = ld(c, v + 0x3f8, 4);
        act3 += a && ld(c, a + 0x1f8, 4) == 3;
    }
    if ((t += 6) < 600) return;
    t = 0;
    rn_log("TRAFSPEED <2 %d <6.5 %d <12 %d <20 %d <27 %d more %d avoid %d of %d", hist[0], hist[1], hist[2], hist[3], hist[4], hist[5], act3, seen_cars);
    memset(hist, 0, sizeof hist), act3 = seen_cars = 0;
    traffic_jam_log(c, h, me);
    rn_log("TRAFPROF lc %d cuts %d n %d %d %d %d %d sp %.1f %.1f %.1f %.1f %.1f", lc, cuts, n[0], n[1], n[2], n[3], n[4], n[0] ? sum[0] / n[0] : 0, n[1] ? sum[1] / n[1] : 0, n[2] ? sum[2] / n[2] : 0, n[3] ? sum[3] / n[3] : 0, n[4] ? sum[4] / n[4] : 0);
    lc = cuts = 0;
}
// Traffic paint (OWNER 2026-11-04, "flat, lifeless"): every traffic body uses the light material TRAFFIC (GLOBALB 0x135200, hash 0x19e0ecbe): EnvmapMin 0.29, EnvmapMax 0, diffuse 0.68..1.0, while the METPAINT
// records have Min ~1.0, Max ~0.15, diffuse 0.3..1.2. Here TRAFFIC takes a slightly duller METPAINT in place; 0x40fae0 reads the record at each draw. Records: list [0x743c18], next +0, hash +0xc. RN_TRAFPAINT=0: as shipped.
static void traffic_paint(Ctx *c) {
    static int off = -1;
    if (off < 0) { const char *e = getenv("RN_TRAFPAINT"); off = e && e[0] == '0'; }
    if (off || rn_telem.presents % 300) return;
    uint32_t h = ld(c, 0x743c18, 4);
    for (uint32_t m = h, k = 0; m && m != 0x743c18 && k < 300; m = ld(c, m, 4), k++) {
        if (ld(c, m + 0xc, 4) != 0x19e0ecbe) continue;
        stf(c, m + 0x30, 0.45f), stf(c, m + 0x40, 1.1f), stf(c, m + 0x5c, 0.8f), stf(c, m + 0x6c, 1.1f), stf(c, m + 0x58, 3.0f);
        stf(c, m + 0x7c, 0.35f), stf(c, m + 0x80, 0.85f), stf(c, m + 0x90, 0.13f);
        return;
    }
}
void traffic_tick(Ctx *c) {
    static uint32_t seed = 0x51ed2701;
    static struct { uint32_t car, frame; } seen[32];
    static uint32_t race;   // this race's frozen-car timers, yield stamps and counters (a rebuilt list can reuse node addresses)
    if (rn_new_race(&race)) {
        memset(seen, 0, sizeof seen), memset(still_r, 0, sizeof still_r);
        n_refill = n_refail = 0, memset(n_rf, 0, sizeof n_rf), memset(n_react, 0, sizeof n_react), memset(n_tr, 0, sizeof n_tr);
    }
    ai_log(c);
    handling_data(c);
    ai_tune(c);
    traffic_paint(c);
    if (trafyield_off() || rn_telem.presents % 6 || !rn_racing() || c->mem[0x78a33c]) return;
    uint32_t h = ld(c, 0x7361f8, 4), me = 0;
    for (uint32_t r = h ? ld(c, h, 4) : 0, k = 0; r && r != h && k < 200 && !me; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (e && ld(c, e + 4, 4) == 1) me = r;
    }
    if (!me) return;
    traffic_refill(c, h, me);
    traffic_prof_log(c, h, me);
    float mx = ldf(c, me + 0x50), my = ldf(c, me + 0x54), mvx = ldf(c, me + 0x70), mvy = ldf(c, me + 0x74);
    if (mvx * mvx + mvy * mvy < 64) return;
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
        if (!e || ld(c, e + 4, 4) != 3 || !v || c->mem[v + 0x4d1]) continue;
        float x = ldf(c, r + 0x50), y = ldf(c, r + 0x54), vx = ldf(c, r + 0x70), vy = ldf(c, r + 0x74), sp = sqrtf(vx * vx + vy * vy);
        if (sp < 2 || fabsf(mx - x) > 90 || fabsf(my - y) > 90) continue;
        uint32_t ctx = v + 0x2c, a = ld(c, v + 0x3f8, 4), lane = ld(c, ctx + 0x394, 4);
        if (!a || ld(c, a + 0x1f8, 4) == 3 || ld(c, a + 0x1f8, 4) == 0x12) continue;   // already avoiding, or at a junction
        if (lane < 11 || lane > 16) continue;
        float along = ((mx - x) * vx + (my - y) * vy) / sp, off = ((mx - x) * vy - (my - y) * vx) / sp, mine = (mvx * vx + mvy * vy) / sp;
        float gap = fabsf(along) - 5, rel = along < 0 ? mine - sp : sp - mine;  // rel > 0 closes the gap
        if (gap <= 0 || fabsf(off) > 2) continue;
        int dodge = along > 0 && mine < 0 && rel >= 10 && gap / rel >= 0.6f && gap / rel <= 3.0f;
        int glued = along < 0 && gap < 12 && fabsf(rel) < 5;
        if (!dodge && !glued) continue;
        int s = 0;
        while (s < 31 && seen[s].car && seen[s].car != r) s++;
        if (seen[s].car == r && rn_telem.presents < seen[s].frame + YIELD_WAIT) continue;
        seen[s].car = r, seen[s].frame = rn_telem.presents;
        int beside = 0;                        // any car next to it (0x453ba0's scan reads the neighbour list, empty here)
        for (uint32_t o = ld(c, h, 4), j = 0; o != h && j < 200; o = ld(c, o, 4), j++) {
            float ox = ldf(c, o + 0x50) - x, oy = ldf(c, o + 0x54) - y, oa = (ox * vx + oy * vy) / sp, os = fabsf(ox * vy - oy * vx) / sp;
            beside |= o != r && oa > -10 && oa < 25 && os > 1.5f && os < 6;
        }
        // 0x5a7700 is 0x453ba0's lane test: eax = lane, ecx = a path element (as 0x44efd0: [path + 8 + 4 * [path + 0xb8]], the first when that index is -1), stack: current lane, car.
        uint32_t path = ld(c, ctx + 0x3a8, 4), at = path ? ld(c, path + 0xb8, 4) : 0, elem = path && ld(c, path + 4, 4) ? ld(c, path + 8 + 4 * (at < ld(c, path + 4, 4) ? at : 0), 4) : 0, to = 0, dir = rnd(&seed) & 2;
        for (int t = 0; t < 2 && !to && !glued && !beside && elem; t++, dir ^= 2) {
            uint32_t want = lane + dir - 1, one[2] = {lane, r};
            c->r[EAX] = want, c->r[ECX] = elem;
            if (call_guest(c, 0x5a7700, 2, one) & 0xff) to = want;
        }
        if (to) st(c, ctx + 0x394, to, 4), st(c, ctx + 0x398, 1, 4), st(c, ctx + 0x39c, 0, 4), st(c, ctx + 0x3a0, 0, 4), c->mem[ctx + 0x3a4] = 0;
        if (!to && !glued && !dodge) continue;
        uint32_t honk[6] = {0x3e99999a, 0x3e19999a, 0x3e99999a, 1, 1, 1};              // 0.3, 0.15, 0.3 s; lights, horn, gap
        c->r[ECX] = r, call_guest(c, 0x429100, 6, honk);
        n_react[dodge ? 1 : 2]++;
        if (getenv("RN_FREELOG") || getenv("RN_RIVALLOG"))
            rn_log("trafreact %s %08x: lane %u -> %u, gap %.1f m, rel %.1f m/s, off %.1f m, frame %u", dodge ? "dodge" : "glued", r, lane, to, gap, rel, off, rn_telem.presents);
    }
}

// RN_CAR=<CAR>[:tier[:n]] (?car= on the web): the player's car in every race is the n-th (default 0) persona of that car model
// (CARS above) built at tier 1..3 (default 2; 3 = kits, wings, vinyls), by the same build/apply as a rival, on the player's ride
// (entrant table [0x78a418], 0x750 each, +4 kind 1, +0x10 RideInfo) before the race start builds the cars. The look matrix
// (build/carpack/matrix.sh) needs other cars than the profile's. Called by rival_ride for each race's first opponent (0x4b4321, inside
// 0x4b4040): the player is registered by then and the skin composite 0x5a8a50 of the cars has not run (a call at the race start, 0x422a86,
// was too late: the player's body drew black in 6 of 9 cells).
void rn_player_car(Ctx *c) {
    const char *e = getenv("RN_CAR");
    if (!e) return;
    char nm[16] = {0}; int tier = 2, n = 0;
    sscanf(e, "%15[^:]:%d:%d", nm, &tier, &n);
    int car = -1;
    for (int k = 0; k < 20; k++) if (!strcmp(nm, CARS[k])) car = k;
    if (car < 0 || tier < 1 || tier > 3) { rn_log("RN_CAR: \"%s\" is not CAR[:tier 1..3[:n]]", e); return; }
    uint32_t cnt = ld(c, 0x78a41c, 4), t = ld(c, 0x78a418, 4);
    for (uint32_t i = 0; i < cnt; i++) {
        if (ld(c, t + 0x750 * i + 4, 4) != 1) continue;
        if (!ready) catalog(c);
        if (getenv("RN_CARLIST")) {   // which persona n of a model is dark or light: the paint's own RGB of the first 6 personas of every model
            uint32_t ride = t + 0x750 * i + 0x10, scratch = guest_alloc(RIDE_SIZE), tmp = guest_alloc(RIDE_SIZE);
            for (int k = 0; k < 20; k++) for (int j = 0, q = 0; j < POOL && q < 6; j++) {
                if (pool[j].car != k) continue;
                memcpy(G(scratch), G(ride), RIDE_SIZE); memcpy(G(tmp), G(ride), RIDE_SIZE);
                float r0; apply(c, scratch, tmp, syn[0], "RN_PLAYER", &pool[j], 3, &r0);
                for (int sl = 0; sl < 0x78; sl++) {
                    uint32_t key = ld(c, syn[0] + 0x4c + 8 * sl, 4);
                    for (int u = 0; key && u < nparts; u++)
                        if (parts[u].key == key && parts[u].slot == sl && parts[u].kind >= K_GLOSS && parts[u].kind <= K_CUSTOM)
                            rn_log("RN_CARLIST %s n=%d %s %s rgb %u,%u,%u lum %.2f", CARS[k], q, ARCH[pool[j].arch].name, G(parts[u].name), parts[u].rgb[0], parts[u].rgb[1], parts[u].rgb[2],
                                   (0.2126 * parts[u].rgb[0] + 0.7152 * parts[u].rgb[1] + 0.0722 * parts[u].rgb[2]) / 255);
                }
                q++;
            }
            guest_free(scratch); guest_free(tmp);
        }
        const Persona *pe = NULL;
        for (int j = 0, q = 0; j < POOL && !pe; j++) if (pool[j].car == car && q++ == n) pe = &pool[j];
        if (!pe) { rn_log("RN_CAR: %s has no persona %d", nm, n); return; }
        uint32_t ride = t + 0x750 * i + 0x10, tmp = guest_alloc(RIDE_SIZE);
        memcpy(G(tmp), G(ride), RIDE_SIZE);
        float r0;
        apply(c, ride, tmp, syn[0], "RN_PLAYER", pe, tier, &r0);
        guest_free(tmp);
        rn_log("RN_CAR: player is %s tier %d, persona %s (%s)", nm, tier, pe->name, ARCH[pe->arch].name);
        return;
    }
}

// BRIDGE: every racer at the player's car detail (OWNER 2026-10-27: the rivals as well made as the Supra). 0x56dc30 draws
// a car with model BODY_A..D by its size on screen, s = 3 * [view+0xc] / (distance - 3) (0x545180): s >= 120 = A,
// >= 45 = B, >= 20 = C, else D (table 0x6b5dec, from the minimum LOD args 10 / 11 up), and ORs flag 0x800 into the draw
// when LOD >= 1 or the car type's usage ([0x734588] + 0xc90 * [[model+4]] + 0xc54) is 2, traffic (0x56e15d). The player's
// car is always near, so A; a rival 20-40 m ahead got B or C with the traffic flag. Two debug words of the game force the
// body and parts LOD, 0x6f1b30 / 0x6f1b34 (-1 = by size; one reader each, 0x56e12d / 0x56e13d, no writer: REA ev_cd471810,
// Hopper build/hopper/viewscale.txt). PATCH 0x57119a sends the race list's draw (0x571050, list [0x7361f8]) here (cave
// 0x43a7e4: jmp [SCREEN_ADDR+0x64]); a car that is not traffic is drawn with both at 0, then they go back to -1.
// Traffic keeps the game's LOD. RN_CARLOD=0: the original.
// Traffic body motion (OWNER 2026-11-04, "rigid"): 0x571050 passes the car's own matrix, record+0x90 (rows forward, right, up, 0x10 apart), to the draw (arg 3). The body leans on a damped spring from the car's
// acceleration: nose dips under braking, rolls out in a turn. Drawn only: physics and collisions keep record+0x90. Wheels share the matrix; the angle stays under 3 deg. RN_TRAFLEAN=0: the game's matrix.
static uint32_t traffic_lean(Ctx *c, uint32_t mat) {
    static int off = -1;
    static uint32_t tmp;
    static struct { uint32_t rec, at; float vx, vy, p, r, dp, dr; } s[64];
    static uint32_t race;   // a new race's cars may reuse an old record address: no lean carried over
    if (off < 0) { const char *e = getenv("RN_TRAFLEAN"); off = e && e[0] == '0'; }
    if (rn_new_race(&race)) memset(s, 0, sizeof s);
    if (off || mat < 0x90 || mat >= GUEST_MEM - 0x100) return mat;
    uint32_t rec = mat - 0x90, slot = 0;
    for (uint32_t i = 0; i < 64; i++) {
        if (s[i].rec == rec) { slot = i; break; }
        if (s[i].at < s[slot].at) slot = i;
    }
    float fx = ldf(c, mat), fy = ldf(c, mat + 4), vx = ldf(c, rec + 0x70), vy = ldf(c, rec + 0x74);
    if (s[slot].rec != rec) memset(&s[slot], 0, sizeof s[slot]), s[slot].rec = rec, s[slot].vx = vx, s[slot].vy = vy;
    else if (s[slot].at != rn_telem.presents) {                 // once per present: a car draws again in reflections
        const float dt = 1.0f / 60, w = 7.0f, z = 0.45f;        // about 1.1 Hz, some overshoot, as a soft street car
        float ax = (vx - s[slot].vx) / dt, ay = (vy - s[slot].vy) / dt, al = ax * fx + ay * fy, as = ax * fy - ay * fx;
        s[slot].vx = vx, s[slot].vy = vy;
        if (fabsf(al) > 15 || fabsf(as) > 15) al = as = 0;      // a hit or a recycle jump, not driving
        float tp = fmaxf(-0.05f, fminf(0.05f, 0.0065f * al)), tr = fmaxf(-0.05f, fminf(0.05f, 0.0065f * as));
        s[slot].dp += (w * w * (tp - s[slot].p) - 2 * z * w * s[slot].dp) * dt, s[slot].p += s[slot].dp * dt;
        s[slot].dr += (w * w * (tr - s[slot].r) - 2 * z * w * s[slot].dr) * dt, s[slot].r += s[slot].dr * dt;
    }
    s[slot].at = rn_telem.presents;
    if (!tmp) tmp = guest_alloc(64 * 2);
    uint32_t out = tmp + (rn_telem.presents & 1) * 64;
    float m[16], p = s[slot].p, ro = s[slot].r;
    for (int i = 0; i < 16; i++) m[i] = ldf(c, mat + i * 4);
    for (int i = 0; i < 3; i++) {                               // small angles: forward tips along up, right along up, up the other way
        float f = m[i], rg = m[4 + i], u = m[8 + i];
        stf(c, out + i * 4, f + p * u), stf(c, out + 0x10 + i * 4, rg + ro * u), stf(c, out + 0x20 + i * 4, u - p * f - ro * rg);
    }
    for (int i = 3; i < 16; i += (i == 3 || i == 7 ? 4 : 1)) stf(c, out + i * 4, m[i]);
    return out;
}
static uint32_t car_draw(Ctx *c) {
    static int lod = -1;
    if (lod < 0) { const char *e = getenv("RN_CARLOD"); lod = !(e && e[0] == '0'); }
    uint32_t a[12];
    for (int k = 0; k < 12; k++) a[k] = ARG(k);
    uint32_t m = a[0], t = m ? ld(c, m + 4, 4) : 0, tab = ld(c, 0x734588, 4);
    int racer = lod && t && tab && ld(c, tab + 0xc90 * ld(c, t, 4) + 0xc54, 4) != 2;
    if (getenv("RN_CARLODLOG")) {   // each model once
        static uint32_t seen[64]; static int n;
        int k = 0;
        while (k < n && seen[k] != m) k++;
        if (k == n && n < 64) seen[n++] = m, rn_log("CARLOD model %08x type %u usage %u racer %d", m, t ? ld(c, t, 4) : 0,
                                                    t && tab ? ld(c, tab + 0xc90 * ld(c, t, 4) + 0xc54, 4) : 0, racer);
    }
    if (racer) { st(c, 0x6f1b30, 0, 4); st(c, 0x6f1b34, 0, 4); }
    if (lod && t && tab && !racer) a[3] = traffic_lean(c, a[3]);
    uint32_t r = call_guest(c, 0x56dc30, 12, a);
    if (racer) { st(c, 0x6f1b30, 0xffffffffu, 4); st(c, 0x6f1b34, 0xffffffffu, 4); }
    return r;
}

// PATCH 0x44c573 (cave 0x43b556: jmp [SCREEN_ADDR+0xb0]): the racer's desired-speed step 0x44c550 (ebx = the AIVehicle v, once per racer and
// step) calls the catch-up 0x44bd10 (eax = v) right before it reads the speed: the route node's byte at index node + [v+0x404] (offset drawn
// every 5 s, stamp [v+0x400]) x record+0x14 x [v+0x4b8] when the action's +0x1f0 is set, else the action's own target [act+0x1e4] (m/s).
// Here the original call runs first, then each personality adjusts those inputs (see Personalities above). v+0x2c = ctx: [ctx] = car,
// [car+0x14] = entrant (+4 kind 2 = rival, +0x735 level), neighbour rows ctx + 8 + i * 0x38 (+4 speed of the other minus own, +0xc half
// length, +0x10 route position, +0x34 body node), own row index (int8) ctx+0x388. Nitro burns while [car+0x3fc] (start tick of the
// clock [0x73ad34]) is set and younger than [car+0x3f8] ticks (0x465430 on car+0x40). Returns 0x44bd10's eax.

static uint32_t persona_step(Ctx *c) {
    static struct { uint32_t v, stamp, shot, said; } s[16];
    static struct { uint32_t v; float last; } rb[16];
    static uint32_t race;   // 16 slots, one per rival of this race (they filled up over races)
    if (rn_new_race(&race)) memset(s, 0, sizeof s), memset(rb, 0, sizeof rb);
    uint32_t v = c->r[EAX], r = call_guest(c, 0x44bd10, 0, NULL);
    if (!persona_on || !v) return r;
    if (rn_pool()) {
        // Less rubber band: 0x44bd10 writes its scale at [v+0x4b8] (raw) and [[v+4]+0x404] (max(raw, 1)) once per 0.3 s (0x44bfe9..0x44bffe). A new value keeps 35 % of its distance to 1.
        int q = 0;
        while (q < 15 && rb[q].v && rb[q].v != v) q++;
        float raw = ldf(c, v + 0x4b8);
        if (rb[q].v != v || raw != rb[q].last) {
            uint32_t veh = ld(c, v + 4, 4);
            float d = 1.f + (raw - 1.f) * 0.35f;
            stf(c, v + 0x4b8, d);
            if (veh) stf(c, veh + 0x404, d > 1.f ? d : 1.f);
            rb[q].v = v; rb[q].last = d;
        }
    }
    uint32_t ctx = v + 0x2c, car = ld(c, ctx, 4), ent = car ? ld(c, car + 0x14, 4) : 0, act = ld(c, v + 0x3f8, 4);
    if (!ent || ld(c, ent + 4, 4) != 2 || !act) return r;
    int lv = (int8_t)c->mem[ent + 0x735], p = lv >= 0 && lv <= 9 ? PERSONA[lv] : NORMAL;
    if (p == NORMAL) return r;
    int k = 0;
    while (k < 15 && s[k].v && s[k].v != v) k++;
    if (s[k].v != v) {
        s[k].v = v, s[k].stamp = s[k].shot = s[k].said = 0;
        if (getenv("RN_RIVALLOG") || getenv("RN_FREELOG")) rn_log("persona %s L%d %s: on", G(ent + 0x73c), lv, PNAME[p]);
    }
    uint32_t type = ld(c, act + 0x1f8, 4), now = ld(c, 0x73ad34, 4), route = c->mem[act + 0x1f0];
    int own = (int8_t)c->mem[ctx + 0x388], n = (int)ld(c, ctx + 4, 4);
    float vx = ldf(c, car + 0x70), vy = ldf(c, car + 0x74), sp = sqrtf(vx * vx + vy * vy);
    const char *ev = NULL;
    float tgt = 0;
    if (ld(c, v + 0x400, 4) != s[k].stamp) {                      // a new speed lookup offset: brake early or late
        s[k].stamp = ld(c, v + 0x400, 4);
        if (p == NERVOUS || p == AGGRESSIVE) st(c, v + 0x404, ld(c, v + 0x404, 4) + (p == NERVOUS ? 2 : -2), 4);
        uint32_t e = (s[k].stamp ^ v) * 0x9e3779b1u >> 24;       // ?pool=1: a mistake now and then, it reads the curve late and overshoots
        if (rn_pool() && e < (p == NERVOUS ? 77u : p == AGGRESSIVE ? 38u : 13u)) st(c, v + 0x404, ld(c, v + 0x404, 4) - 6, 4);
    }
    if (p == AGGRESSIVE && type == 0xc && !route && own >= 0 && n <= 16) {   // IJustGotHit: revenge on the culprit [act+0x1fc]
        uint32_t who = ld(c, act + 0x1fc, 4);
        for (int i = 0; i < n && who; i++) {
            uint32_t row = ctx + 8 + i * 0x38;
            if (i == own || ld(c, row + 0x34, 4) != who) continue;
            tgt = sp + ldf(c, row + 4) + 4;
            if (tgt > ldf(c, act + 0x1e4)) stf(c, act + 0x1e4, tgt), ev = "revenge";
            break;
        }
    }
    if (p == TIDY && type == 4 && !route && own > 0 && n <= 16) {      // Draft near a car: hold the lead's speed, stay in the tow
        uint32_t orow = ctx + 8 + own * 0x38, row = orow - 0x38;
        float gap = ldf(c, row + 0x10) - ldf(c, row + 0xc) - ldf(c, orow + 0x10) - ldf(c, orow + 0xc);
        tgt = sp + ldf(c, row + 4) + (gap > 3 ? 1.0f : 0.0f);
        if (gap > 0 && gap < 12 && tgt > ldf(c, act + 0x1e4)) stf(c, act + 0x1e4, tgt), ev = "draft";
    }
    uint32_t t0 = ld(c, car + 0x3fc, 4);
    if (p == NERVOUS && t0 && t0 != 0x7fffffffu && now - t0 < ld(c, car + 0x3f8, 4)) {   // its nitro burns: it lifts
        if (route) stf(c, v + 0x4b8, ldf(c, v + 0x4b8) * 0.88f);
        else stf(c, act + 0x1e4, ldf(c, act + 0x1e4) * 0.88f);
        if (s[k].shot != t0) s[k].shot = t0, ev = "panic";
    }
    if (ev && (getenv("RN_RIVALLOG") || getenv("RN_FREELOG")) && now - s[k].said > 8000) {
        s[k].said = now;
        rn_log("persona %s L%d %s: %s speed %.1f target %.1f frame %u", G(ent + 0x73c), lv, PNAME[p], ev, sp, tgt, rn_telem.presents);
    }
    return r;
}

// PATCH 0x45c8c2 (cave 0x43db2a: jmp [SCREEN_ADDR+0xb4]): the side-line builder 0x45c760 (Pass, Avoid and IJustGotHit in route state 2/3)
// puts the line at the other car's lateral +- (own half width + its half width + 0x45cea0's clearance, st0; ecx = ctx, edx = the other's row,
// 2 stack args, ret 8), then clamps it to the road edges. A clean rival passes wide: its clearance + 1.5 m.
static uint32_t persona_clear(Ctx *c) {
    uint32_t a[2] = {ARG(0), ARG(1)}, ctx = c->r[ECX];
    call_guest(c, 0x45cea0, 2, a);
    uint32_t car = persona_on ? ld(c, ctx, 4) : 0, ent = car ? ld(c, car + 0x14, 4) : 0;
    int lv = ent && ld(c, ent + 4, 4) == 2 ? (int8_t)c->mem[ent + 0x735] : -1;
    if (lv >= 0 && lv <= 9 && PERSONA[lv] == TIDY) c->st[c->ftop] += 1.5;
    return 0;
}

// BRIDGE: neon puddle, OWNER 2026-11-03 (?pool=1, Remaster only, off by default). DrawLampFlares 0x56d8d0 draws the car's shadow and then its
// neon (+0x4bc, texture <CAR>_NEON, pass 1 of the loop at 0x56f200) over one 4x4 grid on the road (16 points of 16 bytes at [esp+0x5b0]), colour [esp+0x1c].
// PATCH 0x56f21e sends the neon pass's setup here. The puddle keeps the game's size, alpha and light (OWNER: x1.18 area and x1.3 light were too marked);
// outside the career SHOW and BOSO rivals only pulse or sweep hue. Clock [0x73ad34] = 4000 Hz (0x6cca38 = 0.00025).
static uint32_t neon_pass(Ctx *c) {
    uint32_t esp = c->r[ESP] + 4, info = ld(c, c->r[EBP] + 8, 4), tex = ld(c, info + 0x4bc, 4), col = ld(c, esp + 0x1c, 4), ride = ld(c, info + 4, 4);
    uint32_t skin = ride ? ld(c, ride + 0x444, 4) : 0;
    if (rn_pool() && tex && (col >> 24) && !c->mem[0x78a33c] && skin && skin != 0x530b82b0)
        for (int i = 0; i < NSYN; i++) if (neon_ride[i] == skin) {
            float t = ld(c, 0x73ad34, 4) * 0.00025f, q[3], k = skin & 1 ? 0.8f + 0.2f * sinf(t * 2.5f) : 1.0f, m = skin & 1 ? 0.0f : 0.5f + 0.5f * sinf(t * 0.75f);
            for (int j = 0; j < 3; j++) q[j] = (col >> (8 * j) & 255);
            float r[3] = {q[1], q[2], q[0]};
            uint32_t out = col & 0xff000000u;
            for (int j = 0; j < 3; j++) out |= (uint32_t)((q[j] + (r[j] - q[j]) * m) * k) << (8 * j);
            col = out;
            break;
        }
    st(c, esp + 0x20, col, 4);
    return tex;
}

const Api rivals_apis[] = {{"rn", "rival_ride", 7, rival_ride}, {"rn", "car_draw", 12, car_draw}, {"rn", "traffic_behind", 0, traffic_behind},
                           {"rn", "persona_step", 0, persona_step}, {"rn", "persona_clear", 2, persona_clear}, {"rn", "neon_pass", 0, neon_pass}};
const int rivals_api_count = 6;
