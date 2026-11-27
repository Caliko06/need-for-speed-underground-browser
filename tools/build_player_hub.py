#!/usr/bin/env python3
"""Player topical authority & interactive SEO pages (EN + ES twins) for nfsu.cc.
Generates 8 static HTML pages under web/blog/en/ and web/blog/es/ matching tools/build_blog.py.

All game facts are directly extracted and verified from the shipped 2003 PC binary and data files:
- 20 playable cars: game/Global/GLOBALB.BUN (chunk 0x34600 CarTypeInfo, drivetrain torque split +0x2d0),
  game/LANGUAGES/English.bin (display names), game/FrontEnd/FrontB.lzc (chunk 0x34a02 EventDesc car rewards),
  pc/Speed.exe (0x306918..0x306cf4 individual car cheat codes).
- 26 soundtrack tracks: pc/Speed.exe (0x2f4d08..0x2f4ea4 EA TRAX table: title, artist, album, IG/FE zone),
  cross-checked with game/LANGUAGES/English.bin (0x023b63..0x0255aa).
- 33 PC cheat codes: pc/Speed.exe EasterEggs table (0x306918..0x306ec8, 29 x 0x34-byte records)
  plus 4 artist/sponsor preset car codes (0x2b88dc..0x2b895c).
- Career events: game/FrontEnd/FrontB.lzc (chunk 0x34a02 EventDesc: event 0 intro + 111 main Underground
  events IDs 1..112 excluding unused ID 85 + final challenge #113 Melissa = 112 post-intro events).

Usage: python3 tools/build_player_hub.py
Import: from build_player_hub import build_player_hub  # returns [(lang, slug, twin_slug, title, desc), ...]
"""
import html
import json
import os

DATE = "2026-11-26"
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_common import ROOT, W, SITE, REPO, LANGS, ORG, e, url

UI = {
    "en": dict(
        guides="Guides",
        play="Play",
        other="Español",
        more="More guides",
        foot="NFSU.cc: Need for Speed Underground in the browser.",
        code="Code on GitHub",
        updated="Updated November 26, 2026",
    ),
    "es": dict(
        guides="Guías",
        play="Jugar",
        other="English",
        more="Más guías",
        foot="NFSU.cc: Need for Speed Underground en el navegador.",
        code="Código en GitHub",
        updated="Actualizado el 26 de noviembre de 2026",
    ),
}

# Verified data extracted from game/Global/GLOBALB.BUN, game/LANGUAGES/English.bin,
# game/FrontEnd/FrontB.lzc, and pc/Speed.exe.
# (model, make, drivetrain, unlock_en, unlock_es, cheat_code)
CARS = [
    ("2003 Volkswagen Golf GTI 2.0L", "Volkswagen", "FWD", "Starter (Event #0)", "Inicial (Evento #0)", "334mygolf"),
    ("2003 Ford Focus ZX3", "Ford", "FWD", "Event #8", "Evento #8", "119focus"),
    ("1999 Mazda MX-5 Miata", "Mazda", "RWD", "Starter (Event #0)", "Inicial (Evento #0)", "221miata"),
    ("1999 Dodge Neon", "Dodge", "FWD", "Starter (Event #0)", "Inicial (Evento #0)", "893neon"),
    ("2000 Honda Civic Si Coupe", "Honda", "FWD", "Starter (Event #0)", "Inicial (Evento #0)", "889civic"),
    ("2003 Peugeot 206", "Peugeot", "FWD", "Starter (Event #0)", "Inicial (Evento #0)", "77peugeot"),
    ("2002 Toyota Celica GT-S", "Toyota", "FWD", "Event #41", "Evento #41", "239celica"),
    ("1999 Mitsubishi Eclipse GSX", "Mitsubishi", "AWD", "Event #58", "Evento #58", "899eclipse"),
    ("1995 Mazda RX-7", "Mazda", "RWD", "Event #73", "Evento #73", "777rx7"),
    ("1998 Toyota Supra", "Toyota", "RWD", "Event #64", "Evento #64", "228supra"),
    ("2003 Honda S2000", "Honda", "RWD", "Event #69", "Evento #69", "2000s2000"),
    ("2003 Acura RSX Type-S", "Acura", "FWD", "Event #46", "Evento #46", "973rsx777"),
    ("2003 Subaru Impreza 2.5 RS", "Subaru", "AWD", "Event #22", "Evento #22", "371impreza"),
    ("2003 Mitsubishi Lancer ES", "Mitsubishi", "FWD", "Event #4", "Evento #4", "222lancer"),
    ("2000 Acura Integra Type-R", "Acura", "FWD", "Event #53", "Evento #53", "342integra"),
    ("2003 Hyundai Tiburon GT V6", "Hyundai", "FWD", "Event #17", "Evento #17", "667tiburon"),
    ("2003 Nissan 350Z", "Nissan", "RWD", "Event #75", "Evento #75", "350350z"),
    ("2004 Nissan Sentra SE-R Spec V", "Nissan", "FWD", "Event #24", "Evento #24", "922sentra"),
    ("1992 Nissan 240SX SE", "Nissan", "RWD", "Event #33", "Evento #33", "240240sx"),
    ("1999 Nissan Skyline R34 GTR", "Nissan", "AWD", "Event #79", "Evento #79", "111skyline"),
]

# Verified from pc/Speed.exe EA TRAX table at 0x2f4d08..0x2f4ea4 (26 tracks: 19 IG, 7 FE)
# (num, artist, title, album, zone)
SOUNDTRACK = [
    (1, "Overseer", "Doomsday", "Wreckage", "IG"),
    (2, "The Crystal Method", "Born Too Slow", "Legion of Boom", "IG"),
    (3, "Rancid", "Out of Control", "Indestructible", "IG"),
    (4, "Rob Zombie", "Two-Lane Blacktop", "Past, Present & Future", "IG"),
    (5, "BT", "Kimosabe", "Emotional Technology", "IG"),
    (6, "Static-X", "The Only", "Shadow Zone", "IG"),
    (7, "Element Eighty", "Broken Promises", "Element Eighty", "IG"),
    (8, "Asian Dub Foundation", "Fortress Europe", "Enemy of the Enemy", "IG"),
    (9, "Hotwire", "Invisible", "The Routine", "IG"),
    (10, "Story of the Year", "And the Hero Will Drown", "Page Avenue", "IG"),
    (11, "Andy Hunter", "The Wonders of You", "Exodus", "IG"),
    (12, "Junkie XL", "Action Radius", "Big Sounds of the Drags", "IG"),
    (13, "Fuel", "Quarter", "Natural Selection", "IG"),
    (14, "Jerk", "Sucked In", "When Pure is Defiled", "IG"),
    (15, "Fluke", "Snapshot", "Puppy", "IG"),
    (16, "lostprophets", "Ride", "Start Something", "IG"),
    (17, "Overseer", "Supermoves", "Wreckage", "IG"),
    (18, "FC Kahuna", "Glitterball", "Machine Says Yes", "IG"),
    (19, "Blindside", "Swallow", "About a Burning Fire", "IG"),
    (20, "Lil Jon & the Eastside Boyz", "Get Low", "Kings of Crunk", "FE"),
    (21, "Mystikal", "Smashing the Gas (Get Faster)", "Need for Speed Exclusive", "FE"),
    (22, "Dilated Peoples", "Who's Who", "Neighborhood Watch", "FE"),
    (23, "Nate Dogg", "Keep It Coming", "Need for Speed Exclusive", "FE"),
    (24, "X-ecutioners", "Body Rock", "Built from Scratch", "FE"),
    (25, "Petey Pablo", "Need For Speed", "Need for Speed Exclusive", "FE"),
    (26, "T.I.", "24's", "Trap Muzik", "FE"),
]

