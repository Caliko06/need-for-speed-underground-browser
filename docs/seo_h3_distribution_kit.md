# H3 Brand Mentions, AEO & Distribution Kit (`nfsu.cc`)

Actionable launch kit for building branded web mentions across Tier 3 (YouTube), Tier 2 (Reddit & Hacker News), and Tier 1 (gaming/tech press & outdated "how to play" guides). All technical metrics below are verified against `CHANGELOG.md` and `web/reverse-engineering/index.html`.

---

## A. YouTube Launch Video Blueprint (Tier 3)

### 1. SEO-Optimized Titles

**English options:**
- `I Statically Recompiled Need for Speed Underground (2003) to Play Free in Your Browser (nfsu.cc)`
- `Play Need for Speed Underground Online in Any Browser (No Emulator, 60 FPS, Full Soundtrack)`
- `Need for Speed Underground 2003 Running in WebGPU + WebAssembly (PC & Mobile) | nfsu.cc`

**Spanish options:**
- `Ya Puedes Jugar Need for Speed Underground (2003) Gratis en el Navegador (PC y Celular) | nfsu.cc`
- `Need for Speed Underground Recompilado a WebAssembly: 60 FPS y Soundtrack Completo en nfsu.cc`

### 2. Video Description (Ready to Copy)

```text
Play Need for Speed Underground (2003) directly in your browser at https://nfsu.cc/ (no install, no emulator, free on PC, Mac, Android, iPhone, and iPad).

Open-source repository & Reverse Engineering Field Guide:
- Live game: https://nfsu.cc/
- Reverse Engineering & Static Recompilation Guide: https://nfsu.cc/reverse-engineering/index.html
- Engineering Devlog: https://nfsu.cc/devlog/index.html
- Source code (GitHub): https://github.com/Caliko06/need-for-speed-underground-browser

What is running under the hood:
The original 2003 Windows x86 executable (Speed.exe) was statically recompiled into C and compiled to WebAssembly (7.04 MB Brotli) with a custom Win32 / DirectX 9 host targeting WebGPU (with automatic WebGL 2 fallback) and Web Audio. It is not an emulator: 13,766 x86 functions run compiled in-tab with the full 2003 soundtrack, career mode ("Go Underground"), widescreen support, Original 2003 + Remaster toggle (F4), keyboard, gamepad, and mobile touch controls.

Timestamps:
0:00 Hook: 2003 Speed.exe running live in a browser tab
0:12 Live Olympic City race (WebGPU, 60 FPS, zero download)
0:28 Full 2003 soundtrack, Remaster toggle (F4), and gamepad support
0:42 Mobile browser demo (448 MB lite WASM + touch controls)
0:52 How to play right now at https://nfsu.cc/
```

### 3. Tags

`need for speed underground browser, play need for speed underground online, nfsu.cc, need for speed underground 2003 pc windows 11, need for speed underground mac, webassembly game port, webgpu racing game, static recompilation, nfsu1 web, speed.exe wasm, play nfsu1 mobile, retro racing games in browser`

### 4. Pinned Comment

```text
Play right here in your browser (PC, Mac, or phone): https://nfsu.cc/
Press F4 on desktop to switch between Original 2003 visuals and Remaster mode, and plug in any Xbox/PlayStation controller or use keyboard/touch.
If you want to see how all 13,766 x86 functions were lifted to WebAssembly + WebGPU, the open-source repo and field guide are here: https://nfsu.cc/reverse-engineering/index.html
Drop what browser/device you tested it on and your FPS below!
```

### 5. 45-60s Demo Script

- **0:00-0:10 (Hook):** Show a normal browser address bar typing `https://nfsu.cc/` and hitting Enter. Voiceover: *"Everyone knows Need for Speed Underground isn't sold anywhere, and getting the 2003 disc working on Windows 11 or Mac is a pain. So I statically recompiled the original exe to run straight inside a browser tab."*
- **0:10-0:28 (Live Browser Gameplay):** Cut straight to an Olympic City night race in Chrome/Edge at 60 FPS, drifting a blue Skyline through neon reflections. Voiceover: *"No emulator, no VirtualBox, no SafeDisc No-CD hacks. All 13,766 functions from the 2003 PC executable are lifted to WebAssembly and DirectX 9 translates directly to WebGPU."*
- **0:28-0:44 (Full Soundtrack / 60 FPS / Mobile):** Quick split showing the launcher, pressing `F4` to toggle Original 2003 vs. Remaster bloom, audio waveform / full soundtrack playing, then cut to an iPhone/Android screen steering with touch controls. Voiceover: *"You get the full Go Underground career, every single 2003 soundtrack song, plug-and-play controller support, and a 448 MB mobile build with touch controls."*
- **0:44-0:55 (CTA & Link):** End on car select + live URL card (`https://nfsu.cc/`). Voiceover: *"Saves live locally in your browser. Open nfsu.cc, hit Play, and race."*

