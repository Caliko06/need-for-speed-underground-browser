#!/usr/bin/env python3
"""Public Reverse Engineering Atlas (/re/), Engineering Devlog (/devlog/), Atom feed (/feed.xml),
and GEO compendiums (/llms.txt, /llms-full.txt) for https://nfsu.cc/.

Every technical claim cites real files, commits, sizes, or Speed.exe addresses from this repo.
URLs end in .html on purpose: Cloudflare R2 serves no directory index (only "/" is rewritten).
Every /re/ and /devlog/ article also ships a clean .md sibling linked via <link rel="alternate" type="text/markdown">.

Usage: python3 tools/build_re_devlog.py   (also called automatically by tools/build_blog.py)
"""
import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "web")
DOCS_RE = os.path.join(ROOT, "docs", "re")
SITE = "https://nfsu.cc"
REPO = "https://github.com/Caliko06/need-for-speed-underground-browser"
DATE = "2026-11-24"
ORG = {
    "@type": "Organization",
    "name": "NFSU.cc",
    "url": SITE + "/",
    "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png"},
}

RE_CATEGORIES = [
    ("Driving & Physics", "Física y manejo", ["physics", "accel", "tuning", "feel_patch_plan", "feel_probe_fix"]),
    ("Camera Systems", "Sistemas de cámara", ["camera", "camera_chase", "camera_speed", "camera_jump", "camera_crash"]),
    ("Rivals & Race AI", "Rivales e IA de carrera", ["rivals", "race_ai", "ai_stuck", "ai_draft", "ai_review2", "reset_causes"]),
    ("Traffic Simulation", "Simulación de tráfico", ["traffic", "traffic_limits", "traffic_react", "traffic_honks", "traffic_cap_plan"]),
    ("Tracks, Roads & Props", "Pistas, caminos y props", ["track", "roadid", "props"]),
    ("Rendering & Shaders", "Render y shaders (D3D9 / WebGPU)", ["render", "render_pc", "blur", "hitches"]),
    ("Audio & Soundtrack", "Audio y soundtrack", ["sound"]),
    ("Menus, Garage & Career Flow", "Menús, garaje y modo carrera", ["gameflow", "frontend_menu", "garage", "race_setup", "hud_input", "unlock", "mode_menu"]),
    ("Assets, Runtime & Shipping", "Assets, runtime y hosting", ["assets", "car_assets", "runtime", "misc", "public_pack", "hosting"]),
    ("RE Methodology", "Metodología de ingeniería inversa", ["systems_method", "coverage_method"]),
]

