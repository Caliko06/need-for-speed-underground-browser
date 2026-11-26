#!/usr/bin/env python3
"""Static Press & Media Fact Sheet generator (EN + ES) for https://nfsu.cc/press/.
Zero JS, zero extra image assets (reuses /og.jpg and /blog/img/*.webp), zero impact on game boot weight.
Usage: python3 tools/build_press.py
Import: from build_press import build_press  # returns [(loc, lastmod, alts_dict), ...]
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "web")
SITE = "https://nfsu.cc"
REPO = "https://github.com/Caliko06/need-for-speed-underground-browser"
DATE = "2026-11-26"
e = html.escape

ORG = {
    "@type": "Organization",
    "name": "NFS Underground Web",
    "url": SITE + "/",
    "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png"},
}

DATA = {
    "en": {
        "rel": "press/index.html",
        "other_rel": "press/es/index.html",
        "other_lang": "es",
        "other_label": "Español",
        "title": "Press Kit & Fact Sheet: Need for Speed Underground (2003) in Browser",
        "desc": "Verified facts, engineering benchmarks, press screenshots, and quotable summaries for NFSU.cc, the open-source WebAssembly and WebGPU static recompilation of Need for Speed: Underground (2003).",
        "h1": "Press Kit & Fact Sheet (NFSU.cc)",
        "lead": "Everything journalists, YouTubers, and community editors need to cover NFSU.cc: verified metrics from Speed.exe, quotable summaries, and high-resolution browser screenshots.",
        "play": "Play now",
        "guides": "Guides",
        "quote_h": "One-paragraph summary (ready to quote)",
        "quote": "NFSU.cc is a free, open-source browser port of the original 2003 PC release of Need for Speed: Underground. Rather than emulating a PC at runtime, the project statically recompiles all 13,766 x86 functions from Speed.exe into WebAssembly (7.04 MB Brotli) and translates DirectX 9 to WebGPU with automatic WebGL 2 fallback. It runs directly in desktop and mobile browsers (Chrome, Edge, Firefox, Safari) with no installation, preserving the full Go Underground career (111 main events), all 20 tuner cars, all 26 original 2003 soundtrack tracks, 33 PC cheat codes, local browser saves, keyboard, gamepad, and mobile touch controls.",
        "facts_h": "Verified fact sheet",
        "facts": [
            ("Project name", "NFS Underground Web (nfsu.cc)"),
            ("Live URL", f'<a href="{SITE}/">{SITE}/</a>'),
            ("Source code", f'<a href="{REPO}" rel="noopener">github.com/Caliko06/need-for-speed-underground-browser</a>'),
            ("Technology", "Ahead-of-time x86-to-C static recompilation -> WebAssembly + WebGPU (automatic WebGL 2 fallback) + Web Audio"),
            ("Lifted binary", "Speed.exe (2003 PC, 3.18 MB, 13,766 lifted x86 functions -> 7.04 MB Brotli WASM)"),
            ("Desktop cold boot", "2.27 s to live 3D WebGPU frames"),
            ("Mobile build", "448 MB lite WASM heap (speed_lite.wasm) with touch controls for Android & iOS"),
            ("Game content", "20 playable cars, 26 original soundtrack tracks, 33 PC cheat codes, 111 main Go Underground career events + final challenge"),
            ("Visual modes", "Original 2003 (as shipped) + Remaster mode (bloom, edge smoothing; toggle with F4 on desktop)"),
            ("Price & status", "Free, non-commercial open-source fan preservation project. Not affiliated with Electronic Arts."),
        ],
        "shots_h": "Press screenshots (free to embed with credit to nfsu.cc)",
        "shots": [
            ("/og.jpg", "Need for Speed Underground (2003) running in a web browser at nfsu.cc (1200x630)", "Hero banner (1200x630 JPG): Olympic City at night in Chrome via WebGPU."),
            ("/blog/img/olympic-city-world.webp", "Olympic City street race in Need for Speed Underground running in Chrome", "Desktop gameplay (WebGPU): Olympic City night street race."),
            ("/blog/img/olympic-city-drive.webp", "Blue Nissan Skyline driving through Olympic City in browser", "Desktop gameplay: Skyline R34 in motion with original 2003 lighting."),
            ("/blog/img/phone-touch.webp", "Need for Speed Underground running on a smartphone browser with touch controls", "Mobile browser build (448 MB lite WASM): on-screen touch controls."),
        ],
        "links_h": "Deep links for readers",
        "links": [
            ("/", "Play Need for Speed Underground Online Free (Browser)"),
            ("/blog/en/need-for-speed-underground-car-list.html", "Complete 20-Car List & Unlock Guide (verified from GLOBALB.BUN)"),
            ("/blog/en/need-for-speed-underground-soundtrack.html", "Complete 26-Track 2003 Soundtrack (verified from Speed.exe EA TRAX)"),
            ("/blog/en/need-for-speed-underground-cheat-codes.html", "All 33 PC Cheat Codes (verified from Speed.exe EasterEggs)"),
            ("/blog/en/need-for-speed-underground-career-events-guide.html", "Go Underground Career Guide (111 Events & Bosses)"),
            ("/reverse-engineering/index.html", "Reverse Engineering & Static Recompilation Field Guide"),
            ("/devlog/index.html", "Engineering Devlog & A/B Benchmarks"),
            ("/llms.txt", "Machine-readable LLM / AEO Index (llms.txt)"),
        ],
        "legal_h": "Editorial & legal note",
        "legal": "NFS Underground Web (nfsu.cc) is an independent, non-commercial open-source preservation and reverse-engineering project. It is not affiliated with, sponsored by, or endorsed by Electronic Arts Inc. Need for Speed is a registered trademark of Electronic Arts Inc.",
        "foot": "NFS Underground Web · Press Kit",
    },
    "es": {
        "rel": "press/es/index.html",
        "other_rel": "press/index.html",
        "other_lang": "en",
        "other_label": "English",
        "title": "Kit de Prensa y Ficha Técnica: Need for Speed Underground (2003) en Navegador",
        "desc": "Datos verificados, benchmarks de ingeniería, capturas de prensa y resumen listo para citar de NFSU.cc, la recompilación estática a WebAssembly y WebGPU de Need for Speed: Underground (2003).",
        "h1": "Kit de Prensa y Ficha Técnica (NFSU.cc)",
        "lead": "Todo lo que periodistas, creadores de YouTube y editores necesitan para cubrir NFSU.cc: métricas reales de Speed.exe, resumen citable y capturas en alta resolución.",
        "play": "Jugar ahora",
        "guides": "Guías",
        "quote_h": "Resumen de un párrafo (listo para citar)",
        "quote": "NFSU.cc es un port gratuito y de código abierto para navegador del Need for Speed: Underground original de PC (2003). En lugar de emular una PC en tiempo real, el proyecto recompila estáticamente las 13,766 funciones x86 de Speed.exe a WebAssembly (7.04 MB en Brotli) y traduce DirectX 9 a WebGPU con fallback automático a WebGL 2. Corre directo en navegadores de escritorio y celular (Chrome, Edge, Firefox, Safari) sin descargar ni instalar nada, conservando el modo carrera Go Underground completo (111 eventos principales), los 20 autos, las 26 canciones originales de 2003, 33 trucos de PC, guardado local, teclado, mando y controles táctiles.",
        "facts_h": "Ficha técnica verificada",
        "facts": [
            ("Nombre del proyecto", "NFS Underground Web (nfsu.cc)"),
            ("Enlace para jugar", f'<a href="{SITE}/">{SITE}/</a>'),
            ("Código fuente", f'<a href="{REPO}" rel="noopener">github.com/Caliko06/need-for-speed-underground-browser</a>'),
            ("Tecnología", "Recompilación estática x86 a C -> WebAssembly + WebGPU (fallback automático a WebGL 2) + Web Audio"),
            ("Binario recompilado", "Speed.exe (PC 2003, 3.18 MB, 13,766 funciones x86 -> 7.04 MB WASM en Brotli)"),
            ("Arranque en escritorio", "2.27 s hasta los primeros cuadros 3D en WebGPU"),
            ("Build móvil", "Heap WASM ligero de 448 MB (speed_lite.wasm) con controles táctiles en Android y iOS"),
            ("Contenido del juego", "20 autos jugables, 26 canciones del soundtrack original, 33 trucos de PC, 111 eventos de Go Underground + reto final"),
            ("Modos visuales", "Original 2003 (como salió) + modo Remaster (bloom y suavizado; alterna con F4 en PC)"),
            ("Precio y licencia", "Gratuito, proyecto fan no comercial de preservación y código abierto. Sin afiliación con Electronic Arts."),
        ],
        "shots_h": "Capturas de prensa (libres de uso citando nfsu.cc)",
        "shots": [
            ("/og.jpg", "Need for Speed Underground (2003) corriendo en navegador en nfsu.cc (1200x630)", "Banner principal (1200x630 JPG): Olympic City de noche en Chrome vía WebGPU."),
            ("/blog/img/olympic-city-world.webp", "Carrera nocturna en Olympic City dentro de Chrome", "Gameplay de escritorio (WebGPU): carrera callejera nocturna en Olympic City."),
            ("/blog/img/olympic-city-drive.webp", "Nissan Skyline azul corriendo en Olympic City en el navegador", "Gameplay de escritorio: Skyline R34 en movimiento con iluminación original de 2003."),
            ("/blog/img/phone-touch.webp", "Need for Speed Underground en navegador móvil con controles táctiles", "Build móvil (WASM ligero de 448 MB): controles táctiles en pantalla."),
        ],
        "links_h": "Enlaces útiles para lectores",
        "links": [
            ("/", "Jugar Need for Speed Underground Online Gratis (Navegador)"),
            ("/blog/es/lista-autos-need-for-speed-underground.html", "Lista completa de 20 autos y desbloqueos (verificada en GLOBALB.BUN)"),
            ("/blog/es/soundtrack-need-for-speed-underground.html", "Soundtrack completo de 26 canciones (verificado en Speed.exe EA TRAX)"),
            ("/blog/es/trucos-need-for-speed-underground-pc.html", "Todos los 33 trucos de PC (verificados en Speed.exe EasterEggs)"),
            ("/blog/es/guia-modo-carrera-need-for-speed-underground.html", "Guía del Modo Carrera Go Underground (111 eventos y jefes)"),
            ("/reverse-engineering/index.html", "Guía de Ingeniería Inversa y Recompilación Estática"),
            ("/devlog/es/index.html", "Bitácora de Ingeniería y Benchmarks A/B"),
            ("/llms.txt", "Índice para IA / AEO (llms.txt)"),
        ],
        "legal_h": "Nota editorial y legal",
        "legal": "NFS Underground Web (nfsu.cc) es un proyecto independiente, no comercial y de código abierto enfocado en preservación e ingeniería inversa. No está afiliado, patrocinado ni respaldado por Electronic Arts Inc. Need for Speed es una marca registrada de Electronic Arts Inc.",
        "foot": "NFS Underground Web · Kit de Prensa",
    },
}


def build_press():
    sitemap_urls = []
    alts_map = {
        "en": f"{SITE}/press/index.html",
        "es": f"{SITE}/press/es/index.html",
    }
    for lang, d in DATA.items():
        out_path = os.path.join(W, d["rel"])
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        canon = f"{SITE}/{d['rel']}"
        other_url = f"/{d['other_rel']}"
        facts_rows = "".join(f"<tr><td><b>{e(k)}</b></td><td>{v}</td></tr>" for k, v in d["facts"])
        shots_html = "".join(
            f'<figure><img src="{src}" alt="{e(alt)}" loading="lazy"><figcaption>{e(cap)} (<a href="{SITE}{src}">{src}</a>)</figcaption></figure>'
            for src, alt, cap in d["shots"]
        )
        links_html = "".join(f'<li><a href="{href}">{e(label)}</a></li>' for href, label in d["links"])
        ld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebPage",
                    "name": d["title"],
                    "description": d["desc"],
                    "url": canon,
                    "inLanguage": lang,
                    "datePublished": DATE,
                    "dateModified": DATE,
                    "publisher": ORG,
                    "about": {"@type": "VideoGame", "name": "Need for Speed: Underground", "url": SITE + "/"},
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "NFSU.cc", "item": SITE + "/"},
                        {"@type": "ListItem", "position": 2, "name": d["h1"], "item": canon},
                    ],
                },
            ],
        }
        page_html = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#04121a">
<title>{e(d['title'])} | NFS Underground Web</title>
<meta name="description" content="{e(d['desc'])}">
<link rel="canonical" href="{canon}">
<link rel="alternate" hreflang="en" href="{alts_map['en']}">
<link rel="alternate" hreflang="es" href="{alts_map['es']}">
<link rel="alternate" hreflang="x-default" href="{alts_map['en']}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:site_name" content="NFS Underground Web">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{e(d['title'])}">
<meta property="og:description" content="{e(d['desc'])}">
<meta property="og:image" content="{SITE}/og.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(d['title'])}">
<meta name="twitter:description" content="{e(d['desc'])}">
<meta name="twitter:image" content="{SITE}/og.jpg">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96.png">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png">
<link rel="stylesheet" href="/blog/blog.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body style="--pic: url(/blog/img/olympic-city-world.webp)">
<header class="top">
  <a class="logo" href="/"><img src="/launcher/v2/ui/logo.webp" alt="Need for Speed Underground" width="688" height="125"></a>
  <nav>
    <a href="/blog/{lang}/index.html">{e(d['guides'])}</a>
    <a href="/reverse-engineering/index.html">Reverse Engineering</a>
    <a href="/re/{'es/' if lang == 'es' else ''}index.html">RE Atlas</a>
    <a href="/devlog/{'es/' if lang == 'es' else ''}index.html">Devlog</a>
    <a href="{other_url}" hreflang="{d['other_lang']}" lang="{d['other_lang']}">{e(d['other_label'])}</a>
    <a href="{REPO}" rel="noopener">GitHub</a>
    <a class="play" href="/">{e(d['play'])}</a>
  </nav>
</header>
<main>
<p class="crumbs"><a href="/">NFSU.cc</a> / {e(d['h1'])}</p>
<article>
<h1>{e(d['h1'])}</h1>
<p class="lead">{e(d['lead'])}</p>
<h2>{e(d['quote_h'])}</h2>
<p>{e(d['quote'])}</p>
<h2>{e(d['facts_h'])}</h2>
<div class="table-wrap"><table class="data-table"><tbody>{facts_rows}</tbody></table></div>
<h2>{e(d['shots_h'])}</h2>
{shots_html}
<h2>{e(d['links_h'])}</h2>
<ul>{links_html}</ul>
<h2>{e(d['legal_h'])}</h2>
<p>{e(d['legal'])}</p>
<div class="cta"><a href="/">{e(d['play'])}</a></div>
</article>
</main>
<footer><span>{e(d['foot'])}</span><a href="/">{e(d['play'])}</a><a href="/blog/{lang}/index.html">{e(d['guides'])}</a><a href="/llms.txt">llms.txt</a><a href="{REPO}" rel="noopener">GitHub</a><a href="{other_url}" hreflang="{d['other_lang']}" lang="{d['other_lang']}">{e(d['other_label'])}</a></footer>
</body>
</html>
"""
        open(out_path, "w", encoding="utf-8").write(page_html)
        sitemap_urls.append((canon, DATE, alts_map))
    return sitemap_urls


if __name__ == "__main__":
    urls = build_press()
    print(f"press: {len(urls)} pages")
