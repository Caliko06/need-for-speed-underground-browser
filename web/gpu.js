// Runs the frames that host/gpu.c hands over (see host/gpu.h; the numbers below mirror it) with
// WebGPU, on the page's thread. The game thread waits in Present until the page has run the frame
// before the one it submits. Shaders arrive as WGSL (host/sm1.c); textures as RGBA8.
'use strict';
const GPU_TARGET = 1, GPU_CLEAR = 2, GPU_PRESENT = 3, GPU_DRAW = 4, GPU_SHADER = 5, GPU_DECL = 6, GPU_TEXTURE = 7,
  GPU_TEXDATA = 8, GPU_TEXKEY = 9, GPU_CUBE = 10, GPU_FXAA = 11, GPU_SKIN = 12,
  GPU_BUFFER = 13, GPU_BUFDATA = 14, GPU_LIVERY = 15;
const D_TOPO = 0, D_NVERT = 1, D_NIDX = 2, D_STRIDE = 3, D_VS = 4, D_PS = 5, D_DECL = 6, D_RT = 7, D_DS = 8, D_VP = 9,
  D_SC = 15, D_ZEN = 19, D_ZWRITE = 20, D_ZFUNC = 21, D_CULL = 22, D_BLEND = 23, D_SRCB = 24, D_DSTB = 25, D_BOP = 26,
  D_SEPA = 27, D_SRCBA = 28, D_DSTBA = 29, D_BOPA = 30, D_BFACTOR = 31, D_CWRITE = 32, D_AFUNC = 33, D_AREF = 34,
  D_FOG = 35, D_FOGC = 36, D_TEX = 37, D_TEXN = 8, D_NVC = 37 + 64, D_NPC = 38 + 64,
  D_RVB = 39 + 64, D_RVOFF = 40 + 64, D_RIB = 41 + 64, D_RIFMT = 42 + 64, D_RFIRST = 43 + 64, D_RBASEV = 44 + 64, D_HDR = 45 + 64;
const T_ID = 0, T_AU = 1, T_AV = 2, T_MAG = 3, T_MIN = 4, T_MIP = 5, T_TT = 6, T_ANISO = 7, T_CUBE = 0x10000;
const U_SIZE = 4320, U_FIXED = 224;     // sm1.h SM1_U_SIZE; fixed fields at 0..223, c[256] at 224..4319

// PS2 depth speed blur (psblur below): web/tune.js sets .on from the blur preset ('PS2 depth') and ?psblur.
const RN_PS = { on: false };
const CMP = [null, 'never', 'less', 'equal', 'less-equal', 'greater', 'not-equal', 'greater-equal', 'always'];
const BLEND = [null, 'zero', 'one', 'src', 'one-minus-src', 'src-alpha', 'one-minus-src-alpha', 'dst-alpha',
  'one-minus-dst-alpha', 'dst', 'one-minus-dst', 'src-alpha-saturated', null, null, 'constant', 'one-minus-constant'];
const BLENDOP = [null, 'add', 'subtract', 'reverse-subtract', 'min', 'max'];
const ADDRESS = [null, 'repeat', 'mirror-repeat', 'clamp-to-edge'];
// D3DDECLTYPE -> vertex format (the types WGSL vec4f can take). D3DCOLOR is BGRA in memory.
const VFMT = ['float32', 'float32x2', 'float32x3', 'float32x4', 'unorm8x4-bgra', null, null, null, 'unorm8x4',
  'snorm16x2', 'snorm16x4', 'unorm16x2', 'unorm16x4', null, null, 'float16x2', 'float16x4'];

