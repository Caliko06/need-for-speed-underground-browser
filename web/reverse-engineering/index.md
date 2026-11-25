# Reverse Engineering & Static Recompilation Field Guide (x86 to WebAssembly)

> Plain-English (ELI5) intuition + production-verified deep dives on binary reverse engineering, x86-to-WebAssembly static recompilation, DirectX 9-to-WebGPU translation, and AI-assisted binary analysis.
> Primary open-source evidence base: `https://github.com/Caliko06/need-for-speed-underground-browser` · Live WebAssembly demo: https://nfsu.cc/

## ELI5: Reverse Engineering & Static Recompilation in 60 Seconds

Think of a compiled 2003 Windows `.exe` file like a baked cake where the original recipe (the C/C++ source code) was lost:

- **Reverse engineering** is figuring out the recipe by inspecting the cake under a microscope (disassemblers and decompilers like Ghidra, Hopper, and automated MCP tools) and writing down what every function and memory address actually does.
- **Emulation** is building a virtual 2003 PC inside software and simulating every CPU cycle at runtime. It works, but it is heavy for a browser tab or a phone.
- **Static recompilation** is translating the old machine instructions (32-bit x86) into clean modern C code **once ahead of time**, then compiling that C into **WebAssembly (WASM)** using LLVM. Instead of pretending to be an old CPU, the browser executes modern compiled code directly while a small host layer translates Windows/DirectX calls to WebGPU, WebGL 2, and Web Audio.

## Verified Production Proof (Real Numbers From One Shipped Binary)

