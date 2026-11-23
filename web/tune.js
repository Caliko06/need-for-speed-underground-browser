// Blur bank: presets for the game's own motion blur (0x40cd40). host/d3d9.c tune_apply copies the 4 floats into its .data
// (ramp start/end m/s 0x702a38/0x702a3c, cap of t 0x702a40, streak length 0x702a44) at the next Present.
// ?blur=0..7 picks one; F6 / F7 step down / up in game (the game maps neither key). The choice is kept in this browser.
// Composite alpha at full speed = min(1.5 cap, 1). PC original: 25 -> 125 m/s, cap 0.65; PS2 ramp 0.1 -> 25 m/s
// (SLUS_208.11 0x4ff95c/0x4ff960), strongest PS2 copy alpha 50/128 (0x4485f0) = cap 0.26.
// trails = light-trail strength s (PATCH 0x409bdb, [0x707fcc]): a still lamp is s times its flare, a moving one keeps the
// game's trail length (= the PS2 one in time); 'raw' is the shipped colour 0x1fffffff (still lamps 2-3.4x, blue-white).
const BLUR = [
  { name: 'off',          ramp: [0.1, 25], cap: 0,    trails: 1.0 },
  { name: 'light',        ramp: [0.1, 25], cap: 0.10, trails: 1.0 },
  { name: 'medium',       ramp: [0.1, 25], cap: 0.18, trails: 1.25 },
  { name: 'PS2',          ramp: [0.1, 25], cap: 0.26, trails: 1.5 },
  { name: 'strong',       ramp: [0.1, 25], cap: 0.45, trails: 2.0 },
  { name: 'PC original',  ramp: [25, 125], cap: 0.65, trails: 'raw' },
  // PS2 depth: the PS2's 4-copy zoom blur weighted by the scene's depth (web/gpu.js psblur; car sharp, far city stretched; nitrous adds
  // the PS2's 2 extra passes). The game's own blur is off (cap 0) so the two do not stack; trails as 'PS2'. ?psblur=0 falls back to 3.
  { name: 'PS2 depth',    ramp: [0.1, 25], cap: 0,    trails: 1.5, ps: true },
  // Soft (?pool=1): the PC ramp at a third of its cap. PC cap 0.65 lays a half-resolution zoomed copy of the world over it at up to 97.5 % while the car stays sharp: the OWNER's myopia.
  { name: 'Soft',         ramp: [25, 125], cap: 0.22, trails: 'raw' },
];
const BLUR_ORIGINAL = 5;    // 'PC original': Original mode starts there, as shipped
const BLUR_DEFAULT = 6;     // PS2 depth (before it: 3 = PS2, OWNER 2026-10-26: medium made the blur and the light aura hard to see)
// Trail decay k per frame, R G B: shipped BLENDFACTOR 0x008296b4 at 0x409bca (trail 4.4 / 5.6 / 8.6 frames to 5%: the blue tail).
// Remaster: one k = 0x60 for all three (3.1 frames, white, no blue smear; host/d3d9.c SetRenderState swaps the value), and 'raw'
// becomes s = 1 (a still lamp = its flare, not 2-3.4x). OWNER 2026-10-31: the trail looked like astigmatism, too aggressive.
// Phones keep the short white trail in Original too: at 30 fps the shipped decay lasts twice as long on screen.
const DECAY_SHIPPED = RN_MODE === 'original' && !RN_PHONE;
const DECAY = DECAY_SHIPPED ? [0x82, 0x96, 0xb4] : [0x60, 0x60, 0x60];
const DECAY_RS = DECAY_SHIPPED ? 0 : DECAY.reduce((c, k) => c << 8 | k, 0);
// D3DCOLOR 0x1fRRGGBB with channel = s (1 - k): the add weight that makes a still light s times its flare.
const trailColor = s => s === 'raw' && RN_MODE === 'original' ? 0x1fffffff :
  (0x1f000000 | DECAY.reduce((c, k) => c << 8 | Math.min(255, Math.round((s === 'raw' ? 1 : s) * (255 - k))), 0)) >>> 0;
const STREAK = 0.00625;     // 0x702a44 as shipped
// ?speedfov=<deg>: the chase camera's FOV grows by up to this many degrees from 90 to 270 km/h (host/d3d9.c fov_frame: it rewrites
// the game's FOV table 0x6fbdf4 from the camera's speed, the camera and projection follow). 0 = off, as shipped; Original mode sets 0.
const SPEEDFOV = 0;   // was 10: the wider view at speed made the acceleration feel stronger than the shipped game (OWNER 2026-10-31)
// ?chasecam=1|0: the far and close chase cameras look 8 degrees steeper at the same distance (host/d3d9.c chase_frame rewrites the car's camera rows).
const CHASECAM = 0;   // OWNER 2026-10-31: the steeper eye hid the car's rear; the shipped rows (1:1)
// ?nitrocam=1|0: while the nitrous burns the chase camera goes 10% farther and 5% lower (host/d3d9.c chase_frame, same rows).
const NITROCAM = 0;   // was 1: the pull-back with nitrous, off (OWNER 2026-10-31: camera not farther)
// ?hfov=<deg>: the horizontal view at 16:9 or wider in races, in degrees (host/d3d9.c hfov_frame, k of the widescreen caves). Absent = the shipped 96.5 (the PS2's
// vertical view, PATCH 0x40debb); 4:3 PC was 71.5 horizontal. k = tan(71.5/2) * 16/9 / tan(hfov/2).

