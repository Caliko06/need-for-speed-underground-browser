// Boot: the page log, the WebAssembly start and the frame loop (moved out of web/index.html, GOAL 2026-11-05).
const log = document.getElementById('log'), status = document.getElementById('status');
const t0 = performance.now();
// Everything shown here also goes to tools/serve.py (build/web.log), so a session can be read afterwards.
const LOG_MAX = 5000, DOM_LOG_MAX = 500;
let pending = [], allLog = [], memTick = 0;       // allLog: bounded session log (cap LOG_MAX), for the F10 download (telemetry.js)
const duelBox = Object.assign(document.createElement('div'), { style: 'position:fixed;left:50%;top:14%;transform:translateX(-50%);padding:6px 16px;background:rgba(0,0,0,.72);color:#ffc24a;font:bold 20px system-ui;border-radius:6px;pointer-events:none;display:none;z-index:9' });
const toast = text => { if (!duelBox.isConnected) document.body.appendChild(duelBox); duelBox.textContent = text; duelBox.style.display = ''; clearTimeout(toast.t); toast.t = setTimeout(() => duelBox.style.display = 'none', 3500); };
const duelSay = s => { const m = /DUEL (\S+) (start|won|lost)/.exec(s); if (m) toast({ start: `Duelo con ${m[1]}`, won: `${m[1]} te ganó`, lost: `Le ganaste a ${m[1]}` }[m[2]]); };
const keep = s => { pending.push(s); allLog.push(s); if (allLog.length > LOG_MAX) allLog.splice(0, allLog.length - LOG_MAX); if (s.includes('DUEL ')) duelSay(s); };
let logUp = !window.RN_PUBLIC;                    // tools/serve.py answers /log; a plain web host does not, and then nothing is sent
function flush() {
  if (!pending.length) return;
  if (!logUp) { pending = []; return; }
  const body = pending.join('\n') + '\n';
  pending = [];
  // keepalive (the batch still goes out if the page is closing) caps the body at 64 KB: a bigger batch was dropped whole,
  // silently (518 pack errors in one second took the race HUD line with them and the run looked hung, build/bench/g_cas).
  fetch('/log', { method: 'POST', body, keepalive: body.length < 60000 }).catch(() => {});
}
if (logUp) fetch('/log?new', { method: 'POST', body: `page ${location.origin + location.pathname + RN_SEARCH} ${new Date().toISOString()}\n` }).then(r => { logUp = r.ok; }, () => { logUp = false; });
setInterval(flush, 1000);
const secs = () => ((performance.now() - t0) / 1000).toFixed(2);
addEventListener('keydown', e => { if (!e.repeat) keep(`${secs()} key down ${e.code}`); }, true);
addEventListener('keyup', e => keep(`${secs()} key up ${e.code}`), true);
// A page error ends the session while the game is still loading (it would never start) or when it is the engine's
// (out/speed.js and its threads, memory). Once the game runs, an error in the page's own controls is logged and the game goes on
// (2026-11-15: a setPointerCapture error in web/touch.js put the stop card over a running race).
const fatal = (msg, file) => RN_APP.state === 'check' || RN_APP.state === 'load' || !file || /speed\.js/.test(file) || /RuntimeError|abort|memory|unreachable|worker/i.test(msg);
addEventListener('error', e => { line('JS error: ' + e.message + ' at ' + e.filename + ':' + e.lineno, fatal(String(e.message), e.filename) ? 'stop' : 'dim'); flush(); });
addEventListener('unhandledrejection', e => { const t = String(e.reason && e.reason.stack || e.reason); line('JS rejection: ' + t, fatal(t, /speed\.js/.test(t) ? 'speed.js' : /\.js/.test(t) ? 'page' : '') ? 'stop' : 'dim'); flush(); });
addEventListener('pagehide', flush);
// The session report: one .json the browser saves (Downloads). Nothing is sent, so it also works on a plain host (RN_PUBLIC).
// F10 saves it (a media key on a Mac); the stop card has the download button.
window.rnReport = () => {
  const date = new Date().toISOString(), name = `nfsu-session-${date.replace(/[:.]/g, '-')}.json`;
  const blob = new Blob([JSON.stringify({ format: 'rn-session-2', url: location.origin + location.pathname + RN_SEARCH, date, ua: navigator.userAgent,
    screen: `${innerWidth}x${innerHeight} dpr ${devicePixelRatio}`, saved: +secs(), state: RN_APP.state,
    ...(telem ? telem.dump() : {}), log: allLog })], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  line(`report: session saved as ${name}`); toast('Reporte descargado');
};
let telem = null;
addEventListener('keydown', e => {
  if (e.code !== 'F10') return;
  e.preventDefault(); e.stopPropagation();
  if (!e.repeat) window.rnReport();
}, true);
// ?dbg=1: the log panel open from the start (a phone has no F2), to read or screenshot what the page did.
if (RN_Q.get('dbg') === '1') document.body.classList.add('dbg');
addEventListener('keydown', e => { if (e.code === 'F2') { document.body.classList.toggle('dbg'); e.preventDefault(); e.stopPropagation(); } }, true);
// Crash report (OWNER 2026-11-21: crashes only, anonymous): on nfsu.cc the first stop line sends one small JSON to /crash
// (tools/crash/worker.js keeps it in the private R2 bucket nfsu-crash; tools/crash/read.sh lists them). No address, no ids,
// no saves: the build, the browser, the GPU path and the log lines around the stop. ?crash=0 sends nothing.
function crashSend(s) {
  if (!window.RN_PUBLIC || crashSend.done || RN_Q.get('crash') === '0') return;
  crashSend.done = true;
  const cut = l => l.length > 300 ? l.slice(0, 300) + '...' : l;
  navigator.sendBeacon('/crash', new Blob([JSON.stringify({ format: 'rn-crash-1', v: window.RN_V || '', stop: cut(s), at: +secs(), state: RN_APP.state,
    ua: navigator.userAgent, screen: `${innerWidth}x${innerHeight} dpr ${devicePixelRatio}`, mem: navigator.deviceMemory || 0, cores: navigator.hardwareConcurrency || 0,
    head: allLog.filter(l => /gpu\.js: (adapter|WebGL)| mode: /.test(l)).slice(0, 4).map(cut), tail: allLog.slice(-40).map(cut) })], { type: 'application/json' }));
}
function line(s, cls) {
  keep(`${secs()} ${s}`);
  if (/^STOP|^JS |abort|Aborted|RuntimeError/.test(s)) setTimeout(flush, 0);
  // The front-end packages on screen (host/d3d9.c flow_log): web/touch.js picks its layout from them.
  if (s.includes('flow manual ')) { window.RN_MANUAL = /flow manual 1/.test(s); dispatchEvent(new Event('rn-fe')); }
  if (s.includes('flow fe ')) { const m = /flow fe (\S*) \(frame/.exec(s); if (m) { window.RN_FE = m[1].split(',').filter(Boolean); dispatchEvent(new Event('rn-fe')); } }
  const d = document.createElement('div');
  if (cls) d.className = cls;
  else if (/^STOP/.test(s)) d.className = 'stop';
  else if (/^  \S+!/.test(s)) d.className = 'api';
  d.textContent = s;
  log.appendChild(d);
  while (log.childElementCount > DOM_LOG_MAX) log.firstElementChild.remove();
  // A 'stop' line (missing WebGPU, COOP/COEP, a lost GPU) ends the session: the gate says why (web/app.js), F2 opens this log.
  if (cls === 'stop' || /^STOP/.test(s)) { crashSend(s); if (memTick) { clearInterval(memTick); memTick = 0; } status.textContent = 'detenido a los ' + ((performance.now() - t0) / 1000).toFixed(2) + ' s'; status.className = 'stop'; RN_APP.set('stop', s); }
  // The launcher's curtain (?fast=1 with ?start=, web/index.html) lifts on arrival: the main menu, or the screen after the main menu (career).
  else if (CURTAIN && RN_APP.state === 'load') {
    if (/flow fe .*MU_Main_PC\.fng/.test(s)) { if (DEST === 'menu') arrive(); else main = true; }
    else if (main && /flow fe /.test(s)) arrive();
  }
}
const START = RN_Q.get('start'), CURTAIN = RN_Q.get('fast') === '1' && !!START;
// Where the scripted trip ends, and so what lifts the curtain: career, any other ?start= is the main menu (WORLD retired 2026-11-17, attic/world/README.md:
// an old ?start=world link lands on the main menu). The curtain is down while RN_APP.state is 'load' (web/app.js): no flag of its own.
const DEST = START === 'career' ? 'career' : 'menu';
let main = false;
const arrive = () => { if (RN_APP.state === 'load') RN_APP.set('run'); };
RN_APP.on((s, from) => {
  keep(`${secs()} app: ${from} -> ${s}`);
  if (s === 'stop' && memTick) { clearInterval(memTick); memTick = 0; }
});
// A download whose bytes are counted on the gate. Compressed transfers have no usable total, so it shows megabytes.
async function download(url, what) {
  const r = await fetch(url + (window.RN_V ? '?v=' + RN_V : ''));   // RN_V: tools/build_public.py, a new address per build
  if (!r.ok) throw new Error(`descarga de ${url}: HTTP ${r.status}`);
  let n = 0, mb = -1;
  const count = new TransformStream({ transform(c, ctl) {
    n += c.byteLength;
    if (n >> 20 !== mb) { mb = n >> 20; if (RN_APP.state === 'load') RN_APP.say(`${what} ${mb} MB`); }
    ctl.enqueue(c);
  } });
  return new Response(r.body.pipeThrough(count), { headers: { 'Content-Type': r.headers.get('Content-Type') || 'application/octet-stream' } });
}
(async () => {
  // check: what the game cannot run without, before any download (the wasm is 70 MB).
  if (!crossOriginIsolated || typeof SharedArrayBuffer === 'undefined') { line('sin aislamiento: crossOriginIsolated false (COOP/COEP); WebViews like LineageOS Jelly never isolate', 'stop'); return; }
  // No WebGPU adapter (iOS 18 and older, Firefox on Android/Linux, old Android) or ?gl=1: WebGPU on WebGL 2 (web/webgpu_gl.js). It
  // replaces navigator.gpu and canvas.getContext('webgpu'), so it is loaded only here, never next to a working WebGPU.
  const webgl2 = RN_Q.get('gl') === '1' || !await navigator.gpu?.requestAdapter().catch(() => null);
  RN_TIER = rnDetectTier(!webgl2);
  line(`tier: ${RN_TIER} (${['full', 'standard', 'lite', 'ultralite'].includes(RN_TIER_OVERRIDE) ? 'override' : 'auto'}, ${webgl2 ? 'WebGL 2' : 'WebGPU'}, RAM ${navigator.deviceMemory || '?'} GB, cores ${navigator.hardwareConcurrency || '?'})`);
  if (webgl2) {
    // Resolve the mobile default before startGpu consumes RN_Q; this visit's ?sharp= still wins.
    if ((RN_LOW_TIER || RN_APP.coarse) && !RN_SHARP_EXPLICIT) RN_Q.set('sharp', 'off');
    const probe = document.createElement('canvas').getContext('webgl2');
    if (!probe) { line('gpu.js: este navegador no tiene WebGPU ni WebGL 2', 'stop'); return; }
    probe.getExtension('WEBGL_lose_context')?.loseContext(); // release the capability probe, never retain a second GL device
    await new Promise((ok, no) => document.head.appendChild(Object.assign(document.createElement('script'), { src: 'webgpu_gl.js' + (window.RN_V ? '?v=' + RN_V : ''), onload: ok, onerror: no })));
    navigator.gpu.gpu_js.canvas = document.getElementById('screen');
    if (RN_Q.get('glerr') === '1') navigator.gpu.gpu_js.errs = {};   // GL errors per command kind (web/webgpu_gl.js submit)   // the device's GL context is the page's canvas (no copy per frame)
    line('gpu.js: WebGL 2 (sin WebGPU)');
  }
  RN_APP.set('load');
  if (window.RN_HOLD) await window.RN_HOLD;       // ?fast=1: scene B draws first (web/index.html)
  // Speed.exe downloads in parallel with speed.wasm (or speed_lite.wasm on lite/ultralite).
  const wantLite = RN_TIER === 'lite' || RN_TIER === 'ultralite';
  const loadScript = src => new Promise((ok, no) => document.head.appendChild(Object.assign(document.createElement('script'), { src: src + (window.RN_V ? '?v=' + RN_V : ''), onload: ok, onerror: no })));
  let wasmUrl = 'out/speed.wasm';
  if (wantLite) {
    try { await loadScript('out/speed_lite.js'); wasmUrl = 'out/speed_lite.wasm'; line('wasm: speed_lite (640 MB)'); }
    catch { await loadScript('out/speed.js'); line('wasm: speed_lite missing, fallback speed'); }
  } else {
    await loadScript('out/speed.js');
  }
  let exe = null;
  const exeP = download('pc/Speed.exe', 'Descargando').then(r => r.arrayBuffer()).then(b => new Uint8Array(b));
  exeP.catch(() => {});
  // Game files are read on demand by the game thread (host/files.c), not loaded here.
  status.textContent = 'corriendo'; status.className = 'run';
  const M = await Speed({
    arguments: ['/pc/Speed.exe', '/game'],
    print: s => line(s), printErr: s => line(s, 'dim'),
    onAbort: what => line('STOP wasm abort: ' + what),
    // The 70 MB module compiles while it downloads, as Emscripten's own loader does, with the bytes counted on the gate.
    instantiateWasm: (imports, done) => {
      Promise.all([exeP, download(wasmUrl, 'Descargando').then(r => WebAssembly.instantiateStreaming(r, imports))])
        .then(([e, w]) => { exe = e; RN_APP.say('Arrancando…'); done(w.instance, w.module); }, e => line('STOP wasm: ' + e.message));
      return {};
    },
    preRun: [m => {
      m.FS.mkdir('/pc'); m.FS.writeFile('/pc/Speed.exe', exe);
      // The game draws at the pixels of this window (PATCH 0x408760), at most 2560x1440 to keep the GPU load sane.
      // A phone opened upright still gets a landscape back buffer (the game waits behind the upright gate, web/app.js): the
      // size is fixed here for the whole session.
      // Opened from the home screen (no browser bars) the picture is the whole screen: its size comes from screen.*, which does not
      // depend on how the phone was held at launch (iPhone starts a home-screen app upright; a window size read then left bars).
      const home = RN_APP.coarse && (navigator.standalone || matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches);
      const turned = RN_APP.coarse && innerHeight > innerWidth;
      const vw = home ? Math.max(screen.width, screen.height) : turned ? innerHeight : innerWidth, vh = home ? Math.min(screen.width, screen.height) : turned ? innerWidth : innerHeight;
      const low = RN_LOW_TIER || RN_PHONE || RN_APP.coarse, dpr = window.devicePixelRatio || 1;
      const requestedBB = Number(RN_Q.get('bbmax') || (low ? (webgl2 ? 960 : 1280) : 2560));
      const BB = RN_TIER === 'lite' && webgl2 ? Math.min(960, requestedBB) : requestedBB;
      const k = Math.min(1, BB / (vw * dpr), BB * 9 / 16 / (vh * dpr));
      // Ultra-Lite caps bbmax at 720 in mode.js; Lite WebGL2 caps at 960. Other tiers retain their existing defaults.
      // Even sizes: the layer keeps width and height even (host/win32.c). At k = 1 the canvas gets exactly
      // back buffer / dpr CSS pixels, centred, so one back-buffer pixel is one device pixel; k < 1: Chrome scales it up.
      const bw = 2 * Math.floor(vw * dpr * k / 2), bh = 2 * Math.floor(vh * dpr * k / 2);
      m.ENV.RN_SCREEN = `${bw}x${bh}`;
      if (k === 1 && !turned) Object.assign(document.getElementById('screen').style, { width: `${bw / dpr}px`, height: `${bh / dpr}px`, margin: 'auto' });
      line(`screen: window ${innerWidth}x${innerHeight} css${home ? `, home screen ${screen.width}x${screen.height}` : ''}, dpr ${dpr}, k ${k.toFixed(3)}, back buffer ${m.ENV.RN_SCREEN}`);
      // web/mode.js: the original mode turns the native bridges off too (?env= still wins)
      m.ENV.RN_MODE = RN_MODE;
      if (RN_MODE === 'original') {
        Object.assign(m.ENV, RN_ORIGINAL_ENV);
        // Phones (OWNER 2026-11-15: "NO en 4:3"): the game's own HUD at the edges of the wide screen (host/d3d9.c, RN_HUD unset);
        // web/touch.js keeps its side groups clear of the notch.
        if (RN_PHONE) { delete m.ENV.RN_HUD; m.ENV.RN_FESIDE = '0'; }   // the in-race menus stay centred: the touch buttons own the margins
      } else m.ENV.RN_WALLSOFTEN = '1'; // 0x46bae0: remove the remaster's grazing wall rebound
      line(`mode: ${RN_MODE} (F4 switches)`);
      // ?fps=30: the host frame pacer targets 30 fps (web/mode.js degradation switches; ?fx=0 is read there)
      if (RN_Q.get('fps') === '30') m.ENV.RN_FPS = '30';
      // host/files.c: the cache of fetched pieces (256 MB elsewhere). Phones: 96 MB, enough for the boot hint, one track and the cars (wasm break 1342 MB with 16 MB, 1523 with 256 on desktop, loadcap 2026-11-18); an iPhone tab dies near 1.5 GB.
      if (RN_LOW_TIER) { m.ENV.RN_RANGEMB = '32'; m.ENV.RN_NPRE = '2'; }   // ?env= below can override (32 MB keeps 4 MB whole-file reads, saves 64 MB on 3 GB iPhones)
      // host/files.c: helper threads bring what this entry always reads (web/entry_hint.tsv) while the engine boots and the menus pass; then each track's race load and the cars.
      m.ENV.RN_PREFETCH = 'boot';
      if (RN_Q.get('fx') === '0' || RN_Q.get('fps') === '30') line(`lite: fx ${RN_Q.get('fx') === '0' ? 'off' : 'on'}, fps ${RN_Q.get('fps') === '30' ? 30 : 60}`);
      // ?env=RN_TRACE=1,RN_API=Present: the debug switches of the native build
      for (const kv of (RN_Q.get('env') || '').split(',').filter(Boolean)) {
        const k = kv.indexOf('=');
        m.ENV[k < 0 ? kv : kv.slice(0, k)] = k < 0 ? '1' : kv.slice(k + 1);
      }
      // Keep the renderer and host on the same tier; Ultra-Lite's budget cannot be undone by ?env=.
      m.ENV.RN_TIER = RN_TIER;
      if (RN_TIER === 'ultralite') { m.ENV.RN_FPS = '30'; m.ENV.RN_LIMSLEEP = '1'; }
      // ?ai=0: rivals drive the shipped skill records, no nervous, clean or aggressive personalities (host/rivals.c). Read at each race.
      if (RN_Q.get('ai') === '0') m.ENV.RN_AI = '0';
      // ?trafyield=0: traffic does not move aside for the player closing from behind (host/rivals.c traffic_tick)
      if (RN_Q.get('trafyield') === '0') m.ENV.RN_TRAFYIELD = '0';
      // ?rivalopen=0: Free Run rivals stay on the start grid until the 10 s respawn rules move them (host/free.c free_respawn)
      if (RN_Q.get('rivalopen') === '0') m.ENV.RN_RIVALOPEN = '0';
      // ?pool=1 (OWNER 2026-11-03): the car pool: neon puddle, liveries, personas, warm car light (host/rivals.c, web/gpu.js livery). Test only:
      // the launcher stopped sending it with the WORLD retirement (OWNER 2026-11-17).
      if (RN_Q.get('pool') === '1') { m.ENV.RN_POOL = '1'; m.ENV.RN_TRAFMODELS = '1'; m.ENV.RN_TRAFREFILL = '1'; m.ENV.RN_FREETMOVE = '0'; }
      // Verbose C-host diagnostic loggers: off by default in production; enable with ?debuglog=1 or individually via ?env=...
      if (RN_Q.get('debuglog') === '1') {
        for (const k of ['RN_JCLOG', 'RN_FREELOG', 'RN_AILOG', 'RN_RESETLOG', 'RN_HORNLOG', 'RN_FEELLOG'])
          if (!(k in m.ENV)) m.ENV[k] = '1';
      }
      // ?hornfix=1: no traffic honk from a parked, undrawn or just-recycled car (host/horn.c)
      if (RN_Q.get('hornfix') === '1') m.ENV.RN_HORNFIX = '1';
      // ?aistuck=1: rivals count as stuck after 1.5 s under 3 m/s, not 0.4 s under 5 m/s (host/rivals.c ai_tune)
      if (RN_Q.get('aistuck') === '1') m.ENV.RN_AI_STUCK = '1';
      // Shipped rear grip assist by default (OWNER 2026-10-31: the feel must be the original's); ?handling=1: the 0.18 cap (host/rivals.c)
      if (RN_Q.get('handling') !== '1') m.ENV.RN_HANDLING = '0';
      // Traffic (host/rivals.c): ?trafmodels=1 bus, ambulance, fire truck on any track; ?trafrefill=1 traffic_refill in place of free_tmove;
      // ?traffic=<n> free mode's traffic count, x1.5 = cars, 23 at most with 6 rivals (0x4322a0)
      if (RN_Q.has('trafmodels')) m.ENV.RN_TRAFMODELS = RN_Q.get('trafmodels');
      if (RN_Q.get('trafrefill') === '1') { m.ENV.RN_TRAFREFILL = '1'; m.ENV.RN_FREETMOVE = '0'; }
      if (RN_Q.has('traffic')) m.ENV.RN_FREETRAFFIC = RN_Q.get('traffic');
      // Always on: it fills rn_fe, which the curtain, touch layouts, @-gated ?keys= and F3's briefing check read (host/input.c
      // cheat_briefing), and an F10 session then shows the menus and files of a normal play (tools/playindex.py). Lines only on a change.
      if (!('RN_FLOWLOG' in m.ENV)) m.ENV.RN_FLOWLOG = '1';
      // ?keys=: an RN_KEYS script (host/input.c; it holds commas, so not in ?env=), e.g. a tools/completion.py row
      const keys = RN_Q.get('keys');
      if (keys) m.ENV.RN_KEYS = keys;
      // ?jump=5:1201,6:1304: RN_JUMP (host/input.c). On Quick Race, each race of the list starts at once (mode:track;
      // 0 circuit, 1 sprint, 2 lap KO, 3 free run, 5 drag, 6 drift), the next one when a race comes back to the menu
      const jump = RN_Q.get('jump');
      if (jump) m.ENV.RN_JUMP = jump;
      // ?start=menu|career (OWNER 2026-11-16, WORLD retired 2026-11-17): the launcher's entries (web/launcher.js JUGAR, CARRERA). The game's own Accept takes the
      // player there (RN_KEYS, host/input.c) under the launcher's curtain (web/index.html), so no menu is ever seen moving by itself. Without ?start= no key is scripted.
      // The intro movies and the splash are gone (PATCH 0x4de395, tools/recomp/patches_launcher.py), so the profile screen is first: Enter 1.5 s after it shows,
      // then twice more 1.2 s apart unless the main menu is already up (the game loads the last profile; a tap is dropped once MU_Main_PC shows).
      // career: one UP on the main menu (the cursor starts on Quick Race, docs/re/frontend_menu.md:29; tools/completion.py:34), then Enter = Go Underground. ?keys= or ?jump= take over.
      if (START && !keys && !jump) {
        // The two retries wait 1.2 s each (3 s each cost 6 s of every entry, log 2026-11-16: the main menu was up 50 ms after the first Enter).
        const menu = '800@=MU_UG_NewOrLoad_PC2:RETURN,1200@!MU_Main_PC:RETURN,1200@!MU_Main_PC:RETURN';
        if (DEST === 'career') m.ENV.RN_KEYS = menu + ',800@=MU_Main_PC:UP,800@=MU_Main_PC:RETURN';
        else m.ENV.RN_KEYS = menu + ',3000@!MU_Main_PC:RETURN';
      }
      // ?carlook=0: the car paint as car.efx draws it (host/sm1.c clearcoat bridge off), 2003: also at the shipped strength,
      // 1: the clearcoat (OWNER: flat), 2: the sharp clearcoat candidate, 3 (default): live, the 2003 strength with contrast
      // ?steer=pad: the keyboard steers through the game's gamepad model (PATCH 0x460a80, host/win32.c RN_STEER)
      if (RN_Q.get('steer') === 'pad') m.ENV.RN_STEER = 'pad';
      // ?career=normal: the Underground as shipped, events open one by one (unlock patches off: PATCH 0x63b370 caves read
      // [0x7677ac] alone, debug byte 0x735ec1 = 0; host/win32.c RN_UNLOCK). Default: everything unlocked
      if (RN_Q.get('career') === 'normal') m.ENV.RN_UNLOCK = '0';
      // ?cardetail=0: the car paint without the occlusion and grime terms (host/sm1.c car_ps_detail); =split: right half only
      const cd = RN_Q.get('cardetail');
      if (cd !== null) m.ENV.RN_CARDETAIL = cd;
      // ?roadrefl=game|sq|cube|off: how strongly the road reflects. sq / cube: the reflection weight (vertex alpha x texture alpha) squared /
      // cubed (host/sm1.c); off: the game's own ROADREFLECTION level 1, no mirrored world (PATCH 0x410c1b, host/win32.c). Read at boot.
      // Remaster default is off, a dry road (OWNER 2026-10-30: too much reflection); Original mode sets game (web/mode.js).
      m.ENV.RN_ROADREFL = RN_Q.get('roadrefl') ?? 'off';
      // ?car=<name|index>: the player's car in every race is a career rival's car (RN_CAR, host/free.c player_car; ?car=list logs the choices)
      const car = RN_Q.get('car');
      if (car) m.ENV.RN_CAR = car;
      const look = RN_Q.get('carlook');
      if (look !== null) m.ENV.RN_CARLOOK = look;
    }],
  });
  telem = startTelemetry(M, t0, s => line(s));
  const onFrame = (s, t, ms) => { if (s.present && RN_APP.state === 'load') { if (!CURTAIN) arrive(); else if (!arrive.t) arrive.t = setTimeout(arrive, 45000); /* a trip that stalls must not leave the curtain down */ } telem?.frame?.(s, t, ms); };
  startGpu(M, document.getElementById('screen'), s => line(s, 'api'), onFrame).catch(e => line('gpu.js: ' + e.message, 'stop'));
  // RN_STEERLOG (host/input.c): also each key at the page and each present's GPU completion, on the page's clock
  const input = startInput(M, document.getElementById('screen'), /RN_STEERLOG/.test(location.search) ? s => line(s) : null);
  startPad(input);                          // web/pad.js: a gamepad into the same ring
  startTouch(input);                        // web/touch.js: the touch overlay (coarse pointer or ?touch=1) into the same ring
  startNameKeys(input);                     // web/namekeys.js: on-screen keys for the profile name (touch devices)
  startTune(M);
  startAudio(M, s => line(s)).catch(e => line('audio.js: ' + e.message, 'stop'));
  window.RN_M = M;                          // for checks from the console or tools/webcheck.mjs
  // The loading line: megabytes the prefetch has brought of what it was asked (host/files.c rn_load, KB), while the curtain or the gate is up.
  const loadTick = setInterval(() => {
    if (RN_APP.state !== 'load') { if (RN_APP.state !== 'check') clearInterval(loadTick); return; }
    const a = M._rn_load_addr?.() >>> 0, v = a ? new Uint32Array(M.HEAPU8.buffer, a, 2) : null;
    if (!v || !v[0]) return;
    if (v[1] < v[0]) RN_APP.say(`${RN_TR('Cargando')} ${v[1] >> 10} / ${v[0] >> 10} MB`, v[1] / v[0]);
    else RN_APP.say(RN_TR('Arrancando…'), 1);
  }, 200);
  // Memory line when it moves by 16 MB or more (host/win32.c rn_mem_mb): what an iPhone tab (~1.5 GB, then iOS kills it) holds.
  let memLast = '';
  memTick = setInterval(() => {
    if (RN_APP.state === 'stop') { clearInterval(memTick); memTick = 0; return; }
    const v = [0, 1, 2].map(k => M._rn_mem_mb(k)), key = v.map(x => x >> 4).join();
    if (key !== memLast) { memLast = key; line(`mem: wasm break ${v[0]} MB (guest 384 untouched until used), guest heap ${v[1]} MB, guest virtual ${v[2]} MB`); }
  }, 2000);
})();
