// The launcher inside the running game (plan row 10): a corner button opens a panel with quality, game, version, sound and controls (phones: the three profiles).
// The full pre-game launcher stays at /launcher. A choice is saved like the launcher does (RN_LAUNCH.save) and the game reloads with it.
(() => {
  const L = window.RN_LAUNCH;
  if (!L) return;
  const sel = L.load(), defs = Object.fromEntries(L.opts.map(o => [o.id, o.def]));
  const stateOf = p => Object.assign({ ...defs }, p.set);
  const active = () => L.presets.find(p => { const s = stateOf(p); return Object.keys(s).every(k => s[k] === sel[k]); });
  // mode is not sent: L.save stores it for web/mode.js, and a ?mode= in the URL would pin it and break F4 (same as web/launcher.js)
  // Phones start light on every visit (web/mode.js RN_PHONE): the panel shows what runs, and a choice made here lasts this visit only (mode and fx in sessionStorage rn_q).
  if (RN_PHONE && !new URLSearchParams(RN_SEARCH).has('mode')) Object.assign(sel, stateOf(L.presets.find(p => p.id === 'modesto')), { vol: sel.vol });
  const go = () => {
    L.save(sel);
    // The launcher's entry of this visit (web/launcher.js: fast, go, start) stays, so the reload ends where the player came in: main menu or Go Underground.
    const was = new URLSearchParams(RN_SEARCH), trip = ['fast', 'go', 'start'].filter(k => was.has(k)).map(k => k + '=' + was.get(k));
    const q = L.query(sel).split('&').filter(x => x !== 'play=1' && (RN_PHONE || !x.startsWith('mode=')))
      .concat(RN_PHONE && sel.fx !== '0' ? ['fx=1'] : [], trip).join('&');
    try { sessionStorage.setItem('rn_q', q); } catch {}   // this tab's switches (web/index.html RN_SEARCH), never in the address
    location.href = '/';
  };

  const css = document.createElement('style');
  css.textContent = `
    #ov-btn { position: fixed; top: 10px; right: 10px; z-index: 15; width: 34px; height: 34px; border-radius: 50%; border: 1px solid rgba(255,255,255,.25);
      background: linear-gradient(135deg, #ff7a18, #af002d); color: #fff; font: 17px/1 system-ui; cursor: pointer; opacity: .35; padding: 0; display: flex; align-items: center; justify-content: center;
      transition: opacity .16s, transform .12s; }
    #ov-btn:hover, #ov-btn.on { opacity: 1; } #ov-btn:active { transform: scale(.97); }
    #ov { position: fixed; top: 52px; right: 10px; z-index: 15; width: 250px; padding: 12px; display: none; flex-flow: row wrap; gap: 8px;
      background: rgba(12,10,24,.9); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,.14); border-radius: 12px; color: #e8e6f2; font: 13px system-ui, sans-serif; }
    #ov.on { display: flex; } #ov > * { flex: 1 1 100%; } #ov button.h { flex: 1 1 40%; text-align: center; } #ov h4 { margin: 0; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #9a93c0; }
    #ov button, #ov a { font: inherit; color: inherit; text-align: left; padding: 7px 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,.14);
      background: rgba(255,255,255,.06); cursor: pointer; text-decoration: none; transition: transform .12s; }
    #ov button:active { transform: scale(.97); } #ov .sel { background: linear-gradient(135deg, #ff7a18, #af002d); border-color: transparent; }
    #ov small { color: #9a93c0; }
    @media (prefers-reduced-motion: reduce) { #ov-btn, #ov button { transition: none; } }`;
  document.head.appendChild(css);

  const btn = Object.assign(document.createElement('button'), { id: 'ov-btn', title: (window.RN_TR || (s => s))('Opciones') });   // sliders, drawn: the ⚙ glyph is an emoji on phones
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="55%" height="55%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 8h9M19 8h1M4 16h1M11 16h9"/><circle cx="16" cy="8" r="2.4"/><circle cx="8" cy="16" r="2.4"/></svg>';
  btn.tabIndex = -1;
  const panel = Object.assign(document.createElement('div'), { id: 'ov' });
  const toggle = on => { panel.classList.toggle('on', on); btn.classList.toggle('on', on); if (on) render(); else document.getElementById('screen')?.focus(); };
  btn.onclick = () => toggle(!panel.classList.contains('on'));
  function render() {
    const a = active(), muted = sel.vol === '0';
    panel.replaceChildren();
    const add = (tag, text, cls, fn, href) => { const e = Object.assign(document.createElement(tag), { textContent: (window.RN_TR || (s => s))(text) }); if (cls) e.className = cls; if (fn) e.onclick = fn; if (href) e.href = href; e.tabIndex = -1; panel.appendChild(e); };
    if (RN_PHONE) {
      add('h4', 'Perfil');
      for (const p of L.presets) add('button', p.label, a === p ? 'sel' : '', () => { Object.assign(sel, stateOf(p), { vol: sel.vol }); go(); });
    } else {      // computers: the launcher's first board (web/launcher.js), same options, same storage
      const set = (id, v) => () => { sel[id] = v; go(); }, q = L.qualityOf(sel);
      add('h4', 'Calidad' + (q ? '' : ' (a mano)'));
      for (const x of L.quality) add('button', x.label, q === x ? 'sel h' : 'h', () => { Object.assign(sel, x.set); go(); });
      add('h4', 'Versión');
      add('button', 'Remaster', sel.mode === 'remaster' ? 'sel h' : 'h', set('mode', 'remaster')); add('button', 'Original 2003', sel.mode === 'original' ? 'sel h' : 'h', set('mode', 'original'));
    }
    add('h4', 'Sonido');
    add('button', muted ? 'Silenciado (clic para activar)' : 'Sonido activo (clic para silenciar)', muted ? 'sel' : '', () => { sel.vol = muted ? '100' : '0'; go(); });
    add('h4', 'Controles');
    add('button', 'Teclas y mando (K)', '', () => { toggle(false); BINDS.toggle(); });
    const T = window.RN_TOUCH;   // web/touch.js, phones and tablets: these apply at once
    if (T) {
      const t = T.get(), next = (list, v) => list[(list.indexOf(v) + 1) % list.length], set = o => { T.set(o); render(); };
      add('h4', 'Táctil');
      add('button', `Botones: ${{ 25: 'tenues', 35: 'medios', 50: 'visibles' }[t.o] || t.o + ' %'}`, '', () => set({ o: next([25, 35, 50], t.o) }));
    }
    add('small', 'Un cambio aquí reinicia el juego.');
    add('a', 'Todos los ajustes', '', null, 'launcher.html');
  }
  document.body.append(btn, panel);
  addEventListener('keydown', e => { if (e.code === 'Escape' && panel.classList.contains('on')) { e.stopPropagation(); toggle(false); } }, true);
})();
