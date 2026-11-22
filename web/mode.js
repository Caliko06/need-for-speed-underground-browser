// Mode: one address (5180) for everything. 'remaster' (default) = every bridge and effect we added; 'original' = the
// game as Speed.exe ships it, for A/B. F4 asks, F4 again within 3 s switches and reloads (most switches are read at boot).
// The choice is kept in this browser. A key=value of this visit (RN_SEARCH, web/index.html) still wins over the mode.
// RN_Q replaces new URLSearchParams(location.search) in every page script.
const RN_ORIGINAL = {
  remaster: '0',      // texture pack (world and cars), web/gpu.js
  skinhd: '0',        // HD car skin composite, web/gpu.js
  bloom: '0', fxaa: '0', sharp: 'off', aniso: '1',
  carlook: '2003',    // host/sm1.c: car.efx at the shipped strength
  cardetail: '0',     // host/sm1.c: no AO/grime terms
  handling: '0',      // host/rivals.c: the shipped rear grip assist
  trafyield: '0',     // host/rivals.c: traffic never sees a car closing from behind
  ai: '0',            // host/rivals.c: rival personalities off, the shipped skill records
  speedfov: '0',      // web/tune.js, host/d3d9.c: the chase camera's FOV stays at the shipped 71.5 deg
  chasecam: '0',      // web/tune.js, host/d3d9.c: the chase camera keeps the car's shipped distance and height rows
  nitrocam: '0',      // web/tune.js, host/d3d9.c: no extra pull-back while the nitrous burns
  roadrefl: 'game',   // host/sm1.c: the road reflection as worldreflect.efx weights it
};   // blur: web/tune.js starts the original mode at 'PC original' (shipped blur and flare colour)
// Native switches of the same mode (host/: traffic pool and pace, rivals, car smoothing, HUD places, night lights, free mode).
const RN_ORIGINAL_ENV = { RN_TRAFFIC: '0', RN_RIVALS: '0', RN_SMOOTH: '0', RN_HUD: '43', RN_LIGHTS: '0', RN_CARLOD: '0', RN_FREE: '0', RN_TRAFPAINT: '0', RN_TRAFLEAN: '0', RN_FEEL: '0', RN_WALLSOFTEN: '0', RN_NPCSMOOTH: '0' };

// ?mode=original|remaster: one run in that mode without touching the stored choice (tools/webcheck.mjs).
// Phones and tablets (coarse pointer) always start light (OWNER 2026-11-15): Original, effects off, 30 fps, whatever this
// browser stored; only a ?mode= / ?fx= / ?fps= in the address (this visit's overlay or menu switch, a test) says otherwise.
const RN_PHONE = (() => { try { return matchMedia('(pointer: coarse)').matches; } catch { return false; } })();
// Policy: treat reported hardware as 80% usable capacity and step down 1 tier ("concepto -1")
// when lacking WebGPU or running on a low-RAM phone, so devices stay inside real-world headroom.
const RN_TIERS = ['ultralite', 'lite', 'standard', 'full'];
const RN_TIER_OVERRIDE = new URLSearchParams(RN_SEARCH).get('tier');
function rnDetectTier(webgpu = !!navigator.gpu) {
  if (RN_TIERS.includes(RN_TIER_OVERRIDE)) return RN_TIER_OVERRIDE;
  const ram = Number(navigator.deviceMemory) || 0, cores = Number(navigator.hardwareConcurrency) || 0;
  const effRam = ram * 0.8, effCores = Math.floor(cores * 0.8);
  let idx;
  if ((effRam > 0 && effRam < 3) || (effCores > 0 && effCores <= 2)) idx = 0;
  else if (RN_PHONE || (effRam > 0 && effRam < 4) || (effCores > 0 && effCores <= 3)) idx = 1;
  else if (webgpu && effRam >= 6.4 && effCores >= 6) idx = 3;
  else idx = 2;
  if (!webgpu && idx > 0) idx--;
  if (RN_PHONE && effRam > 0 && effRam < 4 && idx > 0) idx--;
  return RN_TIERS[idx];
}
// boot.js resolves adapter availability before loading either renderer or exporting host ENV,
// then calls rnSetTier() so RN_TIER, RN_LOW_TIER, RN_MODE and RN_Q stay in sync.
let RN_TIER = rnDetectTier();
let RN_LOW_TIER = RN_TIER === 'lite' || RN_TIER === 'ultralite';
let RN_MODE = (() => {
  const q = new URLSearchParams(RN_SEARCH).get('mode');
  if (q === 'original' || q === 'remaster') return q;
  if (RN_LOW_TIER) return 'original';
  // Default remaster (OWNER 2026-11-10); original only when picked.
  try { return localStorage.getItem('rn_mode') === 'original' ? 'original' : 'remaster'; } catch { return 'remaster'; }
})();
// Degradation switches for weaker devices (OWNER 2026-11-02: accepted, each a switch, off by default):
// ?fx=0: the remaster's visual effects off (texture pack, HD skins, bloom, FXAA, sharpen, aniso, car and road shader
//        terms back to the shipped ones); the remaster's gameplay and camera keys stay. ?fps=30: host RN_FPS (frame pacer).
const RN_FX_OFF = ['remaster', 'skinhd', 'bloom', 'fxaa', 'sharp', 'aniso', 'carlook', 'cardetail', 'roadrefl'];
const RN_SHARP_EXPLICIT = new URLSearchParams(RN_SEARCH).has('sharp');
function rnBuildQ() {
  const q = new URLSearchParams(RN_SEARCH);
  // WebGPU phones keep sharpen on upscale (OWNER 2026-11-15); boot.js turns this default off for WebGL2 after adapter detection.
  if (RN_LOW_TIER && !RN_SHARP_EXPLICIT) q.set('sharp', '0.5');
  if (RN_MODE === 'original') for (const [k, v] of Object.entries(RN_ORIGINAL)) if (!q.has(k)) q.set(k, v);
  if (RN_LOW_TIER && !q.has('fx')) q.set('fx', '0');
  if (q.get('fx') === '0') for (const k of RN_FX_OFF) if (!q.has(k)) q.set(k, RN_ORIGINAL[k]);
  // 30 fps unless ?fps= says otherwise (host RN_FPS, web/boot.js)
  if (RN_LOW_TIER && !q.has('fps')) q.set('fps', '30');
  // Phones (OWNER 2026-11-15: the blur and the motion looked wrong, the phone ran hot): the game's speed blur off (web/tune.js level 0; the
  // shipped one lays a half-size zoomed copy of the world over a picture that is already scaled up) and the frame limiter sleeps
  // instead of spinning (host/win32.c limiter_sleep: in menus the spin held one core at 99 %). ?blur= or ?env=RN_LIMSLEEP=0 say otherwise.
  if (RN_LOW_TIER && !q.has('blur')) q.set('blur', '0');
  if (RN_LOW_TIER) q.set('env', ['RN_LIMSLEEP=1', q.get('env')].filter(Boolean).join(','));
  if (RN_TIER === 'ultralite') {
    q.set('msaa', '1'); q.set('fx', '0'); q.set('fps', '30'); q.set('blur', '0'); q.set('sharp', 'off'); q.set('roadrefl', 'off');
    for (const k of RN_FX_OFF) if (k !== 'roadrefl') q.set(k, RN_ORIGINAL[k]);
    const bb = Number(q.get('bbmax'));
    q.set('bbmax', String(bb > 0 ? Math.min(720, bb) : 720));
  }
  return q;
}
const RN_Q = rnBuildQ();
function rnSetTier(tier) {
  RN_TIER = tier;
  RN_LOW_TIER = tier === 'lite' || tier === 'ultralite';
  const explicitMode = new URLSearchParams(RN_SEARCH).get('mode');
  if (explicitMode !== 'original' && explicitMode !== 'remaster' && RN_LOW_TIER) RN_MODE = 'original';
  const fresh = rnBuildQ();
  for (const k of [...RN_Q.keys()]) RN_Q.delete(k);
  for (const [k, v] of fresh) RN_Q.set(k, v);
}

