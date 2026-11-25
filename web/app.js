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

  const TR = s => (window.RN_TR ? window.RN_TR(s) : s);
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const isStandalone = () => matchMedia('(display-mode: standalone)').matches || matchMedia('(display-mode: fullscreen)').matches || navigator.standalone === true;
  let deferredInstall = null;
  addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; if (shown === 'turn') { shown = ''; render(); } });

  const css = document.createElement('style');
  css.textContent = `
    #gate { position: fixed; inset: 0; z-index: 14; display: none; box-sizing: border-box; pointer-events: none; text-align: center; color: #b9c3ec;
      padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));
      font: italic 700 clamp(14px, 1.5vw, 20px) "Avenir Next Condensed", "DIN Condensed", "Bahnschrift", "Roboto Condensed", "Arial Narrow", "Helvetica Neue", Arial, sans-serif; }
    #gate.load { display: flex; align-items: flex-end; justify-content: center; padding-bottom: 7vh; letter-spacing: .2em; text-transform: uppercase;
      text-shadow: 0 0 .9em rgba(255,47,168,.45), 0 2px 8px #000; font-variant-numeric: tabular-nums; }
    #gate.load i { position: absolute; left: 30vw; right: 30vw; bottom: calc(7vh - 14px); height: 2px; transform-origin: 0 50%; background: linear-gradient(90deg, #ff2fa8, #b9c3ec); box-shadow: 0 0 10px rgba(255,47,168,.6); }
    #gate.card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; pointer-events: auto; overflow-y: auto;
      background: radial-gradient(120% 80% at 50% 0%, #0d2238 0%, #05080d 72%); }
    #gate h2 { margin: 0; font-size: clamp(22px, 5vw, 34px); letter-spacing: .1em; text-transform: uppercase; color: #fff; text-wrap: balance; text-shadow: 0 2px 14px rgba(56,189,248,.35); }
    #gate p { margin: 0; max-width: 44ch; font: 400 15px/1.45 system-ui, -apple-system, sans-serif; color: #c7d4e8; text-wrap: pretty; }
    #gate .tech { font: 12px/1.4 ui-monospace, Menlo, monospace; color: #6e7681; word-break: break-word; user-select: text; -webkit-user-select: text; }
    #gate button { font: inherit; letter-spacing: .12em; text-transform: uppercase; color: #fff; min-height: 44px; padding: 10px 24px; border: 0; border-radius: 10px; cursor: pointer;
      background: linear-gradient(135deg, #f59e0b, #ea580c); box-shadow: 0 6px 20px rgba(234,88,12,.35); transition: transform 130ms cubic-bezier(.22,1,.36,1), opacity 130ms; }
    #gate button:active { transform: scale(.97); }
    #gate button:focus-visible { outline: 2px solid #fff; outline-offset: 3px; }
    #gate .btn-ghost { background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.16); box-shadow: none; font-size: 13px; padding: 8px 14px; min-height: 40px; }
    #gate svg { width: 84px; height: 84px; }
    #gate .rot-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%; max-width: 380px; }
    #gate .rot-stage { position: relative; width: 96px; height: 72px; display: grid; place-items: center; }
    #gate .rot-phone { width: 42px; height: 70px; border: 2.5px solid #e2ecf8; border-radius: 9px; background: linear-gradient(180deg, #0b1b2e 0%, #102a45 58%, #07101b 100%);
      position: relative; box-shadow: 0 8px 22px rgba(0,0,0,.55), inset 0 0 0 1px rgba(255,255,255,.08); transform-origin: center;
      animation: rn-rot 2.6s cubic-bezier(.22,1,.36,1) infinite; }
    #gate .rot-phone::before { content: ''; position: absolute; left: 50%; top: 5px; width: 12px; height: 2px; transform: translateX(-50%); border-radius: 2px; background: rgba(255,255,255,.45); }
    #gate .rot-phone::after { content: ''; position: absolute; left: 5px; right: 5px; bottom: 16px; height: 2px; border-radius: 2px; background: linear-gradient(90deg, #38bdf8, #f59e0b); }
    @keyframes rn-rot { 0%, 18% { transform: rotate(0deg); } 45%, 82% { transform: rotate(-90deg); } 100% { transform: rotate(0deg); } }
    #gate .wiz { width: 100%; max-width: 380px; text-align: left; padding: 14px; border-radius: 14px; box-sizing: border-box;
      background: rgba(10, 22, 36, .88); border: 1px solid rgba(255,255,255,.12); box-shadow: 0 14px 36px rgba(0,0,0,.48);
      font: 400 14px/1.45 system-ui, -apple-system, sans-serif; color: #dbe7f5; }
    #gate .wiz-hd { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
    #gate .wiz-hd strong { font: italic 700 16px/1.1 "Avenir Next Condensed", "DIN Condensed", "Bahnschrift", "Roboto Condensed", Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #fff; }
    #gate .wiz-pill { font: 600 11px/1 system-ui, sans-serif; padding: 4px 8px; border-radius: 999px; background: rgba(245,158,11,.16); border: 1px solid rgba(245,158,11,.4); color: #fde68a; }
    #gate .wiz-sub { font-size: 13px; color: #9fb4cc; margin: 0 0 10px; }
    #gate .cmp { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
    #gate .cmp-box { padding: 8px; border-radius: 10px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.08); text-align: center; }
    #gate .cmp-box.best { background: rgba(56,189,248,.08); border-color: rgba(56,189,248,.38); }
    #gate .cmp-scr { height: 42px; border-radius: 6px; border: 1.5px solid rgba(255,255,255,.28); overflow: hidden; display: flex; flex-direction: column; margin-bottom: 6px; background: #071320; }
    #gate .cmp-bar { height: 9px; background: rgba(255,255,255,.18); flex: 0 0 auto; }
    #gate .cmp-game { flex: 1; background: linear-gradient(135deg, #0ea5e9 0%, #1d4ed8 55%, #f59e0b 100%); opacity: .75; }
    #gate .cmp-box.best .cmp-game { opacity: 1; }
    #gate .cmp-lbl { font-size: 11px; color: #9fb4cc; font-weight: 600; }
    #gate .cmp-box.best .cmp-lbl { color: #e0f2fe; }
    #gate .wiz-step { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 10px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); min-height: 58px; }
    #gate .wiz-ico { flex: 0 0 38px; height: 38px; border-radius: 9px; display: grid; place-items: center; background: rgba(56,189,248,.14); border: 1px solid rgba(56,189,248,.3); color: #7dd3fc; }
    #gate .wiz-ico svg { width: 20px; height: 20px; }
    #gate .wiz-txt { flex: 1; font-size: 13.5px; color: #eff6ff; }
    #gate .wiz-txt small { display: block; font-size: 11px; color: #94a3b8; font-variant-numeric: tabular-nums; margin-bottom: 2px; }
    #gate .wiz-nav { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px; }
    #gate .wiz-dots { display: flex; gap: 6px; }
    #gate .wiz-dot { width: 8px; height: 8px; border-radius: 999px; background: rgba(255,255,255,.22); border: 0; padding: 0; min-height: 0; box-shadow: none; }
    #gate .wiz-dot.on { width: 20px; background: #38bdf8; }
    body.dbg #gate { display: none; }
    @media (prefers-reduced-motion: reduce) { #gate button { transition: none; } #gate .rot-phone { animation: none; transform: rotate(-90deg); } }`;
  document.head.appendChild(css);
  const gate = Object.assign(document.createElement('div'), { id: 'gate' });
  gate.setAttribute('role', 'status');
  document.body.appendChild(gate);
  const el = (tag, text, cls) => { const e = Object.assign(document.createElement(tag), { textContent: text }); if (cls) e.className = cls; return e; };

  let note = 'Cargando…', frac = null, why = '', shown = '', wizStep = 0;
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
      const wrap = el('div', '', 'rot-wrap');
      const stage = el('div', '', 'rot-stage');
      stage.setAttribute('aria-hidden', 'true');
      stage.append(el('div', '', 'rot-phone'));
      wrap.append(
        stage,
        el('h2', TR('Gira el teléfono')),
        el('p', TR('El juego es horizontal y espera en pausa.') + ' ' + TR('Si no gira, quita el bloqueo de rotación.'))
      );
      if (document.documentElement.requestFullscreen) {
        const fsBtn = el('button', TR('Pantalla completa ahora'));
        fsBtn.type = 'button';
        fsBtn.onclick = e => { e.stopPropagation(); full(); };
        wrap.append(fsBtn);
      }
      gate.append(wrap);

      // Mini wizard: show why Home Screen (standalone) is much better + platform-specific steps. Hidden once already standalone.
      if (!isStandalone()) {
        const ICONS = {
          share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>',
          plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><path d="M12 8v8M8 12h8"/></svg>',
          menu: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>',
          play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="3"/><path d="m10 9 5 3-5 3z" fill="currentColor" stroke="none"/></svg>',
        };
        const steps = isIOS ? [
          { ico: ICONS.share, text: TR('Toca el botón Compartir en la barra inferior de Safari.') },
          { ico: ICONS.plus, text: TR('Desliza y elige "Agregar a inicio".') },
          { ico: ICONS.play, text: TR('Abre NFS Underground desde tu pantalla de inicio y gira el teléfono.') },
        ] : [
          { ico: ICONS.menu, text: TR('Toca el menú (⋮) arriba a la derecha en Chrome.') },
          { ico: ICONS.plus, text: TR('Elige "Agregar a pantalla principal" o "Instalar app".') },
          { ico: ICONS.play, text: TR('Ábrelo desde tu inicio para jugar sin barras y gira el teléfono.') },
        ];
        wizStep = Math.max(0, Math.min(steps.length - 1, wizStep));

        const wiz = el('section', '', 'wiz');
        wiz.setAttribute('aria-label', TR('Cómo agregarlo al inicio'));
        const hd = el('div', '', 'wiz-hd');
        hd.append(el('strong', TR('Mejor a pantalla completa')), el('span', TR('Recomendado'), 'wiz-pill'));
        const sub = el('p', TR('Sin barras del navegador, más espacio para los botones táctiles y acceso en un toque.'), 'wiz-sub');

        const cmp = el('div', '', 'cmp');
        cmp.setAttribute('aria-hidden', 'true');
        const c1 = el('div', '', 'cmp-box');
        c1.innerHTML = `<div class="cmp-scr"><div class="cmp-bar"></div><div class="cmp-game"></div><div class="cmp-bar"></div></div><div class="cmp-lbl">${TR('En navegador')}</div>`;
        const c2 = el('div', '', 'cmp-box best');
        c2.innerHTML = `<div class="cmp-scr"><div class="cmp-game"></div></div><div class="cmp-lbl">${TR('Desde tu inicio')}</div>`;
        cmp.append(c1, c2);

        const stepBox = el('div', '', 'wiz-step');
        const icoEl = el('div', '', 'wiz-ico');
        const txtEl = el('div', '', 'wiz-txt');
        const nav = el('div', '', 'wiz-nav');
        const prev = el('button', TR('Anterior'), 'btn-ghost');
        const next = el('button', TR('Siguiente'), 'btn-ghost');
        prev.type = 'button';
        next.type = 'button';
        const dots = el('div', '', 'wiz-dots');
        const dotBtns = steps.map((_, idx) => {
          const d = el('button', '', 'wiz-dot');
          d.type = 'button';
          d.setAttribute('aria-label', `${TR('Paso')} ${idx + 1}`);
          d.onclick = e => { e.stopPropagation(); wizStep = idx; drawStep(); };
          dots.append(d);
          return d;
        });

        const drawStep = () => {
          const st = steps[wizStep];
          icoEl.innerHTML = st.ico;
          txtEl.replaceChildren();
          txtEl.append(el('small', `${TR('Paso')} ${wizStep + 1} / ${steps.length}`), document.createTextNode(st.text));
          prev.disabled = wizStep === 0;
          prev.style.opacity = wizStep === 0 ? '.35' : '1';
          next.textContent = wizStep === steps.length - 1 ? TR('Listo') : TR('Siguiente');
          dotBtns.forEach((d, idx) => d.classList.toggle('on', idx === wizStep));
        };
        prev.onclick = e => { e.stopPropagation(); if (wizStep > 0) { wizStep--; drawStep(); } };
        next.onclick = e => { e.stopPropagation(); wizStep = (wizStep + 1) % steps.length; drawStep(); };
        stepBox.append(icoEl, txtEl);
        nav.append(prev, dots, next);
        drawStep();

        wiz.append(hd, sub, cmp, stepBox);
        if (deferredInstall) {
          const inst = el('button', TR('Instalar acceso directo'));
          inst.type = 'button';
          inst.style.cssText = 'width:100%;margin-top:10px';
          inst.onclick = async e => {
            e.stopPropagation();
            const ev = deferredInstall; deferredInstall = null;
            try { await ev.prompt(); } catch {}
            shown = ''; render();
          };
          wiz.append(inst);
        }
        wiz.append(nav);
        gate.append(wiz);
      }
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
  addEventListener('touchend', e => { if (!e.target?.closest?.('.wiz')) full(); }, { capture: true });
  gate.addEventListener('click', e => { if (!e.target?.closest?.('.wiz, button')) full(); });

  // Until the game runs it gets no keys or taps (F keys and K, the bindings overlay, stay): a key pressed over the
  // loading screen would land in the first menu.
  const early = () => app.state === 'check' || app.state === 'load';
  for (const t of ['keydown', 'keyup']) addEventListener(t, e => { if (early() && !/^F\d+$/.test(e.code) && e.code !== 'KeyK') { e.preventDefault(); e.stopPropagation(); } }, true);
  addEventListener('pointerdown', e => { if (early() && !e.target.closest?.('#ov, #ov-btn')) { e.preventDefault(); e.stopPropagation(); } }, true);

  render();
  return app;
})();