# Verified from pc/Speed.exe:
# - EasterEggs table at 0x306918..0x306ec8 (29 entries)
# - Preset car codes at 0x2b88dc..0x2b895c (4 entries)
# (code, category, effect_en, effect_es)
CHEATS = [
    # Tracks & Modes (4)
    ("gimmesomecircuits", "tracks", "Unlock all Circuit tracks in Quick Race", "Desbloquea todas las pistas de Circuito en Carrera Rápida"),
    ("gimmesomesprints", "tracks", "Unlock all Sprint tracks in Quick Race", "Desbloquea todas las pistas de Sprint en Carrera Rápida"),
    ("gimmesomedrag", "tracks", "Unlock all Drag tracks in Quick Race", "Desbloquea todas las pistas de Arrancones (Drag) en Carrera Rápida"),
    ("driftdriftbaby", "tracks", "Unlock all Drift tracks in Quick Race", "Desbloquea todas las pistas de Drift en Carrera Rápida"),
    # Upgrades & Physics (4)
    ("allmylvloneparts", "upgrades", "Unlock all Level 1 performance parts", "Desbloquea todas las piezas de rendimiento Nivel 1"),
    ("allmylvl2parts", "upgrades", "Unlock all Level 2 performance parts", "Desbloquea todas las piezas de rendimiento Nivel 2"),
    ("seemylvl2parts", "upgrades", "Unlock all Level 2 visual customization parts", "Desbloquea todas las piezas visuales Nivel 2"),
    ("slidingwithstyle", "upgrades", "Enable Drift physics in all game modes", "Activa la física de Drift en todos los modos de juego"),
    # Special Preset Cars (5)
    ("givemenismo", "presets", "Unlock Nismo Nissan Sentra SE-R Spec V preset", "Desbloquea el Nissan Sentra SE-R Spec V edición Nismo"),
    ("gimmeppablo", "presets", "Unlock Petey Pablo's Mitsubishi Eclipse preset", "Desbloquea el Mitsubishi Eclipse de Petey Pablo"),
    ("gotcharobzombie", "presets", "Unlock Rob Zombie's Nissan 350Z preset", "Desbloquea el Nissan 350Z de Rob Zombie"),
    ("havyamystikal", "presets", "Unlock Mystikal's Toyota Celica preset", "Desbloquea el Toyota Celica de Mystikal"),
    ("needmylostprophets", "presets", "Unlock Lostprophets' Honda S2000 preset", "Desbloquea el Honda S2000 de Lostprophets"),
    # Individual Playable Cars (20)
    ("111skyline", "cars", "Unlock 1999 Nissan Skyline R34 GTR", "Desbloquea el 1999 Nissan Skyline R34 GTR"),
    ("350350z", "cars", "Unlock 2003 Nissan 350Z", "Desbloquea el 2003 Nissan 350Z"),
    ("777rx7", "cars", "Unlock 1995 Mazda RX-7", "Desbloquea el 1995 Mazda RX-7"),
    ("228supra", "cars", "Unlock 1998 Toyota Supra", "Desbloquea el 1998 Toyota Supra"),
    ("2000s2000", "cars", "Unlock 2003 Honda S2000", "Desbloquea el 2003 Honda S2000"),
    ("899eclipse", "cars", "Unlock 1999 Mitsubishi Eclipse GSX", "Desbloquea el 1999 Mitsubishi Eclipse GSX"),
    ("342integra", "cars", "Unlock 2000 Acura Integra Type-R", "Desbloquea el 2000 Acura Integra Type-R"),
    ("973rsx777", "cars", "Unlock 2003 Acura RSX Type-S", "Desbloquea el 2003 Acura RSX Type-S"),
    ("239celica", "cars", "Unlock 2002 Toyota Celica GT-S", "Desbloquea el 2002 Toyota Celica GT-S"),
    ("240240sx", "cars", "Unlock 1992 Nissan 240SX SE", "Desbloquea el 1992 Nissan 240SX SE"),
    ("922sentra", "cars", "Unlock 2004 Nissan Sentra SE-R Spec V", "Desbloquea el 2004 Nissan Sentra SE-R Spec V"),
    ("371impreza", "cars", "Unlock 2003 Subaru Impreza 2.5 RS", "Desbloquea el 2003 Subaru Impreza 2.5 RS"),
    ("667tiburon", "cars", "Unlock 2003 Hyundai Tiburon GT V6", "Desbloquea el 2003 Hyundai Tiburon GT V6"),
    ("119focus", "cars", "Unlock 2003 Ford Focus ZX3", "Desbloquea el 2003 Ford Focus ZX3"),
    ("222lancer", "cars", "Unlock 2003 Mitsubishi Lancer ES", "Desbloquea el 2003 Mitsubishi Lancer ES"),
    ("889civic", "cars", "Unlock 2000 Honda Civic Si Coupe", "Desbloquea el 2000 Honda Civic Si Coupe"),
    ("221miata", "cars", "Unlock 1999 Mazda MX-5 Miata", "Desbloquea el 1999 Mazda MX-5 Miata"),
    ("893neon", "cars", "Unlock 1999 Dodge Neon", "Desbloquea el 1999 Dodge Neon"),
    ("334mygolf", "cars", "Unlock 2003 Volkswagen Golf GTI 2.0L", "Desbloquea el 2003 Volkswagen Golf GTI 2.0L"),
    ("77peugeot", "cars", "Unlock 2003 Peugeot 206", "Desbloquea el 2003 Peugeot 206"),
]

# Scoped interactive component styles inheriting ../blog.css tokens
EXTRA_CSS = """
.hub-controls { display: flex; flex-wrap: wrap; gap: 10px 12px; align-items: center; margin: 24px var(--pad) 0; }
.hub-search { flex: 1 1 220px; padding: 10px 14px; background: rgba(2, 12, 18, .75); border: 2px solid var(--bar); color: var(--hi); font: 15px/1.3 var(--f); }
.hub-search::placeholder { color: var(--dim); }
.hub-search:focus { outline: none; border-color: var(--key); }
.hub-select { padding: 10px 12px; background: rgba(2, 12, 18, .85); border: 2px solid var(--bar); color: var(--hi); font: 15px/1.3 var(--f); }
.hub-select:focus { outline: none; border-color: var(--key); }
.hub-pills { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px var(--pad) 0; }
.hub-pill { padding: 6px 12px; border: 1px solid var(--bar); background: rgba(4, 20, 29, .6); color: var(--text); font: italic 600 13px/1.2 var(--f); text-transform: uppercase; letter-spacing: .04em; cursor: pointer; transition: background-color .12s, border-color .12s, color .12s, transform .12s var(--ease); }
.hub-pill:hover { border-color: var(--key); color: var(--hi); }
.hub-pill[aria-pressed="true"] { background: rgba(63, 173, 209, .24); border-color: var(--key); color: #fff; }
.hub-pill:active, .copy-btn:active { transform: scale(.97); }
.hub-count { margin: 12px var(--pad) 0; font-size: 14px; color: var(--dim); }
.hub-table-wrap { margin: 14px var(--pad) 0; overflow-x: auto; border: 1px solid var(--bar); background: rgba(2, 12, 18, .48); }
.hub-table { width: 100%; border-collapse: collapse; font-size: 15px; line-height: 1.45; }
.hub-table th { text-align: left; padding: 11px 12px; background: rgba(92, 150, 184, .18); color: var(--hi); font: italic 600 13px/1.2 var(--f); text-transform: uppercase; letter-spacing: .04em; border-bottom: 2px solid var(--bar); white-space: nowrap; }
.hub-table td { padding: 10px 12px; border-bottom: 1px solid var(--bar2); vertical-align: middle; }
.hub-table tbody tr:hover { background: rgba(92, 150, 184, .09); }
.hub-table tr[hidden] { display: none; }
.tag { display: inline-block; padding: 2px 7px; border: 1px solid var(--bar); font: 600 12px/1.3 var(--f); letter-spacing: .04em; color: var(--hi); background: rgba(92, 150, 184, .14); white-space: nowrap; }
.tag-awd, .tag-fe { border-color: var(--key); color: var(--key); }
.tag-rwd, .tag-ig { border-color: rgba(196, 225, 229, .45); color: var(--hi); }
.code-cell { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; color: var(--hi); font-weight: 600; white-space: nowrap; }
.copy-btn { padding: 5px 11px; border: 1px solid var(--key); background: rgba(63, 173, 209, .14); color: var(--hi); font: 600 12px/1.2 var(--f); text-transform: uppercase; letter-spacing: .04em; cursor: pointer; transition: background-color .12s, color .12s, transform .12s var(--ease); white-space: nowrap; }
.copy-btn:hover { background: rgba(63, 173, 209, .32); color: #fff; }
.copy-btn.copied { background: var(--key); color: #031018; }
.hub-table code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; color: var(--key); }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 20px var(--pad) 0; }
.stat-card { padding: 14px 16px; border: 1px solid var(--bar); background: rgba(2, 12, 18, .55); }
.stat-card b { display: block; font: italic 600 26px/1.1 var(--f); color: var(--hi); }
.stat-card span { display: block; margin-top: 4px; font-size: 13px; color: var(--dim); }
article h3 { margin: 24px var(--pad) 0; font: 600 18px/1.35 var(--f); color: var(--hi); }
@media (prefers-reduced-motion: reduce) { .hub-pill, .copy-btn { transition: none !important; } .hub-pill:active, .copy-btn:active { transform: none; } }
"""

