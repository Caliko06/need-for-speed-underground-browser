#!/usr/bin/env python3
"""Guides for search engines and newcomers (OWNER 2026-11-16: more SEO, a blog, English and Spanish).
Writes web/blog/<lang>/*.html, web/sitemap.xml and web/robots.txt from the texts below. Style: web/blog/blog.css.
Every game fact in the texts names its source in the comment above the article; change the text when the source changes.
URLs end in .html on purpose: the R2 host serves no directory index (docs/re/hosting.md, only "/" is rewritten).
Usage: python3 tools/build_blog.py   (then tools/build_public.py ships web/blog/ with the rest)"""
import html, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blog_dev import CODE, DEV, DEV_DATE, REPO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "web")
SITE = "https://nfsu.cc"
DATE = "2026-11-24"          # last updated
LANGS = ("en", "es")
UI = {
    "en": dict(guides="Guides", play="Play", other="Español", home="NFSU.cc", more="More guides", cta="Play now", updated="Updated %s", dev="How it works", code="Code on GitHub", inrepo="In the repo:",
               hub_title="Need for Speed Underground in the browser: guides", hub_h1="Guides",
               hub_desc="How to play Need for Speed Underground online at nfsu.cc: first start, controls, browsers and phones, and how it works: static recompilation, reverse engineering tools, WebGPU and AI agents.",
               hub_lead="NFSU.cc is Need for Speed Underground (2003) running in a browser tab. These pages explain how to start, how to drive and what is under the hood.",
               foot="NFSU.cc: Need for Speed Underground in the browser."),
    "es": dict(guides="Guías", play="Jugar", other="English", home="NFSU.cc", more="Más guías", cta="Jugar ahora", updated="Actualizado el %s", dev="Cómo funciona", code="Código en GitHub", inrepo="En el repo:",
               hub_title="Need for Speed Underground en el navegador: guías", hub_h1="Guías",
               hub_desc="Cómo jugar Need for Speed Underground online en nfsu.cc: primer arranque, controles, navegadores y celulares, y cómo funciona: recompilación estática, herramientas de ingeniería inversa, WebGPU y agentes de IA.",
               hub_lead="NFSU.cc es Need for Speed Underground (2003) corriendo en una pestaña del navegador. Estas páginas explican cómo empezar, cómo manejar y qué hay bajo el cofre.",
               foot="NFSU.cc: Need for Speed Underground en el navegador."),
}

K = lambda *keys: " ".join("<kbd>%s</kbd>" % k for k in keys)
def keys(rows):
    return '<ul class="keys">' + "".join("<li><span>%s</span><span>%s</span></li>" % (a, k) for a, k in rows) + "</ul>"

