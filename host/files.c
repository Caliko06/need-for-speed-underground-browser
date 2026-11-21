// Read-only access to the game folder (C:\NFSU = game/) and the save folder (what the game keeps under
// CSIDL_COMMON_APPDATA\NFS Underground = save/ of this repo). Names match without case, like NTFS.
// Native: the folder on disk. Web: the reading thread fetches byte ranges with synchronous XHR (allowed in its worker).
// Over the internet a request costs a round trip (live 2026-11-16: 516 requests in a row at 75 ms = most of the 65 s into
// WORLD), so a file up to WHOLE_MAX comes whole in one request, the pieces are kept for every thread (blks), and helper
// threads bring ahead what the entry is known to open (gf_prefetch: web/entry_hint.tsv and the pool's cars).
#include <ctype.h>
#include <sched.h>
#include <stdlib.h>
#include <strings.h>
#include <unistd.h>
#include <sys/stat.h>
#include "host.h"

#define MAXF 256
#define AHEAD (256u << 10)
#define AHEAD_MAX (4u << 20)
// Save files live whole in memory (data): changed there, written back whole by gf_flush and gf_close.
typedef struct {
    int used, save, dirty;
    uint64_t size, cap;
    char real[512];
    FILE *f;
    uint8_t *data;
    uint64_t next;                        // where the last request ended
    uint32_t ahead;
} GFile;
static GFile files[MAXF];
static char root[1024], save_root[1024];

#ifdef __EMSCRIPTEN__
static void files_prefetch_start(void);
#endif
void files_set_root(const char *dir) {
    snprintf(root, sizeof root, "%s", dir);
#ifdef __EMSCRIPTEN__
    (void)dir;
    snprintf(save_root, sizeof save_root, "/save");               // web/saves.js mounts it in memory and keeps it in the browser (IndexedDB)
    files_prefetch_start();
#else
    snprintf(save_root, sizeof save_root, "%s/../save", dir);
    mkdir(save_root, 0755);
#endif
}
// Native: every path is on disk. Web: only the save folder is (an in-memory FS saved in IndexedDB); game files are read over HTTP.
static int on_fs(const char *real) {
#ifdef __EMSCRIPTEN__
    return !strncmp(real, save_root, strlen(save_root));
#else
    (void)real;
    return 1;
#endif
}
#define SAVE_DIR "C:/Documents and Settings/All Users/Application Data/NFS Underground"