PAGES_META = [
    dict(
        key="cars",
        img="olympic-city-world.webp",
        pic="olympic-city-drive.webp",
        slug=dict(en="need-for-speed-underground-car-list", es="lista-autos-need-for-speed-underground"),
        title=dict(
            en="Need for Speed Underground car list: all 20 cars, drivetrains & unlocks",
            es="Lista de autos de Need for Speed Underground: los 20 coches, tracción y desbloqueo",
        ),
        desc=dict(
            en="Complete list of all 20 playable cars in Need for Speed Underground (2003), verified from GLOBALB.BUN and Speed.exe, with drivetrain, career unlock event and Quick Race cheat code.",
            es="Lista completa de los 20 autos jugables de Need for Speed Underground (2003), verificada en GLOBALB.BUN y Speed.exe, con tracción, evento de desbloqueo y truco de Carrera Rápida.",
        ),
        lead=dict(
            en="Need for Speed Underground (2003) includes 20 licensed tuner cars across 12 manufacturers: 11 FWD, 6 RWD and 3 AWD. Five are available from the start of Go Underground; the other 15 unlock as you clear career events up to event #79.",
            es="Need for Speed Underground (2003) incluye 20 autos tuner licenciados de 12 marcas: 11 tracción delantera (FWD), 6 tracción trasera (RWD) y 3 tracción integral (AWD). Cinco están disponibles al empezar Go Underground y los otros 15 se desbloquean hasta el evento #79.",
        ),
        cta=dict(en="Play this game now on NFSU.cc", es="Juega ahora en NFSU.cc"),
    ),
    dict(
        key="soundtrack",
        img="olympic-city-drive.webp",
        pic="olympic-city-world.webp",
        slug=dict(en="need-for-speed-underground-soundtrack", es="soundtrack-need-for-speed-underground"),
        title=dict(
            en="Need for Speed Underground soundtrack: all 26 EA TRAX songs",
            es="Soundtrack de Need for Speed Underground: las 26 canciones de EA TRAX",
        ),
        desc=dict(
            en="Full 26-song Need for Speed Underground (2003) EA TRAX tracklist verified from Speed.exe: artist, song title, album and whether each track plays in menus or races.",
            es="Lista completa de las 26 canciones del soundtrack de Need for Speed Underground (2003) verificada en Speed.exe: artista, canción, álbum y dónde suena en el juego.",
        ),
        lead=dict(
            en="The original 2003 PC soundtrack contains 26 licensed EA TRAX songs: 19 rock, metal and electronic tracks assigned to races (IG) and 7 hip-hop tracks assigned to menus (FE), starting with Lil Jon & the Eastside Boyz's \"Get Low\". NFSU.cc streams all 26 original songs in your browser.",
            es="El soundtrack original de PC de 2003 tiene 26 canciones licenciadas de EA TRAX: 19 temas de rock, metal y electrónica para carreras (IG) y 7 temas de hip-hop para menús (FE), encabezados por \"Get Low\" de Lil Jon & the Eastside Boyz. NFSU.cc incluye las 26 canciones originales en el navegador.",
        ),
        cta=dict(en="Play with the full soundtrack on NFSU.cc", es="Juega con el soundtrack completo en NFSU.cc"),
    ),
    dict(
        key="cheats",
        img="olympic-city-world.webp",
        pic="olympic-city-drive.webp",
        slug=dict(en="need-for-speed-underground-cheat-codes", es="trucos-need-for-speed-underground-pc"),
        title=dict(
            en="Need for Speed Underground cheat codes (PC): all 33 verified codes",
            es="Trucos de Need for Speed Underground (PC): los 33 códigos verificados",
        ),
        desc=dict(
            en="All 33 PC cheat codes extracted directly from Speed.exe for Need for Speed Underground (2003): unlock all cars, tracks, Level 1 and 2 parts, drift physics and 5 special preset cars.",
            es="Los 33 códigos de trucos para PC extraídos directo de Speed.exe en Need for Speed Underground (2003): desbloquea autos, pistas, piezas nivel 1 y 2, física drift y 5 autos especiales.",
        ),
        lead=dict(
            en="The 2003 PC build of Need for Speed Underground contains 33 working cheat codes inside Speed.exe: 20 individual car unlocks, 5 special artist and Nismo presets, 4 track-mode unlocks, 3 upgrade unlocks and 1 drift-physics toggle. Every code works inside the browser version at NFSU.cc.",
            es="La versión de PC de 2003 de Need for Speed Underground contiene 33 trucos funcionales dentro de Speed.exe: 20 autos individuales, 5 autos especiales de artistas y Nismo, 4 códigos de pistas, 3 de piezas y 1 de física drift. Todos funcionan directo en el navegador en NFSU.cc.",
        ),
        cta=dict(en="Try these codes in your browser now", es="Prueba estos trucos en tu navegador ahora"),
    ),
    dict(
        key="career",
        img="olympic-city-drive.webp",
        pic="olympic-city-world.webp",
        slug=dict(en="need-for-speed-underground-career-events-guide", es="guia-modo-carrera-need-for-speed-underground"),
        title=dict(
            en="Need for Speed Underground career guide: all 111 events, modes & bosses",
            es="Guía del modo carrera de Need for Speed Underground: 111 eventos, modos y jefes",
        ),
        desc=dict(
            en="Complete Go Underground career guide verified from FrontB.lzc: 111 main events plus Melissa's final race, all 6 race modes, Reputation and Style Points, and boss battles against Samantha, TJ and Eddie.",
            es="Guía completa del modo carrera Go Underground verificada en FrontB.lzc: 111 eventos principales más la carrera final contra Melissa, los 6 modos, Reputación, Style Points y jefes Samantha, TJ y Eddie.",
        ),
        lead=dict(
            en="Go Underground is the story career of Need for Speed Underground (2003). After the intro daydream race (Event #0), you climb through 111 main Underground events ending against Eddie (#112), followed by a final challenge against Melissa (#113) for 112 post-intro events in total.",
            es="Go Underground es el modo historia de Need for Speed Underground (2003). Tras la carrera introductoria (Evento #0), avanzas por 111 eventos principales hasta enfrentar a Eddie (#112), seguidos de un reto final contra Melissa (#113), sumando 112 eventos después de la introducción.",
        ),
        cta=dict(en="Start Go Underground in your browser", es="Empieza Go Underground en tu navegador"),
    ),
]


def build_cars_body(lang):
    makes = sorted({c[1] for c in CARS})
    rows_html = []
    for idx, (model, make, dt, u_en, u_es, code) in enumerate(CARS, 1):
        u_txt = u_en if lang == "en" else u_es
        dt_cls = "tag-awd" if dt == "AWD" else ("tag-rwd" if dt == "RWD" else "")
        rows_html.append(
            f'<tr data-make="{e(make)}" data-dt="{dt}" data-q="{e((model + " " + make + " " + dt + " " + code).lower())}">'
            f'<td>{idx}</td>'
            f'<td><b>{e(model)}</b></td>'
            f'<td>{e(make)}</td>'
            f'<td><span class="tag {dt_cls}">{dt}</span></td>'
            f'<td>{e(u_txt)}</td>'
            f'<td class="code-cell"><code>{e(code)}</code></td>'
            f'</tr>'
        )
    make_opts = "".join(f'<option value="{e(m)}">{e(m)}</option>' for m in makes)
    if lang == "en":
        return f"""
<h2>Quick summary</h2>
<p>Every car below is read directly from the 2003 PC data tables (<code>CarTypeInfo</code> in <code>GLOBALB.BUN</code>, career rewards in <code>FrontB.lzc</code> and cheat codes in <code>Speed.exe</code>). Eleven cars are front-wheel drive (including the 2003 Mitsubishi Lancer ES), six are rear-wheel drive, and three are all-wheel drive with a 50/50 torque split (Eclipse GSX, Impreza 2.5 RS and Skyline R34 GTR).</p>
<div class="stat-grid">
  <div class="stat-card"><b>20</b><span>Playable tuner cars</span></div>
  <div class="stat-card"><b>11 / 6 / 3</b><span>FWD / RWD / AWD</span></div>
  <div class="stat-card"><b>5</b><span>Starter cars (Event #0)</span></div>
  <div class="stat-card"><b>Event #79</b><span>Final unlock (Skyline R34)</span></div>
</div>
<h2>Complete Need for Speed Underground car list</h2>
<p>Filter by make, drivetrain or search by model name or cheat code.</p>
<div class="hub-controls">
  <input id="car-search" class="hub-search" type="search" placeholder="Search car, make or cheat code..." aria-label="Search cars">
  <select id="car-make" class="hub-select" aria-label="Filter by make">
    <option value="">All makes (12)</option>
    {make_opts}
  </select>
</div>
<div class="hub-pills" role="group" aria-label="Filter by drivetrain">
  <button type="button" class="hub-pill" data-dt="" aria-pressed="true">All (20)</button>
  <button type="button" class="hub-pill" data-dt="FWD" aria-pressed="false">FWD (11)</button>
  <button type="button" class="hub-pill" data-dt="RWD" aria-pressed="false">RWD (6)</button>
  <button type="button" class="hub-pill" data-dt="AWD" aria-pressed="false">AWD (3)</button>
</div>
<p id="car-count" class="hub-count">Showing 20 of 20 cars</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="car-table">
    <thead>
      <tr><th>#</th><th>Car</th><th>Make</th><th>Drivetrain</th><th>Career Unlock</th><th>Quick Race Code</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>Starter cars vs. late-game unlocks</h2>
<p>Five cars unlock immediately after the intro daydream race (Event #0): the <b>1999 Mazda MX-5 Miata</b> (only RWD starter), <b>2000 Honda Civic Si Coupe</b>, <b>1999 Dodge Neon</b>, <b>2003 Volkswagen Golf GTI 2.0L</b> and <b>2003 Peugeot 206</b>. The final four unlocks arrive between Events #69 and #79: Honda S2000 (#69), Mazda RX-7 (#73), Nissan 350Z (#75) and Nissan Skyline R34 GTR (#79).</p>
<p>Want to test any car right away in Quick Race? Type its code from the table above on the Main Menu (see <a href="need-for-speed-underground-cheat-codes.html">the complete PC cheat codes guide</a>), or select <b>All open</b> in the <a href="/">NFSU.cc</a> launcher.</p>
<h2>Frequently asked questions</h2>
<h3>How many playable cars are in Need for Speed Underground?</h3>
<p>There are 20 playable tuner cars in Need for Speed Underground (2003), plus 15 non-playable traffic vehicles stored in the same <code>CarTypeInfo</code> table.</p>
<h3>Which cars are AWD in Need for Speed Underground?</h3>
<p>Three cars use an all-wheel-drive 50/50 torque split in the game's physics table: the 1999 Mitsubishi Eclipse GSX, the 2003 Subaru Impreza 2.5 RS and the 1999 Nissan Skyline R34 GTR. The 2003 Mitsubishi Lancer ES in this game is front-wheel drive.</p>
<h3>When do you unlock the Nissan Skyline R34 GTR?</h3>
<p>The 1999 Nissan Skyline R34 GTR is the last car unlocked in Go Underground career mode, awarded after winning Event #79. You can also unlock it in Quick Race with the code <code>111skyline</code>.</p>
<script>
(function(){{
  var search = document.getElementById('car-search');
  var makeSel = document.getElementById('car-make');
  var pills = document.querySelectorAll('.hub-pill[data-dt]');
  var rows = document.querySelectorAll('#car-table tbody tr');
  var countEl = document.getElementById('car-count');
  var activeDt = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var mk = makeSel.value;
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!mk || r.dataset.make === mk) && (!activeDt || r.dataset.dt === activeDt);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Showing ' + vis + ' of ' + rows.length + ' cars';
  }}
  search.addEventListener('input', apply);
  makeSel.addEventListener('change', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeDt = this.dataset.dt;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
}})();
</script>
"""
    return f"""
<h2>Resumen rápido</h2>
<p>Cada auto de esta tabla se extrajo directo de los archivos originales de PC de 2003 (<code>CarTypeInfo</code> en <code>GLOBALB.BUN</code>, recompensas en <code>FrontB.lzc</code> y códigos en <code>Speed.exe</code>). Once autos son tracción delantera (incluido el Mitsubishi Lancer ES 2003), seis son tracción trasera y tres son tracción integral con reparto 50/50 (Eclipse GSX, Impreza 2.5 RS y Skyline R34 GTR).</p>
<div class="stat-grid">
  <div class="stat-card"><b>20</b><span>Autos tuner jugables</span></div>
  <div class="stat-card"><b>11 / 6 / 3</b><span>FWD / RWD / AWD</span></div>
  <div class="stat-card"><b>5</b><span>Autos iniciales (Evento #0)</span></div>
  <div class="stat-card"><b>Evento #79</b><span>Último auto (Skyline R34)</span></div>
</div>
<h2>Lista completa de autos de Need for Speed Underground</h2>
<p>Filtra por marca, tipo de tracción o busca por modelo o código.</p>
<div class="hub-controls">
  <input id="car-search" class="hub-search" type="search" placeholder="Buscar auto, marca o código..." aria-label="Buscar autos">
  <select id="car-make" class="hub-select" aria-label="Filtrar por marca">
    <option value="">Todas las marcas (12)</option>
    {make_opts}
  </select>
</div>
<div class="hub-pills" role="group" aria-label="Filtrar por tracción">
  <button type="button" class="hub-pill" data-dt="" aria-pressed="true">Todos (20)</button>
  <button type="button" class="hub-pill" data-dt="FWD" aria-pressed="false">FWD (11)</button>
  <button type="button" class="hub-pill" data-dt="RWD" aria-pressed="false">RWD (6)</button>
  <button type="button" class="hub-pill" data-dt="AWD" aria-pressed="false">AWD (3)</button>
</div>
<p id="car-count" class="hub-count">Mostrando 20 de 20 autos</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="car-table">
    <thead>
      <tr><th>#</th><th>Auto</th><th>Marca</th><th>Tracción</th><th>Desbloqueo Carrera</th><th>Código Carrera Rápida</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>Autos iniciales frente a los últimos desbloqueos</h2>
<p>Cinco autos se desbloquean justo después de la carrera introductoria (Evento #0): el <b>1999 Mazda MX-5 Miata</b> (único inicial RWD), <b>2000 Honda Civic Si Coupe</b>, <b>1999 Dodge Neon</b>, <b>2003 Volkswagen Golf GTI 2.0L</b> y <b>2003 Peugeot 206</b>. Los últimos cuatro llegan entre los eventos #69 y #79: Honda S2000 (#69), Mazda RX-7 (#73), Nissan 350Z (#75) y Nissan Skyline R34 GTR (#79).</p>
<p>Si quieres probar cualquier auto al instante en Carrera Rápida, escribe su código en el Menú Principal (ver <a href="trucos-need-for-speed-underground-pc.html">la guía completa de trucos de PC</a>), o elige <b>Todo abierto</b> en el launcher de <a href="/">NFSU.cc</a>.</p>
<h2>Preguntas frecuentes</h2>
<h3>¿Cuántos autos jugables tiene Need for Speed Underground?</h3>
<p>Need for Speed Underground (2003) tiene 20 autos tuner jugables, además de 15 vehículos de tráfico no jugables en la misma tabla <code>CarTypeInfo</code>.</p>
<h3>¿Qué autos son tracción integral (AWD) en Need for Speed Underground?</h3>
<p>Solo tres autos tienen tracción integral 50/50 en la física del juego: el 1999 Mitsubishi Eclipse GSX, el 2003 Subaru Impreza 2.5 RS y el 1999 Nissan Skyline R34 GTR. El 2003 Mitsubishi Lancer ES de esta entrega es tracción delantera.</p>
<h3>¿Cuándo se desbloquea el Nissan Skyline R34 GTR?</h3>
<p>El 1999 Nissan Skyline R34 GTR es el último auto que se desbloquea en Go Underground, al ganar el Evento #79. También puedes abrirlo en Carrera Rápida con el código <code>111skyline</code>.</p>
<script>
(function(){{
  var search = document.getElementById('car-search');
  var makeSel = document.getElementById('car-make');
  var pills = document.querySelectorAll('.hub-pill[data-dt]');
  var rows = document.querySelectorAll('#car-table tbody tr');
  var countEl = document.getElementById('car-count');
  var activeDt = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var mk = makeSel.value;
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!mk || r.dataset.make === mk) && (!activeDt || r.dataset.dt === activeDt);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Mostrando ' + vis + ' de ' + rows.length + ' autos';
  }}
  search.addEventListener('input', apply);
  makeSel.addEventListener('change', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeDt = this.dataset.dt;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
}})();
</script>
"""


