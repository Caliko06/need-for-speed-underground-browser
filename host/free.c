// BRIDGE: free mode (OWNER 2026-10-27: "on the track with real rivals driving, like a free online"), not in the original.
// Quick Race Free Run (mode 3, setup 0x4b5090) is the game's own endless drive: laps [0x78a31c] = 0, so nobody finishes.
// It registers only the player (0x5809c0 kind 1, grid [0x78a334] = 2) and the traffic (0x4b3ac0), and never calls the
// opponent builder 0x4b4040 that Circuit (0x4b49e0) calls with ([0x78a324] opponents, 0). Everything after that is mode
// blind (REA ev_289db272, ev_6d7d9c51): the race start 0x422a70 walks grid slots 1..4 of the entrant table [0x78a418]
// (0x750 each: +3 grid, +4 kind 1 player / 2 opponent / 3 traffic, +0x10 RideInfo) and builds each car with 0x422410,
// which gives an opponent driver type 3, the racer AI (0x425150, skill [0x6b7c20 + 4 * [0x78a40c]], 0x4a9900).
// PATCH 0x4b528d sends Free Run's traffic call here (cave 0x6736b7: jmp [SCREEN_ADDR+0x68]). With RN_FREE on, it sets
// [0x78a324] = 3 and calls 0x4b4040(3, 0) as Circuit does, the player first on the grid and the rivals behind; each
// opponent then reaches host/rivals.c rival_ride, which hands it to free_rival: one of the career's own rivals (name and
// preset of their last event, census/career_oracle.json), dressed by the game's preset code 0x4b26f0 (eax = preset hash,
// the career path at 0x4b4155). 0x4b4380, which 0x4b4040 runs in Quick Race, then matches every opponent's rating to the
// player's (0x57f700). Off by default since 2026-11-21 (OWNER: Free Run as shipped in both modes); RN_FREE=1 turns it on.
#include "host.h"
#include <math.h>
#include <string.h>

#define NRIV_MAX 9          // rivals: the race start's 10 grid slots (PATCH 0x422a78) hold the player and 9; 1 + 9 + 19 traffic <= the entrant table's 30
static int nriv = 6;        // RN_FREERIV (default 6, 0..NRIV_MAX): 0x4b4040's count; RN_FREERIV=3 is the first free mode

// The career's rivals (census/career_oracle.json: every event's opponents, each name with the preset of its last event).
static const struct { const char *name; uint32_t preset; } CANON[] = {
    {"BRIAN", 0xa76ad63d}, {"BRETT", 0x8d2d3d32}, {"LOLA", 0x32d6d2f5}, {"WART", 0x3e438ee6}, {"NESTO", 0x493349a9},
    {"JOSE", 0x496e17a8}, {"ROSIE", 0xf713b959}, {"JACKIE", 0x6b75fb86}, {"BRYCE", 0x71845b7d}, {"CARL", 0xbff2ba3c},
    {"CARLA", 0xf5ea3c46}, {"DIRT", 0x6f1ac102}, {"DARYL", 0xb83c0594}, {"KLUTCH", 0x6408b98a}, {"PRISS", 0x7335abb4},
    {"STEFAN", 0x4e07a75c}, {"PROBES", 0x283031c5}, {"STEWART", 0x3328d41a}, {"AL", 0x98b598cb}, {"SCOTT", 0x869bd62b},
    {"HUNTER", 0xf71014d2}, {"TERRY", 0xf9ed7e06}, {"FISH", 0x4fa5993d}, {"LEBRON", 0x3bd031d5}, {"MACCA", 0x49f9c026},
    {"HECTOR", 0x6ff2a4c1}, {"JET", 0x43fe5c0b}, {"SPIN", 0x939ccbd4}, {"DESHAWN", 0xb708963b}, {"WILL", 0xdb2d97c0},
    {"MUTT", 0xa0f830fe}, {"RICCO", 0x3ea53eed}, {"HOFFMAN", 0x46ae2a9a}, {"CHAD", 0x9f2a8223}, {"JARED", 0xb62f8a53},
    {"TODD", 0xf9a6c94e}, {"BRAD", 0x6c79e5d4}, {"PAUL", 0x7bf9866c}, {"BOPPER", 0x5aa66cf5}, {"LAZIO", 0xf0f1052f},
    {"MACK-D", 0x4c9b52c8}, {"KURT", 0x174fa745}, {"B-DOG", 0xe8a7e7be}, {"BRITTON", 0x3bcf59bc},
    {"TANAKA", 0xe604f578}, {"VINCE", 0x541a96c6}, {"TAKASHI", 0x465bbc40}, {"NUTZ", 0xe8171d01}, {"STAN", 0x4438edd1},
    {"TICKETS", 0xf5cd094d}, {"GEARS", 0x5c075321}, {"VIONCE", 0x541a96c5}, {"SKID", 0x41234aa7},
    {"ISHII", 0xa7feadd8}, {"WU", 0x0fca18ce}, {"FORGE", 0xfc79d032}, {"MATT", 0xec5c29db}, {"SLIK", 0x8837ee78},
    {"JARRUS", 0x3f9cd43c}, {"KIRBY", 0xe7a47752}, {"SAMANTHA", 0xa4045c39}, {"KAZ", 0x4b23fd55},
    {"SPARKS", 0xba053fb6}, {"AMY", 0x45f16bb8}, {"TJ", 0x33f2f54a}, {"EDDIE", 0x7a282c98}, {"MELISSA", 0xf35d35de},
};
#define NCANON (int)(sizeof CANON / sizeof *CANON)

int rn_free_now;                 // 1 while 0x4b4040 builds free mode's rivals (host/rivals.c rival_ride asks free_rival), 2 in its traffic
static int on, live, picked[NRIV_MAX], npicked;
static uint32_t zone_at, zone_was;     // the clear zone free_place changed (free mode, the whole race) and its value
// The rubber band 0x44bd10 needs a gap from 0x44c010, which is 0 while [0x78a400] (the race options' Catch Up byte +0x1f, set by
// the mode setups 0x4b4a56..0x4b5f47) is 0, as shipped in Free Run. RN_FREECU=1 sets it to 1 for the race (rivals ahead wait, rivals
// behind boosted, as in a Quick Race with Catch Up on); off by default (OWNER 2026-10-31, "the AI is dumb"): the gap is route progress
// car+0x814, which means nothing when each rival walks its own direction, so rivals sat at racer+0x4b8 0.47-0.57 for minutes, ahead or
// behind (F10 AIR lines). Respawn (RN_RIVALFAR) keeps them near instead. Put back at race end (free_tick).
static int cu_was = -1;
// 0x44c010 reads the gap through the curves 0x779c78/0x779dd8 (8 rows of 11 (x m, y) points, loaded at run time): a
// leader is slowed only 3 % at 120 m and 30 % at 320 m, so in Free Run rivals settle 250 m ahead. Free mode scales the
// x axis by RN_FREECUX (default 0.35: 30 % at 110 m) and puts the curves back at race end.
static float cu_x[8][11];
static void free_curves(Ctx *c, int on) {
    static int saved;
    float f = getenv("RN_FREECUX") ? (float)atof(getenv("RN_FREECUX")) : 0.35f;
    for (int r = 0; r < 8; r++)
        for (int k = 0; k < 11; k++) {
            uint32_t a = 0x779c78 + 0x58 * r + 8 * k;
            float x;
            if (on) cu_x[r][k] = ldf(c, a), x = cu_x[r][k] * f;
            else if (saved) x = cu_x[r][k];
            else continue;
            uint32_t u; memcpy(&u, &x, 4); st(c, a, u, 4);
        }
    saved = on;
}
static struct { uint32_t drv, dir; } rdir[16];   // free_dir's table, see riv_place
static int n_game, n_free;             // free_spacing: moves with the game's spacing, moves given the track's spacing
#define KEEP_M 200.0f   // free_recycle: a car this close and ahead of the player is never moved
static int n_far, n_kept, n_offbit, n_onbit;   // free_recycle: far cars sent to a move; free_tnode: cars placed on a node without / with the bit
static uint32_t xrec[12], nxrec;       // the extra racers' records (rm_records, outside the RaceManager) and how many there are
static uint32_t names;           // NRIV_MAX guest strings of 16 bytes: 0x5809c0 copies the entrant name from its 4th argument

static uint32_t rnd(uint32_t *s) { uint32_t x = *s; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return *s = x ? x : 0x9e3779b9u; }
static uint32_t ghash(Ctx *c, uint32_t p) { uint32_t h = 0xffffffffu; for (uint8_t b; (b = c->mem[p]); p++) h = h * 33 + b; return h; }
static uint32_t nhash(const char *p) { uint32_t h = 0xffffffffu; for (; *p; p++) h = h * 33 + (uint8_t)*p; return h; }
extern int rn_tex_overlay;      // host/trackfiles.c: Cars/TEXTURES.BIN came from the overlay
static uint32_t preset_named(Ctx *c, uint32_t h) {   // the game's preset list 0x748844 (0x4b2640 finds them the same way)
    for (uint32_t p = ld(c, 0x748844, 4); p && p != 0x748844; p = ld(c, p, 4))
        if (ghash(c, p + 0x28) == h) return p;
    return 0;
}

// 0x5809c0(id, 2, ride, name, skill, ?, index) of one free mode rival: a career rival not yet in this race.
uint32_t free_rival(Ctx *c, uint32_t *a) {
    uint32_t s = ld(c, 0x6f227c, 4) ^ (a[6] * 0x85ebca6bu) ^ rn_telem.presents * 0x9e3779b9u;
    int k = rnd(&s) % NCANON;
    for (int tries = 0; tries < NCANON; tries++, k = (k + 1) % NCANON) {
        int dup = 0;
        for (int j = 0; j < npicked; j++) dup |= picked[j] == k;
        if (!dup) break;
    }
    uint32_t ride = a[2], rec = preset_named(c, CANON[k].preset);
    if (rec) {
        uint32_t one = ride;
        c->r[EAX] = CANON[k].preset;
        call_guest_cdecl(c, 0x4b26f0, 1, &one);
    }
    // 0x4b4040 hands the builder's own 4 names (0x4b3a20) to its first 4 rivals; the 5th and later read the next stack slots
    // (a sprintf buffer): the name is always ours.
    uint32_t nm = names + 16 * (npicked % NRIV_MAX);
    snprintf(G(nm), 16, "%s", CANON[k].name);
    a[3] = nm;
    // Personalities: the AI's skill level 1..9 is this call's 5th argument (0x5809c0 stores it in entrant+0x735 at 0x5809f6,
    // the racer AI reads it through vtable +0x58 = 0x44ca10) and picks its record 0x779ff8 + 0x54 * level (wander chance,
    // speed fractions, catch-up; docs/openworld/re_rival_personality.md). Free mode gives each rival its own level,
    // RN_FREESKILL (default "2,5,9,...": clumsy, steady, aggressive, then the others); "0" keeps the game's.
    uint32_t game_skill = a[4];
    const char *sk = getenv("RN_FREESKILL");
    if (!sk) sk = "2,5,9,4,7,3,6,8,1";            // the first three are the first free mode's
    if (strcmp(sk, "0")) {
        int len = 1;
        for (const char *z = sk; *z; z++) len += *z == ',';
        const char *q = sk;
        for (int j = 0; j < npicked % len && q; j++) q = strchr(q, ','), q = q ? q + 1 : NULL;
        int lv = q ? atoi(q) : 0;
        if (lv >= 1 && lv <= 9) a[4] = (uint32_t)lv;
    }
    if (npicked < NRIV_MAX) picked[npicked++] = k;
    if (getenv("RN_FREELOG"))
        rn_log("FREE rival %u: %s preset %08x %s (%s) skill %d -> %d", a[6], CANON[k].name, CANON[k].preset, rec ? "applied" : "MISSING",
               rec ? G(rec + 0x28) : "-", (int)game_skill, (int)a[4]);
    return call_guest(c, 0x5809c0, 7, a);
}

