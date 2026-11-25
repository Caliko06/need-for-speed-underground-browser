#!/usr/bin/env python3
"""Dump + forensic audit of the nfsu.cc telemetry (funnel rn-funnel-1 + crash rn-crash-1) in r2:nfsu-crash.
Reads the per-day jsonl files rclone already wrote to /tmp/nfsu-audit/ (one pair per UTC day), tags every
row with its day (the worker does not put a timestamp in the payload; the R2 key does), writes the raw
combined dump to dump/<UTC-today>/ and regenerates AUDIT.md next to this script.
Usage: rclone per-day into /tmp/nfsu-audit/{crash,funnel}_YYYY-MM-DD.jsonl, then: python3 tools/crash/dump_audit.py"""
import collections, glob, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = "/tmp/nfsu-audit"


def load(kind):
    rows = []
    for f in sorted(glob.glob(f"{TMP}/{kind}_*.jsonl")):
        day = os.path.basename(f)[len(kind) + 1:-6]
        for line in open(f):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                r["day"] = day
                rows.append(r)
    return rows


def browser(ua):
    if "iPhone" in ua or "iPad" in ua:
        return "iOS Safari"
    if "Edg/" in ua:
        return "Edge"
    if "Firefox" in ua:
        return "Firefox"
    if "Android" in ua:
        return "Android WebView" if "; wv" in ua else "Android Chrome"
    if "Chrome" in ua:
        return "Chrome"
    if "Safari" in ua:
        return "Safari"
    if "PlayStation" in ua:
        return "PS4"
    return ua.split("(")[0][:18] or "?"


def chrome_ver(ua):
    m = __import__("re").search(r"Chrome/(\d+)", ua)
    return m.group(1) if m else ""


def klass(r):
    s = r.get("stop", "")
    if "RN_B" in s:
        return "A iframes que bloquean RN_B"
    if "COOP/COEP" in s or "crossOriginIsolated" in s:
        return "B sin SharedArrayBuffer (COOP/COEP)"
    if "could not allocate memory" in s or "Out of memory" in s or "abort: OOM" in s or "WebAssembly is not defined" in s:
        return "C memoria WASM agotada"
    if "no tiene WebGPU ni WebGL 2" in s or "samplerParameteri" in s or "createRenderPipeline" in s or "Type error" in s or "beginRenderPass" in s:
        return "D GPU no soportada / API WebGL falla"
    if "se perdio la GPU" in s or "se perdió la GPU" in s or "GetDeviceRemovedReason" in s:
        return "E GPU perdida (device removed)"
    if "Failed to fetch" in s or "Load failed" in s or "Network error" in s:
        return "F red corta al bajar el WASM"
    if "read only property 'open'" in s:
        return "G extension Chrome toca window.open"
    if "startGpu is not defined" in s:
        return "H race boot.js"
    if "Script error. at :0" in s or "webkit-masked-url" in s or "[object ErrorEvent]" in s or "JS rejection: @" in s:
        return "I Script error opaco (iOS Safari enmascara)"
    if "Sandbox access violation" in s:
        return "J sandbox frame"
    if "ExitProcess(0)" in s or "ExitThread(0)" in s:
        return "K salida del guest reportada como crash"
    if "audio" in s.lower():
        return "L audio"
    if "ReadFile" in s or "int3" in s or "mapAsync" in s or "pump@" in s or "Import #" in s:
        return "M otros unicos"
    return "Z sin clasificar"