def build_soundtrack_body(lang):
    rows_html = []
    for num, artist, title, album, zone in SOUNDTRACK:
        if lang == "en":
            zone_label = "Race (In-Game)" if zone == "IG" else "Menu (Front End)"
        else:
            zone_label = "Carrera (In-Game)" if zone == "IG" else "Menú (Front End)"
        z_cls = "tag-ig" if zone == "IG" else "tag-fe"
        rows_html.append(
            f'<tr data-zone="{zone}" data-q="{e((artist + " " + title + " " + album + " " + zone_label).lower())}">'
            f'<td>{num}</td>'
            f'<td><b>{e(title)}</b></td>'
            f'<td>{e(artist)}</td>'
            f'<td>{e(album)}</td>'
            f'<td><span class="tag {z_cls}">{e(zone_label)}</span></td>'
            f'</tr>'
        )
    if lang == "en":
        return f"""
<h2>Full soundtrack included in the browser</h2>
<p>Every song below comes from the EA TRAX table inside <code>Speed.exe</code> (offset <code>0x2f4d08</code>) and streams straight from the original 2003 audio banks when you play on <a href="/">NFSU.cc</a>. Nothing is cut or replaced: you can still configure each track for Menus, Racing, Both or Off inside Options &gt; EA TRAX.</p>
<div class="stat-grid">
  <div class="stat-card"><b>26</b><span>Total EA TRAX songs</span></div>
  <div class="stat-card"><b>19</b><span>Default Race tracks (IG)</span></div>
  <div class="stat-card"><b>7</b><span>Default Menu tracks (FE)</span></div>
  <div class="stat-card"><b>3</b><span>NFS Exclusive recordings</span></div>
</div>
<h2>Complete Need for Speed Underground tracklist</h2>
<p>Search by artist, song title or album, or filter by default playback zone.</p>
<div class="hub-controls">
  <input id="trax-search" class="hub-search" type="search" placeholder="Search artist, song or album..." aria-label="Search soundtrack">
</div>
<div class="hub-pills" role="group" aria-label="Filter by playback zone">
  <button type="button" class="hub-pill" data-zone="" aria-pressed="true">All (26)</button>
  <button type="button" class="hub-pill" data-zone="IG" aria-pressed="false">Race / In-Game (19)</button>
  <button type="button" class="hub-pill" data-zone="FE" aria-pressed="false">Menu / Front End (7)</button>
</div>
<p id="trax-count" class="hub-count">Showing 26 of 26 tracks</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="trax-table">
    <thead>
      <tr><th>#</th><th>Song</th><th>Artist</th><th>Album</th><th>Default Playback</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>How EA TRAX splits menus and races</h2>
<p>By default, Need for Speed Underground plays hip-hop tracks in the garage and menus (<code>FE</code>), led by Lil Jon &amp; the Eastside Boyz ("Get Low"), T.I. ("24's") and three tracks recorded specifically for the game by Mystikal, Nate Dogg and Petey Pablo. Once a race starts, EA TRAX switches to the 19 rock, metal and breakbeat tracks (<code>IG</code>), including Overseer, The Crystal Method, Static-X, Rob Zombie and Story of the Year.</p>
<h2>Frequently asked questions</h2>
<h3>Does NFSU.cc include "Get Low" and the full 2003 soundtrack?</h3>
<p>Yes. All 26 original EA TRAX songs from the 2003 PC release are included and play through the browser's audio engine. Click or press any key on the page once so your browser unlocks audio playback.</p>
<h3>Can I play menu songs during races?</h3>
<p>Yes. Open <b>Options &gt; EA TRAX</b> in the game menu to set any of the 26 tracks to Menu, Race, Everywhere or Off, or toggle sequential vs. random playback.</p>
<h3>Which songs were Need for Speed Underground exclusives?</h3>
<p>Three tracks in <code>Speed.exe</code> are tagged "Need for Speed Exclusive": Mystikal's "Smashing the Gas (Get Faster)", Nate Dogg's "Keep It Coming" and Petey Pablo's "Need For Speed".</p>
<script>
(function(){{
  var search = document.getElementById('trax-search');
  var pills = document.querySelectorAll('.hub-pill[data-zone]');
  var rows = document.querySelectorAll('#trax-table tbody tr');
  var countEl = document.getElementById('trax-count');
  var activeZone = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!activeZone || r.dataset.zone === activeZone);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Showing ' + vis + ' of ' + rows.length + ' tracks';
  }}
  search.addEventListener('input', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeZone = this.dataset.zone;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
}})();
</script>
"""
    return f"""
<h2>Soundtrack original completo en el navegador</h2>
<p>Cada canción de la tabla viene directo del índice EA TRAX dentro de <code>Speed.exe</code> (offset <code>0x2f4d08</code>) y suena desde los bancos de audio originales de 2003 cuando juegas en <a href="/">NFSU.cc</a>. No falta ninguna pista: igual que en PC, puedes configurar cada canción para Menú, Carrera, Ambos o Apagada en Opciones &gt; EA TRAX.</p>
<div class="stat-grid">
  <div class="stat-card"><b>26</b><span>Canciones en EA TRAX</span></div>
  <div class="stat-card"><b>19</b><span>Temas de carrera (IG)</span></div>
  <div class="stat-card"><b>7</b><span>Temas de menú (FE)</span></div>
  <div class="stat-card"><b>3</b><span>Temas exclusivos de NFS</span></div>
</div>
<h2>Lista completa del soundtrack de Need for Speed Underground</h2>
<p>Busca por artista, canción o álbum, o filtra según dónde suena por defecto.</p>
<div class="hub-controls">
  <input id="trax-search" class="hub-search" type="search" placeholder="Buscar artista, canción o álbum..." aria-label="Buscar soundtrack">
</div>
<div class="hub-pills" role="group" aria-label="Filtrar por zona">
  <button type="button" class="hub-pill" data-zone="" aria-pressed="true">Todas (26)</button>
  <button type="button" class="hub-pill" data-zone="IG" aria-pressed="false">Carrera / In-Game (19)</button>
  <button type="button" class="hub-pill" data-zone="FE" aria-pressed="false">Menú / Front End (7)</button>
</div>
<p id="trax-count" class="hub-count">Mostrando 26 de 26 canciones</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="trax-table">
    <thead>
      <tr><th>#</th><th>Canción</th><th>Artista</th><th>Álbum</th><th>Dónde suena</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>Cómo divide EA TRAX los menús y las carreras</h2>
<p>Por defecto, Need for Speed Underground reproduce hip-hop en el garaje y los menús (<code>FE</code>), encabezado por Lil Jon &amp; the Eastside Boyz ("Get Low"), T.I. ("24's") y tres temas grabados en exclusiva para el juego por Mystikal, Nate Dogg y Petey Pablo. Al arrancar una carrera, EA TRAX cambia a los 19 temas de rock, metal y electrónica (<code>IG</code>), como Overseer, The Crystal Method, Static-X, Rob Zombie y Story of the Year.</p>
<h2>Preguntas frecuentes</h2>
<h3>¿NFSU.cc incluye "Get Low" y el soundtrack completo de 2003?</h3>
<p>Sí. Las 26 canciones originales de EA TRAX de la versión de PC de 2003 están incluidas y suenan en el motor de audio del navegador. Solo haz un clic o presiona una tecla para que el navegador active el sonido.</p>
<h3>¿Puedo escuchar las canciones del menú durante las carreras?</h3>
<p>Sí. Entra a <b>Opciones &gt; EA TRAX</b> dentro del juego para elegir si cada una de las 26 canciones suena en Menú, Carrera, Ambos o Apagada, y alternar entre orden secuencial o aleatorio.</p>
<h3>¿Qué canciones fueron exclusivas de Need for Speed Underground?</h3>
<p>Tres temas aparecen marcados como "Need for Speed Exclusive" en <code>Speed.exe</code>: "Smashing the Gas (Get Faster)" de Mystikal, "Keep It Coming" de Nate Dogg y "Need For Speed" de Petey Pablo.</p>
<script>
(function(){{
  var search = document.getElementById('trax-search');
  var pills = document.querySelectorAll('.hub-pill[data-zone]');
  var rows = document.querySelectorAll('#trax-table tbody tr');
  var countEl = document.getElementById('trax-count');
  var activeZone = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!activeZone || r.dataset.zone === activeZone);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Mostrando ' + vis + ' de ' + rows.length + ' canciones';
  }}
  search.addEventListener('input', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeZone = this.dataset.zone;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
}})();
</script>
"""