Every technique in this field guide is proven in production on a real 3.18 MB 32-bit x86 Windows PE binary (`Speed.exe`, 2003, base `0x400000`, MD5 `b6b9232c55376b3c38c56aac1f8a121d`) running live at [https://nfsu.cc/](https://nfsu.cc/):

| Dimension | Measured Value | Where to Inspect |
|---|---:|---|
| Lifted x86 functions (`x86 -> C -> WASM`) | **13,766** | `tools/recomp/lift.py` (`3,334` LOC across `23` Python files) |
| Custom Win32 / D3D9 / DInput / DSound host | **15,035 LOC** | `host/` (`34` C/H files) + `web/` |
| Verified binary subsystem monographs | **49 notes** (`2,858` unique hex addrs) | [Reverse Engineering Atlas](/re/index.html) |
| Evidence-tagged symbol census (`V/I/U`) | **18,293 rows** (`7,886` `V`-verified across `59` tables) | [Symbol Census Catalog](/reverse-engineering/symbols.html) |
| Non-destructive binary patch modules | **15 modules** (`753` unique hex addrs) | [Modular Patching Guide](/reverse-engineering/patches.html) |
| Compiled WASM footprint (Brotli `-q 11`) | **7.04 MB** (`42.31 MB` raw, `-39.9%` after compiler passes) | [Recompiler Passes Devlog](/devlog/recompiler-dead-flags-chk-sp-fast-x87.html) |
| Mobile WASM heap budget | **448 MB** (`256 MB` guest RAM, down from `640 MB`) | [OOM & Mobile Heap Devlog](/devlog/production-crash-hardening-and-448mb-phone-wasm.html) |
| Cold boot to live 3D WebGPU frames | **2.27 s** desktop (`-30.5 s` on mobile after curtain gate) | [V8 Cache & Mobile Boot Devlog](/devlog/v8-wasm-code-cache-mobile-boot-and-r2-immutable.html) |

## Four Reusable Playbooks (For Engineers & AI Agents)

### 1. Static x86-to-C Recompilation & Compiler Optimization

- **ELI5**: A naive translator writes down every tiny side effect of every x86 instruction (like carry flags and stack safety checks), even when nobody ever checks them. Smart compiler passes delete the useless work and bundle repetitive safety checks into one check per block.
- **Technical deep dive**:
  - **Inter-procedural EFLAGS liveness (`FlagABI`)**: Computes live flag masks across basic blocks and direct calls, cutting `par(` by `-82.1%`, `af=` by `-80.7%`, and `c->cf=cf` by `-69.4%`.
  - **Stack & image bounds coalescing (`CHK_IMG`, `CHK_SP`)**: Static PE image reads skip dynamic bounds checks; straight-line `esp` deltas coalesce into one min/max check per block (`619,768 -> 385,228` checks, `-37.8%`).
  - **Differential testing (`difftest.py`)**: Every compiler optimization is checked per-function against native traces (`RN_STRICT_X87` vs `RN_FAST_X87`, `5,404/5,407` functions passing).
- **Read full write-up**: [Dead x86 Flag Pruning, CHK_SP Coalescing, and Fast x87](/devlog/recompiler-dead-flags-chk-sp-fast-x87.html) ([Markdown](/devlog/recompiler-dead-flags-chk-sp-fast-x87.md))

### 2. Translating DirectX 9 to WebGPU & WebGL 2

- **ELI5**: Old PC games send hundreds of small drawing orders every frame and store textures in compressed GPU blocks (DXT). If the browser decompresses those textures on the CPU or rebuilds GPU state on every draw call, it stutters. Keeping textures compressed and slicing one shared uniform buffer keeps frames under 1 millisecond on GPU.
- **Technical deep dive**:
  - **Native BC1/2/3 (`S3TC`) passthrough**: Uploads raw DXT1/3/5 mip bytes directly to `bc1/2/3-rgba-unorm` on WebGPU (`texture-compression-bc`) and `WEBGL_compressed_texture_s3tc` on WebGL 2, saving `4x-8x` VRAM.
  - **Zero-waste dynamic UBO & `bindGroup` cache**: Compact `256 B` dynamic uniform buffer slicing cut per-frame uniform uploads from `~9.6 MB` to `1.32 MB` (`-86.2%`).
  - **Production GPU fallbacks**: Software fallback when `unorm8x4-bgra` vertex formats are unsupported, plus guarded `tsBuf.unmap()` during device teardown.
- **Read full write-up**: [DirectX 9 to WebGPU & WebGL 2: Native BC1/2/3 & Zero-Waste Draws](/devlog/zero-waste-webgpu-draw-pipeline-and-bc-textures.html) ([Markdown](/devlog/zero-waste-webgpu-draw-pipeline-and-bc-textures.md))

### 3. Shipping Large WebAssembly Apps in Real Browsers & Cloudflare R2

- **ELI5**: Browsers have hidden fast paths (like saving compiled WebAssembly on disk so repeat visits are instant) and hidden traps (like phones running out of RAM if you load a 3D menu on top of a 448 MB app). Measuring real crashes and real A/B timings catches what local desktop tests hide.
- **Technical deep dive**:
  - **V8 WASM code cache**: Pass raw `fetch()` straight to `WebAssembly.instantiateStreaming(r, imports)` with zero `TransformStream` wrapper (`-77.2%` JS memory at run).
  - **50-minute browser OOM**: Freeing CPU-side shadow vertex/index buffers (`SmoothEnt`) immediately after GPU upload eliminated linear heap growth across long sessions.
  - **Zero-upload R2 `immutable` migration**: S3 `CopyObject` with `MetadataDirective=REPLACE` updated `419/419` objects in-place (`Cache-Control: public, max-age=31536000, immutable`) without re-uploading `1.32 GB`.
  - **Closed-loop frame-time quality control**: A 256-frame `Present()` ring buffer scales resolution and post-FX dynamically while keeping audio intact.
- **Read full write-ups**: [V8 WASM Code Cache, Mobile Boot & R2 Immutable](/devlog/v8-wasm-code-cache-mobile-boot-and-r2-immutable.html) · [50-Minute OOM & 448 MB Mobile WASM](/devlog/production-crash-hardening-and-448mb-phone-wasm.html) · [Adaptive Frame-Time Quality Control](/devlog/adaptive-frame-time-quality-and-dual-wasm-builds.html)

### 4. Evidence-First Reverse Engineering With AI Agents

- **ELI5**: AI coding agents are fast at reading assembly, but if you let them guess, they invent plausible-sounding nonsense. Giving them direct binary-reading tools and forcing every single sentence to cite a real hex address turns them into reliable reverse engineers.
- **Technical deep dive**:
  - **Mandatory `V / I / U` evidence tags**: Every function name, struct offset, and state-machine transition is tagged **V** (verified in binary instructions/bytes via REA MCP, Ghidra, or Hopper), **I** (inferred), or **U** (open/unproven).
  - **Modular non-destructive patching**: All `753` hex patches live in `15` topic modules (`tools/recomp/patches_*.py`), each citing its exact binary address and keeping the original behavior toggleable.
  - **Machine-readable publication**: Every monograph, devlog, and guide ships as both semantic HTML and a clean `.md` sibling indexed in [`/llms.txt`](/llms.txt) and [`/llms-full.txt`](/llms-full.txt).
- **Explore the primary evidence**: [Symbol Census (18,293 rows)](/reverse-engineering/symbols.html) · [Modular Binary Patching (753 addrs)](/reverse-engineering/patches.html) · [49-Subsystem Binary Atlas](/re/index.html)

## Frequently Asked Questions (Reverse Engineering & Static Recompilation)

### What is static recompilation vs emulation (ELI5)?

An emulator is like a live translator reading a foreign book aloud sentence by sentence while you listen, which burns CPU every frame. Static recompilation translates the entire 32-bit x86 executable into C source code once ahead of time, then compiles that C into native WebAssembly with Clang/LLVM so the browser runs it near native speed.

### How do you optimize lifted x86-to-C code for WebAssembly?

Three compiler passes eliminate most naive lifting overhead: (1) inter-procedural EFLAGS liveness analysis to prune dead flag calculations (cutting par/af/cf writes by 69-82%), (2) static image address bypass (CHK_IMG) plus straight-line stack-pointer bounds coalescing (CHK_SP, cutting checks by 37.8%), and (3) native IEEE-754 floating point (RN_FAST_X87) verified against strict x87 via single-function differential testing.

### Why does wrapping fetch() in a TransformStream break V8 WebAssembly code caching?

Chromium's V8 engine only caches compiled WebAssembly modules on disk when WebAssembly.instantiateStreaming() receives a genuine network Response with a cacheable URL. Wrapping response.body in a TransformStream or new Response() strips the URL identity, disables the code cache, and increases JS heap usage (+77% measured in production).

### How do you prevent AI agents from hallucinating during reverse engineering?

Enforce an evidence-first contract: every claim about a binary must cite the exact virtual address and tool output (Ghidra, Hopper, or REA MCP) and carry a confidence tag: V (verified in instructions/bytes), I (inferred), or U (open/unproven). Memory, docs, and prior summaries are treated only as leads to re-check.

### How do you update Cache-Control headers on gigabytes of Cloudflare R2 / S3 files without re-uploading?

Use the S3 CopyObject API targeting the same bucket and key with x-amz-metadata-directive: REPLACE and the new Cache-Control header (e.g. public, max-age=31536000, immutable). R2 updates metadata server-side with zero upload bandwidth.