// In place of Free Run's call to AddTrafficCars 0x4b3ac0 (no arguments).
static uint32_t free_setup(Ctx *c) {
    if (!on) { const char *e = getenv("RN_FREE"); on = e && e[0] == '1' ? 1 : -1; }   // OWNER 2026-11-21: off by default
    if (on > 0 && ld(c, 0x777cc8, 4) == 3 && !c->mem[0x78a347]) {
        if (!names) names = guest_alloc(16 * NRIV_MAX);
        const char *fr = getenv("RN_FREERIV");
        nriv = fr ? atoi(fr) : 6;                   // WORLD too (OWNER 2026-11-11: 8 rivals + 40 cars was too much)
        nriv = nriv < 0 ? 0 : nriv > NRIV_MAX ? NRIV_MAX : nriv;
        uint32_t tab = ld(c, 0x78a418, 4), n = ld(c, 0x78a41c, 4);
        for (uint32_t i = 0; i < n; i++)                          // the player leads the grid (0x422a70 slot 1 = the front)
            if (ld(c, tab + 0x750 * i + 4, 4) == 1) c->mem[tab + 0x750 * i + 3] = 1;
        c->mem[0x78a334] = 1;
        st(c, 0x78a324, nriv, 4);
        npicked = 0, rn_free_now = 1;
        memset(rdir, 0, sizeof rdir);
        st(c, 0x6c89f0 + 0x40, host_addr_of("rn", "free_dir"), 4);   // racer vtable slot +0x40: each rival's own route direction
        st(c, 0x6b8968 + 0x2c, host_addr_of("rn", "free_hseed"), 4); // player driver vtable: route seed by place, not by tour progress
        st(c, 0x6b8968 + 0x40, host_addr_of("rn", "free_hdir"), 4);  // and route direction from the seed node (free_hseed)
        uint32_t args[2] = {(uint32_t)nriv, 0};
        call_guest_cdecl(c, 0x4b4040, 2, args);
        rn_free_now = 0;
        tab = ld(c, 0x78a418, 4), n = ld(c, 0x78a41c, 4);
        for (uint32_t i = 0, g = 2; i < n; i++)                   // 0x4b4040 numbered them 1..N: behind the player, 2..N+1
            if (ld(c, tab + 0x750 * i + 4, 4) == 2) c->mem[tab + 0x750 * i + 3] = g++;
        if (getenv("RN_FREELOG")) rn_log("FREE setup: %u entrants, %u rivals at frame %u", n, nriv, rn_telem.presents);
        live = 1, rn_free_now = 2;                                // AddTrafficCars: free_traffic dresses the racer rows
    }
    // The traffic count of AddTrafficCars (0x4b3b01 reads i8 [0x441fe0() + [0x78a2fc] + [0x78a300] * 2 + 0xc0], 6 on 1003 and 12 on 1001
    // and 1010, then PATCH 0x57d060's x1.5, at most 55): set to FREE_TRAFFIC, then put back (the track table outlives the race).
    c->r[ESI] = ld(c, 0x78a2f0, 4);                               // 0x441fe0 reads its argument in esi
    uint32_t ti = call_guest(c, 0x441fe0, 0, NULL), cnt = ti + ld(c, 0x78a2fc, 4) + ld(c, 0x78a300, 4) * 2 + 0xc0;
    int8_t keep = (int8_t)c->mem[cnt];
    int base = getenv("RN_FREETRAFFIC") ? atoi(getenv("RN_FREETRAFFIC")) : FREE_TRAFFIC;   // WORLD too: 13 x1.5 = 19 cars (OWNER 2026-11-11; was 27 = 40)
    if (live && base >= 0) c->mem[cnt] = (int8_t)base;   // 0 = no traffic: 0x4b3b11 skips the add loop on a count <= 0 (launcher 'Sin tráfico')
    if (getenv("RN_FREELOG")) rn_log("FREE traffic asked: trackinfo count %d -> %d (x1.5, at most 55)", keep, (int8_t)c->mem[cnt]);
    uint32_t r = call_guest(c, 0x4b3ac0, 0, NULL);
    c->mem[cnt] = (uint8_t)keep;
    rn_free_now = 0;
    return r;
}

// Tuned traffic. AddTrafficCars 0x4b3ac0 builds each traffic ride stock (0x57d160 type, 0x57d340, 0x57e9a0 the first
// paint) and registers it with 0x5809c0(0x32 + i, 3, ride, "", -1, 0, 0) at 0x4b3c2f; with PATCH 0x57cfc7 (off since
// 2026-10-28: racer bodies need a DUMMY_SKIN slot, tools/recomp/patches.py) the traffic pool also picks racer rows, type usage 0 ([0x734588] + 0xc90 * type + 0xc54). PATCH 0x4b3c2f sends that call here (cave
// 0x43a7ea: jmp [SCREEN_ADDR+0x6c]). In free mode a racer row wears the preset of a career rival with the same car,
// applied by 0x4b26f0 (it resets the ride to the preset's car, 0x57cf70 -> 0x57d160, then sets its 0x78 part slots at
// ride +0x44c). A traffic ride has no skin of its own (0x57d160 zeroes the DUMMY_SKIN / DUMMY_WHEEL hashes at +0x444 /
// +0x448, which 0x4b4040 sets for the four racers only), so the vinyl, decal and rim paint slots are cleared again, the
// way 0x57e9a0 clears the vinyls of stock traffic, and 0x57ea80 (stdcall, the ride) recomputes the ride's derived state.
static int8_t ctype[NCANON];      // the car type of each career preset (-1 = not in the game's list), filled once
void rn_pool_traffic(Ctx *c, uint32_t ride, uint32_t seed);   // host/rivals.c
int rn_pool(void);
static uint32_t free_traffic(Ctx *c) {
    uint32_t a[7];
    for (int k = 0; k < 7; k++) a[k] = ARG(k);
    uint32_t ride = a[2], type = ld(c, ride, 4), tab = ld(c, 0x734588, 4);
    if (rn_free_now == 2 && tab && ld(c, tab + 0xc90 * type + 0xc54, 4) == 0) {
        static int typed;
        if (!typed++) {
            uint32_t tmp = guest_alloc(0x720);
            for (int k = 0; k < NCANON; k++) {
                ctype[k] = -1;
                if (!preset_named(c, CANON[k].preset)) continue;
                uint32_t one = tmp;
                c->r[EAX] = CANON[k].preset;
                call_guest_cdecl(c, 0x4b26f0, 1, &one);
                ctype[k] = (int8_t)ld(c, tmp, 4);
            }
            guest_free(tmp);
        }
        int cand[NCANON], n = 0;
        for (int k = 0; k < NCANON; k++) if (ctype[k] == (int)type) cand[n++] = k;
        if (!n) rn_log("NOSKIN traffic %u: racer type %u has no career preset", a[0], type);
        if (n) {
            uint32_t s = ld(c, 0x6f227c, 4) ^ a[0] * 0x9e3779b9u, one = ride;
            int k = cand[rnd(&s) % n];
            c->r[EAX] = CANON[k].preset;
            call_guest_cdecl(c, 0x4b26f0, 1, &one);
            // Vinyls, decals and rim paint off; body kit (slots < 0x13), paint 0x1e, part paint 0x23..0x28, tint 0x73 and neon 0x74 are kept.
            static int slot;
            if (a[0] == 0x32) slot = 0;
            for (int sl = 0x13; sl <= 0x72; sl++)
                if (sl <= 0x1d || (sl >= 0x1f && sl <= 0x22) || sl == 0x29 || sl >= 0x2a) {
                    st(c, ride + 0x44c + 4 * sl, 0, 4);
                    c->mem[ride + 0x62c + sl]++;
                }
            call_guest(c, 0x57ea80, 1, &one);
            // The body is drawn with the texture at ride +0x444 (DUMMY_SKIN<n>) and the rims with +0x448 (DUMMY_WHEEL<n>), which the loader
            // 0x58cbb0 -> 0x58be50 -> 0x5a9ce0 bakes the paint into (docs/openworld/re_traffic_racers.md). 0x57d160 zeroed them; the slots 1..4
            // are the player's and the first rivals', 5..20 are the overlay's (rivals 4+: 5..10, traffic racers 13..28) (Cars/TEXTURES.BIN, tools/remaster/world_overlays.py): one per racer.
            if (rn_tex_overlay && slot < 16) {
                char nm[24];     // 13..20: the rivals take DUMMY_SKIN2..N+1 by name (0x4b4040), up to 10
                snprintf(nm, sizeof nm, "DUMMY_SKIN%d", 13 + slot); st(c, ride + 0x444, nhash(nm), 4);
                snprintf(nm, sizeof nm, "DUMMY_WHEEL%d", 13 + slot); st(c, ride + 0x448, nhash(nm), 4);
                slot++;
            }
            rn_pool_traffic(c, ride, a[0]);
            if (!ld(c, ride + 0x444, 4)) rn_log("NOSKIN traffic %u: racer type %u has no body texture (slot %d)", a[0], type, slot);
            if (getenv("RN_FREELOG")) rn_log("FREE traffic %u: type %u wears %s's preset %08x skin %08x%s", a[0], type, CANON[k].name, CANON[k].preset, ld(c, ride + 0x444, 4), "");
        }
    }
    return call_guest(c, 0x5809c0, 7, a);
}