def build_cheats_body(lang):
    cat_labels = {
        "en": {"tracks": "Tracks & Modes", "upgrades": "Upgrades & Physics", "presets": "Special Presets", "cars": "Cars"},
        "es": {"tracks": "Pistas y Modos", "upgrades": "Mejoras y Física", "presets": "Autos Especiales", "cars": "Autos"},
    }[lang]
    copy_txt = "Copy" if lang == "en" else "Copiar"
    copied_txt = "Copied" if lang == "en" else "Copiado"
    rows_html = []
    for code, cat, eff_en, eff_es in CHEATS:
        eff = eff_en if lang == "en" else eff_es
        clab = cat_labels[cat]
        rows_html.append(
            f'<tr data-cat="{cat}" data-q="{e((code + " " + eff + " " + clab).lower())}">'
            f'<td class="code-cell"><code>{e(code)}</code></td>'
            f'<td>{e(eff)}</td>'
            f'<td><span class="tag">{e(clab)}</span></td>'
            f'<td><button type="button" class="copy-btn" data-code="{e(code)}">{copy_txt}</button></td>'
            f'</tr>'
        )
    if lang == "en":
        return f"""
<h2>How to enter cheat codes on PC and NFSU.cc</h2>
<p>Follow these exact steps inside Need for Speed Underground (no text box appears on screen while you type):</p>
<ol>
  <li>Open the <b>Main Menu</b>.</li>
  <li>Select <b>Statistics</b>.</li>
  <li>Press <kbd>Delete</kbd> (or <kbd>Backspace</kbd>) to return to the Main Menu and arm the code listener.</li>
  <li>Type any code from the table below in lowercase letters, then press <kbd>Enter</kbd>.</li>
</ol>
<p>If accepted, the game unlocks the item for Quick Race and Customize immediately. Note that <code>Speed.exe</code> does not contain a money cheat or Level 3 performance cheat in its <code>EasterEggs</code> table; if you want every career car and upgrade open on <a href="/">NFSU.cc</a>, choose <b>Career &gt; All open</b> in the launcher.</p>
<h2>All 33 verified Need for Speed Underground PC cheat codes</h2>
<p>Extracted directly from <code>pc/Speed.exe</code> (29 codes at offset <code>0x306918</code> plus 4 artist preset codes at <code>0x2b88dc</code>). Click <b>Copy</b> on any row to copy the exact string.</p>
<div class="hub-controls">
  <input id="cheat-search" class="hub-search" type="search" placeholder="Search code, car or reward..." aria-label="Search cheat codes">
</div>
<div class="hub-pills" role="group" aria-label="Filter by category">
  <button type="button" class="hub-pill" data-cat="" aria-pressed="true">All (33)</button>
  <button type="button" class="hub-pill" data-cat="tracks" aria-pressed="false">Tracks &amp; Modes (4)</button>
  <button type="button" class="hub-pill" data-cat="upgrades" aria-pressed="false">Upgrades &amp; Physics (4)</button>
  <button type="button" class="hub-pill" data-cat="presets" aria-pressed="false">Special Presets (5)</button>
  <button type="button" class="hub-pill" data-cat="cars" aria-pressed="false">Cars (20)</button>
</div>
<p id="cheat-count" class="hub-count">Showing 33 of 33 codes</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="cheat-table">
    <thead>
      <tr><th>Code</th><th>Effect</th><th>Category</th><th>Action</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>Frequently asked questions</h2>
<h3>Why are some popular internet codes missing from this list?</h3>
<p>Codes like <code>regmebaby</code> or <code>opendoors</code> belong to Need for Speed Underground 2 (2004), not Underground 1 (2003). The 33 codes above are the complete set actually compiled into <code>Speed.exe</code>.</p>
<h3>Do these cheat codes work in the browser on NFSU.cc?</h3>
<p>Yes. Because NFSU.cc runs a static WebAssembly recompilation of the original 2003 <code>Speed.exe</code>, the exact same <code>EasterEggs</code> handler listens for all 33 codes on the Main Menu after exiting Statistics.</p>
<h3>Is there a cheat code for Level 3 upgrades or infinite cash?</h3>
<p>No. The PC <code>EasterEggs</code> table only includes Level 1 and Level 2 performance parts (<code>allmylvloneparts</code>, <code>allmylvl2parts</code>) and Level 2 visual parts (<code>seemylvl2parts</code>). Level 3 upgrades and Junkman unique parts are earned in Go Underground career mode.</p>
<script>
(function(){{
  var search = document.getElementById('cheat-search');
  var pills = document.querySelectorAll('.hub-pill[data-cat]');
  var rows = document.querySelectorAll('#cheat-table tbody tr');
  var countEl = document.getElementById('cheat-count');
  var activeCat = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!activeCat || r.dataset.cat === activeCat);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Showing ' + vis + ' of ' + rows.length + ' codes';
  }}
  search.addEventListener('input', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeCat = this.dataset.cat;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
  document.getElementById('cheat-table').addEventListener('click', function(ev){{
    var btn = ev.target.closest('.copy-btn');
    if (!btn) return;
    var code = btn.dataset.code;
    function mark(){{
      btn.textContent = '{copied_txt}';
      btn.classList.add('copied');
      setTimeout(function(){{ btn.textContent = '{copy_txt}'; btn.classList.remove('copied'); }}, 1400);
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(code).then(mark);
    }} else {{
      var ta = document.createElement('textarea');
      ta.value = code; document.body.appendChild(ta); ta.select();
      try {{ document.execCommand('copy'); }} catch (err) {{}}
      document.body.removeChild(ta); mark();
    }}
  }});
}})();
</script>
"""
    return f"""
<h2>Cómo ingresar los trucos en PC y en NFSU.cc</h2>
<p>Sigue estos pasos exactos dentro de Need for Speed Underground (no aparece ningún cuadro de texto en pantalla al escribir):</p>
<ol>
  <li>Entra al <b>Menú Principal</b> (Main Menu).</li>
  <li>Entra a <b>Estadísticas</b> (Statistics).</li>
  <li>Presiona <kbd>Supr</kbd> / <kbd>Delete</kbd> (o <kbd>Retroceso</kbd> / <kbd>Backspace</kbd>) para volver al Menú Principal.</li>
  <li>Escribe cualquiera de los códigos de abajo en minúsculas y presiona <kbd>Enter</kbd>.</li>
</ol>
<p>Si el código entra bien, el juego desbloquea el contenido al instante para Carrera Rápida y Personalizar. Toma en cuenta que <code>Speed.exe</code> no tiene truco de dinero infinito ni de piezas Nivel 3; si quieres todo abierto en <a href="/">NFSU.cc</a>, elige <b>Carrera &gt; Todo abierto</b> en el launcher.</p>
<h2>Los 33 trucos verificados de Need for Speed Underground para PC</h2>
<p>Extraídos directo de <code>pc/Speed.exe</code> (29 códigos en el offset <code>0x306918</code> más 4 códigos de autos especiales en <code>0x2b88dc</code>). Haz clic en <b>Copiar</b> en cualquier fila para copiar el texto exacto.</p>
<div class="hub-controls">
  <input id="cheat-search" class="hub-search" type="search" placeholder="Buscar código, auto o recompensa..." aria-label="Buscar trucos">
</div>
<div class="hub-pills" role="group" aria-label="Filtrar por categoría">
  <button type="button" class="hub-pill" data-cat="" aria-pressed="true">Todos (33)</button>
  <button type="button" class="hub-pill" data-cat="tracks" aria-pressed="false">Pistas y Modos (4)</button>
  <button type="button" class="hub-pill" data-cat="upgrades" aria-pressed="false">Mejoras y Física (4)</button>
  <button type="button" class="hub-pill" data-cat="presets" aria-pressed="false">Autos Especiales (5)</button>
  <button type="button" class="hub-pill" data-cat="cars" aria-pressed="false">Autos (20)</button>
</div>
<p id="cheat-count" class="hub-count">Mostrando 33 de 33 códigos</p>
<div class="hub-table-wrap">
  <table class="hub-table" id="cheat-table">
    <thead>
      <tr><th>Código</th><th>Efecto</th><th>Categoría</th><th>Acción</th></tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</div>
<h2>Preguntas frecuentes</h2>
<h3>¿Por qué faltan códigos famosos de internet como regmebaby?</h3>
<p>Códigos como <code>regmebaby</code> o <code>opendoors</code> pertenecen a Need for Speed Underground 2 (2004), no a Underground 1 (2003). Los 33 códigos de esta lista son el conjunto exacto compilado dentro de <code>Speed.exe</code>.</p>
<h3>¿Funcionan estos trucos en el navegador en NFSU.cc?</h3>
<p>Sí. Como NFSU.cc ejecuta una recompilación estática a WebAssembly del <code>Speed.exe</code> original de 2003, el mismo manejador <code>EasterEggs</code> escucha los 33 códigos en el Menú Principal tras salir de Estadísticas.</p>
<h3>¿Existe un truco para piezas Nivel 3 o dinero infinito?</h3>
<p>No. La tabla <code>EasterEggs</code> de PC solo incluye piezas de rendimiento Nivel 1 y Nivel 2 (<code>allmylvloneparts</code>, <code>allmylvl2parts</code>) y piezas visuales Nivel 2 (<code>seemylvl2parts</code>). Las piezas Nivel 3 y las mejoras únicas de Junkman se ganan en el modo carrera Go Underground.</p>
<script>
(function(){{
  var search = document.getElementById('cheat-search');
  var pills = document.querySelectorAll('.hub-pill[data-cat]');
  var rows = document.querySelectorAll('#cheat-table tbody tr');
  var countEl = document.getElementById('cheat-count');
  var activeCat = '';
  function apply(){{
    var q = search.value.trim().toLowerCase();
    var vis = 0;
    for (var i = 0; i < rows.length; i++){{
      var r = rows[i];
      var ok = (!q || r.dataset.q.indexOf(q) !== -1) && (!activeCat || r.dataset.cat === activeCat);
      r.hidden = !ok;
      if (ok) vis++;
    }}
    countEl.textContent = 'Mostrando ' + vis + ' de ' + rows.length + ' códigos';
  }}
  search.addEventListener('input', apply);
  for (var j = 0; j < pills.length; j++){{
    pills[j].addEventListener('click', function(){{
      activeCat = this.dataset.cat;
      for (var k = 0; k < pills.length; k++) pills[k].setAttribute('aria-pressed', pills[k] === this ? 'true' : 'false');
      apply();
    }});
  }}
  document.getElementById('cheat-table').addEventListener('click', function(ev){{
    var btn = ev.target.closest('.copy-btn');
    if (!btn) return;
    var code = btn.dataset.code;
    function mark(){{
      btn.textContent = '{copied_txt}';
      btn.classList.add('copied');
      setTimeout(function(){{ btn.textContent = '{copy_txt}'; btn.classList.remove('copied'); }}, 1400);
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(code).then(mark);
    }} else {{
      var ta = document.createElement('textarea');
      ta.value = code; document.body.appendChild(ta); ta.select();
      try {{ document.execCommand('copy'); }} catch (err) {{}}
      document.body.removeChild(ta); mark();
    }}
  }});
}})();
</script>
"""


