// One headless Chrome run of the page on 5180: prints the page log when it stops (or after the timeout)
// and saves a screenshot of the page.
// Usage: node tools/webcheck.mjs [url] [seconds] [screenshot.png] [keys]
// keys: "20:Enter,23:ArrowDown" = at that second, a tap of that KeyboardEvent.code on the canvas;
// "60:KeyW+6" holds it 6 seconds (released on the first check after that).
// node tools/webcheck.mjs --route: the regression route; exit 0 = PASS. It grows with each milestone met.
import { execSync, spawn } from 'node:child_process';
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Title -> profile "asas" -> Quick Race, Olympic Square. Since the title movie really plays (MMX, 2026-10-25) the menus
// land later: the last Enters (58-74 s) keep the path going; during the load they do nothing. PASS: no STOP, the race starts (its HUD at the window size: the
// device is made at the screen size since PATCH 0x408a24, so no Reset comes) and runs `hold` more seconds. M8.5: the page is 1920x1080 device pixels (dpr 1), so the
// race HUD and every present are 1920x1080.
const ROUTE = { keys: '20:Enter,23:Enter,26:ArrowRight,29:Enter,32:Enter,35:Enter,38:Enter,44:Enter,50:Enter,58:Enter,66:Enter,74:Enter',
  marker: /d3d9 race HUD 1920x1080 /, present: /present 1920x1080/, view: { width: 1920, height: 1080 }, hold: 20, secs: 150,
  shot: 'build/route.png' };
const route = process.argv[2] === '--route';
const arg = route ? [] : process.argv.slice(2);
let url = process.env.RN_URL || arg[0] || 'http://127.0.0.1:5180/?play=1';   // RN_URL: a window's own server (5181-5183), also for --route
if (!url.includes('?')) url += '?play=1';    // a bare address is the game too; ?play=1 stays harmless
const secs = route ? ROUTE.secs : Number(arg[1] || 120);
const shot = route ? ROUTE.shot : arg[2] || 'build/webcheck.png';
const keys = ((route ? ROUTE.keys : arg[3]) || '').split(',').filter(Boolean).map(k => k.split(':')).map(([t, c]) => ({ t: +t, code: c.split('+')[0], hold: +(c.split('+')[1] || 0) }));
// Each run starts from a fresh copy of the OWNER's save (tools/serve.py gives headless Chrome build/save-headless).
// RN_KEEP_SAVE=1 keeps the last run's: a second run is a page reload on what the first one saved (block 3 gate).
if (!process.env.RN_KEEP_SAVE) rmSync('build/save-headless', { recursive: true, force: true });
// RE-NFSU's own CDP port: another repo's webcheck held 9333 (127.0.0.1) and once took this repo's run into its Chrome,
// which died with its run (2026-10-25, the page stopped at 61 s).
const port = Number(process.env.RN_CDP_PORT || 9381);
const profileDir = process.env.RN_PROFILE_DIR || mkdtempSync(join(tmpdir(), 'rn-'));   // RN_PROFILE_DIR: a profile kept between runs (a warm HTTP and code cache)
// RN_X11=1 (Pod, AGENTS.md): headless Chrome on Linux gets SwiftShader, so Chrome runs on an Xvfb DISPLAY with Vulkan,
// which gives WebGPU the NVIDIA. The user agent still says HeadlessChrome: tools/serve.py tells test runs apart by it.
const x11 = process.env.RN_X11 ? ['--ozone-platform=x11', '--enable-features=Vulkan', '--ignore-gpu-blocklist', '--no-sandbox',
  '--user-agent=Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome webcheck'] : ['--headless=new'];
const chrome = spawn(process.env.RN_CHROME || '/Users/angeldamian/.local/bin/chrome-bot', [
  ...x11, `--remote-debugging-port=${port}`, `--user-data-dir=${profileDir}`,
  '--no-first-run', '--enable-unsafe-webgpu', '--mute-audio', '--window-size=1280,1100', 'about:blank'], { stdio: 'ignore' });