// Each Present (host/d3d9.c): with RN_FREELOG, every 2 s of a free mode race, each rival's distance to the player. A car of
// the race list [0x7361f8] (next at +0, position +0x50, host/lights.c) points at its entrant at +0x14 (0x425150 reads it).
// Respawn (OWNER 2026-10-28: rivals that leave the minimap come back "out of nowhere", ahead, behind or on a cross street).
// Once a second, a rival farther than RN_RIVALFAR m (straight line, default 400) from the player, and not moved in the last
// 8 s, is put on a street node 220..380 m of road from the player with the game's own AI-car reset 0x427f70, the call
// 0x4264d0 makes when [car+0x87c] asks for a reset (stdcall, ret 0x24: car, section, node, speed, 1, dir +-1.0 along the
// node's direction +0xc/+0x10, 0, 0, lateral 0.0); it puts the car on the node, then resets the AI to that node (ctx vt
// 0x10, 0x30), which drives back to its route. The node: the player's (0x428150/0x428160, eax = car, arg 0, as the traffic
// teleporter 0x59a2c0 asks it) walked with 0x4563d0 (ecx section, eax node, cdecl: &pair in/out, 1, metres, along the node
// direction 1 / against 0, 0; 0x59a2c0 walks 250 m the same way), checked with 0x456c90 (eax = &pair). Ahead or behind is
// a coin; the walk takes whatever link the network gives at a junction, so some land on cross streets. RN_RESPAWN=0: off.
// Each rival's own walk direction (docs/openworld/re_rival_turnback.md, Follow-up). The racer class (vtable 0x6c89f0) answers its
// route direction at slot +0x40 = 0x45d640, `mov eax,[0x78a2fc]`, the same for all; 0x44b85d (per frame, into the path grower
// 0x458cc0) and the reset 0x44adff (forward flag = dir == 0) ask it. The slot now points here (written by free_setup): the
// driver's own value from the table below, else the game's. dir 0 = along the nodes' direction +0xc/+0x10, 1 = against.
// Flipping a racer is the traffic decider's own recipe (0x59c210..0x59c28b): 0x457060(path) with edi = dir, 0x5a5340 (esi =
// the new path) to empty it, bit 0 of the 8 decision slots driver+0xc..+0x28 cleared; the path is ctx+0x3a8, ctx = driver+0x2c.
static uint32_t free_dir(Ctx *c) {
    uint32_t drv = c->r[ECX];
    for (int i = 0; i < 16 && rdir[i].drv && !rn_race_over(); i++)   // finished: new drivers (FinishCar), maybe at a freed one's address
        if (rdir[i].drv == drv) return rdir[i].dir;
    return ld(c, 0x78a2fc, 4);
}
static void rival_flip(Ctx *c, uint32_t drv, uint32_t dir) {
    int i = 0;
    while (i < 15 && rdir[i].drv && rdir[i].drv != drv) i++;
    rdir[i].drv = drv, rdir[i].dir = dir;
    uint32_t pa = drv + 0x2c + 0x3a8, edi = c->r[EDI], arg = pa;
    c->r[EDI] = dir;
    call_guest_cdecl(c, 0x457060, 1, &arg);
    c->r[EDI] = edi;
    uint32_t path = ld(c, pa, 4), esi = c->r[ESI];
    if (path) c->r[ESI] = path, call_guest(c, 0x5a5340, 0, NULL), c->r[ESI] = esi;
    for (int k = 0; k < 8; k++) st(c, drv + 0xc + 4 * k, ld(c, drv + 0xc + 4 * k, 4) & ~1u, 4);
}
static uint32_t respawn_pair, go_at;
static int drove;                       // seconds in a row the player has been driving (10+ m/s)
// Each rival's life in a free mode race (OWNER 2026-11-06: explicit states; host/phase.c starts every race with an empty table):
//   R_GRID      on the grid. Once the player drives 2 s (the go; RN_RIVALOPEN=0: never) it gets its own opening spot, 90 + 35 i m of
//               road from the player, ahead and behind in turn, already rolling (OWNER 2026-10-31: rivals vanished after the start,
//               others were not there until later). A spot that is not clear is tried again next second; the other rivals go on.
//   R_ROAD      driving. Under 2 m in a second for 5 s in a row (OWNER 2026-10-28, MW's AIPursuit/AITrafficManager rule) or farther
//               than RN_RIVALFAR (400 m) from the player, 10 s after the race start: respawned 220..380 m out, one rival a second.
//   R_COOLDOWN  8 s after its last placement nothing moves it, then R_ROAD.
// A grid rival is also respawned when stuck or far (the player may never drive off).
enum { R_GRID, R_ROAD, R_COOLDOWN };
static const char *const RIV_ST[] = {"GRID", "ROAD", "COOLDOWN"};
static struct { uint32_t r, since; int st, slow; float x, y; } riv[16];   // this race's rivals, by record (free_race_begin zeroes it)
static void riv_go(Ctx *c, int k, int to, const char *why) {
    if (getenv("RN_FREELOG")) rn_log("FREE %s %s -> %s (%s) frame %u", G(ld(c, riv[k].r + 0x14, 4) + 0x73c), RIV_ST[riv[k].st], RIV_ST[to], why, rn_telem.presents);
    riv[k].st = to, riv[k].since = rn_telem.presents, riv[k].slow = 0;
}
// Candidate spots (docs/re/traffic.md: the game keeps no list; 0x59a2c0 walks 250 m once and steps on ~31 m 4 times). Built once a
// second, when a rival needs one: both ways from the player's node, 40..600 m of road in 25 m steps with 0x4563d0 (ecx section, eax
// node, cdecl: &pair in/out, 1, metres, along the node direction 1 / against 0, 0), each distinct node 0x456c90 accepts and 60+ m
// from the player in a straight line. -1 = no player node.
#define RING 48
static struct { uint32_t sec, node; float x, y, m; int ahead; } ring[RING];
static int nring, ring_along, ring_stall;
static uint32_t ring_at, ring_sec, ring_node;
static int riv_ring(Ctx *c, uint32_t pc, double vx, double vy) {
    if (ring_at == rn_telem.presents) return ring_node ? nring : -1;
    ring_at = rn_telem.presents, nring = ring_stall = 0;
    if (!respawn_pair) respawn_pair = guest_alloc(8);
    uint32_t zero = 0, ft = c->ftop;
    c->r[EAX] = pc; uint32_t sec = call_guest(c, 0x428150, 1, &zero);
    c->r[EAX] = pc; uint32_t node = call_guest(c, 0x428160, 1, &zero);
    st(c, respawn_pair, sec, 4), st(c, respawn_pair + 4, node, 4);
    c->r[EAX] = respawn_pair;
    ring_sec = sec, ring_node = node;
    if (!sec || !node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { ring_node = 0; c->ftop = ft; return -1; }
    // along the player's node (dot of its direction and the player's motion) = ahead
    ring_along = ldf(c, node + 0xc) * vx + ldf(c, node + 0x10) * vy >= 0;
    double px = ldf(c, pc + 0x50), py = ldf(c, pc + 0x54);
    for (int side = 0; side < 2; side++)
        for (float m = 40.0f; m <= 600.0f && nring < RING; m += 25.0f) {
            st(c, respawn_pair, sec, 4), st(c, respawn_pair + 4, node, 4);
            uint32_t a[5] = {respawn_pair, 1, 0, (uint32_t)(side ? !ring_along : ring_along), 0};
            memcpy(&a[2], &m, 4);
            c->r[ECX] = sec, c->r[EAX] = node;
            call_guest_cdecl(c, 0x4563d0, 5, a);
            uint32_t s2 = ld(c, respawn_pair, 4), n2 = ld(c, respawn_pair + 4, 4);
            c->r[EAX] = respawn_pair;
            if (n2 == node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { ring_stall++; break; }   // the walk ends here (dead end): farther walks give the same node
            int dup = 0;
            for (int k = 0; k < nring && !dup; k++) dup = ring[k].node == n2;
            float nx = ldf(c, n2), ny = ldf(c, n2 + 4);
            if (dup || hypot(nx - px, ny - py) < 60) continue;
            ring[nring].sec = s2, ring[nring].node = n2, ring[nring].x = nx, ring[nring].y = ny, ring[nring].m = m, ring[nring].ahead = !side, nring++;
        }
    c->ftop = ft;
    return nring;
}
// A spot is taken as the game's 0x59b1e0 takes it (docs/re/traffic.md), in straight metres (route positions in the city net are
// spanning-tree values and car+0x814 lags after a move): a traffic car within 31 m blocks it; the player or a racer blocks it only
// when it lies 0..31 m ahead of that car (a racer just ahead of the spot does not).
static int spot_clear(Ctx *c, uint32_t h, uint32_t r, float nx, float ny) {
    for (uint32_t o = ld(c, h, 4), j = 0; o != h && j < 200; o = ld(c, o, 4), j++) {
        if (o == r) continue;
        float dx = nx - ldf(c, o + 0x50), dy = ny - ldf(c, o + 0x54);
        if (dx * dx + dy * dy >= 31.0f * 31.0f) continue;
        uint32_t e = ld(c, o + 0x14, 4);
        if (!e || ld(c, e + 4, 4) == 3 || dx * ldf(c, o + 0x90) + dy * ldf(c, o + 0x94) > 0) return 0;
    }
    return 1;
}
// One placement of rival r on the road from the player: 1 placed, 0 no clear spot, -1 no player node (nothing can be placed now).
// The spot: the ring's clear node nearest to m0 of road (opening 90 + 35 i m, ahead and behind in turn; respawn 220..380 m, a coin
// for the side), the wanted side first.
static int riv_place(Ctx *c, uint32_t h, uint32_t pc, uint32_t r, double vx, double vy, int open, int nr, int stuck) {
    static int rev = -1; static uint32_t seed = 0x5eed1234;
    if (rev < 0) rev = getenv("RN_RESPAWNREV") != NULL;   // test-only: every respawn drives the way opposite to the player's (the flipped racer AI on its own)
    if (riv_ring(c, pc, vx, vy) < 0) {
        if (getenv("RN_FREELOG")) rn_log("FREE place skip %s: no player node (sec %08x node %08x) frame %u", G(ld(c, r + 0x14, 4) + 0x73c), ring_sec, ring_node, rn_telem.presents);
        return -1;
    }
    double px = ldf(c, pc + 0x50), py = ldf(c, pc + 0x54), sp = hypot(vx, vy);
    int along = ring_along, ahead = open ? !(nr & 1) : rnd(&seed) & 1, best = -1, blocked = 0;
    float m0 = open ? 90.0f + 35.0f * (float)nr : 220.0f + (float)(rnd(&seed) % 160), cost = 1e9f;
    for (int k = 0; k < nring; k++) {
        float q = fabsf(ring[k].m - m0) + (ring[k].ahead == ahead ? 0.0f : 1000.0f);
        if (q >= cost) continue;
        if (!spot_clear(c, h, r, ring[k].x, ring[k].y)) { blocked++; continue; }
        cost = q, best = k;
    }
    if (best < 0) {
        if (getenv("RN_FREELOG")) rn_log("FREE %s fail: %s %d (ring %d spots, %d blocked, %d walks stalled)", open ? "open" : "respawn spot", G(ld(c, r + 0x14, 4) + 0x73c), nr, nring, blocked, ring_stall);
        return 0;
    }
    uint32_t s2 = ring[best].sec, n2 = ring[best].node, w = 0, ft = c->ftop;
    float m = ring[best].m;
    // dir: the player's way along the road (`along`, at the player's own node; the node 300 m on may bend past 90 degrees from the
    // player's heading, its direction vector says nothing about the way); a stopped player: the rival keeps its own. The racer's
    // route flag is 0 along the node direction, 1 against (forward flag = dir == 0, 0x44ae02).
    uint32_t drv = ld(c, r + 0x2c, 4), had = drv ? ld(c, drv, 4) : 0, flag = !along ^ rev;
    if (sp < 2.0) { c->r[ECX] = drv; flag = free_dir(c) != 0; }
    float dir = flag ? -1.0f : 1.0f, lo = ldf(c, 0x700d58), v = sp > lo ? (float)sp : lo;   // 0x426617: 8 m/s at least
    if (open && v < 14.0f) v = 14.0f;   // rolling from the first second
    if (drv && on > 0) rival_flip(c, drv, flag);
    double was = hypot(ldf(c, r + 0x50) - px, ldf(c, r + 0x54) - py);
    uint32_t p[9] = {r, s2, n2, 0, 1, 0, 0, 0, 0};
    memcpy(&p[3], &v, 4), memcpy(&p[5], &dir, 4);
    call_guest(c, 0x427f70, 9, p);
    c->ftop = ft;
    double dx = ldf(c, r + 0x50) - px, dy = ldf(c, r + 0x54) - py;
    if (getenv("RN_FREELOG"))
        rn_log("FREE respawn %s%s: %.0f m -> %.0f m %s (walk %s %.0f m, ret %u, node %08x dir %+.0f flag %u vt %08x, %.0f m/s) frame %u", G(ld(c, r + 0x14, 4) + 0x73c),
               open ? " (open)" : stuck ? " (stuck)" : "", was, hypot(dx, dy), dx * vx + dy * vy >= 0 ? "ahead" : "behind", ahead ? "ahead" : "behind", m, w, n2, dir, flag, had, v, rn_telem.presents);
    return 1;
}
// Once a second in a race: every rival's state (see R_GRID). go = the player has driven off; late = 10 s after the race start.
static void free_rivals(Ctx *c, uint32_t h, uint32_t pc, double vx, double vy, int go, int late) {
    static int off = -1; static float far;
    if (off < 0) off = getenv("RN_RESPAWN") && !atoi(getenv("RN_RESPAWN")), far = getenv("RN_RIVALFAR") ? (float)atof(getenv("RN_RIVALFAR")) : 400.0f;
    if (off || !pc || rn_race_over()) return;   // after the finish the game's AIActionEndOfRace stops every rival where it is
    double px = ldf(c, pc + 0x50), py = ldf(c, pc + 0x54);
    int nr = -1, moved = 0, ngrid = 0;   // moved: one far or stuck respawn a second, as before
    for (uint32_t r = ld(c, h, 4), n = 0; r != h && n < 200; r = ld(c, r, 4), n++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (!e || ld(c, e + 4, 4) != 2) continue;
        nr++;
        int k = 0;
        while (k < 16 && riv[k].r && riv[k].r != r) k++;
        if (k == 16) continue;   // more than 16 rivals in one race: not possible (NRIV_MAX 9)
        uint32_t rec = ld(c, r + 0x1c, 4);
        if (rec && ld(c, rec + 0x10, 2)) continue;   // this rival finished (record +0x10 = finish reason, FinishCar 0x435315 also swapped its driver)
        float x = ldf(c, r + 0x50), y = ldf(c, r + 0x54);
        if (!riv[k].r) riv[k].r = r, riv[k].st = R_GRID, riv[k].since = rn_telem.presents;
        else riv[k].slow = hypot(x - riv[k].x, y - riv[k].y) < 2.0 ? riv[k].slow + 1 : 0;
        riv[k].x = x, riv[k].y = y;
        if (riv[k].st == R_COOLDOWN && rn_telem.presents >= riv[k].since + 480) riv_go(c, k, R_ROAD, "8 s");
        int stuck = riv[k].slow >= 5, gone = hypot(x - px, y - py) >= far;
        if (riv[k].st == R_GRID && go) {
            int got = riv_place(c, h, pc, r, vx, vy, 1, nr, 0);
            if (got < 0) return;
            if (got) { riv_go(c, k, R_COOLDOWN, "opening spot"); continue; }
        }
        if (riv[k].st == R_COOLDOWN || !late || moved || !(stuck || gone)) { ngrid += riv[k].st == R_GRID; continue; }
        int got = riv_place(c, h, pc, r, vx, vy, 0, nr, stuck);
        if (got < 0) return;
        if (got) { riv_go(c, k, R_COOLDOWN, stuck ? "stuck" : "far"); moved = 1; }
        else ngrid += riv[k].st == R_GRID;
    }
    static uint32_t told;   // the frame the opening ended (logged once a race)
    if (go && !ngrid && nr >= 0 && told < go_at && getenv("RN_FREELOG"))
        told = rn_telem.presents, rn_log("FREE opening done: %d rivals on the road %.1f s after the go, frame %u", nr + 1, (rn_telem.presents - go_at) / 60.0, rn_telem.presents);
}

// Traffic (OWNER 2026-10-28: "traffic like MW"): the TrafficTeleporter keeps cars only along the race route, so in the open
// world the player outruns them and drives empty streets. MW's AITrafficManager rule, with this game's own placer: every
// 30 frames, while fewer than TMOVE_NEAR cars are within 250 m, one car that is parked (driver +0x4d1), farther than 400 m,
// or behind the player (dot with his motion < 0) and > 130 m away for 4 s, goes to a node TMOVE_AHEAD +-50 m + 1 s of speed
// ahead on the road (0x4563d0 from the player's node, as riv_place), at least 150 m away in a straight line (out of view
// distance) and 20 m from every car. The move is the Free Run move's own tail (0x59a2c0 at 0x59a5ac..0x59a6c6): lane =
// 0x5995e0(ecx = teleporter; node, side = 0x59aea0's coin on [0x78a304]), -1 = none; speed = 0x42adf0 (eax node, ecx lane:
// byte [node + lane + 0x6a]); 0x59a7c0(car, node, 0, lane, 0x41c4b127, speed, 0) (thiscall, ret 0x1c: a lane >= 6 drives
// against the node direction, then 0x427f70 places the car and its AI). RN_FREETMOVE=0: off.
#define TMOVE_NEAR 10
#define TMOVE_AHEAD 200.0f
static int n_tmove, n_tfail, n_twhy[4];
static void free_tmove(Ctx *c, uint32_t h, uint32_t pc, double vx, double vy) {
    static int off = -1; static uint32_t seed = 0x7a11c0de;
    static struct { uint32_t car, since; } bh[64];
    static uint32_t race;
    if (rn_new_race(&race)) memset(bh, 0, sizeof bh);   // 64 slots per race (they filled up over races)
    if (off < 0) off = getenv("RN_FREETMOVE") && !atoi(getenv("RN_FREETMOVE"));
    uint32_t tele = ld(c, h + 0x2f0, 4);              // the TrafficTeleporter of this race's car list (ecx at 0x420c77), read live
    if (off || !tele || !pc) return;
    double px = ldf(c, pc + 0x50), py = ldf(c, pc + 0x54), sp = hypot(vx, vy);
    uint32_t pick = 0; int prio = 0, near = 0;
    double far = 400;
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), v = ld(c, r + 0x2c, 4);
        if (!e || ld(c, e + 4, 4) != 3 || !v) continue;
        double dx = ldf(c, r + 0x50) - px, dy = ldf(c, r + 0x54) - py, d = hypot(dx, dy);
        near += d < 250;
        int b = 0;
        while (b < 63 && bh[b].car && bh[b].car != r) b++;
        if (bh[b].car != r) bh[b].car = r, bh[b].since = 0;
        int behind = sp > 2 && dx * vx + dy * vy < 0 && d > 130;
        if (!behind) bh[b].since = 0;
        else if (!bh[b].since) bh[b].since = rn_telem.presents;
        int p = c->mem[v + 0x4d1] ? 3 : d > far ? 2 : behind && rn_telem.presents >= bh[b].since + 240 ? 1 : 0;
        if (p > prio) prio = p, pick = r;
    }
    if (near >= TMOVE_NEAR || !pick) return;
    if (!respawn_pair) respawn_pair = guest_alloc(8);
    uint32_t zero = 0, ft = c->ftop;
    c->r[EAX] = pc; uint32_t sec = call_guest(c, 0x428150, 1, &zero);
    c->r[EAX] = pc; uint32_t node = call_guest(c, 0x428160, 1, &zero);
    st(c, respawn_pair, sec, 4), st(c, respawn_pair + 4, node, 4);
    c->r[EAX] = respawn_pair;
    if (!sec || !node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { c->ftop = ft; n_tfail++, n_twhy[3]++; return; }
    int along = ldf(c, node + 0xc) * vx + ldf(c, node + 0x10) * vy >= 0, lane = -1;
    uint32_t n2 = 0;
    float m = 0;
    // One spot per check; n_twhy counts the refusals: [3] no player node, walk stalled / within 150 m of the player or 20 m of a car / no free lane.
    for (int t = 0; t < 1 && lane == -1; t++) {
        m = TMOVE_AHEAD - 50.0f + (float)(rnd(&seed) % 101) + (float)sp;
        st(c, respawn_pair, sec, 4), st(c, respawn_pair + 4, node, 4);
        uint32_t a[5] = {respawn_pair, 1, 0, (uint32_t)along, 0};
        memcpy(&a[2], &m, 4);
        c->r[ECX] = sec, c->r[EAX] = node;
        call_guest_cdecl(c, 0x4563d0, 5, a);
        n2 = ld(c, respawn_pair + 4, 4);
        c->r[EAX] = respawn_pair;
        if (n2 == node || !(call_guest(c, 0x456c90, 0, NULL) & 0xff)) { n_twhy[0]++; continue; }
        float nx = ldf(c, n2), ny = ldf(c, n2 + 4);
        int ok = hypot(nx - px, ny - py) >= 150;
        for (uint32_t o = ld(c, h, 4), j = 0; o != h && j < 200 && ok; o = ld(c, o, 4), j++)
            ok = o == pick || hypot(ldf(c, o + 0x50) - nx, ldf(c, o + 0x54) - ny) >= 20;
        if (!ok) { n_twhy[1]++; continue; }
        c->r[ECX] = tele;
        uint32_t side = call_guest(c, 0x59aea0, 0, NULL) & 0xff, la[2] = {n2, side};
        c->r[ECX] = tele;
        lane = (int)call_guest(c, 0x5995e0, 2, la);
        if (lane == -1) n_twhy[2]++;
    }
    if (lane == -1) { c->ftop = ft; n_tfail++; return; }
    c->r[EAX] = n2, c->r[ECX] = (uint32_t)lane;
    call_guest(c, 0x42adf0, 0, NULL);
    float v = (float)c->st[c->ftop];
    fpop(c);    // a pop, not ftop = ft: the slot's tag stays set otherwise, and 0x59a7c0's next push (0x442590) reads it as a stack overflow -> NaN

    uint32_t p[7] = {pick, n2, 0, (uint32_t)lane, 0x41c4b127, 0, 0};
    memcpy(&p[5], &v, 4);
    double was = hypot(ldf(c, pick + 0x50) - px, ldf(c, pick + 0x54) - py);
    c->r[ECX] = tele;
    call_guest(c, 0x59a7c0, 7, p);
    c->ftop = ft;
    for (int b = 0; b < 64; b++) if (bh[b].car == pick) bh[b].since = 0;
    n_tmove++;
    static int shown;
    if (getenv("RN_FREELOG") && shown++ < 40)
        rn_log("FREE tmove %s %.0f m -> %.0f m (walk %.0f m, lane %d, %.1f m/s, %d near) frame %u", prio == 3 ? "parked" : prio == 2 ? "far" : "behind", was,
               hypot(ldf(c, pick + 0x50) - px, ldf(c, pick + 0x54) - py), m, lane, v, near, rn_telem.presents);
}

// Traffic driver profile, used by the RN_AILOG speed log (host/rivals.c).
// 0 slow 20%, 1 normal 45%, 2 fast 25%, 3 very fast 10%; RN_TRAFPROF=0: -1, none.
int traffic_profile(uint32_t ai) {
    static int off = -1;
    if (off < 0) { const char *e = getenv("RN_TRAFPROF"); off = e && e[0] == '0'; }
    if (off) return -1;
    uint32_t b = (ai >> 4) * 0x9e3779b1u >> 24;   // AI objects are aligned; a different mix from the cave's x0.85..1.15
    return b < 51 ? 0 : b < 166 ? 1 : b < 230 ? 2 : 3;
}

// Back in the front end (host/phase.c): free mode's event is over; the game's values come back.
void free_frontend(Ctx *c) {
    if (!live) return;
    live = 0;
    if (zone_at) st(c, zone_at, zone_was, 4), zone_at = 0;   // free_place's clear zone back to the game's value
    if (cu_was >= 0) cu_was = -1, free_curves(c, 0);   // [0x78a400] itself: 0x431df0 reset it on the way here (flow 1)
}
// A race's grid is placed (host/phase.c; Restart and the career retry too): what the guest callbacks fill per race starts empty.
// Lifetime (docs/re/gameflow.md): cars, drivers, the car list and its TrafficTeleporter are freed by the teardown 0x422130 and made
// again by the build 0x421f00, which places the grid (0x422a70, here) before the records (0x434590 -> rm_records refills xrec).
// No car is made or freed inside a race; a finished car gets a new driver (FinishCar 0x435315), so rdir is not used after the finish.
void free_race_begin(Ctx *c) {
    (void)c;
    memset(rdir, 0, sizeof rdir), nxrec = 0;
    drove = 0, go_at = 0, memset(riv, 0, sizeof riv);
    n_game = n_free = n_far = n_kept = n_offbit = n_onbit = 0, n_tmove = n_tfail = 0, memset(n_twhy, 0, sizeof n_twhy);
}

void free_tick(Ctx *c) {
    static uint32_t start;           // the first race frame: respawns wait 10 s (the grid)
    // RN_FREELOG probes and speeds: this race's (zeroed when host/phase.c begins a new race)
    static uint32_t race, first, last_contact, cand[64], acts[64][0x16], last_type[64], tframe[200], tcar[200], ntcar;
    static double tw[2], was[2], rp[8][2];
    static float tpos[200][2], ppos[2], last[64][2];
    static int ncand;
    if (rn_new_race(&race)) {
        start = first = last_contact = 0, ncand = 0, ntcar = 0;
        memset(cand, 0, sizeof cand), memset(acts, 0, sizeof acts), memset(last_type, 0, sizeof last_type), memset(tframe, 0, sizeof tframe), memset(tcar, 0, sizeof tcar);
        memset(tw, 0, sizeof tw), memset(was, 0, sizeof was), memset(rp, 0, sizeof rp), memset(tpos, 0, sizeof tpos), memset(ppos, 0, sizeof ppos), memset(last, 0, sizeof last);
    }
    if (!live || !rn_racing()) return;
    // The RaceManager's frame 0x435570 calls the record update 0x4338c0 (edi = record: route progress +0x14/+0x1c/+0x20, checkpoint
    // +4/+6/+8) for each record of its own, so the extra records get the same call (RN_FREEXREC=0: not).
    static int xr = -1;
    if (xr < 0) xr = !getenv("RN_FREEXREC") || atoi(getenv("RN_FREEXREC"));
    // The RM never ranks an extra record (position +0xa stays 0), and the catch-up 0x44c010 reads its position curve 0x779f38/0x779f78
    // at index (pos[player rec] - pos[rival rec]) + 7 (or + 8 when < 0): an extra at 0 against a player at 1..4 got a leader's slowdown
    // or a tail's boost by rank alone. Each extra gets the player's position, so the index is 7 (equal ranks) and the route gap decides.
    uint32_t prec = 0, rl = ld(c, 0x7361f8, 4);
    for (uint32_t r = rl ? ld(c, rl, 4) : 0, k = 0; r && r != rl && k < 200 && !prec; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (e && ld(c, e + 4, 4) == 1) prec = ld(c, r + 0x1c, 4);
    }
    for (uint32_t k = 0; xr && k < nxrec; k++) {
        uint32_t keep[4] = {c->r[EBX], c->r[ESI], c->r[EDI], c->r[EBP]};
        if (ld(c, xrec[k] + 0x10, 2) == 0) {   // still racing (+0x10 = finish reason)
            c->r[EDI] = xrec[k], call_guest(c, 0x4338c0, 0, NULL);
            if (prec) c->mem[xrec[k] + 0xa] = c->mem[prec + 0xa];
        }
        c->r[EBX] = keep[0], c->r[ESI] = keep[1], c->r[EDI] = keep[2], c->r[EBP] = keep[3];
    }
    if (cu_was < 0 && getenv("RN_FREECU") && atoi(getenv("RN_FREECU"))) {
        cu_was = (int)ld(c, 0x78a400, 4);
        st(c, 0x78a400, 1, 4);
        free_curves(c, 1);
        if (getenv("RN_FREELOG")) rn_log("FREE catch up: game %d, now 1; curve x %.0f -> %.0f m", cu_was, cu_x[0][10], ldf(c, 0x779c78 + 80));
    }
    if (!start) start = rn_telem.presents;
    if (getenv("RN_FREELOG") && (rn_telem.presents == start + 2 || rn_telem.presents == start + 300)) {   // the grid: every racer's place
        uint32_t rh = ld(c, 0x7361f8, 4);
        for (uint32_t r = rh ? ld(c, rh, 4) : 0, k = 0; r && r != rh && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4), kind = e ? ld(c, e + 4, 4) : 0;
            if (kind == 1 || kind == 2) rn_log("FREE grid +%u: %s kind %u grid %d at %.1f %.1f %.1f rec %08x", rn_telem.presents - start, G(e + 0x73c), kind, (int8_t)c->mem[e + 3],
                                               ldf(c, r + 0x50), ldf(c, r + 0x54), ldf(c, r + 0x58), ld(c, r + 0x1c, 4));
        }
    }
    if (rn_telem.presents % 30 == 0 && rn_telem.presents > start + 300) {  // traffic, after the grid
        uint32_t rh = ld(c, 0x7361f8, 4), me = 0;
        for (uint32_t r = rh ? ld(c, rh, 4) : 0, k = 0; r && r != rh && k < 200 && !me; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (e && ld(c, e + 4, 4) == 1) me = r;
        }
        if (me && (tw[0] || tw[1])) free_tmove(c, rh, me, (ldf(c, me + 0x50) - tw[0]) * (60.0 / 30), (ldf(c, me + 0x54) - tw[1]) * (60.0 / 30));
        if (me) tw[0] = ldf(c, me + 0x50), tw[1] = ldf(c, me + 0x54);
    }
    if (rn_telem.presents % 60 == 0) {
        uint32_t rh = ld(c, 0x7361f8, 4), me = 0;
        for (uint32_t r = rh ? ld(c, rh, 4) : 0, k = 0; r && r != rh && k < 200 && !me; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (e && ld(c, e + 4, 4) == 1) me = r;
        }
        double x = me ? ldf(c, me + 0x50) : 0, y = me ? ldf(c, me + 0x54) : 0;   // m/s over the last second
        static int shown;
        if (me && !shown && getenv("RN_FREELOG")) {       // one line: the racer vtable slot and the player's driver class
            uint32_t pd = ld(c, me + 0x2c, 4), pv = pd ? ld(c, pd, 4) : 0;
            rn_log("FREE vtable 0x6c89f0+0x40 = %08x; player driver %08x vt %08x slot40 %08x", ld(c, 0x6c89f0 + 0x40, 4), pd, pv, pv ? ld(c, pv + 0x40, 4) : 0), shown = 1;
        }
        static int ropen = -1;
        if (ropen < 0) ropen = !getenv("RN_RIVALOPEN") || atoi(getenv("RN_RIVALOPEN"));
        drove = (was[0] || was[1]) && hypot(x - was[0], y - was[1]) > 10.0 ? drove + 1 : 0;   // the parked car drifts 4-7 m/s, a grid teleport is one jump; driving is 10+ m/s, seconds in a row
        if (me && ropen && drove >= 2 && !go_at) go_at = rn_telem.presents;   // the player drives 2 s = the go (the game re-grids at the pre-race screen, after `start`)
        if (me) free_rivals(c, rh, me, x - was[0], y - was[1], go_at != 0, rn_telem.presents > start + 600);
        was[0] = x, was[1] = y;
    }
    // RN_BODYLOG: the player's position every frame (WORLD vs 1001 handling A/B: z jitter = bumps, xy = speed and turns).
    static int body = -1;
    if (body < 0) body = getenv("RN_BODYLOG") != NULL;
    if (body) {
        uint32_t rh = ld(c, 0x7361f8, 4);
        for (uint32_t r = rh ? ld(c, rh, 4) : 0, k = 0; r && r != rh && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (e && ld(c, e + 4, 4) == 1) { rn_log("BODY %u %.3f %.3f %.3f", rn_telem.presents, ldf(c, r + 0x50), ldf(c, r + 0x54), ldf(c, r + 0x58)); break; }
        }
    }
    static int log = -1;
    if (log < 0) log = getenv("RN_FREELOG") != NULL;
    if (!log) return;
    uint32_t h = ld(c, 0x7361f8, 4), player = 0;
    // Every 5 s: each rival's skill level (entrant+0x735) and speed over those 5 s (personality A/B).
    if (h && rn_telem.presents % 300 == 0) {
        char b[640];
        int n = 0, i = 0;
        for (uint32_t r = ld(c, h, 4), k = 0; r && r != h && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4), rec = ld(c, r + 0x1c, 4);
            if (e && ld(c, e + 4, 4) == 1) n += snprintf(b + n, sizeof b - n, " PLAYER [rec14 %.0f route %.0f pos %d] |", rec ? ldf(c, rec + 0x14) : -1.0, ldf(c, r + 0x814), rec ? c->mem[rec + 0xa] : -1);
        }
        for (uint32_t r = ld(c, h, 4), k = 0; r && r != h && k < 200 && i < 8; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (!e || ld(c, e + 4, 4) != 2) continue;
            double x = ldf(c, r + 0x50), y = ldf(c, r + 0x54);
            uint32_t rec = ld(c, r + 0x1c, 4);
            n += snprintf(b + n, sizeof b - n, " %s L%d %.0f @%.0f,%.0f [rec14 %.0f route %.0f pos %d cu %.2f]", G(e + 0x73c), (int8_t)c->mem[e + 0x735], hypot(x - rp[i][0], y - rp[i][1]) / 5, x, y,
                          rec ? ldf(c, rec + 0x14) : -1.0, ldf(c, r + 0x814), rec ? c->mem[rec + 0xa] : -1, ldf(c, r + 0x404));
            rp[i][0] = x, rp[i][1] = y, i++;
        }
        if (i) rn_log("FREE rivals%s m/s frame %u", b, rn_telem.presents);
    }
    // A contact: a rival's centre within 4 m of the player's (car to car), 10 s after the start (the grid), at most one line per second.
    if (!first) first = rn_telem.presents;
    if (h && rn_telem.presents > first + 600 && rn_telem.presents > last_contact + 60) {
        uint32_t pc = 0;
        for (uint32_t r = ld(c, h, 4), k = 0; r && r != h && k < 200 && !pc; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (e && ld(c, e + 4, 4) == 1) pc = r;
        }
        for (uint32_t r = pc ? ld(c, h, 4) : h, k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
            uint32_t e = ld(c, r + 0x14, 4);
            if (!e || ld(c, e + 4, 4) != 2) continue;
            double dx = ldf(c, r + 0x50) - ldf(c, pc + 0x50), dy = ldf(c, r + 0x54) - ldf(c, pc + 0x54);
            if (dx * dx + dy * dy < 16) { rn_log("FREE contact %s %.1f m frame %u", G(e + 0x73c), sqrt(dx * dx + dy * dy), rn_telem.presents); last_contact = rn_telem.presents; }
        }
    }
    // Each rival's current action (docs/openworld/re_rivals_ai.md 0: [obj+0x3f8], type +0x1f8: 0 Pass, 1 AvoidAvoidable, 5 Block,
    // 7 JustDrive, 0xa GetUnstuck, 0xc IJustGotHit, 0xe AccidentRecovery): every change counted, printed every 10 s.
    for (int j = 0; j < ncand; j++) {
        uint32_t act = ld(c, cand[j], 4) == 0x6c89f0 ? ld(c, cand[j] + 0x3f8, 4) : 0, ty = act ? ld(c, act + 0x1f8, 4) : 0x15;
        if (ty > 0x15) ty = 0x15;
        if (ty != last_type[j]) acts[j][ty]++, last_type[j] = ty;
    }
    // Each traffic car that jumped > 60 m in one frame was moved by the TrafficTeleporter (0x599830): where it landed, as the
    // straight and route distance ([car+0x814]) from the player, and whether it is in front of the player's nose (camera side).
    // Keyed by the car pointer: the game reorders this list, so a list index is not a car.
    uint32_t pc = 0;
    for (uint32_t r = h ? ld(c, h, 4) : 0, k = 0; r && r != h && k < 200 && !pc; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (e && ld(c, e + 4, 4) == 1) pc = r;
    }
    double vx = pc ? (ldf(c, pc + 0x50) - ppos[0]) * 60 : 0, vy = pc ? (ldf(c, pc + 0x54) - ppos[1]) * 60 : 0;   // m/s at 60 fps
    if (pc) ppos[0] = ldf(c, pc + 0x50), ppos[1] = ldf(c, pc + 0x54);
    for (uint32_t r = pc ? ld(c, h, 4) : h, k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), i = 0;
        if (!e || ld(c, e + 4, 4) != 3) continue;
        while (i < ntcar && tcar[i] != r) i++;
        if (i == ntcar) { if (ntcar == 200) continue; tcar[ntcar++] = r; tframe[i] = 0; }
        float x = ldf(c, r + 0x50), y = ldf(c, r + 0x54);
        if (tframe[i] + 1 == rn_telem.presents && hypot(x - tpos[i][0], y - tpos[i][1]) > 60) {
            double dx = x - ldf(c, pc + 0x50), dy = y - ldf(c, pc + 0x54);
            rn_log("FREE tp car %u: %.0f m (route %+.0f) %s, player %.0f m/s, frame %u", i, hypot(dx, dy), ldf(c, r + 0x814) - ldf(c, pc + 0x814),
                   dx * vx + dy * vy >= 0 ? "ahead" : "behind", hypot(vx, vy), rn_telem.presents);
        }
        tpos[i][0] = x, tpos[i][1] = y, tframe[i] = rn_telem.presents;
    }
    if (rn_telem.presents % 120) return;
    int ntraffic = 0;
    for (uint32_t r = h ? ld(c, h, 4) : 0, k = 0; r && r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4), kind = e ? ld(c, e + 4, 4) : 0;
        if (kind == 1) player = r;
        ntraffic += kind == 3;
    }
    if (!player) return;
    char line[256]; int o = snprintf(line, sizeof line, "FREE frame %u traffic %d:", rn_telem.presents, ntraffic);
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (!e || ld(c, e + 4, 4) != 2) continue;
        double dx = ldf(c, r + 0x50) - ldf(c, player + 0x50), dy = ldf(c, r + 0x54) - ldf(c, player + 0x54);
        double dz = ldf(c, r + 0x58) - ldf(c, player + 0x58);
        // route distance [car+0x814] (0x41f5f0) ahead (+) or behind (-) the player's
        o += snprintf(line + o, sizeof line - o, " %s %.0f m (%+.0f)", G(e + 0x73c), sqrt(dx * dx + dy * dy + dz * dz),
                      ldf(c, r + 0x814) - ldf(c, player + 0x814));
        if (o > 200) break;
    }
    // docs/openworld_e_re.md B: each rival's AI context: the racer's AIVehicle (vtable 0x6c89f0, ctor 0x4620c0 over the base 0x44a330, +4 = its vehicle) with the
    // context at +0x2c and its PATH list (ctx + 0x3a8 -> object: count +4, node objects at +8 + 4 i, section byte +0x5c, node short
    // +0x5e (short), current index +0xac).
    // The AI factory 0x425fe0 stores each car's AI object at car+0x2c (esi[0xb], kind esi[9]; case 3 = 0x4620c0), so the race list
    // gives every AIVehicle; new ones are appended so acts[] keeps its index (audit 2026-11-05 C05: was a 1 GB scan every 120 frames).
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200 && ncand < 64; r = ld(c, r, 4), k++) {
        uint32_t obj = ld(c, r + 0x2c, 4), j = 0;
        if (!obj || obj > GUEST_MEM - 0x500 || ld(c, obj, 4) != 0x6c89f0) continue;
        while (j < (uint32_t)ncand && cand[j] != obj) j++;
        if (j < (uint32_t)ncand) continue;
        cand[ncand++] = obj;
        rn_log("FREE aivehicle %08x: +4 %08x +8 %08x", obj, ld(c, obj + 4, 4), ld(c, obj + 8, 4));
    }
    for (int j = 0; j < ncand; j++) {
        uint32_t obj = cand[j], veh = ld(c, obj + 4, 4);
        if (ld(c, obj, 4) != 0x6c89f0 || veh < 0x10000 || veh > (GUEST_MEM - 0x10000)) continue;
        uint32_t e = ld(c, veh + 0x14, 4);
        if (!e || ld(c, e + 4, 4) != 2) continue;
        uint32_t ctx = obj + 0x2c, path = ld(c, ctx + 0x3a8, 4), cnt = path ? ld(c, path + 4, 4) : 0;
        // Catch-up 0x44bd10 (eax = this AIVehicle; docs/openworld/re_rivals_ai.md 4): the boost [veh+0x404], [obj+0x4b8], the gate byte
        // [obj+0x46c] (1 in the base ctor 0x44a330, vslot 0x3c 0x44c920), the racer flag [[obj+0x3f8]+0x1f2], the target [obj+0x470].
        uint32_t act = ld(c, obj + 0x3f8, 4);
        char pl[400]; int q = snprintf(pl, sizeof pl, "FREE path %s pos %.0f %.0f cu %.2f %.2f on %u/%u tgt %08x slot %d idx %d n %u:", G(e + 0x73c),
                                       ldf(c, veh + 0x50), ldf(c, veh + 0x54), ldf(c, veh + 0x404), ldf(c, obj + 0x4b8), c->mem[obj + 0x46c],
                                       act ? c->mem[act + 0x1f2] : 9, ld(c, obj + 0x470, 4), (int8_t)c->mem[ctx + 0x388],
                                       path ? (int)ld(c, path + 0xac, 4) : -1, cnt);
        int ps = -2, pn = 0, first = 0;                   // run-length: section:first-last node
        for (uint32_t i = 0; i <= cnt && i < 64 && q < 360; i++) {
            uint32_t n = i < cnt ? ld(c, path + 8 + 4 * i, 4) : 0;
            int sec = i < cnt ? (int8_t)c->mem[n + 0x5c] : -3, nd = i < cnt ? (int16_t)(c->mem[n + 0x5e] | c->mem[n + 0x5f] << 8) : 0;
            if (sec != ps) { if (ps != -2) q += snprintf(pl + q, sizeof pl - q, " %d:%d-%d", ps, first, pn); ps = sec, first = nd; }
            pn = nd;
        }
        rn_log("%s", pl);
    }
    // The three nearest traffic cars (kind 3): whether the game keeps traffic near the player at all.
    double near[3] = {1e9, 1e9, 1e9};
    for (uint32_t r = ld(c, h, 4), k = 0; r != h && k < 200; r = ld(c, r, 4), k++) {
        uint32_t e = ld(c, r + 0x14, 4);
        if (!e || ld(c, e + 4, 4) != 3) continue;
        double dx = ldf(c, r + 0x50) - ldf(c, player + 0x50), dy = ldf(c, r + 0x54) - ldf(c, player + 0x54);
        double d = sqrt(dx * dx + dy * dy);
        for (int j = 0; j < 3; j++) if (d < near[j]) { double t = near[j]; near[j] = d; d = t; }
    }
    o += snprintf(line + o, sizeof line - o, " | traffic near %.0f %.0f %.0f m | tmove %d fail %d (player node %d, walk %d, close %d, lane %d)", near[0], near[1], near[2], n_tmove, n_tfail, n_twhy[3], n_twhy[0], n_twhy[1], n_twhy[2]);
    rn_log("%s", line);
    // Every 10 s, each traffic car as TrafficTeleporter 0x598600 sees it: the cars [L+0x28 + 4 i], i from L[9] to L[6]
    // (L = [0x7361f8], 0x41f680/0x41f690), driver V = car+0x2c (0x41f5d0). Flags of V: +0x4d1 parked (0x583350, the
    // teleporter recycles it), +0x410 no path after a reset (0x583700: braked, never parked), +0x4d0. Moved = metres since the last line.
    if (rn_telem.presents % 600) return;
    char tl[1600]; int t = snprintf(tl, sizeof tl, "FREE tcars:");
    uint32_t L = ld(c, 0x7361f8, 4);
    for (uint32_t i = ld(c, L + 0x24, 4), k = 0; i < ld(c, L + 0x18, 4) && k < 64 && t < 1100; i++, k++) {
        uint32_t r = ld(c, L + 0x28 + 4 * i, 4), v = ld(c, r + 0x2c, 4);
        float x = ldf(c, r + 0x50), y = ldf(c, r + 0x54);
        double dx = x - ldf(c, player + 0x50), dy = y - ldf(c, player + 0x54);
        t += snprintf(tl + t, sizeof tl - t, " %u:%.0fm/%.0f%s%s%s", i, sqrt(dx * dx + dy * dy), hypot(x - last[k][0], y - last[k][1]),
                      c->mem[v + 0x4d1] ? "P" : "", c->mem[v + 0x410] ? "N" : "", c->mem[v + 0x4d0] ? "o" : "");
        last[k][0] = x, last[k][1] = y;
    }
    for (int j = 0; j < ncand; j++) {
        uint32_t veh = ld(c, cand[j] + 4, 4), e = veh > 0x10000 && veh < (GUEST_MEM - 0x10000) ? ld(c, veh + 0x14, 4) : 0;
        if (!e || ld(c, e + 4, 4) != 2) continue;
        char al[200]; int a = snprintf(al, sizeof al, "FREE actions %s:", G(e + 0x73c));
        for (int ty = 0; ty < 0x16; ty++) if (acts[j][ty]) a += snprintf(al + a, sizeof al - a, " %x:%u", ty, acts[j][ty]);
        rn_log("%s", al);
    }
    t += snprintf(tl + t, sizeof tl - t, " | spacing %d game, %d free | far %d kept %d | placed on node bit %d, off %d", n_game, n_free, n_far, n_kept, n_onbit, n_offbit);
    // The catch-up's gates (re_rivals_ai.md 4): 0x78a344 (byte), 0x7361a8, 0x78a320 > 0, 0x7360ac, [0x7361f0] != 9, players 0x7361c4,
    // player 0x7361bc, strength [0x78a404 + 4 slot], difficulty 0x78a40c.
    uint32_t pt = ld(c, 0x7361f0, 4);
    rn_log("FREE catchup: 78a344 %u 7361a8 %u 78a320 %d 7360ac %u 7361f0 %u 7361c4 %u 7361bc %08x 78a404 %.2f %.2f 78a40c %u 78a2f0 %x 78a400 %u 77a4a0 %.1f 77a49c %.2f",
           c->mem[0x78a344], ld(c, 0x7361a8, 4), (int)ld(c, 0x78a320, 4), ld(c, 0x7360ac, 4), pt ? ld(c, pt, 4) : 0xffffffffu,
           ld(c, 0x7361c4, 4), ld(c, 0x7361bc, 4), ldf(c, 0x78a404), ldf(c, 0x78a408), ld(c, 0x78a40c, 4), ld(c, 0x78a2f0, 4), ld(c, 0x78a400, 4), ldf(c, 0x77a4a0), ldf(c, 0x77a49c));
    static int curves;      // the catch-up curves 0x44c010 reads (x = route gap * [0x7372b0]): loaded at run time
    if (!curves++) {
        rn_log("FREE cu 7372b0 %.3f 78a318 %u 78a31c %u 78a300 %u", ldf(c, 0x7372b0), ld(c, 0x78a318, 4), ld(c, 0x78a31c, 4), ld(c, 0x78a300, 4));
        for (uint32_t r = 0; r < 16; r++) {
            char b[400]; int n = 0;
            for (int k = 0; k < 22; k++) n += snprintf(b + n, sizeof b - n, " %.2f", ldf(c, 0x779c78 + 0x58 * r + 4 * k));
            rn_log("FREE cu %08x%s", 0x779c78 + 0x58 * r, b);
        }
        char b[400]; int n = 0;
        for (int k = 0; k < 32; k++) n += snprintf(b + n, sizeof b - n, " %.2f", ldf(c, 0x779f38 + 4 * k));
        rn_log("FREE cu pos%s", b);
    }
    rn_log("%s", tl);
}