# [[key]] in a text = the address of that guide in the same language.
ARTICLES = [
    # Sources: browsers web/app.js:29; launcher rows web/launcher.js (screen A) and web/launcher_opts.js; first visit web/index.html:55;
    # in-game panel web/overlay.js; load sizes: one cold visit with tools/loadcap.mjs 2026-11-21 (32.6 MB to the menu, speed.wasm 11.1 MB brotli);
    # remaster 1.1 GB web/launcher_opts.js; saves web/saves.js; F4 web/mode.js:78; low level = fx off, 30 fps, 1280 (launcher_opts.js quality).
    dict(key="play", img="olympic-city-world.webp",
         slug=dict(en="play-need-for-speed-underground-online", es="jugar-need-for-speed-underground-online"),
         title=dict(en="How to play Need for Speed Underground online in your browser", es="Cómo jugar Need for Speed Underground online en tu navegador"),
         desc=dict(en="Open nfsu.cc, press Play and drive. What you need, how big the first load is, where your saves live and what to do if the game does not start.",
                   es="Abre nfsu.cc, presiona Jugar y maneja. Qué necesitas, cuánto pesa la primera carga, dónde quedan tus partidas y qué hacer si el juego no arranca."),
         alt=dict(en="Need for Speed Underground running in a browser: a blue Skyline in Olympic City", es="Need for Speed Underground corriendo en el navegador: un Skyline azul en Olympic City"),
         cap=dict(en="The 2003 game in a browser tab.", es="El juego de 2003 en una pestaña del navegador."),
         lead=dict(en="NFSU.cc runs the original PC game of 2003 inside a browser tab. There is nothing to install and no account to make: you open the page, press Play and you are in the garage.",
                   es="NFSU.cc corre el juego original de PC de 2003 dentro de una pestaña del navegador. No hay nada que instalar ni cuenta que crear: abres la página, presionas Jugar y ya estás en el garaje."),
         body=dict(en="""
<h2>What you need</h2>
<p>A modern browser with <b>WebGPU</b> (fastest) or <b>WebGL 2</b> (automatic fallback on older GPUs and phones):</p>
<ul>
<li><b>Chrome or Edge</b> on Windows, macOS, Linux, or Android (WebGPU on 113+ / Android 12+, WebGL 2 fallback on older devices).</li>
<li><b>Safari</b> on Mac, iPhone, or iPad (WebGPU on Safari 26+, WebGL 2 fallback on earlier versions).</li>
<li><b>Firefox</b> on Windows, macOS, or Linux (WebGPU on 141+ Windows / 145+ Apple Silicon, WebGL 2 fallback elsewhere).</li>
</ul>
<p>A keyboard is enough. A gamepad works as soon as you plug it in, and phones get buttons on the screen. The details are in <a href="[[controls]]">the controls guide</a>. The project is built and tested mostly on Chrome, so that is the safest pick if something looks wrong elsewhere.</p>
<h2>Start in three steps</h2>
<ol>
<li>Open <a href="/">nfsu.cc</a>. On a computer the first visit shows the launcher: a menu with Play, Quality, Game, Volume and Controls.</li>
<li>Press <b>Play</b> (or Enter). The game loads and you land on the profile screen.</li>
</ol>
<p>Later visits go straight into the game. A small button in the corner opens a panel with the same options, and its "All settings" link takes you back to the launcher.</p>
<h2>How big the first load is</h2>
<p>Reaching the game's menu downloads about 32 MB; the game program itself is 11 MB compressed. Your browser keeps the files, so the second visit starts faster.</p>
<p>The optional remaster textures are a separate 1.1 GB download. They are off until you turn them on or pick the Ultra quality level.</p>
<h2>Play or Career, Original or Remaster</h2>
<p><b>Play</b> opens the game's main menu. <b>Career</b> goes straight into Go Underground; its progress can be "All open" or "Normal", where events unlock one by one.</p>
<p><b>Version</b> picks between <b>Original 2003</b>, the game as it looked, and <b>Remaster</b>, which adds effects such as bloom, edge smoothing and sharper car paint. Inside the game, F4 switches between the two.</p>
<h2>Where your saves live</h2>
<p>Profiles and progress are stored in your own browser, not on a server. That means they stay on this device and in this browser, and clearing the site's data erases them. In the launcher, Options has a Saves group with <b>Save a backup</b>, which downloads everything as one file, and <b>Restore a backup</b>, which loads it again, also on another computer.</p>
<h2>If it does not start</h2>
<ul>
<li><b>Opened inside Instagram, TikTok or another in-app browser</b>: tap the menu and choose "Open in Chrome" or "Open in Safari" so the browser allows shared memory.</li>
<li><b>It runs slowly</b>: set Quality to Low in the launcher (no effects, 30 fps, 1280 pixels wide). <a href="[[devices]]">The performance guide</a> explains each option.</li>
<li><b>No sound</b>: browsers keep a page silent until your first click or key press. Check the Volume row in the launcher too.</li>
</ul>
<h2>Frequently asked questions</h2>
<h3>Is NFSU.cc an emulator or a remake?</h3>
<p>Neither. It is a static recompilation of the original 2003 PC executable (<code>Speed.exe</code>) to WebAssembly, so the physics, AI rivals, menus and career progression are the original game's own code.</p>
<h3>Does it include the original soundtrack?</h3>
<p>Yes. Every song from the 2003 PC soundtrack is included and streams as you play.</p>
<h3>Does it work on Android and iPhone?</h3>
<p>Yes. Phones and tablets automatically use a lighter 448 MB WebAssembly build, Original 2003 graphics, 30 fps and on-screen touch controls. On iPhone, add the page to your Home Screen for full screen.</p>
<h3>Is it free and do I need an account?</h3>
<p>It is free, with no account and nothing to install. Saves stay locally in your browser and can be exported as a backup file at any time.</p>
""", es="""
<h2>Qué necesitas</h2>
<p>Un navegador moderno con <b>WebGPU</b> (más rápido) o <b>WebGL 2</b> (respaldo automático en GPUs y celulares más viejos):</p>
<ul>
<li><b>Chrome o Edge</b> en Windows, macOS, Linux o Android (WebGPU en 113+ / Android 12+, respaldo WebGL 2 en equipos anteriores).</li>
<li><b>Safari</b> en Mac, iPhone o iPad (WebGPU en Safari 26+, respaldo WebGL 2 en versiones anteriores).</li>
<li><b>Firefox</b> en Windows, macOS o Linux (WebGPU en 141+ Windows / 145+ Apple Silicon, respaldo WebGL 2 en el resto).</li>
</ul>
<p>Con el teclado basta. Un mando funciona en cuanto lo conectas y los celulares reciben botones en la pantalla. Los detalles están en <a href="[[controls]]">la guía de controles</a>. El proyecto se construye y se prueba sobre todo en Chrome, así que es la opción más segura si algo se ve raro en otro navegador.</p>
<h2>Empieza en tres pasos</h2>
<ol>
<li>Abre <a href="/">nfsu.cc</a>. En computadora, la primera visita muestra el launcher: un menú con Jugar, Calidad, Juego, Volumen y Controles.</li>
<li>Presiona <b>Jugar</b> (o Enter). El juego carga y llegas a la pantalla de perfil.</li>
</ol>
<p>Las siguientes visitas entran directo al juego. Un botón pequeño en la esquina abre un panel con las mismas opciones, y su enlace "Todos los ajustes" te regresa al launcher.</p>
<h2>Cuánto pesa la primera carga</h2>
<p>Llegar al menú del juego descarga unos 32 MB; el programa del juego pesa 11 MB comprimido. Tu navegador guarda los archivos, así que la segunda visita arranca más rápido.</p>
<p>Las texturas del remaster son una descarga aparte de 1.1 GB. Están apagadas hasta que las prendes o eliges la calidad Ultra.</p>
<h2>Jugar o Carrera, Original o Remaster</h2>
<p><b>Jugar</b> abre el menú principal del juego. <b>Carrera</b> entra directo a Go Underground; su progreso puede ser "Todo abierto" o "Normal", donde los eventos se abren uno por uno.</p>
<p><b>Versión</b> elige entre <b>Original 2003</b>, el juego como se veía, y <b>Remaster</b>, que agrega efectos como brillo de luces, suavizado de bordes y pintura más nítida. Dentro del juego, F4 cambia entre los dos.</p>
<h2>Dónde quedan tus partidas</h2>
<p>Los perfiles y el progreso se guardan en tu propio navegador, no en un servidor. Por eso se quedan en este dispositivo y en este navegador, y borrar los datos del sitio las elimina. En el launcher, Opciones tiene un grupo Partidas con <b>Guardar copia</b>, que descarga todo en un archivo, y <b>Restaurar copia</b>, que lo vuelve a cargar, también en otra computadora.</p>
<h2>Si no arranca</h2>
<ul>
<li><b>Lo abriste dentro de Instagram, TikTok u otra app</b>: toca el menú y elige "Abrir en Chrome" o "Abrir en Safari" para que el navegador permita memoria compartida.</li>
<li><b>Va lento</b>: pon Calidad en Baja en el launcher (sin efectos, 30 fps, 1280 pixeles de ancho). <a href="[[devices]]">La guía de rendimiento</a> explica cada opción.</li>
<li><b>No hay sonido</b>: los navegadores mantienen la página en silencio hasta tu primer clic o tecla. Revisa también la fila Volumen del launcher.</li>
</ul>
<h2>Preguntas frecuentes</h2>
<h3>¿NFSU.cc es un emulador o un remake?</h3>
<p>Ninguno de los dos. Es una recompilación estática del ejecutable original de PC de 2003 (<code>Speed.exe</code>) a WebAssembly, así que la física, los rivales, los menús y el modo carrera son el código del propio juego.</p>
<h3>¿Trae el soundtrack original completo?</h3>
<p>Sí. Incluye todas las canciones originales del juego de PC de 2003.</p>
<h3>¿Funciona en Android y iPhone?</h3>
<p>Sí. Los celulares y tabletas cargan automáticamente un build ligero de 448 MB en WebAssembly, gráficos Original 2003, 30 fps y controles táctiles en pantalla. En iPhone, agrégalo a la pantalla de inicio para jugar a pantalla completa.</p>
<h3>¿Es gratis y pide cuenta?</h3>
<p>Es gratis, sin cuenta y sin instalar nada. Tus partidas se guardan en tu navegador y puedes descargar un respaldo cuando quieras.</p>
""")),

    # Sources: keys web/binds.js BIND_KEYS (game table 0x702c98) and web/pad.js header; Backspace = the menus' Back (table 0x7032d8 row 0x17);
    # K and Select open the overlay (web/binds.js); F4 web/mode.js:78; touch layer HANDOFF.md "Phone HUD v4"
    # (GAS, BRAKE, NITROUS holds gas, HAND BRAKE in drift, SHIFT in drag or manual, CAMERA, RESET); iPhone home screen web/touch.js:131;
    # "Teclado como mando" web/launcher_opts.js steer.
    dict(key="controls", img="olympic-city-drive.webp",
         slug=dict(en="need-for-speed-underground-controls-keyboard-gamepad-phone", es="controles-need-for-speed-underground-teclado-mando-celular"),
         title=dict(en="Controls: keyboard, gamepad and phone", es="Controles: teclado, mando y celular"),
         desc=dict(en="Every key and button of Need for Speed Underground in the browser: default keyboard keys, gamepad layout, touch buttons on phones and how to remap them.",
                   es="Todas las teclas y botones de Need for Speed Underground en el navegador: teclado por defecto, botones del mando, controles táctiles en celulares y cómo reasignarlos."),
         alt=dict(en="Driving through Olympic City at night in Need for Speed Underground", es="Manejando de noche por Olympic City en Need for Speed Underground"),
         cap=dict(en="The defaults are the game's own keys from 2003.", es="Los valores por defecto son las teclas del propio juego de 2003."),
         lead=dict(en="The page keeps the keys the PC game shipped with, adds a gamepad layout and draws buttons on touch screens. Everything except the sticks and triggers can be remapped.",
                   es="La página conserva las teclas con las que salió el juego de PC, agrega una distribución para mando y dibuja botones en pantallas táctiles. Todo, salvo palancas y gatillos, se puede reasignar."),
         body=dict(en="""
<h2>Keyboard</h2>
""" + keys([("Steer", K("←", "→")), ("Gas", K("↑")), ("Brake / reverse", K("↓")), ("Nitrous", K("Space")), ("Handbrake", K("Left Shift")), ("Change camera", K("C")), ("Reset car", K("R")),
            ("Pause", K("Esc")), ("Menus: accept", K("Enter")), ("Menus: back", K("Backspace"))]) + """
<p>Three more keys belong to the page, not to the game:</p>
""" + keys([("Remap keys and buttons", K("K")), ("Original / Remaster", K("F4"))]) + """
<h2>Gamepad</h2>
<p>Any pad the browser sees with the standard layout works (Xbox, PlayStation, most USB and Bluetooth pads). Names below are the Xbox ones.</p>
""" + keys([("Steer", "Left stick"), ("Gas", K("RT")), ("Brake / reverse", K("LT")), ("Nitrous", K("A")), ("Handbrake", K("B")), ("Change camera", K("Y")), ("Reset car", K("RB")),
            ("Pause", K("Start")), ("Menus: move", "D-pad or left stick"), ("Menus: accept / back", K("A", "B"))]) + """
<p>The pad starts in menu mode and switches to driving when you pull a trigger, so in a race the first thing to do is press the gas.</p>
<h2>Remap anything</h2>
<p>Press <b>K</b> in the game, or <b>Select</b> on the pad, or open Controls in the launcher. Click an action and then press the key or button you want for it. If that key already did something else, the two swap. Sticks, d-pad and triggers stay fixed, and so do Esc and Enter. The choice is saved in your browser.</p>
<p>If you prefer smoother steering on the arrow keys, the launcher has a <b>Keyboard steering</b> option that makes them turn with the gamepad's steering model.</p>
<h2>Phones and tablets</h2>
<p>On a touch screen the page draws thin round buttons with the game's own words over the picture: <b>GAS</b>, <b>BRAKE</b>, <b>NITROUS</b> (which also holds the gas), two steering arrows, pause, <b>CAMERA</b> and <b>RESET</b>. <b>HAND BRAKE</b> appears in drift events, and <b>SHIFT -</b> / <b>SHIFT +</b> only in drag races or with a manual gearbox.</p>
<p>Android Chrome goes full screen on the first touch. An iPhone does not let a web page do that: tap Share, choose "Add to Home Screen" and open the game from that icon to fill the screen. What phones can and cannot run is in <a href="[[devices]]">the browsers and phones guide</a>.</p>
""", es="""
<h2>Teclado</h2>
""" + keys([("Girar", K("←", "→")), ("Acelerar", K("↑")), ("Frenar / reversa", K("↓")), ("Nitro", K("Espacio")), ("Freno de mano", K("Shift izq.")), ("Cambiar cámara", K("C")), ("Reiniciar el coche", K("R")),
            ("Pausa", K("Esc")), ("Menús: aceptar", K("Enter")), ("Menús: atrás", K("Retroceso"))]) + """
<p>Tres teclas más son de la página, no del juego:</p>
""" + keys([("Reasignar teclas y botones", K("K")), ("Original / Remaster", K("F4"))]) + """
<h2>Mando</h2>
<p>Funciona cualquier mando que el navegador reconozca con la distribución estándar (Xbox, PlayStation, casi todos los USB y Bluetooth). Los nombres de abajo son los de Xbox.</p>
""" + keys([("Girar", "Palanca izquierda"), ("Acelerar", K("RT")), ("Frenar / reversa", K("LT")), ("Nitro", K("A")), ("Freno de mano", K("B")), ("Cambiar cámara", K("Y")), ("Reiniciar el coche", K("RB")),
            ("Pausa", K("Start")), ("Menús: moverse", "Cruceta o palanca izquierda"), ("Menús: aceptar / atrás", K("A", "B"))]) + """
<p>El mando empieza en modo menú y pasa a modo manejo cuando jalas un gatillo, así que en una carrera lo primero es acelerar.</p>
<h2>Reasigna lo que quieras</h2>
<p>Presiona <b>K</b> dentro del juego, o <b>Select</b> en el mando, o abre Controles en el launcher. Haz clic en una acción y luego presiona la tecla o el botón que quieras para ella. Si esa tecla ya hacía otra cosa, las dos se intercambian. Palancas, cruceta y gatillos son fijos, igual que Esc y Enter. La elección se guarda en tu navegador.</p>
<p>Si prefieres un giro más suave con las flechas, el launcher tiene la opción <b>Giro del teclado</b>, que las hace girar con el modelo de dirección del mando.</p>
<h2>Celulares y tabletas</h2>
<p>En una pantalla táctil la página dibuja botones redondos y delgados con las palabras del propio juego sobre la imagen: <b>GAS</b>, <b>BRAKE</b>, <b>NITROUS</b> (que también mantiene el acelerador), dos flechas para girar, pausa, <b>CAMERA</b> y <b>RESET</b>. <b>HAND BRAKE</b> aparece en los eventos de drift, y <b>SHIFT -</b> / <b>SHIFT +</b> solo en arrancones o con caja manual.</p>
<p>Chrome en Android pasa a pantalla completa al primer toque. Un iPhone no le permite eso a una página web: toca Compartir, elige "Agregar a inicio" y abre el juego desde ese ícono para llenar la pantalla. Qué pueden correr los celulares está en <a href="[[devices]]">la guía de navegadores y celulares</a>.</p>
""")),

    # Sources: browsers web/app.js:29; quality levels and every option web/launcher_opts.js (quality, opts); machine detection web/launcher.js detect()
    # (median frame time of the menu scene: > 28 ms low, > 20 ms medium, else high; Ultra never picked); phones start light plan.json step 2 row 5
    # (Original, effects off, 30 fps) and the presets of web/launcher_opts.js; in-game panel web/overlay.js; iPhone web/touch.js:131.
    dict(key="devices", img="phone-touch.webp",
         slug=dict(en="browsers-phones-performance-settings", es="navegadores-celulares-ajustes-rendimiento"),
         title=dict(en="Browsers, phones and performance settings", es="Navegadores, celulares y ajustes de rendimiento"),
         desc=dict(en="Which browsers and devices run Need for Speed Underground at nfsu.cc, what phones get, and what each quality level and performance option changes.",
                   es="Qué navegadores y dispositivos corren Need for Speed Underground en nfsu.cc, qué reciben los celulares y qué cambia cada nivel de calidad y opción de rendimiento."),
         alt=dict(en="Need for Speed Underground on a phone screen with touch buttons over the picture", es="Need for Speed Underground en la pantalla de un celular con botones táctiles sobre la imagen"),
         cap=dict(en="On a phone the page adds touch buttons and starts with the lightest settings.", es="En un celular la página agrega botones táctiles y arranca con los ajustes más ligeros."),
         lead=dict(en="The game draws with WebGPU when available and automatically falls back to WebGL 2 on older browsers and phones. On desktop, the launcher measures your machine and picks a quality level, and you can change every part of it.",
                   es="El juego dibuja con WebGPU cuando está disponible y cambia automáticamente a WebGL 2 en navegadores y celulares más viejos. En computadora, el launcher mide tu equipo y elige un nivel de calidad, y tú puedes cambiar cada parte."),
         body=dict(en="""
<h2>Supported browsers</h2>
<ul>
<li><b>Chrome and Edge</b> on Windows, macOS, Linux and Android (WebGPU on 113+ / Android 12+, automatic WebGL 2 fallback on older devices).</li>
<li><b>Safari</b> on Mac, iPhone and iPad (WebGPU on Safari 26+, automatic WebGL 2 fallback on earlier versions).</li>
<li><b>Firefox</b> on Windows, macOS and Linux (WebGPU on 141+ Windows / 145+ Apple Silicon, WebGL 2 fallback elsewhere).</li>
</ul>
<p>If you open a link inside Instagram, TikTok or another in-app browser, choose "Open in Chrome" or "Open in Safari": in-app WebViews often block shared memory (COOP/COEP). Most testing happens on Chrome on desktop.</p>
<h2>The four quality levels</h2>
<p>On your first visit the launcher times how fast your machine draws its 3D menu and sets a level for you. You can change it in the Quality row.</p>
<ul>
<li><b>Low</b>: no remaster effects, 30 fps, picture 1280 pixels wide. For modest machines.</li>
<li><b>Medium</b>: effects on, 1920 pixels wide, lighter filters.</li>
<li><b>High</b>: everything on at the resolution of your screen.</li>
<li><b>Ultra</b>: High plus the remaster textures (a 1.1 GB download) and MSAA 4x. It is never chosen for you.</li>
</ul>
<h2>Options that matter most for speed</h2>
<ul>
<li><b>Resolution</b>: the widest picture the game draws. Fewer pixels is the biggest single gain.</li>
<li><b>Frame rate</b>: 30 fps is half the work of 60.</li>
<li><b>Remaster effects</b>: turns off bloom, smoothing and the other visual extras in one switch, without touching the gameplay improvements.</li>
<li><b>MSAA 4x</b>: sharper edges, heavy on the graphics card. Leave it off on a laptop.</li>
</ul>
<p>Picking <b>Original 2003</b> as the version is the lightest way to play: it is the game as it shipped, with none of the extra effects.</p>
<h2>Phones and tablets</h2>
<p>A phone or tablet starts light on every visit: the Original version, effects off and 30 fps. The corner button in the game offers three profiles (Original 2003, Remaster, and Modest machine / iPad) plus the touch button opacity.</p>
<p>On an iPhone, add the page to the home screen to play full screen. The touch layout is described in <a href="[[controls]]">the controls guide</a>.</p>
<h2>Changing settings later</h2>
<p>After the first visit a computer goes straight into the game. The small button in the top corner opens quality, game, version, sound and keys; a change there restarts the game with the new setting. "All settings" opens the full launcher with every option, grouped as Game, Picture, Camera, Performance, Gameplay, and Sound and controls.</p>
""", es="""
<h2>Navegadores compatibles</h2>
<ul>
<li><b>Chrome y Edge</b> en Windows, macOS, Linux y Android (WebGPU en 113+ / Android 12+, respaldo automático WebGL 2 en equipos anteriores).</li>
<li><b>Safari</b> en Mac, iPhone y iPad (WebGPU en Safari 26+, respaldo automático WebGL 2 en versiones anteriores).</li>
<li><b>Firefox</b> en Windows, macOS y Linux (WebGPU en 141+ Windows / 145+ Apple Silicon, respaldo WebGL 2 en el resto).</li>
</ul>
<p>Si abres el enlace dentro de Instagram, TikTok u otra app, elige "Abrir en Chrome" o "Abrir en Safari": los WebViews integrados suelen bloquear la memoria compartida (COOP/COEP). La mayoría de las pruebas se hacen en Chrome de escritorio.</p>
<h2>Los cuatro niveles de calidad</h2>
<p>En tu primera visita el launcher mide qué tan rápido dibuja tu equipo su menú en 3D y te pone un nivel. Puedes cambiarlo en la fila Calidad.</p>
<ul>
<li><b>Baja</b>: sin efectos del remaster, 30 fps, imagen de 1280 pixeles de ancho. Para equipos modestos.</li>
<li><b>Media</b>: efectos activados, 1920 pixeles de ancho, filtros más ligeros.</li>
<li><b>Alta</b>: todo activado a la resolución de tu pantalla.</li>
<li><b>Ultra</b>: Alta más las texturas del remaster (descarga de 1.1 GB) y MSAA 4x. Nunca se elige por ti.</li>
</ul>
<h2>Las opciones que más pesan</h2>
<ul>
<li><b>Resolución</b>: el ancho máximo de la imagen que dibuja el juego. Menos pixeles es la mayor ganancia.</li>
<li><b>Fotogramas</b>: 30 fps es la mitad del trabajo de 60.</li>
<li><b>Efectos remaster</b>: apaga de un golpe el brillo, el suavizado y los demás extras visuales, sin tocar las mejoras de juego.</li>
<li><b>MSAA 4x</b>: bordes más nítidos, pesado para la tarjeta gráfica. Déjalo apagado en una laptop.</li>
</ul>
<p>Elegir <b>Original 2003</b> como versión es la forma más ligera de jugar: es el juego como salió, sin ninguno de los efectos extra.</p>
<h2>Celulares y tabletas</h2>
<p>Un celular o tableta arranca ligero en cada visita: versión Original, efectos apagados y 30 fps. El botón de la esquina dentro del juego ofrece tres perfiles (Original 2003, Remaster y Equipo modesto / iPad) y la opacidad de los botones táctiles.</p>
<p>En un iPhone, agrega la página a la pantalla de inicio para jugar a pantalla completa. Los botones táctiles se explican en <a href="[[controls]]">la guía de controles</a>.</p>
<h2>Cambiar ajustes después</h2>
<p>Después de la primera visita, una computadora entra directo al juego. El botón pequeño de la esquina superior abre calidad, juego, versión, sonido y teclas; un cambio ahí reinicia el juego con el ajuste nuevo. "Todos los ajustes" abre el launcher completo con cada opción, en los grupos Juego, Imagen, Cámara, Rendimiento, Jugabilidad, y Sonido y controles.</p>
""")),

    # Sources: AGENTS.md map (Speed.exe statically recompiled x86 -> WebAssembly, tools/recomp; host/ and web/ stand in for Windows/DirectX);
    # speed.wasm 70 MB raw, 11.1 MB brotli tools/upload_r2.sh:29; WebGPU web/gpu.js; threads + cross-origin isolation web/boot.js:97, plan.json step 2 row 2;
    # game files by Range host/files.c (tools/upload_r2.sh comment); keys as DirectInput codes web/binds.js, web/dik.js; saves web/saves.js;
    # remaster effects web/launcher_opts.js (bloom, FXAA, MSAA, sharpness, anisotropic filter).
    dict(key="tech", img="olympic-city-drive.webp",
         slug=dict(en="how-need-for-speed-underground-runs-in-a-browser-webassembly", es="como-corre-need-for-speed-underground-en-el-navegador-webassembly"),
         title=dict(en="How it works: a 2003 Windows game recompiled to WebAssembly", es="Cómo funciona: un juego de Windows de 2003 recompilado a WebAssembly"),
         desc=dict(en="NFSU.cc is not an emulator or a remake. The original Need for Speed Underground program was translated to WebAssembly and its Windows and DirectX calls were rebuilt on WebGPU.",
                   es="NFSU.cc no es un emulador ni un remake. El programa original de Need for Speed Underground se tradujo a WebAssembly y sus llamadas a Windows y DirectX se reconstruyeron sobre WebGPU."),
         alt=dict(en="A car driving through Olympic City in the browser version of Need for Speed Underground", es="Un coche manejando por Olympic City en la versión de navegador de Need for Speed Underground"),
         cap=dict(en="The same physics, AI and HUD code as in 2003, now running as WebAssembly.", es="El mismo código de física, rivales y HUD de 2003, ahora corriendo como WebAssembly."),
         lead=dict(en="What runs in your tab is the game's own code from 2003. It was not rewritten and it is not emulated: the program was translated once, ahead of time, into something a browser can run.",
                   es="Lo que corre en tu pestaña es el código del propio juego de 2003. No se reescribió ni se emula: el programa se tradujo una sola vez, por adelantado, a algo que un navegador puede ejecutar."),
         body=dict(en="""
<h2>Static recompilation</h2>
<p>The PC game is one Windows program, Speed.exe, made of machine code for 32-bit Intel processors. A tool reads that program and writes the same logic again as WebAssembly, the portable code format browsers run at close to native speed. This is called static recompilation: the translation happens before you ever open the page, not while you play.</p>
<p>An emulator would have to imitate a whole PC, instruction by instruction, every frame. Here the handling, the rival drivers, the menus and the career rules are the original ones, already in the browser's own format. The result is a file of about 70 MB that travels compressed in 11 MB.</p>
<h2>A new home for an old program</h2>
<p>The game still believes it is on Windows XP. It asks for windows, files, sound buffers, keyboard state and a DirectX 9 graphics card. A layer written for this project answers each of those calls with what a browser has:</p>
<ul>
<li><b>Graphics</b>: the DirectX 9 drawing calls are turned into WebGPU.</li>
<li><b>Sound</b>: music and effects play through the browser's audio system.</li>
<li><b>Input</b>: keys, gamepads and touch buttons are handed to the game as the keyboard codes it expects, which is why its own key table still applies.</li>
<li><b>Files</b>: the game opens its data files as it always did, and the layer fetches only the parts it reads from the server.</li>
<li><b>Threads</b>: the game runs off the page's main thread on shared memory, which is why the site is served with cross-origin isolation.</li>
<li><b>Saves</b>: the save folder lives in memory and is copied to your browser's own storage a moment after each change.</li>
</ul>
<h2>The remaster layer</h2>
<p>Because the page owns the drawing step, it can add things the 2003 renderer did not have: bloom on lights, edge smoothing, sharpening, anisotropic filtering, sharper car paint and optional high resolution textures. All of it is a layer on top. Switch the version to Original 2003 and the picture is the one the game always drew.</p>
<h2>Try it</h2>
<p>The quickest way to judge the result is to drive it: <a href="[[play]]">how to start playing</a> takes a minute to read.</p>
""", es="""
<h2>Recompilación estática</h2>
<p>El juego de PC es un programa de Windows, Speed.exe, hecho de código máquina para procesadores Intel de 32 bits. Una herramienta lee ese programa y escribe la misma lógica otra vez en WebAssembly, el formato de código portátil que los navegadores ejecutan casi a velocidad nativa. A esto se le llama recompilación estática: la traducción ocurre antes de que abras la página, no mientras juegas.</p>
<p>Un emulador tendría que imitar una PC completa, instrucción por instrucción, en cada cuadro. Aquí el manejo, los rivales, los menús y las reglas del modo carrera son los originales, ya en el formato del navegador. El resultado es un archivo de unos 70 MB que viaja comprimido en 11 MB.</p>
<h2>Una casa nueva para un programa viejo</h2>
<p>El juego sigue creyendo que está en Windows XP. Pide ventanas, archivos, búferes de sonido, estado del teclado y una tarjeta gráfica con DirectX 9. Una capa escrita para este proyecto responde cada una de esas llamadas con lo que tiene un navegador:</p>
<ul>
<li><b>Gráficos</b>: las llamadas de dibujo de DirectX 9 se convierten en WebGPU.</li>
<li><b>Sonido</b>: la música y los efectos suenan por el sistema de audio del navegador.</li>
<li><b>Entrada</b>: teclas, mandos y botones táctiles se le entregan al juego como los códigos de teclado que espera; por eso su propia tabla de teclas sigue valiendo.</li>
<li><b>Archivos</b>: el juego abre sus archivos de datos como siempre, y la capa pide al servidor solo las partes que lee.</li>
<li><b>Hilos</b>: el juego corre fuera del hilo principal de la página, sobre memoria compartida; por eso el sitio se sirve con aislamiento de origen cruzado.</li>
<li><b>Partidas</b>: la carpeta de guardado vive en memoria y se copia al almacenamiento de tu navegador un momento después de cada cambio.</li>
</ul>
<h2>La capa del remaster</h2>
<p>Como la página es dueña del paso de dibujo, puede agregar cosas que el motor de 2003 no tenía: brillo en las luces, suavizado de bordes, nitidez, filtro anisotrópico, pintura de coches más nítida y texturas opcionales de alta resolución. Todo es una capa encima. Cambia la versión a Original 2003 y la imagen es la que el juego siempre dibujó.</p>
<h2>Pruébalo</h2>
<p>La forma más rápida de juzgar el resultado es manejarlo: <a href="[[play]]">cómo empezar a jugar</a> se lee en un minuto.</p>
""")),
]
GUIDES = list(ARTICLES)
ARTICLES += DEV
BY = {a["key"]: a for a in ARTICLES}
WHEN = {"en": lambda d: "November %d, 2026" % int(d[-2:]), "es": lambda d: "%d de noviembre de 2026" % int(d[-2:])}
e = html.escape