// C:\NFSU\a\b or a\b or .\a\b -> "a/b": 0 in the game folder, 1 in the save folder, -1 outside both.
// D:\ is the CD-ROM drive with the game disc in it; the OWNER's folder holds the disc files too.
static int game_rel(const char *gpath, char *rel, size_t n) {
    char p[512];
    snprintf(p, sizeof p, "%s", gpath);
    for (char *q = p; *q; q++) if (*q == '\\') *q = '/';
    const char *r = p;
    int save = 0, k = (int)strlen(SAVE_DIR);
    if (!strncasecmp(p, SAVE_DIR, k) && (p[k] == '/' || !p[k])) r = p + k + (p[k] == '/'), save = 1;
    else if (!strncasecmp(p, "C:/NFSU", 7) && (p[7] == '/' || !p[7])) r = p + 7 + (p[7] == '/');
    else if ((p[0] == 'D' || p[0] == 'd') && p[1] == ':' && (p[2] == '/' || !p[2])) r = p + 2 + (p[2] == '/');
    else if (p[0] && p[1] == ':') return -1;
    while (r[0] == '.' && r[1] == '/') r += 2;
    char *o = rel;
    for (; *r && (size_t)(o - rel) < n - 1; r++)
        if (!(*r == '/' && (o == rel || o[-1] == '/'))) *o++ = *r;     // drop empty components
    *o = 0;
    return save;
}

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
// Index of game/ from /game-files.json: lower-case path -> [real path, size]; directories too.
EM_JS(double, web_lookup, (const char *rel, char *real, int realsz), {
    if (!Module.rnIndex) {
        var x = new XMLHttpRequest();
        x.open('GET', '/game-files.json', false);
        x.send();
        var files = new Map(), dirs = new Set();
        for (const [p, n] of JSON.parse(x.responseText)) {
            var low = p.toLowerCase();
            files.set(low, [p, n]);
            var parts = low.split('/');
            for (var k = 1; k < parts.length; k++) dirs.add(parts.slice(0, k).join('/'));
        }
        Module.rnIndex = { files: files, dirs: dirs };
    }
    var key = UTF8ToString(rel).toLowerCase();
    var e = Module.rnIndex.files.get(key);
    if (!e) return Module.rnIndex.dirs.has(key) || key === '' ? -2 : -1;
    stringToUTF8(e[0], real, realsz);
    return e[1];
});
// Names in a directory, "name\tsize\n" (size -1 = a directory), into out; the count, or -1 no directory.
EM_JS(int, web_list, (const char *rel, char *out, int outsz), {
    var dir = UTF8ToString(rel).toLowerCase(), seen = new Map();
    var add = (p, n) => {
        var low = p.toLowerCase();
        if (dir && !low.startsWith(dir + '/')) return;
        var rest = p.slice(dir ? dir.length + 1 : 0), k = rest.indexOf('/');
        if (k < 0) seen.set(rest, n); else if (!seen.has(rest.slice(0, k))) seen.set(rest.slice(0, k), -1);
    };
    for (const [low, e] of Module.rnIndex.files) add(e[0], e[1]);
    var s = '';
    for (const [name, n] of seen) s += name + '\t' + n + '\n';
    stringToUTF8(s, out, outsz);
    return seen.size;
});
// real is "game/<path>".
EM_JS(int, web_read, (const char *real, double off, uint8_t *dst, int n), {
    // The game has no answer to a failed disc read (it waits on its loading screen), and a play over the internet makes
    // hundreds of these requests: a dropped one (a phone changing cell, a 5xx at the edge) is asked again after 0.3, 1, 2, 4 s.
    var path = UTF8ToString(real), x, waits = [300, 1000, 2000, 4000];
    // Exact read pieces, independently HTTP-gzipped by tools/data_chunks.py. Unlisted reads keep Range.
    // Each worker has its own Module; even prefetch workers load the small index once.
    if (!Module.rnDataChunks) {
        var index = new XMLHttpRequest();
        index.open('GET', '/data-chunks.json', false);
        index.send();
        Module.rnDataChunks = index.status === 200 ? JSON.parse(index.responseText) : {};
    }
    var chunk = Module.rnDataChunks[path + ':' + off + ':' + n];
    for (var t = 0; ; t++) {
        try {
            x = new XMLHttpRequest();
            x.open('GET', chunk ? '/data-chunks/' + chunk : '/' + path.split('/').map(encodeURIComponent).join('/'), false);
            x.responseType = 'arraybuffer';
            if (!chunk) x.setRequestHeader('Range', 'bytes=' + off + '-' + (off + n - 1));
            x.send();
            if (x.status === (chunk ? 200 : 206) && x.response.byteLength === n) break;
            err('files: ' + path + ' at ' + off + ': HTTP ' + x.status + ', try ' + (t + 1));
        } catch (e) { err('files: ' + path + ' at ' + off + ': ' + e.message + ', try ' + (t + 1)); }
        if (t === waits.length) return -1;
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, waits[t]);
    }
    var a = new Uint8Array(x.response);
    HEAPU8.set(a, dst);
    return a.length;
});
// A small text file of the site into out; its length, or -1.
EM_JS(int, web_text, (const char *url, char *out, int cap), {
    try {
        var x = new XMLHttpRequest();
        x.open('GET', UTF8ToString(url), false);
        x.send();
        if (x.status !== 200) { err('files: ' + UTF8ToString(url) + ': HTTP ' + x.status); return -1; }
        return stringToUTF8(x.responseText, out, cap);
    } catch (e) { err('files: ' + UTF8ToString(url) + ': ' + e.message); return -1; }
});
#endif

// 0 = found (size set), 1 = a directory, -1 = missing, -2 = outside the game and save folders.
static int lookup(const char *gpath, char *real, size_t n, uint64_t *size) {
    char rel[512];
    int save = game_rel(gpath, rel, sizeof rel);
    if (save < 0) return -2;
#ifdef __EMSCRIPTEN__
    if (!save) {
    char g[512];
    double r = web_lookup(rel, g, sizeof g);
    if (r == -2) return 1;
    if (r < 0) return -1;
    snprintf(real, n, "game/%s", g);
    *size = (uint64_t)r;
    return 0;
    }
#endif
    {
    // Each component, matched without case against the directory on disk.
    snprintf(real, n, "%s", save ? save_root : root);
    for (char *c = rel; *c;) {
        char *e = strchr(c, '/');
        if (e) *e = 0;
        size_t len = strlen(real);
        snprintf(real + len, n - len, "/%s", c);
        struct stat sb;
        if (stat(real, &sb)) {
            real[len] = 0;
            DIR *d = opendir(real);
            int found = 0;
            struct dirent *de;
            while (d && (de = readdir(d)))
                if (!strcasecmp(de->d_name, c)) { snprintf(real + len, n - len, "/%s", de->d_name); found = 1; break; }
            if (d) closedir(d);
            if (!found) return -1;
        }
        if (!e) break;
        c = e + 1;
    }
    struct stat sb;
    if (stat(real, &sb)) return -1;
    if (S_ISDIR(sb.st_mode)) return 1;
    *size = (uint64_t)sb.st_size;
    return 0;
    }
}