// The traffic placer 0x598bf0 (thiscall, ecx = [esi + 0x2f0], arg = the entrant), run step by step from race start 0x422a70
// (PATCH 0x422b36, cave 0x673842: jmp [SCREEN_ADDR+0x7c]): 0x5991a0 along the route (only if 0x421a50), 0x598c80 a grid slot,
// 0x598fb0 any free spot, each with 100 random tries (free mode repeats the last one 4 times). A try fails on 0x4420a0 (node flag, 2 of 3 nodes), on the clear zone round
// the player's start (59aa60: [[0x736174] + side * 4 + 0xcc], 500 m, while he stands still) and on 31 m to every car already
// placed (+0xd4, 0x59b1e0): on the base track's network (1001, and the WORLD's 1010, 520 nodes) about 13 of 18 cars fit and the
// other tries are lost (0.1 % of 3000 tries still pass; docs/traffic_placement.md). In free mode the clear zone is FREE_ZONE
// for the placement (RN_FREEZONE, metres) and the whole race, and the table is put back when the race ends (free_tick);
// RN_FREE=0 leaves the game's value. The zone must stay small after the start: the TrafficTeleporter's Free Run move
// 0x59a2c0 walks the road graph from the player by 250 m and gives up past 500 m route distance, while 0x59aa60 rejects
// every spot nearer than this zone (500 m), so nearly every move failed and the car was parked (0x5832a0, car+0x4d1);
// the few that passed all landed on the same node at ~500 m (the tight groups of runs/jump_3_1001: all 19 cars parked).
#define FREE_ZONE 100.0f
static uint32_t free_place(Ctx *c) {
    uint32_t e = ARG(0), self = c->r[ECX], r = 0;
    static int gridlog;     // RN_FREELOG: the start positions 0x422580 made, still in 0x422a70's frame (PATCH 0x422a78: 10 slots of 0x20 end at ebp & -16)
    if (!gridlog++ && getenv("RN_FREELOG")) {
        uint32_t b = (c->r[EBP] & ~15u) - 0x140;
        for (int k = 0; k < 10; k++) rn_log("FREE start slot %d: %.1f %.1f %.1f dir %04x", k + 1, ldf(c, b + 0x20 * k), ldf(c, b + 0x20 * k + 4), ldf(c, b + 0x20 * k + 8), ld(c, b + 0x20 * k + 0x10, 2));
    }
    int route = ld(c, 0x78a344, 1) & 0xff || ld(c, 0x7361a8, 4), step = 0;
    uint32_t tb = ld(c, 0x736174, 4) + ld(c, 0x78a2fc, 4) * 4, sp = ld(c, tb + 0xd4, 4), zn = ld(c, tb + 0xcc, 4);
    if (live) {
        float f = getenv("RN_FREEZONE") ? atof(getenv("RN_FREEZONE")) : FREE_ZONE;
        if (zone_at != tb + 0xcc) zone_at = tb + 0xcc, zone_was = zn;
        memcpy(&c->mem[tb + 0xcc], &f, 4);
    }
    c->r[EAX] = 0x78a2f0;
    if (route) { c->r[ECX] = self; r = call_guest(c, 0x5991a0, 1, &e); step = 1; }
    if (!r) { c->r[ECX] = self; r = call_guest(c, 0x598c80, 1, &e); step = 2; }
    for (int k = 0; !r && k < (live ? 4 : 1) && (!route || ld(c, SCREEN_ADDR + 28, 4)); k++) { c->r[ECX] = self; r = call_guest(c, 0x598fb0, 1, &e); step = 3; }   // free mode: 400 tries
    if (!live) st(c, tb + 0xcc, zn, 4);
    static int n, lost;
    lost += !r;
    if (getenv("RN_FREELOG")) rn_log("FREE place #%d entrant %08x route=%d spacing %.1f zone %.1f: %s (%d lost)", n++, e, route, *(float *)&sp,
                                     *(float *)&zn, r ? (step == 1 ? "route" : step == 2 ? "grid" : "last resort") : "NOT PLACED", lost);
    return r;
}

