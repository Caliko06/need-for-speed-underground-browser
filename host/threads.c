// Threads and synchronization. Every guest thread is a host thread, but one global lock (the GIL,
// handed out in ticket order) lets only one of them run guest code at a time. A thread gives the
// lock up only inside APIs that block on Windows: Sleep, waits, a critical section owned by another
// thread. So the guest sees real threads; the lifted code needs no atomics.
#include <pthread.h>
#include <sched.h>
#include <time.h>
#include <unistd.h>
#include "host.h"

#define PROCESS_ID 0x8
#define WAIT_TIMEOUT 0x102u
#define INFINITE 0xffffffffu

typedef struct Thread {
    Ctx ctx;
    uint32_t id, handle, start, param, exit_code;
    int started, finished, suspended, parked;
    pthread_t pt;
    uint32_t timer_ms, timer_flags, timer_user, timer_id, killed;   // winmm timers
    uint32_t stack_top;
} Thread;
static Thread *threads[64];
static int nthreads;

static pthread_mutex_t gm = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t turn_cv[128] = {[0 ... 127] = PTHREAD_COND_INITIALIZER};   // ticket t waits on turn_cv[t & 127]
static pthread_cond_t scv = PTHREAD_COND_INITIALIZER;   // some object changed state
static unsigned long next_ticket, serving, gen;

