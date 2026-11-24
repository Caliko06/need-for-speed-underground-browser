// Host layer: the Windows APIs Speed.exe imports, written against the documented API.
#pragma once
#include <stdio.h>
#include <stdlib.h>
#include "rt.h"

// One parse for every RN_ switch (audit 2026-11-05 C14): unset or empty = dflt, else its integer value ("0" off, "1" on, "2" forced...).
static inline int rn_env(const char *name, int dflt) { const char *e = getenv(name); return e && *e ? atoi(e) : dflt; }

// Guest memory layout (no relocations in Speed.exe: the image must sit at 0x400000).
#ifdef RN_LITE_WASM
#define GUEST_MEM   0x10000000u     // 256 MB flat guest space (peak measured 118 MB)
#else
#define GUEST_MEM   0x18000000u     // 384 MB flat guest space
#endif
#define TEB_ADDR    0x00010000u
#define PEB_ADDR    0x00011000u
#define STR_ADDR    0x00012000u     // command line, environment, module name
#define STACK_LO    0x00300000u     // 1 MB main stack (SizeOfStackReserve)
#define STACK_HI    0x00400000u
#define IMAGE_BASE  0x00400000u
#define SCREEN_ADDR 0x00013000u     // PATCH 0x40877e reads the screen width and height here (win32_init writes them)
// PATCH 0x40bf09..: the 2D quad code reads S/320 (+8) and S (+12) as floats; S = 4:3 over the screen aspect, at most 1
// PATCH 0x4470f0: the RNG seed reads RN_SEED at +16 (0 = the original clock seed); PATCH 0x42d4b0: RN_AUTOPILOT at +20
// PATCH 0x42d4a9: the drag player mode at +24 (4 with RN_AUTOPILOT, else 3); PATCH 0x460a80: the steering model at +32
// PATCH 0x4b4321: the host function that builds each race opponent (host/rivals.c) at +0x60
// PATCH 0x57119a: host/rivals.c car_draw (racers at the LOD of the player's car) at +0x64
// PATCH 0x410c1b: the ROADREFLECTION cap word at +0x70 (host/win32.c, RN_ROADREFL=off makes it 1)
// PATCH 0x4b528d: host/free.c free_setup (free mode's rivals in Free Run) at +0x68; PATCH 0x4b3c2f: free_traffic at +0x6c
// PATCH 0x422b36: host/free.c free_place (the traffic placer 0x598bf0, step by step) at +0x7c
// PATCH 0x45399f: host/rivals.c traffic_behind (a traffic car sees the player closing from behind) at +0x98
#define HEAP_LO     0x00800000u
#define HOST_BASE   0xe0000000u     // fake code addresses of host functions: HOST_BASE + 16*index

#include <dirent.h>

typedef uint32_t (*HostFn)(Ctx *c);
typedef struct { const char *dll, *name; int nargs; HostFn fn; } Api;   // nargs < 0: cdecl

extern Ctx *g_ctx;
extern const Api win32_apis[], user32_apis[], thread_apis[], net_apis[], d3d9_apis[], dinput8_apis[], dsound_apis[], rivals_apis[], free_apis[], horn_apis[];
extern const int win32_api_count, user32_api_count, thread_api_count, net_api_count, d3d9_api_count, dinput8_api_count, dsound_api_count, rivals_api_count, free_api_count, horn_api_count;
extern int rn_free_now;
uint32_t free_rival(Ctx *c, uint32_t *a);
void traffic_tick(Ctx *c);
void horn_tick(Ctx *c);          // host/horn.c, at each Present next to free_tick
void rn_player_car(Ctx *c);   // RN_CAR: the player's car in a race (host/rivals.c)
void free_tick(Ctx *c);          // host/free.c, at each Present
void crashwatch_present(Ctx *c); // host/crashwatch.c, at each Present (RN_CRASHWATCH, off by default)
void crashwatch_stop(Ctx *c);
void crashwatch_free(Ctx *c, uint32_t p);   // from win32.c heap_free (RN_STW build only acts)    // host/crashwatch.c, from rn_stop
void lights_init(Ctx *c);   // host/lights.c
#define LIGHTS_N 4          // other cars' headlights on the world (sm1.h SM1_HL_N, the free texcoords t4..t7)
const float *lights_hl(Ctx *c);   // their projectors this frame: VS c16..c31 of the headlight world shaders