---

## B. Community Posts Ready to Copy (Tier 2)

### 1. `r/needforspeed` (Nostalgia + Practical "No Windows 11/SafeDisc Hassle" Angle)

**Title:** `You can now play Need for Speed Underground (2003) directly in your browser at nfsu.cc (PC, Mac, and mobile, full soundtrack, controller support)`

**Body:**
```text
If you've ever tried to replay NFS Underground 1 on Windows 11 or a Mac, you know the usual drill: hunting down ISOs, bypassing SafeDisc DRM, enabling DirectPlay, and dropping in widescreen fixes.

I've been working on an open-source static recompilation of the 2003 PC version (`Speed.exe`) to WebAssembly + WebGPU so you can just open a tab and drive: https://nfsu.cc/

What works right now:
- Full game: Quick Race, Go Underground career, garage/tuning, and local browser saves
- Full 2003 soundtrack (every song included)
- Keyboard, plug-and-play gamepads, and touch controls on Android/iOS (uses a lighter 448 MB WASM build on phones)
- Original 2003 look or Remaster mode with bloom/edge smoothing (press F4 on desktop to switch)
- Runs on Windows, macOS (Apple Silicon & Intel), Linux, and phones via WebGPU with automatic WebGL 2 fallback

Unlike an emulator, this lifts the 13,766 functions from the original x86 binary to C/WebAssembly ahead of time, so the handling, physics, and rivals behave like the 2003 PC release.

Repo for anyone curious: https://github.com/Caliko06/need-for-speed-underground-browser

Would love feedback on controller mapping and frame pacing on your setup!
```

### 2. `r/webgames` (Zero-Install Instant Play + Mobile Support Angle)

**Title:** `Need for Speed Underground (2003) running natively in the browser via WebAssembly + WebGPU (no install, keyboard/gamepad/mobile)`

**Body:**
```text
Hey r/webgames, sharing a browser port I built for the 2003 street-racing classic Need for Speed Underground: https://nfsu.cc/

Instead of running a heavy PC emulator in JS, the original 2003 Windows binary was statically recompiled ahead of time into a 7.04 MB (Brotli) WebAssembly module, with DirectX 9 mapped to WebGPU (and automatic WebGL 2 fallback).

Features for browser players:
- Starts in a few seconds (2.27 s cold boot to live 3D WebGPU frames on desktop)
- Full career mode ("Go Underground"), Quick Race, car customization, and the full 2003 soundtrack
- Works with keyboard, USB/Bluetooth gamepads, and mobile touch controls
- Saves persist locally in your browser
- Built-in adaptive quality controller that scales resolution/effects dynamically if your device drops frames

Source code is open here: https://github.com/Caliko06/need-for-speed-underground-browser

Curious how it feels on your browser/GPU!
```

### 3. `r/WebAssembly` (Compiler Passes, V8 Code Cache, & Graphics Pipeline Angle)

**Title:** `Statically recompiling Need for Speed Underground (13,766 x86 functions) to WebAssembly + WebGPU (7.04 MB Brotli, 448 MB mobile heap)`

