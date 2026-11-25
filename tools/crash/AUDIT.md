# Auditoria forense de telemetria nfsu.cc (2026-11-25)

Datos: bucket privado R2 `nfsu-crash` (rclone). Dump crudo: `tools/crash/dump/2026-11-25/`
(`crash.jsonl` 400 reportes, `funnel.jsonl` 864 beacons, cada linea con su dia UTC).

Build vivo: `af14b300fc`. Builds anteriores: `b7dd88e9bf`, `233cad7d29`, `a32b59f504`, ...
RN_V es un hash de contenido (tools/build_public.py:18-26), no un commit: no mapea 1:1 a git.

VENTANAS DE DATOS DISTINTAS: el beacon funnel solo existe desde 2026-11-25 (commit `653dc84`): la conversión
y los load_ms son de UN dia. Los reportes crash van del 2026-11-21 al 2026-11-25. No mezclar.

## 1. Linea de tiempo por dia (UTC)

| dia | beacons funnel | llegan a run | se detienen | conv | reportes crash | crashes build vivo |
|---|---|---|---|---|---|---|
| 2026-11-21 | 0 | 0 | 0 | 0% | 3 | 0 |
| 2026-11-22 | 0 | 0 | 0 | 0% | 12 | 0 |
| 2026-11-23 | 0 | 0 | 0 | 0% | 12 | 0 |
| 2026-11-24 | 0 | 0 | 0 | 0% | 229 | 0 |
| 2026-11-25 | 864 | 776 | 88 | 90% | 144 | 92 |

## 2. Funnel: conversion y carga

| OS | run | stop | conv | load p50 | p90 |
|---|---|---|---|---|---|
| Windows | 391 | 28 | 93% | 9769ms | 40047ms |
| Android | 230 | 30 | 88% | 9162ms | 33288ms |
| iOS | 93 | 14 | 87% | 5537ms | 21962ms |
| macOS | 36 | 8 | 82% | 7533ms | 24417ms |
| Linux | 14 | 2 | 88% | 7675ms | 18150ms |
| ChromeOS | 12 | 3 | 80% | 10997ms | 40257ms |
| Other | 0 | 3 | 0% | 0ms | 0ms |

Total: 776 runs / 864 sesiones = 90% conversion.
Paises top: IN 144, LK 92, US 40, DE 37, RU 30, EG 29, UA 22, PK 22, GB 20, DZ 20, PL 18, PA 17

Carga del WASM: frio p50 1967ms p90 14023ms; caliente (cache V8) p50 624ms. El cache de codigo ya paga (commit 653dc84).

## 3. Taxonomia de crashes (cada clase con su evidencia)

| clase | total | en build vivo | navegador tipico |
|---|---|---|---|
| A iframes que bloquean RN_B | 100 | 0 | Chrome |
| B sin SharedArrayBuffer (COOP/COEP) | 64 | 32 | Chrome |
| C memoria WASM agotada | 59 | 21 | Android Chrome |
| D GPU no soportada / API WebGL falla | 50 | 13 | Chrome |
| K salida del guest reportada como crash | 43 | 0 | Chrome |
| F red corta al bajar el WASM | 30 | 7 | Android Chrome |
| E GPU perdida (device removed) | 20 | 7 | Chrome |
| I Script error opaco (iOS Safari enmascara) | 12 | 7 | iOS Safari |
| M otros unicos | 8 | 0 | Chrome |
| J sandbox frame | 5 | 0 | iOS Safari |
| L audio | 4 | 0 | iOS Safari |
| G extension Chrome toca window.open | 4 | 4 | Chrome |
| H race boot.js | 1 | 1 | Chrome |

### Detalle por clase

**A iframes que bloquean RN_B (100 total, 0 en build vivo)**
Todos del build `b7dd88e9bf`. La linea 146 de web/index.html leia `ab.contentWindow.RN_B.ready` sin guard y un iframe (embed de terceros) cruzado tiraba SecurityError en el primer frame (p50 0.07s). FIXED en commit `ab2f271` (try/catch, catch = listo). Cero ocurrencias en el build vivo.