// 0 = a file, 1 = a directory, -1 = missing, -2 = outside the game folder.
int gf_stat(const char *gpath) {
    char real[512];
    uint64_t size;
    return lookup(gpath, real, sizeof real, &size);
}

void rn_race_bridge(const char *gpath);   // host/bridge.c
int rn_overlay_open(const char *gpath, char *real, size_t n, uint64_t *size) __attribute__((weak));   // host/trackfiles.c: the Cars/TEXTURES.BIN overlay
extern Ctx *g_ctx;

// Every open asks where the race is going: the mode setup writes the track to [0x78a2f0] when the player confirms (0x4b4a90 and the
// other modes' setups, 0x43b181, 0x4abc5c), so the first open after it (GLOBAL\INGAMEA.BUN) is ahead of TRACKB. Once per track change.
static void track_hook(void) {
#ifdef __EMSCRIPTEN__
    if (!g_ctx) return;
    int id = (int)ld(g_ctx, 0x78a2f0, 4);
    if (id >= 1000 && id < 2000) { cars_hook(g_ctx); gf_prefetch_track(id); }   // cars first: the load reads them first; the track is a no-op when the highlight poll queued it
#endif
}

// Opens a game file: id >= 0, or -1 missing, -2 outside the folder, -3 a directory.
int gf_open(const char *gpath) {
    char real[512];
    uint64_t size = 0;
    rn_race_bridge(gpath);
    track_hook();
    int r = rn_overlay_open && rn_overlay_open(gpath, real, sizeof real, &size) ? 0 : lookup(gpath, real, sizeof real, &size);
    if (r) return r == 1 ? -3 : r;
    for (int k = 0; k < MAXF; k++) {
        GFile *g = &files[k];
        if (g->used) continue;
        memset(g, 0, sizeof *g);
        if (on_fs(real)) {
            g->f = fopen(real, "rb");
            if (!g->f) return -1;
        }
        g->used = 1;
        g->size = size;
        snprintf(g->real, sizeof g->real, "%s", real);
        return k;
    }
    return -1;
}
uint64_t gf_size(int id) { return files[id].size; }
void gf_close(int id) {
    gf_flush(id);
    if (files[id].f) fclose(files[id].f);
    free(files[id].data);
    files[id].used = 0;
}
#ifdef __EMSCRIPTEN__
#include <pthread.h>
// ---- web: the fetched pieces of the game files, shared by every reading thread ------------------
#define WHOLE_MAX (8u << 20)   // live capture 2026-11-16: 382 of 516 requests were pieces of files this small (car GEOMETRY 5.5 MB in 13 steps)
#define NBLK 1024
typedef struct { char real[256]; uint64_t off; uint32_t len, tick; uint8_t *data; int state; } Blk;   // state: 0 free, 1 on its way, 2 ready
static Blk blks[NBLK];
static pthread_mutex_t blk_mu = PTHREAD_MUTEX_INITIALIZER;   // blks, the prefetch queue; copies out of a piece run under it, so a piece is never freed mid-copy
static uint64_t blk_bytes, blk_cap;
static uint32_t blk_tick;
static uint32_t rn_load[2];    // KB the prefetch was asked for, KB it has brought: the page's loading bar (web/boot.js)
uint32_t *rn_load_addr(void) { return rn_load; }