#define QUANTUM_US 20000
// A guest loop holds the GIL while threads that Windows runs on other cores wait: the movie clock is a one-shot
// winmm timer (0x63eaa0) that re-arms itself and wakes the scheduler thread 0x63ea00, which counts the tick
// [0x70fe28] the decoder 0x645a77 spins on. Two GIL hand-offs per tick: at a 20 ms quantum the title movie ran
// ~20x slow and "Press enter" never came. A waiter asks the looping holder to yield after 2 ms.
#define PREEMPT_US 2000
// In a race the main thread passes the GIL ~60 times per frame (at clock reads, to the sound and timer threads) and each
// turn is short; a wake from the condition variable lay ~22 us per hand-off (telemetry gilGap, 2026-10-25). The main
// thread spins this long for its turn before it sleeps. Only the main thread: it is the frame's critical path.
#define MAIN_SPIN_US 300
volatile int rn_preempt;
static uint64_t slice_start, hold_start;
static uint64_t frame_start, frame_hold_us;   // under the GIL; independent of Telem maxima cleared by the page
static uint64_t frame_wait_us, frame_other_us;   // per Present interval: main's total wait for the GIL, longest hold by another thread
static uint32_t frame_other_who;                // start address of that thread (spike lines, host/d3d9.c spike_log)
static uint64_t free_since;     // the GIL was passed on (under gm) to a thread that waits for it; 0 = it was taken
static __thread int is_main;
static __thread uint32_t self_start;    // the guest thread's start address (telemetry hold_other_who)
// Under gm: the next ticket's turn. Only its thread wakes (a broadcast woke every waiter to re-check its ticket).
// Telemetry times the gap until that thread holds the GIL.
// A woken thread can start 17-37 ms late on the web (telemetry gilGap, benches p1103/g60_1103 2026-10-29) and the main
// thread, queued behind it, misses the frame; Windows would run main on its own core meanwhile. So main borrows a turn
// still untaken after one of its 2 ms waits: it gives up its own ticket (pass_turn skips it), and the late thread runs
// when main releases.
static int borrowed;                    // under gm: main holds the GIL on the turn passed to a late thread
static unsigned char cancelled[128];    // under gm: the ticket main gave up when it borrowed
static void pass_turn(void) {
    unsigned long s = __atomic_add_fetch(&serving, 1, __ATOMIC_RELEASE);
    while (s != next_ticket && cancelled[s & 127]) { cancelled[s & 127] = 0; s = __atomic_add_fetch(&serving, 1, __ATOMIC_RELEASE); }
    if (next_ticket != s) { free_since = now_us(); pthread_cond_signal(&turn_cv[s & 127]); }
}
static void release_turn(void) {        // under gm, by the holder
    if (borrowed) { borrowed = 0; free_since = now_us(); pthread_cond_signal(&turn_cv[serving & 127]); return; }
    pass_turn();
}
void gil_acquire(void) {
    uint64_t t0 = now_us();
    pthread_mutex_lock(&gm);
    unsigned long t = next_ticket++;
    if (is_main && t != serving) {
        pthread_mutex_unlock(&gm);
        for (unsigned k = 1; __atomic_load_n(&serving, __ATOMIC_ACQUIRE) != t; k++)
            if (!(k & 63) && now_us() - t0 >= MAIN_SPIN_US) break;
        pthread_mutex_lock(&gm);
    }
    unsigned long late = ~0ul;      // main: the turn seen passed but untaken at its last wait
    while (t != serving || (!is_main && borrowed)) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        uint64_t ns = (uint64_t)ts.tv_nsec + PREEMPT_US * 1000ull;
        ts.tv_sec += ns / 1000000000ull;
        ts.tv_nsec = ns % 1000000000ull;
        if (pthread_cond_timedwait(&turn_cv[t & 127], &gm, &ts) && t != serving) {
            if (is_main && free_since && late == serving) { borrowed = 1; cancelled[t & 127] = 1; break; }
            if (is_main) late = free_since ? serving : ~0ul;
            rn_preempt = 1;   // the holder ran a quantum
        }
    }
    if (free_since && !borrowed) {       // the web's clock is per worker: a gap measured across two threads can come out < 0
        uint64_t now = now_us();
        rn_telem.gil_handoffs++;
        if (now > free_since) rn_telem.gil_gap_us += (uint32_t)(now - free_since);
        free_since = 0;
    }
    pthread_mutex_unlock(&gm);
    slice_start = hold_start = now_us();
    *(is_main ? &rn_telem.gil_main_ms : &rn_telem.gil_other_ms) += (double)(slice_start - t0) / 1000;
    if (is_main) frame_wait_us += slice_start - t0;
}
// Windows preempts a thread when its quantum (about 20 ms on XP) ends. A guest that polls for work
// done by another thread relies on it. The GIL holder gives its turn away at the next API call
// once it has run a quantum (since it got the GIL) while another thread waits for the GIL.
// This runs at every API call (thousands per frame): with no waiter it reads no clock (a clock read
// is a call out to JS on the web), and with one it reads the clock every 256th call: at every 16th the reads were ~9% of
// the main thread's race work (D3DX state calls 0x5c97cb, CPU profile prof1 2026-10-29).
#define SPIN_QUANTUM_US 2000
static int spinners;     // threads that gave the GIL away at a clock read (gil_clock) and wait to get it back
void gil_slice(void) {
    static unsigned calls;
    if (__atomic_load_n(&next_ticket, __ATOMIC_RELAXED) == __atomic_load_n(&serving, __ATOMIC_RELAXED) + 1) return;
    if (++calls & 255 || now_us() - slice_start < (__atomic_load_n(&spinners, __ATOMIC_RELAXED) ? SPIN_QUANTUM_US : QUANTUM_US) * rn_turbo) return;   // a real-time quantum
    gil_release();
    gil_acquire();
}
// A thread that polls the clock is spinning: Speed.exe's frame limiter 0x585b40 loops on QueryPerformanceCounter
// until the frame time is used up. On Windows it spins on its own core while the other threads run (the file
// thread 0x63e4d0 during a load). Under the GIL the spin took their turn: the file thread waited for the GIL 55%
// of the menu->race load (CPU profile 2026-10-24). So a clock read hands the GIL to a waiting thread, and that
// thread gets a short quantum, so the spinner is back about as soon as its time would pass on Windows.
// The main thread also reads the clock ~250 times in a frame's own work. Passing the GIL at each read cost 49 ms of
// waiting in one 83 ms race frame (247 hand-offs, ~190 us each to come back; bench b4_gil1, 2026-10-26), so it passes
// at a clock read only after holding it this long: the limiter's spin still hands its time to the other threads.
// RN_MAINCLOCK=0: pass at every read again (the A/B).
static uint64_t main_clock_us = 1000;
void gil_clock(void) {
    if (__atomic_load_n(&next_ticket, __ATOMIC_RELAXED) == __atomic_load_n(&serving, __ATOMIC_RELAXED) + 1) return;
    if (is_main && now_us() - slice_start < main_clock_us) return;
    __atomic_add_fetch(&spinners, 1, __ATOMIC_RELAXED);
    gil_release();
    gil_acquire();
    __atomic_sub_fetch(&spinners, 1, __ATOMIC_RELAXED);
}
// A sleep without the GIL that counts as a spinner (as gil_clock): a thread that takes the turn meanwhile gets the
// short quantum, so the sleeper is back on time (the limiter sleep, host/win32.c limiter_sleep).
void gil_sleep_us(uint64_t us) {
    __atomic_add_fetch(&spinners, 1, __ATOMIC_RELAXED);
    gil_release();
    usleep((useconds_t)us);
    gil_acquire();
    __atomic_sub_fetch(&spinners, 1, __ATOMIC_RELAXED);
}
// The GIL holder at a backward jump after a waiter's quantum ran out (rt.h PREEMPT).
void gil_preempt(void) {
    rn_preempt = 0;
    gil_release();
    gil_acquire();
}
static void count_hold(void) {
    uint64_t now = now_us(), us = now - hold_start;
    uint64_t start = hold_start > frame_start ? hold_start : frame_start;
    if (now > start && now - start > frame_hold_us) frame_hold_us = now - start;
    double held = (double)us / 1000;
    if (is_main) {
        rn_telem.hold_main_us += (uint32_t)us;
        if (held > rn_telem.hold_main_max_ms) rn_telem.hold_main_max_ms = held;
    } else {
        if (us > frame_other_us) frame_other_us = us, frame_other_who = self_start;
        rn_telem.hold_other_us += (uint32_t)us;
        if (held > rn_telem.hold_other_max_ms) { rn_telem.hold_other_max_ms = held; rn_telem.hold_other_who = self_start; }
    }
}
void gil_frame_detail(float *wait_ms, float *other_ms, uint32_t *who) {
    *wait_ms = (float)(frame_wait_us / 1000.0), *other_ms = (float)(frame_other_us / 1000.0), *who = frame_other_who;
    frame_wait_us = frame_other_us = 0, frame_other_who = 0;
}
float gil_frame_hold_ms(void) {
    uint64_t now = now_us(), start = hold_start > frame_start ? hold_start : frame_start;
    if (now > start && now - start > frame_hold_us) frame_hold_us = now - start;
    float ms = (float)(frame_hold_us / 1000.0);
    frame_start = now;
    frame_hold_us = 0;
    return ms;
}
void gil_release(void) {
    count_hold();
    pthread_mutex_lock(&gm);
    release_turn();
    pthread_mutex_unlock(&gm);
}
static void notify(void) {
    pthread_mutex_lock(&gm);
    gen++;
    pthread_cond_broadcast(&scv);
    pthread_mutex_unlock(&gm);
}
// Give up the GIL until some object changes state or the deadline (µs, 0 = none) passes.
static void wait_change(uint64_t deadline) {
    uint64_t t0 = now_us();
    count_hold();
    pthread_mutex_lock(&gm);
    unsigned long g = gen;
    release_turn();
    while (gen == g) {
        uint64_t now = now_us();
        if (deadline && now >= deadline) break;
        uint64_t step = (deadline ? deadline - now : 100000) / rn_turbo;   // real time: now_us runs rn_turbo times faster
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        uint64_t ns = (uint64_t)ts.tv_nsec + step * 1000;
        ts.tv_sec += ns / 1000000000ull;
        ts.tv_nsec = ns % 1000000000ull;
        pthread_cond_timedwait(&scv, &gm, &ts);
    }
    pthread_mutex_unlock(&gm);
    if (is_main) rn_telem.idle_main_ms += (double)(now_us() - t0) / 1000;   // before the GIL is back: this thread's field
    gil_acquire();
}