async function startGpu(M, canvas, report, onFrame) {
  if (!navigator.gpu) throw new Error('WebGPU no disponible en este navegador (hace falta Chrome/Edge 113+, Safari 26+ o Firefox 145+ en Mac Apple Silicon)');
  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) throw new Error('WebGPU: sin adaptador');
  // Which GPU drew (the Pod's Chrome must get the NVIDIA, not SwiftShader).
  report(`gpu.js: adapter ${adapter.info?.vendor || '?'} ${adapter.info?.architecture || ''} ${adapter.info?.description || ''}`);
  // timestamp-query (when the adapter has it): GPU time of each frame's passes, reported with the frame log (gpu.js ts).
  const TS = adapter.features.has('timestamp-query');
  // texture-compression-bc (Apple and desktop GPUs have it): the remaster pack in BC7 (loadDds).
  const BC = adapter.features.has('texture-compression-bc');
  // S3TC: DXT textures stay BC1/2/3 (host/d3d9.c RN_S3TC). The WebGL 2 shim has no texture-compression-bc, so it names its own feature.
  const S3 = BC || adapter.features.has('rn-s3tc');
  const device = await adapter.requestDevice({ requiredFeatures: [...(TS ? ['timestamp-query'] : []), ...(BC ? ['texture-compression-bc'] : [])] });
  device.addEventListener('uncapturederror', e => report('webgpu: ' + e.error.message));
  // ?apicount=1 (debug): WebGPU calls per frame list, reported with the frame log (wraps the prototypes).
  const apiN = {};
  if (RN_Q.get('apicount') === '1') {
    const wrap = (proto, names) => { for (const m of names) { const f = proto[m]; proto[m] = function (...x) { apiN[m] = (apiN[m] || 0) + 1; return f.apply(this, x); }; } };
    wrap(GPURenderPassEncoder.prototype, ['setPipeline', 'setBindGroup', 'setVertexBuffer', 'setIndexBuffer', 'setViewport', 'setScissorRect', 'setBlendConstant', 'setStencilReference', 'draw', 'drawIndexed']);
    wrap(GPUDevice.prototype, ['createBindGroup', 'createRenderPipeline']);
    wrap(GPUQueue.prototype, ['writeBuffer', 'writeTexture']);
    wrap(GPUCommandEncoder.prototype, ['beginRenderPass']);
  }
  // A lost device (GPU reset, iOS reclaiming a background tab) stops drawing for good: say so instead of a frozen frame.
  device.lost.then(i => { if (i.reason !== 'destroyed') report(`STOP webgpu: se perdió la GPU (${i.reason || '?'}: ${i.message}). Recarga la página.`); });
  // ?watchdog=1 (probe, OFF by default; w1 2026-11-05): in Safari the page's main thread stopped 15 times in 24 min, for
  // 20-113 s each (rAF, timers and the log all stopped, no visibilitychange; F10 nfsu-session-2026-11-05T20-46-57). A worker
  // watches a heartbeat the main thread bumps every 100 ms and writes to build/web.log with its own fetch: how long the
  // main thread stopped, its phase (1 pump runs a frame list, 2 rAF present, 3 telemetry flush, 4 pump in waitAsync,
  // 5 pump yielding a task, 0 other) and the pump turns meanwhile (turns that go on while timers starve = a microtask loop).
  const WD = RN_Q.get('watchdog') === '1' ? new Int32Array(new SharedArrayBuffer(16)) : null;   // heartbeat, phase, pump turns
  globalThis.RN_WD = WD;
  if (WD) {
    setInterval(() => Atomics.add(WD, 0, 1), 100);
    const src = `onmessage = ({ data: [wd, url, t0] }) => {
      const pt = () => (performance.timeOrigin + performance.now() - t0) / 1000;   // seconds on the page's clock
      const say = s => fetch(url, { method: 'POST', body: pt().toFixed(2) + ' watchdog: ' + s + '\\n' }).catch(() => {});
      let hb = -1, since = 0, turns = 0, ph = 0, told = 0;
      say('worker up');
      setInterval(() => {
        const h = Atomics.load(wd, 0), now = performance.now();
        if (h !== hb) {
          if (told) say('page main thread back after ' + ((now - since) / 1000).toFixed(1) + ' s; phase at the stop ' + ph +
                        ', now ' + Atomics.load(wd, 1) + ', pump turns during it ' + (Atomics.load(wd, 2) - turns));
          hb = h; since = now; turns = Atomics.load(wd, 2); ph = Atomics.load(wd, 1); told = 0;
          return;
        }
        const s = (now - since) / 1000;
        if (s >= 2 && s >= 2 * (told || 1)) {   // at 2, 4, 8, 16 ... s
          told = s;
          say('page main thread stopped ' + s.toFixed(1) + ' s; phase ' + Atomics.load(wd, 1) + ' (at the stop ' + ph +
              '), pump turns ' + (Atomics.load(wd, 2) - turns));
        }
      }, 200);
    };`;
    new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' }))).postMessage([WD, location.origin + '/log', performance.timeOrigin]);
    report('watchdog: on (?watchdog=1)');
  }
  const ctx = canvas.getContext('webgpu');
  const box = M._rn_gpu_mailbox() >> 2;     // u32 index: seq, done, ptr[2], len[2]
  const H = () => M.HEAPU32;                // the view of the shared wasm memory
  const res = new Map();                    // id -> {tex, w, h, depth} (targets and textures)
  const shaders = new Map(), decls = new Map();
  let canvasSize = '';
  const fail = msg => { throw new Error('gpu.js: ' + msg); };

  // Present queue. The game asks for vsync (CreateDevice PresentationInterval 0 = D3DPRESENT_INTERVAL_DEFAULT) and paces
  // itself on QPC (limiter 0x585b40, 1/60 s), so on Windows Present fed D3D's queue and the screen took one frame per
  // refresh. Writing the canvas on submit instead put each Present right at the refresh edge, its jitter picking the
  // refresh before or after: in a 60 Hz Chrome run, windows of ~15 s every ~40 s showed 150 repeats + 150 drops per
  // 300 refreshes (30 fps judder, the OWNER's "lagazos"). Here a Present renders into a queued texture and each animation
  // frame shows the oldest one (at most QMAX queued: a hidden page or a slow screen drops the oldest).
  // ?present=now = the old way (canvas on submit). RN_PACE counts what reached the screen (web/telemetry.js 'vsync').
  const PRESENT_NOW = RN_Q.get('present') === 'now', QMAX = 3;
  const RN_PACE = globalThis.RN_PACE = { shown: 0, dropped: 0 };
  const shownQ = [], freeQ = [];
  let qSize = '';
  const queueTex = (w, h) => {
    const s = `${w}x${h}`;
    if (s !== qSize) { for (const q of freeQ) q.tex.destroy(); freeQ.length = 0; qSize = s; }
    return freeQ.pop() || { w, h, tex: device.createTexture({ size: [w, h], format: 'rgba8unorm',
      usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC | GPUTextureUsage.COPY_DST }) };
  };
  const recycle = q => { if (`${q.w}x${q.h}` === qSize) freeQ.push(q); else q.tex.destroy(); };
  // Race frames on the display grid (ON by default since 2026-11-14, ?pace=0 off; th0mk/nfsu2-web framerate.c). Headless WORLD race,
  // same build: off 24-60 frames > 23 ms, worst 30.5-47 ms; on 8, worst 27.9 (build/world_spikes2-3). Each animation frame writes the refresh time (ms,
  // timeOrigin based like the worker's emscripten_get_now) and the measured refresh period into host/d3d9.c pace_box,
  // whose address comes with each Present. In a race the game thread then sleeps after Present to the next display slot.
  const PACE = RN_Q.get('pace') !== '0';
  let paceBox = 0, paceT = 0, paceP = 0;
  function showQueued(ts) {
    requestAnimationFrame(showQueued);
    const wdWas = WD ? WD[1] : 0;
    if (WD) WD[1] = 2;
    try { showQueuedBody(ts); } finally { if (WD) WD[1] = wdWas; }
  }
  function showQueuedBody(ts) {
    if (PACE && paceBox) {
      const d = ts - paceT;
      if (paceT && d > 4 && d < 50) paceP = !paceP || d < paceP * 0.75 ? d : d < paceP * 1.5 ? paceP + (d - paceP) * 0.05 : paceP;
      paceT = ts;
      M.HEAPF64[paceBox >> 3] = performance.timeOrigin + ts;
      M.HEAPF64[(paceBox >> 3) + 1] = paceP;
    }
    const q = shownQ.shift();
    if (!q) return;
    const tex = ctx.getCurrentTexture();
    if (tex.width === q.w && tex.height === q.h) {
      const e = device.createCommandEncoder();
      e.copyTextureToTexture({ texture: q.tex }, { texture: tex }, [q.w, q.h]);
      device.queue.submit([e.finish()]);
      RN_PACE.shown++;
    } else RN_PACE.dropped++;
    recycle(q);
  }
  if (!PRESENT_NOW) requestAnimationFrame(showQueued);

  // Remaster pack (web/remaster, tools/remaster/index.py): FNV-1a 64 of a DXT level 0 -> an upscaled PNG.
  // A texture keeps its original; while its contents match the index it is drawn with the PNG (own mip chain).
  // Opt-in (OWNER 2026-11-14): ?remaster=1, the launcher's 'Texturas del remaster' toggle. The 1.1 GB pack is never in the first load. No index file = off.
  const pack = new Map(), hd = new Map();   // key -> png name; png name -> {view} once loaded, null while loading
  let packed = 0, hdMs = 0;   // hdMs: page-thread ms in pack uploads and view swaps since the last frame report
  // ?hdlog=1: each pack hit once (texture id, size, key, png), to find a texture the pack should not take.
  const hdLog = RN_Q.get('hdlog') === '1' ? new Set() : null;
  if (RN_Q.get('remaster') === '1') {
    // No world textures (STREAML1R*.BUN): OWNER 2026-10-31, the upscaled world pack reads too smooth and badly made; its ?worldhd=1 switch removed 2026-11-19.
    // Pack v2 (tools/remaster/pack_v2.sh: deblock + 4x-UltraSharpV2) overrides the v1 entries it has; ?pack=1 = v1 only.
    // index_fe_v2.tsv (SETS=fe): the front end, HUD and global textures, only in v2.
    const q = RN_Q, v2 = q.get('pack') !== '1';
    // index_bc.tsv (tools/remaster/pack_bc7.py): the same three lists as BC7 .dds, a quarter of the GPU memory of rgba8
    // (title screen: 528 MB -> ~132 MB for its 539 textures); it overrides the keys it has. ?packbc=0 = the webp/png as before.
    const packBc = v2 && BC && q.get('packbc') !== '0';
    const lists = ['remaster/index.tsv', ...(v2 ? ['remaster/index_v2.tsv', 'remaster/index_fe_v2.tsv'] : []),
      ...(packBc ? ['remaster/index_bc.tsv'] : []),
      'remaster/index_glow.tsv'];   // last: tools/remaster/flare_glow.py, the clean round lamp glow wins over any upscale of the flares
    for (const u of lists) try {
      const r = await fetch(u);
      if (r.ok) for (const l of (await r.text()).split('\n')) { const f = l.split('\t'); if (f[1]) pack.set(f[0], f[1]); }
    } catch {}
    // web/remaster_off.tsv: keys the pack made worse (smeared text, melted photos, faded dials): drawn as shipped.
    let off = 0;
    try {
      const r = await fetch('remaster_off.tsv');
      if (r.ok) for (const l of (await r.text()).split('\n')) if (l && l[0] !== '#' && pack.delete(l.split('\t')[0])) off++;
    } catch {}
    if (pack.size) report(`gpu.js: remaster pack ${pack.size} textures (${off} off: remaster_off.tsv)`);
  }
  const HD_MAX = Number(RN_Q.get('hdmax') || 1024);
  // At most HD_NET pack downloads at once (?hdnet=): Chrome opens 6 connections to one host, and the ~1600 world textures
  // a race uploads took all 6, so the game's own reads of the track (host/files.c sync XHR) waited behind them: 6/1 -> race
  // HUD 1.0 s without the world pack, 6.0 s with it, STREAML1RA.BUN reads > 100 ms (build/bench/e_world2, 2026-10-26).
  const HD_NET = Number(RN_Q.get('hdnet') || 3), netQ = [];
  let netN = 0;
  async function hdBlob(url) {
    if (netN < HD_NET) netN++; else await new Promise(r => netQ.push(r));   // a finished download hands its slot over
    try { return await (await fetch(url)).blob(); }
    finally { const next = netQ.shift(); if (next) next(); else netN--; }
  }
  async function loadHd(name) {
    if (name.endsWith('.dds')) return loadDds(`remaster/${name}`);
    // A name with a path is a file under remaster/ (e.g. cars2/<hash>.webp); a bare key is png/<key>.png.
    const blob = await hdBlob(name.includes('/') ? `remaster/${name}` : `remaster/png/${name}.png`);
    const opt = { premultiplyAlpha: 'none', colorSpaceConversion: 'none' };
    // Level 0 is at most HD_MAX on a side (?hdmax=, default 1024): the 2048 car PNGs cost 22 MB each and, with ~80 in a
    // race, made the GPU wait 60-110 ms a frame at 2560x1116 (OWNER 2026-10-22 session).
    const full = await createImageBitmap(blob, opt), f = Math.min(1, HD_MAX / Math.max(full.width, full.height));
    const W = Math.round(full.width * f), H = Math.round(full.height * f);
    const base = f < 1 ? await createImageBitmap(blob, { ...opt, resizeWidth: W, resizeHeight: H, resizeQuality: 'high' }) : full;
    const levels = Math.floor(Math.log2(Math.max(W, H))) + 1;
    const tex = device.createTexture({ size: [W, H], mipLevelCount: levels, format: 'rgba8unorm',
      usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT });
    // The mips are drawn on the GPU from the level above (mipPipe, as the car skins). Decoding the blob again per level
    // (~720 world textures x ~11 levels in the first 4 s of a race) dropped it to 22-30 ms frames, and resizing the
    // bitmap instead still cost 11 % of the page thread in createImageBitmap (build/bench/e_world_q, e_default_p, 2026-10-26).
    if (full !== base) full.close();
    const t = performance.now();
    device.queue.copyExternalImageToTexture({ source: base }, { texture: tex, mipLevel: 0 }, [W, H]);
    base.close();
    const e = device.createCommandEncoder(), mp = getMipPipe();
    for (let l = 1; l < levels; l++) {
      const p = e.beginRenderPass({ colorAttachments: [{ view: tex.createView({ baseMipLevel: l, mipLevelCount: 1 }), loadOp: 'clear', storeOp: 'store' }] });
      p.setPipeline(mp);
      p.setBindGroup(0, device.createBindGroup({ layout: mp.getBindGroupLayout(0), entries: [
        { binding: 0, resource: tex.createView({ baseMipLevel: l - 1, mipLevelCount: 1 }) }, { binding: 1, resource: skinLin }] }));
      p.draw(3); p.end();
    }
    device.queue.submit([e.finish()]);
    hdMs += performance.now() - t;
    return { view: tex.createView() };
  }
  // A BC7 .dds with its mip chain (tools/remaster/pack_bc7.py), gzipped on disk next to it (<name>.gz):
  // no decode on the page thread, a quarter of the VRAM of rgba8.
  async function loadDds(url) {
    if (netN < HD_NET) netN++; else await new Promise(r => netQ.push(r));
    let tex;
    try {
      let r = await fetch(url + '.gz'), gz = r.ok;
      if (!gz) r = await fetch(url);
      // Streamed: each mip goes to writeTexture as soon as its bytes have arrived, so only one level (<= 1 MB) is held
      // at a time, not the whole gunzipped file (ArrayBuffers wait for a GC; the renderer's peak RSS was 1.6 GB at the title).
      const rd = (gz ? r.body.pipeThrough(new DecompressionStream('gzip')) : r.body).getReader();
      let chunk = new Uint8Array(0), pos = 0;
      const take = async n => {
        const out = new Uint8Array(n);
        for (let got = 0; got < n;) {
          if (pos === chunk.length) { const x = await rd.read(); if (x.done) throw new Error('short dds'); chunk = x.value; pos = 0; }
          const k = Math.min(n - got, chunk.length - pos);
          out.set(chunk.subarray(pos, pos + k), got); got += k; pos += k;
        }
        return out;
      };
      const h = await take(148), u = new Uint32Array(h.buffer, 0, 32);
      if (u[0] !== 0x20534444 || u[21] !== 0x30315844 || new Uint32Array(h.buffer, 128, 1)[0] !== 98) throw new Error('not a BC7 dds');
      const H = u[3], W = u[4], levels = u[7];
      tex = device.createTexture({ size: [W, H], mipLevelCount: levels, format: 'bc7-rgba-unorm',
        usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST });
      for (let l = 0; l < levels; l++) {
        const bw = Math.ceil(Math.max(1, W >> l) / 4), bh = Math.ceil(Math.max(1, H >> l) / 4), d = await take(bw * bh * 16), t = performance.now();
        device.queue.writeTexture({ texture: tex, mipLevel: l }, d, { bytesPerRow: bw * 16, rowsPerImage: bh }, [bw * 4, bh * 4]);
        hdMs += performance.now() - t;
      }
      rd.cancel().catch(() => {});
    } finally { const next = netQ.shift(); if (next) next(); else netN--; }
    return { view: tex.createView() };
  }
  function useHd(t, key) {
    const name = pack.get(key);
    if (!name) { t.view = t.own; return; }
    if (hdLog && !hdLog.has(t.id + name)) { hdLog.add(t.id + name); report(`gpu.js: hd ${name} on ${t.id} ${t.w}x${t.h}`); }
    const h = hd.get(name);
    if (h) { t.view = h.view; return; }
    t.view = t.own;
    if (h === null) return;
    hd.set(name, null);
    loadHd(name).then(v => {
      const t = performance.now();
      hd.set(name, v); packed++;
      for (const x of res.values()) if (x.key && pack.get(x.key) === name) x.view = v.view;
      hdMs += performance.now() - t;
    }, e => report(`gpu.js: remaster ${name}: ${e.message}`));
  }

  // Clear of a rectangle: a full-screen triangle under a scissor, writing the color, depth and
  // stencil the D3DCLEAR flags ask for. Uniforms come from a ring with 256-byte steps.
  const clearShader = device.createShaderModule({ code: `
    struct U { color: vec4f, z: f32 };
    @group(0) @binding(0) var<uniform> u: U;
    @vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
      let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u)) * 2.0 - 1.0;
      return vec4f(p, u.z, 1.0);
    }
    struct O { @location(0) c: vec4f };
    @fragment fn fs() -> O { return O(u.color); }
    @fragment fn fs_none() {}` });
  const clearRing = device.createBuffer({ size: 256 * 1024, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
  const clearBgl = device.createBindGroupLayout({ entries: [{ binding: 0, visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
    buffer: { type: 'uniform', hasDynamicOffset: true, minBindingSize: 32 } }] });
  const clearBind = device.createBindGroup({ layout: clearBgl, entries: [{ binding: 0, resource: { buffer: clearRing, size: 32 } }] });
  const clearLayout = device.createPipelineLayout({ bindGroupLayouts: [clearBgl] });
  // BRIDGE: remaster, OWNER 2026-10-22: 4x MSAA on the screen-sized targets, opt-in with ?msaa=4. Off by default since
  // 2026-10-25: in a race at 2560x1116 GPU time per frame (timestamp-query) was p50 17.5 ms with it and 7.6 without (bloom
  // on), and the queue behind it gave the OWNER 200-400 ms stalls. The game draws the screen in ~8 passes a frame (scene,
  // the draws after the motion blur, copies, HUD); on Apple's tiled GPUs each one loads and stores every sample of colour and
  // depth (~190 MB a pass). FXAA (below) is the antialiasing when it is off. With it on, each colour target keeps its
  // single-sample texture (what the game samples and presents) and a multisampled twin that the passes draw into and
  // resolve from; depth targets are multisampled themselves. Size decides, so a pass's colour and depth always agree.
  const MSAA = RN_Q.get('msaa') === '4' ? 4 : 1;
  // BRIDGE: FXAA over the 3D scene (FXAA 3.11 quality, T. Lottes, public domain), not in the original. The host sends GPU_FXAA at the first HUD quad of a race
  // frame. Pixels whose neighbourhood has little contrast are returned untouched, so textures keep their detail. ?fxaa=0 turns it off.
  const FXAA_MODE = RN_Q.get('fxaa');   // '0' off, '2' debug: edges in red
  const FXAA_ON = FXAA_MODE !== '0';
  let fxaaMod = null, fxaaPipe = null;
  const getFxaaMod = () => fxaaMod ??= device.createShaderModule({ code: `
const DBG = ${FXAA_MODE === '2' ? 1 : 0};
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
fn lum(c: vec3f) -> f32 { return dot(c, vec3f(0.299, 0.587, 0.114)); }
fn L(uv: vec2f) -> f32 { return lum(textureSampleLevel(src, smp, uv, 0.0).rgb); }
const Q = array<f32, 12>(1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 2.0, 2.0, 2.0, 2.0, 4.0, 8.0);
@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let rcp = 1.0 / vec2f(textureDimensions(src));
  let uv0 = pos.xy * rcp;
  let m4 = textureSampleLevel(src, smp, uv0, 0.0);
  let lumaM = lum(m4.rgb);
  var lumaN = L(uv0 + vec2f(0.0, -rcp.y)); var lumaS = L(uv0 + vec2f(0.0, rcp.y));
  let lumaW0 = L(uv0 + vec2f(-rcp.x, 0.0)); let lumaE0 = L(uv0 + vec2f(rcp.x, 0.0));
  let rangeMax = max(max(lumaN, lumaW0), max(lumaE0, max(lumaS, lumaM)));
  let rangeMin = min(min(lumaN, lumaW0), min(lumaE0, min(lumaS, lumaM)));
  let range = rangeMax - rangeMin;
  if (range < max(0.0625, rangeMax * 0.125)) { return m4; }
  if (DBG == 1) { return vec4f(1.0, 0.0, 0.0, m4.a); }
  let lumaNW = L(uv0 + vec2f(-rcp.x, -rcp.y)); let lumaNE = L(uv0 + vec2f(rcp.x, -rcp.y));
  let lumaSW = L(uv0 + vec2f(-rcp.x, rcp.y)); let lumaSE = L(uv0 + vec2f(rcp.x, rcp.y));
  let lumaNS = lumaN + lumaS; let lumaWE = lumaW0 + lumaE0;
  let subpixNSWE = lumaNS + lumaWE;
  let edgeHorz1 = -2.0 * lumaM + lumaNS; let edgeVert1 = -2.0 * lumaM + lumaWE;
  let lumaNESE = lumaNE + lumaSE; let lumaNWNE = lumaNW + lumaNE;
  let edgeHorz2 = -2.0 * lumaE0 + lumaNESE; let edgeVert2 = -2.0 * lumaN + lumaNWNE;
  let lumaNWSW = lumaNW + lumaSW; let lumaSWSE = lumaSW + lumaSE;
  let edgeHorz4 = abs(edgeHorz1) * 2.0 + abs(edgeHorz2); let edgeVert4 = abs(edgeVert1) * 2.0 + abs(edgeVert2);
  let edgeHorz3 = -2.0 * lumaW0 + lumaNWSW; let edgeVert3 = -2.0 * lumaS + lumaSWSE;
  let edgeHorz = abs(edgeHorz3) + edgeHorz4; let edgeVert = abs(edgeVert3) + edgeVert4;
  let subpixNWSWNESE = lumaNWSW + lumaNESE;
  let horzSpan = edgeHorz >= edgeVert;
  var lengthSign = rcp.x;
  let subpixA = subpixNSWE * 2.0 + subpixNWSWNESE;
  if (!horzSpan) { lumaN = lumaW0; lumaS = lumaE0; } else { lengthSign = rcp.y; }
  let subpixB = subpixA * (1.0 / 12.0) - lumaM;
  let gradientN = lumaN - lumaM; let gradientS = lumaS - lumaM;
  var lumaNN = lumaN + lumaM; let lumaSS = lumaS + lumaM;
  let pairN = abs(gradientN) >= abs(gradientS);
  let gradient = max(abs(gradientN), abs(gradientS));
  if (pairN) { lengthSign = -lengthSign; }
  let subpixC = clamp(abs(subpixB) / range, 0.0, 1.0);
  var posB = uv0;
  let offNP = select(vec2f(0.0, rcp.y), vec2f(rcp.x, 0.0), horzSpan);
  if (!horzSpan) { posB.x = posB.x + lengthSign * 0.5; } else { posB.y = posB.y + lengthSign * 0.5; }
  var posN = posB - offNP * Q[0]; var posP = posB + offNP * Q[0];
  let subpixD = -2.0 * subpixC + 3.0;
  var lumaEndN = L(posN); let subpixE = subpixC * subpixC; var lumaEndP = L(posP);
  if (!pairN) { lumaNN = lumaSS; }
  let gradientScaled = gradient * 0.25;
  let lumaMM = lumaM - lumaNN * 0.5;
  let subpixF = subpixD * subpixE;
  let lumaMLTZero = lumaMM < 0.0;
  lumaEndN = lumaEndN - lumaNN * 0.5; lumaEndP = lumaEndP - lumaNN * 0.5;
  var doneN = abs(lumaEndN) >= gradientScaled; var doneP = abs(lumaEndP) >= gradientScaled;
  for (var i = 1; i < 12 && !(doneN && doneP); i++) {
    if (!doneN) { posN = posN - offNP * Q[i]; lumaEndN = L(posN) - lumaNN * 0.5; doneN = abs(lumaEndN) >= gradientScaled; }
    if (!doneP) { posP = posP + offNP * Q[i]; lumaEndP = L(posP) - lumaNN * 0.5; doneP = abs(lumaEndP) >= gradientScaled; }
  }
  let dstN = select(uv0.y - posN.y, uv0.x - posN.x, horzSpan);
  let dstP = select(posP.y - uv0.y, posP.x - uv0.x, horzSpan);
  let directionN = dstN < dstP;
  let lumaEndG = select(lumaEndP, lumaEndN, directionN);
  let goodSpan = (lumaEndG < 0.0) != lumaMLTZero;
  let spanLength = dstP + dstN;
  let dstM = select(dstP, dstN, directionN);
  let pixelOffset = dstM * (-1.0 / spanLength) + 0.5;
  let pixelOffsetGood = select(0.0, pixelOffset, goodSpan);
  let pixelOffsetSubpix = max(pixelOffsetGood, subpixF * subpixF * 0.75);
  var uv = uv0;
  if (!horzSpan) { uv.x = uv.x + pixelOffsetSubpix * lengthSign; } else { uv.y = uv.y + pixelOffsetSubpix * lengthSign; }
  return vec4f(textureSampleLevel(src, smp, uv, 0.0).rgb, m4.a);
}` });
  const getFxaaPipe = () => {
    if (!fxaaPipe) {
      const mod = getFxaaMod();
      fxaaPipe = device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
        fragment: { module: mod, entryPoint: 'fs', targets: [{ format: 'rgba8unorm' }] }, primitive: { topology: 'triangle-list' } });
    }
    return fxaaPipe;
  };
  const fxaaSamp = device.createSampler({ magFilter: 'linear', minFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' });
  let fxaaTmp = null, fxaaView = null, fxaaBg = null;
  // BRIDGE: remaster, the last step of a frame. The back buffer is at most 2560 wide (web/index.html), so on the OWNER's
  // window (1920x871 css, dpr 2) Chrome stretched 2560x1160 to 3840x1742 with a bilinear filter: a soft image. The present
  // now draws it into a canvas at the window's device pixels through AMD FidelityFX CAS (MIT; its upscaling path: the four
  // nearest texels each sharpened by their contrast, then blended), so the 1.5x upscale keeps edges and text crisp.
  // ?sharp=0..1 is CAS's sharpness (default 0.5); ?sharp=off = the old copy at the back buffer size.
  const SHARP_Q = RN_Q.get('sharp'), SHARP = SHARP_Q === 'off' ? -1 : Number(SHARP_Q ?? 0.5);
  let casMod = null, casPipe = null;
  const getCasMod = () => casMod ??= device.createShaderModule({ code: `
struct U { scale: vec2f, peak: f32, pad: f32, inMax: vec2i };
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var<uniform> u: U;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
fn T(p: vec2i) -> vec3f { return textureLoad(src, clamp(p, vec2i(0), u.inMax), 0).rgb; }
// Weight of one quadrant's sharpening: CAS's soft min/max over a cross of 5 texels.
fn amp(a: vec3f, b: vec3f, c: vec3f, d: vec3f, e: vec3f, mn: ptr<function, f32>, mx: ptr<function, f32>) -> vec3f {
  let lo = min(min(min(a, b), min(c, d)), e);
  let hi = max(max(max(a, b), max(c, d)), e);
  *mn = lo.g; *mx = hi.g;
  return sqrt(clamp(min(lo, 2.0 - hi) / max(hi, vec3f(1e-5)), vec3f(0.0), vec3f(1.0))) * u.peak;
}
@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  //    b c
  //  e f g h
  //  i j k l
  //    n o
  var pp = pos.xy * u.scale - 0.5;
  let fp = floor(pp); pp -= fp;
  let q = vec2i(fp);
  let b = T(q + vec2i(0, -1)); let c = T(q + vec2i(1, -1));
  let e = T(q + vec2i(-1, 0)); let f = T(q); let g = T(q + vec2i(1, 0)); let h = T(q + vec2i(2, 0));
  let i = T(q + vec2i(-1, 1)); let j = T(q + vec2i(0, 1)); let k = T(q + vec2i(1, 1)); let l = T(q + vec2i(2, 1));
  let n = T(q + vec2i(0, 2)); let o = T(q + vec2i(1, 2));
  var mnf: f32; var mxf: f32; var mng: f32; var mxg: f32; var mnj: f32; var mxj: f32; var mnk: f32; var mxk: f32;
  let wf = amp(b, e, f, g, j, &mnf, &mxf); let wg = amp(c, f, g, h, k, &mng, &mxg);
  let wj = amp(f, i, j, k, n, &mnj, &mxj); let wk = amp(g, j, k, l, o, &mnk, &mxk);
  // bilinear weights of the four results, thinned where the quadrant has contrast (hides the bilinear on diagonals)
  let s = (1.0 - pp.x) * (1.0 - pp.y) / (1.0 / 32.0 + mxf - mnf);
  let t = pp.x * (1.0 - pp.y) / (1.0 / 32.0 + mxg - mng);
  let uu = (1.0 - pp.x) * pp.y / (1.0 / 32.0 + mxj - mnj);
  let v = pp.x * pp.y / (1.0 / 32.0 + mxk - mnk);
  let qbe = wf * s; let qch = wg * t; let qir = wj * uu; let qlo = wk * v;
  let qf = wg * t + wj * uu + s; let qg = wf * s + wk * v + t;
  let qj = wf * s + wk * v + uu; let qk = wg * t + wj * uu + v;
  let sum = (b + e) * qbe + (c + h) * qch + (i + n) * qir + (l + o) * qlo + f * qf + g * qg + j * qj + k * qk;
  return vec4f(clamp(sum / (2.0 * (qbe + qch + qir + qlo) + qf + qg + qj + qk), vec3f(0.0), vec3f(1.0)), 1.0);
}` });
  const getCasPipe = () => {
    if (!casPipe) {
      const mod = getCasMod();
      casPipe = device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
        fragment: { module: mod, entryPoint: 'fs', targets: [{ format: 'rgba8unorm' }] }, primitive: { topology: 'triangle-list' } });
    }
    return casPipe;
  };
  const casU = device.createBuffer({ size: 32, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
  const casBgs = new WeakMap();
  // The canvas's size in device pixels (what the screen shows), kept by a ResizeObserver.
  let disp = null;
  if (SHARP >= 0) new ResizeObserver(([e]) => {
    const b = e.devicePixelContentBoxSize?.[0];
    disp = b ? [b.inlineSize, b.blockSize] : [Math.round(e.contentRect.width * devicePixelRatio), Math.round(e.contentRect.height * devicePixelRatio)];
  }).observe(canvas);
  // BRIDGE: bloom over the 3D scene, not in the original (docs/archive/PLAN.md block 5). PC NFSU1 has its own light glow and
  // streaks (0x409b70, PATCH 0x409bdb), and it is the sharpest of the four versions, so this one only lifts what is
  // already near white: a quarter-size bright pass (luma over 0.72), a separable 9-tap Gaussian, added back with weight
  // 0.2. It runs at GPU_FXAA (the first HUD quad: the scene is done, the HUD comes after) and adds into the multisampled
  // twin too, so the HUD pass's resolve keeps it. ?bloom=0 turns it off; ?bloom=split = only the right half (A/B in one frame).
  // ?bloom=lights (OWNER 2026-10-27, "the lights and how they look"): street lamps, neon and headlights glow wider: the
  // bright pass starts at luma 0.55 and adds back at 0.35 (the default lifts only near-white, 0.72 at 0.2).
  const BLOOM_MODE = RN_Q.get('bloom'), BLOOM_ON = BLOOM_MODE !== '0';
  const [BLOOM_T, BLOOM_W] = BLOOM_MODE?.startsWith('lights') ? ['0.55', '0.35'] : ['0.72', '0.2'];   // lights-split: A/B
  let bloomMod = null, bloomPipes = null;
  const getBloomMod = () => bloomMod ??= device.createShaderModule({ code: `
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;
struct V { @builtin(position) p: vec4f, @location(0) uv: vec2f };
@vertex fn vs(@builtin(vertex_index) i: u32) -> V {
  let xy = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return V(vec4f(xy * 2.0 - 1.0, 0.0, 1.0), vec2f(xy.x, 1.0 - xy.y));
}
@fragment fn bright(v: V) -> @location(0) vec4f {
  let t = 1.0 / vec2f(textureDimensions(src));
  let c = 0.25 * (textureSampleLevel(src, smp, v.uv + vec2f(-t.x, -t.y), 0.0).rgb + textureSampleLevel(src, smp, v.uv + vec2f(t.x, -t.y), 0.0).rgb
    + textureSampleLevel(src, smp, v.uv + vec2f(-t.x, t.y), 0.0).rgb + textureSampleLevel(src, smp, v.uv + vec2f(t.x, t.y), 0.0).rgb);
  let l = dot(c, vec3f(0.299, 0.587, 0.114));
  return vec4f(c * smoothstep(${BLOOM_T}, 1.0, l), 1.0);
}
fn blur(uv: vec2f, d: vec2f) -> vec4f {
  let w = array<f32, 5>(0.2270270, 0.1945946, 0.1216216, 0.0540540, 0.0162162);
  var c = textureSampleLevel(src, smp, uv, 0.0).rgb * w[0];
  for (var k = 1; k < 5; k++) {
    c += (textureSampleLevel(src, smp, uv + d * f32(k), 0.0).rgb + textureSampleLevel(src, smp, uv - d * f32(k), 0.0).rgb) * w[k];
  }
  return vec4f(c, 1.0);
}
@fragment fn blurH(v: V) -> @location(0) vec4f { return blur(v.uv, vec2f(1.0 / f32(textureDimensions(src).x), 0.0)); }
@fragment fn blurV(v: V) -> @location(0) vec4f { return blur(v.uv, vec2f(0.0, 1.0 / f32(textureDimensions(src).y))); }
@fragment fn add(v: V) -> @location(0) vec4f {
  let k = select(${BLOOM_W}, ${BLOOM_W} * step(0.5, v.uv.x), ${BLOOM_MODE?.endsWith('split') ? 'true' : 'false'});
  return vec4f(textureSampleLevel(src, smp, v.uv, 0.0).rgb * k, 0.0);
}` });
  const bloomPipe = (fs, sc) => {
    const mod = getBloomMod();
    return device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
      fragment: { module: mod, entryPoint: fs, targets: [{ format: 'rgba8unorm', ...(fs === 'add' ? { blend: {
        color: { srcFactor: 'one', dstFactor: 'one', operation: 'add' }, alpha: { srcFactor: 'zero', dstFactor: 'one', operation: 'add' } } } : {}) }] },
      primitive: { topology: 'triangle-list' }, multisample: { count: sc } });
  };
  const getBloomPipes = () => bloomPipes ??= { bright: bloomPipe('bright', 1), blurH: bloomPipe('blurH', 1), blurV: bloomPipe('blurV', 1), add: new Map() };
  // A resource replaced while the frame is being encoded is destroyed after the frame's submit: the game reuses a
  // buffer or texture id mid-frame (GPU_BUFFER on a live id), and destroying it at once made WebGPU reject the whole
  // frame's command buffer ("used in submit while destroyed": 2 frames lost per race, build/bench/f_default_bc7).
  const doomed = [], doom = x => { if (x) doomed.push(x); };
  let bloomA = null, bloomB = null;
  function bloom(enc, rt) {
    const bw = Math.max(1, rt.w >> 2), bh = Math.max(1, rt.h >> 2);
    if (!bloomA || bloomA.width !== bw || bloomA.height !== bh) {
      doom(bloomA); doom(bloomB);
      const mk = () => device.createTexture({ size: [bw, bh], format: 'rgba8unorm', usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING });
      bloomA = mk(); bloomB = mk();
    }
    const step = (pipe, from, att, lab) => {
      const p = enc.beginRenderPass({ timestampWrites: tsw(lab), colorAttachments: [att] });
      p.setPipeline(pipe);
      p.setBindGroup(0, device.createBindGroup({ layout: pipe.getBindGroupLayout(0),
        entries: [{ binding: 0, resource: from.createView() }, { binding: 1, resource: fxaaSamp }] }));
      p.draw(3);
      p.end();
    };
    const to = t => ({ view: t.createView(), loadOp: 'clear', clearValue: [0, 0, 0, 1], storeOp: 'store' });
    const bp = getBloomPipes();
    step(bp.bright, rt.tex, to(bloomA), 'bloom bright');
    step(bp.blurH, bloomA, to(bloomB), 'bloom blur');
    step(bp.blurV, bloomB, to(bloomA), 'bloom blur');
    const sc = rt.msView ? rt.sc : 1;
    if (!bp.add.has(sc)) bp.add.set(sc, bloomPipe('add', sc));
    step(bp.add.get(sc), bloomA, colorAtt(rt), 'bloom add');
  }

  // BRIDGE: PS2 speed blur with the scene's real depth, not in the PC game. Source: SLUS_208.11 0x113fc8 (read in the corpus C and the
  // ELF data 2026-10-27; ref/docs/re/postfx-elf.md section 4). The PS2 copies the frame into a texture whose alpha is
  // min(depth_byte * k, 255) (k = 2), then draws it back over the frame, one pass per offset (2.3 6.4 8.8 11.4 px at 512 x 448), each
  // copy stretched along the car's velocity in camera space (x, y, z, normalised; y down, as here): rect X0 = -(x+z) o, X1 = W + (z-x) o,
  // Y0 = -(y+z) o, Y1 = H + (z-y) o, o = offset_i * c, c = 2. Vertex alpha 50 35 28 17 (/128), times t, the speed ramp
  // below (speed in m/s, |[0x740500]+0x1e0|). The GS modulates the texture alpha by the vertex alpha (As = At * Af / 128) and blends
  // Cs * As + Cd * (1 - As), 128 = 1.
  // Nitrous (the game's [0x73654c], the PS2's view +0x50): a counter climbs 2 a frame to 15 and falls 1 a frame; k = 2 + 13 r and
  // c = 2 + 2 r (r = counter / 15); passes 5-6 (22 and 40 px, alpha 8 r and 4 r) join, and while it is active every copy is tinted
  // (130 + 10 i, 130 + 10 i, 130 + 28 i) / 128 for pass i (the PS2's table 0x44a680; plain 130 / 128 otherwise).
  // The depth byte (scratchpad RE 2026-10-27, SLUS FUN_00112ba8 + FUN_00113fc8, projection FUN_0010a7f8): Z24 bits 15:8, Z24 linear in
  // 1/z, so byte = z <= 128 N ? 254 : 32768 N / z (N = camera near, lens default 0.5 m, FUN_001b1200), and the sky (no Z) 0: the near
  // road and walls take the full copy, the far city little, the sky none. Here the depth buffer is turned into metres (z_ndc = _33 +
  // _43 / z). ?psweight=ps2 takes that weight (?psnear=N); it also streaks the player's car, which the PS2 keeps sharp (its draw order
  // against FUN_00113fc8 is still unread), so the default stays the reverse weight: 255 * metres / ?psfar, far = strong.
  // Offsets scale with the resolution per axis (W / 512, H / 448). It runs on the scene colour (not the FXAA target: that one holds
  // the light trails and the HUD), after the game's own blur, which must be off (web/tune.js 'PS2 depth' sets its cap to 0), before the
  // HUD. ?psblur=0 off, ?psblur=depth shows the weight (debug), ?psblur=split = the right half only (A/B in one frame),
  // ?psspeed=57 a still scene as if driving straight at 57 m/s.
  const PS_DBG = RN_Q.get('psblur') === 'depth', PS_SPLIT = RN_Q.get('psblur') === 'split';   // split: the pass on the right half only (A/B in one frame)
  // The speed ramp. Both games read the same input, the view-1 camera's velocity |[0x740500] + 0x1e0| ([0x740500] = camera 0x78d270,
  // set by 0x40a7f0; PC 0x40cd40, PS2 0x113fc8 via view +0x40); measured 2026-10-27 within ~1 % of the car's own speed (+0x3d4, the
  // HUD's), 0 -> 27 m/s in 3 s from a launch. They ramp it differently: Speed.exe 0x702a38 / 0x702a3c / 0x702a40 = 25 -> 125 m/s, cap 0.65 (no blur under 90 km/h);
  // SLUS 0x4ff95c / 0x4ff960 / 0x4ff954 = 0.1 -> 25 m/s, cap 1 (full blur ~3 s after a launch here). OWNER 2026-10-27: "agresivo desde el
  // arranque", so the PC exe's ramp is the default; ?psramp=ps2 the PS2's.
  const PS_RAMP = RN_Q.get('psramp') === 'ps2' ? [0.1, 25, 1] : [25, 125, 0.65];
  const PS_FORCE = Number(RN_Q.get('psspeed') || 0);   // debug: a still scene as if driving straight at this many m/s (?psspeed=57)
  const PS_OFF = [2.3, 6.4, 8.8, 11.4, 22, 40], PS_ALPHA = [50, 35, 28, 17];
  const PS_FAR = Number(RN_Q.get('psfar') || 200);   // metres where the depth byte reaches 255 (not with ?psweight=ps2)
  const PS_W2 = RN_Q.get('psweight') === 'ps2', PS_NEAR = Number(RN_Q.get('psnear') || 0.5);
  let psMod = null;
  const getPsMod = () => psMod ??= device.createShaderModule({ code: `
struct U { rect: vec4f, par: vec4f, zz: vec4f, tint: vec4f };
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var dep: texture_depth_2d;
@group(0) @binding(2) var smp: sampler;
@group(0) @binding(3) var<uniform> u: U;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let uv = (pos.xy - u.rect.xy) / (u.rect.zw - u.rect.xy);
  if (any(uv < vec2f(0.0)) || any(uv > vec2f(1.0)) || pos.x < u.par.z) { discard; }
  let col = textureSampleLevel(src, smp, uv, 0.0).rgb;
  let dsz = vec2f(textureDimensions(dep));
  let zn = textureLoad(dep, vec2i(clamp(uv * dsz, vec2f(0.0), dsz - 1.0)), 0);
  // metres from the camera: z_ndc = _33 + _43 / z. The far clear (1.0) is the sky.
  let zv = select(u.zz.z, u.zz.y / (zn - u.zz.x), zn < 0.99999);
  let far = 255.0 * clamp(zv / u.zz.z, 0.0, 1.0);
  let ps2 = select(0.0, select(min(floor(32768.0 * u.zz.z / zv), 254.0), 254.0, zv <= 128.0 * u.zz.z), zn < 0.99999);
  let byte = select(far, ps2, u.zz.w > 0.5);
  let at = min(byte * u.par.y, 255.0);                  // CLUT alpha
  let a = min(at * u.par.x / 128.0, 255.0) / 128.0;     // x vertex alpha (par.x = Af * t), GS modulate then blend weight
  if (${PS_DBG ? 'true' : 'false'}) { return vec4f(vec3f(at / 255.0), 1.0); }
  return vec4f(min(col * u.tint.rgb, vec3f(1.0)), a);
}` });
  const psPipes = new Map();
  const getPsPipe = () => {
    if (!psPipes.has(0)) {
      const mod = getPsMod();
      psPipes.set(0, device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
        fragment: { module: mod, entryPoint: 'fs', targets: [{ format: 'rgba8unorm', blend: {
          color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha', operation: 'add' },
          alpha: { srcFactor: 'zero', dstFactor: 'one', operation: 'add' } } }] }, primitive: { topology: 'triangle-list' } }));
    }
    return psPipes.get(0);
  };
  const psPipe = getPsPipe;
  const psU = Array.from({ length: 6 }, () => device.createBuffer({ size: 64, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST }));
  const PS_LOG = RN_Q.get('pslog') === '1';
  let psN = 0, psTmp = null, psCount = 0;
  const psBase = (v) => { const z = Math.hypot(v[0], v[1], v[2]); return z > 0.5; };
  function psblur(enc, rt, ds, v, nitro) {
    // v: x y z (unit velocity in camera space), speed (m/s), (nitro bits), _33, _43
    if (PS_LOG && ++psN % 120 === 1) report(`gpu.js: psblur ds ${ds ? `${ds.w}x${ds.h} sc ${ds.sc} depth ${ds.depth}` : 'none'} rt ${rt.w}x${rt.h} v ${Array.from(v).map(x => x.toFixed(3)).join(' ')} nitro ${nitro}`);
    if (PS_FORCE) v = Float32Array.of(0, 0, 1, PS_FORCE, 0, v[5], v[6]);
    if (!ds || !ds.depth || ds.sc !== 1 || ds.w !== rt.w || ds.h !== rt.h || !psBase(v)) return;
    const t = Math.min(PS_RAMP[2], Math.max(0, Math.min(1, (v[3] - PS_RAMP[0]) / (PS_RAMP[1] - PS_RAMP[0]))));
    psCount = nitro ? Math.min(15, psCount + 2) : Math.max(0, psCount - 1);   // one step per race frame
    const r = psCount / 15, active = nitro || psCount > 0, k = 2 + 13 * r, c = 2 + 2 * r;
    if (t <= 0) return;
    if (!psTmp || psTmp.width !== rt.w || psTmp.height !== rt.h) {
      doom(psTmp);
      psTmp = device.createTexture({ size: [rt.w, rt.h], format: 'rgba8unorm', usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.TEXTURE_BINDING });
    }
    enc.copyTextureToTexture({ texture: rt.tex }, { texture: psTmp }, [rt.w, rt.h]);
    const pipe = psPipe(), W = rt.w, Hh = rt.h, sx = W / 512, sy = Hh / 448;
    const srcV = psTmp.createView(), depV = ds.tex.createView({ aspect: 'depth-only' });
    const n = active ? 6 : 4;
    for (let i = 0; i < n; i++) {
      const ox = PS_OFF[i] * c * sx, oy = PS_OFF[i] * c * sy, x = v[0], y = v[1], z = v[2];
      device.queue.writeBuffer(psU[i], 0, new Float32Array([
        -(x + z) * ox, -(y + z) * oy, W + (z - x) * ox, Hh + (z - y) * oy,
        Math.floor((i === 4 ? 8 * r : i === 5 ? 4 * r : PS_ALPHA[i]) * t), k, PS_SPLIT ? W / 2 : 0, 0,
        v[5], v[6], PS_W2 ? PS_NEAR : PS_FAR, PS_W2 ? 1 : 0,
        ...(active ? [(130 + 10 * i) / 128, (130 + 10 * i) / 128, (130 + 28 * i) / 128, 0] : [130 / 128, 130 / 128, 130 / 128, 0])]));
      const p = enc.beginRenderPass({ timestampWrites: tsw('psblur'), colorAttachments: [{ view: rt.view, loadOp: 'load', storeOp: 'store' }] });
      p.setPipeline(pipe);
      p.setBindGroup(0, device.createBindGroup({ layout: pipe.getBindGroupLayout(0), entries: [
        { binding: 0, resource: srcV }, { binding: 1, resource: depV }, { binding: 2, resource: fxaaSamp }, { binding: 3, resource: { buffer: psU[i] } }] }));
      p.draw(3);
      p.end();
    }
  }
  const msFor = (w, h) => MSAA > 1 && w >= 1000 && h >= 500 ? MSAA : 1;
  const colorAtt = rt => rt.msView ? { view: rt.msView, resolveTarget: rt.view, loadOp: 'load', storeOp: 'store' }
    : { view: rt.view, loadOp: 'load', storeOp: 'store' };
  const IN_CL = [];      // commands that open, close or clear passes
  for (const op of [GPU_TARGET, GPU_CLEAR, GPU_DRAW, GPU_FXAA, GPU_PRESENT]) IN_CL[op] = true;
  const cl = [];
  const clearPipes = new Map();
  function clearPipe(hasColor, hasDepth, flags, sc) {
    const key = `${hasColor}${hasDepth}${flags}${sc}`;
    if (clearPipes.has(key)) return clearPipes.get(key);
    const st = { compare: 'always', passOp: (flags & 4) ? 'replace' : 'keep' };
    const p = device.createRenderPipeline({ layout: clearLayout,
      vertex: { module: clearShader, entryPoint: 'vs' },
      fragment: { module: clearShader, entryPoint: hasColor ? 'fs' : 'fs_none',
        targets: hasColor ? [{ format: 'rgba8unorm', writeMask: (flags & 1) ? GPUColorWrite.ALL : 0 }] : [] },
      primitive: { topology: 'triangle-list' }, multisample: { count: sc },
      depthStencil: hasDepth ? { format: 'depth24plus-stencil8', depthWriteEnabled: !!(flags & 2), depthCompare: 'always',
        stencilFront: st, stencilBack: st, stencilWriteMask: (flags & 4) ? 0xff : 0 } : undefined });
    clearPipes.set(key, p);
    return p;
  }

  // ---- draws: one uniform block per draw (dynamic offset), textures + samplers in group 1 ----
  const drawBgl = device.createBindGroupLayout({ entries: [{ binding: 0, visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
    buffer: { type: 'uniform', hasDynamicOffset: true, minBindingSize: U_SIZE } }] });
  const texBgls = new Map();      // tex mask -> layout
  function texBgl(mask) {
    if (!texBgls.has(mask)) {
      const entries = [];
      for (let k = 0; k < 8; k++) if (mask >> k & 1) {
        entries.push({ binding: 2 * k, visibility: GPUShaderStage.FRAGMENT, sampler: { type: 'filtering' } });
        entries.push({ binding: 2 * k + 1, visibility: GPUShaderStage.FRAGMENT, texture: { sampleType: 'float' } });
        entries.push({ binding: 16 + k, visibility: GPUShaderStage.FRAGMENT, texture: { sampleType: 'float', viewDimension: 'cube' } });
      }
      texBgls.set(mask, device.createBindGroupLayout({ entries }));
    }
    return texBgls.get(mask);
  }
  const layouts = new Map();
  function drawLayout(mask) {
    if (!layouts.has(mask)) layouts.set(mask, device.createPipelineLayout({ bindGroupLayouts: [drawBgl, texBgl(mask)] }));
    return layouts.get(mask);
  }
  // Unbound stage: opaque black (what Wine binds; the D3D9 docs leave it open).
  const dummy = device.createTexture({ size: [1, 1], format: 'rgba8unorm', usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST });
  device.queue.writeTexture({ texture: dummy }, new Uint8Array([0, 0, 0, 255]), { bytesPerRow: 4 }, [1, 1]);
  const dummyView = dummy.createView();
  const dummyCube = device.createTexture({ size: [1, 1, 6], format: 'rgba8unorm', usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST });
  device.queue.writeTexture({ texture: dummyCube }, new Uint8Array(24).map((_, i) => i % 4 === 3 ? 255 : 0),
    { bytesPerRow: 4, rowsPerImage: 1 }, [1, 1, 6]);
  const dummyCubeView = dummyCube.createView({ dimension: 'cube' });
  const ANISO = Number(RN_Q.get('aniso') ?? 16);   // ?aniso=1 turns the bridge off
  const samplers = new Map();
  function samplerFrom(w, to) {
    const auv = w[to + T_AU], avv = w[to + T_AV], mag = w[to + T_MAG], min = w[to + T_MIN], mip = w[to + T_MIP], aniso = w[to + T_ANISO];
    const key = (auv < 16 && avv < 16 && mag < 16 && min < 16 && mip < 16 && aniso < 256)
      ? (auv | (avv << 4) | (mag << 8) | (min << 12) | (mip << 16) | (aniso << 20))
      : `${auv},${avv},${mag},${min},${mip},${aniso}`;
    let s = samplers.get(key);
    if (s) return s;
    const au = ADDRESS[auv], av = ADDRESS[avv];
    if (!au || !av) fail(`texture address ${auv}/${avv}`);
    const filt = f => f >= 2 ? 'linear' : 'nearest';
    const d = { addressModeU: au, addressModeV: av, magFilter: filt(mag), minFilter: filt(min),
      mipmapFilter: mip === 2 ? 'linear' : 'nearest' };
    if (!mip) d.lodMaxClamp = 0;      // D3DTEXF_NONE: level 0 only
    if ((min === 3 || mag === 3) && mip === 2) d.maxAnisotropy = Math.min(16, Math.max(1, aniso));
    // BRIDGE: remaster, OWNER 2026-10-22: every linear sampler of a mipmapped texture is trilinear with 16x anisotropy
    // (the game asks for point mips or no anisotropy). WebGPU needs all three filters linear for maxAnisotropy > 1.
    if (ANISO > 1 && mip && filt(min) === 'linear' && filt(mag) === 'linear') { d.mipmapFilter = 'linear'; d.maxAnisotropy = ANISO; }
    s = device.createSampler(d);
    samplers.set(key, s);
    return s;
  }
  function sampler(t) { return samplerFrom(t, 0); }
  function blendState(w, hdr) {
    if (!w[hdr + D_BLEND]) return undefined;
    const comp = (src, dst, op) => {
      let s = BLEND[src], d = BLEND[dst];
      if (src === 12) { s = 'src-alpha'; d = 'one-minus-src-alpha'; }       // BOTHSRCALPHA
      if (src === 13) { s = 'one-minus-src-alpha'; d = 'src-alpha'; }       // BOTHINVSRCALPHA
      if (!s || !d || !BLENDOP[op]) fail(`blend ${src}/${dst}/${op}`);
      if (op >= 4) { s = 'one'; d = 'one'; }                                 // MIN/MAX ignore the factors
      return { srcFactor: s, dstFactor: d, operation: BLENDOP[op] };
    };
    const color = comp(w[hdr + D_SRCB], w[hdr + D_DSTB], w[hdr + D_BOP]);
    return { color, alpha: w[hdr + D_SEPA] ? comp(w[hdr + D_SRCBA], w[hdr + D_DSTBA], w[hdr + D_BOPA]) : color };
  }
  // Index size of a draw: resident index buffers keep the game's 16 or 32 bits; payload indices are 32 bits.
  const ifmt = (w, hdr) => w[hdr + D_RIB] && w[hdr + D_RIFMT] === 2 ? 'uint16' : 'uint32';
  const gbufs = new Map();   // resident vertex / index buffers (GPU_BUFFER): id -> GPUBuffer
  // ?warm=1 (OFF by default; th0mk/nfsu2-web encoder.ts loadWarm/warmUp): each new pipeline is remembered in localStorage
  // by its shader texts' hashes, its declaration and the draw state it reads; the next session builds them with
  // createRenderPipelineAsync as soon as those shaders and that declaration exist, so a first draw finds its pipeline made
  // (shader ids change between sessions, the texts do not). Same pipelines, same pixels. A draw that comes first still
  // creates it at once. Kept: the last WARM_MAX.
  const WARM = RN_Q.get('warm') === '1', WARM_KEY = 'rn-warm-pipes', WARM_MAX = 4000;
  const WARM_F = [D_TOPO, D_NIDX, D_DS, D_ZEN, D_ZWRITE, D_ZFUNC, D_CULL, D_BLEND, D_SRCB, D_DSTB, D_BOP, D_SEPA, D_SRCBA,
    D_DSTBA, D_BOPA, D_CWRITE, D_RIB, D_RIFMT];
  const hash53 = s => { let a = 0xdeadbeef, b = 0x41c6ce57;
    for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); a = Math.imul(a ^ c, 2654435761); b = Math.imul(b ^ c, 1597334677); }
    a = Math.imul(a ^ a >>> 16, 2246822507) ^ Math.imul(b ^ b >>> 13, 3266489909);
    b = Math.imul(b ^ b >>> 16, 2246822507) ^ Math.imul(a ^ a >>> 13, 3266489909);
    return (b >>> 0).toString(36) + '.' + (a >>> 0).toString(36); };
  const warmShader = new Map(), warmDecl = new Map();   // this session: text hash -> shader id, declaration words -> id
  let warmList = [];
  try { if (WARM) warmList = JSON.parse(localStorage.getItem(WARM_KEY) || '[]'); } catch {}
  const warmSeen = new Set(warmList.map(r => r.k));
  let warmTodo = warmList.slice(), warmSave = 0, warmMade = 0;
  function warmTry() {     // after a shader or declaration arrives: build every remembered pipeline it completes
    if (!warmTodo.length) return;
    warmTodo = warmTodo.filter(r => {
      const vs = warmShader.get(r.vs), ps = warmShader.get(r.ps), dc = warmDecl.get(r.decl);
      if (vs === undefined || ps === undefined || dc === undefined) return true;
      if (shaders.get(vs)?.h !== r.vs || shaders.get(ps)?.h !== r.ps || decls.get(dc)?.sig !== r.decl) return true;
      const h = new Uint32Array(D_HDR);
      WARM_F.forEach((f, i) => { h[f] = r.st[i]; });
      h[D_VS] = vs; h[D_PS] = ps; h[D_DECL] = dc;
      try { pipeline(h, 0, r.stride, r.sc, true); warmMade++; } catch {}
      return false;
    });
  }
  function warmRemember(vs, ps, dc, stride, sc, w, hdr, tail) {
    const k = hash53(`${vs.h} ${ps.h} ${dc.sig} ${tail}`);
    if (warmSeen.has(k)) return;
    warmSeen.add(k);
    warmList.push({ k, vs: vs.h, ps: ps.h, decl: dc.sig, stride, sc, st: WARM_F.map(f => w[hdr + f]) });
    if (!warmSave) warmSave = setTimeout(() => {
      warmSave = 0;
      try { localStorage.setItem(WARM_KEY, JSON.stringify(warmList.slice(-WARM_MAX))); } catch {}
    }, 5000);
  }
  function findPipe(list, tag, stride, topo, ds, zen, zwrite, zfunc, cull, blend, srcb, dstb, bop, sepa, srcba, dstba, bopa, cwrite, sc, fmt) {
    for (let i = 0; i < list.length; i++) {
      const e = list[i];
      if (e.tag === tag && e.stride === stride && e.topo === topo && e.ds === ds && e.zen === zen &&
          e.zwrite === zwrite && e.zfunc === zfunc && e.cull === cull && e.blend === blend &&
          e.srcb === srcb && e.dstb === dstb && e.bop === bop && e.sepa === sepa &&
          e.srcba === srcba && e.dstba === dstba && e.bopa === bopa && e.cwrite === cwrite &&
          e.sc === sc && e.fmt === fmt) return e.p;
    }
    return null;
  }
  function pipeline(w, hdr, stride, sc, warm) {
    const vs = shaders.get(w[hdr + D_VS]), ps = shaders.get(w[hdr + D_PS]), decl = decls.get(w[hdr + D_DECL]);
    if (!vs || !ps || !decl) fail('draw with an unknown shader or declaration');
    const topo = w[hdr + D_TOPO], ds = w[hdr + D_DS] !== 0 ? 1 : 0, zen = w[hdr + D_ZEN], zwrite = w[hdr + D_ZWRITE],
      zfunc = w[hdr + D_ZFUNC], cull = w[hdr + D_CULL], blend = w[hdr + D_BLEND], srcb = w[hdr + D_SRCB],
      dstb = w[hdr + D_DSTB], bop = w[hdr + D_BOP], sepa = w[hdr + D_SEPA], srcba = w[hdr + D_SRCBA],
      dstba = w[hdr + D_DSTBA], bopa = w[hdr + D_BOPA], cwrite = w[hdr + D_CWRITE],
      fmt = (w[hdr + D_RIB] && w[hdr + D_RIFMT] === 2) ? 1 : 0;
    const tag = ((stride << 12) ^ (ds << 11) ^ (zen << 10) ^ (zwrite << 9) ^ (blend << 8) ^ (zfunc << 4) ^ (cull << 2) ^ topo ^ (sc << 20) ^ (fmt << 24)) | 0;
    let m1 = vs._pipes;
    let m2 = m1 && m1.get(ps);
    let list = m2 && m2.get(decl);
    if (list) {
      const hit = findPipe(list, tag, stride, topo, ds, zen, zwrite, zfunc, cull, blend, srcb, dstb, bop, sepa, srcba, dstba, bopa, cwrite, sc, fmt);
      if (hit) return hit;
    }
    if (WARM && !warm) {
      const tail = `,${stride},${topo},${ds !== 0},${zen},${zwrite},${zfunc},${cull},${blend},${srcb},${dstb},${bop},${sepa},${srcba},${dstba},${bopa},${cwrite},${sc},${fmt ? 'uint16' : 'uint32'}`;
      warmRemember(vs, ps, decl, stride, sc, w, hdr, tail);
    }
    const attributes = [];
    for (let k = 0; k < 16; k++) {
      const inp = vs.inputs[k];
      if (!inp) continue;
      const usage = (inp >>> 8) & 255, index = inp & 255;
      const e = decl.find(e => e.stream === 0 && e.usage === usage && e.index === index);
      if (!e) fail(`vs input v${k} (usage ${usage}/${index}) not in the declaration`);
      if (!VFMT[e.type]) fail(`vertex element type ${e.type}`);
      attributes.push({ shaderLocation: k, offset: e.offset, format: VFMT[e.type] });
    }
    const topoStr = topo === 4 ? 'triangle-list' : topo === 5 ? 'triangle-strip' : fail(`topology ${topo}`);
    const cullStr = cull === 3 ? 'back' : cull === 2 ? 'front' : 'none';
    const st = { compare: 'always' };
    const desc = { layout: drawLayout(ps.texMask),
      vertex: { module: vs.module, entryPoint: 'main', buffers: [{ arrayStride: stride, attributes }] },
      fragment: { module: ps.module, entryPoint: 'main',
        targets: [{ format: 'rgba8unorm', blend: blendState(w, hdr), writeMask: cwrite & 15 }] },
      // D3D9 front faces are clockwise on screen; CULL_CCW (the default) culls the back ones.
      multisample: { count: sc },
      primitive: { topology: topoStr, frontFace: 'cw', cullMode: cullStr,
        stripIndexFormat: topoStr === 'triangle-strip' && w[hdr + D_NIDX] ? (fmt ? 'uint16' : 'uint32') : undefined },
      depthStencil: ds ? { format: 'depth24plus-stencil8', depthWriteEnabled: !!(zen && zwrite),
        depthCompare: zen ? CMP[zfunc] : 'always', stencilFront: st, stencilBack: st } : undefined };
    if (!m1) vs._pipes = m1 = new Map();
    if (!m2) m1.set(ps, m2 = new Map());
    if (!list) m2.set(decl, list = []);
    const entry = { tag, stride, topo, ds, zen, zwrite, zfunc, cull, blend, srcb, dstb, bop, sepa, srcba, dstba, bopa, cwrite, sc, fmt, p: null };
    if (warm) {
      device.createRenderPipelineAsync(desc).then(p => {
        if (!findPipe(list, tag, stride, topo, ds, zen, zwrite, zfunc, cull, blend, srcb, dstb, bop, sepa, srcba, dstba, bopa, cwrite, sc, fmt)) {
          entry.p = p;
          list.push(entry);
        }
      }, () => {});
      return null;
    }
    const p = device.createRenderPipeline(desc);
    entry.p = p;
    list.push(entry);
    newPipes++;
    return p;
  }
  let newPipes = 0;     // telemetry: pipelines made in this frame (each is a shader compile in the browser)
  // Per-frame data: vertices, indices and uniforms gathered on the CPU, written once before submit.
  let vbuf = null, ibuf = null, ubuf = null, vcap = 0, icap = 0, ucap = 0;
  const grow = (buf, cap, need, usage) => {
    if (need <= cap) return [buf, cap];
    doom(buf);
    cap = Math.max(need, cap * 2, 1 << 20);
    return [device.createBuffer({ size: cap, usage: usage | GPUBufferUsage.COPY_DST }), cap];
  };
  // Their CPU copies live across frames (allocating per frame made GC pauses). Each draw writes its fixed fields
  // (0..223) followed by its nvc vertex constants (224..), stepped to the 256-byte uniform offset alignment.
  const uni = new ArrayBuffer(256 * 1024), uf = new Float32Array(uni);
  const UOFF_ARR = [0], BF_ARR = [0, 0, 0, 0];
  let vdata = new Uint8Array(0), idata = new Uint32Array(0), udata = new ArrayBuffer(0), udw = null, udf = null,
    uBind = null, uBindBuf = null;
  // Texture bind groups by layout and resources (each GPU object gets a number the first time it is seen).
  const objIds = new WeakMap(), texBinds = new Map();
  let nextObj = 1, texBindCount = 0;
  const oid = o => { let k = objIds.get(o); if (!k) objIds.set(o, k = nextObj++); return k; };
  function makeTexBindGroup(mask, w, a) {
    if (texBindCount >= 8192) { texBinds.clear(); texBindCount = 0; }     // keys of destroyed textures are never asked again
    if (mask === 0) {
      const bg = device.createBindGroup({ layout: texBgl(0), entries: [] });
      texBinds.set(0, bg);
      texBindCount++;
      return bg;
    }
    const entries = [];
    let node = texBinds.get(mask);
    if (!node) texBinds.set(mask, node = new Map());
    let parent = texBinds, lastKey = mask;
    for (let k = 0; k < 8; k++) if ((mask >>> k) & 1) {
      const to = a + D_TEX + D_TEXN * k;
      const tid = w[to + T_ID];
      const img = tid ? res.get(tid) : null, cube = (w[to + T_TT] & T_CUBE) !== 0;
      const smp = samplerFrom(w, to), v2 = (!cube && img?.view) || dummyView, vc = (cube && img?.cube) || dummyCubeView;
      entries.push({ binding: 2 * k, resource: smp }, { binding: 2 * k + 1, resource: v2 }, { binding: 16 + k, resource: vc });
      const sId = oid(smp), v2Id = oid(v2), vcId = oid(vc);
      let m1 = node.get(sId); if (!m1) node.set(sId, m1 = new Map());
      let m2 = m1.get(v2Id); if (!m2) m1.set(v2Id, m2 = new Map());
      parent = m2; lastKey = vcId;
      node = m2.get(vcId);
      if (!node && (mask >>> (k + 1)) !== 0) m2.set(vcId, node = new Map());
    }
    const bg = device.createBindGroup({ layout: texBgl(mask), entries });
    parent.set(lastKey, bg);
    texBindCount++;
    return bg;
  }

  // BRIDGE: HD car skins (host/d3d9.c skin_bridge; OWNER 2026-10-23, remaster scope). GPU_SKIN replays the game's CPU composite
  // 0x5a8a50 of DUMMY_SKINn on the GPU at 4x (at most 2048), with the 512 layers and masks sampled bilinear, so mask edges
  // follow a smooth curve instead of the 512 grid. Per texel, as 0x5a8a50/0x5a8640 do (V, Hopper): m = mask blue byte;
  // m = 0 keeps; a recolour layer first becomes sum_k ftol(colour_k * w_k), w = layer (R, G, B) * 1/255 rounded to f32, only
  // w > 1/255 counted (alpha: the largest term); m >= 128 replaces, 1..127 blends ftol(L * m/128) + ftol(D * (1 - m/128)), alpha
  // summed; every channel stops at 255. Then the marker texels (the 4 colours of the spec) are written.
  // ?skinhd=0 off; ?skinhd=check runs it at 512 with nearest texels and reports the texels that differ from the game's result.
  const SKIN_MODE = RN_Q.get('skinhd');
  let skinMod = null, skinPipe = null, mipMod = null, mipPipe = null;
  const getSkinMod = () => skinMod ??= device.createShaderModule({ code: `
struct U { mode: u32, recolour: u32, nmark: u32, exact: u32, src: vec2f, k: f32, pad: f32, cols: array<vec4f, 4>, marks: array<vec4u, 64> };
@group(0) @binding(0) var prev: texture_2d<f32>;
@group(0) @binding(1) var layer: texture_2d<f32>;
@group(0) @binding(2) var mask: texture_2d<f32>;
@group(0) @binding(3) var smp: sampler;
@group(0) @binding(4) var<uniform> u: U;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
// ftol(c * w) for a colour byte c and an f32 weight w < 2, from the exact product as the x87 makes it: c * mantissa fits 32 bits.
fn mulfloor(c: f32, w: f32) -> f32 {
  let b = bitcast<u32>(w); let e = (b >> 23u) & 255u;
  if (e == 0u || e > 150u || 150u - e >= 32u) { return 0.0; }
  return f32((u32(c) * ((b & 0x7fffffu) | 0x800000u)) >> (150u - e));
}
@fragment fn fs(@builtin(position) p: vec4f) -> @location(0) vec4f {
  let size = vec2f(textureDimensions(prev));
  let uv = p.xy / size;
  var d = round(textureLoad(prev, vec2i(p.xy), 0) * 255.0);
  if (u.mode == 1u) {
    let t = vec2u(uv * u.src); let i = t.y * u32(u.src.x) + t.x;
    for (var m = 0u; m < u.nmark; m++) { if (u.marks[m].x == i) { return u.cols[u.marks[m].y] / 255.0; } }
    return d / 255.0;
  }
  var l = textureSampleLevel(layer, smp, uv, 0.0) * 255.0;
  var m = textureSampleLevel(mask, smp, uv, 0.0).b * 255.0;
  if (u.exact == 1u) { l = round(l); m = round(m); }
  if (m <= 0.0) { return d / 255.0; }
  if (u.recolour == 1u) {
    let w = vec3f(l.r * u.k, l.g * u.k, l.b * u.k);
    var acc = vec3f(0.0); var a = 0.0;
    for (var k = 0u; k < 3u; k++) {
      if (w[k] > u.k) {
        let c = u.cols[k];
        acc += vec3f(mulfloor(c.r, w[k]), mulfloor(c.g, w[k]), mulfloor(c.b, w[k]));
        a = max(a, mulfloor(c.a, w[k]));
      }
    }
    l = min(vec4f(acc, a), vec4f(255.0));
  }
  if (m >= 128.0) { return l / 255.0; }
  let t = m * (1.0 / 128.0); let r = 1.0 - t;
  var s = vec4f(0.0);
  if (t > u.k) { s += floor(l * t); }
  if (r > u.k) { s += floor(d * r); }
  return min(s, vec4f(255.0)) / 255.0;
}` });
  const getMipMod = () => mipMod ??= device.createShaderModule({ code: `
@group(0) @binding(0) var down: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}
@fragment fn fs(@builtin(position) p: vec4f) -> @location(0) vec4f {
  return textureSampleLevel(down, smp, 2.0 * p.xy / vec2f(textureDimensions(down)), 0.0);
}` });
  const getSkinPipe = () => {
    if (!skinPipe) {
      const mod = getSkinMod();
      skinPipe = device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
        fragment: { module: mod, entryPoint: 'fs', targets: [{ format: 'rgba8unorm' }] }, primitive: { topology: 'triangle-list' } });
    }
    return skinPipe;
  };
  const getMipPipe = () => {
    if (!mipPipe) {
      const mod = getMipMod();
      mipPipe = device.createRenderPipeline({ layout: 'auto', vertex: { module: mod, entryPoint: 'vs' },
        fragment: { module: mod, entryPoint: 'fs', targets: [{ format: 'rgba8unorm' }] }, primitive: { topology: 'triangle-list' } });
    }
    return mipPipe;
  };
  const skinLin = device.createSampler({ magFilter: 'linear', minFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' });
  const skinNear = device.createSampler({ magFilter: 'nearest', minFilter: 'nearest' });
  const skinTmp = new Map();     // size -> [ping, pong]
  const argb = c => [(c >>> 16) & 255, (c >>> 8) & 255, c & 255, c >>> 24];
  function skin(w, a) {
    const id = w[a], t = res.get(id);     // id read now: w is the frame list, reused by the time a check reports
    if (!t || SKIN_MODE === '0') return;
    const check = SKIN_MODE === 'check', S = check ? t.w : Math.min(2048, 4 * t.w);
    if (!skinTmp.has(S)) skinTmp.set(S, [0, 1].map(() => device.createTexture({ size: [S, S], format: 'rgba8unorm',
      usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_SRC })));
    const [A, B] = skinTmp.get(S), e = device.createCommandEncoder(), sp = getSkinPipe();
    const n = w[a + 2], fill = argb(w[a + 1]);
    const step = (dst, bind) => {
      const p = e.beginRenderPass({ colorAttachments: [{ view: dst.createView(), loadOp: 'load', storeOp: 'store' }] });
      p.setPipeline(sp); p.setBindGroup(0, bind); p.draw(3); p.end();
    };
    const uni = (mode, recolour, cols, marks) => {
      const b = new ArrayBuffer(96 + 64 * 16), u = new Uint32Array(b), f = new Float32Array(b);
      u[0] = mode; u[1] = recolour; u[2] = marks.length / 2; u[3] = check ? 1 : 0; f[4] = t.w; f[5] = t.h;
      f[6] = 0.003921569;    // the 1/255 of 0x5a8d1a and 0x5a8681 (f32)
      cols.forEach((c, k) => f.set(argb(c), 8 + 4 * k));
      for (let m = 0; m < marks.length / 2; m++) { u[24 + 4 * m] = marks[2 * m]; u[25 + 4 * m] = marks[2 * m + 1]; }
      const g = device.createBuffer({ size: b.byteLength, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
      device.queue.writeBuffer(g, 0, b); return g;
    };
    const bind = (src, l, m, buf) => device.createBindGroup({ layout: sp.getBindGroupLayout(0), entries: [
      { binding: 0, resource: src.createView() }, { binding: 1, resource: l.own }, { binding: 2, resource: m.own },
      { binding: 3, resource: check ? skinNear : skinLin }, { binding: 4, resource: { buffer: buf } }] });
    e.beginRenderPass({ colorAttachments: [{ view: A.createView(), loadOp: 'clear', storeOp: 'store',
      clearValue: { r: fill[0] / 255, g: fill[1] / 255, b: fill[2] / 255, a: fill[3] / 255 } }] }).end();
    let src = A, dst = B, o = a + 3;
    for (let i = 0; i < n; i++, o += 7) {
      const l = res.get(w[o]), m = res.get(w[o + 1]);
      if (!l || !m) return;
      step(dst, bind(src, l, m, uni(0, w[o + 2], [w[o + 3], w[o + 4], w[o + 5], w[o + 6]], [])));
      [src, dst] = [dst, src];
    }
    const nm = w[o + 4];
    step(dst, bind(src, t, t, uni(1, 0, [w[o], w[o + 1], w[o + 2], w[o + 3]], Array.from(w.subarray(o + 5, o + 5 + 2 * nm)))));
    if (check) {
      const bufs = [dst, t.tex].map(x => { const b = device.createBuffer({ size: S * S * 4, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
        e.copyTextureToBuffer({ texture: x }, { buffer: b, bytesPerRow: S * 4 }, [S, S]); return b; });
      device.queue.submit([e.finish()]);
      Promise.all(bufs.map(b => b.mapAsync(GPUMapMode.READ))).then(() => {
        const [x, y] = bufs.map(b => new Uint8Array(b.getMappedRange()));
        let diff = 0, max = 0, first = '';
        for (let k = 0; k < x.length; k += 4) {
          let dk = 0; for (let c = 0; c < 4; c++) dk = Math.max(dk, Math.abs(x[k + c] - y[k + c]));
          if (dk && !first) first = ` first at texel ${k / 4}: gpu ${x.subarray(k, k + 4).join(',')} game ${y.subarray(k, k + 4).join(',')}`;
          if (dk) diff++; max = Math.max(max, dk);
        }
        report(`gpu.js: skinhd check id ${id} ${S}x${S} layers ${n} markers ${nm}: ${diff} texels differ, max ${max}${first}`);
      });
      return;
    }
    if (!t.skin || t.skin.width !== S) {
      doom(t.skin);
      t.skin = device.createTexture({ size: [S, S], mipLevelCount: Math.log2(S) + 1, format: 'rgba8unorm',
        usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_DST });
    }
    e.copyTextureToTexture({ texture: dst }, { texture: t.skin }, [S, S]);
    skinMips(e, t.skin);
    device.queue.submit([e.finish()]);
    t.view = t.skin.createView();
  }
  function skinMips(e, tex) {
    const mp = getMipPipe();
    for (let l = 1; l < tex.mipLevelCount; l++) {
      const p = e.beginRenderPass({ colorAttachments: [{ view: tex.createView({ baseMipLevel: l, mipLevelCount: 1 }), loadOp: 'clear', storeOp: 'store' }] });
      p.setPipeline(mp);
      p.setBindGroup(0, device.createBindGroup({ layout: mp.getBindGroupLayout(0), entries: [
        { binding: 0, resource: tex.createView({ baseMipLevel: l - 1, mipLevelCount: 1 }) }, { binding: 1, resource: skinLin }] }));
      p.draw(3); p.end();
    }
  }
  // ?pool=1 (OWNER 2026-11-03): host/d3d9.c skin_bridge names a livery right after GPU_SKIN. The art (tools/art/compose.py, RGBA, skin UV) loads
  // once and is alpha-blended over mip 0 of the HD skin. The skin's alpha (reflectivity) stays. A car drawn before it loads just pops in.
  const LIV_CARS = ['GOLF', 'FOCUS', 'MIATA', 'NEON', 'CIVIC', 'PEUGOT', 'CELICA', 'ECLIPSE', 'RX7', 'SUPRA', 'S2000', 'RSX', 'IMPREZA', 'LANCER', 'INTEGRA', 'TIBURON', '350Z', 'SENTRA', '240SX', 'SKYLINE'];
  const livCache = new Map();
  let livPipe = null;
  let livGate = null;                    // one probe for the whole session: web/remaster/liv is not shipped, so a 404 per URL is pointless
  function livery(id, car, n) {
    const t = res.get(id), url = `remaster/liv/${LIV_CARS[car]}/${n}.webp`;
    if (!t || !t.skin) return;
    const skinTex = t.skin;
    // The first livery decides whether the art dir exists at all; when it does not, later calls reuse the resolved gate and never fetch.
    if (!livCache.has(url)) livCache.set(url, (livGate ??= fetch(url).then(r => r.ok, () => false))
      .then(ok => ok ? fetch(url) : null)
      .then(r => r && r.ok ? r.blob() : null)
      .then(b => b && createImageBitmap(b, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' })).then(img => {
        if (!img) return null;                // no sticker art for this car yet
        const a = device.createTexture({ size: [img.width, img.height], format: 'rgba8unorm', usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT });
        device.queue.copyExternalImageToTexture({ source: img }, { texture: a }, [img.width, img.height]);
        return a;
      }));
    livCache.get(url).then(a => {
      if (!a || t.skin !== skinTex) return;
      livPipe ??= device.createRenderPipeline({ layout: 'auto', vertex: { module: getMipMod(), entryPoint: 'vs' }, fragment: { module: device.createShaderModule({ code: `
@group(0) @binding(0) var art: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;
@fragment fn fs(@builtin(position) p: vec4f) -> @location(0) vec4f {
  return textureSampleLevel(art, smp, p.xy / vec2f(${skinTex.width}.0), 0.0);
}` }), entryPoint: 'fs', targets: [{ format: 'rgba8unorm', writeMask: GPUColorWrite.RED | GPUColorWrite.GREEN | GPUColorWrite.BLUE,
        blend: { color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha' }, alpha: { srcFactor: 'zero', dstFactor: 'one' } } }] }, primitive: { topology: 'triangle-list' } });
      const e = device.createCommandEncoder();
      const p = e.beginRenderPass({ colorAttachments: [{ view: skinTex.createView({ baseMipLevel: 0, mipLevelCount: 1 }), loadOp: 'load', storeOp: 'store' }] });
      p.setPipeline(livPipe);
      p.setBindGroup(0, device.createBindGroup({ layout: livPipe.getBindGroupLayout(0), entries: [{ binding: 0, resource: a.createView() }, { binding: 1, resource: skinLin }] }));
      p.draw(3); p.end();
      skinMips(e, skinTex);
      device.queue.submit([e.finish()]);
    }).catch(err => report('gpu.js: livery ' + err.message));
  }

  const gpuDone = [], TS_MAX = 256;
  const tsq = TS ? { set: device.createQuerySet({ type: 'timestamp', count: TS_MAX }),
    res: device.createBuffer({ size: 8 * TS_MAX, usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC }), free: [] } : null;
  let tsN = 0;
  // ?gpuprof=1: GPU time per pass kind (label = what the pass does and its target), summed over 300 frames, in the frame log.
  const PROF = RN_Q.get('gpuprof') === '1', profLab = [], profSum = new Map();
  let profFrames = 0, profSeq = [], profLast = '';   // the frame's pass breaks in order (?gpuprof=1)
  const tsw = lab => {
    if (!tsq || tsN + 2 > TS_MAX) return undefined;
    if (PROF) profLab[tsN >> 1] = lab;
    return { querySet: tsq.set, beginningOfPassWriteIndex: tsN++, endOfPassWriteIndex: tsN++ };
  };
  const passLab = (kind, rt) => rt ? `${kind} ${rt.w}x${rt.h}${rt.sc > 1 || rt.msView ? ' ms' : ''}` : kind;
  const gpuReport = () => {
    if (!gpuDone.length) return '';
    const v = gpuDone.splice(0).sort((x, y) => x - y), q = f => v[Math.min(v.length - 1, Math.floor(f * v.length))].toFixed(1);
    let prof = '';
    if (PROF && profFrames) {
      prof = '; per frame: ' + [...profSum].sort((x, y) => y[1][0] - x[1][0]).slice(0, 10)
        .map(([l, e]) => `${l} ${(e[0] / profFrames).toFixed(2)} ms/${(e[1] / profFrames).toFixed(1)}`).join(', ');
      profSum.clear(); profFrames = 0;
      const e = encMs.splice(0).sort((x, y) => x - y);
      if (e.length) prof += `; encode p50 ${e[e.length >> 1].toFixed(1)} p90 ${e[Math.floor(e.length * .9)].toFixed(1)} max ${e[e.length - 1].toFixed(1)} ms`;
      prof += '; passes: ' + profLast;
    }
    return `, gpu ts p50 ${q(0.5)} p90 ${q(0.9)} max ${q(1)} ms` + prof;
  };
  // ?gpuprof=1: the JS time to encode and submit one command list (the page's CPU side of a frame)
  const encMs = [];
  function run(ptr, len) {
    if (!PROF) return runList(ptr, len);
    const t = performance.now(), r = runList(ptr, len);
    encMs.push(performance.now() - t);
    return r;
  }
  function runList(ptr, len) {
    const w = H().subarray(ptr >> 2, (ptr >> 2) + len);
    const f32 = new Float32Array(w.buffer, w.byteOffset, w.length);
    const u8 = new Uint8Array(w.buffer, w.byteOffset, w.length * 4);
    const enc = device.createCommandEncoder();
    tsN = 0;
    let nuni = 0, stats = { clears: 0, draws: 0, present: '', words: w.length, texKb: 0, pipes: 0, shaders: 0, targets: 0 };
    // First pass over the frame: sizes of the per-frame buffers.
    // It also lists the commands that open, close or clear targets (cl): a pass looks ahead in it to know if
    // its attachments are read again in this frame.
    let vneed = 0, ineed = 0, uneed = 0;
    cl.length = 0;
    for (let i = 0; i < w.length;) {
      const op = w[i] & 0xff, n = w[i] >>> 8, a = i + 1;
      if (IN_CL[op]) cl.push(i);
      i += 1 + n;
      if (op === GPU_DRAW && !w[a + D_RVB]) {
        vneed += ((w[a + D_NVERT] * w[a + D_STRIDE] + 3) & ~3) + w[a + D_STRIDE];   // + start on a whole vertex
        ineed += 4 * w[a + D_NIDX];
      }
      if (op === GPU_DRAW) uneed += (U_FIXED + 16 * w[a + D_NVC] + 255) & ~255;
    }
    [vbuf, vcap] = grow(vbuf, vcap, vneed, GPUBufferUsage.VERTEX);
    [ibuf, icap] = grow(ibuf, icap, ineed + 4, GPUBufferUsage.INDEX);
    // Tail padding of U_SIZE keeps uoff + U_SIZE <= ubuf.size for every draw (WebGPU minBindingSize & WebGL2 bindBufferRange).
    [ubuf, ucap] = grow(ubuf, ucap, uneed + U_SIZE, GPUBufferUsage.UNIFORM);
    if (vdata.length < vneed) vdata = new Uint8Array(vcap);
    if (idata.length < ineed / 4 + 1) idata = new Uint32Array(icap / 4);
    if (udata.byteLength < uneed + U_SIZE) {
      udata = new ArrayBuffer(ucap); udw = new Uint32Array(udata); udf = new Float32Array(udata);
    }
    if (uBindBuf !== ubuf) {
      uBind = device.createBindGroup({ layout: drawBgl, entries: [{ binding: 0, resource: { buffer: ubuf, size: U_SIZE } }] });
      uBindBuf = ubuf;
    }
    let voff = 0, ioff = 0, uoff = 0;
    let pass = null, passRt = -1, passDs = -1, pend = null, ci = 0, sceneDs = 0, sceneRt = 0;
    // What the current draw pass already holds (WebGPU keeps state for the whole pass): a draw sets only what changes,
    // and payload draws keep one binding of the frame's vertex/index buffers, addressed by first vertex/index.
    let stPass = null, stPipe, stBg1, stVp0 = -1, stVp1 = 0, stVp2 = 0, stVp3 = 0, stVp4 = 0, stVp5 = 0,
      stSc0 = -1, stSc1 = 0, stSc2 = 0, stSc3 = 0, stBf = -1, stVb, stVo = -1, stIb, stIf = '';
    if (PROF) profSeq = [];
    // A clear that covers whole attachments waits (pend) and becomes the loadOp of the next pass on them;
    // if no such pass comes next, it runs alone as an empty pass with loadOp 'clear' (no timestamps: Metal skips them there).
    const endPass = keepClear => {
      if (pass) { pass.end(); pass = null; passRt = -1; passDs = -1; }
      if (pend && !keepClear) { enc.beginRenderPass(passDesc(null, pend.mask & 1 ? pend.rt : 0, pend.mask & 6 ? pend.ds : 0, pend.k, pend)).end(); pend = null; }
    };
    // What a later command does to target id's colour (asp 0, the MSAA twin), depth (1) or stencil (2):
    // true = it reads it (draw or partial clear: loadOp 'load'), false = it overwrites it first (full clear, new target).
    const needed = (k, id, asp) => {
      for (; k < cl.length; k++) {
        const a = cl[k] + 1, op = w[a - 1] & 0xff;
        if (op === GPU_TARGET) { if (w[a] === id) return false; }
        else if (op === GPU_DRAW) { if (w[a + (asp ? D_DS : D_RT)] === id) return true; }
        else if (op === GPU_FXAA) { if (window.MaxChar?.enabled || (asp && RN_PS.on && res.get(id)?.w >= 1000)) return true; }   // psblur reads the scene depth
        else if (op === GPU_CLEAR && w[a + (asp ? 1 : 0)] === id) return !(fullClear(a) & (1 << asp));
      }
      return true;     // the next frame may read it
    };
    // The aspects (1 colour, 2 depth, 4 stencil) a clear writes over whole attachments; 0 if it is partial.
    const fullClear = a => {
      const rt = w[a] ? res.get(w[a]) : null, ds = w[a + 1] ? res.get(w[a + 1]) : null;
      const mask = (rt ? w[a + 2] & 1 : 0) | (ds ? w[a + 2] & 6 : 0);
      const all = t => w[a + 6] <= 0 && w[a + 7] <= 0 && w[a + 8] >= t.w && w[a + 9] >= t.h;
      return mask && (!(mask & 1) || all(rt)) && (!(mask & 6) || all(ds)) ? mask : 0;
    };
    // Pass on rid/did whose last command is cl[k - 1]: storeOp 'discard' where nothing reads the attachment again
    // (the single-sample colour texture is what the game samples and presents, so it is always stored or resolved).
    function passDesc(lab, rid, did, k, pc) {
      const rt = rid ? res.get(rid) : null, ds = did ? res.get(did) : null;
      const d = { timestampWrites: lab ? tsw(passLab(lab, rt || ds)) : undefined, colorAttachments: [] };
      if (rt) {
        const c = rt.msView ? { view: rt.msView, resolveTarget: rt.view, storeOp: needed(k, rid, 0) ? 'store' : 'discard' }
          : { view: rt.view, storeOp: 'store' };
        c.loadOp = pc && pc.mask & 1 ? 'clear' : 'load';
        if (pc && pc.mask & 1) c.clearValue = pc.color;
        d.colorAttachments.push(c);
      }
      if (ds) {
        const z = pc && pc.mask & 2, s = pc && pc.mask & 4;
        // Depth and stencil are discarded together or not at all: discarding one aspect alone cost more than storing
        // it (race frames >20 ms 0.1 -> 4 %, 2026-10-24; Dawn re-initializes the texture).
        const st = needed(k, did, 1) || needed(k, did, 2) ? 'store' : 'discard';
        d.depthStencilAttachment = { view: ds.view, depthLoadOp: z ? 'clear' : 'load', depthStoreOp: st,
          stencilLoadOp: s ? 'clear' : 'load', stencilStoreOp: st };
        if (z) d.depthStencilAttachment.depthClearValue = pc.z;
        if (s) d.depthStencilAttachment.stencilClearValue = pc.stencil;
      }
      return d;
    }

    for (let i = 0; i < w.length;) {
      const op = w[i] & 0xff, n = w[i] >>> 8, a = i + 1;
      if (IN_CL[op]) ci++;
      i += 1 + n;
      if (op === GPU_TARGET) {
        if (PROF) profSeq.push('T');
        endPass();
        const depth = w[a + 3] === 1;
        const sc = msFor(w[a + 1], w[a + 2]);
        const tex = device.createTexture({ size: [w[a + 1], w[a + 2]], format: depth ? 'depth24plus-stencil8' : 'rgba8unorm',
          sampleCount: depth ? sc : 1,
          usage: GPUTextureUsage.RENDER_ATTACHMENT | (depth ? (sc === 1 ? GPUTextureUsage.TEXTURE_BINDING : 0) : GPUTextureUsage.COPY_SRC | GPUTextureUsage.TEXTURE_BINDING) });
        const ms = !depth && sc > 1 ? device.createTexture({ size: [w[a + 1], w[a + 2]], format: 'rgba8unorm', sampleCount: sc,
          usage: GPUTextureUsage.RENDER_ATTACHMENT }) : null;
        const old = res.get(w[a]);
        doom(old?.tex); doom(old?.ms);
        res.set(w[a], { tex, view: tex.createView(), w: w[a + 1], h: w[a + 2], depth, sc, ms, msView: ms?.createView() });
        stats.targets++;
      } else if (op === GPU_CLEAR) {
        if (PROF) { const t = res.get(w[a]) || res.get(w[a + 1]); profSeq.push(`c${fullClear(a) ? 'F' : 'p'}${w[a + 2] & 7}${t ? t.w : 0}`); }
        endPass();
        const rt = w[a] ? res.get(w[a]) : null, ds = w[a + 1] ? res.get(w[a + 1]) : null, flags = w[a + 2];
        const c = w[a + 3], off = nuni * 256, mask = fullClear(a);
        if (mask) {
          pend = { rt: w[a], ds: w[a + 1], mask, k: ci, z: f32[a + 4], stencil: w[a + 5] & 0xff,
            color: { r: ((c >>> 16) & 255) / 255, g: ((c >>> 8) & 255) / 255, b: (c & 255) / 255, a: (c >>> 24) / 255 } };
          stats.clears++;
          continue;
        }
        if (nuni === 1024) fail('more than 1024 clears in a frame');
        uf.set([((c >>> 16) & 255) / 255, ((c >>> 8) & 255) / 255, (c & 255) / 255, (c >>> 24) / 255, f32[a + 4]], off / 4);
        nuni++;
        const p = enc.beginRenderPass({ timestampWrites: tsw(passLab('clear', rt || ds)),
          colorAttachments: rt ? [colorAtt(rt)] : [],
          depthStencilAttachment: ds ? { view: ds.view, depthLoadOp: 'load', depthStoreOp: 'store',
            stencilLoadOp: 'load', stencilStoreOp: 'store' } : undefined });
        p.setPipeline(clearPipe(!!rt, !!ds, flags, (rt || ds)?.sc || 1));
        p.setBindGroup(0, clearBind, [off]);
        p.setStencilReference(w[a + 5] & 0xff);
        p.setScissorRect(w[a + 6], w[a + 7], w[a + 8] - w[a + 6], w[a + 9] - w[a + 7]);
        p.draw(3);
        p.end();
        stats.clears++;
      } else if (op === GPU_SHADER) {
        const kind = w[a + 1], ntok = w[a + 2], nbytes = w[a + 3];
        const text = new TextDecoder().decode(u8.slice(4 * (a + 21 + ntok), 4 * (a + 21 + ntok) + nbytes));
        const module = device.createShaderModule({ code: text });
        const id = w[a];
        module.getCompilationInfo().then(info => {
          for (const m of info.messages) if (m.type === 'error') report(`gpu.js: shader ${id}: ${m.message} (line ${m.lineNum})`);
        });
        const sh = { kind, module, inputs: Array.from(w.subarray(a + 4, a + 20)), texMask: w[a + 20] };
        shaders.set(id, sh);
        stats.shaders++;
        if (WARM) { sh.h = hash53(text); warmShader.set(sh.h, id); warmTry(); }
      } else if (op === GPU_DECL) {
        const els = [];
        for (let k = 0; k < w[a + 1]; k++) {
          const x = w[a + 2 + 2 * k], y = w[a + 3 + 2 * k];
          els.push({ stream: x & 0xffff, offset: x >>> 16, type: y & 255, usage: (y >>> 16) & 255, index: y >>> 24 });
        }
        decls.set(w[a], els);
        if (WARM) { els.sig = Array.from(w.subarray(a + 1, a + 2 + 2 * w[a + 1])).join(','); warmDecl.set(els.sig, w[a]); warmTry(); }
      } else if (op === GPU_TEXTURE) {
        doom(res.get(w[a])?.tex);
        // word 4 (host dxt_native): 0 RGBA8, 1/2/3 = BC1/2/3 with the raw blocks sent by GPU_TEXDATA
        const bcf = S3 ? [null, 'bc1-rgba-unorm', 'bc2-rgba-unorm', 'bc3-rgba-unorm'][w[a + 4]] : null;
        const tex = device.createTexture({ size: [w[a + 1], w[a + 2]], mipLevelCount: w[a + 3], format: bcf || 'rgba8unorm',
          usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC });
        const own = tex.createView();
        res.set(w[a], { tex, own, view: own, w: w[a + 1], h: w[a + 2], depth: false, bc: bcf ? (w[a + 4] === 1 ? 8 : 16) : 0 });
      } else if (op === GPU_CUBE) {
        // One texture, six layers: each face target draws into its layer, the stage samples the cube view.
        const e = w[a + 1], f0 = w[a + 2];
        const tex = device.createTexture({ size: [e, e, 6], format: 'rgba8unorm',
          usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_SRC });
        for (let k = 0; k < 6; k++) {
          doom(res.get(f0 + k)?.tex);
          res.set(f0 + k, { tex, view: tex.createView({ dimension: '2d', baseArrayLayer: k, arrayLayerCount: 1 }), w: e, h: e, depth: false });
        }
        res.set(w[a], { tex, cube: tex.createView({ dimension: 'cube' }), w: e, h: e, depth: false });
        stats.targets++;
      } else if (op === GPU_TEXKEY) {
        const t = res.get(w[a]);
        if (t && pack.size) { t.id = w[a]; t.key = (w[a + 2] >>> 0).toString(16).padStart(8, '0') + (w[a + 1] >>> 0).toString(16).padStart(8, '0'); useHd(t, t.key); }
      } else if (op === GPU_TEXDATA) {
        // queue.writeTexture runs before this frame's commands: a texture changed after a draw of the
        // same frame that used it would show its new texels in that draw (not seen yet).
        const t = res.get(w[a]), tw = w[a + 2], th = w[a + 3];
        if (t.bc) {   // raw blocks; a level under 4 px is one block row/column and its physical size is 4
          const bw = (tw + 3) >> 2, bh = (th + 3) >> 2;
          device.queue.writeTexture({ texture: t.tex, mipLevel: w[a + 1] }, u8.subarray(4 * (a + 4), 4 * (a + 4) + bw * bh * t.bc),
            { bytesPerRow: bw * t.bc }, [bw * 4, bh * 4]);
          stats.texKb += bw * bh * t.bc >> 10;
        } else {
          device.queue.writeTexture({ texture: t.tex, mipLevel: w[a + 1] }, u8.subarray(4 * (a + 4), 4 * (a + 4 + tw * th)),
            { bytesPerRow: 4 * tw }, [tw, th]);
          stats.texKb += tw * th >> 8;
        }
      } else if (op === GPU_DRAW) {
        const rtId = w[a + D_RT], dsId = w[a + D_DS];
        const rt = res.get(rtId), ds = dsId ? res.get(dsId) : null;
        if (ds && w[a + D_ZEN] && (ds.w >= 1000 || window.MaxChar?.enabled) && rt?.w === ds.w) { sceneDs = dsId; sceneRt = rtId; }
        if (rtId !== passRt || dsId !== passDs) {
          const fold = pend && (!(pend.mask & 1) || pend.rt === rtId) && (!(pend.mask & 6) || pend.ds === dsId);
          endPass(fold);
          let k = ci;      // the pass runs while the draws keep this target pair
          while (k < cl.length && (w[cl[k]] & 0xff) === GPU_DRAW && w[cl[k] + 1 + D_RT] === rtId && w[cl[k] + 1 + D_DS] === dsId) k++;
          pass = enc.beginRenderPass(passDesc('draw', rtId, dsId, k, fold ? pend : null));
          if (PROF) profSeq.push(`D${rt ? rt.w : 0}:${rtId}/${dsId}${w[a + D_ZEN] ? 'z' : ''}x${k - ci + 1}`);
          if (fold) pend = null;
          passRt = rtId; passDs = dsId;
        }
        const nv = w[a + D_NVERT], ni = w[a + D_NIDX], stride = w[a + D_STRIDE], nvc = w[a + D_NVC], npc = w[a + D_NPC];
        const ps = shaders.get(w[a + D_PS]);
        // uniforms (sm1.h SM1_U_*: pc[8], hp, fogc, af, ar, tt[8] at 0..223, then c[0..nvc-1] at 224..)
        const ub = uoff >>> 2, src = a + D_HDR;
        const nv4 = 4 * nvc, np4 = 4 * npc, psrc = src + nv4;
        if (np4) udf.set(f32.subarray(psrc, psrc + np4), ub);
        if (npc < 8) udf.fill(0, ub + np4, ub + 32);
        udf[ub + 32] = 1 / w[a + D_VP + 2]; udf[ub + 33] = 1 / w[a + D_VP + 3];
        const fc = w[a + D_FOGC];
        udf[ub + 36] = ((fc >>> 16) & 255) / 255; udf[ub + 37] = ((fc >>> 8) & 255) / 255; udf[ub + 38] = (fc & 255) / 255;
        udw[ub + 40] = w[a + D_AFUNC]; udw[ub + 41] = w[a + D_FOG]; udw[ub + 42] = 0;   // af.z must stay 0 (sm1.c d3d_inf)
        udf[ub + 44] = w[a + D_AREF] / 255;
        for (let k = 0; k < 8; k++) udw[ub + 48 + k] = w[a + D_TEX + D_TEXN * k + T_TT];
        if (nv4) udf.set(f32.subarray(src, src + nv4), ub + 56);
        // vertices and indices: in the payload, or in resident buffers (GPU_BUFFER)
        const rvb = w[a + D_RVB], vsrc = 4 * (src + nv4 + np4), vbytes = rvb ? 0 : nv * stride;
        if (!rvb && stride) voff = Math.ceil(voff / stride) * stride;
        if (!rvb) {
          vdata.set(u8.subarray(vsrc, vsrc + vbytes), voff);
          if (ni) idata.set(w.subarray(src + nv4 + np4 + ((vbytes + 3) >> 2), src + nv4 + np4 + ((vbytes + 3) >> 2) + ni), ioff / 4);
        }
        const sc0 = w[a + D_SC], sc1 = w[a + D_SC + 1], sc2 = Math.min(w[a + D_SC + 2], rt.w), sc3 = Math.min(w[a + D_SC + 3], rt.h);
        if (sc2 > sc0 && sc3 > sc1) {
          if (pass !== stPass) {
            stPass = pass; stPipe = stBg1 = stVb = stIb = undefined;
            stVp0 = stSc0 = stBf = stVo = -1; stIf = '';
          }
          const pl = pipeline(w, a, stride, rt.sc || 1);
          if (pl !== stPipe) { pass.setPipeline(pl); stPipe = pl; }
          UOFF_ARR[0] = uoff;
          pass.setBindGroup(0, uBind, UOFF_ARR);
          const mask = ps.texMask & 0xff;
          let bg = texBinds.get(mask);
          if (bg !== undefined && mask !== 0) {
            for (let k = 0; k < 8; k++) if ((mask >>> k) & 1) {
              const to = a + D_TEX + D_TEXN * k;
              const tid = w[to + T_ID];
              const img = tid ? res.get(tid) : null, cube = (w[to + T_TT] & T_CUBE) !== 0;
              const smp = samplerFrom(w, to), v2 = (!cube && img?.view) || dummyView, vc = (cube && img?.cube) || dummyCubeView;
              bg = bg.get(oid(smp));
              if (bg === undefined) break;
              bg = bg.get(oid(v2));
              if (bg === undefined) break;
              bg = bg.get(oid(vc));
              if (bg === undefined) break;
            }
          }
          if (bg === undefined) bg = makeTexBindGroup(mask, w, a);
          if (bg !== stBg1) { pass.setBindGroup(1, bg); stBg1 = bg; }
          const vp0 = w[a + D_VP], vp1 = w[a + D_VP + 1], vp2 = w[a + D_VP + 2], vp3 = w[a + D_VP + 3], vp4 = w[a + D_VP + 4], vp5 = w[a + D_VP + 5];
          if (vp0 !== stVp0 || vp1 !== stVp1 || vp2 !== stVp2 || vp3 !== stVp3 || vp4 !== stVp4 || vp5 !== stVp5) {
            pass.setViewport(vp0, vp1, vp2, vp3, f32[a + D_VP + 4], f32[a + D_VP + 5]);
            stVp0 = vp0; stVp1 = vp1; stVp2 = vp2; stVp3 = vp3; stVp4 = vp4; stVp5 = vp5;
          }
          if (sc0 !== stSc0 || sc1 !== stSc1 || sc2 !== stSc2 || sc3 !== stSc3) {
            pass.setScissorRect(sc0, sc1, sc2 - sc0, sc3 - sc1);
            stSc0 = sc0; stSc1 = sc1; stSc2 = sc2; stSc3 = sc3;
          }
          const bf = w[a + D_BFACTOR];
          if (w[a + D_BLEND] && (bf !== stBf)) {
            BF_ARR[0] = ((bf >>> 16) & 255) / 255; BF_ARR[1] = ((bf >>> 8) & 255) / 255; BF_ARR[2] = (bf & 255) / 255; BF_ARR[3] = (bf >>> 24) / 255;
            pass.setBlendConstant(BF_ARR);
            stBf = bf;
          }
          if (rvb) {
            const vb = gbufs.get(rvb), rvoff = w[a + D_RVOFF];
            if (vb !== stVb || rvoff !== stVo) { pass.setVertexBuffer(0, vb, rvoff); stVb = vb; stVo = rvoff; }
            const rib = w[a + D_RIB];
            if (rib) {
              const ib = gbufs.get(rib), f = ifmt(w, a);
              if (ib !== stIb || f !== stIf) { pass.setIndexBuffer(ib, f); stIb = ib; stIf = f; }
              pass.drawIndexed(ni, 1, w[a + D_RFIRST], w[a + D_RBASEV] | 0);
            }
            else pass.draw(nv, 1, w[a + D_RFIRST]);
          } else if (stride) {   // one binding of the frame's vertex/index buffers, addressed per draw
            if (vbuf !== stVb || stVo !== 0) { pass.setVertexBuffer(0, vbuf); stVb = vbuf; stVo = 0; }
            if (ni) {
              if (ibuf !== stIb || stIf !== 'uint32') { pass.setIndexBuffer(ibuf, 'uint32'); stIb = ibuf; stIf = 'uint32'; }
              pass.drawIndexed(ni, 1, ioff / 4, voff / stride);
            } else pass.draw(nv, 1, voff / stride);
          } else {
            pass.setVertexBuffer(0, vbuf, voff, vbytes); stVb = undefined;
            if (ni) { pass.setIndexBuffer(ibuf, 'uint32', ioff, 4 * ni); stIb = undefined; pass.drawIndexed(ni); }
            else pass.draw(nv);
          }
        }
        if (!rvb) { voff += (vbytes + 3) & ~3; ioff += 4 * ni; }
        uoff += (U_FIXED + 16 * nvc + 255) & ~255;
        stats.draws++;
      } else if (op === GPU_FXAA) {
        if (PROF) {   // the draws on this target after the scene, and how many of them test or write depth
          let n = 0, z = 0;
          for (let k = ci; k < cl.length; k++) {
            const b = cl[k] + 1;
            if ((w[b - 1] & 0xff) === GPU_DRAW && w[b + D_RT] === w[a]) { n++; z += w[b + D_ZEN] ? 1 : 0; }
          }
          profSeq.push(`fxaa(post ${n}, zen ${z})`);
        }
        endPass();
        const rt = res.get(w[a]);
        // F-Max
        window.MaxChar?.scene(device, M, enc, res.get(sceneRt), res.get(sceneDs));
        // The scene colour (the target the depth-tested screen-size draws went to), not the FXAA target: that one holds the light trails
        // and the HUD, which the game adds onto the scene afterwards (draws 118 -> 636 with ONE / ONE).
        if (RN_PS.on) { const st = res.get(sceneRt); if (st && !st.depth && !st.msView) psblur(enc, st, res.get(sceneDs), f32.subarray(a + 1, a + 8), w[a + 5]); }
        if (BLOOM_ON && rt && !rt.depth) bloom(enc, rt);
        if (FXAA_ON && rt && !rt.depth && !rt.msView) {
          if (!fxaaTmp || fxaaTmp.width !== rt.w || fxaaTmp.height !== rt.h) {
            doom(fxaaTmp);
            fxaaTmp = device.createTexture({ size: [rt.w, rt.h], format: 'rgba8unorm', usage: GPUTextureUsage.COPY_DST | GPUTextureUsage.TEXTURE_BINDING });
            fxaaView = fxaaTmp.createView();
            fxaaBg = null;
          }
          enc.copyTextureToTexture({ texture: rt.tex }, { texture: fxaaTmp }, [rt.w, rt.h]);
          const fp = getFxaaPipe();
          if (!fxaaBg) fxaaBg = device.createBindGroup({ layout: fp.getBindGroupLayout(0),
            entries: [{ binding: 0, resource: fxaaView }, { binding: 1, resource: fxaaSamp }] });
          const p = enc.beginRenderPass({ timestampWrites: tsw('fxaa'), colorAttachments: [{ view: rt.view, loadOp: 'load', storeOp: 'store' }] });
          p.setPipeline(fp);
          p.setBindGroup(0, fxaaBg);
          p.draw(3);
          p.end();
        }
      } else if (op === GPU_BUFFER) {
        doom(gbufs.get(w[a]));
        gbufs.set(w[a], device.createBuffer({ size: Math.max(4, w[a + 1]), usage: GPUBufferUsage.VERTEX | GPUBufferUsage.INDEX | GPUBufferUsage.COPY_DST }));
      } else if (op === GPU_BUFDATA) {
        device.queue.writeBuffer(gbufs.get(w[a]), w[a + 1], u8, 4 * (a + 3), w[a + 2]);
      } else if (op === GPU_SKIN) {
        skin(w, a);
      } else if (op === GPU_LIVERY) {
        livery(w[a], w[a + 1], w[a + 2]);
      } else if (op === GPU_PRESENT) {
        endPass();
        if (n > 3) paceBox = w[a + 3];
        const t = res.get(w[a]), size = `${w[a + 1]}x${w[a + 2]}`;
        // The game's cursor moves in back-buffer pixels (web/input.js), whatever the canvas size.
        canvas.gameW = w[a + 1]; canvas.gameH = w[a + 2];
        const [cw, ch] = SHARP >= 0 && disp ? disp : [w[a + 1], w[a + 2]], csize = `${size} ${cw}x${ch}`;
        if (csize !== canvasSize) {
          canvas.width = cw; canvas.height = ch;
          ctx.configure({ device, format: 'rgba8unorm', alphaMode: 'opaque', usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_DST });
          canvasSize = csize;
          device.queue.writeBuffer(casU, 0, new Float32Array([w[a + 1] / cw, w[a + 2] / ch, -1 / (8 - 3 * Math.min(1, SHARP)), 0]));
          device.queue.writeBuffer(casU, 16, new Int32Array([w[a + 1] - 1, w[a + 2] - 1]));
        }
        const q = PRESENT_NOW ? null : queueTex(cw, ch), dst = q ? q.tex : ctx.getCurrentTexture();
        if (q) { shownQ.push(q); while (shownQ.length > QMAX) { recycle(shownQ.shift()); RN_PACE.dropped++; } } else RN_PACE.shown++;
        if (SHARP < 0) enc.copyTextureToTexture({ texture: t.tex }, { texture: dst }, [w[a + 1], w[a + 2]]);
        else {
          const cp = getCasPipe();
          let bg = casBgs.get(t.view);
          if (!bg) {
            bg = device.createBindGroup({ layout: cp.getBindGroupLayout(0),
              entries: [{ binding: 0, resource: t.view }, { binding: 1, resource: { buffer: casU } }] });
            casBgs.set(t.view, bg);
          }
          const p = enc.beginRenderPass({ timestampWrites: tsw('cas'), colorAttachments: [{ view: dst.createView(), loadOp: 'clear', storeOp: 'store' }] });
          p.setPipeline(cp);
          p.setBindGroup(0, bg);
          p.draw(3);
          p.end();
        }
        stats.present = size;
      } else {
        fail('unknown command ' + op);
      }
    }
    endPass();
    if (nuni) device.queue.writeBuffer(clearRing, 0, uni, 0, nuni * 256);
    if (voff) device.queue.writeBuffer(vbuf, 0, vdata, 0, voff);
    if (ioff) device.queue.writeBuffer(ibuf, 0, idata, 0, ioff / 4);
    if (uoff) device.queue.writeBuffer(ubuf, 0, udata, 0, uoff);
    // GPU time of the frame list: first pass begin to last pass end (timestamp-query), read back without waiting.
    let tsBuf = null;
    if (tsq && tsN) {
      enc.resolveQuerySet(tsq.set, 0, tsN, tsq.res, 0);
      tsBuf = tsq.free.pop() || device.createBuffer({ size: 8 * TS_MAX, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
      enc.copyBufferToBuffer(tsq.res, 0, tsBuf, 0, 8 * tsN);
    }
    device.queue.submit([enc.finish()]);
    for (const x of doomed) x.destroy();
    doomed.length = 0;
    if (PROF && stats.present) profLast = profSeq.join(' ');
    if (tsBuf) {
      const n = tsN, labs = PROF ? profLab.slice(0, n >> 1) : null;
      tsBuf.mapAsync(GPUMapMode.READ).then(() => {
        const q = new BigInt64Array(tsBuf.getMappedRange(0, 8 * n));
        // first pass begin to last pass end (Apple GPUs overlap passes, so a sum of passes overcounts)
        let lo = q[0], hi = q[0]; for (let k = 0; k < n; k++) if (q[k] > 0n) { if (q[k] < lo || lo === 0n) lo = q[k]; if (q[k] > hi) hi = q[k]; }
        const ns = hi - lo;
        if (labs) {
          for (let k = 0; k < labs.length; k++) {
            const d = q[2 * k + 1] > q[2 * k] ? Number(q[2 * k + 1] - q[2 * k]) / 1e6 : 0, e = profSum.get(labs[k]) || [0, 0];
            e[0] += d; e[1]++; profSum.set(labs[k], e);
          }
          profFrames++;
        }
        tsBuf.unmap(); tsq.free.push(tsBuf);
        gpuDone.push(Number(ns) / 1e6);
      });
    }
    stats.pipes = newPipes; newPipes = 0;
    stats.hd = packed;
    stats.uniKb = uoff >> 10;
    return stats;
  }

  // ?apicount=1: calls per frame list since the last report
  let apiFrames = 0;
  const apiReport = () => {
    const n = frames - apiFrames; if (!n || !Object.keys(apiN).length) return '';
    const r = '; api/frame ' + Object.entries(apiN).sort().map(([k, v]) => `${k} ${(v / n).toFixed(1)}`).join(' ');
    for (const k in apiN) apiN[k] = 0; apiFrames = frames; return r;
  };
  // ?hold=N (debug): stop after the N-th Present, so a capture shows that frame (the game then waits).
  const hold = Number(RN_Q.get('hold')) || 0;
  let frames = 0, presents = 0;
  const steerLog = /RN_STEERLOG/.test(location.search);   // host/input.c RN_STEERLOG: GPU completion per present
  // The page runs a frame as soon as the game submits it (host/gpu.c wakes seq), not at the next animation frame: with one
  // frame in flight, waiting for requestAnimationFrame made Present wait up to a refresh more (OWNER session 2026-10-23:
  // game thread 40% in gpu_wait, page 62% idle, frames alternating 17 / 34 ms).
  // A task boundary after each pass, so input, timers and the canvas update still get their turns.
  const ch = new MessageChannel(), yields = [];
  ch.port1.onmessage = () => yields.shift()?.();
  const yieldTask = () => new Promise(f => { yields.push(f); ch.port2.postMessage(0); });
  // RN_APP 'paused' (web/app.js: hidden page, phone upright): no frame runs, so the game thread waits in Present
  // (host/gpu.c gpu_wait) until the page is back; the same wait ?hold=N uses.
  let held = null, letGo = null;
  RN_APP.on(s => { if (s === 'paused') held ||= new Promise(f => letGo = f); else if (held) { letGo(); held = null; } });
  async function pump() {
    for (;;) {
      if (held) { await held; continue; }
      if (WD) WD[2]++;
      if (!tick()) return;
      if (hold && presents >= hold) { await new Promise(f => setTimeout(f, 100)); continue; }
      const h = M.HEAP32, seq = Atomics.load(h, box);
      const r = Atomics.load(h, box + 1) < seq ? { async: false } : Atomics.waitAsync(h, box, seq);
      if (WD) WD[1] = r.async ? 4 : 5;
      if (r.async) await r.value; else await yieldTask();
    }
  }
  function tick() {
    if (WD) WD[1] = 1;
    const h = H();
    try {
      while (Atomics.load(h, box + 1) < Atomics.load(h, box) && !(hold && presents >= hold)) {
        const k = Atomics.load(h, box + 1) + 1;
        const t = performance.now();
        const s = run(h[box + 2 + (k & 1)], h[box + 4 + (k & 1)]);
        onFrame?.(s, t, performance.now() - t);
        frames++;
        if (s.present) presents++;
        if (s.present && steerLog) { const p = presents; device.queue.onSubmittedWorkDone().then(() =>
          report(`page present ${p} start ${t.toFixed(1)} done ${performance.now().toFixed(1)}`)); }
        if (frames <= 3 || frames % 300 === 0) report(`gpu.js: frame ${frames}: ${s.clears} clears, ${s.draws} draws, uni ${s.uniKb} KB, present ${s.present}` +
          (pack.size ? `, remaster ${packed} (${hdMs.toFixed(0)} ms)` : '') + (WARM ? `, warm ${warmMade}/${warmList.length}` : '') + gpuReport() + apiReport());
        if (frames % 300 === 0) hdMs = 0;
        Atomics.store(h, box + 1, k);
        Atomics.notify(M.HEAP32, box + 1);
      }
    } catch (e) {
      report('STOP gpu.js: ' + (e && e.message ? e.message : String(e)));
      return false;
    }
    return true;
  }
  pump();
}
