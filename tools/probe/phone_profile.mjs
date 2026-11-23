// CPU profile of every worker of the game page on a USB Android phone (Chrome remote debugging).
// Usage: node tools/probe/phone_profile.mjs [secs=20] [urlPrefix=http://localhost:5185]
// Needs: adb reverse tcp:5185 tcp:5185 (serve), the wasm built with RN_PROF=1 (names f_<hex guest address>).
// Raw .cpuprofile per worker -> build/phone_prof/; top 25 functions by self time per worker on stdout.
import { execSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';

const secs = Number(process.argv[2] || 20), prefix = process.argv[3] || 'http://localhost:5185';
execSync('adb forward tcp:9333 localabstract:chrome_devtools_remote');
const tabs = await (await fetch('http://127.0.0.1:9333/json')).json();
const tab = tabs.find(t => t.type === 'page' && t.url.startsWith(prefix));
if (!tab) { console.error('no page at ' + prefix + '; open tabs: ' + tabs.map(t => t.url).join(' ')); process.exit(1); }
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
let id = 0; const pending = new Map(), workers = new Map();
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Target.attachedToTarget' && m.params.targetInfo.type === 'worker') workers.set(m.params.sessionId, m.params.targetInfo);
};
const send = (method, params = {}, sessionId) => new Promise(ok => { const i = ++id; pending.set(i, ok); ws.send(JSON.stringify({ id: i, method, params, ...(sessionId && { sessionId }) })); });

await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
await new Promise(r => setTimeout(r, 1500));   // attachedToTarget events for the existing workers
console.log(`page ${tab.url}\nworkers attached: ${workers.size}; profiling ${secs} s`);
for (const s of workers.keys()) {
  await send('Profiler.enable', {}, s);
  await send('Profiler.setSamplingInterval', { interval: 1000 }, s);
  await send('Profiler.start', {}, s);
}
await new Promise(r => setTimeout(r, secs * 1000));
mkdirSync('build/phone_prof', { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
let k = 0;
for (const s of workers.keys()) {
  const p = (await send('Profiler.stop', {}, s))?.result?.profile;
  if (!p) continue;
  const file = `build/phone_prof/${stamp}.w${k++}.cpuprofile`;
  writeFileSync(file, JSON.stringify(p));
  const byId = new Map(p.nodes.map(n => [n.id, n])), self = new Map();
  // sample i lasts timeDeltas[i+1] (the gap to the next sample); real time, not count, so a blocked/slow sample weighs what it took
  let total = 0;
  p.samples.forEach((nid, i) => {
    const dt = (p.timeDeltas[i + 1] ?? p.timeDeltas[i] ?? 1000) / 1000;
    const cf = byId.get(nid).callFrame, name = cf.functionName || '(anon)';
    const key = name + (cf.url ? '' : '');
    self.set(key, (self.get(key) || 0) + dt); total += dt;
  });
  const idle = (self.get('(idle)') || 0), prog = self.get('(program)') || 0;
  console.log(`\n== ${workers.get(s).url.split('/').pop()} ${file}: ${p.samples.length} samples, ${total.toFixed(0)} ms, idle ${idle.toFixed(0)} ms, (program) ${prog.toFixed(0)} ms`);
  for (const [name, ms] of [...self].filter(([n]) => n !== '(idle)').sort((a, b) => b[1] - a[1]).slice(0, 25)) {
    const m = /^f_([0-9a-f]{6,8})$/.exec(name);
    console.log(`${ms.toFixed(0).padStart(7)} ms ${(100 * ms / total).toFixed(1).padStart(5)}%  ${name}${m ? `  (exe 0x${m[1]})` : ''}`);
  }
}
ws.close();
process.exit(0);