// The spacing TrafficTeleporter 0x598600 hands each Free Run move (0x598774 call 0x59b3e0, thiscall ecx = the teleporter,
// arg = the player, float in st0; PATCH 0x598774, cave 0x673848: jmp [SCREEN_ADDR+0x80]). 0x59b3e0 returns 99999 m unless the
// player stands in a TRAFFIC_DENSITY zone (0x43db70: 0x4436d0 type 4 at car+0x800) and no traffic car near him is stopped
// (0x59b8d0: speed [car+0x3d4] < 1, not parked +0x4d1, within 250 m of route); in a zone it is random between the zone's
// two values (0x59b670 / 0x59b6a0: [zone+0x7c + i*4]). 0x599830 passes it to 0x59a2c0 -> 0x59aa60 -> 0x59b1e0, which
// rejects a spot with any car nearer than it, so with 99999 every move fails and the car is parked for good (0x5832a0,
// car+0x4d1). The game wants that on a race track (no new traffic outside its zones or into a jam); 1001 has two zones on
// a 4.4 km loop (on the WORLD 1010 tour 47 of 53 moves got 99999), so after ~60 s all 19 cars stood still (runs/jump_3_1001,
// RN_FREELOG "FREE tcars"). In free mode a 99999 becomes the track's own placement spacing ([[0x736174] + side*4 + 0xd4],
// 31 m, the one the placer 0x598bf0 used at the start); RN_FREE=0 or a race: the game's value.
static uint32_t free_spacing(Ctx *c) {
    uint32_t pl = ARG(0);
    call_guest(c, 0x59b3e0, 1, &pl);
    if (live && c->st[c->ftop] >= 99999.0) {
        uint32_t tb = ld(c, 0x736174, 4) + ld(c, 0x78a2fc, 4) * 4;
        c->st[c->ftop] = ldf(c, tb + 0xd4), n_free++;
    } else n_game++;
    return 0;
}