def build_career_body(lang):
    if lang == "en":
        return """
<h2>Go Underground structure at a glance</h2>
<p>Verified from the game's <code>EventDesc</code> table (<code>FrontB.lzc</code>, chunk <code>0x34a02</code>), Go Underground opens with an intro daydream race (Event #0) that unlocks the 5 starter cars, then progresses through 111 main career events (IDs #1 to #112, with ID #85 unused) culminating against Eddie (#112), followed by a final bonus duel against Melissa (#113).</p>
<div class="stat-grid">
  <div class="stat-card"><b>111 + 1</b><span>Main events + Melissa finale</span></div>
  <div class="stat-card"><b>6</b><span>Race modes</span></div>
  <div class="stat-card"><b>12</b><span>Multi-race Tournaments</span></div>
  <div class="stat-card"><b>313</b><span>Configured rival entries</span></div>
</div>
<h2>All 6 race modes in Go Underground</h2>
<p>Every event after Event #0 falls into one of six modes in <code>EventDesc</code>. Twelve of the Circuit events are multi-stage <b>Tournaments</b> (3 consecutive races scored by points).</p>
<div class="hub-table-wrap">
  <table class="hub-table">
    <thead>
      <tr><th>Race Mode</th><th>Events</th><th>Rules &amp; Win Condition</th></tr>
    </thead>
    <tbody>
      <tr><td><b>Circuit</b> (incl. 12 Tournaments)</td><td>28</td><td>Closed-loop street race of 2 to 6 laps against up to 3 rivals. Tournaments sum points across 3 races.</td></tr>
      <tr><td><b>Drag</b></td><td>23</td><td>Straight-line manual shifting race. Hit green Perfect Shifts, dodge traffic and avoid blowing your engine.</td></tr>
      <tr><td><b>Sprint</b></td><td>23</td><td>Point-to-point race across Olympic City. First car across the finish line wins.</td></tr>
      <tr><td><b>Drift</b></td><td>19</td><td>Closed drift arena scored on slide angle, speed and outer-zone proximity. Beat the rival point totals.</td></tr>
      <tr><td><b>Lap Knockout</b></td><td>12</td><td>3-lap circuit where the last-place driver is eliminated at the end of each lap until one car remains.</td></tr>
      <tr><td><b>Time Trial</b></td><td>7</td><td>Solo timed runs (including TJ's unique-part challenges) against a target clock.</td></tr>
    </tbody>
  </table>
</div>
<h2>Key bosses and story milestones</h2>
<p>Progressing through Olympic City pits you against ranked street racers (Jose, Klutch, Kurt, Chad and Todd) before four defining boss events verified in <code>EventDesc</code>:</p>
<div class="hub-table-wrap">
  <table class="hub-table">
    <thead>
      <tr><th>Event</th><th>Boss</th><th>Mode</th><th>Payout (Easy / Med / Hard)</th><th>Significance</th></tr>
    </thead>
    <tbody>
      <tr><td><b>#78</b></td><td><b>Samantha</b></td><td>Sprint (1v1)</td><td>$2,000 / $4,000 / $6,000</td><td>Story turning point after TJ takes Samantha's Civic; awards a unique widebody kit unlock.</td></tr>
      <tr><td><b>#111</b></td><td><b>TJ</b></td><td>Circuit, 5 laps (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Reclaim Samantha's modified Honda Civic Si and earn a Junkman unique upgrade.</td></tr>
      <tr><td><b>#112</b></td><td><b>Eddie</b></td><td>Sprint (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Leader of the Eastsiders in his custom Nissan Skyline R34 GTR; clears the 111-event main ladder.</td></tr>
      <tr><td><b>#113</b></td><td><b>Melissa</b></td><td>Circuit, 4 laps (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Final secret challenge against Melissa's Nissan 350Z; triggers the ending movie (<code>19_FIN</code>).</td></tr>
    </tbody>
  </table>
</div>
<h2>Reputation, Style Points and visual rating</h2>
<p>Winning races earns cash, while jumps, powerslides, drafting, near misses and clean laps earn <b>Style Points</b> (tracked at <code>0x758ad4</code> in the save profile). Higher visual car ratings (1 to 5 stars from body kits, spoilers, rims, paint, neon and vinyls) multiply your Style Points per race. Reaching Style Point thresholds unlocks magazine covers, sponsor vinyls and visual parts, and magazine events require a minimum star rating to enter.</p>
<h2>Tips for clearing Hard difficulty</h2>
<ul>
  <li><b>Upgrade performance before cosmetics on tight cash</b>: save visual spending for star-rating gates, and install TJ's unique Junkman parts on the car you plan to keep for late events (see <a href="need-for-speed-underground-car-list.html">the complete 20-car list</a>).</li>
  <li><b>Use manual shifting only where it helps</b>: Drag forces manual shifting; on Circuit and Sprint, automatic keeps you focused on traffic and shortcuts.</li>
  <li><b>Back up your browser save</b>: on <a href="/">NFSU.cc</a>, career saves live in your browser. Use <b>Options &gt; Saves &gt; Save a backup</b> in the launcher to export your <code>.ugd</code> profile at any time.</li>
</ul>
<h2>Frequently asked questions</h2>
<h3>How many events are in Need for Speed Underground career mode?</h3>
<p>Go Underground has 111 main career events (ending with Eddie at Event #112, since Event ID #85 is unused in the data table), preceded by the intro race (Event #0) and followed by the final challenge against Melissa (Event #113).</p>
<h3>Who is the final boss of Need for Speed Underground?</h3>
<p>Eddie is the final boss of the main 111-event Underground ladder (Event #112, Sprint), and Melissa is the secret final challenger immediately afterward in Event #113 (4-lap Circuit in a Nissan 350Z).</p>
<h3>How do you get Unique (Junkman) upgrades?</h3>
<p>Unique upgrades are rewarded by clearing specific timed challenges and boss races given by Samantha and TJ during Go Underground. Each unique part installs permanently on the car you are currently driving, so switch to your main endgame car before claiming late-game uniques.</p>
"""
    return """
<h2>Estructura de Go Underground de un vistazo</h2>
<p>Verificado en la tabla <code>EventDesc</code> del juego (<code>FrontB.lzc</code>, chunk <code>0x34a02</code>), Go Underground abre con una carrera introductoria (Evento #0) que desbloquea los 5 autos iniciales, avanza por 111 eventos principales (IDs #1 a #112, ya que el ID #85 no se usa) hasta enfrentar a Eddie (#112), y cierra con un duelo final contra Melissa (#113).</p>
<div class="stat-grid">
  <div class="stat-card"><b>111 + 1</b><span>Eventos principales + final Melissa</span></div>
  <div class="stat-card"><b>6</b><span>Modos de carrera</span></div>
  <div class="stat-card"><b>12</b><span>Torneos de 3 carreras</span></div>
  <div class="stat-card"><b>313</b><span>Rivales configurados</span></div>
</div>
<h2>Los 6 modos de carrera en Go Underground</h2>
<p>Cada evento después del Evento #0 pertenece a uno de seis modos en <code>EventDesc</code>. Doce de los eventos de Circuito son <b>Torneos</b> de varias etapas (3 carreras seguidas por puntos).</p>
<div class="hub-table-wrap">
  <table class="hub-table">
    <thead>
      <tr><th>Modo</th><th>Eventos</th><th>Reglas y condición de victoria</th></tr>
    </thead>
    <tbody>
      <tr><td><b>Circuito</b> (incl. 12 Torneos)</td><td>28</td><td>Carrera en circuito cerrado de 2 a 6 vueltas contra hasta 3 rivales. Los torneos suman puntos en 3 carreras.</td></tr>
      <tr><td><b>Arrancones (Drag)</b></td><td>23</td><td>Recta con cambios manuales obligatorios. Clava cambios perfectos en verde, esquiva tráfico y no revientes el motor.</td></tr>
      <tr><td><b>Sprint</b></td><td>23</td><td>Carrera punto a punto por Olympic City. Gana el primero en cruzar la meta.</td></tr>
      <tr><td><b>Drift</b></td><td>19</td><td>Pista cerrada de derrape puntuada por ángulo, velocidad y zona exterior. Supera el puntaje de los rivales.</td></tr>
      <tr><td><b>Eliminación (Lap Knockout)</b></td><td>12</td><td>Circuito de 3 vueltas donde el último lugar queda eliminado al cierre de cada vuelta hasta quedar uno.</td></tr>
      <tr><td><b>Contrarreloj (Time Trial)</b></td><td>7</td><td>Carreras en solitario contra el reloj (incluidos los retos de mejoras únicas de TJ).</td></tr>
    </tbody>
  </table>
</div>
<h2>Jefes clave y momentos de la historia</h2>
<p>Subir en el ranking de Olympic City te enfrenta a rivales con nombre (Jose, Klutch, Kurt, Chad y Todd) antes de los cuatro duelos de jefe verificados en <code>EventDesc</code>:</p>
<div class="hub-table-wrap">
  <table class="hub-table">
    <thead>
      <tr><th>Evento</th><th>Jefe</th><th>Modo</th><th>Premio (Fácil / Medio / Difícil)</th><th>Importancia</th></tr>
    </thead>
    <tbody>
      <tr><td><b>#78</b></td><td><b>Samantha</b></td><td>Sprint (1v1)</td><td>$2,000 / $4,000 / $6,000</td><td>Punto de quiebre tras perder su Civic ante TJ; desbloquea un kit widebody único.</td></tr>
      <tr><td><b>#111</b></td><td><b>TJ</b></td><td>Circuito, 5 vueltas (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Recupera el Honda Civic Si modificado de Samantha y gana una mejora única de Junkman.</td></tr>
      <tr><td><b>#112</b></td><td><b>Eddie</b></td><td>Sprint (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Líder de los Eastsiders en su Nissan Skyline R34 GTR; cierra la escalera principal de 111 eventos.</td></tr>
      <tr><td><b>#113</b></td><td><b>Melissa</b></td><td>Circuito, 4 vueltas (1v1)</td><td>$7,500 / $10,000 / $12,500</td><td>Reto secreto final contra el Nissan 350Z de Melissa; activa la cinemática final (<code>19_FIN</code>).</td></tr>
    </tbody>
  </table>
</div>
<h2>Reputación, Style Points y calificación visual</h2>
<p>Ganar carreras da dinero, mientras que saltos, derrapes, rebufo, rebases cerrados y vueltas limpias suman <b>Style Points</b> (guardados en <code>0x758ad4</code> en tu perfil). Subir las estrellas visuales de tu auto (de 1 a 5 estrellas con carrocería, alerones, rines, pintura, neón y vinilos) multiplica los Style Points ganados en cada carrera. Alcanzar metas de Style Points desbloquea portadas de revista, vinilos de patrocinador y piezas visuales, y las portadas exigen un mínimo de estrellas para competir.</p>
<h2>Consejos para pasar el modo Difícil</h2>
<ul>
  <li><b>Prioriza rendimiento antes que estética cuando falte dinero</b>: guarda el gasto visual para las portadas de revista e instala las mejoras únicas de TJ en el auto que planeas llevar al final (ver <a href="lista-autos-need-for-speed-underground.html">la lista completa de 20 autos</a>).</li>
  <li><b>Usa cambios manuales solo donde conviene</b>: Drag exige caja manual; en Circuito y Sprint, la automática te deja concentrarte en el tráfico y los atajos.</li>
  <li><b>Respalda tu partida del navegador</b>: en <a href="/">NFSU.cc</a> tus partidas se guardan localmente. Usa <b>Opciones &gt; Partidas &gt; Guardar copia</b> en el launcher para exportar tu archivo <code>.ugd</code> cuando quieras.</li>
</ul>
<h2>Preguntas frecuentes</h2>
<h3>¿Cuántos eventos tiene el modo carrera de Need for Speed Underground?</h3>
<p>Go Underground tiene 111 eventos principales (terminando con Eddie en el Evento #112, ya que el ID #85 no se usa en la tabla de datos), precedidos por la carrera introductoria (Evento #0) y seguidos del reto final contra Melissa (Evento #113).</p>
<h3>¿Quién es el jefe final de Need for Speed Underground?</h3>
<p>Eddie es el jefe final de la escalera principal de 111 eventos (Evento #112, Sprint), y Melissa es la retadora final secreta justo después en el Evento #113 (Circuito de 4 vueltas en su Nissan 350Z).</p>
<h3>¿Cómo se consiguen las mejoras Únicas (Junkman)?</h3>
<p>Las mejoras únicas se obtienen al ganar retos contrarreloj y carreras especiales de Samantha y TJ durante Go Underground. Cada mejora única se instala de forma permanente en el auto que estás manejando en ese momento, así que cambia a tu auto principal antes de reclamar las últimas.</p>
"""


