"""How-it-works posts for tools/build_blog.py: what runs today and why, for people who search RE and decomp, not only the game.
Present tense, current numbers, no history. Same rule as the guides: every number names its source above the post."""

from site_common import REPO
# Repo folders and files each post explains: shown as "In the repo" links under the post.
CODE = dict(play=["web", "web/launcher.js", "web/saves.js"], controls=["web/input.js", "web/pad.js", "web/touch.js", "host/dinput8.c"],
            devices=["web/gpu.js", "web/audio.js", "web/webgpu_gl.js"], tech=["tools/recomp", "host", "web", "census"],
            recomp=["tools/recomp", "tools/recomp/lift.py", "tools/recomp/difftest.py", "tools/recomp/patches.py", "tools/recomp/abk.py"],
            retools=["docs/re", "census", "tools/hopper", "census/ghidra"], host=["host", "host/d3d9.c", "host/gpu.c", "web/gpu.js", "host/dsound.c", "host/threads.c"],
            load=["host/files.c", "tools/build_public.py", "tools/data_chunks.py", "docs/re/hosting.md"], agents=["tools/recomp/difftest.py", "docs/re", "census"])
DEV_DATE = "2026-11-21"

DEV = [
    # Sources: tools/recomp/lift.py docstring (Capstone, f_<addr>(Ctx*), registers and flags as C locals, rn_call, TRAP);
    # tools/recomp/build.py:16 CHUNKS = 160 (clang -O2 native, emcc -O2 -pthread web); census/lift_report.json (13,764 functions,
    # 106 ABK files, 79 modules, 28 ABK functions); host/abk.c; tools/recomp/difftest.py docstring (Unicorn oracle, random inputs, registers,
    # x87 stack, all memory); census/difftest.json (5,805 compared, 5,802 all match, 3 with mismatches); patches tools/recomp/patches_*.py.
    dict(key="recomp", img="olympic-city-drive.webp", dev=True,
         slug=dict(en="static-recompilation-x86-to-webassembly", es="recompilacion-estatica-x86-a-webassembly"),
         title=dict(en="Static recompilation: how a 2003 x86 .exe runs as WebAssembly", es="Recompilación estática: cómo un .exe x86 de 2003 corre como WebAssembly"),
         desc=dict(en="How NFSU.cc turns Speed.exe into WebAssembly: Capstone reads it, every one of its 13,764 functions becomes C, Emscripten compiles them, and Unicorn checks them bit for bit.",
                   es="Cómo NFSU.cc convierte Speed.exe en WebAssembly: Capstone lo lee, cada una de sus 13,764 funciones pasa a C, Emscripten las compila y Unicorn las revisa bit a bit."),
         alt=dict(en="Olympic City at night, drawn by the recompiled game", es="Olympic City de noche, dibujada por el juego recompilado"),
         cap=dict(en="Every frame here comes from functions translated out of the 2003 executable.", es="Cada cuadro sale de funciones traducidas del ejecutable de 2003."),
         lead=dict(en="There is no source code for Need for Speed Underground. There is one Windows program, Speed.exe, and a translator that turns it, function by function, into code a browser runs.",
                   es="No existe el código fuente de Need for Speed Underground. Existe un programa de Windows, Speed.exe, y un traductor que lo convierte, función por función, en código que corre un navegador."),
         body=dict(en="""
<h2>Translate once instead of emulating forever</h2>
<p>An emulator reads each x86 instruction while you play and imitates it, on every frame. Static recompilation pays once: before the page exists, a tool reads the whole program and writes the same logic in another language. When you open the site, the translation is already done, and the browser runs it at close to native speed.</p>
<h2>The translator</h2>
<p>The translator is a Python program (<a href="REPO/blob/main/tools/recomp/lift.py">tools/recomp/lift.py</a>). It opens the executable with <b>pefile</b>, disassembles it with <b>Capstone</b> and writes every function of the game as one C function:</p>
<ul>
<li>The eight x86 registers and the flags are C local variables, written back to a shared context only at calls and exits, so the C compiler optimizes them like normal code.</li>
<li>A direct call is a direct C call. An indirect call or jump, through a pointer the game computes, goes through one table from game address to function.</li>
<li>An instruction the translator does not know becomes a <b>TRAP</b>: if it ever runs, the game stops and prints its address. Nothing is guessed.</li>
</ul>
<p>The list of functions comes from a census of the executable. The translator writes all 13,764 of them into 160 files of C, and <code>emcc</code> (Emscripten) compiles them with <code>-O2</code> into one WebAssembly program. The same C also builds natively with <code>clang</code>, for tests.</p>
<h2>Code that hides in the data</h2>
<p>Not all of the game's code lives in Speed.exe. Its sound engine loads small x86 modules out of the <code>.abk</code> sound banks and relocates them in memory. A static translator never sees that code in the executable, so a second pass reads all 106 sound banks, finds 79 code modules (28 distinct functions) and translates them ahead of time. When the game loads one, the host recognizes it by its header and calls the translated version.</p>
<h2>Checked bit for bit</h2>
<p>A translation is only useful if it is exact. <a href="REPO/blob/main/tools/recomp/difftest.py">difftest.py</a> runs each translated function next to <b>Unicorn</b>, a reference x86 CPU, on random inputs. Both stop at the first Windows call or at the return, and every register, the x87 floating point stack and all of memory are compared. Of the 5,805 functions it reaches, 5,802 match on every case; the three that differ are listed by address. Unicorn is only the judge: it never ships in the game.</p>
<h2>Changing the game without editing the game</h2>
<p>Fixes and options are patches applied while translating: small files such as <code>patches_render.py</code> or <code>patches_input.py</code>, one line per patch, each with the address it changes and the reason. The executable's bytes stay as they are, and the Original 2003 version plays as the game shipped.</p>
<h2>Read the code</h2>
<p>The translator, the tests and the patch files are on <a href="REPO">GitHub</a>. The next piece is what answers the game when it calls Windows: <a href="[[host]]">DirectX 9 and Windows rebuilt for the browser</a>.</p>
""", es="""
<h2>Traducir una vez en vez de emular siempre</h2>
<p>Un emulador lee cada instrucción x86 mientras juegas y la imita, en cada cuadro. La recompilación estática paga una sola vez: antes de que exista la página, una herramienta lee todo el programa y escribe la misma lógica en otro lenguaje. Cuando abres el sitio, la traducción ya está hecha, y el navegador la corre casi a velocidad nativa.</p>
<h2>El traductor</h2>
<p>El traductor es un programa en Python (<a href="REPO/blob/main/tools/recomp/lift.py">tools/recomp/lift.py</a>). Abre el ejecutable con <b>pefile</b>, lo desensambla con <b>Capstone</b> y escribe cada función del juego como una función de C:</p>
<ul>
<li>Los ocho registros x86 y las banderas son variables locales de C, que se escriben de vuelta a un contexto compartido solo en llamadas y salidas; así el compilador las optimiza como código normal.</li>
<li>Una llamada directa es una llamada directa de C. Una llamada o salto indirecto, por un puntero que calcula el juego, pasa por una tabla que va de dirección del juego a función.</li>
<li>Una instrucción que el traductor no conoce se vuelve un <b>TRAP</b>: si alguna vez se ejecuta, el juego se detiene e imprime su dirección. Nada se adivina.</li>
</ul>
<p>La lista de funciones sale de un censo del ejecutable. El traductor escribe las 13,764 en 160 archivos de C, y <code>emcc</code> (Emscripten) los compila con <code>-O2</code> en un solo programa WebAssembly. El mismo C también compila nativo con <code>clang</code>, para pruebas.</p>
<h2>Código escondido en los datos</h2>
<p>No todo el código del juego vive en Speed.exe. Su motor de sonido carga pequeños módulos x86 desde los bancos de sonido <code>.abk</code> y los reubica en memoria. Un traductor estático nunca ve ese código en el ejecutable, así que una segunda pasada lee los 106 bancos, encuentra 79 módulos de código (28 funciones distintas) y los traduce por adelantado. Cuando el juego carga uno, el host lo reconoce por su encabezado y llama a la versión traducida.</p>
<h2>Revisado bit a bit</h2>
<p>Una traducción solo sirve si es exacta. <a href="REPO/blob/main/tools/recomp/difftest.py">difftest.py</a> corre cada función traducida junto a <b>Unicorn</b>, un CPU x86 de referencia, con entradas aleatorias. Los dos se detienen en la primera llamada a Windows o en el retorno, y se comparan todos los registros, la pila de punto flotante x87 y toda la memoria. De las 5,805 funciones que alcanza, 5,802 coinciden en todos los casos; las tres que difieren quedan anotadas por dirección. Unicorn es solo el juez: nunca va dentro del juego.</p>
<h2>Cambiar el juego sin editar el juego</h2>
<p>Las correcciones y opciones son parches que se aplican al traducir: archivos pequeños como <code>patches_render.py</code> o <code>patches_input.py</code>, una línea por parche, cada una con la dirección que cambia y el porqué. Los bytes del ejecutable se quedan como están, y la versión Original 2003 se juega como salió.</p>
<h2>Lee el código</h2>
<p>El traductor, las pruebas y los parches están en <a href="REPO">GitHub</a>. La siguiente pieza es lo que le responde al juego cuando llama a Windows: <a href="[[host]]">DirectX 9 y Windows reconstruidos para el navegador</a>.</p>
""")),

    # Sources: AGENTS.md (REA MCP + a second tool on every value; census V/I/U; Hopper census/hopper/decomp.c; Ghidra headless census/ghidra/;
    # objdump); census/names_*.tsv = 56 files, 10,755 lines (wc 2026-11-21); census/speed_exe_functions.tsv 14,330 lines;
    # RN_TRACE in host/d3d9.c header; menu action table 0x7032d8 action Back 0x17 docs/re/hud_input.md:47, census/names_input.tsv:16;
    # docs/re/README.md (one note per system).
    dict(key="retools", img="olympic-city-world.webp", dev=True,
         slug=dict(en="reverse-engineering-tools-ghidra-hopper-rea", es="herramientas-ingenieria-inversa-ghidra-hopper-rea"),
         title=dict(en="Reading the binary: Ghidra, Hopper, REA and a census of names", es="Leer el binario: Ghidra, Hopper, REA y un censo de nombres"),
         desc=dict(en="The disassemblers and decompilers behind every option and fix in Need for Speed Underground on NFSU.cc, and the rule that keeps them honest: no address counts until two tools agree.",
                   es="Los desensambladores y descompiladores detrás de cada opción y arreglo de Need for Speed Underground en NFSU.cc, y la regla que los mantiene honestos: ninguna dirección vale hasta que dos herramientas coinciden."),
         alt=dict(en="A street in Olympic City from the recompiled game", es="Una calle de Olympic City en el juego recompilado"),
         cap=dict(en="Every option on this site touches an address someone read first.", es="Cada opción de este sitio toca una dirección que alguien leyó primero."),
         lead=dict(en="Recompiling a game makes it run. Changing it, fixing it or adding options means understanding it, and a 2003 executable comes with no names, no symbols and no comments.",
                   es="Recompilar un juego lo hace correr. Cambiarlo, corregirlo o agregarle opciones exige entenderlo, y un ejecutable de 2003 llega sin nombres, sin símbolos y sin comentarios."),
         body=dict(en="""
<h2>The tools</h2>
<ul>
<li><b>Ghidra</b>, run headless from scripts: the whole executable decompiled to C-like code, saved as text so any search tool can read it.</li>
<li><b>Hopper</b>, a disassembler for macOS: a second decompiler with its own opinion of each function, exported the same way.</li>
<li><b>REA</b>, a reverse engineering server that AI agents talk to over MCP (Model Context Protocol): open the binary, read a function's pseudocode, list who calls an address, read raw bytes.</li>
<li><b>objdump</b> and <b>Capstone</b> for the plain instruction listing, the last word when the decompilers disagree.</li>
<li><b>The running game</b>: a trace switch logs every Windows and DirectX call with its arguments, so what a function is believed to do can be checked against what it does.</li>
</ul>
<h2>Two tools or it does not count</h2>
<p>Decompilers are wrong in small ways: a missed argument, a float read as an integer, a jump table cut short. So every value, file format or patch names what proves it (an address in the executable, a chunk id in a data file, a line in the code), read with REA plus a second tool. What is not proven is marked UNKNOWN, and nothing is built on it.</p>
<h2>A census instead of a wiki</h2>
<p>Names are plain tables, one per system: cars, camera, collision, menus, audio, the rival AI. Each row is an address, a name and a mark: <b>V</b> when it was read in the code, <b>I</b> when it is inferred, <b>U</b> when unknown. There are 56 of those tables with about 10,700 rows, next to a census of the 14,330 function entries in Speed.exe. A table can be searched, compared and checked by a script; a page of prose cannot.</p>
<h2>An example</h2>
<p>The phone controls have a BACK button. It does not fake a key and hope: the menu's action table in the game (address 0x7032d8) has an action Back, bound to Escape and Backspace. The touch button sends exactly that key, and the game does the rest the way it always did.</p>
<h2>One note per system</h2>
<p>What the game does inside is kept as one short note per system in <code>docs/re/</code>: how the camera follows the car, how rivals pick a line, how a track loads. They are maps, not essays, and they are on <a href="REPO/tree/main/docs/re">GitHub</a>. AI agents do much of the reading under these rules: <a href="[[agents]]">how that works</a>.</p>
""", es="""
<h2>Las herramientas</h2>
<ul>
<li><b>Ghidra</b>, sin ventana, desde scripts: todo el ejecutable descompilado a un código parecido a C, guardado como texto para que cualquier buscador lo lea.</li>
<li><b>Hopper</b>, un desensamblador para macOS: un segundo descompilador con su propia opinión de cada función, exportado igual.</li>
<li><b>REA</b>, un servidor de ingeniería inversa con el que hablan los agentes de IA por MCP (Model Context Protocol): abrir el binario, leer el pseudocódigo de una función, ver quién llama a una dirección, leer bytes crudos.</li>
<li><b>objdump</b> y <b>Capstone</b> para la lista simple de instrucciones, la última palabra cuando los descompiladores no coinciden.</li>
<li><b>El juego corriendo</b>: un interruptor de traza registra cada llamada a Windows y DirectX con sus argumentos, para comparar lo que se cree que hace una función con lo que de verdad hace.</li>
</ul>
<h2>Dos herramientas o no cuenta</h2>
<p>Los descompiladores se equivocan en cosas pequeñas: un argumento perdido, un número decimal leído como entero, una tabla de saltos cortada. Por eso cada valor, formato de archivo o parche nombra lo que lo prueba (una dirección del ejecutable, un id de bloque en un archivo de datos, una línea del código), leído con REA más una segunda herramienta. Lo que no está probado se marca UNKNOWN, y nada se construye encima.</p>
<h2>Un censo en vez de una wiki</h2>
<p>Los nombres son tablas simples, una por sistema: coches, cámara, colisiones, menús, audio, la IA de los rivales. Cada fila es una dirección, un nombre y una marca: <b>V</b> si se leyó en el código, <b>I</b> si se deduce, <b>U</b> si se desconoce. Hay 56 tablas con unas 10,700 filas, junto a un censo de las 14,330 entradas de función de Speed.exe. Una tabla se puede buscar, comparar y revisar con un script; una página de prosa no.</p>
<h2>Un ejemplo</h2>
<p>Los controles de celular tienen un botón ATRÁS. No simula una tecla a ver si funciona: la tabla de acciones del menú del juego (dirección 0x7032d8) tiene una acción Back, ligada a Escape y Retroceso. El botón táctil manda exactamente esa tecla, y el juego hace el resto como siempre lo hizo.</p>
<h2>Una nota por sistema</h2>
<p>Lo que el juego hace por dentro se guarda como una nota corta por sistema en <code>docs/re/</code>: cómo la cámara sigue al coche, cómo eligen línea los rivales, cómo carga una pista. Son mapas, no ensayos, y están en <a href="REPO/tree/main/docs/re">GitHub</a>. Buena parte de la lectura la hacen agentes de IA bajo estas reglas: <a href="[[agents]]">así funciona</a>.</p>
""")),

    # Sources: host/win32.c header (Windows XP SP2, one CPU, code page 1252, C:\\NFSU); host/d3d9.c header (ATI RADEON 9800 PRO 128 MB HAL, vtable
    # slots as host functions, missing method stops loudly); host/gpu.c + web/gpu.js headers (frame command list, mailbox in the shared heap,
    # WebGPU on the page's thread); web/webgpu_gl.js (WebGL 2 when there is no WebGPU); host/sm1.c (shader model 1 -> WGSL);
    # host/dsound.c + web/audio.js (software mixer 44.1 kHz, AudioWorklet); host/threads.c (one global lock in ticket order);
    # host/files.c (synchronous XHR in a worker, data pieces); host/dinput8.c; web/saves.js; host/*.c + *.h = 14,795 lines (wc 2026-11-21).
    dict(key="host", img="phone-touch.webp", dev=True,
         slug=dict(en="directx-9-and-windows-on-webgpu", es="directx-9-y-windows-sobre-webgpu"),
         title=dict(en="DirectX 9 and Windows XP rebuilt on WebGPU, Web Audio and workers", es="DirectX 9 y Windows XP reconstruidos sobre WebGPU, Web Audio y workers"),
         desc=dict(en="The recompiled game still calls Windows and DirectX. This is the layer that answers: a Radeon 9800 that draws with WebGPU, a sound card made of an AudioWorklet, and a hard drive that lives on a server.",
                   es="El juego recompilado sigue llamando a Windows y DirectX. Esta es la capa que contesta: una Radeon 9800 que dibuja con WebGPU, una tarjeta de sonido hecha con un AudioWorklet y un disco duro que vive en un servidor."),
         alt=dict(en="The browser version on a phone with touch controls", es="La versión de navegador en un celular con controles táctiles"),
         cap=dict(en="The game asks for a keyboard; on a phone the touch layer answers with the key codes it expects.", es="El juego pide un teclado; en un celular la capa táctil contesta con los códigos de tecla que espera."),
         lead=dict(en="Translated code is not enough. The game opens windows, files and sound buffers, and asks for a DirectX 9 card. About 14,800 lines of C and a few JavaScript files answer every one of those calls.",
                   es="El código traducido no basta. El juego abre ventanas, archivos y búferes de sonido, y pide una tarjeta DirectX 9. Unas 14,800 líneas de C y unos cuantos archivos de JavaScript contestan cada una de esas llamadas."),
         body=dict(en="""
<h2>A PC from 2003, always the same one</h2>
<p>The host presents one machine and sticks to it: Windows XP SP2, one CPU, code page 1252, the game installed at <code>C:\\NFSU</code>, and an ATI Radeon 9800 Pro with 128 MB on a 1920x1080 desktop. Each Windows function is written from Microsoft's documentation and knows nothing about the game. A call to a method that does not exist stops the game with that method's name instead of carrying on with a wrong answer.</p>
<h2>Graphics: DirectX 9 to WebGPU</h2>
<p>The game draws through DirectX 9 objects. The host keeps those objects in the game's own memory and records each frame as a compact list of commands. When the game presents a frame, the list goes through a mailbox in shared memory to the page, which runs it with <b>WebGPU</b>, or WebGL 2 on a browser without it. The game's shaders are shader model 1 bytecode; a small translator decodes them and writes WGSL, the shader language of WebGPU.</p>
<h2>Sound: a software mixer and an AudioWorklet</h2>
<p>DirectSound gives the game sound buffers in its own memory. A mixer thread reads them the way a 2003 sound card read its buffers, at 44.1 kHz, and writes into a ring in shared memory. In the page, an <b>AudioWorklet</b> plays that ring and resyncs when the two clocks drift apart.</p>
<h2>Threads: real ones, one at a time</h2>
<p>The game starts several threads. Each one is a real thread (a Web Worker in the browser), but one global lock, handed out in ticket order, lets only one run game code at a time. A thread gives the lock up only where Windows would block it: sleeping, waiting, a busy critical section. The translated code needs no atomics, and the game still sees real threads. Shared memory between workers is why the site is served with cross-origin isolation headers.</p>
<h2>Files: a hard drive on the internet</h2>
<p>The game reads its files with ordinary Windows calls. In the browser, a reading thread turns each read into an HTTP request, synchronous inside its worker, so the game waits exactly as it waited for a hard drive. How that stays fast over the internet: <a href="[[load]]">loading and hosting</a>.</p>
<h2>Input and saves</h2>
<p>DirectInput is rebuilt with one keyboard and one mouse. Gamepads and phone buttons are translated into the keyboard codes the game expects, so its own controls menu still works. The save folder lives in memory and is copied to the browser's storage a moment after each change.</p>
<p>Every file named here is on <a href="REPO/tree/main/host">GitHub</a>.</p>
""", es="""
<h2>Una PC de 2003, siempre la misma</h2>
<p>El host presenta una sola máquina y no se sale de ella: Windows XP SP2, un CPU, página de códigos 1252, el juego instalado en <code>C:\\NFSU</code>, y una ATI Radeon 9800 Pro de 128 MB en un escritorio de 1920x1080. Cada función de Windows se escribe desde la documentación de Microsoft y no sabe nada del juego. Una llamada a un método que no existe detiene el juego con el nombre de ese método en vez de seguir con una respuesta equivocada.</p>
<h2>Gráficos: de DirectX 9 a WebGPU</h2>
<p>El juego dibuja con objetos de DirectX 9. El host guarda esos objetos en la memoria del propio juego y registra cada cuadro como una lista compacta de comandos. Cuando el juego presenta un cuadro, la lista pasa por un buzón en memoria compartida a la página, que la ejecuta con <b>WebGPU</b>, o con WebGL 2 en un navegador que no lo tiene. Los shaders del juego son bytecode de shader model 1; un traductor pequeño los decodifica y escribe WGSL, el lenguaje de shaders de WebGPU.</p>
<h2>Sonido: un mezclador por software y un AudioWorklet</h2>
<p>DirectSound le da al juego búferes de sonido en su propia memoria. Un hilo mezclador los lee como una tarjeta de sonido de 2003 leía los suyos, a 44.1 kHz, y escribe en un anillo de memoria compartida. En la página, un <b>AudioWorklet</b> reproduce ese anillo y se resincroniza cuando los dos relojes se separan.</p>
<h2>Hilos: reales, uno a la vez</h2>
<p>El juego arranca varios hilos. Cada uno es un hilo real (un Web Worker en el navegador), pero un candado global, repartido por turnos, deja que solo uno ejecute código del juego a la vez. Un hilo suelta el candado solo donde Windows lo bloquearía: dormir, esperar, una sección crítica ocupada. El código traducido no necesita operaciones atómicas, y el juego sigue viendo hilos reales. La memoria compartida entre workers es la razón de que el sitio se sirva con aislamiento de origen cruzado.</p>
<h2>Archivos: un disco duro en internet</h2>
<p>El juego lee sus archivos con llamadas normales de Windows. En el navegador, un hilo lector convierte cada lectura en una petición HTTP, síncrona dentro de su worker, así el juego espera igual que esperaba a un disco duro. Cómo se mantiene rápido por internet: <a href="[[load]]">carga y hosting</a>.</p>
<h2>Controles y partidas</h2>
<p>DirectInput se reconstruye con un teclado y un ratón. Los mandos y los botones del celular se traducen a los códigos de teclado que el juego espera, así su propio menú de controles sigue funcionando. La carpeta de partidas vive en memoria y se copia al almacenamiento del navegador un momento después de cada cambio.</p>
<p>Cada archivo nombrado aquí está en <a href="REPO/tree/main/host">GitHub</a>.</p>
""")),

    # Sources: one cold visit to https://nfsu.cc/?go=1 with tools/loadcap.mjs, 2026-11-21: 32.6 MB in 108 requests to the main menu,
    # /out/speed.wasm 11.1 MB content-encoding br (curl -I the same day); tools/upload_r2.sh:29 (speed.wasm 70 MB -> 11.1 MB brotli q11);
    # tools/build_public.py:100 + tools/data_chunks.py (473 read pieces, Content-Encoding br); host/files.c:119-135 (pieces by
    # read, Range for the rest), :257 WHOLE_MAX 8 MB, :329 prefetch threads from web/entry_hint.tsv; build log 2026-11-21 (2.04 GB, songs
    # and movies kept); docs/re/hosting.md (R2, COOP/COEP/CORP, cache rule: pages and scripts no-cache, data 1 day).
    dict(key="load", img="olympic-city-drive.webp", dev=True,
         slug=dict(en="hosting-a-2-gb-game-on-cloudflare-r2-load-time", es="alojar-un-juego-de-2-gb-en-cloudflare-r2-tiempo-de-carga"),
         title=dict(en="Hosting a 2 GB PC game on Cloudflare R2: 32 MB to the main menu", es="Alojar un juego de PC de 2 GB en Cloudflare R2: 32 MB hasta el menú"),
         desc=dict(en="How NFSU.cc serves the whole of Need for Speed Underground, music included, so a first visit reaches the menu after 32 MB: brotli pieces cut to the game's own reads, whole small files and prefetch.",
                   es="Cómo NFSU.cc sirve Need for Speed Underground completo, con música, para que una primera visita llegue al menú tras 32 MB: piezas brotli cortadas a las lecturas del juego, archivos chicos completos y precarga."),
         alt=dict(en="Driving through Olympic City after the game finished loading", es="Manejando por Olympic City después de que el juego terminó de cargar"),
         cap=dict(en="The first visit downloads only what the game reads; the rest waits until you drive there.", es="La primera visita baja solo lo que el juego lee; lo demás espera hasta que manejas ahí."),
         lead=dict(en="A hard drive answers a read in a few milliseconds; a server far away answers in tens. The game does not know the difference, and it reads a lot. Three things make that work over the internet.",
                   es="Un disco duro contesta una lectura en unos milisegundos; un servidor lejano, en decenas. El juego no sabe la diferencia, y lee mucho. Tres cosas hacen que funcione por internet."),
         body=dict(en="""
<h2>The whole game, music included</h2>
<p>The public pack is about 2 GB: the recompiled program, the game's data, every licensed song and the movies. Nothing is cut. The program, speed.wasm, is 70 MB and travels as 11.1 MB of brotli. A cold first visit reaches the game's main menu after 32.6 MB in 108 requests; tracks and cars arrive when the game asks for them.</p>
<h2>Where it is hosted</h2>
<ul>
<li><b>Cloudflare R2</b> holds the files. Downloads from R2 cost nothing, which matters for a 2 GB game.</li>
<li>Three response headers (<code>Cross-Origin-Opener-Policy</code>, <code>Cross-Origin-Embedder-Policy</code>, <code>Cross-Origin-Resource-Policy</code>) turn on cross-origin isolation, which the browser requires before it shares memory between the game's threads.</li>
<li>Pages and scripts are never cached at the edge; game data is cached for a day. Scripts carry the build number in their address, so a new build never mixes with an old one.</li>
</ul>
<h2>Why it loads fast</h2>
<ul>
<li><b>Pieces cut to the game's reads.</b> The reads the game always makes are stored as 473 brotli-compressed pieces, each exactly one read. The browser fetches a piece and unpacks it on the way in; any other read is a plain byte range.</li>
<li><b>Small files come whole.</b> A file up to 8 MB is fetched in one request on its first read and kept, so its next reads cost no round trip.</li>
<li><b>Prefetch.</b> A list of what the game opens on the way to the menu and the first race lets helper threads fetch those files before the game asks.</li>
</ul>
<p>The loader is <a href="REPO/blob/main/host/files.c">host/files.c</a> and the pieces are cut by <a href="REPO/blob/main/tools/data_chunks.py">tools/data_chunks.py</a>. To see the result, <a href="/">open the game</a>.</p>
""", es="""
<h2>El juego completo, con música</h2>
<p>El paquete público pesa unos 2 GB: el programa recompilado, los datos del juego, cada canción con licencia y los videos. No se recorta nada. El programa, speed.wasm, pesa 70 MB y viaja como 11.1 MB de brotli. Una primera visita en frío llega al menú principal del juego tras 32.6 MB en 108 peticiones; pistas y coches llegan cuando el juego los pide.</p>
<h2>Dónde vive</h2>
<ul>
<li><b>Cloudflare R2</b> guarda los archivos. Descargar desde R2 no cuesta nada, y eso importa para un juego de 2 GB.</li>
<li>Tres encabezados de respuesta (<code>Cross-Origin-Opener-Policy</code>, <code>Cross-Origin-Embedder-Policy</code>, <code>Cross-Origin-Resource-Policy</code>) activan el aislamiento de origen cruzado, que el navegador exige antes de compartir memoria entre los hilos del juego.</li>
<li>Las páginas y los scripts nunca se guardan en la caché del borde; los datos del juego se guardan un día. Los scripts llevan el número de build en su dirección, así una build nueva nunca se mezcla con una vieja.</li>
</ul>
<h2>Por qué carga rápido</h2>
<ul>
<li><b>Piezas cortadas a las lecturas del juego.</b> Las lecturas que el juego siempre hace se guardan como 473 piezas comprimidas con brotli, cada una exactamente una lectura. El navegador baja la pieza y la descomprime al llegar; cualquier otra lectura es un rango de bytes normal.</li>
<li><b>Los archivos chicos llegan completos.</b> Un archivo de hasta 8 MB se baja en una sola petición en su primera lectura y se guarda, así sus lecturas siguientes no cuestan un viaje.</li>
<li><b>Precarga.</b> Una lista de lo que el juego abre camino al menú y a la primera carrera deja que hilos auxiliares bajen esos archivos antes de que el juego los pida.</li>
</ul>
<p>El cargador es <a href="REPO/blob/main/host/files.c">host/files.c</a> y las piezas las corta <a href="REPO/blob/main/tools/data_chunks.py">tools/data_chunks.py</a>. Para ver el resultado, <a href="/">abre el juego</a>.</p>
""")),

    # Sources: AGENTS.md (agents choose the method, evidence rule REA + second tool, UNKNOWN, plan.json rows with state + evidence,
    # commit after every step, headless muted Chrome checks, tools/webcheck.mjs); ~/.codex/AGENTS.md (Claude, Codex `cdx`, OpenCode +
    # DeepSeek `bec`); difftest as the judge (tools/recomp/difftest.py); TRAP and missing-method stops (lift.py, host/d3d9.c); REA MCP.
    dict(key="agents", img="olympic-city-world.webp", dev=True,
         slug=dict(en="reverse-engineering-a-game-with-ai-agents", es="ingenieria-inversa-de-un-juego-con-agentes-de-ia"),
         title=dict(en="Reverse engineering a game with AI agents: the rules that keep it exact", es="Ingeniería inversa de un juego con agentes de IA: las reglas que lo mantienen exacto"),
         desc=dict(en="On NFSU.cc, Claude, Codex and OpenCode agents read Speed.exe, write patches and run tests. These are the checks that stop them from guessing.",
                   es="En NFSU.cc, agentes de Claude, Codex y OpenCode leen Speed.exe, escriben parches y corren pruebas. Estos son los controles que les impiden adivinar."),
         alt=dict(en="Olympic City in the browser version of the game", es="Olympic City en la versión de navegador del juego"),
         cap=dict(en="One person decides what to build and judges every result by playing it.", es="Una persona decide qué construir y juzga cada resultado jugándolo."),
         lead=dict(en="One person directs the project; AI coding agents do most of the reading, writing and testing. That works only because a wrong guess cannot survive the checks below.",
                   es="Una persona dirige el proyecto; agentes de IA para programar hacen la mayor parte de la lectura, la escritura y las pruebas. Funciona solo porque una suposición equivocada no sobrevive a los controles de abajo."),
         body=dict(en="""
<h2>Who does what</h2>
<ul>
<li><b>The owner</b> chooses the direction, plays every build and says yes or no.</li>
<li><b>Claude</b> (Anthropic's Claude Code) plans, reads the binary and writes most of the translator and the host.</li>
<li><b>Codex</b> (OpenAI) takes whole slices in parallel: a subsystem, a tool, a test.</li>
<li><b>OpenCode with DeepSeek</b> handles cheap, wide jobs: search the decompiled code, fill a census table, run a batch.</li>
</ul>
<h2>The risk: a confident guess</h2>
<p>A language model can write a plausible offset or a plausible file format that is simply wrong, and a game built on wrong values fails far away from the mistake. These checks exist to stop that:</p>
<ul>
<li><b>Proof or UNKNOWN.</b> Every value, format or patch names what proves it: an address read with REA (a reverse engineering server agents use over MCP) plus a second tool such as Ghidra or Hopper. Unproven means UNKNOWN, and nothing is built on it. More in <a href="[[retools]]">reading the binary</a>.</li>
<li><b>A machine judge.</b> The translator's output is compared bit for bit with a reference x86 CPU. An agent cannot argue with a mismatch. See <a href="[[recomp]]">static recompilation</a>.</li>
<li><b>Loud failures.</b> A missing instruction or a missing DirectX method stops the game with its name, so a gap shows the first time it runs.</li>
<li><b>Real runs.</b> A change is checked in a headless, muted Chrome that boots the real game and takes screenshots, and the owner judges by playing.</li>
<li><b>One state file.</b> A plan file lists every step with its state and its evidence. Every session starts from it, not from memory.</li>
</ul>
<p>The code is public on <a href="REPO">GitHub</a>.</p>
""", es="""
<h2>Quién hace qué</h2>
<ul>
<li><b>El dueño</b> elige la dirección, juega cada build y dice sí o no.</li>
<li><b>Claude</b> (Claude Code de Anthropic) planea, lee el binario y escribe la mayor parte del traductor y del host.</li>
<li><b>Codex</b> (OpenAI) toma tramos completos en paralelo: un subsistema, una herramienta, una prueba.</li>
<li><b>OpenCode con DeepSeek</b> se encarga de trabajos baratos y anchos: buscar en el código descompilado, llenar una tabla del censo, correr un lote.</li>
</ul>
<h2>El riesgo: una suposición segura de sí misma</h2>
<p>Un modelo de lenguaje puede escribir un offset creíble o un formato de archivo creíble que simplemente está mal, y un juego construido sobre valores equivocados falla lejos del error. Estos controles existen para frenarlo:</p>
<ul>
<li><b>Prueba o UNKNOWN.</b> Cada valor, formato o parche nombra lo que lo prueba: una dirección leída con REA (un servidor de ingeniería inversa que los agentes usan por MCP) más una segunda herramienta como Ghidra o Hopper. Sin prueba es UNKNOWN, y nada se construye encima. Más en <a href="[[retools]]">leer el binario</a>.</li>
<li><b>Un juez de máquina.</b> La salida del traductor se compara bit a bit con un CPU x86 de referencia. Un agente no puede discutir con una diferencia. Ver <a href="[[recomp]]">recompilación estática</a>.</li>
<li><b>Fallas ruidosas.</b> Una instrucción o un método de DirectX que falta detiene el juego con su nombre, así un hueco aparece la primera vez que corre.</li>
<li><b>Corridas reales.</b> Un cambio se revisa en un Chrome sin ventana y en silencio que arranca el juego real y toma capturas, y el dueño juzga jugando.</li>
<li><b>Un solo archivo de estado.</b> Un archivo de plan lista cada paso con su estado y su evidencia. Cada sesión empieza desde ahí, no desde la memoria.</li>
</ul>
<p>El código es público en <a href="REPO">GitHub</a>.</p>
""")),
]

for a in DEV:
    for lang in a["body"]:
        a["body"][lang] = a["body"][lang].replace('href="REPO', 'href="' + REPO)
