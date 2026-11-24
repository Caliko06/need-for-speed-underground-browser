// The page's one lifecycle state (OWNER 2026-11-10). Whoever needs it subscribes with RN_APP.on; nobody keeps a flag of its own.
//   check  : web/boot.js tests the browser before any download
//   load   : downloads and the game's boot, under the gate (plus the launcher's scene with ?fast=1, web/index.html)
//   run    : the game draws and takes input
//   paused : run, but the page is hidden or a phone is held upright: the frame pump (web/gpu.js) and the audio
//            (web/audio.js) hold, so the game thread waits in Present. ?bg=1 turns this off (benches behind another window)
//   stop   : fatal and final; the gate says why in plain words, the log stays on F2
// check -> load -> run <-> paused; any -> stop.
'use strict';
const RN_APP = (() => {
  const subs = [], coarse = matchMedia('(pointer: coarse)').matches, bg = RN_Q.get('bg') === '1';
  const upright = () => coarse && !bg && innerHeight > innerWidth;
  const app = {
    state: 'check', coarse,
    on(f) { subs.push(f); },
    set(s, detail) {
      if (s === app.state || app.state === 'stop') return;
      const from = app.state;
      app.state = s;
      for (const f of subs) f(s, from, detail);
    },
    // What the gate says while the state is check or load (web/boot.js: the download counter, the boot); part = 0..1 draws the line of real progress under it.
    say(text, part = null) { note = text; frac = part; render(); },
  };

  // A stop line of the page log -> what a player can do about it.
  const WHY = [
    [/sin aislamiento/, 'Este navegador no puede correr el juego: le falta el modo de memoria compartida que usa (pasa en navegadores dentro de apps y en algunos de sistema, como el de LineageOS). Ábrelo en Chrome, Edge, Firefox o Samsung Internet.'],
    [/ni WebGL 2/, 'Tu navegador no puede dibujar el juego (no tiene WebGPU ni WebGL 2). Usa Chrome, Edge, Safari o Firefox recientes.'],
    [/WebGPU no disponible/, 'Tu navegador no tiene WebGPU. Funciona en Chrome o Edge 113+ (computadora y Android 12+), Safari 26+ (Mac, iPhone, iPad) y Firefox 141+ (Windows) o 145+ (Mac Apple Silicon).'],
    [/sin adaptador/, 'WebGPU está apagado o la tarjeta gráfica de este equipo no es compatible.'],
    [/se perdió la GPU/, 'El navegador soltó la tarjeta gráfica (pasa al dejar la página mucho rato en segundo plano).'],
    [/out of memory|could not allocate memory|memoria|OOM/i, 'Este dispositivo no tiene memoria libre suficiente para el juego. Cierra otras pestañas y apps.'],
    [/descarga|Failed to fetch|NetworkError|Load failed/, 'No se pudo descargar el juego. Revisa tu conexión.'],
    [/: ExitProcess\(0\)/, 'Saliste del juego. Toca Recargar para volver a jugar.'],
  ];

  const css = document.createElement('style');
  css.textContent = `
    #gate { position: fixed; inset: 0; z-index: 14; display: none; box-sizing: border-box; pointer-events: none; text-align: center; color: #b9c3ec;
      padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));
      font: italic 700 clamp(14px, 1.5vw, 20px) "Avenir Next Condensed", "DIN Condensed", "Bahnschrift", "Roboto Condensed", "Arial Narrow", "Helvetica Neue", Arial, sans-serif; }
    #gate.load { display: flex; align-items: flex-end; justify-content: center; padding-bottom: 7vh; letter-spacing: .2em; text-transform: uppercase;
      text-shadow: 0 0 .9em rgba(255,47,168,.45), 0 2px 8px #000; font-variant-numeric: tabular-nums; }
    #gate.load i { position: absolute; left: 30vw; right: 30vw; bottom: calc(7vh - 14px); height: 2px; transform-origin: 0 50%; background: linear-gradient(90deg, #ff2fa8, #b9c3ec); box-shadow: 0 0 10px rgba(255,47,168,.6); }
    #gate.card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; pointer-events: auto;
      background: radial-gradient(120% 90% at 50% 0%, #1a1030 0%, #05080d 70%); }
    #gate h2 { margin: 0; font-size: clamp(20px, 3.2vw, 34px); letter-spacing: .12em; text-transform: uppercase; color: #fff; text-shadow: 0 0 .9em rgba(255,47,168,.45); }
    #gate p { margin: 0; max-width: 46ch; font: 400 16px/1.5 system-ui, sans-serif; color: #c9cdea; }
    #gate .tech { font: 12px/1.4 ui-monospace, Menlo, monospace; color: #6e7681; word-break: break-word; user-select: text; -webkit-user-select: text; }
    #gate button { font: inherit; letter-spacing: .14em; text-transform: uppercase; color: #fff; padding: 12px 28px; border: 0; border-radius: 999px; cursor: pointer;
      background: linear-gradient(135deg, #ff7a18, #af002d); box-shadow: 0 8px 24px rgba(175,0,45,.45); transition: transform .12s; }
    #gate button:active { transform: scale(.97); }
    #gate button:focus-visible { outline: 2px solid #fff; outline-offset: 3px; }
    #gate svg { width: 84px; height: 84px; }
    body.dbg #gate { display: none; }
    @media (prefers-reduced-motion: reduce) { #gate button { transition: none; } }`;
  document.head.appendChild(css);
  const gate = Object.assign(document.createElement('div'), { id: 'gate' });
  gate.setAttribute('role', 'status');
  document.body.appendChild(gate);
  const el = (tag, text, cls) => { const e = Object.assign(document.createElement(tag), { textContent: text }); if (cls) e.className = cls; return e; };

  let note = 'Cargando…', frac = null, why = '', shown = '';
  function render() {
    const s = app.state;
    const view = s === 'stop' ? 'stop' : upright() ? 'turn' : s === 'check' || s === 'load' ? 'load:' + note + (frac === null ? '' : '|' + Math.round(frac * 200)) : '';
    if (view === shown) return;
    shown = view;
    gate.replaceChildren();
    gate.className = !view ? '' : view.startsWith('load') ? 'load' : 'card';
    if (view === 'stop') {
      const b = el('button', 'Recargar');
      b.onclick = () => location.reload();
      const r = el('button', 'Descargar reporte');   // web/boot.js rnReport: the session as one file, to send with the bug
      r.style.cssText = 'background:none;box-shadow:none;border:1px solid #ffffff55;padding:9px 22px;font-size:.8em';
      r.onclick = () => window.rnReport?.();
      // No isolation (Android WebView browsers such as LineageOS Jelly, in-app browsers): reloading never helps, so hand the link to Chrome.
      // iPhone in-app browsers: x-safari-https:// hands the link to Safari (iOS 17+). Android: an intent to Chrome. Tried once on its
      // own (links shared in Instagram, TikTok or WhatsApp open in their WebView); apps that block a jump without a tap keep the button.
      const ios = /iPhone|iPad/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
      if (/sin aislamiento/.test(why) && (ios || /Android/.test(navigator.userAgent))) {
        const to = ios ? `x-safari-https://${location.host}${location.pathname}${location.search}`
          : `intent://${location.host}${location.pathname}${location.search}#Intent;scheme=https;package=com.android.chrome;end`;
        b.textContent = ios ? 'Abrir en Safari' : 'Abrir en Chrome';
        b.onclick = () => { location.href = to; };
        let jumped = false; try { jumped = !!sessionStorage.rnJump; if (!jumped) sessionStorage.rnJump = 1; } catch {}
        if (!jumped) location.href = to;
        r.textContent = 'Copiar enlace';
        r.onclick = () => navigator.clipboard?.writeText(location.origin + '/').then(() => { r.textContent = 'Enlace copiado'; }, () => {});
      }
      gate.append(el('h2', 'El juego se detuvo'), el('p', (WHY.find(([re]) => re.test(why)) || [0, 'El juego falló. Recarga para seguir; el reporte dice qué pasó.'])[1]), b, r, el('p', why, 'tech'));
      b.focus();
    } else if (view === 'turn') {
      gate.innerHTML = '<svg viewBox="0 0 48 48" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="20" width="36" height="20" rx="4"/><path d="M14 13a14 14 0 0 1 20 0"/><path d="M34 7v6h-6"/></svg>';
      gate.append(el('h2', 'Gira el teléfono'), el('p', 'El juego es horizontal y espera en pausa.' + (document.documentElement.requestFullscreen ? ' Toca para pantalla completa.' : ' Si no gira, quita el bloqueo de rotación.')));
    } else if (view) {
      gate.textContent = note;
      if (frac !== null) { const b = el('i'); b.style.transform = `scaleX(${Math.max(0, Math.min(1, frac))})`; gate.append(b); }
    }
  }

  // run <-> paused follows the page: hidden, or a phone held upright.
  const sync = () => {
    const hold = !bg && (document.hidden || upright());
    if (app.state === 'run' && hold) app.set('paused');
    else if (app.state === 'paused' && !hold) app.set('run');
    render();
  };
  app.on((s, from, detail) => { if (s === 'stop') why = String(detail || ''); queueMicrotask(sync); });
  document.addEventListener('visibilitychange', sync);
  addEventListener('resize', sync);

  // Phones and tablets: the first touch asks for the whole screen and a landscape lock (Android Chrome has both; iPhone Safari
  // has neither, so there the upright gate is the answer). A tap on the upright gate asks again.
  // Every touch asks again while the page is not full screen (a swipe can leave it); web/touch.js has a button for it too.
  const full = () => {
    const d = document.documentElement;
    if (!coarse || document.fullscreenElement || !d.requestFullscreen) return;
    d.requestFullscreen({ navigationUI: 'hide' }).then(() => screen.orientation?.lock?.('landscape')).catch(() => {});
  };
  app.full = full;
  addEventListener('touchend', full, { capture: true });
  gate.addEventListener('click', full);

  // Until the game runs it gets no keys or taps (F keys and K, the bindings overlay, stay): a key pressed over the
  // loading screen would land in the first menu.
  const early = () => app.state === 'check' || app.state === 'load';
  for (const t of ['keydown', 'keyup']) addEventListener(t, e => { if (early() && !/^F\d+$/.test(e.code) && e.code !== 'KeyK') { e.preventDefault(); e.stopPropagation(); } }, true);
  addEventListener('pointerdown', e => { if (early() && !e.target.closest?.('#ov, #ov-btn')) { e.preventDefault(); e.stopPropagation(); } }, true);

  render();
  return app;
})();
