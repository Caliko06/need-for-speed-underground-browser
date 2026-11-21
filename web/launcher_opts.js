// Option catalog of the launcher (web/launcher.html) and the in-game panel. Plain data plus query/load/save; the UI only renders it.
// `simple` options sit on the first board; the rest fold under Avanzado. `quality` = one-click sets of the same options.
// Every key and value below was checked in the source named in `src`. A URL key wins over the mode (web/mode.js RN_Q).
// A value equal to `def` is not sent: the game uses it anyway. 'auto' means "send nothing, let the mode/device decide".
(() => {
  const T = (v, label) => ({ v, label });
  const OFF_ON = [T('1', 'Sí'), T('0', 'No')];
  const BOTH = ['original', 'remaster'], REM = ['remaster'];

  const groups = [
    { id: 'juego', title: 'Juego', desc: 'Qué se juega y con qué versión.' },
    { id: 'video', title: 'Imagen', desc: 'Calidad visual. Casi todo es del remaster.' },
    { id: 'camara', title: 'Cámara y blur', desc: 'Cómo se siente y se ve la velocidad.' },
    { id: 'rendimiento', title: 'Rendimiento', desc: 'Para equipos modestos.' },
    { id: 'jugabilidad', title: 'Jugabilidad', desc: 'Tráfico, rivales y manejo. Lo de 2003 o lo mejorado.' },
    { id: 'controles', title: 'Sonido y controles', desc: 'Volumen, teclado, mando y pantalla táctil.' },
  ];

  const opts = [
    { id: 'mode', group: 'juego', label: 'Versión', help: 'Original = el juego como salió. Remaster = con texturas y efectos extra.',
      key: 'mode', type: 'choice', values: [T('original', 'Original 2003'), T('remaster', 'Remaster')], def: 'remaster',
      modes: BOTH, src: 'web/mode.js' },

    { id: 'career', group: 'juego', label: 'Progreso de carrera', help: 'Normal: eventos se abren uno por uno. Todo abierto: sin candados.',
      key: 'career', type: 'choice', values: [T('unlock', 'Todo abierto'), T('normal', 'Normal (como salió)')], def: 'unlock',
      modes: BOTH, src: 'web/boot.js' },

    { id: 'remaster', group: 'video', label: 'Texturas del remaster', help: 'Texturas mejoradas de interfaz y coches. Descarga extra grande (1.1 GB), apagadas de inicio.',
      key: 'remaster', type: 'toggle', values: OFF_ON, def: '0', modes: REM, src: 'web/gpu.js' },
    { id: 'skinhd', group: 'video', label: 'Pinturas de coche en HD', help: 'Calcula las pinturas de los coches a mayor resolución.',
      key: 'skinhd', type: 'toggle', values: OFF_ON, def: '1', modes: REM, src: 'web/gpu.js' },
    { id: 'bloom', group: 'video', label: 'Bloom (brillo de luces)', help: 'Halo de luz en faros y neones. "Luces" lo hace más ancho.',
      key: 'bloom', type: 'choice', values: [T('1', 'Normal'), T('lights', 'Luces anchas'), T('0', 'Apagado')], def: '1', modes: REM, src: 'web/gpu.js' },
    { id: 'fxaa', group: 'video', label: 'Suavizado de bordes (FXAA)', help: 'Quita los dientes de sierra en la escena 3D.',
      key: 'fxaa', type: 'toggle', values: OFF_ON, def: '1', modes: REM, src: 'web/gpu.js' },
    { id: 'msaa', group: 'video', label: 'Suavizado MSAA 4x', help: 'Más nítido pero pesa mucho en la GPU.',
      key: 'msaa', type: 'choice', values: [T('1', 'Apagado'), T('4', '4x')], def: '1', modes: REM, src: 'web/gpu.js' },
    { id: 'sharp', group: 'video', label: 'Nitidez', help: 'Afilado al escalar la imagen a tu pantalla.',
      key: 'sharp', type: 'choice', values: [T('off', 'Apagada'), T('0.25', 'Baja'), T('0.5', 'Media'), T('0.75', 'Alta'), T('1', 'Máxima')],
      def: '0.5', modes: REM, src: 'web/gpu.js' },
    { id: 'aniso', group: 'video', label: 'Filtro anisotrópico', help: 'Texturas del piso más claras a lo lejos.',
      key: 'aniso', type: 'choice', values: [T('16', '16x'), T('8', '8x'), T('4', '4x'), T('1', 'Apagado')], def: '16', modes: REM, src: 'web/gpu.js' },
    { id: 'roadrefl', group: 'video', label: 'Reflejo del camino', help: 'Seco (remaster) o como lo dibuja el juego original.',
      key: 'roadrefl', type: 'choice', values: [T('off', 'Seco'), T('game', 'Como el original')], def: 'off', modes: REM, src: 'web/boot.js' },

    { id: 'blur', group: 'camara', label: 'Blur de velocidad', help: 'Original usa "PC original"; Remaster usa "PS2 con profundidad".',
      key: 'blur', type: 'choice',
      values: [T('auto', 'Según el modo'), T('0', 'Sin blur'), T('1', 'Ligero'), T('2', 'Medio'), T('3', 'PS2'), T('4', 'Fuerte'),
        T('5', 'PC original'), T('6', 'PS2 con profundidad')], def: 'auto', modes: BOTH, src: 'web/tune.js' },
    { id: 'chasecam', group: 'camara', label: 'Cámara trasera más inclinada', help: 'Mira el coche desde 8 grados más arriba.',
      key: 'chasecam', type: 'toggle', values: [T('0', 'No'), T('1', 'Sí')], def: '0', modes: REM, src: 'web/tune.js' },
    { id: 'nitrocam', group: 'camara', label: 'Cámara se aleja con nitro', help: 'La cámara retrocede un poco mientras quema el nitro.',
      key: 'nitrocam', type: 'toggle', values: [T('0', 'No'), T('1', 'Sí')], def: '0', modes: REM, src: 'web/tune.js' },
    { id: 'speedfov', group: 'camara', label: 'Campo de visión con velocidad', help: 'El ángulo de visión se abre al ir rápido.',
      key: 'speedfov', type: 'choice', values: [T('0', 'No'), T('5', 'Poco'), T('10', 'Mucho')], def: '0', modes: REM, src: 'web/tune.js' },

    { id: 'fx', group: 'rendimiento', label: 'Efectos del remaster', help: 'No apaga las mejoras de juego, solo los efectos visuales.',
      key: 'fx', type: 'choice', values: [T('1', 'Activados'), T('0', 'Apagados')], def: '1', modes: REM, src: 'web/mode.js' },
    { id: 'fps', group: 'rendimiento', label: 'Fotogramas por segundo', help: '30 pesa la mitad. En iPad o celular ya es 30 por defecto.',
      key: 'fps', type: 'choice', values: [T('60', '60 fps'), T('30', '30 fps')], def: '60', modes: BOTH, src: 'web/boot.js' },
    { id: 'bbmax', group: 'rendimiento', label: 'Resolución', help: 'Ancho máximo de dibujo. Menos píxeles, más fluidez.',
      key: 'bbmax', type: 'choice', values: [T('auto', 'Automática'), T('1280', '1280'), T('1920', '1920'), T('2560', '2560')], def: 'auto',
      modes: BOTH, src: 'web/boot.js' },

    { id: 'vol', group: 'controles', label: 'Volumen', simple: true, slider: true, help: 'Volumen de todo el juego. Los sonidos de este menú ya suenan a ese nivel. Música y efectos por separado, en el menú del juego.',
      key: 'vol', type: 'choice', values: ['0', '10', '20', '30', '40', '50', '60', '70', '80', '90', '100'].map(v => T(v, v === '0' ? 'Sin sonido' : v + ' %')), def: '100', modes: BOTH, src: 'web/audio.js' },

    { id: 'trafyield', group: 'jugabilidad', label: 'El tráfico se hace a un lado', help: 'Los civiles te ven venir por detrás y abren paso.',
      key: 'trafyield', type: 'toggle', values: OFF_ON, def: '1', modes: REM, src: 'host/rivals.c:789' },
    { id: 'handling', group: 'jugabilidad', label: 'Agarre trasero', help: 'Original: como salió el juego. Suelto: la cola derrapa más fácil.',
      key: 'handling', type: 'choice', values: [T('0', 'Original'), T('1', 'Suelto')], def: '0', modes: REM, src: 'web/boot.js, host/rivals.c:673' },
    { id: 'carlook', group: 'video', label: 'Pintura del coche', help: 'Con contraste (remaster) o tal como la dibuja el juego de 2003.',
      key: 'carlook', type: 'choice', values: [T('3', 'Con contraste'), T('2003', 'Como 2003')], def: '3', modes: REM, src: 'host/sm1.c:503' },

    { id: 'touch', group: 'controles', label: 'Controles táctiles', help: 'Automático los muestra solo en pantallas táctiles.',
      key: 'touch', type: 'choice', values: [T('auto', 'Automático'), T('1', 'Mostrar'), T('0', 'Ocultar')], def: 'auto', modes: BOTH, src: 'web/touch.js' },
    { id: 'steer', group: 'controles', label: 'Teclado como mando', help: 'Las flechas giran con el modelo de dirección del mando.',
      key: 'steer', type: 'choice', values: [T('key', 'Teclado normal'), T('pad', 'Como mando')], def: 'key', modes: BOTH, src: 'web/boot.js' },
  ];

  // Calidad: each level writes every key below (a level is active when all of them match). Ultra is never picked for the user: 1.1 GB.
  const Q = (fx, fps, bbmax, skinhd, aniso, msaa, remaster) => ({ fx, fps, bbmax, skinhd, aniso, msaa, remaster });
  const quality = [
    { id: 'baja', label: 'Baja', desc: 'Sin efectos, 30 fps, 1280 de ancho. Para equipos modestos.', set: Q('0', '30', '1280', '1', '16', '1', '0') },
    { id: 'media', label: 'Media', desc: 'Efectos activados, 1920 de ancho, filtros ligeros.', set: Q('1', '60', '1920', '0', '4', '1', '0') },
    { id: 'alta', label: 'Alta', desc: 'Todo activado a la resolución de tu pantalla.', set: Q('1', '60', 'auto', '1', '16', '1', '0') },
    { id: 'ultra', label: 'Ultra', desc: 'Alta más texturas del remaster (descarga de 1.1 GB) y MSAA 4x.', set: Q('1', '60', 'auto', '1', '16', '4', '1') },
  ];
  const qualityOf = sel => quality.find(q => Object.keys(q.set).every(k => sel[k] === q.set[k]));
  // The in-game panel (web/overlay.js) still lists three whole profiles.
  const presets = [
    { id: 'original', label: 'Original 2003', desc: 'El juego como salió, sin extras.', set: { mode: 'original' } },
    { id: 'remaster', label: 'Remaster', desc: 'Texturas y efectos mejorados.', set: { mode: 'remaster' } },
    { id: 'modesto', label: 'Equipo modesto / iPad', desc: 'Original a 30 fps, sin efectos extra.', set: { mode: 'original', fx: '0', fps: '30' } },
  ];

  const byId = Object.fromEntries(opts.map(o => [o.id, o]));
  const defaults = () => Object.fromEntries(opts.map(o => [o.id, o.def]));
  const valid = (o, v) => o.values.some(x => x.v === v);
  const coarse = () => { try { return matchMedia('(pointer: coarse)').matches; } catch { return false; } };
  // fx=0 already turns these off (web/mode.js RN_FX_OFF), so they are not sent then
  const FX_COVERED = new Set(['remaster', 'skinhd', 'bloom', 'fxaa', 'sharp', 'aniso']);
  // RN_FX_OFF also fills these when absent, but they are the player's look rows: sent even at def under fx=0, so the row wins
  // (roadrefl off is also the cheaper one: no mirrored world, PATCH 0x410c1b, host/win32.c)
  const FX_KEEP = new Set(['roadrefl', 'carlook']);

  function query(sel) {
    const s = { ...defaults(), ...sel };
    const mode = valid(byId.mode, s.mode) ? s.mode : 'original';
    const parts = ['play=1', 'mode=' + mode];
    for (const o of opts) {
      if (o.id === 'mode' || !o.modes.includes(mode)) continue;
      const v = valid(o, s[o.id]) ? s[o.id] : o.def;
      if (o.id === 'fps') {
        // coarse pointers get 30 on their own; an explicit 60 must be sent there
        if (v === '60' && coarse()) parts.push('fps=60');
        else if (v === '30') parts.push('fps=30');
        continue;
      }
      // phones get fx=0 on their own (web/mode.js); an explicit 1 must be sent there
      if (o.id === 'fx' && v === '1' && coarse()) { parts.push('fx=1'); continue; }
      if (v === o.def && !(s.fx === '0' && FX_KEEP.has(o.id))) continue;
      if (s.fx === '0' && FX_COVERED.has(o.id)) continue;
      if (o.id === 'steer' && v === 'key') continue;
      if (o.id === 'vol' && v === '0') { parts.push('mute=1'); continue; }
      parts.push(`${o.key}=${encodeURIComponent(v)}`);
    }
    return parts.join('&');
  }

  function load() {
    const sel = defaults();
    try {
      const j = JSON.parse(localStorage.getItem('rn_launch') || '{}');
      for (const o of opts) if (j && typeof j[o.id] === 'string' && valid(o, j[o.id])) sel[o.id] = j[o.id];
      if (!j.mode) { const m = localStorage.getItem('rn_mode'); if (m === 'remaster' || m === 'original') sel.mode = m; }
    } catch {}
    return sel;
  }

  function save(sel) {
    try {
      localStorage.setItem('rn_launch', JSON.stringify(sel));
      localStorage.setItem('rn_mode', sel.mode === 'remaster' ? 'remaster' : 'original');   // web/mode.js and F4 read this
    } catch {}
  }

  // English visits (web/i18n.js): the same catalog, its display strings swapped
  const tr = window.RN_TR || (s => s);
  for (const g of groups) { g.title = tr(g.title); g.desc = tr(g.desc); }
  for (const o of opts) { o.label = tr(o.label); o.help = tr(o.help); for (const v of o.values) v.label = tr(v.label); }
  for (const q of [...quality, ...presets]) { q.label = tr(q.label); q.desc = tr(q.desc); }

  window.RN_LAUNCH = { groups, opts, presets, quality, qualityOf, query, load, save };
})();