static uint32_t tid(Ctx *c) { return ld(c, c->fs + 0x24, 4); }

static void teb_init(Ctx *c, uint32_t teb, uint32_t lo, uint32_t hi, uint32_t id) {
    c->fs = teb;
    st(c, teb + 0x00, 0xffffffffu, 4);     // SEH chain end
    st(c, teb + 0x04, hi, 4);
    st(c, teb + 0x08, lo, 4);
    st(c, teb + 0x18, teb, 4);
    st(c, teb + 0x20, PROCESS_ID, 4);
    st(c, teb + 0x24, id, 4);
    st(c, teb + 0x2c, teb + 0xe10, 4);     // TLS slots
    st(c, teb + 0x30, PEB_ADDR, 4);
}

int rn_is_main_thread(void) { return is_main; }

void threads_init(Ctx *c) {
    teb_init(c, TEB_ADDR, STACK_LO, STACK_HI, 0xc);
    is_main = 1;
    const char *mc = getenv("RN_MAINCLOCK");
    if (mc) main_clock_us = strtoull(mc, NULL, 10);
    gil_acquire();
}

// ---- threads -------------------------------------------------------------------------------
static void *run(void *arg) {
    Thread *t = arg;
    self_start = t->start;
    gil_acquire();
    Ctx *c = &t->ctx;
    for (;;) {   // a finished thread parks until a new CreateThread takes it (reuse_finished)
        uint32_t args[1] = {t->param};
        if (rn_trace()) rn_log("thread %x starts at %08x", t->id, t->start);
        uint32_t r = call_guest(c, t->start, 1, args);
        if (c->halt) rn_stop(c);
        t->exit_code = r;
        t->finished = t->parked = 1;
        notify();
        while (t->parked) wait_change(0);
        self_start = t->start;
    }
    return NULL;
}
// winmm timer: TIME_PERIODIC (1) or one shot; TIME_CALLBACK_EVENT_SET (0x10) or a TIMECALLBACK.
// A one-shot or killed timer's thread does not end: it parks until a new timeSetEvent re-arms it
// (reuse_timer). Games re-arm one-shot timers from inside the callback, every few milliseconds, and a
// thread start on the web waits for the page's thread, with the GIL held (measured: 16% of the main
// thread's race time waiting for that GIL).
static void *run_timer(void *arg) {
    Thread *t = arg;
    self_start = t->start;
    gil_acquire();
    Ctx *c = &t->ctx;
    for (;;) {
        uint64_t next = now_us();
        do {
            next += (uint64_t)t->timer_ms * 1000;
            while (!t->killed && now_us() < next) wait_change(next);
            if (t->killed) break;
            if (t->timer_flags & 0x10) {
                Handle *h = get_handle(t->start);
                if (h && h->kind == H_EVENT) { h->signaled = 1; notify(); }
            } else {
                uint32_t args[5] = {t->timer_id, 0, t->timer_user, 0, 0};
                call_guest(c, t->start, 5, args);
                if (c->halt) rn_stop(c);
            }
        } while (t->timer_flags & 1);
        t->finished = 1;
        while (t->finished) wait_change(0);
    }
    return NULL;
}
static void start_fn(Thread *t, void *(*fn)(void *)) {
    pthread_attr_t a;
    pthread_attr_init(&a);
#ifdef RN_LITE_WASM
    pthread_attr_setstacksize(&a, 2u << 20);   // lifted calls need a host stack as well as the guest stack
#else
    pthread_attr_setstacksize(&a, 4u << 20);
#endif
    t->started = 1;
    if (pthread_create(&t->pt, &a, fn, t)) { fprintf(stderr, "pthread_create failed\n"); exit(1); }
    if (getenv("RN_RAM_AUDIT")) rn_log("ram thread: id=%x start=%08x timer=%u slots=%d", t->id, t->start, t->timer_id, nthreads);
}
static void start(Thread *t) { start_fn(t, run); }
static Thread *thread_of(uint32_t h) {
    Handle *x = get_handle(h);
    return x && x->kind == H_THREAD ? x->thread : NULL;
}