// TrafficAI update 0x583350 (ebp = the traffic driver): at 0x5833eb a car flagged +0x410 (no path: 0x583700 reset found none,
// or 0x44ca70 lost it) only brakes again (0x44bcb0, vfunc 0x38), every tick, for good; it never retries 0x44cf30 and is never
// parked, so the TrafficTeleporter (0x5988c0 moves only parked cars or ones behind the player on the route) never recycles it
// (on the WORLD three such cars sat 1.8..2.5 km away all run). PATCH 0x5833eb (cave 0x6729f6: jmp [SCREEN_ADDR+0x84]) asks
// here for that byte: in free mode it reads 0, so the car takes the game's own path of every other car: 0x44cf30 again, on
// success it drives (0x583461 clears +0x410), on failure 0x5832a0 parks it and the teleporter moves it near the player.
static uint32_t free_nopath(Ctx *c) {
    return live ? 0 : c->mem[c->r[EBP] + 0x410];
}

// The node test of the Free Run move 0x59a2c0 (0x59a5cf, 0x59a669: call 0x4420b0, eax = road node, cl = side): bit 25 (side 0)
// or 26 (side 1) of [node+0x84] says "traffic may spawn here". Only spawning reads it (also 0x598fb0 at 0x599025 and the
// route move at 0x599bae). A race track sets it on a few stretches only: on 1001 none from 500 to 1750 m and 2500 to 3000 m
// of the route (TRACKB1001, 25 sections), so with the player there the 500 m walk finds no spot and every car is parked in a
// clump. PATCH 0x59a5cf, 0x59a669 (cave 0x439a94: jmp [SCREEN_ADDR+0x88]): in free mode every node passes; the lane
// (0x5995e0), the 31 m spacing and the out-of-sight rules of 0x59aa60 still decide. RN_FREE=0 or a race: the node's bit.
static uint32_t rm_records(Ctx *c), grid_fix(Ctx *c);