enum { H_FREE, H_FILE, H_EVENT, H_MUTEX, H_FIND, H_HEAP, H_THREAD, H_SNAPSHOT, H_KEY, H_MAPPING };
struct Thread;
typedef struct {
    int kind;
    int gf;                         // files: host/files.c id and the file pointer
    uint32_t pos;
    int signaled, manual;           // events; snapshot position
    uint32_t owner, count;          // mutexes
    struct Thread *thread;
    char path[512];
    DIR *dir;
    char pattern[256];
} Handle;
uint32_t new_handle(int kind);
Handle *get_handle(uint32_t h);

// Arguments of a stdcall/cdecl host function: [esp] = return address, [esp+4] = first argument.
#define ARG(n) ld(c, c->r[ESP] + 4 + 4 * (n), 4)
#define G(p) ((char *)c->mem + (uint32_t)(p))

const Api *find_api(const char *dll, const char *name);
uint32_t call_guest(Ctx *c, uint32_t fn, int n, const uint32_t *args);
uint64_t call_guest64(Ctx *c, uint32_t fn, int n, const uint32_t *args);   // stdcall, edx:eax
uint32_t call_guest_cdecl(Ctx *c, uint32_t fn, int n, const uint32_t *args);   // the caller pops the args
uint32_t host_addr_of(const char *dll, const char *name);     // HOST_BASE address, registering if needed
void rn_halt(Ctx *c, const char *fmt, ...);
extern uint32_t rn_flow;   // host/phase.c, every Present: game-flow state [0x77a920] << 8 | race state [[0x7361f0]] (RN_KEYS "ms@S/R:KEY")
extern uint32_t rn_race;   // host/phase.c: races begun this session; a module zeroes its race state when this changes
static inline int rn_racing(void) { return rn_flow >> 8 == 6; }   // in a race (flow 6), grid and pause included
extern uint32_t rn_finished;   // host/phase.c: rn_race once its finish runs (RaceCoordinator 0x423f20: state 8, or 1 with [coord+0x14] == 8)
static inline int rn_race_over(void) { return rn_race && rn_finished == rn_race; }   // this race is finished (results), still flow 6
static inline int rn_new_race(uint32_t *seen) { if (*seen == rn_race) return 0; *seen = rn_race; return 1; }
void rn_phase_tick(Ctx *c);       // host/phase.c, first thing at each Present
void rn_phase_grid(Ctx *c);       // host/phase.c, from host/free.c grid_fix: a race's grid is placed (every race, Restart too)
void free_race_begin(Ctx *c);     // host/free.c: zero free mode's per-race state (from rn_phase)
void free_frontend(Ctx *c);       // host/free.c: back in the front end, free mode's event is over (from rn_phase)
void rivals_frontend(Ctx *c);     // host/rivals.c: back in the front end, the shared tables it changed get the game's values (from rn_phase)
void cars_hook(Ctx *c);          // host/rivals.c: the race's car folders from the entrant list, prefetched once per list (called from gf_open)
extern const char *rn_screen;   // RN_FLOWLOG: the post-race screen shown (e.g. "PostRaceMenu.fng"), "" if none
extern unsigned rn_turbo;       // RN_TURBO: the guest clocks run this many times faster (native tests; 1 = play)
extern const char *rn_fe;       // RN_FLOWLOG: the front end's active packages, "A.fng,B.fng,..."
extern int rn_screen_w, rn_screen_h;   // the desktop the game sees: RN_SCREEN=WxH (the page passes its window size)
void rn_screen_apply(Ctx *c, uint32_t pp);   // host/win32.c: applies a pending rn_request_screen inside Reset
void rn_log(const char *fmt, ...);
void input_jump(Ctx *c);        // RN_JUMP (host/input.c), from the RN_FLOWLOG pass at each Present
void rn_cov_report(void);   // host/cov.c: the coverage bitmap (RN_COV=1 build); empty otherwise
void input_finish(Ctx *c);      // RN_FINISH (host/input.c), same place
void input_unstick(Ctx *c);     // RN_AUTOPILOT reset when stuck (host/input.c), same place
void input_open(Ctx *c);        // RN_OPEN (host/input.c), same place
void input_next(Ctx *c);        // RN_NEXT (host/input.c), same place
void input_call(Ctx *c);        // RN_CALL (host/input.c), same place
void guest_mem_log(const char *why);
void d3d9_mem(uint32_t *dead, uint32_t *live);   // host/d3d9.c: guest memory of its objects   // host/win32.c: heap and VirtualAlloc space, one line
void input_career(Ctx *c);      // RN_CAREER (host/input.c), same place
extern int rn_steerlog;         // RN_STEERLOG (host/input.c): the player's steering, per event and per Present
void steer_event(Ctx *c);       // from rn_call at the steer handler 0x461840
void steer_frame(Ctx *c);       // from Present
int rn_trace(void);
extern int rn_resetlog;     // RN_RESETLOG (host/aitel.c): the game's reset 0x427c50/0x427f70, per call and 120 frames after
void reset_call(Ctx *c, uint32_t target);   // from rn_call before the body
void reset_tel(Ctx *c);     // from Present
void win32_init(Ctx *c, uint32_t image_size);
uint32_t guest_alloc(uint32_t size);                           // zeroed, for host-owned guest data
void guest_free(uint32_t p);       // host/win32.c: back to the guest heap
uint64_t now_us(void);
int rn_is_main_thread(void);
void rn_fixedclock_start(Ctx *c);
uint32_t virtual_reserve(Ctx *c, uint32_t size);
void gil_acquire(void);
void gil_release(void);
void gil_sleep_us(uint64_t us);
void gil_slice(void);                                          // preempt at an API call after a quantum
void gil_clock(void);                                          // a clock read: let a waiting thread run
// Telemetry: running totals that web/telemetry.js reads at every frame (layout mirrored there). Each field has
// one writer: the game threads under the GIL, or the mixer under its lock. The maxima are cleared by the page.
typedef struct {
    double gpu_wait_ms;         // Present waiting for the page (d3d9 hand_off)
    double gil_main_ms;         // the main thread waiting for its GIL turn (another guest thread runs)
    double gil_other_ms;        // every other guest thread waiting for its turn
    double read_ms;             // game file reads from the server (sync XHR, GIL held)
    double idle_main_ms;        // the main thread in Sleep or a wait (GIL given up on purpose)
    double hold_main_max_ms;    // longest time the main thread kept the GIL in one go (a maximum the page clears)
    double hold_other_max_ms;   // the same for every other guest thread
    uint32_t presents, reads, read_kb;
    uint32_t stream_pm;         // worst looping buffer: frames mixed since its last Unlock, per mille of its length
    uint32_t starves;           // times a looping buffer played a whole lap with no Unlock (stale audio repeats)
    uint32_t starve_buf;        // dsound object index of the last one
    uint32_t clock_calls;       // GetTickCount, timeGetTime, QueryPerformanceCounter: many per frame = a busy wait
    uint32_t gil_handoffs;      // GIL turns passed to a thread that was waiting for it
    uint32_t gil_gap_us;        // time the GIL lay free in those hand-offs (the waiter waking up): no guest code runs
    uint32_t hold_main_us;      // time the main thread kept the GIL (its guest code and the APIs it ran)
    uint32_t hold_other_us;     // the same for every other guest thread
    uint32_t hold_other_who;    // start address of the thread behind hold_other_max_ms (the page clears it with the max)
} Telem;
extern Telem rn_telem;
// RnStab: 60 bytes, little-endian 4-byte u32/f32 fields; racing updates every Present, spike data persists until the next spike or race.
typedef struct {
    uint32_t racing, race_id, spikes, last_frame;
    float last_ms;
    uint32_t site[3], site_n[3];
    uint32_t last_reads, last_read_kb;
    float last_read_ms, last_hold_ms;
} RnStab;
void gil_frame_detail(float *wait_ms, float *other_ms, uint32_t *who);   // this Present interval: main's GIL wait, longest other hold + its thread; resets
float gil_frame_hold_ms(void);   // largest GIL hold within this Present interval; resets its separate frame maximum
void dispatch_threads_report(void);                             // log what every guest thread is doing now
void threads_init(Ctx *main_ctx);
void rn_stop(Ctx *c);                                          // report the halt and end the process
void files_set_root(const char *dir);
int gf_stat(const char *gpath);                                // 0 file, 1 directory, -1 missing, -2 outside
int gf_open(const char *gpath);                                // id, or -1 missing, -2 outside, -3 directory
uint64_t gf_size(int id);
int64_t gf_read(int id, uint64_t off, uint8_t *dst, uint32_t n);
void gf_close(int id);
void gf_prefetch_track(int id);                              // web: queue the hint lines of a track (t<id>) once the race is known (host/files.c)
void gf_track_poll(void);                                    // web: every Present, prefetch the track highlighted in the Quick Race menu (host/files.c)
void gf_prefetch(const char *gpath);                         // web: bring a file the game is about to open (host/files.c)
// Save folder only: create/open for writing (disp = CreateFileA dwCreationDisposition). id, or -1 missing,
// -2 outside, -3 a directory, -4 exists (CREATE_NEW), -5 read-only (game folder), -6 the folder is missing.
int gf_create(const char *gpath, int disp, int *existed);
int gf_is_save(int id);
int64_t gf_write(int id, uint64_t off, const uint8_t *src, uint32_t n);
int gf_truncate(int id, uint64_t size);
int gf_flush(int id);
int gf_mkdir(const char *gpath);                                // 0 made, 1 exists, -1 no parent, -2 outside
int gf_delete(const char *gpath);                               // 0, -1 missing, -2 outside the save folder
int gf_find(const char *gpath, char *name, size_t n, int *is_dir, uint64_t *size);
int layer_load(const char *name, uint8_t *dst, int n);         // save/<name>: length, -1 missing
int layer_store(const char *name, const uint8_t *src, int n);
void set_error(Ctx *c, uint32_t e);
// Keyboard and mouse (host/input.c): input_poll hands new events to dinput8_* and user32_key.
void input_poll(void);
uint32_t input_vk_state(uint32_t vk);                          // GetAsyncKeyState/GetKeyState bits
int input_key_down(uint8_t dik);
int input_shift(void);
int input_alt(void);
char input_char_of(uint8_t vk, int shift);
void input_key_name(uint8_t dik, char *out, int n);                 // GetKeyNameText, US layout
void dinput8_key(uint8_t dik, int down);
int dinput8_key_pending(void);
void dinput8_button(int b, int down);
void dinput8_motion(int32_t dx, int32_t dy, int32_t dz);
int input_hud_inset(void);                                    // web: how far the HUD's side groups stay from the picture's edge (notch), permille of its width
void input_mouse_exclusive(int on);                            // web: the page hides and locks the pointer
void user32_key(uint8_t dik, uint8_t vk, int down);

#define FREE_TRAFFIC 13     // free mode trackinfo traffic count (RN_FREETRAFFIC), x1.5 = 19 cars asked; the placer fits 19 to 21 with FREE_ZONE