function startTune(M) {
  const base = M._rn_tune_addr() >> 2;
  const f = new Float32Array(1), u = new Uint32Array(f.buffer);
  const bits = x => (f[0] = x, u[0]);
  let level = RN_MODE === 'original' ? BLUR_ORIGINAL : BLUR_DEFAULT;
  const POOL = RN_MODE !== 'original' && RN_Q.get('pool') === '1';
  if (POOL) level = 7;
  const KEY = RN_MODE === 'original' ? 'rn_blur2_orig' : POOL ? 'rn_blur_pool' : 'rn_blur3';   // web/mode.js: each mode keeps its own F6/F7 choice
  try { const s = localStorage.getItem(KEY); if (s !== null && BLUR[+s]) level = +s; } catch {}
  const q = RN_Q.get('blur');
  if (q !== null && BLUR[+q]) level = +q;
  const sf = parseFloat(RN_Q.get('speedfov') ?? SPEEDFOV);
  const speedfov = isFinite(sf) ? sf : 0;
  const chasecam = RN_Q.get('chasecam') === null ? CHASECAM : +RN_Q.get('chasecam') ? 1 : 0;
  const nitrocam = RN_Q.get('nitrocam') === null ? NITROCAM : +RN_Q.get('nitrocam') ? 1 : 0;
  const hf = parseFloat(RN_Q.get('hfov'));
  const hfovK = hf > 40 && hf < 120 ? Math.tan(35.75 * Math.PI / 180) * 16 / 9 / Math.tan(hf * Math.PI / 360) : 0;
  const psOff = RN_Q.get('psblur') === '0';
  if (psOff && BLUR[level].ps) level = 3;    // ?psblur=0: the pass off, the game's own PS2 blur instead

  const toast = document.createElement('div');
  Object.assign(toast.style, { position: 'fixed', left: '50%', top: '12px', transform: 'translateX(-50%)', padding: '6px 14px',
    background: 'rgba(0,0,0,0.75)', color: '#9fe3ff', font: '14px system-ui, sans-serif', borderRadius: '6px',
    pointerEvents: 'none', display: 'none', zIndex: 10 });
  document.body.appendChild(toast);
  let hide = 0;

  function apply(show, keep) {
    const p = BLUR[level], h = M.HEAPU32;
    RN_PS.on = !!p.ps && !psOff;
    h[base + 1] = bits(p.ramp[0]); h[base + 2] = bits(p.ramp[1]); h[base + 3] = bits(p.cap); h[base + 4] = bits(STREAK); h[base + 5] = trailColor(p.trails);
    h[base + 6] = bits(speedfov);
    h[base + 7] = chasecam;
    h[base + 8] = nitrocam;
    h[base + 9] = hfovK ? bits(hfovK) : 0;
    h[base + 10] = DECAY_RS;
    Atomics.add(h, base, 1);
    if (!keep) try { localStorage.setItem(KEY, String(level)); } catch {}   // keep: the quality controller's change (web/quality.js) is not the player's choice
    if (!show) return;
    toast.textContent = `Blur ${level}/${BLUR.length - 1}: ${p.name}   (F6 / F7)`;
    toast.style.display = 'block';
    clearTimeout(hide); hide = setTimeout(() => toast.style.display = 'none', 1500);
  }
  // Capture phase on window: the canvas (web/input.js) never sees F6/F7, so the game does not get them.
  window.addEventListener('keydown', e => {
    if (e.code !== 'F6' && e.code !== 'F7') return;
    e.preventDefault(); e.stopPropagation();
    if (e.repeat) return;
    level = Math.max(0, Math.min(BLUR.length - 1, level + (e.code === 'F7' ? 1 : -1)));
    if (psOff && BLUR[level].ps) level = BLUR.length - 2;
    apply(true);
  }, true);
  window.addEventListener('keyup', e => { if (e.code === 'F6' || e.code === 'F7') { e.preventDefault(); e.stopPropagation(); } }, true);
  apply(false);
  // web/quality.js: blur off under load and back, without touching the stored choice
  window.rnBlur = { get: () => level, set: l => { if (BLUR[l] && !(psOff && BLUR[l].ps)) { level = l; apply(false, true); } } };
}