// Each profile is ~330 MB: 107 left behind filled 29 GB of the Mac. Removed on every exit.
process.on('exit', () => { chrome.kill('SIGKILL'); if (!process.env.RN_PROFILE_DIR) try { rmSync(profileDir, { recursive: true, force: true }); } catch {} });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tabs;
for (let i = 0; i < 50 && !tabs; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); } }
const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pending = new Map(); const errors = [];
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map(a => a.value ?? a.description).join(' '));
};
const send = (method, params = {}, sessionId) => new Promise(r => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params, sessionId })); });
await send('Runtime.enable');
// RN_PROFILE=start:secs: a CPU sampling profile of every worker (the game runs in them) from second `start` for `secs`
// seconds -> build/profile.txt, functions by self and total time. Names need a web build with RN_PROF=1.
const prof = process.env.RN_PROFILE?.split(':').map(Number), workers = new Map();
const profTop = Number(process.env.RN_PROFILE_TOP || 40);   // functions listed per worker and list
if (prof) {
  const onmsg = ws.onmessage;
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.method === 'Target.attachedToTarget') workers.set(m.params.sessionId, m.params.targetInfo); onmsg(e); };
  await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
}
// RN_NETLOG=file: each game file the page reads (first request per path, any worker), with the page second -> file.
// Which files a menu path loads, without RN_TRACE (its log slows the game down so much that timed keys miss).
const netlog = process.env.RN_NETLOG;
if (netlog) {
  writeFileSync(netlog, '');
  const seen = new Set(), onmsg = ws.onmessage, n0 = Date.now();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.method === 'Target.attachedToTarget') send('Network.enable', {}, m.params.sessionId);
    if (m.method === 'Network.requestWillBeSent') {
      const u = decodeURIComponent(new URL(m.params.request.url).pathname);
      if (u.startsWith('/game/') && !seen.has(u)) { seen.add(u); appendFileSync(netlog, `${((Date.now() - n0) / 1000).toFixed(1)} ${u.slice(6)}\n`); }
    }
    onmsg(e);
  };
  await send('Network.enable');
  await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
}
let profState = 0;
const afterHud = process.env.RN_AFTER_HUD ? Number(process.env.RN_AFTER_HUD) : -1;
let hudAt = 0, untilAt = 0, everyN = 0;
const shotEvery = Number(process.env.RN_SHOT_EVERY || 0);
const until = process.env.RN_UNTIL && { re: new RegExp(process.env.RN_UNTIL.replace(/@\d+$/, '')), s: Number(process.env.RN_UNTIL.match(/@(\d+)$/)?.[1] ?? 5) };
async function profile() {
  if (profState === 0 && Date.now() - t0 >= prof[0] * 1000) {
    profState = 1;
    workers.set(undefined, { url: 'page' });       // the page's own thread (gpu.js runs the frames there)
    for (const s of workers.keys()) { await send('Profiler.enable', {}, s); await send('Profiler.setSamplingInterval', { interval: 250 }, s); await send('Profiler.start', {}, s); }
  } else if (profState === 1 && Date.now() - t0 >= (prof[0] + prof[1]) * 1000) {
    profState = 2;
    let out = `CPU profile ${prof[1]} s from ${prof[0]} s, ${url}; per worker: samples, then functions by self and total %\n`;
    for (const s of workers.keys()) {
      const p = (await send('Profiler.stop', {}, s))?.profile;
      if (!p) continue;
      // RN_PROFILE_RAW=prefix: also each thread's raw .cpuprofile (samples + timeDeltas: slice one slow frame).
      if (process.env.RN_PROFILE_RAW) writeFileSync(`${process.env.RN_PROFILE_RAW}.${(s || 'page').slice(0, 8)}.cpuprofile`, JSON.stringify(p));
      const byId = new Map(p.nodes.map(n => [n.id, n])), parent = new Map();
      for (const n of p.nodes) for (const c of n.children || []) parent.set(c, n.id);
      const self = new Map(), total = new Map(), n = p.samples.length;
      for (const id of p.samples) {
        const name = k => byId.get(k).callFrame.functionName || '(anon)';
        self.set(name(id), (self.get(name(id)) || 0) + 1);
        const seen = new Set();
        for (let k = id; k; k = parent.get(k)) seen.add(name(k));
        for (const x of seen) total.set(x, (total.get(x) || 0) + 1);
      }
      const idle = (self.get('(idle)') || 0) + (self.get('(program)') || 0);
      if (n - idle < 200) continue;
      const pct = v => (100 * v / n).toFixed(1).padStart(5);
      out += `\n== ${s ? 'worker' : 'page'} ${workers.get(s).url.split('/').pop()} ${(s || '').slice(0, 8)}: ${n} samples, idle/program ${pct(idle)}%\n self:\n`;
      for (const [k, v] of [...self].sort((a, b) => b[1] - a[1]).slice(0, profTop)) out += `${pct(v)}  ${k}\n`;
      out += ' total (self + callees):\n';
      for (const [k, v] of [...total].sort((a, b) => b[1] - a[1]).slice(0, profTop)) out += `${pct(v)}  ${k}\n`;
    }
    writeFileSync('build/profile.txt', out);
    console.log('profile: build/profile.txt');
  }
}
if (route) await send('Emulation.setDeviceMetricsOverride', { ...ROUTE.view, deviceScaleFactor: 1, mobile: false });
// RN_VIEW=WxH@dpr: the page at the OWNER's window size and pixel ratio (a stop can depend on the back buffer size).
const view = process.env.RN_VIEW?.match(/^(\d+)x(\d+)@([\d.]+)$/);
// RN_MOBILE=1 (with RN_VIEW): a phone, with touch and a coarse pointer, so web/touch.js and the phone paths turn on.
const mobile = process.env.RN_MOBILE === '1';
if (view) await send('Emulation.setDeviceMetricsOverride', { width: +view[1], height: +view[2], deviceScaleFactor: +view[3], mobile });
if (mobile) await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
// RN_REC=dir: every frame the compositor makes (CDP screencast, jpeg) -> dir/<page ms>.jpg; tools/recvideo.sh turns them
// into a video with the real frame times (A/B against the Wine reference recording, tools/wine/rec.sh).
const rec = process.env.RN_REC;
if (rec) {
  mkdirSync(rec, { recursive: true });
  const onmsg = ws.onmessage;
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.method === 'Page.screencastFrame') {
      writeFileSync(join(rec, `${Math.round(m.params.metadata.timestamp * 1000)}.jpg`), Buffer.from(m.params.data, 'base64'));
      ws.send(JSON.stringify({ id: ++id, method: 'Page.screencastFrameAck', params: { sessionId: m.params.sessionId } }));
    }
    onmsg(e);
  };
}
// RN_REC_AT=s: start that recording at second s of the page (the race start), not at load: the disk is tight.
const recAt = rec ? Number(process.env.RN_REC_AT || 0) : -1;
let recOn = false;
async function recStart() { recOn = true; await send('Page.startScreencast', { format: 'jpeg', quality: 90, everyNthFrame: 1 }); }
if (recAt === 0) await recStart();
// RN_MEASURE=file: what a run costs, as JSON: bytes over the wire by class (wasm, Speed.exe, game files, the rest), peak Chrome RSS (the whole
// process tree, wasm memory included) and peak JS heap of the page, and the page seconds of the load markers in the log.
const measure = process.env.RN_MEASURE, net = new Map(), peak = { rssMB: 0, jsHeapMB: 0 };
if (measure) {
  const onmsg = ws.onmessage;
  ws.onmessage = e => {
    const m = JSON.parse(e.data), k = (m.sessionId || '') + (m.params?.requestId || '');
    if (m.method === 'Target.attachedToTarget') send('Network.enable', {}, m.params.sessionId);
    if (m.method === 'Network.requestWillBeSent') net.set(k, { path: decodeURIComponent(new URL(m.params.request.url).pathname), enc: 0 });
    if (m.method === 'Network.loadingFinished' && net.has(k)) net.get(k).enc = m.params.encodedDataLength;
    onmsg(e);
  };
  await send('Network.enable');
  await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
  await send('Performance.enable');
}
async function sample() {
  const ps = execSync('ps -axo rss=,command=', { maxBuffer: 1 << 26 }).toString().split('\n').filter(l => l.includes(profileDir));
  const by = {};
  for (const l of ps) { const t = l.match(/--type=([\w-]+)/)?.[1] || 'browser'; by[t] = (by[t] || 0) + Number(l.trim().split(/\s+/)[0]) / 1024; }
  const tot = Object.values(by).reduce((a, b) => a + b, 0);
  if (tot > peak.rssMB) { peak.rssMB = tot; peak.byType = Object.fromEntries(Object.entries(by).map(([k, v]) => [k, Math.round(v)])); }
  const h = (await send('Performance.getMetrics'))?.metrics?.find(x => x.name === 'JSHeapUsedSize')?.value || 0;
  peak.jsHeapMB = Math.max(peak.jsHeapMB, h / 1048576);
}
// Physical footprint (macOS `footprint`, counts GPU and compressed memory, unlike RSS) of every process of the run by type, once.
function foot() {
  const by = {};
  for (const l of execSync('ps -axo pid=,command=', { maxBuffer: 1 << 26 }).toString().split('\n').filter(l => l.includes(profileDir))) {
    const t = l.match(/--type=([\w-]+)/)?.[1] || 'browser', pid = l.trim().split(/\s+/)[0];
    try { const m = execSync(`footprint -p ${pid}`, { timeout: 20000 }).toString().match(/Footprint: ([\d.]+) (KB|MB|GB)/); if (m) by[t] = (by[t] || 0) + m[1] * ({ KB: 1 / 1024, MB: 1, GB: 1024 })[m[2]]; } catch {}
  }
  return Object.fromEntries(Object.entries(by).map(([k, v]) => [k, Math.round(v)]));
}
// RN_PHONE=1: the page as a phone held sideways (844x390 at dpr 3, touch, coarse pointer): web/mode.js RN_PHONE and everything behind it.
if (process.env.RN_PHONE) {
  await send('Emulation.setDeviceMetricsOverride', { width: 844, height: 390, deviceScaleFactor: 3, mobile: true, screenOrientation: { type: 'landscapePrimary', angle: 90 } });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
}
// RN_DEVMEM=<GB>: navigator.deviceMemory as a phone reports it (boot.js picks speed_nano at <= 2 on lite tiers).
if (process.env.RN_DEVMEM) await send('Page.enable'), await send('Page.addScriptToEvaluateOnNewDocument', { source: `Object.defineProperty(Navigator.prototype, 'deviceMemory', { get: () => ${+process.env.RN_DEVMEM} })` });
await send('Page.navigate', { url });
const t0 = Date.now();
let text = '', seen = 0;
const shotFe = process.env.RN_SHOT_FE, feSeen = new Set(), feDue = [], feAt = (process.env.RN_SHOT_FE_AT || '2').split(',').map(Number);
let feN = 0;
const shotOn = process.env.RN_SHOT_ON ? new RegExp(process.env.RN_SHOT_ON, 'g') : null, onSeen = new Set(), onDue = [];
if (shotFe) mkdirSync(shotFe, { recursive: true });
const evals = (process.env.RN_EVAL || '').split(';;').filter(Boolean).map(x => ({ t: +x.split(':')[0], expr: x.slice(x.indexOf(':') + 1) }));
const taps = (process.env.RN_TAP || '').split(';;').filter(Boolean).map(x => ({ t: +x.split(':')[0], at: x.slice(x.indexOf(':') + 1) }));
while (Date.now() - t0 < secs * 1000) {
  await sleep(1000);
  // RN_EVAL="64:expr;;70:expr": at that second, run the expression in the page and print its value (a click on a page button).
  for (const e of evals.filter(e => !e.done && Date.now() - t0 >= e.t * 1000)) {
    e.done = true;
    const r = await send('Runtime.evaluate', { expression: e.expr, returnByValue: true });
    console.log(`eval ${e.t}: ${JSON.stringify(r?.result?.value ?? r?.exceptionDetails?.text)}`);
  }
  // RN_TAP="26:#touch .ok;;31:60%,40%": at that second, a real finger tap (CDP touch, so the page's own hit test decides) on the
  // middle of that selector, or at that point of the window.
  for (const e of taps.filter(e => !e.done && Date.now() - t0 >= e.t * 1000)) {
    e.done = true;
    const pc = /^([\d.]+)%,([\d.]+)%$/.exec(e.at);
    const r = await send('Runtime.evaluate', { returnByValue: true, expression: pc ? `[innerWidth*${pc[1] / 100},innerHeight*${pc[2] / 100}]`
      : `(()=>{const b=document.querySelector(${JSON.stringify(e.at)}).getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2]})()` });
    const [x, y] = r?.result?.value || [];
    if (x === undefined) { console.log(`tap ${e.t}: ${e.at} not found`); continue; }
    await send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    await sleep(90);
    await send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    console.log(`tap ${e.t}: ${e.at} at ${Math.round(x)},${Math.round(y)}`);
  }
  for (const k of keys.filter(k => !k.done && Date.now() - t0 >= k.t * 1000)) {
    k.done = true;
    await send('Runtime.evaluate', { expression: "document.getElementById('screen').focus()" });
    await send('Input.dispatchKeyEvent', { type: 'keyDown', code: k.code, key: k.code });
    if (k.hold) continue;
    await sleep(100);
    await send('Input.dispatchKeyEvent', { type: 'keyUp', code: k.code, key: k.code });
  }
  for (const k of keys.filter(k => k.done && k.hold && !k.up && Date.now() - t0 >= (k.t + k.hold) * 1000)) {
    k.up = true;
    await send('Input.dispatchKeyEvent', { type: 'keyUp', code: k.code, key: k.code });
  }
  if (recAt > 0 && !recOn && Date.now() - t0 >= recAt * 1000) await recStart();
  if (prof) await profile();
  if (measure) await sample();
  const r = await send('Runtime.evaluate', { expression: "document.getElementById('status')?.textContent + '\\n' + document.getElementById('log')?.innerText" });
  text = r?.result?.value || '';
  if (/STOP|Falta COOP/.test(text)) break;
  // RN_SHOT_FE=dir: a shot 2 s after each new front-end screen (RN_FLOWLOG "flow fe" line) -> dir/<n>_<screen>.png:
  // one frame per screen of a menu tour (garage, magazines, jukebox), at the page's size. RN_SHOT_FE_AT=2,8,20: a shot at
  // each of those seconds instead (a movie screen).
  if (shotFe) {
    for (const m of text.matchAll(/flow fe (\S+) \(frame/g)) if (!feSeen.has(m[1])) { feSeen.add(m[1]); for (const a of feAt) feDue.push({ at: Date.now() + a * 1000, fe: m[1] }); }
    for (const d of feDue.filter(d => !d.done && Date.now() >= d.at)) {
      d.done = true;
      const fe = [...text.matchAll(/flow fe (\S+) \(frame/g)].pop()?.[1] || d.fe;   // the screen on now, not the one that asked
      const main = fe.split(',').find(x => !/^(GarageMain|PC_|Chyron|MU_HorizontalBrowserBack|MU_QRBackground|MU_MPBackground|background)/.test(x)) || fe.split(',')[0];
      const p = await send('Page.captureScreenshot', { format: 'png' });
      if (p?.data) writeFileSync(join(shotFe, `${String(++feN).padStart(2, '0')}_${main.replace('.fng', '')}.png`), Buffer.from(p.data, 'base64'));
    }
  }
  if (route && !seen && ROUTE.marker.test(text)) seen = Date.now();
  if (measure && seen && !peak.footMB && Date.now() - seen >= (ROUTE.hold - 8) * 1000) peak.footMB = foot();   // in the race, before the hold ends
  if (seen && Date.now() - seen >= ROUTE.hold * 1000) break;
  // RN_AFTER_HUD=s: the shot s seconds after the race HUD appears (the race starts at a different second each run, so a
  // shot at a fixed page time shows a different moment: camera-dependent effects then look like regressions).
  if (afterHud >= 0 && !hudAt && /d3d9 race HUD /.test(text)) hudAt = Date.now();
  if (hudAt && Date.now() - hudAt >= afterHud * 1000) break;
  // RN_SHOT_EVERY=s (with RN_AFTER_HUD): a shot every s seconds of the race -> <shot>.d/<NN>.png, to catch passing cars.
  if (hudAt && shotEvery && Date.now() - hudAt >= (everyN + 1) * shotEvery * 1000) {
    const p = await send('Page.captureScreenshot', { format: 'png' });
    mkdirSync(`${shot}.d`, { recursive: true });
    if (p?.data) writeFileSync(`${shot}.d/${String(++everyN).padStart(2, '0')}.png`, Buffer.from(p.data, 'base64'));
  }
  // RN_SHOT_ON=regex: shots 0, 2 and 4 s after each new distinct match in the page log (e.g. "JC f\\d+ mode [67]", the jump
  // camera) -> <shot>.on/<NN>_<s>.png, at most 30 lines.
  if (shotOn) {
    for (const m of text.matchAll(shotOn)) if (!onSeen.has(m[0]) && onSeen.size < 30) { onSeen.add(m[0]); for (const a of [0, 2, 4]) onDue.push({ at: Date.now() + a * 1000, n: onSeen.size, a }); }
    for (const d of onDue.filter(d => !d.done && Date.now() >= d.at)) {
      d.done = true;
      const p = await send('Page.captureScreenshot', { format: 'png' });
      mkdirSync(`${shot}.on`, { recursive: true });
      if (p?.data) writeFileSync(`${shot}.on/${String(d.n).padStart(2, '0')}_${d.a}.png`, Buffer.from(p.data, 'base64'));
    }
  }
  // RN_UNTIL=regex[@s]: stop s seconds (default 5) after the page log first matches (e.g. "RN_JUMP: done").
  if (until && !untilAt && until.re.test(text)) untilAt = Date.now();
  if (untilAt && Date.now() - untilAt >= until.s * 1000) break;
}
await sleep(500);   // let the last frame reach the canvas
const png = await send('Page.captureScreenshot', { format: 'png' });
if (png?.data) { writeFileSync(shot, Buffer.from(png.data, 'base64')); console.log(`screenshot: ${shot}`); }
console.log(`[${((Date.now() - t0) / 1000).toFixed(1)} s]`);
console.log(text);
if (errors.length) console.log('page errors:\n' + errors.join('\n'));
if (measure) {
  // Page seconds of the load markers come from the server's copy of the page log (build/webcheck.log, one block per page load).
  const wl = existsSync('build/webcheck.log') ? readFileSync('build/webcheck.log', 'utf8') : '';
  const at = re => { const m = wl.match(new RegExp('^([0-9.]+) ' + re, 'm')); return m ? Number(m[1]) : null; };
  const res = (await send('Runtime.evaluate', { returnByValue: true, expression: `JSON.stringify(performance.getEntriesByType('resource').filter(e => /speed\\.(wasm|js)$|Speed\\.exe$/.test(e.name)).map(e => [e.name.split('/').pop(), +e.startTime.toFixed(0), +e.responseEnd.toFixed(0)]))` }))?.result?.value;
  const cls = { wasm: 0, exe: 0, game: 0, gameFiles: new Set(), other: 0 };
  for (const r of net.values()) {
    if (r.path.endsWith('.wasm')) cls.wasm += r.enc; else if (r.path.endsWith('Speed.exe')) cls.exe += r.enc;
    else if (r.path.startsWith('/game/')) { cls.game += r.enc; cls.gameFiles.add(r.path); } else cls.other += r.enc;
  }
  const mb = v => Math.round(v / 1048576 * 10) / 10;
  writeFileSync(measure, JSON.stringify({ url, secs: (Date.now() - t0) / 1000, wire_MB: { wasm: mb(cls.wasm), exe: mb(cls.exe), game: mb(cls.game), other: mb(cls.other) },
    gameFiles: cls.gameFiles.size, requests: net.size, peakRssMB: Math.round(peak.rssMB), rssByType: peak.byType, peakJsHeapMB: Math.round(peak.jsHeapMB), footMB: peak.footMB,
    resourceMs: res ? JSON.parse(res) : null,
    top: Object.entries([...net.values()].reduce((o, r) => { const p = r.path.replace(/^(\/remaster\/.*\/).*/, '$1*'); (o[p] ||= [0, 0]); o[p][0] += r.enc; o[p][1]++; return o; }, {})).sort((a, b) => b[1][0] - a[1][0]).slice(0, 12).map(([p, [n, k]]) => `${(n / 1048576).toFixed(1)} MB x${k} ${p}`),
    pageSec: { screenLine: at('screen:'), exeLoaded: at('Speed.exe loaded'), firstPresent: at('d3d9 first Present'), raceHud: at('d3d9 race HUD') } }, null, 1) + '\n');
  console.log('measure: ' + measure);
}
chrome.kill('SIGKILL');   // headless Chrome can ignore SIGTERM and keep the game (and its sound) running
if (route) {
  const why = /STOP/.test(text) ? 'a STOP' : errors.length ? 'a page error' : !seen ? `no ${ROUTE.marker} in ${secs} s`
    : Date.now() - seen < ROUTE.hold * 1000 ? 'ended early' : !ROUTE.present.test(text) ? `no ${ROUTE.present}` : '';
  console.log(why ? `ROUTE FAIL: ${why}` : `ROUTE PASS: race started at ${((seen - t0) / 1000).toFixed(0)} s and ran ${ROUTE.hold} s, present 1920x1080`);
  process.exit(why ? 1 : 0);
}
process.exit(0);