**B sin SharedArrayBuffer (COOP/COEP) (64 total, 32 en build vivo)**
`crossOriginIsolated false` al arrancar (p50 0.00s). En el build vivo: 7x Chrome 158 Windows, 4x macOS, 3x ChromeOS de escritorio SIN aislamiento (los headers COOP/COEP si llegan: verificado con curl hoy), mas WebViews Android (`; wv` en UA: LineageOS Jelly, PS4). INFERENCE: los de escritorio son la pagina embebida en un iframe ajeno (COOP se rompe dentro de un frame) o un proxy ISP que corta headers (el patron de paises es Africa/MEN/AAsia). Hay que diagnosticarlo en el cliente, no en el servidor.

**C memoria WASM agotada (59 total, 21 en build vivo)**
`WebAssembly.Memory(): could not allocate memory` (p50 0.58s, uno a los 7147s de juego). `deviceMemory` mediana 2 GB, pantallas cortas (684x276, 840x331: telefonos en landscape). Paises: DZ 13, EG 6, IN 6, GR 5, KZ 5. speed_lite ya baja el budget a 448 MB (commit 511830f) pero no alcanza en telefonos de 2 GB. INFERENCE: parte del crecido largo-plazo es nuestro propio crecimiento de memoria en sesiones largas.

**D GPU no soportada / API WebGL falla (50 total, 13 en build vivo)**
Mezcla: 20x Chrome 109 (Win7, sin WebGPU y con WebGL2 caido o bloqueado), iOS 17.7/26 sin WebGL2 util, 3x Safari `samplerParameteri` tipo equivocado (web/gpu.js), 5x `createRenderPipeline` falla, 1x `beginRenderPass` undefined (build vivo). p50 0.01s: muere en el gate, no en el juego.

**K salida del guest reportada como crash (43 total, 0 en build vivo)**
41x `ExitProcess(0)` de build 233cad7d29: el jugador SALIO del menu de pausa y el beacon viejo lo contaba como crash. boot.js ya lo filtra (`if (!/: ExitProcess\(0\)/) crashSend(s)`). Cero en el build vivo. No era un crash del juego.

**F red corta al bajar el WASM (30 total, 7 en build vivo)**
Descarga del WASM cortada (p50 8s). Egipto/Turquia/Irak/China: redes lentas o filtradas. 921e827 ya puso reintentos; quedan 5 en el build vivo.

**E GPU perdida (device removed) (20 total, 7 en build vivo)**
Device removed real: D3D12 `GetDeviceRemovedReason` en Windows y `Instance no longer exists` (WebGPU). p50 60s: pasa DURANTE el juego. Drivers/GPU, no codigo. Hay que mirar si el host sobrecarga la GPU en tier auto.

**I Script error opaco (iOS Safari enmascara) (12 total, 7 en build vivo)**
Safari (iOS 18.7 mayormente) enmascara el detalle del error: 'Script error. at :0', stack `webkit-masked-url://hidden/` o '[object ErrorEvent]'. 6 en el build vivo, a los 0.10s justo despues de `wasm: speed_lite (448 MB)`. UNKNOWN el contenido; actuar requiere filename/lineno en el beacon (seccion 6).

**M otros unicos (8 total, 0 en build vivo)**
Caso unico, ver dump crudo.

**J sandbox frame (5 total, 0 en build vivo)**
5x `Sandbox access violation` (build b7dd88e9bf): la pagina embebida en un frame con sandbox. Ya no aparece.

**L audio (4 total, 0 en build vivo)**
4x audio (InvalidStateError al arrancar el audio device), p50 112s. audio.js ya reintentado en 921e827.

**G extension Chrome toca window.open (4 total, 4 en build vivo)**
`chrome-extension://bkkbcggnhapdmkeljlodobbkopceiche` inyecta y asigna window.open: rompe. NO es nuestro codigo. Accion: solo mejorar el mensaje.

**H race boot.js (1 total, 1 en build vivo)**
1 caso: race de orden de scripts en boot.js (`startGpu` referenciado antes de definirse). Unico.

## 4. Lo que YA arreglamos (con commit)