static Thread *new_thread(Ctx *c, uint32_t size) {
    if (nthreads == 64) { rn_halt(c, "too many threads"); return NULL; }
    Thread *t = calloc(1, sizeof *t);
    uint32_t reserve = size > 0x100000 ? size : 0x100000;
    uint32_t stack = virtual_reserve(c, reserve), teb = guest_alloc(0x1000);
    if (!stack || !teb) { set_error(c, 8); free(t); return NULL; }
    t->ctx = *c;                      // same memory; fresh registers below
    memset(t->ctx.r, 0, sizeof t->ctx.r);
    t->ctx.halt = 0; t->ctx.cf = t->ctx.zf = t->ctx.sf = t->ctx.of = t->ctx.pf = t->ctx.df = t->ctx.af = 0;
    finit(&t->ctx);
    t->ctx.fcw = 0x27f;
    t->id = 0x10 + 4u * nthreads;
    teb_init(&t->ctx, teb, stack, stack + reserve, t->id);
    t->stack_top = stack + reserve - 16;
    t->ctx.r[ESP] = t->stack_top;
    threads[nthreads++] = t;
    return t;
}
// A new timer takes a parked timer thread (its stack and TEB too); timeSetEvent_ wakes it.
static Thread *reuse_timer(void) {
    for (int k = 0; k < nthreads; k++) {
        Thread *t = threads[k];
        if (!t->timer_id || !t->finished) continue;
        memset(t->ctx.r, 0, sizeof t->ctx.r);
        t->ctx.halt = 0; t->ctx.cf = t->ctx.zf = t->ctx.sf = t->ctx.of = t->ctx.pf = t->ctx.df = t->ctx.af = 0;
        finit(&t->ctx);
        t->ctx.fcw = 0x27f;
        t->ctx.r[ESP] = t->stack_top;
        t->finished = 0; t->killed = 0;
        return t;
    }
    return NULL;
}
// A new thread takes a finished one (its stack, TEB and host thread, parked in run): the game starts one per load
// (0x654a90, from 0x654cad: two per career event) and never closes its handle ([0x7160c4] is not read again), so
// threads[64] ran out near event 27; on the web each is a Worker. The old handle keeps the exit code (Handle.count).
static Thread *reuse_finished(uint32_t size) {
    if (size > 0x100000) return NULL;
    for (int k = 0; k < nthreads; k++) {
        Thread *t = threads[k];
        if (t->timer_id || !t->finished || !t->parked) continue;
        Handle *h = get_handle(t->handle);
        if (h && h->kind == H_THREAD && h->thread == t) h->thread = NULL, h->count = t->exit_code;
        memset(t->ctx.r, 0, sizeof t->ctx.r);
        t->ctx.halt = 0; t->ctx.cf = t->ctx.zf = t->ctx.sf = t->ctx.of = t->ctx.pf = t->ctx.df = t->ctx.af = 0;
        finit(&t->ctx);
        t->ctx.fcw = 0x27f;
        t->ctx.r[ESP] = t->stack_top;
        t->finished = 0;
        return t;
    }
    return NULL;
}
static void wake(Thread *t) {
    if (t->parked) { t->parked = 0; notify(); }
    else start(t);
}
static uint32_t CreateThread_(Ctx *c) {
    uint32_t size = ARG(1), entry = ARG(2), param = ARG(3), flags = ARG(4), out = ARG(5);
    Thread *t = reuse_finished(size);
    if (!t) t = new_thread(c, size);
    if (!t) return 0;
    t->start = entry; t->param = param;
    t->handle = new_handle(H_THREAD);
    if (!t->handle) { set_error(c, 8); return 0; }   // table full (host/win32.c new_handle logs it): the thread never starts
    get_handle(t->handle)->thread = t;
    if (out) st(c, out, t->id, 4);
    rn_log("CreateThread %08x(%08x) -> thread %x%s", entry, param, t->id, (flags & 4) ? " suspended" : "");
    if (flags & 4) t->suspended = 1;
    else wake(t);
    return t->handle;
}
static uint32_t ResumeThread_(Ctx *c) {
    Thread *t = thread_of(ARG(0));
    if (!t) { rn_halt(c, "ResumeThread on handle %08x", ARG(0)); return 0xffffffffu; }
    uint32_t prev = (uint32_t)t->suspended;
    if (t->suspended && !--t->suspended && (!t->started || t->parked)) wake(t);
    return prev;
}
static uint32_t SuspendThread_(Ctx *c) {
    Thread *t = thread_of(ARG(0));
    if (!t || t->started) { rn_halt(c, "SuspendThread of a running thread (%08x)", ARG(0)); return 0xffffffffu; }
    return (uint32_t)t->suspended++;
}
static uint32_t GetExitCodeThread_(Ctx *c) {
    Thread *t = thread_of(ARG(0));
    Handle *h = get_handle(ARG(0));
    if (!t && h && h->kind == H_THREAD) { st(c, ARG(1), h->count, 4); return 1; }   // finished, its thread reused
    if (!t) { set_error(c, 6); return 0; }
    st(c, ARG(1), t->finished ? t->exit_code : 259, 4);    // STILL_ACTIVE
    return 1;
}
static uint32_t ExitThread_(Ctx *c) { rn_halt(c, "ExitThread(%u)", ARG(0)); return 0; }
static uint32_t TerminateThread_(Ctx *c) { rn_halt(c, "TerminateThread(%08x)", ARG(0)); return 0; }
static uint32_t GetCurrentThreadId_(Ctx *c) { return tid(c); }

