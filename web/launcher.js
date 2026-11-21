// Launcher (UI): one more screen of the game (OWNER 2026-11-15 night, plan row 10): the menus' sheet with JUGAR first.
// Screen A = main menu, the few options a newcomer needs; screen B (Opciones) = every option of web/launcher_opts.js, one group at a time, plus keys and saves.
// The scene behind is window.RN_SCENE (web/launcher_b/scene.js), sound is window.RN_SND (web/launcher_audio.js); both optional, every call is guarded.
// Game font: launcher/v2/ui/game_font.png + .json; labels drawn from it are mask sprites (class gf).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const eq = (a, b) => String(a) === String(b);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const root = document.documentElement, body = document.body;
  // Display copy: noun phrases, neutral Mexican Spanish. The catalog (launcher_opts.js) keeps its own strings; these win when present.
  const COPY = {
    label: { blur: 'Blur de velocidad', fxaa: 'Suavizado FXAA', msaa: 'Suavizado MSAA', chasecam: 'Cámara inclinada', nitrocam: 'Cámara con nitro', speedfov: 'Visión con velocidad', fps: 'Fotogramas', remaster: 'Texturas remaster', skinhd: 'Pinturas en HD', bloom: 'Brillo de luces', roadrefl: 'Reflejo del camino', fx: 'Efectos remaster', trafyield: 'Tráfico se aparta', career: 'Progreso', touch: 'Táctil', steer: 'Giro del teclado', carlook: 'Pintura del coche' },
    group: { camara: 'Cámara' },
  };
  const t = window.RN_TR || (s => s);      // web/i18n.js: Spanish source, English for every non-Spanish browser
  for (const k in COPY) for (const i in COPY[k]) COPY[k][i] = t(COPY[k][i]);
  root.lang = window.RN_LANG || 'es';
  const L = window.RN_LAUNCH;
  const scene = (fn, ...a) => { try { const s = window.RN_SCENE; if (s && typeof s[fn] === 'function') return s[fn](...a); } catch (e) { console.warn('RN_SCENE.' + fn, e); } };
  const snd = n => { try { window.RN_SND && window.RN_SND.play(n); } catch {} };
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
  const wait = ms => new Promise(r => setTimeout(r, ms));

  // ---------- motion switch (default ON, ignores the OS reduce-motion setting) ----------
  let motion = store.get('rn_launch_motion', '1') !== '0';
  const A = (node, frames, opt) => {      // WAAPI; calm mode keeps only opacity and halves the time
    if (!motion) { frames = frames.map(f => { const g = { ...f }; delete g.transform; return g; }); opt = { ...opt, duration: Math.min(opt.duration || 150, 140), delay: Math.min(opt.delay || 0, 60) }; }
    try { return node.animate(frames, opt); } catch { return null; }
  };

  // ---------- the game's font (optional) ----------
  const GF = (() => {
    const g = { ready: false, cbs: [], onReady(f) { if (g.ready) f(); else g.cbs.push(f); }, pending: new Set(), glyphs: null, atlas: null, lh: 0, cap: 0, space: 0 };
    const norm = j => {
      const m = {}; const common = j.common || {};
      const put = (ch, o) => { if (ch == null || !o) return; m[ch] = { x: +o.x, y: +o.y, w: +(o.w ?? o.width), h: +(o.h ?? o.height), ox: +(o.ox ?? o.xo ?? o.xoffset ?? 0), oy: +(o.oy ?? o.yo ?? o.yoffset ?? 0), adv: +(o.adv ?? o.advance ?? o.xadvance ?? (o.w ?? o.width)) }; };
      const src = j.glyphs || j.chars || j;
      if (Array.isArray(src)) for (const o of src) put(o.ch ?? o.char ?? (o.id != null ? String.fromCodePoint(o.id) : null), o);
      else for (const k in src) if (k.length <= 2 && typeof src[k] === 'object') put(k, src[k]);
      g.lh = +(j.lineHeight ?? common.lineHeight ?? j.size ?? j.cell ?? 0); g.base = +(j.base ?? common.base ?? 0);
      return m;
    };
    (async () => {
      try {
        const [jr, img] = await Promise.all([fetch('launcher/v2/ui/game_font.json'), new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'launcher/v2/ui/game_font.png'; })]);
        if (!jr.ok) return;
        const glyphs = norm(await jr.json());
        if (!Object.keys(glyphs).length) return;
        // make an alpha-only atlas: use the PNG's own alpha, or its brightness when it has none
        const c = el('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
        const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0);
        const d = x.getImageData(0, 0, c.width, c.height), px = d.data;
        let hasAlpha = false; for (let i = 3; i < px.length; i += 4) if (px[i] < 250) { hasAlpha = true; break; }
        if (!hasAlpha) for (let i = 0; i < px.length; i += 4) { px[i + 3] = Math.max(px[i], px[i + 1], px[i + 2]); px[i] = px[i + 1] = px[i + 2] = 255; }
        x.putImageData(d, 0, 0);
        g.glyphs = glyphs; g.atlas = c;
        if (!g.lh) g.lh = Math.max(...Object.values(glyphs).map(q => q.oy + q.h));
        g.cap = (glyphs.H || glyphs.E || glyphs.A || { h: g.lh * .7 }).h;
        g.space = (glyphs[' '] && glyphs[' '].adv) || g.cap * .45;
        if (!g.base) g.base = g.lh * .8;
        g.ready = true;
        for (const s of g.pending) g.draw(s);
        g.pending.clear();
        for (const f of g.cbs) f();
        root.classList.add('gfont');
      } catch { /* no game font: the system stack stays */ }
    })();
    g.draw = s => {
      const text = (s._text || '').toUpperCase();
      const S = 1;                                   // atlas pixels are already large enough for a 1080p label
      let w = 0; const gl = ch => g.glyphs[ch] || g.glyphs[ch.toLowerCase()];
      for (const ch of text) { const q = gl(ch); w += q ? q.adv : g.space; }
      if (!w) return;
      const c = el('canvas'); c.width = Math.ceil(w) + 2; c.height = Math.ceil(g.lh) + 2;
      const x = c.getContext('2d'); let cx = 0;
      for (const ch of text) { const q = gl(ch); if (q) { if (q.w > 0 && q.h > 0) x.drawImage(g.atlas, q.x, q.y, q.w, q.h, Math.round(cx + q.ox), Math.round(q.oy), q.w, q.h); cx += q.adv; } else cx += g.space; }
      const hEm = (c.height / g.cap) * 0.72;          // cap height = .72 em, like the system face
      s.style.setProperty('--w', (hEm * c.width / c.height).toFixed(3) + 'em');
      s.style.setProperty('--h', hEm.toFixed(3) + 'em');
      s.style.setProperty('--dy', (((g.lh / 2 - (g.base - g.cap / 2)) / c.height) * hEm).toFixed(3) + 'em');   // centre the capitals, not the line box
      s.style.setProperty('--m', 'url(' + c.toDataURL('image/png') + ')');
      s.classList.add('gf');
    };
    g.apply = s => { if (g.ready) g.draw(s); else g.pending.add(s); };
    return g;
  })();
  const T = text => { const s = el('span', 't', text); s._text = text; GF.apply(s); return s; };
  const setT = (s, text) => { s._text = text; s.textContent = text; s.classList.remove('gf'); GF.apply(s); };

  // ---------- state ----------
  const opts = L.opts, byId = Object.fromEntries(opts.map(o => [o.id, o]));
  const first = store.get('rn_launch', null) === null;      // first visit: nothing saved, the detected level is applied
  let sel = L.load(), sheet = 'A', tab = null, cur = null, going = false, revealed = false;
  let kind = (matchMedia('(hover: none)').matches && matchMedia('(pointer: coarse)').matches) ? 'touch' : 'key';
  const mode = () => sel.mode === 'remaster' ? 'remaster' : 'original';
  const applies = o => !o.modes || o.modes.includes(mode());
  const save = () => L.save(sel);
  const SHOT = { juego: 'hero', video: 'detail', camara: 'rear', rendimiento: 'low', jugabilidad: 'side', controles: 'hero' };   // the camera goes where the option shows
  const helpBox = $('help');
  const setHelp = text => {
    const old = helpBox.querySelector('.dl:last-child');
    if (old && old._v === text) return;
    const nw = el('span', 'dl', text); nw._v = text; helpBox.append(nw);
    if (old) { A(old, [{ opacity: 1 }, { opacity: 0, transform: 'translateY(-.8rem)' }], { duration: 110, fill: 'forwards' }); setTimeout(() => old.remove(), 130);
      A(nw, [{ opacity: 0, transform: 'translateY(.9rem)' }, { opacity: 1, transform: 'none' }], { duration: 180, delay: 50, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' }); }
  };
  // ---------- rows ----------
  // A row is a menu line: the name, then its value between two arrows. row._adj(±1) changes it, row._ok() activates it.
  function rowBase(box, label, help, group) {
    label = t(label); help = t(help);
    const row = el('div', 'row nav'); row.tabIndex = 0;
    const lt = el('span', 'lt'); lt.append(T(label));
    row.append(lt); row.setAttribute('aria-label', label);
    row._help = help; row._group = group;
    box.append(row);
    return row;
  }
  const arrow = (row, dir) => {
    const a = el('button', 'arr ' + (dir < 0 ? 'l' : 'r')); a.type = 'button'; a.tabIndex = -1; a.setAttribute('aria-label', t(dir < 0 ? 'Anterior' : 'Siguiente'));
    a.addEventListener('click', e => { e.stopPropagation(); choose(row); row._adj(dir); });
    return a;
  };
  // a new value wipes in from the side it was pushed from
  const spray = (vv, label, dir) => {
    const nw = T(label), old = vv.firstElementChild;
    vv.append(nw);
    const fit = () => { nw.style.fontSize = ''; const k = (vv.clientWidth - 4) / (nw.offsetWidth || 1); if (k < 1) nw.style.fontSize = (k * 100).toFixed(1) + '%'; };   // the game font is a picture: it shrinks to its cell
    vv._fit = fit; requestAnimationFrame(fit); GF.onReady(() => requestAnimationFrame(fit));
    if (!old) return;
    if (dir === undefined) { old.remove(); return; }
    A(old, [{ opacity: 1 }, { opacity: 0 }], { duration: 90, fill: 'forwards' }); setTimeout(() => old.remove(), 100);
    if (motion) nw.animate([{ clipPath: dir < 0 ? 'inset(0 0 0 100%)' : 'inset(0 100% 0 0)' }, { clipPath: 'inset(0)' }], { duration: 160, delay: 50, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'backwards' });
  };
  const rows = [];
  function choiceRow(box, o) {
    const row = rowBase(box, COPY.label[o.id] || o.label, o.help, o.group);
    const val = el('span', 'val'), vv = el('span', 'vv');
    val.append(arrow(row, -1), vv, arrow(row, 1)); row.append(val);
    row.setAttribute('role', 'spinbutton');
    row._o = o;
    row._adj = d => { const i = Math.max(0, o.values.findIndex(x => x.v === sel[o.id])); setOpt(o.id, o.values[(i + d + o.values.length) % o.values.length].v, d); };
    row._paint = dir => { const x = o.values.find(y => y.v === sel[o.id]), label = x ? x.label : sel[o.id]; if (row._v !== label) { row._v = label; spray(vv, label, dir); row.setAttribute('aria-valuetext', label); } };
    rows.push(row); return row;
  }
  // volume: ‹ 70 % › like every other line (OWNER 2026-11-17: the bare bar and number did not read), the level as a bar under the value.
  // It stops at 0 and 100 instead of wrapping; a click or drag on the value sets it too. The menu's own sounds follow it (sndVol).
  function sliderRow(box, o) {
    const row = rowBase(box, o.label, o.help, o.group);
    const val = el('span', 'val'), vv = el('span', 'vv lvl');
    val.append(arrow(row, -1), vv, arrow(row, 1)); row.append(val);
    row.setAttribute('role', 'slider'); row.setAttribute('aria-valuemin', '0'); row.setAttribute('aria-valuemax', '100'); row._o = o;
    const n = o.values.length - 1, idx = () => Math.max(0, o.values.findIndex(x => x.v === sel[o.id]));
    row._adj = d => { const i = clamp(idx() + d, 0, n); if (i !== idx()) setOpt(o.id, o.values[i].v, d); else snd('back'); };
    row._paint = dir => { const i = idx(), label = o.values[i].label; vv.style.setProperty('--p', i / n); row.setAttribute('aria-valuenow', o.values[i].v); row.setAttribute('aria-valuetext', label); if (row._v !== label) { row._v = label; spray(vv, label, dir); } };
    const drag = e => { const r = vv.getBoundingClientRect(), i = Math.round(clamp((e.clientX - r.left) / r.width, 0, 1) * n); if (i !== idx()) setOpt(o.id, o.values[i].v, i > idx() ? 1 : -1); };
    vv.addEventListener('pointerdown', e => { e.stopPropagation(); vv.setPointerCapture(e.pointerId); choose(row); drag(e); vv.onpointermove = drag; });
    vv.addEventListener('pointerup', () => { vv.onpointermove = null; });
    vv.addEventListener('click', e => e.stopPropagation());
    rows.push(row); return row;
  }
  function actionRow(box, label, help, group, fn, value) {
    const row = rowBase(box, label, help, group);
    const val = el('span', 'val act'), vv = el('span', 'vv'); value = t(value || 'Abrir'); vv.append(T(value)); val.append(vv, arrow(row, 1)); row.append(val);
    row.setAttribute('role', 'button');
    row._say = m => { spray(vv, t(m), 1); setTimeout(() => spray(vv, value, -1), 2000); };
    row._ok = () => fn(row); row._adj = d => { if (d > 0) fn(row); };
    return row;
  }

  // screen A: the entries (OWNER 2026-11-16; WORLD retired 2026-11-17, attic/world/README.md) Jugar = the game's main menu, Carrera = Go Underground
  // (left / right: everything open or the 2003 progress); then Calidad, Volumen, Controles, Opciones
  $('titleA').append(T(t('Menú principal'))); $('play').append(T(t('Jugar'))); $('more').append(T(t('Opciones'))); $('less').append(T(t('Volver')));
  $('guides').append(T(t('Guías'))); $('guides').href = 'blog/' + (window.RN_LANG === 'es' ? 'es' : 'en') + '/index.html';
  for (const [id, a, s] of [['board', 'aria-label', 'Menú'], ['play', 'aria-label', 'Jugar'], ['tabPrev', 'aria-label', 'Grupo anterior'], ['tabNext', 'aria-label', 'Grupo siguiente'], ['tabs', 'aria-label', 'Grupos de ajustes'], ['btnSnd', 'title', 'Sonido del menú (M)'], ['btnMot', 'title', 'Animación']]) $(id).setAttribute(a, t(s));
  $('rig').querySelector('b').textContent = t('Tu equipo'); $('rigName').textContent = t('midiendo');
  const simple = $('simple'), adv = $('adv');
  const HELP = { play: 'Abre el juego en su menú principal.' };
  const cRow = choiceRow(simple, opts.find(o => o.id === 'career'));
  cRow.querySelector('.lt').replaceChildren(T(t('Carrera'))); cRow.setAttribute('aria-label', t('Carrera'));
  cRow._help = t('Directo a Go Underground, la carrera de 2003. Izquierda o derecha: todo abierto o el progreso normal. Enter para entrar.');
  cRow._ok = () => launch('career');
  const qRow = rowBase(simple, 'Calidad', '', 'rendimiento');
  {
    const val = el('span', 'val'), vv = el('span', 'vv'); val.append(arrow(qRow, -1), vv, arrow(qRow, 1)); qRow.append(val);
    qRow._adj = d => { const q = L.qualityOf(sel), i = q ? L.quality.indexOf(q) : (d > 0 ? -1 : 0); const nq = L.quality[(i + d + L.quality.length) % L.quality.length]; Object.assign(sel, nq.set); changed(d); };
    qRow._paint = dir => { const q = L.qualityOf(sel), label = q ? q.label : t('A mano'); qRow._help = q ? q.desc : t('Ajustes tocados uno por uno en Avanzado.'); if (qRow._v !== label) { qRow._v = label; spray(vv, label, dir); } };
    rows.push(qRow);
  }
  for (const o of opts) if (o.simple) (o.slider ? sliderRow : choiceRow)(simple, o);
  actionRow(simple, 'Controles', 'Teclas, mando y pantalla táctil. Todo se puede reasignar.', 'controles', () => { openAdv('controles'); }, 'Ver');
  // Idioma (OWNER 2026-11-17): each language named in itself; the choice is kept (web/i18n.js 'rn_lang') and the page reloads in it,
  // back on this same line. The game's in-page panel (web/index.html) reads the same key.
  const LANGS = [['es', 'Español'], ['en', 'English']];
  const langRow = rowBase(simple, 'Idioma', 'Idioma del menú, las guías y el panel del juego. El juego en sí está en inglés, como salió.', 'juego');
  {
    const val = el('span', 'val'), vv = el('span', 'vv'); val.append(arrow(langRow, -1), vv, arrow(langRow, 1)); langRow.append(val);
    langRow.setAttribute('role', 'spinbutton');
    const now = LANGS.findIndex(x => x[0] === (window.RN_LANG || 'es'));
    langRow._paint = () => { if (!langRow._v) { langRow._v = LANGS[now][1]; spray(vv, langRow._v); } };
    langRow._adj = d => {
      if (going) return;
      const nx = LANGS[(now + d + LANGS.length) % LANGS.length];
      going = true; snd('tab'); spray(vv, nx[1], d); store.set('rn_lang', nx[0]);
      try { sessionStorage.setItem('rn_launch_at', 'lang'); } catch {}
      setTimeout(() => location.reload(), motion ? 220 : 60);
    };
    langRow._ok = () => langRow._adj(1);
    rows.push(langRow);
  }

  // sheet B: every option, by group
  const groups = L.groups.filter(g => opts.some(o => o.group === g.id)).concat([{ id: 'partidas', title: t('Partidas') }]);
  for (const o of opts) { const r = (o.slider ? sliderRow : choiceRow)(adv, o); r._adv = true; }
  const keysRow = actionRow(adv, 'Teclas y mando', 'Clic en una acción y luego la tecla o el botón. También con K dentro del juego.', 'controles', () => { snd('accept'); BINDS.toggle(); }); keysRow._adv = true;
  const bak = actionRow(adv, 'Guardar copia', 'Descarga tus partidas de este navegador en un archivo.', 'partidas', r => RN_SAVES.backup().then(n => r._say(n ? 'Listo' : 'Sin partidas'), () => r._say('Error')), 'Bajar');
  const res = actionRow(adv, 'Restaurar copia', 'Carga un archivo de partidas descargado antes.', 'partidas', () => $('fileRes').click(), 'Elegir');
  const rst = actionRow(adv, 'Ajustes de fábrica', 'Todos los ajustes vuelven a su valor inicial. Las partidas no se tocan.', 'partidas', r => { sel = Object.fromEntries(opts.map(o => [o.id, o.def])); changed(0); r._say('Hecho'); }, 'Borrar');
  for (const r of [bak, res, rst]) r._adv = true;
  $('fileRes').addEventListener('change', () => { const f = $('fileRes').files[0]; $('fileRes').value = ''; if (f) RN_SAVES.restore(f).then(() => res._say('Restaurado'), () => res._say('Archivo inválido')); });
  const tabBtns = groups.map(g => {
    const b = el('span', 'gtab'); b.setAttribute('role', 'tab'); b.append(T(COPY.group[g.id] || g.title));
    $('tabs').append(b); return { g, b };
  });

  function paint(dir) {
    for (const r of rows) { r._paint(dir); if (r._adv) r.hidden = r._group !== tab || (r._o && !applies(r._o)); }
    for (const r of [keysRow, bak, res, rst]) r.hidden = r._group !== tab;
    for (const { g, b } of tabBtns) { b.setAttribute('aria-selected', String(g.id === tab)); b.hidden = g.id !== 'partidas' && !opts.some(o => o.group === g.id && applies(o)); }
    const vis = tabBtns.filter(x => !x.b.hidden), gi = vis.findIndex(x => x.g.id === tab);
    $('tabCount').textContent = gi < 0 ? '' : `${gi + 1} / ${vis.length}` + (vis[gi].g.desc ? '   ' + vis[gi].g.desc : '');
    if (cur && cur._help !== undefined) setHelp(cur._help || '');
  }
  // the menu's sounds at the chosen volume, squared like the game's own gain (web/audio.js), so a change is heard at its new level
  const sndVol = () => { try { window.RN_SND && window.RN_SND.volume && window.RN_SND.volume(Number(sel.vol) / 100); } catch {} };
  sndVol();
  function changed(dir) { save(); paint(dir); sndVol(); snd('tab'); scene('pulse'); if (cur && motion) { const lt = cur.querySelector('.lt'); if (lt) lt.animate([{ transform: 'scale(.97)' }, { transform: 'none' }], { duration: 140, easing: 'cubic-bezier(.16,1,.3,1)' }); } }
  function setOpt(id, v, dir) { sel[id] = v; changed(dir); }

  // ---------- navigation: one list per screen, JUGAR first ----------
  const items = () => sheet === 'A' ? [...simple.children, $('more'), $('guides')] : [...[...adv.children].filter(r => !r.hidden), $('less')];
  function choose(node, o = {}) {
    if (!node || cur === node) return;
    if (cur) cur.classList.remove('sel');
    cur = node; node.classList.add('sel');
    if (document.activeElement !== node) node.focus({ preventScroll: true });
    if (node.parentElement === adv) node.scrollIntoView({ block: 'nearest', behavior: motion ? 'smooth' : 'auto' });
    if (!o.quiet) snd('move');
    setHelp(HELP[node.id] ? t(HELP[node.id]) : node === $('more') ? t('Imagen, cámara, rendimiento, jugabilidad, teclas y partidas.') : node === $('guides') ? t('Cómo jugar, controles y cómo se hizo.') : node === $('less') ? t('Vuelve al menú principal.') : node._help || '');
    scene('shot', node === $('play') ? null : SHOT[node._group] || 'hero');
  }
  const step = d => { const l = items(), i = l.indexOf(cur); choose(l[i < 0 ? 0 : (i + d + l.length) % l.length]); };
  function setTab(id, dir) {
    tab = id; paint();
    adv.scrollTop = 0;
    const vis = [...adv.children].filter(r => !r.hidden);
    for (const r of vis) { const vv = r.querySelector('.vv'); if (vv && vv._fit) vv._fit(); }
    // the group's lines come in from the side it was browsed from, one after the other
    vis.slice(0, 12).forEach((r, i) => A(r, [{ opacity: 0, transform: `translateX(${dir >= 0 ? 3 : -3}rem)` }, { opacity: 1, transform: 'none' }], { duration: 170, delay: i * 22, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' }));
    A($('tabs'), [{ opacity: 0, transform: `translateX(${dir >= 0 ? 2 : -2}rem)` }, { opacity: 1, transform: 'none' }], { duration: 150, easing: 'cubic-bezier(.16,1,.3,1)' });
    if (sheet === 'B' && vis[0]) choose(vis[0], { quiet: true });
  }
  function flip(to) {      // the other screen slides onto the sheet
    sheet = to; const a = $('sheetA'), b = $('sheetB'), on = to === 'B' ? b : a, off = to === 'B' ? a : b;
    off.hidden = true; on.hidden = false; $('board').dataset.sheet = to;
    A(on, [{ opacity: 0, transform: `translateX(${to === 'B' ? 4 : -4}rem)` }, { opacity: 1, transform: 'none' }], { duration: to === 'B' ? 220 : 150, easing: 'cubic-bezier(.16,1,.3,1)' });   // closing is faster than opening
    hints();
  }
  function openAdv(id) { snd('accept'); flip('B'); setTab(id || tab || groups[0].id, 1); }
  function closeAdv() { if (sheet !== 'B') return; snd('back'); flip('A'); cur = null; paint(); choose($('more'), { quiet: true }); }
  $('more').addEventListener('click', () => openAdv());
  $('less').addEventListener('click', closeAdv);
  $('tabPrev').addEventListener('click', () => tabStep(-1)); $('tabNext').addEventListener('click', () => tabStep(1));
  const tabStep = d => { if (sheet !== 'B') return; const vis = tabBtns.filter(x => !x.b.hidden), i = vis.findIndex(x => x.g.id === tab); snd('tab'); setTab(vis[(i + d + vis.length) % vis.length].g.id, d); };

  // ---------- detect the machine (first visit: its level is applied) ----------
  async function detect() {
    const rig = $('rigName');
    let gpu = '', ok = !!navigator.gpu;
    try { const a = ok && await navigator.gpu.requestAdapter(); ok = !!a; const i = a && a.info; if (i) gpu = [i.vendor, i.architecture || i.device].filter(Boolean).join(' '); } catch { ok = false; }
    // No WebGPU: the game draws through WebGL 2 (web/boot.js loads web/webgpu_gl.js); only a browser with neither stops here.
    if (!ok && !document.createElement('canvas').getContext('webgl2')) { rig.textContent = t('Este navegador no tiene WebGPU ni WebGL 2. Usa Chrome, Edge, Safari o Firefox recientes.'); $('rig').classList.add('bad'); return; }
    if (!ok) gpu = 'WebGL 2';
    // how fast this machine draws the street behind (median of 90 frames once the menu is in)
    const ms = await new Promise(done => { const d = []; let last = 0; const f = t => { if (last) d.push(t - last); last = t; if (d.length < 90) requestAnimationFrame(f); else done(d.sort((a, b) => a - b)[45]); }; requestAnimationFrame(f); setTimeout(() => done(d.length ? d.sort((a, b) => a - b)[d.length >> 1] : 99), 4000); });
    const tier = ms > 28 ? 'baja' : ms > 20 ? 'media' : 'alta';      // thresholds are ours (60 Hz = 16.7 ms)
    const q = L.quality.find(x => x.id === tier);
    $('rig').querySelector('b').textContent = gpu || t('Tu equipo');
    rig.textContent = t('Va bien en ') + q.label;
    $('rig').title = t('La escena de este menú corre a {ms} ms por cuadro en tu equipo.').replace('{ms}', ms.toFixed(1));
    if (first && L.qualityOf(sel) && !detect.touched) { Object.assign(sel, q.set); save(); paint(1); }
    A($('rig'), [{ opacity: 0 }, { opacity: 1 }], { duration: 200 });
  }

  // ---------- confirm: headlights, push-in (RN_SCENE.confirm), fade, then go ----------
  async function launch(start = 'menu') {
    if (going) return;
    going = true; save();
    const u = new URLSearchParams(L.query(sel)); if (!matchMedia('(pointer: coarse)').matches) u.delete('mode'); u.set('play', '1'); u.set('fast', '1'); u.set('go', '1'); u.set('start', start);
      // mode: stored (web/mode.js); a ?mode= would pin it and break F4. Phones keep it: web/mode.js ignores the stored mode there
    snd('accept'); try { window.RN_SND && window.RN_SND.fadeOut(900); } catch {}
    body.classList.add('leaving');
    await Promise.race([Promise.resolve(scene('confirm')).catch(() => 0), wait(1800)]);
    $('fade').classList.add('on');
    await wait(motion ? 220 : 120);
    try { sessionStorage.setItem('rn_q', u.toString()); } catch {}   // web/index.html RN_SEARCH: the switches stay out of the address
    location.href = '/';
  }
  $('play').addEventListener('click', () => launch());
  addEventListener('pageshow', e => { if (e.persisted) { going = false; body.classList.remove('leaving'); $('fade').classList.remove('on'); } });

  // ---------- key hints ----------
  const bar = $('keys'), K = (c, t) => `<kbd class="${c || ''}">${t}</kbd>`;
  function hints() {
    const pad = kind === 'pad', h = (k, label, act) => act ? `<button type="button" class="hint" data-act="${act}">${k}<span>${label}</span></button>` : `<span class="hint nb">${k}<span>${label}</span></span>`;
    const out = [];
    if (kind !== 'touch') {
      out.push(h(K('wide', pad ? '↕' : '↑↓'), t('Elegir')), h(K('wide', pad ? '↔' : '←→'), t('Cambiar')));
      if (sheet === 'B') out.push(h(pad ? K('wide', 'LB') + K('wide', 'RB') : K('', 'Q') + K('', 'E'), t('Grupo')), h(pad ? K('pad b', 'B') : K('wide', 'Esc'), t('Volver'), 'back'));
      if (sheet === 'A') out.push(h(pad ? K('wide', 'Start') : K('wide', '↵'), t('Jugar'), 'play'));   // in Opciones Enter changes the value, it does not start
    } else if (sheet === 'B') out.push(h(K('wide', '←'), t('Volver'), 'back'));
    bar.innerHTML = out.join('');
  }
  bar.addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (b) act(b.dataset.act); });
  const setKind = k => { if (k !== kind) { kind = k; body.classList.toggle('touch', k === 'touch'); hints(); } };

  // ---------- sound and animation switches ----------
  const btnSnd = $('btnSnd'), btnMot = $('btnMot');
  const sndOn = () => !window.RN_SND || window.RN_SND.isOn();
  const paintSnd = () => { btnSnd.setAttribute('aria-pressed', String(sndOn())); btnSnd.querySelector('.sl').textContent = t(sndOn() ? 'Sonido: sí' : 'Sonido: no'); };
  if (window.RN_SND) window.RN_SND.onChange(paintSnd); else btnSnd.hidden = true;
  const toggleSnd = () => { window.RN_SND.init(); window.RN_SND.toggle(); if (sndOn()) snd('accept'); };
  btnSnd.addEventListener('click', toggleSnd);
  paintSnd();
  const setMotion = on => { motion = on; root.classList.toggle('calm', !on); btnMot.setAttribute('aria-pressed', String(on)); btnMot.querySelector('.ml').textContent = t(on ? 'Animación: sí' : 'Animación: no'); store.set('rn_launch_motion', on ? '1' : '0'); scene('motion', on); };
  btnMot.addEventListener('click', () => setMotion(!motion));
  setMotion(motion);

  // ---------- input ----------
  function act(name) {
    if (going || BINDS.open) return;
    if (!revealed) { reveal(); return; }
    detect.touched = true;
    switch (name) {
      case 'up': step(-1); break;
      case 'down': step(1); break;
      case 'left': if (cur && cur._adj) cur._adj(-1); break;
      case 'right': if (cur && cur._adj) cur._adj(1); else if (cur === $('play')) step(1); break;
      case 'ok': if (!cur) step(0); else if (cur._ok) cur._ok(); else if (cur._adj) cur._adj(1); else cur.click(); break;
      case 'back': closeAdv(); break;
      case 'play': launch(); break;
      case 'tab-': tabStep(-1); break;
      case 'tab+': tabStep(1); break;
    }
  }
  document.addEventListener('pointerover', e => { if (e.pointerType === 'touch' || going || !revealed) return; const n = e.target.closest && e.target.closest('.nav'); if (n && items().includes(n)) choose(n); });
  document.addEventListener('pointerdown', e => { setKind(e.pointerType === 'touch' ? 'touch' : 'key'); if (!revealed) { reveal(); return; } detect.touched = true; const n = e.target.closest && e.target.closest('.nav'); if (n && items().includes(n)) choose(n); });
  for (const box of [simple, adv]) box.addEventListener('click', e => { const r = e.target.closest('.row'); if (r && !e.target.closest('.arr, .track')) { if (r._ok) r._ok(); else r._adj(1); } });
  document.addEventListener('focusin', e => { const n = e.target.closest && e.target.closest('.nav'); if (revealed && n && items().includes(n)) choose(n, { quiet: true }); });   // Tab moves the selection too
  const KEYS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Escape: 'back', Backspace: 'back', PageUp: 'tab-', PageDown: 'tab+', q: 'tab-', Q: 'tab-', e: 'tab+', E: 'tab+' };
  addEventListener('keydown', e => {
    if (e.altKey || e.ctrlKey || e.metaKey || BINDS.open) return;
    setKind('key');
    if (e.key === 'm' || e.key === 'M') { e.preventDefault(); if (!e.repeat && window.RN_SND) toggleSnd(); return; }
    const a = KEYS[e.key];
    if (a) { e.preventDefault(); if (!(e.repeat && a !== 'up' && a !== 'down' && a !== 'left' && a !== 'right')) act(a); return; }
    if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest && e.target.closest('.tool, .keys button, .arr, .gtab')) return; e.preventDefault(); if (!e.repeat) act('ok'); }
  });

  // pointer -> scene parallax
  let pRaf = 0, pxn = 0, pyn = 0;
  const setPointer = (x, y) => { pxn = clamp(x, -1, 1); pyn = clamp(y, -1, 1); if (!pRaf) pRaf = requestAnimationFrame(() => { pRaf = 0; scene('pointer', pxn, pyn); }); };
  addEventListener('pointermove', e => { if (e.pointerType !== 'touch') setPointer(e.clientX / innerWidth * 2 - 1, e.clientY / innerHeight * 2 - 1); });
  root.addEventListener('mouseleave', () => setPointer(0, 0));

  // gamepad: d-pad / left stick = move, A / B / LB / RB / Start, right stick = parallax
  const held = {};
  let polling = false;
  const fire = (name, down, now, repeat) => {
    if (!down) { delete held[name]; return false; }
    if (!(name in held)) { held[name] = now + (repeat ? 380 : Infinity); return true; }
    if (repeat && now >= held[name]) { held[name] = now + 130; return true; }
    return false;
  };
  function poll(now) {
    const pads = (navigator.getGamepads ? [...navigator.getGamepads()] : []).filter(Boolean);
    if (!pads.length) { polling = false; return; }
    const b = i => pads.some(p => p.buttons[i] && p.buttons[i].pressed), ax = (i, s) => pads.some(p => (p.axes[i] || 0) * s > 0.55);
    let used = false;
    const press = (name, down, repeat, a) => { if (fire(name, down, now, repeat)) { used = true; act(a); } };
    press('l', b(14) || ax(0, -1), true, 'left'); press('r', b(15) || ax(0, 1), true, 'right');
    press('u', b(12) || ax(1, -1), true, 'up'); press('d', b(13) || ax(1, 1), true, 'down');
    press('a', b(0), false, 'ok'); press('b', b(1), false, 'back'); press('s', b(9), false, 'play');
    press('lb', b(4), false, 'tab-'); press('rb', b(5), false, 'tab+');
    const p0 = pads[0], rx = p0.axes[2] || 0, ry = p0.axes[3] || 0;
    if (Math.abs(rx) > .15 || Math.abs(ry) > .15) setPointer(rx, ry);
    if (used) { setKind('pad'); try { window.RN_SND && window.RN_SND.init(); } catch {} }
    requestAnimationFrame(poll);
  }
  const startPolling = () => { if (!polling) { polling = true; requestAnimationFrame(poll); } };
  addEventListener('gamepadconnected', startPolling);
  if (navigator.getGamepads && [...navigator.getGamepads()].some(Boolean)) startPolling();

  // ---------- start: the UI comes in at once; the scene follows behind ----------
  function reveal() {
    if (revealed) return;
    revealed = true;
    body.classList.remove('boot');
    const e = 'cubic-bezier(.16,1,.3,1)';
    A(document.querySelector('.tools'), [{ opacity: 0 }, { opacity: 1 }], { duration: 280, delay: 200, easing: e, fill: 'backwards' });
    // the sheet slides in from its side, then its lines one after the other
    A($('board'), [{ opacity: 0, transform: 'translateX(8rem)' }, { opacity: 1, transform: 'none' }], { duration: 280, easing: e, fill: 'backwards' });
    [$('titleA'), ...simple.children, $('more'), $('guides')].forEach((r, i) => A(r, [{ opacity: 0, transform: 'translateX(4rem)' }, { opacity: 1, transform: 'none' }], { duration: 200, delay: 140 + i * 35, easing: e, fill: 'backwards' }));
    setTimeout(detect, 900);
  }
  body.classList.toggle('touch', kind === 'touch');
  tab = groups[0].id; paint(); hints();
  { let at = null; try { at = sessionStorage.getItem('rn_launch_at'); sessionStorage.removeItem('rn_launch_at'); } catch {}
    choose(at === 'lang' ? langRow : $('play'), { quiet: true }); }
  // The menu comes in at once (OWNER 2026-11-17: "no abre de inmediato"; it used to wait for the 3D street, ~6 s cold).
  // The street (web/launcher_b/scene.js, PlayCanvas + 16 MB) loads behind it and starts when its module has run ('rn-scene').
  reveal();
  const startScene = () => {
    const S = window.RN_SCENE;
    if (!S || typeof S.start !== 'function') return;
    Promise.resolve().then(() => S.start($('scene'), {})).then(() => scene('motion', motion), e => { console.warn('RN_SCENE.start', e); root.classList.add('static'); });
  };
  if (window.RN_SCENE) startScene(); else addEventListener('rn-scene', startScene, { once: true });
})();