// The Free Run move 0x59a2c0 hunts a spot from the player's node: a 250 m walk (0x59a4b8 call 0x4563d0: ecx section, eax node,
// &pair in/out, 1, metres, side, 0), then a loop (0x59a4fa..0x59a7af) that tries the spot and, when it is refused, walks on
// (0x59a763). It gives up only past 500 m of race route ([0x6b5a3c], 0x443d60 on 0x7372b0 at 0x59a598) or at a dead end. On a
// race track the route distance grows with every step forward; in the WORLD the net is strongly connected (citygraph v2c) and
// streets off the route project near it, so the walk circled a block within 500 m of the player for good and the game froze
// ~10 s into WORLD (OWNER 2026-10-28; RN_PROF stacks: 0x598600 > 0x599830 (0x59a2c0 inlined) > 0x4563d0 at 0x59a763).
// PATCH 0x59a4b8, 0x59a763 (cave 0x439a94, told by their returns): in free mode the metres walked in one move count as its
// route distance, so a walk that would take the move past 500 m is undone (the pair stays, the loop ends on its own test, the
// move fails as at a dead end: the car is parked and moved later). RN_FREE=0 or a race: the original walks.
static uint32_t free_walk(Ctx *c, int first) {
    uint32_t a[5] = {ARG(0), ARG(1), ARG(2), ARG(3), ARG(4)};
    static float walked;
    static unsigned stopped;
    static uint32_t seed = 0x3c1a0b17;
    if (live && first) {   // the first walk is 250 m ([0x6b5a38], also the reject radius: not editable), so every car landed ~230 m ahead, 31 m apart; U(250, 480) spreads them
        float m0 = 250.0f + (float)(rnd(&seed) % 231);
        memcpy(&a[2], &m0, 4);
    }
    float m = *(float *)&a[2];
    walked = first ? m : walked + m;
    if (!live || first || walked <= ldf(c, 0x6b5a3c)) return call_guest_cdecl(c, 0x4563d0, 5, a);
    if (getenv("RN_FREELOG") && !(stopped++ & 63)) rn_log("FREE walk stopped %u times (%.0f m)", stopped, walked);
    return 0;
}

static uint32_t free_tnode(Ctx *c) {
    uint32_t ret = ld(c, c->r[ESP], 4);
    if (ret == 0x4345ae) return rm_records(c);   // PATCH 0x4345a9: the RaceManager's records, same cave
    if (ret == 0x422a8b) return grid_fix(c);     // PATCH 0x422a86: the start positions
    if (ret == 0x59a4bd || ret == 0x59a768) return free_walk(c, ret == 0x59a4bd);   // PATCH 0x59a4b8, 0x59a763: the move's walks
    uint32_t bit = ld(c, c->r[EAX] + 0x84, 4) >> ((c->r[ECX] & 0xff) ? 25 : 26) & 1;
    if (live && ld(c, c->r[ESP], 4) == 0x59a66e) bit ? n_onbit++ : n_offbit++;   // the second call: the node the car is placed on
    return live ? 1 : bit;
}

// PATCH 0x4345a9 (cave 0x439a94 as above, ret 0x4345ae): 0x434590 calls 0x434a80 (esi = the RaceManager) to add a record for each
// racer of the car list L = [0x7361f8] (L[7] players, L[8] players + opponents, cars at L + 0x28 + 4 i). The RM holds 4 records
// (+0x30, 0x13c each; the pointer array at +0x520 follows), so the call sees at most 4 racers (L[8] lowered for its duration),
// and every other racer gets a record of its own made by the record ctor 0x4333c0 (eax = car, ecx = record; it sets car+0x1c) in
// spare memory: the racer AI 0x44b1b0 reads car+0x1c without a null test, but the RM never ranks it (position byte +0xa stays 0).
static uint32_t rm_records(Ctx *c) {
    uint32_t keep[4] = {c->r[EBX], c->r[ESI], c->r[EDI], c->r[EBP]};
    uint32_t h = ld(c, 0x7361f8, 4), n = ld(c, h + 0x20, 4), pl = ld(c, h + 0x1c, 4);
    static uint32_t spare;
    nxrec = 0;
    uint32_t cap = 4;   // the RaceManager holds 4 records (0x434a80 fills 0x13c * 4 + the pointer array at +0x520)
    if (n > cap) st(c, h + 0x20, cap, 4);
    call_guest(c, 0x434a80, 0, NULL);
    if (n > cap) {
        st(c, h + 0x20, n, 4);
        if (!spare) spare = guest_alloc(0x13c * 8);
        for (uint32_t i = cap; i < n && i < 12; i++) {
            c->r[EAX] = ld(c, h + 0x28 + 4 * i, 4), c->r[ECX] = spare + 0x13c * (i - cap);
            call_guest(c, 0x4333c0, 0, NULL);
            xrec[nxrec++] = spare + 0x13c * (i - cap);
        }
        if (getenv("RN_FREELOG")) rn_log("FREE racemanager: %u racers (%u players), RM records %u, extra records for %u", n, pl, ld(c, ld(c, 0x73619c, 4) + 0x24, 4), n - cap);
    }
    c->r[EBX] = keep[0], c->r[ESI] = keep[1], c->r[EDI] = keep[2], c->r[EBP] = keep[3];
    return 0;
}

// PATCH 0x422a86 (same cave, ret 0x422a8b): the race start 0x422a70 calls 0x422580(n, buf) for the start positions (slots of 0x20:
// x, y, z, ... heading word at +0x10) of the grid slots 1..n and builds each entrant's car at the slot of its grid number. On the
// WORLD the positions are the track's markers, in two interleaved columns: the even slots are a line of cars 35 m apart on a road,
// the odd ones lie 1..10 m from each other (slots 1, 3, 5, 7, 9 are within 14 m), so the cars of the 5th racer on spawn inside each
// other and their physics blows up a minute later (NaN position, then the flare pow 0x5443f0 raises 0xc0000090). With more than
// 3 rivals (RN_FREERIV) the slots are compacted: slot 1 stays, then each slot at least GRID_GAP m from every slot kept, in order;
// the ones left over follow. Up to 3 rivals nothing moves (the slots the free mode always had).
#define GRID_GAP 8.0
static uint32_t grid_fix(Ctx *c) {
    rn_phase_grid(c);   // every race places its grid here (Restart too): host/phase.c begins a new race
    // The patched builder asks for 10 slots (push 10, loop to 10); outside a Free Run with more than 3 rivals the original 4 are asked,
    // so career and Quick Race get the same start places as before (the loop's slots 5..10 find no car with that grid index).
    uint32_t a[2] = {(live && nriv > 3) ? ARG(0) : 4, ARG(1)};
    call_guest_cdecl(c, 0x422580, 2, a);
    if (getenv("RN_FREELOG") && !(live && nriv > 3)) {
        char b[200]; int o = snprintf(b, sizeof b, "FREE start slots: original %u (live %d)", a[0], live);
        for (uint32_t k = 0; k < a[0] && k < 4; k++) o += snprintf(b + o, sizeof b - o, " %.1f,%.1f", ldf(c, a[1] + 0x20 * k), ldf(c, a[1] + 0x20 * k + 4));
        rn_log("%s", b);
    }
    if (!live || nriv <= 3 || a[0] > 12 || a[0] < 2) return 0;
    uint32_t n = a[0], buf = a[1], tmp[12 * 8], order[12];
    int kept = 0, rest = 0, ro[12];
    for (uint32_t k = 0; k < n; k++) {
        int ok = 1;
        for (int j = 0; j < kept && ok; j++)
            ok = hypot(ldf(c, buf + 0x20 * k) - ldf(c, buf + 0x20 * order[j]), ldf(c, buf + 0x20 * k + 4) - ldf(c, buf + 0x20 * order[j] + 4)) >= GRID_GAP;
        if (ok) order[kept++] = k; else ro[rest++] = k;
    }
    for (int j = 0; j < rest; j++) order[kept + j] = ro[j];
    for (uint32_t k = 0; k < n; k++) for (int w = 0; w < 8; w++) tmp[k * 8 + w] = ld(c, buf + 0x20 * order[k] + 4 * w, 4);
    for (uint32_t k = 0; k < n; k++) for (int w = 0; w < 8; w++) st(c, buf + 0x20 * k + 4 * w, tmp[k * 8 + w], 4);
    if (getenv("RN_FREELOG")) {
        char b[200]; int o = 0;
        for (uint32_t k = 0; k < n; k++) o += snprintf(b + o, sizeof b - o, " %u", order[k] + 1);
        rn_log("FREE start slots: %d of %u apart, order%s", kept, n, b);
    }
    return 0;
}

// TrafficTeleporter 0x598600 asks 0x5988c0 (call at 0x5987f6, thiscall ecx = the teleporter, arg = the car) whether a car
// needs a move: only when parked (+0x4d1 of its driver) or "passed" (0x598a50: route position [car+0x814] behind or ahead
// of the nearest player's, same section by vfunc 0x40, relative speed [car+0x3d4]) and not within 250 m of route of a player
// (0x59ac20 -> 0x59ad90, race state 4). Every rule is along the race route, which fits a race (cars stay near the route the
// player drives) but not free roam: a car that drove off into another street is never "passed" and drives on, 1..2.5 km
// away, for good (WORLD 1010, RN_FREELOG: 17 of 19 cars at 600..2450 m for the whole run, 3 moves in 75 s). PATCH 0x5987f6
// (cave 0x439a9a: jmp [SCREEN_ADDR+0x8c]): in free mode a car farther than the move's own route limit ([0x6b5a3c], 500 m)
// in a straight line also needs a move, so the cars stay in the band the teleporter keeps around the player; a car within
// KEEP_M ahead of the player never moves (it would vanish in sight). RN_FREE=0 or a race: the game's answer.
static uint32_t free_recycle(Ctx *c) {
    uint32_t car = ARG(0), r = call_guest(c, 0x5988c0, 1, &car) & 0xff, h = ld(c, 0x7361f8, 4);
    if (!live || r || !h) return r;
    for (uint32_t p = ld(c, h, 4), k = 0; p && p != h && k < 200; p = ld(c, p, 4), k++) {
        uint32_t e = ld(c, p + 0x14, 4);
        if (!e || ld(c, e + 4, 4) != 1) continue;
        float dx = ldf(c, car + 0x50) - ldf(c, p + 0x50), dy = ldf(c, car + 0x54) - ldf(c, p + 0x54), d = hypotf(dx, dy);
        if (d > ldf(c, 0x6b5a3c)) { r = 1, n_far++; break; }
        // In view: within KEEP_M ahead of the player (forward car+0x90..0x94, cone of +-70 deg), a move would make it vanish
        // on screen (OWNER 2026-10-31). The route rules above are not geometric in the city, so they fire on cars in sight.
        if (r && d < KEEP_M && dx * ldf(c, p + 0x90) + dy * ldf(c, p + 0x94) > 0.34f * d) r = 0, n_kept++;
        break;
    }
    return r;
}

// The HUD mask: 0x430730 (player update) asks 0x42e620(player) (stdcall, edx:eax) at 0x430dbd for the 64-bit mask of the
// widgets this race shows and, when it changed, pushes it to every widget with 0x42ed40 (a widget updates only when its
// ctor mask meets it). Free mode has no route direction and no opponent to time against, yet the race's mask keeps
// WRONG_WAY (lo 0x4000, widget 0x4a3ba0, from player+0x4ac by 0x430e00) and SPLIT_TIME / LIVE_SPLIT (lo 0x80 / 0x800000,
// the green gap at the top). PATCH 0x430dbd (cave 0x554495: jmp [SCREEN_ADDR+0x90]): in free mode those three bits are
// cleared; player+0x4ac stays (traffic 0x59a2c0 and the camera read it). RN_FREE=0 or a race: the game's mask.
// docs/openworld/re_hud_free.md.
static uint32_t free_hud(Ctx *c) {
    uint32_t pl = ARG(0);
    uint64_t m = call_guest64(c, 0x42e620, 1, &pl);
    static uint64_t was;
    if (m != was && getenv("RN_FREELOG")) rn_log("FREE hud mask %016llx live %d", (unsigned long long)m, live);
    was = m;
    if (live) m &= ~(uint64_t)(0x4000 | 0x80 | 0x800000);
    c->r[EDX] = (uint32_t)(m >> 32);
    return (uint32_t)m;
}