static uint32_t timeSetEvent_(Ctx *c) {
    uint32_t ms = ARG(0), cb = ARG(2), user = ARG(3), flags = ARG(4);
    if (flags & ~0x111u) { rn_halt(c, "timeSetEvent flags %08x", flags); return 0; }
    Thread *t = reuse_timer(), *parked = t;
    if (!t) t = new_thread(c, 0);
    if (!t) return 0;
    t->timer_ms = ms ? ms : 1; t->timer_flags = flags; t->timer_user = user; t->start = cb;
    t->timer_id = t->id;
    if (rn_trace()) rn_log("timeSetEvent %u ms -> %s %08x", ms, (flags & 0x10) ? "event" : "callback", cb);
    if (parked) notify();
    else start_fn(t, run_timer);
    return t->timer_id;
}
static uint32_t timeKillEvent_(Ctx *c) {
    for (int k = 0; k < nthreads; k++)
        if (threads[k]->timer_id && threads[k]->timer_id == ARG(0)) { threads[k]->killed = 1; notify(); return 0; }
    return 97;   // TIMERR_NOCANDO
}

// Pseudo handles of this process/thread duplicate into a real handle.
static uint32_t DuplicateHandle_(Ctx *c) {
    uint32_t src = ARG(1), out = ARG(3);
    if (ARG(0) != 0xffffffffu || ARG(2) != 0xffffffffu || (src != 0xfffffffeu && src != 0xffffffffu)) {
        rn_halt(c, "DuplicateHandle of handle %08x", src);
        return 0;
    }
    uint32_t h = new_handle(H_THREAD);
    if (!h) { set_error(c, 8); return 0; }
    if (src == 0xfffffffeu)
        for (int k = 0; k < nthreads; k++)
            if (threads[k]->id == tid(c)) get_handle(h)->thread = threads[k];
    if (out) st(c, out, h, 4);
    return 1;
}

