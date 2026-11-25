// Language of the launcher, the option catalog and the page panels (OWNER 2026-11-16: English and Spanish, by the visitor's region).
// A browser set to Spanish gets Spanish; every other one gets English. ?lang=es|en forces one (tests); the launcher's Idioma line
// keeps the visitor's own choice in localStorage 'rn_lang' (OWNER 2026-11-17), which wins over the browser.
// The code keeps its Spanish strings; RN_TR(s) returns the English line when the visit is English, and s itself when there is none.
// Loaded first by web/launcher.html and web/index.html. The game itself is English only (its own text, not ours).
(() => {
  let l = 'en';
  try { l = new URLSearchParams(location.search).get('lang') || localStorage.getItem('rn_lang') || navigator.language || 'en'; } catch {}
  const lang = /^es/i.test(l) ? 'es' : 'en';
  const EN = {
    // web/launcher_opts.js: groups
    'Juego': 'Game', 'Qué se juega y con qué versión.': 'What you play and which version.',
    'Imagen': 'Picture', 'Calidad visual. Casi todo es del remaster.': 'Visual quality. Most of it belongs to the remaster.',
    'Cámara y blur': 'Camera and blur', 'Cámara': 'Camera', 'Cómo se siente y se ve la velocidad.': 'How speed looks and feels.',
    'Rendimiento': 'Performance', 'Para equipos modestos.': 'For modest machines.',
    'Jugabilidad': 'Gameplay', 'Tráfico, rivales y manejo. Lo de 2003 o lo mejorado.': 'Traffic, rivals and handling. As in 2003, or improved.',
    'Sonido y controles': 'Sound and controls', 'Volumen, teclado, mando y pantalla táctil.': 'Volume, keyboard, gamepad and touch screen.',
    'Partidas': 'Saves',
    // options
    'Carrera': 'Career', 'Versión': 'Version', 'Original = el juego como salió. Remaster = con texturas y efectos extra.': 'Original = the game as it shipped. Remaster = with extra textures and effects.',
    'Progreso de carrera': 'Career progress', 'Progreso': 'Progress', 'Normal: eventos se abren uno por uno. Todo abierto: sin candados.': 'Normal: events open one by one. All open: no locks.',
    'Todo abierto': 'All open', 'Normal (como salió)': 'Normal (as shipped)',
    'Texturas del remaster': 'Remaster textures', 'Texturas remaster': 'Remaster textures',
    'Texturas mejoradas de interfaz, coches y ciudad. Descarga extra grande (1.1 GB), apagadas de inicio.': 'Better textures for the menus, the cars and the city. A big extra download (1.1 GB), off at the start.',
    'Pinturas de coche en HD': 'HD car paint', 'Pinturas en HD': 'HD car paint', 'Calcula las pinturas de los coches a mayor resolución.': 'Builds the car paint at a higher resolution.',
    'Bloom (brillo de luces)': 'Bloom (light glow)', 'Brillo de luces': 'Light glow', 'Halo de luz en faros y neones. "Luces" lo hace más ancho.': 'A halo on headlights and neon. "Wide lights" makes it wider.',
    'Luces anchas': 'Wide lights', 'Apagado': 'Off', 'Apagada': 'Off', 'Apagados': 'Off', 'Activados': 'On',
    'Suavizado de bordes (FXAA)': 'Edge smoothing (FXAA)', 'Suavizado FXAA': 'FXAA smoothing', 'Quita los dientes de sierra en la escena 3D.': 'Removes the jagged edges of the 3D scene.',
    'Suavizado MSAA 4x': 'MSAA 4x smoothing', 'Suavizado MSAA': 'MSAA smoothing', 'Más nítido pero pesa mucho en la GPU.': 'Sharper, but heavy on the GPU.',
    'Nitidez': 'Sharpness', 'Afilado al escalar la imagen a tu pantalla.': 'Sharpening when the picture is scaled to your screen.',
    'Baja': 'Low', 'Media': 'Medium', 'Alta': 'High', 'Máxima': 'Maximum',
    'Filtro anisotrópico': 'Anisotropic filter', 'Texturas del piso más claras a lo lejos.': 'Clearer road textures in the distance.',
    'Reflejo del camino': 'Road reflection', 'Seco (remaster) o como lo dibuja el juego original.': 'Dry (remaster) or as the original game draws it.',
    'Seco': 'Dry', 'Como el original': 'As the original',
    'Blur de velocidad': 'Speed blur', 'Original usa "PC original"; Remaster usa "PS2 con profundidad".': 'Original uses "Original PC"; Remaster uses "PS2 with depth".',
    'Según el modo': 'By mode', 'Sin blur': 'No blur', 'Ligero': 'Light', 'Medio': 'Medium', 'Fuerte': 'Strong', 'PC original': 'Original PC', 'PS2 con profundidad': 'PS2 with depth',
    'Cámara trasera más inclinada': 'Steeper chase camera', 'Cámara inclinada': 'Steeper camera', 'Mira el coche desde 8 grados más arriba.': 'Looks at the car from 8 degrees higher.',
    'Sí': 'Yes',
    'Cámara se aleja con nitro': 'Camera pulls back on nitrous', 'Cámara con nitro': 'Nitrous camera', 'La cámara retrocede un poco mientras quema el nitro.': 'The camera pulls back a little while the nitrous burns.',
    'Campo de visión con velocidad': 'Field of view with speed', 'Visión con velocidad': 'Speed field of view', 'El ángulo de visión se abre al ir rápido.': 'The view angle opens up as you go faster.',
    'Poco': 'A little', 'Mucho': 'A lot',
    'Efectos del remaster': 'Remaster effects', 'Efectos remaster': 'Remaster effects', 'No apaga las mejoras de juego, solo los efectos visuales.': 'Turns off the visual effects only, not the gameplay improvements.',
    'Fotogramas por segundo': 'Frames per second', 'Fotogramas': 'Frame rate', '30 pesa la mitad. En iPad o celular ya es 30 por defecto.': '30 is half the work. On an iPad or a phone it is already 30.',
    'Resolución': 'Resolution', 'Ancho máximo de dibujo. Menos píxeles, más fluidez.': 'Widest picture drawn. Fewer pixels, smoother play.', 'Automática': 'Automatic',
    'Volumen': 'Volume', 'Sin sonido': 'Muted', 'Idioma': 'Language', 'Idioma del menú, las guías y el panel del juego. El juego en sí está en inglés, como salió.': 'Language of this menu, the guides and the in-game panel. The game itself is in English, as it shipped.', 'Volumen de todo el juego. Los sonidos de este menú ya suenan a ese nivel. Música y efectos por separado, en el menú del juego.': 'Volume of the whole game. The sounds of this menu already play at that level. Music and effects have their own sliders in the game menu.',
    'Tráfico': 'Traffic',
    'Rivales con personalidad': 'Rivals with personality', 'Rivales con carácter': 'Rivals with character', 'Nerviosos, limpios o agresivos. Apagado: corren como en 2003.': 'Nervous, clean or aggressive. Off: they race as in 2003.',
    'El tráfico se hace a un lado': 'Traffic moves aside', 'Tráfico se aparta': 'Traffic moves aside', 'Los civiles te ven venir por detrás y abren paso.': 'Civilians see you coming from behind and make room.',
    'Agarre trasero': 'Rear grip', 'Original: como salió el juego. Suelto: la cola derrapa más fácil.': 'Original: as the game shipped. Loose: the tail slides more easily.', 'Suelto': 'Loose',
    'Pintura del coche': 'Car paint', 'Con contraste (remaster) o tal como la dibuja el juego de 2003.': 'With contrast (remaster) or just as the 2003 game draws it.',
    'Con contraste': 'With contrast', 'Como 2003': 'As in 2003',
    'Controles táctiles': 'Touch controls', 'Táctil': 'Touch', 'Automático los muestra solo en pantallas táctiles.': 'Automatic shows them on touch screens only.',
    'Automático': 'Automatic', 'Mostrar': 'Show', 'Ocultar': 'Hide',
    'Teclado como mando': 'Keyboard as a gamepad', 'Giro del teclado': 'Keyboard steering', 'Las flechas giran con el modelo de dirección del mando.': 'The arrow keys steer with the gamepad steering model.',
    'Teclado normal': 'Plain keyboard', 'Como mando': 'As a gamepad',
    // quality levels and profiles
    'Sin efectos, 30 fps, 1280 de ancho. Para equipos modestos.': 'No effects, 30 fps, 1280 wide. For modest machines.',
    'Efectos activados, 1920 de ancho, filtros ligeros.': 'Effects on, 1920 wide, light filters.',
    'Todo activado a la resolución de tu pantalla.': 'Everything on at your screen resolution.',
    'Alta más texturas del remaster (descarga de 1.1 GB) y MSAA 4x.': 'High plus the remaster textures (a 1.1 GB download) and MSAA 4x.',
    'El juego como salió, sin extras.': 'The game as it shipped, no extras.', 'Texturas y efectos mejorados.': 'Better textures and effects.',
    'Equipo modesto / iPad': 'Modest machine / iPad', 'Original a 30 fps, sin efectos extra.': 'Original at 30 fps, no extra effects.',
    // web/launcher.js
    'Abre el juego en su menú principal.': 'Opens the game on its main menu.',     'Directo a Go Underground, la carrera de 2003. Izquierda o derecha: todo abierto o el progreso normal. Enter para entrar.': 'Straight into Go Underground, the 2003 career. Left or right: everything open or the normal progress. Enter to start.',
    'Menú': 'Menu', 'Menú principal': 'Main menu', 'Jugar': 'Play', 'Opciones': 'Options', 'Volver': 'Back', 'Cargando': 'Loading', 'Arrancando…': 'Starting…', 'Guías': 'Guides', 'Calidad': 'Quality',
    'A mano': 'Custom', 'Ajustes tocados uno por uno en Avanzado.': 'Settings changed one by one in Options.',
    'Controles': 'Controls', 'Teclas, mando y pantalla táctil. Todo se puede reasignar.': 'Keys, gamepad and touch screen. Everything can be remapped.', 'Ver': 'View', 'Abrir': 'Open',
    'Teclas y mando': 'Keys and gamepad', 'Clic en una acción y luego la tecla o el botón. También con K dentro del juego.': 'Click an action, then the key or the button. Also with K inside the game.',
    'Guardar copia': 'Save a backup', 'Descarga tus partidas de este navegador en un archivo.': 'Downloads the saves of this browser as one file.', 'Bajar': 'Download', 'Listo': 'Done', 'Sin partidas': 'No saves',
    'Restaurar copia': 'Restore a backup', 'Carga un archivo de partidas descargado antes.': 'Loads a save file you downloaded before.', 'Elegir': 'Choose', 'Restaurado': 'Restored', 'Archivo inválido': 'Invalid file',
    'Ajustes de fábrica': 'Factory settings', 'Todos los ajustes vuelven a su valor inicial. Las partidas no se tocan.': 'Every setting goes back to its first value. Saves are not touched.', 'Borrar': 'Reset', 'Hecho': 'Done',
    'Imagen, cámara, rendimiento, jugabilidad, teclas y partidas.': 'Picture, camera, performance, gameplay, keys and saves.', 'Vuelve al menú principal.': 'Back to the main menu.',
    'Cómo jugar, controles y cómo se hizo.': 'How to play, controls and how it was made.',
    'Este navegador no tiene WebGPU ni WebGL 2. Usa Chrome, Edge, Safari o Firefox recientes.': 'This browser has neither WebGPU nor WebGL 2. Use a recent Chrome, Edge, Safari or Firefox.',
    'Tu equipo': 'Your machine', 'midiendo': 'measuring', 'Va bien en ': 'Runs well on ', 'La escena de este menú corre a {ms} ms por cuadro en tu equipo.': 'The scene of this menu runs at {ms} ms per frame on your machine.',
    'Anterior': 'Previous', 'Siguiente': 'Next', 'Grupo anterior': 'Previous group', 'Grupo siguiente': 'Next group', 'Grupos de ajustes': 'Setting groups',
    'Cambiar': 'Change', 'Grupo': 'Group',
    'Sonido del menú (M)': 'Menu sound (M)', 'Sonido: sí': 'Sound: on', 'Sonido: no': 'Sound: off', 'Animación': 'Motion', 'Animación: sí': 'Motion: on', 'Animación: no': 'Motion: off',
    // web/binds.js
    'Girar a la izquierda': 'Steer left', 'Girar a la derecha': 'Steer right', 'Acelerar': 'Gas', 'Frenar / reversa': 'Brake / reverse', 'Freno de mano': 'Handbrake',
    'Reiniciar el coche': 'Reset car', 'Pausa (Esc)': 'Pause (Esc)', 'Menú: aceptar': 'Menu: accept', 'Menú: atrás': 'Menu: back',
    'Teclado': 'Keyboard', 'Mando': 'Gamepad', 'pulsa…': 'press…', 'Valores de fábrica': 'Factory defaults',
    'Clic en una acción y luego la tecla o el botón. Palanca, cruceta y gatillos son fijos. Esc, K o Select cierra.': 'Click an action, then the key or the button. Sticks, d-pad and triggers are fixed. Esc, K or Select closes.',
    // web/overlay.js
    'Perfil': 'Profile', 'Calidad (a mano)': 'Quality (custom)', 'Sonido': 'Sound', 'Silenciado (clic para activar)': 'Muted (click to turn on)', 'Sonido activo (clic para silenciar)': 'Sound on (click to mute)',
    'Teclas y mando (K)': 'Keys and gamepad (K)', 'Botones: tenues': 'Buttons: faint', 'Botones: medios': 'Buttons: medium', 'Botones: visibles': 'Buttons: visible',
    'Un cambio aquí reinicia el juego.': 'A change here restarts the game.', 'Todos los ajustes': 'All settings',
    // web/saves.js
    'No se pudo guardar tu partida en este navegador': 'Your progress could not be saved in this browser',
    'No se pudieron leer tus partidas en este navegador': 'Your saves could not be read in this browser',
    // web/app.js (rotate screen + fullscreen home-screen wizard)
    'Gira el teléfono': 'Rotate your phone',
    'El juego es horizontal y espera en pausa.': 'The game runs in landscape and is paused.',
    'Si no gira, quita el bloqueo de rotación.': 'If it does not rotate, unlock screen orientation.',
    'Pantalla completa ahora': 'Enter full screen',
    'Instalar acceso directo': 'Install shortcut',
    'Mejor a pantalla completa': 'Better in full screen',
    'Sin barras del navegador, más espacio para los botones táctiles y acceso en un toque.': 'No browser bars, more room for touch controls, and one-tap launch.',
    'En navegador': 'In browser',
    'Desde tu inicio': 'Home screen',
    'Recomendado': 'Recommended',
    'Cómo agregarlo al inicio': 'How to add to Home Screen',
    'Toca el botón Compartir en la barra inferior de Safari.': 'Tap the Share button in Safari’s bottom bar.',
    'Desliza y elige "Agregar a inicio".': 'Scroll down and tap "Add to Home Screen".',
    'Abre NFS Underground desde tu pantalla de inicio y gira el teléfono.': 'Open NFS Underground from your Home Screen and rotate your phone.',
    'Toca el menú (⋮) arriba a la derecha en Chrome.': 'Tap the menu (⋮) in the top right of Chrome.',
    'Elige "Agregar a pantalla principal" o "Instalar app".': 'Tap "Add to Home screen" or "Install app".',
    'Ábrelo desde tu inicio para jugar sin barras y gira el teléfono.': 'Open it from your Home screen for full screen and rotate your phone.',
    'Paso': 'Step',
    'Listo': 'Done',
  };
  window.RN_LANG = lang;
  window.RN_TR = s => (lang === 'en' && typeof s === 'string' && EN[s]) || s;
})();