DEVLOG_POSTS = [
    dict(
        slug="production-crash-hardening-and-448mb-phone-wasm",
        date="2026-11-24",
        commits=["511830f", "921e827"],
        tags=["WebAssembly", "Memory", "WebGPU", "Production Telemetry"],
        title="Hunting a 50-Minute Browser OOM and Shrinking Mobile WASM to 448 MB",
        desc="How real production crash telemetry from r2:nfsu-crash uncovered a CPU vertex buffer leak, WebGPU format edge cases, and got Need for Speed Underground running inside a 448 MB mobile WebAssembly heap.",
        lead="Shipping a statically recompiled 2003 PC game to thousands of real browsers surfaces failure modes that desktop tests never hit. Here is what production telemetry caught and how two surgical patches fixed both long-session OOMs and low-RAM phone crashes.",
        files=["host/d3d9.c", "host/files.c", "host/main.c", "tools/recomp/build.py", "web/gpu.js", "web/boot.js", "web/audio.js", "web/saves.js"],
        body_md="""## What real browsers broke in production

Once `nfsu.cc` went live, every unhandled browser crash reported a small JSON payload to our Cloudflare R2 crash bucket (`r2:nfsu-crash`). Auditing real user sessions revealed two distinct classes of failure:

1. **Memory exhaustion on phones and long desktop sessions**: `speed_lite.wasm` previously requested a 640 MB initial heap, which caused iOS Safari and 4 GB Android devices to fail WebAssembly instantiation (`could not allocate memory`), while long 50-minute desktop sessions slowly accumulated CPU-side geometry memory.
2. **Browser API edge cases**: GPUs without `unorm8x4-bgra` vertex format support, browsers missing `Atomics.waitAsync`, `tsBuf.unmap()` races on timestamp queries, transient network drops during chunk/WASM fetches, and `IndexedDB` hangs on save boot.

## Cutting the 50-minute OOM and dropping `speed_lite.wasm` to 448 MB (`511830f`)

Three concrete changes eliminated the memory pressure without touching original 2003 gameplay or audio:

- **Freeing CPU-side `SmoothEnt` buffers after GPU upload (`host/d3d9.c`)**: On web builds, once smoothed vertex and index buffers are uploaded to WebGPU/WebGL 2, keeping the host-side CPU shadow copy around caused linear memory growth across races. Freeing them immediately after upload stopped the 50-minute OOM.
- **Lowering `speed_lite.wasm` heap from 640 MB to 448 MB (`tools/recomp/build.py`, `host/host.h`)**: `GUEST_MEM` on the lite build was tightened to 256 MB and total WASM memory to 448 MB, letting budget Android phones and iPhones allocate the module cleanly.
- **Tightening transient host allocations (`host/files.c`, `host/main.c`)**: Desktop block cache cap (`blk_cap`) was reduced from 256 MB to 128 MB, and the temporary PE image buffer (`pe`) is now freed immediately after Win32 import resolution completes.

## Hardening the WebGPU, audio, and network host (`921e827`)

- **WebGPU `unorm8x4-bgra` software fallback (`web/gpu.js`)**: Devices that reject `unorm8x4-bgra` vertex attributes now fall back cleanly instead of throwing during pipeline creation.
- **Guarded timestamp query unmap (`web/gpu.js`)**: Prevented invalid-state throws when `tsBuf.unmap()` raced with device teardown.
- **`Atomics.waitAsync` fallback (`web/boot.js`)**: Older browser engines without `Atomics.waitAsync` no longer abort worker startup.
- **Network retries and clean shutdown (`web/boot.js`, `host/files.c`)**: Fetch and WASM download paths retry transient failures, `IndexedDB` open calls have bounded timeouts (`web/saves.js`), audio degrades gracefully instead of crashing when autoplay/context fails (`web/audio.js`), and `ExitProcess(0)` closes cleanly.

## Takeaway for browser static recompilation

Emulators usually cap memory tightly up front; static recompilations inherit the original PC executable's allocation assumptions plus a host GPU translation layer. Pairing a lightweight crash beacon with strict CPU-shadow freeing after GPU upload is what makes a 2003 Windows binary survive real mobile browsers.
""",
    ),
    dict(
        slug="recompiler-dead-flags-chk-sp-fast-x87",
        date="2026-11-23",
        commits=["8444027", "69f51fb", "fc8ef2e"],
        tags=["Static Recompilation", "x86", "WebAssembly", "Compilers", "Difftest"],
        title="Static Recompiler Optimizations: Dead x86 Flag Pruning, CHK_SP Coalescing, and Fast x87",
        desc="How we cut generated C/WebAssembly overhead across 13,764 lifted x86 functions from Speed.exe using liveness-based flag pruning, stack-pointer check coalescing, and differential testing.",
        lead="Naive x86-to-C static recompilation spends most of its CPU budget updating EFLAGS nobody reads and bounds-checking ESP on every push and pop. Here is how tools/recomp/lift.py eliminates both while staying verified by difftest.py.",
        files=["tools/recomp/lift.py", "tools/recomp/build.py", "tools/recomp/abk.py", "tools/recomp/difftest.py", "host/rt.h"],
        body_md="""## The cost of faithful x86 lifting

`pc/Speed.exe` (3.18 MB, 2003 PC) contains **13,764 functions** lifted ahead of time into C by `tools/recomp/lift.py` and compiled to `web/out/speed.wasm` (42.31 MB uncompressed, ~11.1 MB brotli). In early builds, every arithmetic instruction computed `CF`, `ZF`, `SF`, `OF`, and `PF`, and every stack/memory access emitted a runtime bounds check.

## 1. Liveness-based dead guest flag pruning (`8444027`)

In x86 code, the vast majority of flag writes are overwritten by the next `add`, `sub`, `xor`, or `inc` before any conditional branch (`jcc`), `cmov`, `setcc`, or `adc`/`sbb` ever reads them.

- `tools/recomp/lift.py` and `tools/recomp/abk.py` now compute intra- and inter-procedural **flag liveness** (`FlagABI` argument and live-flag masks across direct `call_to(target)` edges).
- Instructions whose flag outputs are dead emit plain C integer math (`eax = eax + ecx;`) instead of flag-computing helper calls.
- Special control-flow edges (`popfd`, indirect calls, traps, and return boundaries) conservatively preserve live flag masks so semantics never drift.

## 2. `CHK_IMG` and straight-line `CHK_SP` coalescing (`69f51fb`, `fc8ef2e`)

Guest memory safety in `host/rt.h` prevents a bug in lifted x86 from corrupting the Emscripten host heap, but checking every individual stack slot inside a function prologue/epilogue is wasteful:

- **`CHK_IMG`**: Constant addresses known to lie inside the static PE image (`0x400000+`) bypass dynamic range checks.
- **`CHK_SP` coalescing**: Within any straight-line basic block (broken at loop targets and overlap-stream entries), `lift.py` tracks `esp` deltas (`sp_acc` / `sp_move`) and emits **one coalesced stack bounds check** covering the block's min/max stack excursion instead of one check per `push`/`pop`.
- **Cold trap path (`host/rt.h`)**: Bounds-check failure paths are marked cold so Clang/LLVM keeps the hot WebAssembly loop tight.

## 3. `RN_FAST_X87` verified against `RN_STRICT_X87` (`69f51fb`)

x87 floating-point stack emulation is a classic hotspot in 2003 PC racing physics (`physics.md`, `accel.md`). `host/rt.h` now splits x87 execution into:

- **`RN_FAST_X87`** for shipped game builds (fast native IEEE-754 doubles in WASM registers).
- **`RN_STRICT_X87`** for `tools/recomp/difftest.py` trace builds, allowing single-function differential verification (`RN_ONLY=<addr> tools/recomp/difftest.py`) against reference traces whenever a compiler pass changes.
""",
    ),
    dict(
        slug="zero-waste-webgpu-draw-pipeline-and-bc-textures",
        date="2026-11-23",
        commits=["deb8f28", "00e474c"],
        tags=["WebGPU", "WebGL2", "DirectX 9", "S3TC", "Graphics"],
        title="DirectX 9 to WebGPU & WebGL 2: Native BC1/2/3 Textures and a Zero-Waste Draw Pipeline",
        desc="Eliminating CPU texture decompression and per-draw bindGroup churn by keeping DXT1/3/5 textures compressed on the GPU and caching dynamic UBOs in host/d3d9.c and web/gpu.js.",
        lead="Translating a 2003 DirectX 9 renderer to WebGPU (with automatic WebGL 2 fallback) is easy to make correct and hard to make fast. Two rendering passes removed the biggest CPU and VRAM bottlenecks.",
        files=["host/d3d9.c", "host/gpu.c", "host/sm1.c", "web/gpu.js", "web/webgpu_gl.js"],
        body_md="""## Keeping DXT1/3/5 textures compressed as BC1/2/3 (`00e474c`)

Need for Speed Underground ships its car liveries, road surfaces, and Olympic City environment textures as DirectX DXT1, DXT3, and DXT5 blocks. Earlier browser builds decoded those blocks to uncompressed RGBA8 on the CPU before uploading them, multiplying VRAM usage by 4x to 8x and stalling frame times during streaming.

Commit `00e474c` introduced **`RN_S3TC`** end-to-end:

- **`host/d3d9.c`**: Detects hardware block-compression support and passes raw DXT1/3/5 mip bytes straight through the host GPU command stream without CPU decompression.
- **`web/gpu.js` (WebGPU)**: Requests `texture-compression-bc` when available and uploads directly to `bc1-rgba-unorm`, `bc2-rgba-unorm`, and `bc3-rgba-unorm` textures.
- **`web/webgpu_gl.js` (WebGL 2 fallback)**: Uses `WEBGL_compressed_texture_s3tc` (`compressedTexImage2D`) so browsers without WebGPU still get the same 4x-8x VRAM savings and zero-decode uploads.
- **Upload counters**: Boot logs track compressed vs uncompressed texture uploads so regressions are immediately visible.

## Zero-waste draw pipeline, compact dynamic UBO, and post `bindGroup` cache (`deb8f28`)

DirectX 9 games issue hundreds of small stateful draw calls per frame (changing a single transform matrix, light constant, or texture stage). In WebGPU, naively allocating a fresh uniform buffer or `GPUBindGroup` per draw call creates severe JS garbage-collection pressure.

Commit `deb8f28` overhauled `host/d3d9.c`, `host/gpu.c`, `host/sm1.c`, and `web/gpu.js`:

- **Compact dynamic UBO layout**: Packed shader uniforms tightly so each draw call slices a single pre-allocated dynamic uniform buffer via `setBindGroup(..., [dynamicOffset])`.
- **Zero-waste draw state**: Avoided redundant state writes and shader-constant re-uploads when consecutive draws share transforms or materials.
- **Post-process `bindGroup` cache**: Cached post-processing bind groups (bloom, motion blur, tone pass) instead of rebuilding them every frame.
""",
    ),
    dict(
        slug="adaptive-frame-time-quality-and-dual-wasm-builds",
        date="2026-11-22",
        commits=["40e6aff", "b9c9753", "e19daa6", "c8e94a4", "9545ee5"],
        tags=["Performance", "Mobile", "WebAssembly", "Telemetry"],
        title="One URL for Desktops and Phones: Frame-Time Quality Control and Dual WASM Builds",
        desc="How nfsu.cc measures its own 256-frame present ring, scales resolution and effects automatically via web/quality.js, ships a brotli speed_lite.wasm for phones, and never cuts the 2003 soundtrack.",
        lead="Users open nfsu.cc on everything from M4 Macs and RTX desktops to budget Android phones. Instead of forcing manual tuning, the page measures its own frame times and adapts live.",
        files=["host/d3d9.c", "web/stats.js", "web/quality.js", "web/mode.js", "tools/build_public.py", "tools/upload_r2.sh"],
        body_md="""## Always-on 256-frame present ring (`40e6aff`)

You cannot tune performance from guesswork. `host/d3d9.c` now maintains a lightweight ring buffer of the last **256 `Present()` intervals**, exposed to `web/stats.js`. Every windowed p50/p95 frame-time summary feeds both live diagnostics (`rnReport`) and crash telemetry lines so slow devices are immediately identifiable.

## Closed-loop frame-time quality controller (`b9c9753`, `c8e94a4`)

`web/quality.js` observes real measured frame times and steps down (or up) in a strict visual-preservation order:

`resolution -> motion blur -> post effects -> fps target -> quality tier`

- Measured tiers persist in `localStorage` (`rn_quality`) so repeat visits start smoothly.
- If a device stays above `p50 > 100 ms` across two windows even on `ultralite`, the UI surfaces a clean below-the-floor notice (`c8e94a4`) instead of silently freezing.
- On `ultralite`, **the full 2003 soundtrack is preserved** (`9545ee5`): cutting the music breaks the identity of Need for Speed Underground, so audio stays intact while pixels and post-FX scale.

## Shipping `speed_lite.wasm` alongside `speed.wasm` (`e19daa6`)

`tools/build_public.py` and `tools/upload_r2.sh` publish both `out/speed.wasm` (desktop) and `out/speed_lite.wasm` (phones/tablets) pre-compressed with **Brotli `-q 11 -w 24`** directly on Cloudflare R2, served with `Content-Encoding: br` and `Content-Type: application/wasm`. The browser downloads ~11 MB once and streams only the 2003 game chunks needed for the next screen.
""",
    ),
    dict(
        slug="reverse-engineering-44-subsystems-of-speed-exe",
        date="2026-11-24",
        commits=["9776828"],
        tags=["Reverse Engineering", "Ghidra", "Hopper", "AI Agents", "NFS Underground"],
        title="Opening the Complete Reverse Engineering Atlas of Speed.exe (44 Subsystems)",
        desc="Every verified x86 address, struct, state machine, and subsystem note from Need for Speed Underground (2003, Speed.exe) is now published as a searchable web atlas and LLM-ready Markdown corpus.",
        lead="Recompiling a 2003 binary without source code requires understanding how the game actually works inside. Today we are publishing all 44 reverse-engineering system notes from docs/re/ directly on nfsu.cc/re/.",
        files=["docs/re/README.md", "census/", "tools/recomp/patches_feel.py", "tools/recomp/patches_race.py", "tools/recomp/patches_render.py"],
        body_md="""## Why publish the full binary atlas

Most retro web ports are black boxes. `RE-NFSU` was built on an evidence-first rule: every claim about `Speed.exe` (md5 `b6b9232c55376b3c38c56aac1f8a121d`, base `0x400000`, 3.18 MB) must cite the exact address or bytes read in the binary, tagged **V** (verified in code/bytes), **I** (inferred), or **U** (open).

Across the repository, that effort produced:

- **44 subsystem monographs** in [`docs/re/`](https://nfsu.cc/re/index.html): car physics, acceleration curves, tuning math, chase/speed/jump/crash cameras, rival rubber-banding and AI stuck detection, traffic pools and reactions, track splines and Road IDs, DirectX 8/9 render pipeline, motion blur, sound banks, garage/career gameflow, and asset pack formats.
- **57 symbol census tables** (`census/names_*.tsv`) naming thousands of `Speed.exe` functions across every subsystem.
- **14 surgical patch modules** (`tools/recomp/patches_*.py`), where every patch cites the exact `Speed.exe` address it modifies while leaving **Original 2003** mode untouched.

## Built for humans and AI coding/search agents

Every page in the [Reverse Engineering Atlas](https://nfsu.cc/re/index.html) and [Engineering Devlog](https://nfsu.cc/devlog/index.html) is served both as semantic HTML (`TechArticle` JSON-LD) and as a clean **`.md` sibling** (`<link rel="alternate" type="text/markdown">`), indexed in [`/llms.txt`](https://nfsu.cc/llms.txt), [`/llms-full.txt`](https://nfsu.cc/llms-full.txt), and [`/feed.xml`](https://nfsu.cc/feed.xml).

Whether you are researching static recompilation (alongside projects like N64Recomp, XenonRecomp, and NFSU2Recomp), digging into Black Box's 2003 racing physics, or querying an AI assistant about how a 2003 x86 `.exe` runs on WebGPU, you can inspect the primary evidence directly.
""",
    ),
]