// ---- waits ---------------------------------------------------------------------------------
// 1 = signaled (and consumed for auto-reset events and mutexes), 0 = not yet, -1 = not waitable.
static int try_take(Ctx *c, uint32_t hv) {
    Handle *h = get_handle(hv);
    if (!h) return -1;
    switch (h->kind) {
    case H_EVENT:
        if (!h->signaled) return 0;
        if (!h->manual) h->signaled = 0;
        return 1;
    case H_MUTEX:
        if (h->count && h->owner != tid(c)) return 0;
        h->owner = tid(c);
        h->count++;
        return 1;
    case H_THREAD:
        return h->thread ? h->thread->finished : 1;   // NULL: its thread finished and was reused
    }
    return -1;
}
static uint64_t deadline_of(uint32_t ms) { return ms == INFINITE ? 0 : now_us() + (uint64_t)ms * 1000 + (ms == 0); }

static uint32_t WaitForSingleObject_(Ctx *c) {
    uint32_t h = ARG(0), ms = ARG(1);
    uint64_t dl = deadline_of(ms);
    for (;;) {
        int r = try_take(c, h);
        if (r < 0) { rn_halt(c, "WaitForSingleObject on handle %08x", h); return 0; }
        if (r) return 0;
        if (ms == 0 || (dl && now_us() >= dl)) return WAIT_TIMEOUT;
        if (ms == INFINITE && nthreads == 0) { rn_halt(c, "WaitForSingleObject(INFINITE) with no other thread"); return 0; }
        wait_change(dl);
    }
}
static uint32_t WaitForMultipleObjects_(Ctx *c) {
    uint32_t n = ARG(0), arr = ARG(1), all = ARG(2), ms = ARG(3);
    uint64_t dl = deadline_of(ms);
    if (all) { rn_halt(c, "WaitForMultipleObjects(wait all)"); return 0; }
    for (;;) {
        for (uint32_t k = 0; k < n; k++) {
            int r = try_take(c, ld(c, arr + 4 * k, 4));
            if (r < 0) { rn_halt(c, "WaitForMultipleObjects on handle %08x", ld(c, arr + 4 * k, 4)); return 0; }
            if (r) return k;
        }
        if (ms == 0 || (dl && now_us() >= dl)) return WAIT_TIMEOUT;
        wait_change(dl);
    }
}
static uint32_t Sleep_(Ctx *c) {
    uint32_t ms = ARG(0);
    gil_release();
    if (ms) { uint64_t ns = (uint64_t)ms * 1000000 / rn_turbo; struct timespec ts = {(time_t)(ns / 1000000000), (long)(ns % 1000000000)}; nanosleep(&ts, NULL); }
    else sched_yield();
    gil_acquire();
    (void)c;
    return 0;
}
static uint32_t SleepEx_(Ctx *c) { Sleep_(c); return 0; }