(() => {
  const toast = document.createElement('div');
  Object.assign(toast.style, { position: 'fixed', left: '50%', top: '44px', transform: 'translateX(-50%)', padding: '6px 14px',
    background: 'rgba(0,0,0,0.75)', color: '#ffd479', font: '14px system-ui, sans-serif', borderRadius: '6px',
    pointerEvents: 'none', display: 'none', zIndex: 10 });
  const show = (s, ms) => { toast.textContent = s; toast.style.display = 'block'; clearTimeout(show.t); show.t = setTimeout(() => toast.style.display = 'none', ms); };
  window.rnToast = show;
  addEventListener('DOMContentLoaded', () => {
    document.body.appendChild(toast);
    show(RN_PHONE ? (RN_MODE === 'original' ? 'Modo ligero' : 'Modo Remaster') : RN_MODE === 'original' ? 'Modo ORIGINAL (2003)   ·   F4 = Remaster' : 'Modo Remaster   ·   F4 = Original', 2500);
  });
  // The native main-menu button and the second F4 use the same switch.
  window.rnSwitchMode = () => {
    const next = RN_MODE === 'original' ? 'remaster' : 'original';
    try { localStorage.setItem('rn_mode', next); } catch {}
    show('Reiniciando…', 5000);
    const q = new URLSearchParams(RN_SEARCH);
    q.set('mode', next); // This visit's switches must not pin the previous mode.
    try { sessionStorage.setItem('rn_q', q.toString()); } catch {}
    setTimeout(() => location.replace(location.pathname), 150);
  };
  let armed = 0;
  // Capture phase on window: the canvas (web/input.js) never sees F4, so the game does not get it.
  addEventListener('keydown', e => {
    if (e.code !== 'F4') return;
    e.preventDefault(); e.stopPropagation();
    if (e.repeat) return;
    const next = RN_MODE === 'original' ? 'remaster' : 'original';
    if (performance.now() - armed > 3000) {
      armed = performance.now();
      show(`F4 otra vez: cambiar a ${next === 'original' ? 'ORIGINAL (2003)' : 'Remaster'} (el juego reinicia)`, 3000);
      return;
    }
    window.rnSwitchMode();
  }, true);
  addEventListener('keyup', e => { if (e.code === 'F4') { e.preventDefault(); e.stopPropagation(); } }, true);
})();