def esc(s):
    return html.escape(s, quote=True)


def inline_md(text, link_rewriter=None):
    """Convert inline markdown (`code`, **bold**, *italic*, [label](href)) safely."""
    tokens = []

    def stash(html_frag):
        idx = len(tokens)
        tokens.append(html_frag)
        return f"\x00T{idx}\x00"

    # Inline code first so brackets/asterisks inside code are never parsed
    def repl_code(m):
        return stash(f"<code>{esc(m.group(1))}</code>")

    text = re.sub(r"`([^`]+)`", repl_code, text)

    # Links [label](href)
    def repl_link(m):
        label, href = m.group(1), m.group(2).strip()
        if link_rewriter:
            href = link_rewriter(href)
        rel = ' rel="noopener"' if href.startswith("http") and not href.startswith(SITE) else ""
        return stash(f'<a href="{esc(href)}"{rel}>{inline_md(label, link_rewriter)}</a>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, text)

    # Escape remaining plain text
    text = esc(text)

    # Bold & italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)

    # Restore stashed tokens in reverse order so nested tokens (e.g. [`code`](url)) expand cleanly
    for idx in range(len(tokens) - 1, -1, -1):
        text = text.replace(f"\x00T{idx}\x00", tokens[idx])
    return text


def md_to_html(md_text, link_rewriter=None, drop_first_h1=True):
    """Clean stdlib Markdown-to-HTML converter supporting headings, tables, fenced code, lists, blockquotes, paragraphs."""
    lines = md_text.splitlines()
    out = []
    i = 0
    n = len(lines)
    dropped_h1 = False

    def is_table_sep(line):
        s = line.strip()
        return bool(re.match(r"^\|?[\s:-]+\|[\s|:-]*$", s))

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{esc(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{esc(chr(10).join(code_lines))}</code></pre>")
            continue

        # Headings
        hm = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if hm:
            lvl = len(hm.group(1))
            txt = hm.group(2).strip()
            if lvl == 1 and drop_first_h1 and not dropped_h1:
                dropped_h1 = True
                i += 1
                continue
            tag = f"h{min(lvl, 4)}"
            slug_id = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")[:48]
            id_attr = f' id="{slug_id}"' if slug_id else ""
            out.append(f"<{tag}{id_attr}>{inline_md(txt, link_rewriter)}</{tag}>")
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            out.append("<hr>")
            i += 1
            continue

        # Table
        if "|" in line and i + 1 < n and is_table_sep(lines[i + 1]):
            def split_row(r):
                r = r.strip()
                if r.startswith("|"):
                    r = r[1:]
                if r.endswith("|"):
                    r = r[:-1]
                return [c.strip() for c in r.split("|")]

            headers = split_row(line)
            i += 2
            rows = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(split_row(lines[i]))
                i += 1
            tbl = ['<div class="tbl-wrap"><table><thead><tr>']
            tbl.extend(f"<th>{inline_md(h, link_rewriter)}</th>" for h in headers)
            tbl.append("</tr></thead><tbody>")
            for r in rows:
                tbl.append("<tr>" + "".join(f"<td>{inline_md(c, link_rewriter)}</td>" for c in r) + "</tr>")
            tbl.append("</tbody></table></div>")
            out.append("".join(tbl))
            continue

        # Blockquote
        if stripped.startswith(">"):
            qlines = []
            while i < n and lines[i].strip().startswith(">"):
                qlines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{inline_md(' '.join(qlines), link_rewriter)}</p></blockquote>")
            continue

        # Unordered list
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline_md(it, link_rewriter)}</li>" for it in items) + "</ul>")
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline_md(it, link_rewriter)}</li>" for it in items) + "</ol>")
            continue

        # Paragraph
        plines = []
        while i < n:
            s = lines[i].strip()
            if not s or s.startswith(("#", "```", ">", "- ", "* ")) or re.match(r"^\d+\.\s+", s):
                break
            if "|" in lines[i] and i + 1 < n and is_table_sep(lines[i + 1]):
                break
            plines.append(s)
            i += 1
        if plines:
            out.append(f"<p>{inline_md(' '.join(plines), link_rewriter)}</p>")

    return "\n".join(out)


EXTRA_CSS = """
.tbl-wrap{overflow-x:auto;margin:1rem 0;border:1px solid rgba(255,255,255,.1);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{padding:.55rem .7rem;text-align:left;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top}
th{background:rgba(255,255,255,.05);font-weight:600;color:#fff}
pre{background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:.9rem 1rem;overflow-x:auto;font-size:.86rem;line-height:1.45}
pre code{background:none;padding:0}
blockquote{margin:1rem 0;padding:.6rem 1rem;border-left:3px solid #f59e0b;background:rgba(245,158,11,.08);border-radius:0 6px 6px 0}
.badges{display:flex;flex-wrap:wrap;gap:.45rem;margin:.6rem 0 1rem}
.badge{display:inline-block;padding:.2rem .55rem;border-radius:999px;font-size:.78rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);color:#e5e7eb}
.badge.accent{background:rgba(245,158,11,.15);border-color:rgba(245,158,11,.4);color:#fde68a}
.meta-bar{display:flex;flex-wrap:wrap;gap:.8rem;align-items:center;font-size:.86rem;opacity:.85;margin:.5rem 0 1.2rem}
.meta-bar a{color:#93c5fd}
.re-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:.75rem;margin:.75rem 0 1.5rem}
.re-card{display:block;padding:.85rem .95rem;border-radius:8px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);text-decoration:none;color:inherit;transition:border-color .15s,background .15s}
.re-card:hover{border-color:rgba(245,158,11,.55);background:rgba(255,255,255,.07)}
.re-card b{display:block;color:#fff;margin-bottom:.25rem;font-size:.98rem}
.re-card span{display:block;font-size:.84rem;opacity:.8;line-height:1.35}
.re-card small{display:inline-block;margin-top:.45rem;font-size:.74rem;color:#fcd34d;opacity:.9}
"""


def shell_page(lang, canonical_path, title, desc, inner_html, ld_obj, md_alt=None, hreflang_alts=None, og_type="article", date_iso=DATE):
    canon = f"{SITE}/{canonical_path}"
    alt_links = []
    if hreflang_alts:
        for l, p in hreflang_alts.items():
            alt_links.append(f'<link rel="alternate" hreflang="{l}" href="{SITE}/{p}">')
        if "en" in hreflang_alts:
            alt_links.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}/{hreflang_alts["en"]}">')
    if md_alt:
        alt_links.append(f'<link rel="alternate" type="text/markdown" href="{SITE}/{md_alt}">')
    alt_links.append(f'<link rel="alternate" type="application/atom+xml" title="NFSU.cc Engineering Devlog" href="{SITE}/feed.xml">')

    img = f"{SITE}/blog/img/olympic-city-world.webp"
    og_loc = "es_MX" if lang == "es" else "en_US"
    nav_guides = "/blog/es/index.html" if lang == "es" else "/blog/en/index.html"
    nav_re = "/re/es/index.html" if lang == "es" else "/re/index.html"
    nav_dev = "/devlog/es/index.html" if lang == "es" else "/devlog/index.html"
    t_guides = "Guías" if lang == "es" else "Guides"
    t_re = "Atlas RE" if lang == "es" else "RE Atlas"
    t_dev = "Bitácora" if lang == "es" else "Devlog"
    t_play = "Jugar" if lang == "es" else "Play"
    foot = "NFSU.cc: Need for Speed Underground (2003) recompilado a WebAssembly." if lang == "es" else "NFSU.cc: Need for Speed Underground (2003) statically recompiled to WebAssembly."

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#04121a">
<title>{esc(title)} | NFSU.cc</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon}">
{chr(10).join(alt_links)}
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="apple-touch-icon" href="/icon-180.png">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="NFSU.cc">
<meta property="og:locale" content="{og_loc}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:image" content="{img}">
<meta property="og:image:alt" content="Need for Speed Underground (2003) running in a browser at nfsu.cc">
<meta property="article:modified_time" content="{date_iso}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{img}">
<link rel="stylesheet" href="/blog/blog.css">
<style>{EXTRA_CSS}</style>
<script type="application/ld+json">{json.dumps(ld_obj, ensure_ascii=False)}</script>
</head>
<body style="--pic: url(/blog/img/olympic-city-drive.webp)">
<header class="top">
  <a class="logo" href="/"><img src="/launcher/v2/ui/logo.webp" alt="Need for Speed Underground" width="688" height="125"></a>
  <nav aria-label="Primary">
    <a href="{nav_guides}">{t_guides}</a>
    <a href="{nav_re}">{t_re}</a>
    <a href="{nav_dev}">{t_dev}</a>
    <a href="/feed.xml">RSS</a>
    <a class="play" href="/">{t_play}</a>
  </nav>