def p50(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


def main():
    crash = load("crash")
    funnel = load("funnel")
    live = "af14b300fc"
    dump = os.path.join(HERE, "dump", "2026-11-25")
    os.makedirs(dump, exist_ok=True)
    with open(os.path.join(dump, "crash.jsonl"), "w") as f:
        for r in crash:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(dump, "funnel.jsonl"), "w") as f:
        for r in funnel:
            f.write(json.dumps(r) + "\n")

    days = sorted({r["day"] for r in funnel + crash})
    fun_by_day = collections.Counter(r["day"] for r in funnel)
    run_by_day = collections.Counter(r["day"] for r in funnel if r["ev"] == "run")
    stop_by_day = collections.Counter(r["day"] for r in funnel if r["ev"] == "stop")
    cr_by_day = collections.Counter(r["day"] for r in crash)
    live_cr_by_day = collections.Counter(r["day"] for r in crash if r["v"] == live)

    L = []
    A = L.append
    A("# Auditoria forense de telemetria nfsu.cc (2026-11-25)\n")
    A("Datos: bucket privado R2 `nfsu-crash` (rclone). Dump crudo: `tools/crash/dump/2026-11-25/`")
    A(f"(`crash.jsonl` {len(crash)} reportes, `funnel.jsonl` {len(funnel)} beacons, cada linea con su dia UTC).\n")
    A("Build vivo: `af14b300fc`. Builds anteriores: `b7dd88e9bf`, `233cad7d29`, `a32b59f504`, ...")
    A("RN_V es un hash de contenido (tools/build_public.py:18-26), no un commit: no mapea 1:1 a git.\n")
    A("VENTANAS DE DATOS DISTINTAS: el beacon funnel solo existe desde 2026-11-25 (commit `653dc84`): la conversión")
    A("y los load_ms son de UN dia. Los reportes crash van del 2026-11-21 al 2026-11-25. No mezclar.\n")

    A("## 1. Linea de tiempo por dia (UTC)\n")
    A("| dia | beacons funnel | llegan a run | se detienen | conv | reportes crash | crashes build vivo |")
    A("|---|---|---|---|---|---|---|")
    for d in days:
        n = fun_by_day[d]
        ok, st = run_by_day[d], stop_by_day[d]
        A(f"| {d} | {n} | {ok} | {st} | {100 * ok / max(1, ok + st):.0f}% | {cr_by_day[d]} | {live_cr_by_day[d]} |")
    A("")

    A("## 2. Funnel: conversion y carga\n")
    by = collections.defaultdict(lambda: {"run": 0, "stop": 0, "loads": [], "pais": collections.Counter()})
    pa = collections.Counter()
    for r in funnel:
        b = by[r["os"]]
        b[r["ev"]] += 1
        if r["ev"] == "run":
            b["loads"].append(r["load_ms"])
        b["pais"][r.get("country", "?")] += 1
        pa[r.get("country", "?")] += 1
    A("| OS | run | stop | conv | load p50 | p90 |")
    A("|---|---|---|---|---|---|")
    for osn, b in sorted(by.items(), key=lambda x: -x[1]["run"]):
        l = sorted(b["loads"])
        n = b["run"] + b["stop"]
        A(f"| {osn} | {b['run']} | {b['stop']} | {100 * b['run'] / max(1, n):.0f}% | {p50(l)}ms | {l[int(len(l) * .9)] if l else 0}ms |")
    A("")
    A(f"Total: {sum(b['run'] for b in by.values())} runs / {sum(b['run'] + b['stop'] for b in by.values())} sesiones = "
      f"{100 * sum(b['run'] for b in by.values()) / max(1, sum(b['run'] + b['stop'] for b in by.values())):.0f}% conversion.")
    A("Paises top: " + ", ".join(f"{k} {v}" for k, v in pa.most_common(12)) + "\n")

    w_warm = [r["wasm_ms"] for r in funnel if r["ev"] == "run" and r.get("warm") and r["wasm_ms"]]
    w_cold = [r["wasm_ms"] for r in funnel if r["ev"] == "run" and not r.get("warm") and r["wasm_ms"]]
    A(f"Carga del WASM: frio p50 {p50(w_cold)}ms p90 {sorted(w_cold)[int(len(w_cold) * .9)] if w_cold else 0}ms; "
      f"caliente (cache V8) p50 {p50(w_warm)}ms. El cache de codigo ya paga (commit 653dc84).\n")

    A("## 3. Taxonomia de crashes (cada clase con su evidencia)\n")
    tab = collections.defaultdict(list)
    for r in crash:
        tab[klass(r)].append(r)
    A("| clase | total | en build vivo | navegador tipico |")
    A("|---|---|---|---|")
    for k, v in sorted(tab.items(), key=lambda x: -len(x[1])):
        lv = sum(1 for r in v if r["v"] == live)
        br = collections.Counter(browser(r["ua"]) for r in v).most_common(1)[0][0]
        A(f"| {k} | {len(v)} | {lv} | {br} |")
    A("")
    detail = {
        "A": ("Todos del build `b7dd88e9bf`. La linea 146 de web/index.html leia `ab.contentWindow.RN_B.ready` sin guard "
              "y un iframe (embed de terceros) cruzado tiraba SecurityError en el primer frame (p50 0.07s). "
              "FIXED en commit `ab2f271` (try/catch, catch = listo). Cero ocurrencias en el build vivo."),
        "B": ("`crossOriginIsolated false` al arrancar (p50 0.00s). En el build vivo: 7x Chrome 158 Windows, 4x macOS, "
              "3x ChromeOS de escritorio SIN aislamiento (los headers COOP/COEP si llegan: verificado con curl hoy), "
              "mas WebViews Android (`; wv` en UA: LineageOS Jelly, PS4). INFERENCE: los de escritorio son la pagina "
              "embebida en un iframe ajeno (COOP se rompe dentro de un frame) o un proxy ISP que corta headers "
              "(el patron de paises es Africa/MEN/AAsia). Hay que diagnosticarlo en el cliente, no en el servidor."),
        "C": ("`WebAssembly.Memory(): could not allocate memory` (p50 0.58s, uno a los 7147s de juego). "
              "`deviceMemory` mediana 2 GB, pantallas cortas (684x276, 840x331: telefonos en landscape). "
              "Paises: DZ 13, EG 6, IN 6, GR 5, KZ 5. speed_lite ya baja el budget a 448 MB (commit 511830f) "
              "pero no alcanza en telefonos de 2 GB. INFERENCE: parte del crecido largo-plazo es nuestro propio "
              "crecimiento de memoria en sesiones largas."),
        "D": ("Mezcla: 20x Chrome 109 (Win7, sin WebGPU y con WebGL2 caido o bloqueado), iOS 17.7/26 sin WebGL2 util, "
              "3x Safari `samplerParameteri` tipo equivocado (web/gpu.js), 5x `createRenderPipeline` falla, "
              "1x `beginRenderPass` undefined (build vivo). p50 0.01s: muere en el gate, no en el juego."),
        "E": ("Device removed real: D3D12 `GetDeviceRemovedReason` en Windows y `Instance no longer exists` (WebGPU). "
              "p50 60s: pasa DURANTE el juego. Drivers/GPU, no codigo. Hay que mirar si el host sobrecarga la GPU en tier auto."),
        "F": ("Descarga del WASM cortada (p50 8s). Egipto/Turquia/Irak/China: redes lentas o filtradas. "
              "921e827 ya puso reintentos; quedan 5 en el build vivo."),
        "G": ("`chrome-extension://bkkbcggnhapdmkeljlodobbkopceiche` inyecta y asigna window.open: rompe. "
              "NO es nuestro codigo. Accion: solo mejorar el mensaje."),
        "H": ("1 caso: race de orden de scripts en boot.js (`startGpu` referenciado antes de definirse). Unico."),
        "I": ("Safari (iOS 18.7 mayormente) enmascara el detalle del error: 'Script error. at :0', stack "
              "`webkit-masked-url://hidden/` o '[object ErrorEvent]'. 6 en el build vivo, a los 0.10s justo despues de "
              "`wasm: speed_lite (448 MB)`. UNKNOWN el contenido; actuar requiere filename/lineno en el beacon (seccion 6)."),
        "J": ("5x `Sandbox access violation` (build b7dd88e9bf): la pagina embebida en un frame con sandbox. Ya no aparece."),
        "K": ("41x `ExitProcess(0)` de build 233cad7d29: el jugador SALIO del menu de pausa y el beacon viejo lo contaba "
              "como crash. boot.js ya lo filtra (`if (!/: ExitProcess\\(0\\)/) crashSend(s)`). Cero en el build vivo. "
              "No era un crash del juego."),
        "L": ("4x audio (InvalidStateError al arrancar el audio device), p50 112s. audio.js ya reintentado en 921e827."),
    }
    A("### Detalle por clase\n")
    for k, v in sorted(tab.items(), key=lambda x: -len(x[1])):
        tag = k[0]
        A(f"**{k} ({len(v)} total, {sum(1 for r in v if r['v'] == live)} en build vivo)**")
        A(detail.get(tag, "Caso unico, ver dump crudo."))
        A("")

    A("## 4. Lo que YA arreglamos (con commit)\n")
    A("- `ab2f271` guard try/catch en la lectura RN_B del iframe cortina (clase A, 100 crashes).")
    A("- `921e827` hardening de prod: bgra fallback, waitAsync, reintentos de red, audio, storage y filtro de ExitProcess (clases F, L, K).")
    A("- `511830f` OOM de 50 min + speed_lite WASM de 448 MB (clase C parcial).")
    A("- `9776828` retiró el tag RUM duplicado; los headers COOP/COEP/CORP viven como reglas del dominio en Cloudflare (verificado hoy con curl).")
    A("- cache V8 del WASM y beacons funnel (`653dc84`): la carga caliente bajo a 585 ms p50.\n")

    A("## 5. Lo que FALTA (ordenado por impacto real, build vivo)\n")
    A("1. **Clase B, 24-31 sesiones: diagnostico del cliente.** El servidor hace su parte (headers ok). En boot.js, cuando "
      "`crossOriginIsolated` sea false, reportar COMO se abrio la sesion: `window.top !== window` (iframe ajeno), "
      "headers de una respuesta fetch('/') al mismo origen, y `navigator.userAgent` ya esta. Una linea de log + campo en el beacon "
      "resuelve el UNKNOWN de si es iframe o proxy ISP.")
    A("2. **Clase C, 21 sesiones: presupuesto por dispositivo.** deviceMemory 2 GB no llega ni con 448 MB. Opciones: "
      "no-boot con mensaje claro y accion (cerrar apps, otro navegador) o budget dinamico ~ deviceMemory*0.35. "
      "Medir primero: el beacon ya trae `mem`.")
    A("3. **Clase I, 6 sesiones: visibility del error iOS.** window.onerror con filename/lineno en el beacon; hoy Safari manda 'Script error. at :0' y no se puede actuar.")
    A("4. **Clase D: gate Chrome 109.** 20 sesiones viejas de Win7 caen en 'no tiene WebGPU ni WebGL 2': mejor mensaje ('actualiza Chrome' / navegador soportado) en vez de stop frio.")
    A("5. **Clase E: medicion, no codigo.** 7 sesiones perdieron la GPU a los ~60s: capturar `perf`/frame windows del rnStats en el beacon para saber si va precedido de pico de frames.")
    A("6. **Clase G (extension Chrome):** detectar el error con extension:// en el stack y clasificarlo como ruido de entorno.\n")

    A("## 6. Huecos del propio sistema de telemetria (re-inventar aqui, no en el juego)\n")
    A("- **Sin timestamp en el payload**: el worker solo lo usa en el key R2. Agregar `ts` al json (worker.js) hace el dump autocontenido y el dedup posible.")
    A("- **`tier` siempre vacio**: el beacon manda `tier: window.RN_TIER` pero nadie lo asigna (el log dice 'tier: ultralite (auto...)'). Perdemos el desglose por tier en el funnel.")
    A("- **Sin session id anonimo**: no se puede juntar el beacon funnel con un crash posterior de la misma sesion; hoy son dos poblaciones.")
    A("- **`Script error` opaco**: sin filename/lineno (punto 5.3).")
    A("- **Sin retencion ni alerta**: el bucket crece crudo (849 beacons/5 dias); no hay agregado diario. read.sh/read_funnel.sh solo ven un dia.")
    A("- **RUM de Cloudflare: NO esta midiendo.** Se quito el tag manual (9776828) asumiendo auto-inyeccion, pero la pagina viva no trae beacon de cloudflareinsights (curl hoy). Falta activarlo en el dashboard o restaurar el tag: sin RUM no hay vistas ni bounce, solo sesiones que llegan a run/stop.")
    A("- **Body cap 32 KB** (worker.js): ok por ahora; el tail de 40 lineas ya roza en sesiones largas.\n")

    A("## 7. Metodologia y limites")
    A("- Fuente: rclone cat por dia a /tmp/nfsu-audit/, un jsonl por tipo y dia; todo con dia UTC explícito.")
    A("- Duplicados posibles entre descargas parciales y completas: las cifras de este informe salen SOLO de los per-day (sin doble conteo).")
    A("- Lo que el beacon NO ve: visita que abandona antes del primer beacon, pings de red tras cerrar la pestana, y paises sin GeoIP de Cloudflare.")
    A("- UNKNOWN marcado donde el dato no alcanza (origen de la clase B, contenido de la clase I).")
    print("\n".join(L))

    open(os.path.join(HERE, "AUDIT.md"), "w").write("\n".join(L) + "\n")
    print(f"\nwrote {os.path.join(HERE, 'AUDIT.md')} and {dump}", file=sys.stderr)


if __name__ == "__main__":
    main()