def url(lang, name):
    return "%s/blog/%s/%s.html" % (SITE, lang, name)


def page(lang, name, names, title, desc, pic, h1, inner, ld, date=None, og_img=None, og_alt=None):
    """names = {lang: file name} of this page in every language (hreflang)."""
    u = UI[lang]
    alts = "".join('<link rel="alternate" hreflang="%s" href="%s">\n' % (l, url(l, names[l])) for l in LANGS)
    alts += '<link rel="alternate" hreflang="x-default" href="%s">\n' % url("en", names["en"])
    other = "es" if lang == "en" else "en"
    og_url_img = og_img or (SITE + "/og.jpg")
    alt_txt = e(og_alt or title)
    art_meta = (f'<meta property="article:published_time" content="{date}">\n'
                f'<meta property="article:modified_time" content="{date}">\n') if date else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#04121a">
<title>{e(title)} | NFSU.cc</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url(lang, name)}">
{alts}<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="{'website' if name == 'index' else 'article'}">
<meta property="og:site_name" content="NFSU.cc">
<meta property="og:url" content="{url(lang, name)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{og_url_img}">
<meta property="og:image:alt" content="{alt_txt}">
<meta property="og:locale" content="{'en_US' if lang == 'en' else 'es_MX'}">
<meta property="og:locale:alternate" content="{'es_MX' if lang == 'en' else 'en_US'}">
{art_meta}<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{og_url_img}">
<meta name="twitter:image:alt" content="{alt_txt}">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="apple-touch-icon" href="/icon-180.png">
<link rel="alternate" type="application/atom+xml" title="NFSU.cc Engineering Devlog" href="{SITE}/feed.xml">
<link rel="stylesheet" href="../blog.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body style="--pic: url(/blog/img/{pic})">
<header class="top">
  <a class="logo" href="/"><img src="/launcher/v2/ui/logo.webp" alt="Need for Speed Underground" width="688" height="125"></a>
  <nav>
    <a href="index.html">{u['guides']}</a>
    <a href="/re/{'es/' if lang == 'es' else ''}index.html">{'Atlas RE' if lang == 'es' else 'RE Atlas'}</a>
    <a href="/devlog/{'es/' if lang == 'es' else ''}index.html">{'Bitácora' if lang == 'es' else 'Devlog'}</a>
    <a href="../{other}/{names[other]}.html" hreflang="{other}" lang="{other}">{u['other']}</a>
    <a href="{REPO}" rel="noopener">GitHub</a>
    <a class="play" href="/">{u['play']}</a>
  </nav>