- `ab2f271` guard try/catch en la lectura RN_B del iframe cortina (clase A, 100 crashes).
- `921e827` hardening de prod: bgra fallback, waitAsync, reintentos de red, audio, storage y filtro de ExitProcess (clases F, L, K).
- `511830f` OOM de 50 min + speed_lite WASM de 448 MB (clase C parcial).
- `9776828` retiró el tag RUM duplicado; los headers COOP/COEP/CORP viven como reglas del dominio en Cloudflare (verificado hoy con curl).
- cache V8 del WASM y beacons funnel (`653dc84`): la carga caliente bajo a 585 ms p50.

## 5. Lo que FALTA (ordenado por impacto real, build vivo)

1. **Clase B, 24-31 sesiones: diagnostico del cliente.** El servidor hace su parte (headers ok). En boot.js, cuando `crossOriginIsolated` sea false, reportar COMO se abrio la sesion: `window.top !== window` (iframe ajeno), headers de una respuesta fetch('/') al mismo origen, y `navigator.userAgent` ya esta. Una linea de log + campo en el beacon resuelve el UNKNOWN de si es iframe o proxy ISP.
2. **Clase C, 21 sesiones: presupuesto por dispositivo.** deviceMemory 2 GB no llega ni con 448 MB. Opciones: no-boot con mensaje claro y accion (cerrar apps, otro navegador) o budget dinamico ~ deviceMemory*0.35. Medir primero: el beacon ya trae `mem`.
3. **Clase I, 6 sesiones: visibility del error iOS.** window.onerror con filename/lineno en el beacon; hoy Safari manda 'Script error. at :0' y no se puede actuar.
4. **Clase D: gate Chrome 109.** 20 sesiones viejas de Win7 caen en 'no tiene WebGPU ni WebGL 2': mejor mensaje ('actualiza Chrome' / navegador soportado) en vez de stop frio.
5. **Clase E: medicion, no codigo.** 7 sesiones perdieron la GPU a los ~60s: capturar `perf`/frame windows del rnStats en el beacon para saber si va precedido de pico de frames.
6. **Clase G (extension Chrome):** detectar el error con extension:// en el stack y clasificarlo como ruido de entorno.

## 6. Huecos del propio sistema de telemetria (re-inventar aqui, no en el juego)

- **Sin timestamp en el payload**: el worker solo lo usa en el key R2. Agregar `ts` al json (worker.js) hace el dump autocontenido y el dedup posible.
- **`tier` siempre vacio**: el beacon manda `tier: window.RN_TIER` pero nadie lo asigna (el log dice 'tier: ultralite (auto...)'). Perdemos el desglose por tier en el funnel.
- **Sin session id anonimo**: no se puede juntar el beacon funnel con un crash posterior de la misma sesion; hoy son dos poblaciones.
- **`Script error` opaco**: sin filename/lineno (punto 5.3).
- **Sin retencion ni alerta**: el bucket crece crudo (849 beacons/5 dias); no hay agregado diario. read.sh/read_funnel.sh solo ven un dia.
- **RUM de Cloudflare: NO esta midiendo.** Se quito el tag manual (9776828) asumiendo auto-inyeccion, pero la pagina viva no trae beacon de cloudflareinsights (curl hoy). Falta activarlo en el dashboard o restaurar el tag: sin RUM no hay vistas ni bounce, solo sesiones que llegan a run/stop.
- **Body cap 32 KB** (worker.js): ok por ahora; el tail de 40 lineas ya roza en sesiones largas.

## 7. Metodologia y limites
- Fuente: rclone cat por dia a /tmp/nfsu-audit/, un jsonl por tipo y dia; todo con dia UTC explícito.
- Duplicados posibles entre descargas parciales y completas: las cifras de este informe salen SOLO de los per-day (sin doble conteo).
- Lo que el beacon NO ve: visita que abandona antes del primer beacon, pings de red tras cerrar la pestana, y paises sin GeoIP de Cloudflare.
- UNKNOWN marcado donde el dato no alcanza (origen de la clase B, contenido de la clase I).