static uint32_t CreateEventA_(Ctx *c) {
    if (ARG(3)) { rn_halt(c, "CreateEventA named %s", G(ARG(3))); return 0; }
    uint32_t h = new_handle(H_EVENT);
    if (!h) { set_error(c, 8); return 0; }
    get_handle(h)->manual = ARG(1) != 0;
    get_handle(h)->signaled = ARG(2) != 0;
    set_error(c, 0);
    return h;
}
static uint32_t SetEvent_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_EVENT) { set_error(c, 6); return 0; }
    h->signaled = 1;
    notify();
    return 1;
}
static uint32_t ResetEvent_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_EVENT) { set_error(c, 6); return 0; }
    h->signaled = 0;
    return 1;
}
// Named mutexes live in this process only: the first CreateMutexA of a name creates it.
static struct { char name[128]; uint32_t h; } named[16];
static uint32_t CreateMutexA_(Ctx *c) {
    uint32_t own = ARG(1), name = ARG(2);
    if (name)
        for (int k = 0; k < 16; k++)
            if (named[k].h && !strcmp(named[k].name, G(name))) { set_error(c, 183); return named[k].h; }
    uint32_t h = new_handle(H_MUTEX);
    if (!h) { set_error(c, 8); return 0; }
    if (own) { get_handle(h)->owner = tid(c); get_handle(h)->count = 1; }
    if (name)
        for (int k = 0; k < 16; k++)
            if (!named[k].h) { snprintf(named[k].name, sizeof named[k].name, "%s", G(name)); named[k].h = h; break; }
    set_error(c, 0);
    return h;
}
static uint32_t ReleaseMutex_(Ctx *c) {
    Handle *h = get_handle(ARG(0));
    if (!h || h->kind != H_MUTEX || !h->count || h->owner != tid(c)) { set_error(c, 288); return 0; }
    if (!--h->count) { h->owner = 0; notify(); }
    return 1;
}