FAQS = {
    "cars": {
        "en": [
            ("How many playable cars are in Need for Speed Underground?", "There are 20 playable tuner cars in Need for Speed Underground (2003), plus 15 non-playable traffic vehicles stored in the same CarTypeInfo table."),
            ("Which cars are AWD in Need for Speed Underground?", "Three cars use an all-wheel-drive 50/50 torque split in the game's physics table: the 1999 Mitsubishi Eclipse GSX, the 2003 Subaru Impreza 2.5 RS and the 1999 Nissan Skyline R34 GTR. The 2003 Mitsubishi Lancer ES in this game is front-wheel drive."),
            ("When do you unlock the Nissan Skyline R34 GTR?", "The 1999 Nissan Skyline R34 GTR is the last car unlocked in Go Underground career mode, awarded after winning Event #79. You can also unlock it in Quick Race with the code 111skyline."),
        ],
        "es": [
            ("¿Cuántos autos jugables tiene Need for Speed Underground?", "Need for Speed Underground (2003) tiene 20 autos tuner jugables, además de 15 vehículos de tráfico no jugables en la misma tabla CarTypeInfo."),
            ("¿Qué autos son tracción integral (AWD) en Need for Speed Underground?", "Solo tres autos tienen tracción integral 50/50 en la física del juego: el 1999 Mitsubishi Eclipse GSX, el 2003 Subaru Impreza 2.5 RS y el 1999 Nissan Skyline R34 GTR. El 2003 Mitsubishi Lancer ES de esta entrega es tracción delantera."),
            ("¿Cuándo se desbloquea el Nissan Skyline R34 GTR?", "El 1999 Nissan Skyline R34 GTR es el último auto que se desbloquea en Go Underground, al ganar el Evento #79. También puedes abrirlo en Carrera Rápida con el código 111skyline."),
        ],
    },
    "soundtrack": {
        "en": [
            ("Does NFSU.cc include 'Get Low' and the full 2003 soundtrack?", "Yes. All 26 original EA TRAX songs from the 2003 PC release are included and play through the browser's audio engine. Click or press any key on the page once so your browser unlocks audio playback."),
            ("Can I play menu songs during races?", "Yes. Open Options > EA TRAX in the game menu to set any of the 26 tracks to Menu, Race, Everywhere or Off, or toggle sequential vs. random playback."),
            ("Which songs were Need for Speed Underground exclusives?", "Three tracks in Speed.exe are tagged 'Need for Speed Exclusive': Mystikal's 'Smashing the Gas (Get Faster)', Nate Dogg's 'Keep It Coming' and Petey Pablo's 'Need For Speed'."),
        ],
        "es": [
            ("¿NFSU.cc incluye 'Get Low' y el soundtrack completo de 2003?", "Sí. Las 26 canciones originales de EA TRAX de la versión de PC de 2003 están incluidas y suenan en el motor de audio del navegador. Solo haz un clic o presiona una tecla para que el navegador active el sonido."),
            ("¿Puedo escuchar las canciones del menú durante las carreras?", "Sí. Entra a Opciones > EA TRAX dentro del juego para elegir si cada una de las 26 canciones suena en Menú, Carrera, Ambos o Apagada, y alternar entre orden secuencial o aleatorio."),
            ("¿Qué canciones fueron exclusivas de Need for Speed Underground?", "Tres temas aparecen marcados como 'Need for Speed Exclusive' en Speed.exe: 'Smashing the Gas (Get Faster)' de Mystikal, 'Keep It Coming' de Nate Dogg y 'Need For Speed' de Petey Pablo."),
        ],
    },
    "cheats": {
        "en": [
            ("Why are some popular internet codes missing from this list?", "Codes like regmebaby or opendoors belong to Need for Speed Underground 2 (2004), not Underground 1 (2003). The 33 codes above are the complete set actually compiled into Speed.exe."),
            ("Do these cheat codes work in the browser on NFSU.cc?", "Yes. Because NFSU.cc runs a static WebAssembly recompilation of the original 2003 Speed.exe, the exact same EasterEggs handler listens for all 33 codes on the Main Menu after exiting Statistics."),
            ("Is there a cheat code for Level 3 upgrades or infinite cash?", "No. The PC EasterEggs table only includes Level 1 and Level 2 performance parts (allmylvloneparts, allmylvl2parts) and Level 2 visual parts (seemylvl2parts). Level 3 upgrades and Junkman unique parts are earned in Go Underground career mode."),
        ],
        "es": [
            ("¿Por qué faltan códigos famosos de internet como regmebaby?", "Códigos como regmebaby o opendoors pertenecen a Need for Speed Underground 2 (2004), no a Underground 1 (2003). Los 33 códigos de esta lista son el conjunto exacto compilado dentro de Speed.exe."),
            ("¿Funcionan estos trucos en el navegador en NFSU.cc?", "Sí. Como NFSU.cc ejecuta una recompilación estática a WebAssembly del Speed.exe original de 2003, el mismo manejador EasterEggs escucha los 33 códigos en el Menú Principal tras salir de Estadísticas."),
            ("¿Existe un truco para piezas Nivel 3 o dinero infinito?", "No. La tabla EasterEggs de PC solo incluye piezas de rendimiento Nivel 1 y Nivel 2 (allmylvloneparts, allmylvl2parts) y piezas visuales Nivel 2 (seemylvl2parts). Las piezas Nivel 3 y las mejoras únicas de Junkman se ganan en el modo carrera Go Underground."),
        ],
    },
    "career": {
        "en": [
            ("How many events are in Need for Speed Underground career mode?", "Go Underground has 111 main career events (ending with Eddie at Event #112, since Event ID #85 is unused in the data table), preceded by the intro race (Event #0) and followed by the final challenge against Melissa (Event #113)."),
            ("Who is the final boss of Need for Speed Underground?", "Eddie is the final boss of the main 111-event Underground ladder (Event #112, Sprint), and Melissa is the secret final challenger immediately afterward in Event #113 (4-lap Circuit in a Nissan 350Z)."),
            ("How do you get Unique (Junkman) upgrades?", "Unique upgrades are rewarded by clearing specific timed challenges and boss races given by Samantha and TJ during Go Underground. Each unique part installs permanently on the car you are currently driving, so switch to your main endgame car before claiming late-game uniques."),
        ],
        "es": [
            ("¿Cuántos eventos tiene el modo carrera de Need for Speed Underground?", "Go Underground tiene 111 eventos principales (terminando con Eddie en el Evento #112, ya que el ID #85 no se usa en la tabla de datos), precedidos por la carrera introductoria (Evento #0) y seguidos del reto final contra Melissa (Evento #113)."),
            ("¿Quién es el jefe final de Need for Speed Underground?", "Eddie es el jefe final de la escalera principal de 111 eventos (Evento #112, Sprint), y Melissa es la retadora final secreta justo después en el Evento #113 (Circuito de 4 vueltas en su Nissan 350Z)."),
            ("¿Cómo se consiguen las mejoras Únicas (Junkman)?", "Las mejoras únicas se obtienen al ganar retos contrarreloj y carreras especiales de Samantha y TJ durante Go Underground. Cada mejora única se instala de forma permanente en el auto que estás manejando en ese momento, así que cambia a tu auto principal antes de reclamar las últimas."),
        ],
    },
}

