// Quality follows measurement (plan rows Q4 + Q5, OWNER 2026-11-22). Sacrifice order: resolution > effects > fps > content.
// Reads each 5 s window of web/stats.js ('rn-stats') while in a race. Overload = p95 > 1.15x the frame budget or >= 3 stutters, 2 windows
// running (low-pass + hysteresis, as Intel DRR / Unity Dynamic Resolution); a p95 that climbs >= 15 % over 4 windows (phones throttle after
// minutes, arXiv 1904.09814) counts at once. Headroom = p95 < 0.7x budget, no stutters, 6 windows running.
// Ladder (overload goes down it, one action per decision, then 2 windows of rest; headroom undoes the last action, one per streak):
//   res   next race at 0.8x per axis (min 400x240), host _rn_request_screen, applied at the race boundary
//   blur  the game's blur off, live (web/tune.js rnBlur)
//   fx    boot-only effects off at the next boot (stored fx 0, web/mode.js)
//   fps   60 -> 30 live (host _rn_set_fps)
//   tier  next boot one tier down (content gates)
// Never above the ceiling of the static detection (tier) / boot rule (RN_CEIL). The result is kept per device in localStorage 'rn_quality'
// (web/mode.js reads it before static detection). ?adapt=0 turns all of it off.
const RN_LADDER = ['res', 'blur', 'fx', 'fps', 'tier'];
function startQuality(M, say, webgpu) {
  if (!RN_ADAPT) return;
  const S = new URLSearchParams(RN_SEARCH), MIN_W = 400, MIN_H = 240, STEP = 0.8, OVER_N = 2, HEAD_N = 6, REST = 2, TREND_N = 4;
  const even = x => 2 * Math.floor(x / 2);
  const decisions = [], stack = [];            // stack: applied actions, last = next to undo
  const ceil = window.RN_CEIL || { w: 1280, h: 720 };
  const size = n => ({ w: even(Math.max(MIN_W, ceil.w * Math.pow(STEP, n))), h: even(Math.max(MIN_H, ceil.h * Math.pow(STEP, n))) });
  const [bw0] = String(M.ENV.RN_SCREEN || '').split('x').map(Number);
  let resN = 0; while (bw0 && size(resN).w > bw0 + 2 && resN < 12) resN++;
  // ceiling tier = static detection without the stored value (an address ?tier= is its own ceiling)
  const staticTier = rnDetectTier(webgpu, true);
  const tierIdx = t => RN_TIERS.indexOf(t), minTier = tierIdx(staticTier);
  let tier = RN_TIER;
  const fxFixed = S.has('fx') || RN_MODE === 'original' || tierIdx(staticTier) < 2;   // no effects to give back and forth
  let fx = RN_Q.get('fx') !== '0' && RN_MODE !== 'original';
  const fpsFixed = S.has('fps') || RN_TIER === 'ultralite';
  let fps = RN_Q.get('fps') === '30' || RN_TIER === 'ultralite' ? 30 : 60;
  const fpsCeil = fpsFixed ? fps : (RN_TIERS.indexOf(staticTier) <= 1 ? 30 : 60);
  const tierFixed = RN_TIERS.includes(RN_TIER_OVERRIDE);
  // what the stored boot values already took away goes on the stack in ladder order, so headroom can give it back
  for (let i = 0; i < resN; i++) stack.push({ a: 'res', boot: 1 });
  if (!fxFixed && !fx) stack.push({ a: 'fx', boot: 1 });
  if (!fpsFixed && fps === 30 && fpsCeil === 60) stack.push({ a: 'fps', boot: 1 });
  for (let i = tierIdx(tier); i < minTier; i++) stack.push({ a: 'tier', boot: 1 });
  let blurSaved = null, resPending = false, inRace = false, raceTicks = 0, over = 0, head = 0, rest = 0, hist = [];
  const inRaceNow = () => (window.RN_FE || []).some(p => /HUD/i.test(p));
  const resSize = () => size(stack.filter(e => e.a === 'res').length);

  const save = () => {
    const nres = stack.filter(e => e.a === 'res').length;
    const rec = { tier, bbmax: nres ? resSize().w : 0, fx: fx ? 1 : 0, fps, updated: new Date().toISOString() };
    window.rnQuality.record = rec;
    gpuId().then(g => { try { localStorage.setItem('rn_quality', JSON.stringify({ dev: rnDevKey(g), ...rec })); } catch {} });
  };
  let gpuP = null;
  const gpuId = () => gpuP || (gpuP = (async () => {
    let g = '';
    try { const ad = await navigator.gpu?.requestAdapter(); const i = ad?.info; if (i) g = [i.vendor, i.architecture, i.description].join('/'); } catch {}
    if (!g) try {   // WebGL 2 (no adapter): the unmasked renderer string
      const c = document.createElement('canvas').getContext('webgl2'), e = c && c.getExtension('WEBGL_debug_renderer_info');
      g = c ? String(c.getParameter(e ? e.UNMASKED_RENDERER_WEBGL : c.RENDERER)) : '';
      c?.getExtension('WEBGL_lose_context')?.loseContext();
    } catch {}
    try { if (localStorage.getItem('rn_gpu') !== g) localStorage.setItem('rn_gpu', g); } catch {}
    return g;
  })());
  gpuId();

  const resLeft = () => { const n = stack.filter(e => e.a === 'res').length; return typeof M._rn_request_screen === 'function' && (size(n + 1).w < size(n).w || size(n + 1).h < size(n).h); };
  const can = {
    res: () => resLeft() && !resPending,   // a requested size waits for its race boundary; meanwhile the live levers go on
    blur: () => !!window.rnBlur && window.rnBlur.get() > 0 && blurSaved === null,
    fx: () => !fxFixed && fx,
    fps: () => !fpsFixed && fps === 60 && typeof M._rn_set_fps === 'function',
    tier: () => !tierFixed && tierIdx(tier) > 0 && !resLeft() && !can.blur() && !can.fx() && !can.fps(),   // content goes last
  };
  const apply = {   // down: returns the log text
    res() { const n = stack.filter(e => e.a === 'res').length + 1, s = size(n); M._rn_request_screen(s.w, s.h); resPending = true; return `next race ${s.w}x${s.h}`; },
    blur() { blurSaved = window.rnBlur.get(); window.rnBlur.set(0); return 'blur off'; },
    fx() { fx = false; return 'effects off at next boot'; },
    fps() { fps = 30; M._rn_set_fps(30); RN_Q.set('fps', '30'); return 'fps 30'; },
    tier() { tier = RN_TIERS[tierIdx(tier) - 1]; return `next boot tier ${tier}`; },
  };
  const undo = {
    res() { const n = stack.filter(e => e.a === 'res').length - 1, s = n ? size(n) : { w: ceil.w, h: ceil.h }; M._rn_request_screen(s.w, s.h); resPending = true; return `next race ${s.w}x${s.h}`; },
    blur() { window.rnBlur.set(blurSaved); blurSaved = null; return 'blur back'; },
    fx() { fx = true; return 'effects on at next boot'; },
    fps() { fps = 60; if (typeof M._rn_set_fps === 'function') M._rn_set_fps(60); RN_Q.set('fps', '60'); return 'fps 60'; },
    tier() { tier = RN_TIERS[tierIdx(tier) + 1]; return `next boot tier ${tier}`; },
  };
  const canUndo = e => (e.a !== 'res' || (typeof M._rn_request_screen === 'function' && !resPending)) && (e.a !== 'blur' || !!window.rnBlur) && (e.a !== 'fps' || typeof M._rn_set_fps === 'function');
  const decide = (dir, why, w) => {
    let action, text;
    if (dir === 'down') {
      action = RN_LADDER.find(k => can[k]());
      if (!action) return false;
      text = apply[action](); stack.push({ a: action });
    } else {
      const e = stack[stack.length - 1];
      if (!e || !canUndo(e)) return false;
      action = e.a; text = undo[action](); stack.pop();
    }
    decisions.push({ t: w.t, dir, action, why, p95: w.p95, target: w.target, stutters: w.stutters, text, step: stack.length });
    say(`quality: ${dir} ${action} (${text}), ${why}, p95 ${w.p95} ms of ${w.target}, step ${stack.length}`);
    rest = REST; over = head = 0; hist = [];
    save();
    return true;
  };

  addEventListener('rn-fe', () => {
    const now = inRaceNow();
    if (inRace && !now) resPending = false;   // the host applies a requested size at the race boundary
    inRace = now;
  });
  addEventListener('rn-stats', ev => {
    const w = ev.detail, now = inRaceNow(), before = inRace;
    if (before && !now) resPending = false;
    inRace = now;
    if (!now || !before) { raceTicks = 0; over = head = 0; hist = []; return; }
    if (++raceTicks < 3) return;                // the first 10 s of a race: track load, shader compile, streaming
    if (rest > 0) { rest--; return; }
    const bad = w.p95 > 1.15 * w.target || w.stutters >= 3;
    hist.push(w.p95); if (hist.length > TREND_N) hist.shift();
    const trend = hist.length === TREND_N && hist.every((x, i) => i === 0 || x >= hist[i - 1]) && hist[TREND_N - 1] >= 1.15 * hist[0] && w.p95 > 0.8 * w.target;
    over = bad ? over + 1 : 0;
    head = !bad && w.p95 < 0.7 * w.target && w.stutters === 0 ? head + 1 : 0;
    if (over >= OVER_N) decide('down', 'overload', w);
    else if (trend) decide('down', `p95 rising ${hist[0]} -> ${hist[TREND_N - 1]} ms`, w);
    else if (head >= HEAD_N) decide('up', 'headroom', w);
  });

  window.rnQuality = Object.assign(window.rnQuality || {}, { decisions, record: null,
    label() { const n = stack.length; return `q step ${n} res ${resSize().w}x${resSize().h}${resPending ? '*' : ''} blur ${window.rnBlur && window.rnBlur.get() > 0 ? 'on' : 'off'} fx ${fx ? 'on' : 'off'} fps ${fps} tier ${tier}`; } });
  say(`quality: controller on (step ${stack.length}, ceiling tier ${staticTier}, res ${ceil.w}x${ceil.h}${RN_STORED ? ', stored ' + RN_STORED.updated : ''})`);
}