// CRITICAL_SECTION: +4 LockCount, +8 RecursionCount, +12 OwningThread.
static int cs_waiters;
static uint32_t InitializeCriticalSection_(Ctx *c) {
    uint32_t p = ARG(0);
    memset(G(p), 0, 24);
    st(c, p + 4, 0xffffffffu, 4);
    return 0;
}
static uint32_t InitializeCriticalSectionAndSpinCount_(Ctx *c) { InitializeCriticalSection_(c); return 1; }
static uint32_t EnterCriticalSection_(Ctx *c) {
    uint32_t p = ARG(0), me = tid(c);
    while (ld(c, p + 8, 4) && ld(c, p + 12, 4) != me) {
        cs_waiters++;
        wait_change(0);
        cs_waiters--;
    }
    st(c, p + 4, ld(c, p + 4, 4) + 1, 4);
    st(c, p + 8, ld(c, p + 8, 4) + 1, 4);
    st(c, p + 12, me, 4);
    return 0;
}
static uint32_t LeaveCriticalSection_(Ctx *c) {
    uint32_t p = ARG(0), rc = ld(c, p + 8, 4) - 1;
    st(c, p + 4, ld(c, p + 4, 4) - 1, 4);
    st(c, p + 8, rc, 4);
    if (!rc) { st(c, p + 12, 0, 4); if (cs_waiters) notify(); }
    return 0;
}
static uint32_t DeleteCriticalSection_(Ctx *c) { (void)c; return 0; }

#define T(name, n) {"kernel32.dll", #name, n, name##_}
const Api thread_apis[] = {
    T(CreateThread, 6), T(ResumeThread, 1), T(SuspendThread, 1), T(GetExitCodeThread, 2), T(ExitThread, 1),
    T(TerminateThread, 2), T(GetCurrentThreadId, 0), T(DuplicateHandle, 7),
    T(WaitForSingleObject, 2), T(WaitForMultipleObjects, 4), T(Sleep, 1), T(SleepEx, 2),
    T(CreateEventA, 4), T(SetEvent, 1), T(ResetEvent, 1), T(CreateMutexA, 3), T(ReleaseMutex, 1),
    T(InitializeCriticalSection, 1), T(InitializeCriticalSectionAndSpinCount, 2), T(EnterCriticalSection, 1),
    T(LeaveCriticalSection, 1), T(DeleteCriticalSection, 1),
    {"winmm.dll", "timeSetEvent", 5, timeSetEvent_}, {"winmm.dll", "timeKillEvent", 1, timeKillEvent_},
};
const int thread_api_count = sizeof thread_apis / sizeof thread_apis[0];