// The player's route in free mode (docs/re/camera_jump_route.md). The player driver class (vtable 0x6b8968) seeds its route each frame
// with slot +0x2c = 0x59bd90 (ecx = driver, 1 arg: a flag byte): keep [drv+0x2c] if 0x442690 still finds it near the TrackPath cursor
// car+0x814, else 0x4561d0 (ecx = car+0x60, eax = 0, cdecl &out, flags, car+0x814) with flags (0x24|0x64)|0x8c0, then without 0x8c0.
// Flag 0x20 ranks nodes by |node+0x38 - car+0x814|: in WORLD the cursor runs on the old tour polyline and node+0x38 is the new net's,
// so the seed lands 300..400 m away on another road and the route (jump cam eye, 0x42c4b0) is behind the car or far (OWNER 21:06 log:
// 13 of 14 refused). free_hseed: the game's call, then, if the seed is missing or more than SEED_M from the car, the same two
// 0x4561d0 calls without flag 0x20 (rank by XY distance). Free mode only; a race keeps the game's seed.
#define SEED_M 64.0f
static uint32_t seed_out;
static uint32_t free_hseed(Ctx *c) {
    uint32_t drv = c->r[ECX], flag = ARG(0), ret = call_guest(c, 0x59bd90, 1, &flag);
    if (!live) return ret;
    uint32_t node = ld(c, drv + 0x2c, 4), car = ld(c, drv + 4, 4);
    if (node && hypotf(ldf(c, node) - ldf(c, car + 0x60), ldf(c, node + 4) - ldf(c, car + 0x64)) <= SEED_M) return ret;
    if (!seed_out) seed_out = guest_alloc(16);
    uint32_t f = ((flag & 0xff) ? 0x24 : 0x64) & ~0x20u, ecx = c->r[ECX], eax = c->r[EAX];
    uint32_t a[3] = {seed_out, f | 0x8c0, ld(c, car + 0x814, 4)};
    c->r[ECX] = car + 0x60, c->r[EAX] = 0;
    uint32_t ok = call_guest_cdecl(c, 0x4561d0, 3, a) & 0xff;
    if (!ok) { a[1] = f; c->r[ECX] = car + 0x60, c->r[EAX] = 0; ok = call_guest_cdecl(c, 0x4561d0, 3, a) & 0xff; }
    c->r[ECX] = ecx, c->r[EAX] = eax;
    if (ok) st(c, drv + 0x2c, ld(c, seed_out + 4, 4), 4);
    return ret;
}
// Slot +0x40 = 0x59c7b0 gives the route direction from the TrackPath tangent car+0x818/0x81c (same polyline, so on WORLD roads that run
// against it the route walks behind the car). free_hdir: the seed node's own direction (node+0xc/+0x10) against the car's velocity
// (car+0x70/0x74, or its heading car+0x90/0x94 when car+0x3d4 * [0x6cc9f0] <= [0x6cca94], as 0x59c7b0 picks): 0 = along the nodes
// (free_dir's convention), 1 = against. No seed or a race: the game's answer.
static uint32_t free_hdir(Ctx *c) {
    uint32_t drv = c->r[ECX], node = ld(c, drv + 0x2c, 4), car = ld(c, drv + 4, 4);
    if (!live || !node) return call_guest(c, 0x59c7b0, 0, NULL);
    int fast = ldf(c, car + 0x3d4) * ldf(c, 0x6cc9f0) > ldf(c, 0x6cca94);
    uint32_t v = car + (fast ? 0x70 : 0x90);
    return ldf(c, v) * ldf(c, node + 0xc) + ldf(c, v + 4) * ldf(c, node + 0x10) > 0 ? 0 : 1;
}

// The jump and crash cameras (PATCH 0x426dd7, 0x4662e0, cave 0x5567e3: jmp [SCREEN_ADDR+0x94]) ask 0x42c4b0 (esi = camera ctrl) for the
// JUMPVIEW route: a clone of the driver's TrackPath nodes (ctrl+0x5c4: +4 count, +8 node pointers), the node nearest the car k (ctrl+0x5c8)
// and the first node 75 m or more past it (ctrl+0x5cc). The shot 0x42da40(6) -> 0x42c6d0(ctrl, 0xf, 1) then puts the eye, fixed for the
// whole shot, on one road edge of node e = [5cc] - 2 (e = [5cc] when [5cc] - k < 5, case 0x42ca9b) and looks at the car with no wall
// check. The game has a portal test for that (0x457300: the car -> eye segment must cross the cross-section [node+0x20, node+0x3c] of
// every node k..e-1), tries the other road edge when it fails and then uses that edge unchecked. In a city, 80 to 100 m along a road that
// bends, the view is buildings. docs/re/camera_jump.md.
// Free mode (live; a race or RN_FREE=0 is the exact original call): after the original call, walk e from the game's eye node back toward
// k and keep the first e whose eye (the edge the game would use, 0x42cd24..0x42cf6e) passes that portal test and is 30 m or more from the
// car; [5cc] is set so the game takes it. None: the clone is freed (0x42c640) and the answer is 0, so the chase camera stays.
#define JUMP_MIN_M 40.0f
static uint32_t jump_scr;   // 3 x 16 bytes of guest memory: the eye's left end, right end and the candidate the portal test reads

// A guest method that returns a float in st(0) (thiscall, one stack argument): read and pop the x87 result.
static float guest_float(Ctx *c, uint32_t fn, uint32_t self, uint32_t arg) {
    uint32_t ecx = c->r[ECX];
    c->r[ECX] = self;
    call_guest(c, fn, 1, &arg);
    c->r[ECX] = ecx;
    float v = (float)*fr(c, 0);
    fpop(c);
    return v;
}

// 0x5a7270 (esi = node): the world point at lateral offset lat from the node's route position, three floats to out.
static void node_point(Ctx *c, uint32_t node, float lat, uint32_t lane, uint32_t out) {
    uint32_t esi = c->r[ESI], a[4] = {out, ld(c, node + 0x58, 4), 0, lane};
    memcpy(&a[2], &lat, 4);
    c->r[ESI] = node;
    call_guest(c, 0x5a7270, 4, a);
    c->r[ESI] = esi;
}

// Does the game's own portal test 0x457300 (eax = first node, ecx = route; the car and eye points, last node) pass for the eye
// placed at the edge the game takes first (the one less far ahead along car+0x70..0x78, 0x42cdb1..0x42ce3c) or, when that fails,
// at the other edge (0x42cf12)? Returns the used edge's distance to the car in metres, or -1 when both fail.
static float eye_check(Ctx *c, uint32_t route, int k, int e, uint32_t car, uint32_t lane) {
    uint32_t node = ld(c, route + 8 + 4 * e, 4), vt = ld(c, node, 4), ends[2] = {jump_scr, jump_scr + 16}, eye = jump_scr + 32;
    float off = ldf(c, 0x6b7aac), dot[2];
    node_point(c, node, guest_float(c, ld(c, vt + 0xc, 4), node, lane) - off, lane, ends[0]);    // left end: vt[+0xc] - 2.0
    node_point(c, node, guest_float(c, ld(c, vt + 8, 4), node, lane) + off, lane, ends[1]);      // right end: vt[+8] + 2.0
    for (int s = 0; s < 2; s++) {
        dot[s] = 0;
        for (int a = 0; a < 3; a++) dot[s] += (ldf(c, ends[s] + 4 * a) - ldf(c, car + 0x60 + 4 * a)) * ldf(c, car + 0x70 + 4 * a);
    }
    int first = dot[0] <= dot[1] ? 0 : 1;
    for (int t = 0; t < 2; t++) {
        uint32_t end = ends[first ^ t], args[3] = {car + 0x60, eye, (uint32_t)(e - 1)}, eax = c->r[EAX], ecx = c->r[ECX], ok = 1;
        memcpy(c->mem + eye, c->mem + end, 12);
        if (k <= e - 1) {   // no node between the car and the eye: nothing to cross
            c->r[EAX] = (uint32_t)k, c->r[ECX] = route;
            ok = call_guest_cdecl(c, 0x457300, 3, args) & 0xff;
            c->r[EAX] = eax, c->r[ECX] = ecx;
        }
        if (ok) return hypotf(ldf(c, end) - ldf(c, car + 0x60), ldf(c, end + 4) - ldf(c, car + 0x64));
    }
    return -1;
}

static uint32_t free_jumpcam(Ctx *c) {
    uint32_t ret = call_guest(c, 0x42c4b0, 0, NULL), ctrl = c->r[ESI];
    if (!live || !(ret & 0xff)) return ret;
    if (!jump_scr) jump_scr = guest_alloc(64);   // +48: a node centre
    uint32_t route = ld(c, ctrl + 0x5c4, 4), car = ld(c, ctrl + 4, 4), drv = ld(c, car + 0x2c, 4), zero = 0;
    int k = (int)ld(c, ctrl + 0x5c8, 4), end = (int)ld(c, ctrl + 0x5cc, 4), e0 = end - k >= 5 ? end - 2 : end, e = e0;
    uint32_t ecx = c->r[ECX];
    c->r[ECX] = drv;                                                                     // the lane the game puts the eye on: 0x42cae9, driver vt[+0x1c](0), at least 0
    int lane = (int)call_guest(c, ld(c, ld(c, drv, 4) + 0x1c, 4), 1, &zero);
    c->r[ECX] = ecx;
    // The portal starts at the first node ahead of the car, f: the route cursor k lags up to ~55 m behind a fast car (updated every
    // 60 frames, 0x426b63), and a car past node k never crosses its section, so the test failed on both edges at speed
    // (OWNER 19:00 log: 8 of 9 refused). The eye is searched upward from f + 1 (docs/re/camera_crash.md).
    int n = (int)ld(c, route + 4, 4), f = k;
    if (k >= 0 && k < n) {   // a route far from the car (seed on another road) gives a far eye: keep the chase camera
        uint32_t nd = ld(c, route + 8 + 4 * k, 4), ctr = jump_scr + 48;
        node_point(c, nd, 0.5f * (ldf(c, nd + 0x20) + ldf(c, nd + 0x3c)), 0, ctr);
        float dk = hypotf(ldf(c, ctr) - ldf(c, car + 0x60), ldf(c, ctr + 4) - ldf(c, car + 0x64));
        if (dk > SEED_M) {
            rn_log("JCPICK f%u k %d n %d route far %.0f m refused", rn_telem.presents, k, n, dk);
            call_guest(c, 0x42c640, 0, NULL);
            return 0;
        }
    }
    for (; f < n; f++) {
        uint32_t nd = ld(c, route + 8 + 4 * f, 4), ctr = jump_scr + 48;
        node_point(c, nd, 0.5f * (ldf(c, nd + 0x20) + ldf(c, nd + 0x3c)), 0, ctr);
        float dp = 0;
        for (int a = 0; a < 3; a++) dp += (ldf(c, ctr + 4 * a) - ldf(c, car + 0x60 + 4 * a)) * ldf(c, car + 0x70 + 4 * a);
        if (dp > 0) break;
    }
    float dist = 0, best = 0;
    for (e = f + 1; e < n; e++) {
        if ((dist = eye_check(c, route, f, e, car, lane > 0 ? (uint32_t)lane : 0)) >= JUMP_MIN_M) break;
        if (dist > best) best = dist;
    }
    if (e >= n) e = k, dist = best;   // none
    if (e > k && e != e0) st(c, ctrl + 0x5cc, e - k <= 4 ? (uint32_t)e : (uint32_t)e + 2, 4);   // [5cc] - k < 5 gives e; otherwise [5cc] = e + 2 gives e (0x42ca9b)
    rn_log("JCPICK f%u k %d f %d n %d end %d eye %d of orig %d dist %.0f m %s 4ac %u", rn_telem.presents, k, f, n, (int)ld(c, ctrl + 0x5cc, 4),
           e > k ? e : -1, e0, dist, e > k ? "clear" : "refused", ld(c, ctrl + 0x4ac, 1));
    if (e > k) return ret;
    call_guest(c, 0x42c640, 0, NULL);                                                    // frees the clone, [5c4] = 0, [5c8] = [5cc] = -1 (reads esi only)
    return 0;
}

uint32_t mode_menu(Ctx *c), mode_switch(Ctx *c);
uint32_t coll_widx(Ctx *c);   // host/trackfiles.c: the collision index loader (PATCH 0x441423)
const Api free_apis[] = {{"rn", "free_setup", 0, free_setup}, {"rn", "free_traffic", 7, free_traffic},
                         {"rn", "mode_menu", 0, mode_menu}, {"rn", "mode_switch", 0, mode_switch}, {"rn", "coll_widx", -1, coll_widx},
                         {"rn", "free_place", 1, free_place}, {"rn", "free_spacing", 1, free_spacing},
                         {"rn", "free_nopath", 0, free_nopath},
                         {"rn", "free_tnode", 0, free_tnode}, {"rn", "free_recycle", 1, free_recycle},
                         {"rn", "free_hud", 1, free_hud}, {"rn", "free_dir", 0, free_dir},
                         {"rn", "free_jumpcam", 0, free_jumpcam}, {"rn", "free_hseed", 1, free_hseed},
                         {"rn", "free_hdir", 0, free_hdir}};
const int free_api_count = sizeof free_apis / sizeof *free_apis;