</header>
<main>
{inner}
</main>
<footer><span>{u['foot']}</span><a href="/">{u['play']}</a><a href="index.html">{u['guides']}</a><a href="/re/{'es/' if lang == 'es' else ''}index.html">{'Atlas RE' if lang == 'es' else 'RE Atlas'}</a><a href="/devlog/{'es/' if lang == 'es' else ''}index.html">{'Bitácora' if lang == 'es' else 'Devlog'}</a><a href="/llms.txt">llms.txt</a><a href="/feed.xml">RSS</a><a href="{REPO}" rel="noopener">{u['code']}</a><a href="../{other}/{names[other]}.html" hreflang="{other}" lang="{other}">{u['other']}</a></footer>
</body>
</html>
"""


def rows(lang, skip=None, only=None):
    return '<ul class="list">' + "".join(
        '<li><a href="%s.html"><b>%s</b><span>%s</span></a></li>' % (a["slug"][lang], e(a["title"][lang]), e(a["desc"][lang]))
        for a in ARTICLES if a["key"] != skip and (only is None or a.get("dev", False) == only)) + "</ul>"


def figure(a, lang, n=""):
    return '<figure><img src="../img/%s" alt="%s" width="1000" height="%d" %s><figcaption>%s</figcaption></figure>' % (
        a["img" + n], e(a["alt" + n][lang]), HEIGHT[a["img" + n]], 'loading="lazy"' if n else 'fetchpriority="high"', e(a["cap" + n][lang]))


HEIGHT = {"olympic-city-world.webp": 700, "bayview-palms.webp": 703, "bayview-race.webp": 703, "world-map.webp": 850, "phone-touch.webp": 462, "olympic-city-drive.webp": 703}
BACK = ["olympic-city-drive.webp", "olympic-city-world.webp"]   # behind the sheet: a street picture that is not the one shown in the text
ORG = {"@type": "Organization", "name": "NFSU.cc", "url": SITE + "/", "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png"}}
PLAY_FAQ = {
    "en": [
        ("Is NFSU.cc an emulator or a remake?", "Neither. It is a static recompilation of the original 2003 PC executable (Speed.exe) to WebAssembly, so the physics, AI rivals, menus and career progression are the original game's own code."),
        ("Does it include the original soundtrack?", "Yes. Every song from the 2003 PC soundtrack is included and streams as you play."),
        ("Does it work on Android and iPhone?", "Yes. Phones and tablets automatically use a lighter 448 MB WebAssembly build, Original 2003 graphics, 30 fps and on-screen touch controls. On iPhone, add the page to your Home Screen for full screen."),
        ("Is it free and do I need an account?", "It is free, with no account and nothing to install. Saves stay locally in your browser and can be exported as a backup file at any time."),
    ],
    "es": [
        ("¿NFSU.cc es un emulador o un remake?", "Ninguno de los dos. Es una recompilación estática del ejecutable original de PC de 2003 (Speed.exe) a WebAssembly, así que la física, los rivales, los menús y el modo carrera son el código del propio juego."),
        ("¿Trae el soundtrack original completo?", "Sí. Incluye todas las canciones originales del juego de PC de 2003."),
        ("¿Funciona en Android y iPhone?", "Sí. Los celulares y tabletas cargan automáticamente un build ligero de 448 MB en WebAssembly, gráficos Original 2003, 30 fps y controles táctiles en pantalla. En iPhone, agrégalo a la pantalla de inicio para jugar a pantalla completa."),
        ("¿Es gratis y pide cuenta?", "Es gratis, sin cuenta y sin instalar nada. Tus partidas se guardan en tu navegador y puedes descargar un respaldo cuando quieras."),
    ],
}
pages = []          # (lang, name, names) for the sitemap
for lang in LANGS:
    os.makedirs(os.path.join(W, "blog", lang), exist_ok=True)
    u = UI[lang]
    for old in os.listdir(os.path.join(W, "blog", lang)):
        os.remove(os.path.join(W, "blog", lang, old))
    # hub
    names = {l: "index" for l in LANGS}
    inner = f'<h1>{u["hub_h1"]}</h1>\n<p class="lead">{e(u["hub_lead"])}</p>\n{rows(lang, only=False)}\n<h2 class="more">{u["dev"]}</h2>\n{rows(lang, only=True)}\n<p><a href="{REPO}" rel="noopener">{u["code"]}</a></p>\n<div class="cta"><a href="/">{u["cta"]}</a></div>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": u["hub_title"], "description": u["hub_desc"], "url": url(lang, "index"), "inLanguage": lang,
          "isPartOf": {"@type": "WebSite", "name": "NFSU.cc", "url": SITE + "/"},
          "hasPart": [{"@type": "Article", "headline": a["title"][lang], "url": url(lang, a["slug"][lang])} for a in ARTICLES]}
    open(os.path.join(W, "blog", lang, "index.html"), "w", encoding="utf-8").write(page(lang, "index", names, u["hub_title"], u["hub_desc"], BACK[1], u["hub_h1"], inner, ld))
    pages.append((lang, "index", names))
    for a in ARTICLES:
        names = a["slug"]
        date = DEV_DATE if a.get("dev") else DATE
        body = re.sub(r"\[\[(\w+)\]\]", lambda m: figure(a, lang, "2") if m.group(1) == "figure2" else BY[m.group(1)]["slug"][lang] + ".html", a["body"][lang].strip())
        inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / <a href="index.html">{u['guides']}</a></p>
<article>
<h1>{e(a['title'][lang])}</h1>
<p class="lead">{e(a['lead'][lang])}</p>
<p class="date"><time datetime="{date}">{u['updated'] % WHEN[lang](date)}</time></p>
{figure(a, lang)}
{body}
<p class="repo"><b>{u['inrepo']}</b> {" · ".join('<a href="%s/%s/main/%s" rel="noopener"><code>%s</code></a>' % (REPO, "blob" if "." in c.rsplit("/", 1)[-1] else "tree", c, c) for c in CODE[a['key']])}</p>
<div class="cta"><a href="/">{u['cta']}</a></div>
</article>
<h2 class="more">{u['more']}</h2>
{rows(lang, a['key'], a.get('dev', False))}"""
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "TechArticle" if a.get("dev") else "Article", "headline": a["title"][lang], "description": a["desc"][lang], "inLanguage": lang, "datePublished": date, "dateModified": date,
             "image": "%s/blog/img/%s" % (SITE, a["img"]), "mainEntityOfPage": url(lang, names[lang]), "author": ORG, "publisher": ORG,
             "about": {"@type": "VideoGame", "name": "Need for Speed Underground", "url": SITE + "/"}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "NFSU.cc", "item": SITE + "/"},
                {"@type": "ListItem", "position": 2, "name": u["guides"], "item": url(lang, "index")},
                {"@type": "ListItem", "position": 3, "name": a["title"][lang], "item": url(lang, names[lang])}]}]
              + ([{"@type": "SoftwareSourceCode", "name": "need-for-speed-underground-browser", "codeRepository": REPO, "url": REPO, "programmingLanguage": ["C", "Python", "JavaScript"],
                   "runtimePlatform": "WebAssembly", "description": "Static recompilation of Need for Speed Underground (2003, PC) to WebAssembly."}] if a.get("dev") else [])
              + ([{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in PLAY_FAQ[lang]]}] if a["key"] == "play" else [])}
        open(os.path.join(W, "blog", lang, names[lang] + ".html"), "w", encoding="utf-8").write(page(lang, names[lang], names, a["title"][lang], a["desc"][lang], next(b for b in BACK if b not in (a["img"], a.get("img2"))), a["title"][lang], inner, ld, date=date, og_alt=a["alt"][lang]))
        pages.append((lang, names[lang], names))