// Under blk_mu: the piece, ready or on its way, that holds byte `at` of the file.
static Blk *blk_at(const char *real, uint64_t at) {
    for (Blk *b = blks; b < blks + NBLK; b++)
        if (b->state && at >= b->off && at - b->off < b->len && !strcmp(b->real, real)) return b;
    return 0;
}
// The cache of pieces: 256 MB (the wasm break stood at 1555 of 2048 MB at the WORLD HUD with it full, log 2026-11-16); RN_RANGEMB=16 on phones and tablets (web/boot.js).
static uint64_t cap(void) {
    if (!blk_cap) { const char *e = getenv("RN_RANGEMB"); blk_cap = (uint64_t)(e && atoi(e) > 0 ? atoi(e) : 256) << 20; }
    return blk_cap;
}
// A whole file is at most an eighth of the cache, so a phone's 16 MB keeps the old 256 KB steps for anything over 2 MB.
static uint64_t whole_max(void) { return cap() / 8 < WHOLE_MAX ? cap() / 8 : WHOLE_MAX; }
// Under blk_mu: a slot marked "on its way". The least recently used ready pieces go first when the cap or the table is full.
static Blk *blk_new(const char *real, uint64_t off, uint32_t len) {
    if (strlen(real) >= sizeof blks->real) return 0;
    for (;;) {
        Blk *spare = 0, *old = 0;
        for (Blk *b = blks; b < blks + NBLK; b++) {
            if (!b->state) spare = b;
            else if (b->state == 2 && (!old || b->tick < old->tick)) old = b;
        }
        if (spare && (blk_bytes + len <= cap() || !old)) {
            snprintf(spare->real, sizeof spare->real, "%s", real);
            spare->off = off; spare->len = len; spare->data = 0; spare->state = 1;
            blk_bytes += len;
            return spare;
        }
        if (!old) return 0;
        free(old->data);
        blk_bytes -= old->len;
        old->state = 0;
    }
}
// One request to the server, on the calling thread, outside blk_mu. 0 when the piece is ready.
static int blk_fetch(Blk *b) {
    uint8_t *p = malloc(b->len);
    int r = p ? web_read(b->real, (double)b->off, p, (int)b->len) : -1;
    pthread_mutex_lock(&blk_mu);
    if (r == (int)b->len) { b->data = p; b->tick = ++blk_tick; b->state = 2; }
    else { free(p); blk_bytes -= b->len; b->state = 0; }
    pthread_mutex_unlock(&blk_mu);
    return r == (int)b->len ? 0 : -1;
}

// ---- web: bringing files ahead of the game, NPRE requests at a time ------------------------------
static int npre(void) {     // RN_NPRE (1..4, default 4): prefetch workers; phones ask for 2 (web/boot.js)
    const char *e = getenv("RN_NPRE");
    int n = e && *e ? atoi(e) : 4;
    return n < 1 ? 1 : n > 4 ? 4 : n;
}
#define NPRE npre()
#define NQ 1024
static struct { char real[256]; uint64_t off; uint32_t len; int trk; } preq[NQ];   // trk: queued by gf_prefetch_track (droppable)
static int queued_id;                 // the track whose lines were queued last (under blk_mu)
static unsigned pre_head, pre_tail;   // under blk_mu
static int pre_run, pre_on;           // threads alive (under blk_mu); set by RN_PREFETCH

