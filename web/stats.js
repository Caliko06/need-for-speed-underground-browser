// Always-on frame stats (plan row Q2). Reads the host's ring of the last 256 Presents (host/d3d9.c rn_frame_ring, export
// _rn_frame_ring_addr) every 5 s and keeps 24 windows: p50/p95/p99 frame ms, stutters (> 1.5x the target frame time), mean gpu wait.
// window.rnStats = { windows, last(), line() } is what a quality controller reads. ?stats=1 shows a thin corner overlay.
window.rnStats = { windows: [], last() { return this.windows[this.windows.length - 1] || null; }, line() { const w = this.last(); return w ? `fps ${w.fps} p95 ${w.p95} stutters ${w.stutters}` : ''; } };
function startStats(M) {
  const ring = M._rn_frame_ring_addr(), WIN_MS = 5000, KEEP = 24;
  // Same place boot.js sets RN_FPS: ?fps=30 and the ultralite tier run the pacer at 30 fps.
  const target = () => (RN_Q.get('fps') === '30' || RN_TIER === 'ultralite') ? 1000 / 30 : 1000 / 60;
  let seen = 0, box = null;
  if (RN_Q.get('stats') === '1') {
    box = document.createElement('div');
    box.style.cssText = 'position:fixed;left:6px;bottom:4px;z-index:99999;font:10px/1.2 monospace;color:#fff;opacity:.4;pointer-events:none;white-space:pre';
    document.body.appendChild(box);
  }
  const tick = () => {
    const u = M.HEAPU32, f = M.HEAPF32 || new Float32Array(u.buffer), w = ring >> 2;
    const idx = u[w], n = Math.min(idx - seen, 256);
    seen = idx;
    if (n < 2) return;
    const ms = [], gpu = [], lim = 1.5 * target();
    for (let k = 1; k <= n; k++) { const o = w + 4 + (((idx - k) & 255) << 2); ms.push(f[o]); gpu.push(f[o + 1]); }
    const s = ms.slice().sort((a, b) => a - b), q = p => s[Math.min(s.length - 1, Math.floor(p * s.length))];
    const sum = ms.reduce((a, b) => a + b, 0);
    const win = { t: Math.round(performance.now() / 1000), frames: n, fps: +(1000 * n / sum).toFixed(1), p50: +q(.5).toFixed(1), p95: +q(.95).toFixed(1), p99: +q(.99).toFixed(1),
      stutters: ms.filter(x => x > lim).length, gpuMs: +(gpu.reduce((a, b) => a + b, 0) / n).toFixed(2), target: +target().toFixed(1) };
    const W = window.rnStats.windows; W.push(win); if (W.length > KEEP) W.shift();
    if (box) box.textContent = `${win.fps} fps  p95 ${win.p95} ms  stutters ${win.stutters}`;
  };
  setInterval(() => { if (RN_APP.state !== 'stop') tick(); }, WIN_MS);
}