**Body:**
```text
We just shipped a production WebAssembly + WebGPU port of Need for Speed Underground (2003, 32-bit x86 Windows PE `Speed.exe`, 3.18 MB) live at https://nfsu.cc/ and documented the full toolchain at https://nfsu.cc/reverse-engineering/index.html.

Key numbers and engineering lessons from lifting and shipping a real 2003 game in WASM:
- **Static recompiler (`tools/recomp/`):** Lifted 13,766 x86 functions to C -> Clang/LLVM WASM (7.04 MB Brotli-11, down 39.9% from compiler passes).
- **Dead EFLAGS pruning (`FlagABI`) + bounds coalescing (`CHK_IMG`, `CHK_SP`):** Inter-procedural flag liveness cut `par(` by 82.1%, `af=` by 80.7%, and `c->cf=cf` by 69.4%. Coalescing straight-line `esp` checks cut `CHK_SP` from 619,768 to 385,228 (-37.8%). Every pass is verified per-function via differential testing (`5,404/5,407` functions passing strict x87 vs. IEEE-754 fast mode).
- **V8 WASM code cache trap:** Wrapping `fetch()` in a `TransformStream` or `new Response()` stripped URL identity and broke V8's disk code cache. Switching directly to `fetch()` -> `WebAssembly.instantiateStreaming()` dropped desktop `atRunMem` from 58.08 MiB to 13.22 MiB (-77.2%).
- **D3D9 -> WebGPU/WebGL 2 (`15,035` LOC host):** Native BC1/2/3 (`S3TC`) texture passthrough saves 4x-8x VRAM; compact 256 B dynamic UBO slicing reduced per-frame uniform uploads from ~9.6 MB to 1.32 MB (-86.2%).
- **448 MB mobile budget & 50-min OOM fix:** Freeing CPU-side `SmoothEnt` vertex/index buffers after GPU upload fixed linear heap growth, and gating a 20 MB 3D menu curtain off mobile dropped first `Present()` from 107.08 s to 76.62 s and mobile JS heap by 79.3%.

Repo: https://github.com/Caliko06/need-for-speed-underground-browser
Devlogs: https://nfsu.cc/devlog/index.html
```

### 4. `Show HN` (Hacker News: Minimalist, Deep Technical Rigor)

**Title:** `Show HN: Need for Speed Underground (2003) statically recompiled to WebAssembly/WebGPU`

**Body / First Comment:**
```text
Hi HN,

I statically recompiled Need for Speed Underground (2003, x86 Windows PE) into C and compiled it to WebAssembly + WebGPU so it runs directly in a browser tab: https://nfsu.cc/

Code and reverse engineering field guide:
- GitHub: https://github.com/Caliko06/need-for-speed-underground-browser
- Field Guide & Symbol Census: https://nfsu.cc/reverse-engineering/index.html
- Devlogs: https://nfsu.cc/devlog/index.html

How it works:
1. A Python static recompiler (`tools/recomp/`, 3,334 LOC) lifts 13,766 x86 functions from `Speed.exe` (3.18 MB) into C, compiled to a 7.04 MB Brotli-compressed WASM binary.
2. Three optimization passes cut WASM size by 39.9%: inter-procedural EFLAGS liveness pruning (-82.1% parity flag writes), static image bounds bypass (`CHK_IMG`) + straight-line stack check coalescing (`CHK_SP`, -37.8% checks), and native IEEE-754 floating point checked per-function via differential testing (`5,404/5,407` functions passing against strict x87).
3. A 15,035-LOC C/JS host translates Win32, Direct3D 9, DirectInput, and DirectSound to WebGPU (with WebGL 2 fallback), Gamepad/Touch, and Web Audio. DXT1/3/5 textures upload natively via `texture-compression-bc`, and 256 B dynamic UBO slicing cut uniform uploads by 86.2% (to 1.32 MB/frame).
4. Passing raw `fetch()` straight to `WebAssembly.instantiateStreaming()` restored V8's WASM code cache (-77.2% JS memory at runtime), and a 448 MB lite WASM build lets it boot on iOS/Android Safari and Chrome.

Happy to answer questions about x86-to-C lifting, D3D9-to-WebGPU edge cases, or differential testing!
```

### 5. Active Reddit Threads for Helpful Replies (Verified Live URLs)

When dropping a brief, helpful reply in existing threads asking how to play NFSU1/NFSU2 on modern systems, keep it strictly helpful (answer their OS issue first, then mention `nfsu.cc` as a zero-install option):
- `https://www.reddit.com/r/needforspeed/comments/1p2aybr/nfs_underground_is_still_alive_in_2025_small/` (r/needforspeed thread on NFS Underground in 2025)
- `https://www.reddit.com/r/needforspeed/comments/1jvzpne/the_best_way_to_play_need_for_speed_underground/` (r/needforspeed thread: "The best way to play Need for Speed Underground")
- `https://www.reddit.com/r/needforspeed/comments/191su6w/run_need_for_speed_underground_on_windows_781011/` (r/needforspeed Windows 7/8/10/11 guide)
- `https://www.reddit.com/r/NFSU2/comments/1xepz3o/need_for_speed_underground_is_playable_in_a/` (r/NFSU2 thread already mentioning NFSU in browser)
- `https://www.reddit.com/r/NFSU2/comments/1xfw8lc/best_way_to_play_in_2026/` (r/NFSU2 "Best way to play in 2026")
- `https://www.reddit.com/r/macgaming/comments/1xeg47m/i_made_need_for_speed_underground_2_run_natively/` (r/macgaming native Apple Silicon thread)

---

## C. Outreach Target Table (Tier 1 Press & Outdated Guides)

### Group 1: Press & Tech Sites That Already Covered `nfsu2.xyz` / Browser Ports (EN & ES)

| Site | Real URL & Title | Why Relevant | 4-Line Update / Follow-Up Pitch |
|---|---|---|---|
| **TechPowerUp** | [Need for Speed Underground 2 Gets a Free Browser Port With Multiplayer Free Roam](https://www.techpowerup.com/354422/need-for-speed-underground-2-gets-a-free-browser-port-with-multiplayer-free-roam) | Major PC hardware/gaming news outlet that covered `nfsu2.xyz` static recompilation in browser. | Hi TechPowerUp team, since your readers loved the `nfsu2.xyz` static recompilation story, the original 2003 *Need for Speed: Underground* is now also live in browsers at `https://nfsu.cc/`.<br>It statically recompiles 13,766 x86 functions from `Speed.exe` to WebAssembly + WebGPU (with WebGL 2 fallback), keeping the full 2003 soundtrack and career.<br>It also ships a 448 MB mobile lite build with touch controls plus an F4 Remaster toggle.<br>Open-source repo and technical breakdown are live at `https://nfsu.cc/reverse-engineering/index.html` if you'd like to cover the prequel. |
| **Tech Bytes** | [Need for Speed Underground 2 online in the browser](https://techbytes.app/posts/need-for-speed-underground-2-online-in-the-browser/) | Developer/tech news blog that specifically explained the `NFSU2Recomp` WASM + WebGPU stack. | Hi Tech Bytes, loved your write-up on the WASM/WebGPU browser port of NFSU2.<br>We just launched the same static-recompilation treatment for the original 2003 *Need for Speed: Underground* at `https://nfsu.cc/` (open source on GitHub).<br>We documented all 13,766 lifted x86 functions, EFLAGS pruning, and V8 WASM code-cache numbers in a public field guide (`https://nfsu.cc/reverse-engineering/index.html`).<br>Would make a great follow-up or "Update" note for readers wanting to play Underground 1 in-tab too! |
| **Softonic (EN)** | [Need for Speed Underground 2 launches in browsers: fan project revives online multiplayer](https://en.softonic.com/articles/need-for-speed-underground-2-launches-in-browsers-fan-project-revives-online-multiplayer) | High-authority software/gaming portal ranking for browser NFS queries. | Hi Softonic editorial team, quick tip following your coverage of the Underground 2 browser port.<br>The original *Need for Speed: Underground* (2003) now has a full open-source WebAssembly + WebGPU browser port live at `https://nfsu.cc/`.<br>It runs directly on PC, Mac, Android, and iOS with zero install, keyboard/gamepad/touch support, and the complete 2003 soundtrack.<br>Worth a quick update link or companion news post for fans looking for the first game! |
| **GameSeal News** | [Classic 2000s games playable in browser (NFSU2)](https://gameseal.com/news-and-rumors/classic-2000s-games-playable-browser-nfsu2) | Gaming news listicle covering 2000s classics playable in the browser. | Hi GameSeal team, saw your piece on classic 2000s games playable in a browser tab.<br>You can now add the original *Need for Speed: Underground* (2003) via `https://nfsu.cc/`.<br>It statically recompiles the PC binary to WebAssembly + WebGPU, includes full career mode and every 2003 soundtrack track, and runs on phones too.<br>Happy to share screenshots or technical details if you update the list! |
| **daily.dev** | [Need for Speed Underground 2 online in the browser](https://daily.dev/posts/need-for-speed-underground-2-online-in-the-browser-glptsw2ca) | Developer aggregator thread with strong AEO/LLM crawl weight for dev audiences. | Hi! For devs following the NFSU2 WASM/WebGPU thread, the original 2003 *Need for Speed: Underground* is also open-source and live at `https://nfsu.cc/`.<br>It lifts 13,766 x86 functions to C/WASM (7.04 MB Brotli) with a 15,035-LOC D3D9-to-WebGPU/WebGL 2 host.<br>Full compiler pass benchmarks (`FlagABI`, `CHK_SP`, V8 `instantiateStreaming` code cache) are at `https://nfsu.cc/reverse-engineering/index.html`.<br>Check it out and share how WebGPU runs on your machine! |
| **HardZone (ES)** | [Vuelve Need for Speed Underground 2, pero en tu navegador, gratis y a 120 FPS](https://hardzone.es/noticias/juegos/need-for-speed-underground-2-gratis-navegador/) | Tier 1 Spanish PC hardware/gaming outlet (Grupo ADSLZone) covering the browser port. | Hola equipo de HardZone, tras vuestra noticia sobre NFS Underground 2 en navegador, ya está disponible también el *Need for Speed: Underground* original (2003) gratis en `https://nfsu.cc/`.<br>Está recompilado estáticamente de x86 a WebAssembly + WebGPU (con fallback automático a WebGL 2), incluye la banda sonora completa, modo historia y soporte para mando y móvil.<br>El código es abierto (`github.com/Caliko06/need-for-speed-underground-browser`) y detallamos las optimizaciones de WebGPU/WASM en `https://nfsu.cc/reverse-engineering/index.html`.<br>Por si os encaja mencionarlo como actualización o nueva noticia para los fans del clásico! |
| **Tarreo (ES)** | [Juega gratis Need for Speed Underground 2 sin instalar nada, en el navegador o el celular y con carreras en línea](https://www.tarreo.com/noticia/juega-gratis-need-for-speed-underground-2-navegador-celular-online/) | High-traffic LATAM gaming outlet covering both browser and mobile play. | Hola equipo de Tarreo, vimos su nota sobre jugar NFS Underground 2 desde el navegador o celular.<br>Les comparto que el primer *Need for Speed: Underground* (2003) también se puede jugar gratis y sin instalar nada en `https://nfsu.cc/`.<br>Funciona en PC, Mac, Android y iPhone (con controles táctiles o mando, y toda la música original de 2003) gracias a WebAssembly y WebGPU.<br>Si actualizan la nota o cubren la primera entrega, aquí tienen el enlace directo y la guía técnica en `https://nfsu.cc/reverse-engineering/index.html`. |
| **Pisapapeles (ES)** | [Ya puedes jugar gratis a Need for Speed Underground 2 desde el navegador](https://pisapapeles.net/ya-puedes-jugar-gratis-a-need-for-speed-underground-2-desde-el-navegador-con-multijugador-en-linea/) | LATAM tech site covering browser-based NFSU2. | Hola equipo de Pisapapeles, excelente nota sobre NFS Underground 2 en navegador.<br>Para quienes buscan también la primera entrega de 2003, ya está en línea `https://nfsu.cc/`, un port de código abierto basado en recompilación estática a WebAssembly + WebGPU.<br>Corre directo en navegador de escritorio y móviles (build ligero de 448 MB) manteniendo el soundtrack completo y modo carrera.<br>Les dejo el dato por si quieren añadirlo como actualización al artículo! |
| **ClicClick (ES)** | [NFS Underground 2 en el navegador y Revived: cómo jugar](https://clicclick.cl/gaming/need-for-speed-underground-2-navegador/) | Spanish "how to play in browser" guide ranking for NFSU browser queries. | Hola! Vi su guía sobre cómo jugar NFS Underground 2 en el navegador.<br>Si quieren añadir una sección o guía paralela para *Need for Speed: Underground* (2003), ya corre en `https://nfsu.cc/` sin descargas ni emuladores.<br>Incluye modo carrera completo, toda la música de 2003, selector de calidad (Original o Remaster con F4) y soporte táctil en celulares.<br>Ojalá les sirva para mantener la guía al día! |

### Group 2: Outdated "How to Play NFS Underground / Modern PC / Remakes" Guides (Matt Diggity Update Strategy)

| Site | Real URL & Title | Why Relevant | 4-Line Update Pitch |
|---|---|---|---|
| **Fusion Fix** | [Need for Speed: Underground · Fusion Fix](https://fusionfix.io/games/nfsu/) | Primary community destination for fixing NFSU1 on modern Windows PCs. | Hi Fusion Fix maintainers, users landing on your NFSU1 modern-PC guide often ask about Mac, Linux, or zero-install options.<br>We built an open-source static recompilation of `Speed.exe` (2003) to WebAssembly + WebGPU live at `https://nfsu.cc/` (`github.com/Caliko06/need-for-speed-underground-browser`).<br>It runs directly in Chrome, Edge, Firefox, and Safari with native widescreen, gamepad support, and the full 2003 soundtrack.<br>If you list alternative ways to play on modern OSes/macOS, feel free to reference `nfsu.cc`! |
| **Fusion-Fix.net** | [Need for Speed: Underground Widescreen Fix - download \| 16:9 · 4K](https://fusion-fix.net/nfs-underground-widescreen-fix/) | Ranks for NFSU1 widescreen & modern Windows playability searches. | Hi! Readers grabbing the Widescreen Fix here are usually trying to get the 2003 PC release working on Windows 11 or macOS.<br>Just wanted to share an open-source browser option you could mention in a quick note: `https://nfsu.cc/` runs the statically recompiled 2003 game via WebAssembly + WebGPU.<br>No SafeDisc No-CD patches or Windows compatibility tweaks needed, and it keeps the original physics, career, and full soundtrack.<br>Happy to share any details if you add a "Play in Browser / Mac" tip! |
| **WSGF** | [Need for Speed: Underground \| WSGF](https://www.wsgf.org/dr/need-speed-underground/en) | Classic technical reference for running NFSU1 on modern widescreen displays. | Hello WSGF editors, on the *Need for Speed: Underground* entry it may be worth noting a 2026 preservation update in the modern compatibility notes.<br>An open-source static recompilation (`github.com/Caliko06/need-for-speed-underground-browser`) now runs `Speed.exe` natively in browsers at `https://nfsu.cc/` via WebAssembly + WebGPU.<br>It supports widescreen displays, Original vs. Remaster toggle (`F4`), and gamepad/keyboard input without Win11 SafeDisc workarounds.<br>Sharing in case you'd like to add `https://nfsu.cc/` to the external links/notes! |
| **VidaExtra (ES)** | [Puedes jugar al remake de Need for Speed Underground 2 que siempre deseaste en Unreal Engine 5](https://www.vidaextra.com/conduccion/puedes-jugar-al-remake-need-for-speed-underground-2-que-siempre-deseaste-unreal-engine-5-solo-demo) | Tier 1 Spanish gaming outlet covering fan remakes/demos of NFS Underground. | Hola equipo de VidaExtra, viendo el enorme interés que generan en vuestra web los proyectos fan de *Need for Speed Underground*, os paso un hallazgo diferente: el *Need for Speed: Underground* original de 2003 ya se puede jugar completo en el navegador en `https://nfsu.cc/`.<br>A diferencia de una demo en UE5, es una recompilación estática de código abierto del `Speed.exe` original a WebAssembly y WebGPU (sin emulador).<br>Incluye el modo carrera completo, toda la banda sonora de 2003, modo Remaster con F4 y soporte para móvil y mando.<br>Por si os encaja para un artículo rápido para los nostálgicos del primer Underground! |
| **Vandal (ES)** | [Need for Speed: Underground (Ficha oficial Vandal)](https://vandal.elespanol.com/juegos/ps2/need-for-speed-underground/1963) | Top Spanish authority page ranking for *Need for Speed Underground* queries. | Hola redacción de Vandal, para lectores que consultan la ficha de *Need for Speed: Underground* preguntando cómo jugarlo hoy en PC o Mac al estar descatalogado.<br>Existe ya un proyecto de preservación de código abierto que recompila estáticamente el juego de PC de 2003 a WebAssembly + WebGPU para jugarlo gratis en navegador: `https://nfsu.cc/`.<br>Mantiene el modo historia completo, los coches, el soundtrack original íntegro y funciona también en móviles.<br>Os lo comparto por si queréis cubrirlo en noticias o mencionarlo para la comunidad! |
| **3DJuegos (ES)** | [Need for Speed: Underground (Ficha 3DJuegos)](https://www.3djuegos.com/juegos/need-for-speed-underground/) | Top Spanish gaming portal ranking for NFSU1 searches. | Hola equipo de 3DJuegos, ya que *Need for Speed: Underground* (2003) no se vende en tiendas digitales, muchos jugadores buscan cómo volver a jugarlo sin lidiar con parches en Windows 11.<br>Acaba de publicarse una recompilación estática de código abierto que permite jugar el título completo directamente en cualquier navegador (PC, Mac o móvil) en `https://nfsu.cc/`.<br>Usa WebAssembly y WebGPU con la banda sonora de 2003 completa y guardado local.<br>Si os interesa hacer una noticia sobre preservación clásica en navegador, aquí tenéis el proyecto: `https://nfsu.cc/reverse-engineering/index.html`. |
| **VOGONS** | [Need for Speed Underground Windows setup thread (t=103147)](https://www.vogons.org/viewtopic.php?t=103147) | Deep retro-PC troubleshooting forum for getting 2003 `Speed.exe` running. | Posting a helpful preservation note for anyone hitting SafeDisc/DirectPlay headaches on modern Windows or macOS in this thread:<br>There's now an open-source static recompilation of the 2003 `Speed.exe` running in-browser via WebAssembly + WebGPU at `https://nfsu.cc/`.<br>It lifts all 13,766 x86 functions ahead of time (no CPU emulation), preserves the full 2003 soundtrack, and lets you toggle Original 2003 vs. Remaster with F4.<br>Technical write-up and source are here if anyone wants to inspect the D3D9 wrapper: `https://nfsu.cc/reverse-engineering/index.html`. |
| **NFSU2.org Guides** | [PC installation on Windows - NFSU2](https://nfsu2.org/guides/browser-support/) | Dedicated NFSU guide hub that documents PC installation & browser support. | Hi NFSU2.org maintainers, noticed your guide hub covers browser support and Windows setup.<br>If you also reference the first game, the 2003 *Need for Speed: Underground* is now playable directly in-browser at `https://nfsu.cc/` via open-source static recompilation (WebAssembly + WebGPU/WebGL 2).<br>It runs full career mode, controller/keyboard/touch, and the complete 2003 soundtrack with zero Windows 11 SafeDisc setup.<br>Would be awesome to see `https://nfsu.cc/` listed alongside your browser resources! |

---

## D. Live Press Kit & 7-Day Launch Sequence

Include the live Press Kit link in every outreach email so journalists and YouTubers get verified stats and screenshots in one click:
- **English Press Kit:** `https://nfsu.cc/press/index.html`
- **Kit de Prensa (Español):** `https://nfsu.cc/press/es/index.html`

### 7-Day Rollout (15 min/day)
1. **Day 1 (Tier 3 + Tier 2):** Publish 60s YouTube demo video (Section A) + post on `r/needforspeed` (Section B.1).
2. **Day 2 (Tier 2 Tech):** Post `Show HN` (Section B.4, best at 9-11 AM EST) + `r/WebAssembly` (Section B.3).
3. **Day 3 (Tier 2 Casual + Helpful Replies):** Post on `r/webgames` (Section B.2) + leave helpful replies in the 6 active Reddit threads (Section B.5).
4. **Day 4 (Tier 1 EN Press):** Send 4-line pitches with `https://nfsu.cc/press/index.html` to TechPowerUp, Tech Bytes, Softonic EN, GameSeal, and daily.dev.
5. **Day 5 (Tier 1 ES Press):** Send 4-line pitches with `https://nfsu.cc/press/es/index.html` to HardZone, Tarreo, Pisapapeles, ClicClick, VidaExtra, Vandal, and 3DJuegos.
6. **Day 6 (Outdated Compatibility Hubs):** Send update notes to Fusion Fix, Fusion-Fix.net, WSGF, VOGONS, and NFSU2.org.
7. **Day 7 (Measure):** Check Cloudflare Analytics referrers, Google Search Console impressions, and re-run `search_web` for `"jugar need for speed underground online"` and `"play need for speed underground browser"`.