static void *pre_main(void *hint);
static void pre_spawn(void *hint) {     // under blk_mu, or before any thread
    pthread_t t; pthread_attr_t a;
    pthread_attr_init(&a); pthread_attr_setdetachstate(&a, PTHREAD_CREATE_DETACHED);
    if (!pthread_create(&t, &a, pre_main, hint)) pre_run++;
}
static void pre_start(void) { for (int k = pre_run; k < NPRE; k++) pre_spawn(0); }
static char hint_text[256 << 10];     // /entry_hint.tsv (23 KB with 8 tracks, 2026-11-18), kept for gf_prefetch_track
static int hint_n;                    // its bytes; set under blk_mu once read
// Under blk_mu: queue a hint line, 1 when it was queued.
static int pre_push(const char *real, double off, double len, int trk) {
    if (pre_tail - pre_head >= NQ) return 0;
    snprintf(preq[pre_tail % NQ].real, 256, "%s", real);
    preq[pre_tail % NQ].off = (uint64_t)off; preq[pre_tail % NQ].len = (uint32_t)len; preq[pre_tail % NQ].trk = trk;
    pre_tail++;
    rn_load[0] += (uint32_t)len >> 10;
    return 1;
}
static void *pre_main(void *hint) {
    if (hint) {     // "phase \t path \t offset \t length" lines (tools/entry_hint.py): b = up to the main menu, t<id> = a track's race load
        int n = web_text("/entry_hint.tsv", hint_text, sizeof hint_text - 1);
        pthread_mutex_lock(&blk_mu);
        hint_n = n > 0 ? n : 0;
        hint_text[hint_n] = 0;
        for (char *l = hint_n ? hint_text : 0; l && *l; ) {
            char ph[16], real[256]; double off, len;
            if (sscanf(l, "%15[^\t]\t%255[^\t]\t%lf\t%lf", ph, real, &off, &len) == 4 && !strcmp(ph, "b")) pre_push(real, off, len, 0);
            l = strchr(l, '\n'); if (l) l++;
        }
        // One line per visit: with no hint the boot reads every file on demand (65.7 s instead of 22.7 s, HANDOFF 2026-11-16).
        if (pre_tail) rn_log("files: prefetch boot: %u requests, %u KB", pre_tail, rn_load[0]);
        else rn_log("files: prefetch OFF: /entry_hint.tsv gave no lines (%d bytes)", n);
        pre_start();
        pthread_mutex_unlock(&blk_mu);
    }
    for (;;) {
        pthread_mutex_lock(&blk_mu);
        if (pre_head == pre_tail && !hint) { pre_run--; pthread_mutex_unlock(&blk_mu); return 0; }   // the hint's thread stays for what comes later
        Blk *b = 0;
        uint32_t len = 0;
        if (pre_head != pre_tail) {
            unsigned k = pre_head++ % NQ;
            len = preq[k].len;
            if (!len) b = 0;
            else if (blk_at(preq[k].real, preq[k].off)) rn_load[1] += len >> 10;      // the game got there first
            else b = blk_new(preq[k].real, preq[k].off, len);
        }
        pthread_mutex_unlock(&blk_mu);
        if (b) { blk_fetch(b); __atomic_add_fetch(&rn_load[1], len >> 10, __ATOMIC_RELAXED); }
        else if (!len) usleep(20000);
    }
}
// RN_PREFETCH=boot (web/boot.js, the launcher's entry): the hint's files start coming while the engine boots.
static void files_prefetch_start(void) {
    const char *e = getenv("RN_PREFETCH");
    if (!e || !*e) return;
    pre_on = 1;
    pre_spawn((void *)e);
}
#endif
// A game file the host knows the game is about to open (host/rivals.c: the pool's cars): whole when small, else its head.
void gf_prefetch(const char *gpath) {
#ifdef __EMSCRIPTEN__
    char real[512];
    uint64_t size = 0;
    if (!pre_on || lookup(gpath, real, sizeof real, &size) || !size || strlen(real) > 255) return;
    pthread_mutex_lock(&blk_mu);
    if (!blk_at(real, 0) && pre_tail - pre_head < NQ) {
        unsigned k = pre_tail++ % NQ;
        snprintf(preq[k].real, 256, "%s", real);
        preq[k].trk = 0; preq[k].off = 0; preq[k].len = size <= whole_max() ? (uint32_t)size : AHEAD;
        rn_load[0] += preq[k].len >> 10;
        pre_start();
    }
    pthread_mutex_unlock(&blk_mu);
#else
    (void)gpath;
#endif
}

#ifdef __EMSCRIPTEN__
// Under blk_mu: forget the track requests no thread has started yet (the previous highlight's); blocks in flight or cached stay.
static void track_drop(void) {
    for (unsigned k = pre_head; k != pre_tail; k++)
        if (preq[k % NQ].trk && preq[k % NQ].len) { rn_load[0] -= preq[k % NQ].len >> 10; preq[k % NQ].len = 0; }
    queued_id = 0;
}
#endif

// The track the race will load is known ([0x78a2f0], written by the mode setup when the player confirms): its hint lines
// "t<id> \t path \t offset \t length" come now, once per call, while they fit in the cache.
void gf_prefetch_track(int id) {
#ifdef __EMSCRIPTEN__
    if (!pre_on) return;
    char tag[16];
    snprintf(tag, sizeof tag, "t%d", id);
    unsigned q = 0;
    uint64_t kb = 0, room = 0;
    pthread_mutex_lock(&blk_mu);
    if (id == queued_id) { pthread_mutex_unlock(&blk_mu); return; }   // the highlight poll and the Accept hook both land here
    track_drop();
    queued_id = id;
    room = cap() > blk_bytes ? cap() - blk_bytes : 0;
    for (char *l = hint_n ? hint_text : 0; l && *l; ) {
        char ph[16], real[256]; double off, len;
        if (sscanf(l, "%15[^\t]\t%255[^\t]\t%lf\t%lf", ph, real, &off, &len) == 4 && !strcmp(ph, tag) && !blk_at(real, (uint64_t)off)) {
            if ((kb + ((uint64_t)len >> 10)) << 10 > room || !pre_push(real, off, len, 1)) break;
            kb += (uint64_t)len >> 10; q++;
        }
        l = strchr(l, '\n'); if (l) l++;
    }
    if (q) pre_start();
    pthread_mutex_unlock(&blk_mu);
    rn_log("files: prefetch track %d: %u requests, %u KB", id, q, (unsigned)kb);
#else
    (void)id;
#endif
}