</header>
<main>
{inner_html}
</main>
<footer><span>{foot}</span><a href="/">{t_play}</a><a href="{nav_re}">{t_re}</a><a href="{nav_dev}">{t_dev}</a><a href="/llms.txt">llms.txt</a><a href="/llms-full.txt">llms-full.txt</a><a href="/feed.xml">RSS</a><a href="{REPO}" rel="noopener">GitHub</a></footer>
</body>
</html>
"""


def parse_re_notes():
    """Read all docs/re/*.md (excluding README.md) and extract metadata."""
    notes = {}
    for p in sorted(glob.glob(os.path.join(DOCS_RE, "*.md"))):
        base = os.path.basename(p)
        if base == "README.md":
            continue
        stem = base[:-3]
        raw = open(p, encoding="utf-8", errors="replace").read()
        raw = re.sub(r"/Users/[^/\s`'\")]+/RE-NFSU/", "./", raw)
        raw = re.sub(r"/Users/[^/\s`'\")]+/", "~/", raw)
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        h1 = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else stem.replace("_", " ").title()
        lead = ""
        for l in lines[1:12]:
            if not l.startswith(("#", "|", "```", ">", "---")):
                lead = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", l)
                lead = re.sub(r"[`*]", "", lead).strip()
                if len(lead) > 20:
                    break
        if not lead:
            lead = f"Verified reverse engineering notes for the {stem} subsystem of Need for Speed Underground (2003, Speed.exe)."
        if len(lead) > 190:
            lead = lead[:187].rsplit(" ", 1)[0] + "..."
        addrs = sorted(set(re.findall(r"0x(?:00)?[4-7][0-9a-fA-F]{5}\b", raw)))
        notes[stem] = dict(stem=stem, path=p, raw=raw, title=h1, desc=lead, addrs=addrs, size=len(raw))
    return notes


def build_re_atlas():
    """Generate web/re/<stem>.html, web/re/<stem>.md, web/re/index.html, web/re/es/index.html."""
    out_dir = os.path.join(W, "re")
    out_es = os.path.join(out_dir, "es")
    os.makedirs(out_es, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.html")) + glob.glob(os.path.join(out_dir, "*.md")):
        os.remove(old)

    notes = parse_re_notes()
    known_stems = set(notes.keys())

    def re_link_rewriter(href):
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return href
        # Sibling note like physics.md or physics.md#anchor
        m = re.match(r"^([a-zA-Z0-9_-]+)\.md(#.*)?$", href)
        if m and m.group(1) in known_stems:
            return f"{m.group(1)}.html{m.group(2) or ''}"
        if href == "README.md":
            return "index.html"
        # Repo-relative links like ../night_re.md or ../../census
        norm = os.path.normpath(os.path.join("docs/re", href)).replace("\\", "/")
        if not norm.startswith(".."):
            kind = "blob" if "." in norm.rsplit("/", 1)[-1] else "tree"
            return f"{REPO}/{kind}/main/{norm}"
        return href

    sitemap_urls = []
    # Map stem -> category name
    stem_cat = {}
    for cat_en, _, stems in RE_CATEGORIES:
        for s in stems:
            stem_cat[s] = cat_en

    # Individual RE pages + .md mirrors
    for stem, n in sorted(notes.items()):
        # Write clean .md mirror
        md_rel = f"re/{stem}.md"
        with open(os.path.join(W, md_rel), "w", encoding="utf-8") as f:
            f.write(f"# {n['title']}\n\n")
            f.write(f"> Source: `docs/re/{stem}.md` in `{REPO}` · Live game: {SITE}/\n")
            f.write(f"> Verified `Speed.exe` (2003 PC, base `0x400000`) addresses cited: {len(n['addrs'])}\n\n")
            f.write(n["raw"])

        cat = stem_cat.get(stem, "Subsystem Notes")
        html_body = md_to_html(n["raw"], link_rewriter=re_link_rewriter, drop_first_h1=True)
        addr_badge = f'<span class="badge accent">{len(n["addrs"])} verified Speed.exe addresses</span>' if n["addrs"] else ""
        inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / <a href="index.html">RE Atlas</a> / {esc(cat)}</p>
<article>
<h1>{esc(n['title'])}</h1>
<div class="badges">
  <span class="badge">{esc(cat)}</span>
  {addr_badge}
  <span class="badge">Speed.exe (2003, x86)</span>
</div>
<div class="meta-bar">
  <span>Updated <time datetime="{DATE}">{DATE}</time></span>
  <a href="{stem}.md">View raw Markdown (.md)</a>
  <a href="{REPO}/blob/main/docs/re/{stem}.md" rel="noopener">Source on GitHub</a>
</div>
{html_body}
<div class="cta"><a href="/">Play Need for Speed Underground in Browser</a></div>
</article>"""
        page_title = f"{n['title']} — NFS Underground (Speed.exe) Reverse Engineering"
        canon_rel = f"re/{stem}.html"
        ld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "TechArticle",
                    "headline": n["title"],
                    "description": n["desc"],
                    "inLanguage": "en",
                    "datePublished": DATE,
                    "dateModified": DATE,
                    "url": f"{SITE}/{canon_rel}",
                    "author": ORG,
                    "publisher": ORG,
                    "about": {"@type": "VideoGame", "name": "Need for Speed Underground (2003)"},
                    "proficiencyLevel": "Expert",
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "NFSU.cc", "item": f"{SITE}/"},
                        {"@type": "ListItem", "position": 2, "name": "RE Atlas", "item": f"{SITE}/re/index.html"},
                        {"@type": "ListItem", "position": 3, "name": n["title"], "item": f"{SITE}/{canon_rel}"},
                    ],
                },
            ],
        }
        open(os.path.join(W, canon_rel), "w", encoding="utf-8").write(
            shell_page("en", canon_rel, page_title, n["desc"], inner, ld, md_alt=md_rel)
        )
        sitemap_urls.append((f"{SITE}/{canon_rel}", DATE, None))

    # Build EN and ES RE Atlas Hubs
    total_addrs = len({a for n in notes.values() for a in n["addrs"]})
    assigned = {s for _, _, stems in RE_CATEGORIES for s in stems}
    leftover = sorted(known_stems - assigned)
    cats = list(RE_CATEGORIES)
    if leftover:
        cats.append(("Other Subsystems", "Otros subsistemas", leftover))

    def render_hub(lang):
        is_es = lang == "es"
        prefix = "../" if is_es else ""
        h1 = "Atlas de Ingeniería Inversa de Speed.exe (2003)" if is_es else "Need for Speed Underground (Speed.exe) Reverse Engineering Atlas"
        lead = (
            f"Documentación técnica de {len(notes)} subsistemas reales de Speed.exe (2003, PC x86, 3.18 MB, 13,764 funciones recompiladas a WebAssembly), con {total_addrs} direcciones hexadecimales únicas verificadas en el binario. Las notas individuales están en inglés técnico con versión Markdown (.md) para humanos y agentes de IA."
            if is_es
            else f"Primary binary documentation for {len(notes)} subsystems of Need for Speed Underground (2003 PC Speed.exe, 3.18 MB, 13,764 x86 functions statically recompiled to WebAssembly), citing {total_addrs} unique verified binary addresses. Every note ships in both HTML and raw Markdown (.md)."
        )
        sections = []
        for cat_en, cat_es, stems in cats:
            present = [notes[s] for s in stems if s in notes]
            if not present:
                continue
            cards = []
            for n in present:
                acount = f"{len(n['addrs'])} addrs" if n["addrs"] else "method / spec"
                cards.append(
                    f'<a class="re-card" href="{prefix}{n["stem"]}.html">'
                    f'<b>{esc(n["title"])}</b>'
                    f'<span>{esc(n["desc"])}</span>'
                    f'<small>{acount} · .html / .md</small></a>'
                )
            sections.append(f'<h2>{esc(cat_es if is_es else cat_en)}</h2>\n<div class="re-grid">{"".join(cards)}</div>')

        other_link = '<a href="../index.html">Read in English</a>' if is_es else '<a href="es/index.html">Ver resumen en Español</a>'
        inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / {"Atlas RE" if is_es else "RE Atlas"}</p>
<h1>{esc(h1)}</h1>
<p class="lead">{esc(lead)}</p>
<div class="meta-bar">
  <span>Binary: <code>Speed.exe</code> (md5 <code>b6b9232c55376b3c38c56aac1f8a121d</code>, base <code>0x400000</code>)</span>
  {other_link}
  <a href="/llms-full.txt">llms-full.txt</a>
  <a href="{REPO}/tree/main/docs/re" rel="noopener">docs/re/ on GitHub</a>
</div>
{"".join(sections)}
<div class="cta"><a href="/">{"Jugar NFS Underground en el navegador" if is_es else "Play Need for Speed Underground in Browser"}</a></div>"""
        canon_rel = "re/es/index.html" if is_es else "re/index.html"
        alts = {"en": "re/index.html", "es": "re/es/index.html"}
        ld = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": h1,
            "description": lead,
            "url": f"{SITE}/{canon_rel}",
            "inLanguage": lang,
            "isPartOf": {"@type": "WebSite", "name": "NFSU.cc", "url": f"{SITE}/"},
            "hasPart": [{"@type": "TechArticle", "headline": n["title"], "url": f"{SITE}/re/{n['stem']}.html"} for n in notes.values()],
        }
        open(os.path.join(W, canon_rel), "w", encoding="utf-8").write(
            shell_page(lang, canon_rel, h1, lead, inner, ld, hreflang_alts=alts, og_type="website")
        )
        sitemap_urls.append((f"{SITE}/{canon_rel}", DATE, {"en": f"{SITE}/re/index.html", "es": f"{SITE}/re/es/index.html"}))

    render_hub("en")
    render_hub("es")
    return notes, total_addrs, sitemap_urls


def build_devlog():
    """Generate web/devlog/<slug>.html, web/devlog/<slug>.md, EN/ES hubs, and web/feed.xml."""
    out_dir = os.path.join(W, "devlog")
    out_es = os.path.join(out_dir, "es")
    os.makedirs(out_es, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.html")) + glob.glob(os.path.join(out_dir, "*.md")):
        os.remove(old)

    sitemap_urls = []
    for p in DEVLOG_POSTS:
        md_rel = f"devlog/{p['slug']}.md"
        with open(os.path.join(W, md_rel), "w", encoding="utf-8") as f:
            f.write(f"# {p['title']}\n\n")
            f.write(f"- Date: {p['date']}\n")
            f.write(f"- Commits: {', '.join(p['commits'])}\n")
            f.write(f"- Live game: {SITE}/\n")
            f.write(f"- Repository: {REPO}\n\n")
            f.write(p["lead"] + "\n\n")
            f.write(p["body_md"].strip() + "\n")

        body_html = md_to_html(p["body_md"], drop_first_h1=False)
        tags_html = "".join(f'<span class="badge">{esc(t)}</span>' for t in p["tags"])
        commits_html = " · ".join(f'<a href="{REPO}/commit/{c}" rel="noopener"><code>{c}</code></a>' for c in p["commits"])
        files_html = " · ".join(
            f'<a href="{REPO}/{"blob" if "." in f.rsplit("/", 1)[-1] else "tree"}/main/{f}" rel="noopener"><code>{f}</code></a>'
            for f in p["files"]
        )
        inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / <a href="index.html">Devlog</a></p>
<article>
<h1>{esc(p['title'])}</h1>
<p class="lead">{esc(p['lead'])}</p>
<div class="badges">{tags_html}</div>
<div class="meta-bar">
  <span><time datetime="{p['date']}">{p['date']}</time></span>
  <span>Commits: {commits_html}</span>
  <a href="{p['slug']}.md">View raw Markdown (.md)</a>
</div>
{body_html}
<p class="repo"><b>Files in repo:</b> {files_html}</p>
<div class="cta"><a href="/">Play Need for Speed Underground in Browser</a></div>
</article>"""
        canon_rel = f"devlog/{p['slug']}.html"
        ld = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "TechArticle",
                    "headline": p["title"],
                    "description": p["desc"],
                    "inLanguage": "en",
                    "datePublished": p["date"],
                    "dateModified": p["date"],
                    "url": f"{SITE}/{canon_rel}",
                    "image": f"{SITE}/blog/img/olympic-city-world.webp",
                    "author": ORG,
                    "publisher": ORG,
                    "keywords": ", ".join(p["tags"]),
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "NFSU.cc", "item": f"{SITE}/"},
                        {"@type": "ListItem", "position": 2, "name": "Devlog", "item": f"{SITE}/devlog/index.html"},
                        {"@type": "ListItem", "position": 3, "name": p["title"], "item": f"{SITE}/{canon_rel}"},
                    ],
                },
            ],
        }
        open(os.path.join(W, canon_rel), "w", encoding="utf-8").write(
            shell_page("en", canon_rel, f"{p['title']} — NFSU.cc Devlog", p["desc"], inner, ld, md_alt=md_rel, date_iso=p["date"])
        )
        sitemap_urls.append((f"{SITE}/{canon_rel}", p["date"], None))

    # EN & ES Devlog Hubs
    for lang in ("en", "es"):
        is_es = lang == "es"
        prefix = "../" if is_es else ""
        h1 = "Bitácora de Ingeniería y Actualizaciones (Devlog)" if is_es else "NFSU.cc Engineering Devlog & Updates"
        lead = (
            "Bitácora técnica real sobre cómo recompilamos Need for Speed Underground (2003, x86) a WebAssembly y WebGPU/WebGL 2: optimizaciones del recompilador, memoria móvil de 448 MB, texturas BC1/2/3 y fixes de crashes reales. Entradas en inglés técnico con RSS y Markdown (.md)."
            if is_es
            else "Engineering updates on statically recompiling Need for Speed Underground (2003, x86) to WebAssembly and WebGPU/WebGL 2: compiler passes, DXT/BC textures, 448 MB mobile WASM, and production crash telemetry."
        )
        cards = []
        for p in DEVLOG_POSTS:
            cards.append(
                f'<a class="re-card" href="{prefix}{p["slug"]}.html">'
                f'<b>{esc(p["title"])}</b>'
                f'<span>{esc(p["desc"])}</span>'
                f'<small>{p["date"]} · commits {", ".join(p["commits"])} · .html / .md</small></a>'
            )
        other_link = '<a href="../index.html">Read in English</a>' if is_es else '<a href="es/index.html">Ver índice en Español</a>'
        inner = f"""<p class="crumbs"><a href="/">NFSU.cc</a> / {"Bitácora" if is_es else "Devlog"}</p>
<h1>{esc(h1)}</h1>
<p class="lead">{esc(lead)}</p>
<div class="meta-bar">
  {other_link}
  <a href="/feed.xml">Atom RSS Feed</a>
  <a href="/re/index.html">{"Atlas de Ingeniería Inversa (44 sistemas)" if is_es else "Reverse Engineering Atlas (44 systems)"}</a>
  <a href="{REPO}/blob/main/CHANGELOG.md" rel="noopener">CHANGELOG.md</a>
</div>
<div class="re-grid" style="grid-template-columns:1fr">{"".join(cards)}</div>
<div class="cta"><a href="/">{"Jugar ahora en nfsu.cc" if is_es else "Play now at nfsu.cc"}</a></div>"""
        canon_rel = "devlog/es/index.html" if is_es else "devlog/index.html"
        alts = {"en": "devlog/index.html", "es": "devlog/es/index.html"}
        ld = {
            "@context": "https://schema.org",
            "@type": "Blog",
            "name": h1,
            "description": lead,
            "url": f"{SITE}/{canon_rel}",
            "inLanguage": lang,
            "publisher": ORG,
            "blogPost": [
                {"@type": "TechArticle", "headline": p["title"], "datePublished": p["date"], "url": f"{SITE}/devlog/{p['slug']}.html"}
                for p in DEVLOG_POSTS
            ],
        }
        open(os.path.join(W, canon_rel), "w", encoding="utf-8").write(
            shell_page(lang, canon_rel, h1, lead, inner, ld, hreflang_alts=alts, og_type="website")
        )
        sitemap_urls.append((f"{SITE}/{canon_rel}", DATE, {"en": f"{SITE}/devlog/index.html", "es": f"{SITE}/devlog/es/index.html"}))

    # Atom 1.0 RSS Feed (/feed.xml)
    entries = []
    for p in DEVLOG_POSTS:
        u = f"{SITE}/devlog/{p['slug']}.html"
        entries.append(f"""  <entry>
    <title>{esc(p['title'])}</title>
    <link href="{u}" rel="alternate" type="text/html"/>
    <link href="{SITE}/devlog/{p['slug']}.md" rel="alternate" type="text/markdown"/>
    <id>{u}</id>
    <updated>{p['date']}T18:00:00Z</updated>
    <summary>{esc(p['desc'])}</summary>
  </entry>""")
    feed = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>NFSU.cc Engineering Devlog &amp; Reverse Engineering Updates</title>
  <subtitle>Static recompilation of Need for Speed Underground (2003, x86) to WebAssembly and WebGPU/WebGL 2.</subtitle>
  <link href="{SITE}/feed.xml" rel="self" type="application/atom+xml"/>
  <link href="{SITE}/devlog/index.html" rel="alternate" type="text/html"/>
  <id>{SITE}/feed.xml</id>
  <updated>{DATE}T18:00:00Z</updated>
  <author><name>NFSU.cc</name></author>
{chr(10).join(entries)}
</feed>
"""
    open(os.path.join(W, "feed.xml"), "w", encoding="utf-8").write(feed)
    return sitemap_urls


def build_llms_files(notes, total_addrs):
    """Generate concise /llms.txt and comprehensive /llms-full.txt for AI crawlers & agents."""
    llms_txt = f"""# NFSU.cc — Need for Speed Underground (2003) Static Recompilation in WebAssembly

> Play the original 2003 PC version of Need for Speed Underground free in a browser tab at {SITE}/ — no download, no install, no emulator.

NFSU.cc is a static recompilation of the original 2003 Windows executable (`Speed.exe`, 3.18 MB, md5 `b6b9232c55376b3c38c56aac1f8a121d`, 13,764 x86 functions lifted to C and compiled to WebAssembly) with a custom browser host layer replacing Win32, DirectX 9 (WebGPU with automatic WebGL 2 fallback and native BC1/2/3 S3TC textures), DirectInput (keyboard, gamepad, touch), and DirectSound (Web Audio). Includes **Original 2003** and **Remaster** modes plus the full original soundtrack.

- Full single-file technical compendium for LLMs: [{SITE}/llms-full.txt]({SITE}/llms-full.txt)
- Atom RSS feed (engineering updates): [{SITE}/feed.xml]({SITE}/feed.xml)
- Source code & architecture: [{REPO}]({REPO})

## Play & Entry Points

- [Play Need for Speed Underground Online]({SITE}/): Main entry point (launcher on desktop, direct boot with touch controls on phones/tablets).
- [Launcher & Settings]({SITE}/launcher.html): Quality presets, Original 2003 vs Remaster, key rebinding, local IndexedDB save backup/restore.

## Engineering Devlog (HTML + .md mirrors)

- [Engineering Devlog Index (EN)]({SITE}/devlog/index.html) · [Bitácora (ES)]({SITE}/devlog/es/index.html)
""" + "\n".join(
        f"- [{p['title']}]({SITE}/devlog/{p['slug']}.html) ([Markdown]({SITE}/devlog/{p['slug']}.md)) — {p['date']}"
        for p in DEVLOG_POSTS
    ) + f"""

## Reverse Engineering Atlas ({len(notes)} Subsystems, {total_addrs} Verified Speed.exe Addresses)

- [Reverse Engineering Atlas Index (EN)]({SITE}/re/index.html) · [Resumen (ES)]({SITE}/re/es/index.html)
- Key starting notes: [physics]({SITE}/re/physics.md), [camera]({SITE}/re/camera.md), [rivals]({SITE}/re/rivals.md), [traffic]({SITE}/re/traffic.md), [track]({SITE}/re/track.md), [render]({SITE}/re/render.md), [sound]({SITE}/re/sound.md), [gameflow]({SITE}/re/gameflow.md), [assets]({SITE}/re/assets.md)

## Player & Technical Guides (EN / ES)

- [All English Guides]({SITE}/blog/en/index.html) · [Todas las guías en Español]({SITE}/blog/es/index.html)
- [How to Play Online]({SITE}/blog/en/play-need-for-speed-underground-online.html)
- [Static Recompilation: x86 to WebAssembly]({SITE}/blog/en/static-recompilation-x86-to-webassembly.html)
- [DirectX 9 and Windows on WebGPU]({SITE}/blog/en/directx-9-and-windows-on-webgpu.html)
- [Reverse Engineering Tools: Ghidra, Hopper, REA]({SITE}/blog/en/reverse-engineering-tools-ghidra-hopper-rea.html)
- [Reverse Engineering a Game with AI Agents]({SITE}/blog/en/reverse-engineering-a-game-with-ai-agents.html)
"""
    open(os.path.join(W, "llms.txt"), "w", encoding="utf-8").write(llms_txt)

    # /llms-full.txt: rich, self-contained technical reference for Claude, Perplexity, ChatGPT, Google AI
    devlog_sec = []
    for p in DEVLOG_POSTS:
        devlog_sec.append(
            f"### {p['title']} ({p['date']})\n"
            f"URL: {SITE}/devlog/{p['slug']}.html | Markdown: {SITE}/devlog/{p['slug']}.md | Commits: {', '.join(p['commits'])}\n\n"
            f"{p['lead']}\n\n{p['body_md'].strip()}\n"
        )

    atlas_sec = []
    for cat_en, _, stems in RE_CATEGORIES:
        present = [notes[s] for s in stems if s in notes]
        if not present:
            continue
        atlas_sec.append(f"### {cat_en}")
        for n in present:
            sample = ", ".join(n["addrs"][:5]) if n["addrs"] else "method/spec"
            atlas_sec.append(
                f"- **{n['title']}** (`docs/re/{n['stem']}.md`, {len(n['addrs'])} verified addresses e.g. {sample}): "
                f"{n['desc']} — HTML: {SITE}/re/{n['stem']}.html | MD: {SITE}/re/{n['stem']}.md"
            )
        atlas_sec.append("")

    llms_full = f"""# NFSU.cc — Complete Technical & Reverse Engineering Reference (`llms-full.txt`)

Updated: {DATE}
Live URL: {SITE}/
GitHub Repository: {REPO}

## 1. Project Summary & Verified Architecture Facts

NFSU.cc runs **Need for Speed Underground (2003, PC)** directly in modern web browsers via **ahead-of-time static recompilation** (not x86 emulation and not a ground-up remake).

- **Source binary**: `pc/Speed.exe` (3,178,496 bytes / 3.18 MB, MD5 `b6b9232c55376b3c38c56aac1f8a121d`, PE base `0x400000`).
- **Static recompiler (`tools/recomp/`)**: Lifts **13,764 x86 functions** from `Speed.exe` to C (`lift.py`, `abk.py`, `build.py`), compiled with Emscripten to `web/out/speed.wasm` (42.31 MB uncompressed, ~11.1 MB Brotli `-q 11`) and `web/out/speed_lite.wasm` (448 MB WASM heap / 256 MB `GUEST_MEM` for phones and tablets).
- **Recompiler optimizations**: Liveness-based dead x86 EFLAGS pruning (`8444027`), `CHK_IMG` static-image bypass + straight-line `CHK_SP` stack-pointer coalescing (`69f51fb`, `fc8ef2e`), and `RN_FAST_X87` verified against `RN_STRICT_X87` via single-function differential testing (`tools/recomp/difftest.py`).
- **Host & graphics layer (`host/`, `web/`)**: C + JavaScript shims replace Win32, DirectX 9 (`host/d3d9.c`, `host/gpu.c`, `host/sm1.c` -> WebGPU `web/gpu.js` with automatic WebGL 2 fallback `web/webgpu_gl.js`), native DXT1/3/5 -> BC1/2/3 GPU textures (`RN_S3TC`, `00e474c`), DirectInput (keyboard, gamepad, touch), and DirectSound (`web/audio.js` via Web Audio).
- **Adaptive performance & hosting**: Always-on 256-frame present ring (`web/stats.js`), closed-loop frame-time quality controller (`web/quality.js`), 2.05 GB game assets streamed on demand from Cloudflare R2 with Brotli chunks and full original 2003 soundtrack intact.
- **Reverse engineering corpus**: {len(notes)} subsystem notes in `docs/re/` ({total_addrs} unique verified `Speed.exe` hex addresses), 57 symbol census tables (`census/names_*.tsv`), and 14 surgical patch modules (`tools/recomp/patches_*.py`).

## 2. Engineering Devlog (Real Commits & Measurements)

{chr(10).join(devlog_sec)}

## 3. Reverse Engineering Atlas ({len(notes)} Subsystems of Speed.exe)

{chr(10).join(atlas_sec)}
"""
    open(os.path.join(W, "llms-full.txt"), "w", encoding="utf-8").write(llms_full)


def build_all():
    notes, total_addrs, re_urls = build_re_atlas()
    dev_urls = build_devlog()
    build_llms_files(notes, total_addrs)
    print(f"re_devlog: {len(notes)} RE notes ({total_addrs} unique addrs), {len(DEVLOG_POSTS)} devlog posts, feed.xml, llms.txt, llms-full.txt")
    return re_urls + dev_urls


if __name__ == "__main__":
    build_all()