BY_SLUG = {a["slug"][l]: a for a in ARTICLES for l in LANGS}
# sitemap: the game's address and every guide, each with its language twins + x-default
sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
      "<url><loc>%s/</loc><lastmod>%s</lastmod></url>" % (SITE, DATE)]
for lang, name, names in pages:
    lm = DEV_DATE if name != "index" and BY_SLUG[name].get("dev") else DATE
    links = "".join('<xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (l, url(l, names[l])) for l in LANGS)
    links += '<xhtml:link rel="alternate" hreflang="x-default" href="%s"/>' % url("en", names["en"])
    sm.append("<url><loc>%s</loc><lastmod>%s</lastmod>%s</url>" % (url(lang, name), lm, links))

import build_re_devlog
extra_urls = build_re_devlog.build_all()
for loc, lm, alts in extra_urls:
    links = ""
    if alts:
        links = "".join('<xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (l, u) for l, u in alts.items())
        if "en" in alts:
            links += '<xhtml:link rel="alternate" hreflang="x-default" href="%s"/>' % alts["en"]
    sm.append("<url><loc>%s</loc><lastmod>%s</lastmod>%s</url>" % (loc, lm, links))
sm.append("</urlset>")
open(os.path.join(W, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm) + "\n")

# robots: pages, guides, RE atlas, devlog, feeds & LLM compendiums stay open; heavy binary data & manifests stay closed
open(os.path.join(W, "robots.txt"), "w", encoding="utf-8").write("""User-agent: *
Allow: /
Disallow: /game/
Disallow: /data-chunks/
Disallow: /pc/
Disallow: /remaster/
Disallow: /world/
Disallow: /out/
Disallow: /diag.html
Disallow: /launcher_b/index.html
Disallow: /game-files.json
Disallow: /data-chunks.json
Disallow: /manifest.json
Disallow: /seed_save.json

User-agent: ClaudeBot
User-agent: PerplexityBot
User-agent: GPTBot
User-agent: OAI-SearchBot
User-agent: Google-Extended
User-agent: Applebot-Extended
Allow: /
Allow: /re/
Allow: /devlog/
Allow: /blog/
Allow: /llms.txt
Allow: /llms-full.txt
Allow: /feed.xml
Disallow: /game/
Disallow: /data-chunks/
Disallow: /pc/
Disallow: /remaster/
Disallow: /world/
Disallow: /out/

Sitemap: %s/sitemap.xml
""" % SITE)
print("blog: %d pages + %d RE/devlog URLs, sitemap.xml, robots.txt" % (len(pages), len(extra_urls)))