// Every Present: the track highlighted in the Quick Race track menu. The menu stores the highlighted track's id in the mode's staging
// record, rec+8 (0x4bafe0 at 0x4bb0b3 on each move; the ctor 0x4b9d47 for the first), rec = 0x748f70 + {0xfa10,...}[[0x777cc8]] (0x4ab510).
// It is prefetched once it has stayed 500 ms; a move drops the previous one's unstarted requests. Only in the front end (flow 3).
void gf_track_poll(void) {
#ifdef __EMSCRIPTEN__
    static const uint16_t rec[7] = {0xfa10, 0xfa30, 0xfa50, 0xfa70, 0xfa94, 0xfb18, 0xfb44};
    static int cand; static double since;
    if (!pre_on || !g_ctx || ld(g_ctx, 0x77a920, 4) != 3) return;
    uint32_t mode = ld(g_ctx, 0x777cc8, 4);
    if (mode > 6) return;
    int id = (int)ld(g_ctx, 0x748f70 + rec[mode] + 8, 4);
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    double now = ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
    if (id != cand) {
        cand = id; since = now;
        pthread_mutex_lock(&blk_mu);
        if (id != queued_id) track_drop();
        pthread_mutex_unlock(&blk_mu);
    } else if (id >= 1000 && id < 2000 && now - since >= 500) gf_prefetch_track(id);
#endif
}

// Reads up to n bytes at off; returns the count (short at the end of the file), -1 on an I/O error.
int64_t gf_read(int id, uint64_t off, uint8_t *dst, uint32_t n) {
    GFile *g = &files[id];
    if (off >= g->size) return 0;
    if (n > g->size - off) n = (uint32_t)(g->size - off);
    if (g->save) { memcpy(dst, g->data + off, n); return n; }
#ifdef __EMSCRIPTEN__
    if (!g->f) {
    uint32_t done = 0;
    while (done < n) {
        uint64_t at = off + done;
        pthread_mutex_lock(&blk_mu);
        Blk *b = blk_at(g->real, at);
        if (b && b->state == 2) {
            uint32_t k = (uint32_t)(b->off + b->len - at);
            if (k > n - done) k = n - done;
            memcpy(dst + done, b->data + (at - b->off), k);
            b->tick = ++blk_tick;
            pthread_mutex_unlock(&blk_mu);
            done += k;
            continue;
        }
        if (b) {        // another thread is bringing it: the callers hold the GIL, the other guest threads go on meanwhile
            pthread_mutex_unlock(&blk_mu);
            gil_release(); usleep(1000); gil_acquire();
            continue;
        }
        // A small file comes whole. A big one (a track stream, VINYLS, the music) in the steps the game asks for, at least
        // 256 KB; while its reads run on in sequence the step doubles, up to AHEAD_MAX.
        uint64_t from = 0;
        uint32_t len = (uint32_t)g->size;
        if (g->size > whole_max()) {
            uint32_t want = n - done;
            g->ahead = g->ahead && at == g->next ? (g->ahead < AHEAD_MAX ? 2 * g->ahead : AHEAD_MAX) : AHEAD;
            from = at;
            len = want > g->ahead ? want : g->ahead;
            if (len > g->size - at) len = (uint32_t)(g->size - at);
            g->next = at + len;
        }
        b = blk_new(g->real, from, len);
        pthread_mutex_unlock(&blk_mu);
        if (!b) return -1;
        // ReadFile blocks only the calling thread on Windows, so the request runs without the GIL and the other guest
        // threads go on (the main loop drew nothing while the file thread 0x63e4d0 waited: telemetry 2026-10-24).
        gil_release();
        uint64_t t0 = now_us();
        int r = blk_fetch(b);
        uint64_t t1 = now_us();
        gil_acquire();
        rn_telem.read_ms += (double)(t1 - t0) / 1000;
        rn_telem.reads++;
        rn_telem.read_kb += len >> 10;
        // A request this slow waited for a connection or the server (a movie or a track stream read as it plays).
        if (t1 - t0 > 100000) rn_log("files: slow read %s at %llu, %u bytes, %.0f ms", g->real, (unsigned long long)from, len, (t1 - t0) / 1000.0);
        if (r) return -1;
    }
    return done;
    }
#endif
    if (fseeko(g->f, (off_t)off, SEEK_SET)) return -1;
    return (int64_t)fread(dst, 1, n, g->f);
}