BODY_BUILDERS = {
    "cars": build_cars_body,
    "soundtrack": build_soundtrack_body,
    "cheats": build_cheats_body,
    "career": build_career_body,
}


def render_more_links(lang, skip_key):
    items = []
    for p in PAGES_META:
        if p["key"] == skip_key:
            continue
        items.append(
            f'<li><a href="{p["slug"][lang]}.html"><b>{e(p["title"][lang])}</b><span>{e(p["desc"][lang])}</span></a></li>'
        )
    if lang == "en":
        items.append(
            '<li><a href="play-need-for-speed-underground-online.html"><b>How to play Need for Speed Underground online in your browser</b><span>Open nfsu.cc, press Play and drive. First load size, saves and browsers.</span></a></li>'
        )
    else:
        items.append(
            '<li><a href="jugar-need-for-speed-underground-online.html"><b>Cómo jugar Need for Speed Underground online en tu navegador</b><span>Abre nfsu.cc, presiona Jugar y maneja. Peso de carga, partidas y navegadores.</span></a></li>'
        )
    return '<ul class="list">' + "".join(items) + "</ul>"


def render_page(lang, p):
    u = UI[lang]
    names = p["slug"]
    name = names[lang]
    other = "es" if lang == "en" else "en"
    title = p["title"][lang]
    desc = p["desc"][lang]
    alts = "".join('<link rel="alternate" hreflang="%s" href="%s">\n' % (l, url(l, names[l])) for l in LANGS)
    alts += '<link rel="alternate" hreflang="x-default" href="%s">\n' % url("en", names["en"])
    og_img = f"{SITE}/blog/img/{p['img']}"
    body_html = BODY_BUILDERS[p["key"]](lang).strip()
    more_html = render_more_links(lang, p["key"])

    inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / <a href="index.html">{u['guides']}</a></p>
<article>
<h1>{e(title)}</h1>
<p class="lead">{e(p['lead'][lang])}</p>
<p class="date"><time datetime="{DATE}">{u['updated']}</time></p>
{body_html}
<div class="cta"><a href="/">{e(p['cta'][lang])}</a></div>
</article>
<h2 class="more">{u['more']}</h2>
{more_html}"""

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": title,
                "description": desc,
                "inLanguage": lang,
                "datePublished": DATE,
                "dateModified": DATE,
                "image": og_img,
                "mainEntityOfPage": url(lang, name),
                "author": ORG,
                "publisher": ORG,
                "about": {"@type": "VideoGame", "name": "Need for Speed Underground", "url": SITE + "/"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "NFSU.cc", "item": SITE + "/"},
                    {"@type": "ListItem", "position": 2, "name": u["guides"], "item": url(lang, "index")},
                    {"@type": "ListItem", "position": 3, "name": title, "item": url(lang, name)},
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}}
                    for q, ans in FAQS[p["key"]][lang]
                ],
            },
        ],
    }

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#04121a">
<title>{e(title)} | NFS Underground Web</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url(lang, name)}">
{alts}<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:site_name" content="NFS Underground Web">
<meta property="og:url" content="{url(lang, name)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:alt" content="{e(title)}">
<meta property="og:locale" content="{'en_US' if lang == 'en' else 'es_MX'}">
<meta property="og:locale:alternate" content="{'es_MX' if lang == 'en' else 'en_US'}">
<meta property="article:published_time" content="{DATE}">
<meta property="article:modified_time" content="{DATE}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{og_img}">
<meta name="twitter:image:alt" content="{e(title)}">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96.png">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png">
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
<link rel="apple-touch-icon" sizes="180x180" href="/icon-180.png">
<link rel="alternate" type="application/atom+xml" title="NFS Underground Web Engineering Devlog" href="{SITE}/feed.xml">
<link rel="stylesheet" href="../blog.css">
<style>{EXTRA_CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body style="--pic: url(/blog/img/{p['pic']})">
<header class="top">
  <a class="logo" href="/"><img src="/launcher/v2/ui/logo.webp" alt="Need for Speed Underground" width="688" height="125"></a>
  <nav>
    <a href="index.html">{u['guides']}</a>
    <a href="/reverse-engineering/index.html">{'Ingeniería Inversa' if lang == 'es' else 'Reverse Engineering'}</a>
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


def build_player_hub():
    """Generate the 8 player hub HTML pages and return [(lang, slug, twin_slug, title, desc), ...]."""
    results = []
    for lang in LANGS:
        out_dir = os.path.join(W, "blog", lang)
        os.makedirs(out_dir, exist_ok=True)
        other = "es" if lang == "en" else "en"
        for p in PAGES_META:
            slug = p["slug"][lang]
            twin_slug = p["slug"][other]
            out_path = os.path.join(out_dir, slug + ".html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render_page(lang, p))
            results.append((lang, slug, twin_slug, p["title"][lang], p["desc"][lang]))
    return results


if __name__ == "__main__":
    built = build_player_hub()
    print(f"player_hub: generated {len(built)} pages ({len(CARS)} cars, {len(SOUNDTRACK)} tracks, {len(CHEATS)} cheats)")