// ---- writes: only inside the save folder; the game folder is read-only ------------------------

static int save_rel(const char *gpath, char *rel, size_t n) { return game_rel(gpath, rel, n); }

static int put_whole(const char *rel, const char *real, const uint8_t *p, uint64_t n) {
    (void)rel;
    FILE *f = fopen(real, "wb");
    if (!f) return -1;
    size_t w = n ? fwrite(p, 1, n, f) : 0;
    return fclose(f) || w != n ? -1 : 0;
}

// The real path (native) of a save path that may not exist yet: its parent must be a directory.
static int save_target(const char *gpath, char *rel, char *real, size_t n) {
    if (save_rel(gpath, rel, 512) != 1) return -2;
    char parent[600];
    snprintf(parent, sizeof parent, "%s", gpath);
    char *s = strrchr(parent, '\\');
    if (!s) s = strrchr(parent, '/');
    if (!s) return -2;
    *s = 0;
    char preal[512];
    uint64_t sz;
    if (lookup(parent, preal, sizeof preal, &sz) != 1) return -3;
    snprintf(real, n, "%s/%s", preal, s + 1);
    return 0;
}

int gf_create(const char *gpath, int disp, int *existed) {
    char rel[512], real[512];
    uint64_t size = 0;
    int r = lookup(gpath, real, sizeof real, &size), save = save_rel(gpath, rel, sizeof rel);
    if (r == -2 || save != 1) return r == -2 ? -2 : -5;     // outside, or the read-only game folder
    if (r == 1) return -3;
    *existed = r == 0;
    if (r == 0 && disp == 1) return -4;                       // CREATE_NEW
    if (r != 0 && (disp == 3 || disp == 5)) return -1;        // OPEN_EXISTING, TRUNCATE_EXISTING
    if (r != 0) {
        int t = save_target(gpath, rel, real, sizeof real);
        if (t) return t == -3 ? -6 : t;                       // -6: the folder does not exist
    }
    int k = 0;
    while (k < MAXF && files[k].used) k++;
    if (k == MAXF) return -1;
    GFile *g = &files[k];
    memset(g, 0, sizeof *g);
    g->used = g->save = 1;
    snprintf(g->real, sizeof g->real, "%s", real);
    g->cap = size > 4096 ? size : 4096;
    g->data = calloc(1, g->cap);
    if (r == 0 && disp != 2 && disp != 5) {                   // keep the contents
        FILE *f = fopen(real, "rb");
        if (!f || fread(g->data, 1, size, f) != size) { if (f) fclose(f); free(g->data); g->used = 0; return -1; }
        fclose(f);
        g->size = size;
    } else g->dirty = 1;                                      // created or truncated: exists from now on
    if (g->dirty) gf_flush(k);
    return k;
}

int gf_is_save(int id) { return files[id].save; }

int64_t gf_write(int id, uint64_t off, const uint8_t *src, uint32_t n) {
    GFile *g = &files[id];
    if (!g->save) return -1;
    if (off + n > g->cap) {
        uint64_t cap = g->cap;
        while (off + n > cap) cap *= 2;
        g->data = realloc(g->data, cap);
        memset(g->data + g->cap, 0, cap - g->cap);
        g->cap = cap;
    }
    memcpy(g->data + off, src, n);
    if (off + n > g->size) g->size = off + n;
    g->dirty = 1;
    return n;
}

int gf_truncate(int id, uint64_t size) {
    GFile *g = &files[id];
    if (!g->save) return -1;
    if (size > g->size) { uint8_t z = 0; if (gf_write(id, size - 1, &z, 1) < 0) return -1; }
    g->size = size;
    g->dirty = 1;
    return 0;
}

int gf_flush(int id) {
    GFile *g = &files[id];
    if (!g->save || !g->dirty) return 0;
    char rel[512];
    rel[0] = 0;
    if (put_whole(rel, g->real, g->data, g->size)) return -1;
    g->dirty = 0;
    return 0;
}

// 0 made, 1 already there, -1 the parent is missing, -2 outside the save folder.
int gf_mkdir(const char *gpath) {
    char rel[512], real[512];
    int r = gf_stat(gpath);
    if (r == 1) return 1;
    if (r == 0) return 1;
    int t = save_target(gpath, rel, real, sizeof real);
    if (t) return t == -3 ? -1 : -2;
    return mkdir(real, 0755) ? -1 : 0;
}

// 0 deleted, -1 missing, -2 outside the save folder.
int gf_delete(const char *gpath) {
    char rel[512], real[512];
    uint64_t size;
    if (save_rel(gpath, rel, sizeof rel) != 1) return -2;
    if (lookup(gpath, real, sizeof real, &size) != 0) return -1;
    return unlink(real) ? -1 : 0;
}

static int wild(const char *p, const char *s) {
    for (; *p; p++, s++) {
        if (*p == '*') { for (; ; s++) { if (wild(p + 1, s)) return 1; if (!*s) return 0; } }
        if (!*s || (*p != '?' && tolower((unsigned char)*p) != tolower((unsigned char)*s))) return 0;
    }
    return !*s;
}

// First entry of dir\pattern: 0 found (name, is_dir, size), -1 none, -2 outside both folders.
int gf_find(const char *gpath, char *name, size_t n, int *is_dir, uint64_t *size) {
    char dir[600];
    snprintf(dir, sizeof dir, "%s", gpath);
    char *s = strrchr(dir, '\\');
    if (!s) s = strrchr(dir, '/');
    const char *pat = s ? s + 1 : dir;
    char patc[256];
    snprintf(patc, sizeof patc, "%s", pat);
    if (s) *s = 0; else snprintf(dir, sizeof dir, ".");
    if (!strcmp(patc, "*.*")) snprintf(patc, sizeof patc, "*");
    char rel[512], real[512];
    uint64_t sz;
    int save = game_rel(dir, rel, sizeof rel);
    if (save < 0) return -2;
    int r = lookup(dir, real, sizeof real, &sz);
    if (r == -2) return -2;
    if (r != 1 && !(save && !*rel)) return -1;
#ifdef __EMSCRIPTEN__
    if (!save) {
    static char list[65536];
    if (web_list(rel, list, sizeof list) < 0) return -1;
    for (char *l = list; *l;) {
        char *e = strchr(l, '\n');
        *e = 0;
        char *t = strchr(l, '\t');
        *t = 0;
        double v = atof(t + 1);
        if (wild(patc, l)) { snprintf(name, n, "%s", l); *is_dir = v < 0; *size = v < 0 ? 0 : (uint64_t)v; return 0; }
        l = e + 1;
    }
    return -1;
    }
#endif
    DIR *d = opendir(real);
    if (!d) return -1;
    struct dirent *de;
    while ((de = readdir(d)))
        if (strcmp(de->d_name, ".") && strcmp(de->d_name, "..") && wild(patc, de->d_name)) {
            char p[1100];
            struct stat sb;
            snprintf(p, sizeof p, "%s/%s", real, de->d_name);
            stat(p, &sb);
            snprintf(name, n, "%s", de->d_name);
            *is_dir = S_ISDIR(sb.st_mode);
            *size = (uint64_t)sb.st_size;
            closedir(d);
            return 0;
        }
    closedir(d);
    return -1;
}

// State the layer keeps for the PC, not the game: save/<name> (DirectInput user maps). The whole file in
// dst (at most n bytes): its length, -1 missing. layer_store replaces it.
int layer_load(const char *name, uint8_t *dst, int n) {
    char p[600];
    snprintf(p, sizeof p, SAVE_DIR "/%s", name);
    int id = gf_open(p);
    if (id < 0) return -1;
    int64_t r = gf_read(id, 0, dst, gf_size(id) < (uint64_t)n ? (uint32_t)gf_size(id) : (uint32_t)n);
    gf_close(id);
    return (int)r;
}
int layer_store(const char *name, const uint8_t *src, int n) {
    char p[600];
    int existed;
    snprintf(p, sizeof p, SAVE_DIR "/%s", name);
    int id = gf_create(p, 2, &existed);                          // CREATE_ALWAYS
    if (id < 0) return -1;
    int r = gf_write(id, 0, src, (uint32_t)n) == n ? 0 : -1;
    gf_close(id);
    return r;
}
