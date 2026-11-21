/* Interactive Canvas Engines for recomp-kit Workbench:
 * 1. BinaryMapCanvas: PE .text address-space spectrum & coverage scrubber
 * 2. CallGraphCanvas: Real binary xrefs/call-graph with animated cubic Bezier signal traces
 */

(function () {
  const prefersReduced = () =>
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  /* -----------------------------------------------------------------------
   * 1. BinaryMapCanvas — Interactive PE .text Address-Space Telemetry Strip
   * ----------------------------------------------------------------------- */
  class BinaryMapCanvas {
    constructor(canvas, hudEl, onSelectAddr) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.hudEl = hudEl;
      this.onSelectAddr = onSelectAddr;
      this.data = null;
      this.hoverIdx = -1;
      this.smoothX = -1;
      this.targetX = -1;
      this.scanRatio = -1;
      this.scanLabel = "";
      this.rafId = null;
      this._bind();
    }

    setScanProgress(ratio, label) {
      this.scanRatio = typeof ratio === "number" ? Math.max(-1, Math.min(1, ratio)) : -1;
      this.scanLabel = label || "";
      this._schedule();
    }

    _bind() {
      const resize = () => this._resize();
      window.addEventListener("resize", resize);
      this._resize();

      this.canvas.addEventListener("mousemove", (e) => {
        if (!this.data || !this.data.buckets || !this.data.buckets.length) return;
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        this.targetX = x;
        const idx = Math.max(
          0,
          Math.min(this.data.buckets.length - 1, Math.floor((x / rect.width) * this.data.buckets.length))
        );
        this.hoverIdx = idx;
        this._updateHud(this.data.buckets[idx]);
        this._schedule();
      });

      this.canvas.addEventListener("mouseleave", () => {
        this.hoverIdx = -1;
        this.targetX = -1;
        this._updateHud(null);
        this._schedule();
      });

      this.canvas.addEventListener("click", () => {
        if (!this.data || this.hoverIdx < 0) return;
        const b = this.data.buckets[this.hoverIdx];
        if (b && b.sample_addr && this.onSelectAddr) {
          this.onSelectAddr(b.sample_addr);
        }
      });
    }

    _resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = this.canvas.getBoundingClientRect();
      if (!rect.width) return;
      this.w = rect.width;
      this.h = rect.height;
      this.canvas.width = Math.round(rect.width * dpr);
      this.canvas.height = Math.round(rect.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.draw();
    }

    setData(data) {
      this.data = data;
      this.hoverIdx = -1;
      this._resize();
      this._updateHud(null);
      this.draw();
    }

    _updateHud(b) {
      if (!this.hudEl) return;
      if (!this.data || !this.data.buckets || !this.data.buckets.length) {
        this.hudEl.textContent = "Run Discover to map the PE .text address space.";
        return;
      }
      if (!b) {
        this.hudEl.textContent =
          `${this.data.text_start} — ${this.data.text_end}   (${this.data.total_funcs} functions; click any bar to inspect)`;
        return;
      }
      const sample = b.sample_name ? `${b.sample_name} (${b.sample_addr})` : b.sample_addr;
      this.hudEl.textContent =
        `${b.va_start}–${b.va_end}  |  ${b.count} funcs  |  ${b.ran} live  |  ${b.verified} verified  |  ${b.trapped} traps  |  ${sample}`;
    }

    _schedule() {
      if (this.rafId) return;
      this.rafId = requestAnimationFrame(() => {
        this.rafId = null;
        this.draw();
      });
    }

    draw() {
      const ctx = this.ctx;
      const w = this.w || this.canvas.clientWidth;
      const h = this.h || this.canvas.clientHeight;
      if (!w || !h) return;

      ctx.clearRect(0, 0, w, h);

      const cOk = cssVar("--color-ok", "#34d399");
      const cAccent = cssVar("--color-accent", "#38bdf8");
      const cWarm = cssVar("--color-warm", "#fbbf24");
      const cJade = cssVar("--color-jade", "#a78bfa");
      const cDanger = cssVar("--color-danger", "#f87171");
      const cMuted = cssVar("--color-surface-3", "#334155");
      const cRim = cssVar("--color-rim", "rgba(226,232,240,0.11)");

      // Precision oscilloscope grid (horizontal + subtle vertical ticks)
      ctx.strokeStyle = cRim;
      ctx.lineWidth = 1;
      for (let i = 1; i <= 3; i++) {
        const y = Math.round((h / 4) * i) + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.save();
      ctx.globalAlpha = 0.45;
      for (let i = 1; i < 8; i++) {
        const x = Math.round((w / 8) * i) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      ctx.restore();

      if (!this.data || !this.data.buckets || !this.data.buckets.length) {
        if (this.scanRatio >= 0) {
          const sx = Math.round(this.scanRatio * w);
          ctx.fillStyle = cAccent;
          ctx.globalAlpha = 0.14;
          ctx.fillRect(0, 0, sx, h);
          ctx.globalAlpha = 0.95;
          ctx.strokeStyle = cWarm;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(sx + 0.5, 0);
          ctx.lineTo(sx + 0.5, h);
          ctx.stroke();
          if (this.scanLabel) {
            ctx.fillStyle = cWarm;
            ctx.font = `600 11px ${cssVar("--font-mono", "monospace")}`;
            ctx.fillText(this.scanLabel, Math.min(w - 220, sx + 8), 22);
          }
          ctx.globalAlpha = 1;
        }
        return;
      }
      const buckets = this.data.buckets;
      const n = buckets.length;
      const maxCount = Math.max(1, ...buckets.map((b) => b.count));
      const slotW = w / n;
      const barW = Math.max(2, slotW - 1.5);
      const padTop = 14;
      const padBot = 12;
      const plotH = h - padTop - padBot;

      // Smooth curve backdrop connecting density peaks
      ctx.beginPath();
      buckets.forEach((b, i) => {
        const cx = i * slotW + slotW * 0.5;
        const bh = Math.max(6, (b.count / maxCount) * plotH);
        const y = h - padBot - bh;
        if (i === 0) ctx.moveTo(cx, y);
        else ctx.lineTo(cx, y);
      });
      ctx.strokeStyle = cRim;
      ctx.lineWidth = 1.25;
      ctx.stroke();

      for (let i = 0; i < n; i++) {
        const b = buckets[i];
        const x = i * slotW + (slotW - barW) * 0.5;
        const bh = Math.max(6, (b.count / maxCount) * plotH);
        const y = h - padBot - bh;

        let color = cMuted;
        if (b.trapped > 0) color = cDanger;
        else if (b.verified > 0) color = cOk;
        else if (b.ran > 0) color = cWarm;
        else if (b.inferred > 0) color = cAccent;

        const isHover = i === this.hoverIdx;
        ctx.globalAlpha = this.hoverIdx >= 0 ? (isHover ? 1 : 0.42) : 0.85;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect(x, y, barW, bh, [3, 3, 0, 0]);
        ctx.fill();

        if (isHover) {
          ctx.globalAlpha = 1;
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x + barW * 0.5, 0);
          ctx.lineTo(x + barW * 0.5, h);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    }
  }

  /* -----------------------------------------------------------------------
   * 2. CallGraphCanvas — Interactive REA Call-Graph with Animated Bezier Traces
   * ----------------------------------------------------------------------- */
  class CallGraphCanvas {
    constructor(canvas, hudEl, onSelectAddr) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.hudEl = hudEl;
      this.onSelectAddr = onSelectAddr;
      this.graph = null;
      this.nodes = [];
      this.edges = [];
      this.hoverNode = null;
      this.phase = 0;
      this.enterProgress = 1;
      this.running = false;
      this.rafId = null;
      this._bind();
    }

    _bind() {
      window.addEventListener("resize", () => this._resize());
      this._resize();

      this.canvas.addEventListener("mousemove", (e) => {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        let hit = null;
        for (const n of this.nodes) {
          if (mx >= n.x - n.w / 2 && mx <= n.x + n.w / 2 && my >= n.y - n.h / 2 && my <= n.y + n.h / 2) {
            hit = n;
            break;
          }
        }
        this.hoverNode = hit;
        this.canvas.style.cursor = hit && (hit.kind === "caller" || hit.kind === "callee") ? "pointer" : "default";
        if (this.hudEl) {
          if (hit) {
            this.hudEl.textContent = `${hit.kind.toUpperCase()}: ${hit.label} (${hit.id})${hit.ran ? " — live RN_COV" : ""}`;
          } else if (this.graph) {
            this.hudEl.textContent =
              `${this.graph.xrefs_in.length} callers  |  ${this.graph.xrefs_out.length} callees  |  ${this.graph.apis.length} Win32 APIs  |  ${this.graph.strings.length} strings  (click any function node to jump)`;
          }
        }
        if (prefersReduced()) this.draw();
      });

      this.canvas.addEventListener("click", () => {
        if (this.hoverNode && (this.hoverNode.kind === "caller" || this.hoverNode.kind === "callee")) {
          if (this.onSelectAddr) this.onSelectAddr(this.hoverNode.id);
        }
      });
    }

    _resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = this.canvas.getBoundingClientRect();
      if (!rect.width) return;
      this.w = rect.width;
      this.h = rect.height;
      this.canvas.width = Math.round(rect.width * dpr);
      this.canvas.height = Math.round(rect.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this.graph) this._layout();
      this.draw();
    }

    setGraph(graph) {
      this.graph = graph;
      this.hoverNode = null;
      this.enterProgress = prefersReduced() ? 1 : 0;
      this._resize();
      this._layout();
      if (this.hudEl && graph) {
        this.hudEl.textContent =
          `${graph.xrefs_in.length} callers  |  ${graph.xrefs_out.length} callees  |  ${graph.apis.length} Win32 APIs  |  ${graph.strings.length} strings  (click any function node to jump)`;
      }
      this._startLoop();
    }

    _layout() {
      const w = this.w || 800;
      const h = this.h || 310;
      const rawNodes = (this.graph && this.graph.nodes) || [];
      const callers = rawNodes.filter((n) => n.kind === "caller").slice(0, 7);
      const center = rawNodes.find((n) => n.kind === "center");
      const rightItems = rawNodes
        .filter((n) => n.kind === "callee" || n.kind === "api" || n.kind === "string")
        .slice(0, 8);

      const placed = [];
      const byId = {};

      const placeCol = (list, xPos, nodeW) => {
        const count = list.length;
        if (!count) return;
        const pad = 28;
        const avail = Math.max(40, h - pad * 2);
        const step = count === 1 ? 0 : avail / (count - 1);
        list.forEach((item, idx) => {
          const y = count === 1 ? h / 2 : pad + idx * step;
          const node = {
            ...item,
            x: xPos,
            y,
            w: nodeW,
            h: 28,
          };
          placed.push(node);
          byId[node.id] = node;
        });
      };

      const colW = Math.min(200, Math.max(132, w * 0.24));
      placeCol(callers, colW * 0.5 + 18, colW);
      if (center) {
        const cNode = { ...center, x: w * 0.5, y: h * 0.5, w: Math.min(220, colW + 24), h: 42 };
        placed.push(cNode);
        byId[cNode.id] = cNode;
      }
      placeCol(rightItems, w - colW * 0.5 - 18, colW);

      this.nodes = placed;
      this.edges = ((this.graph && this.graph.edges) || [])
        .map((e) => ({ ...e, src: byId[e.from], dst: byId[e.to] }))
        .filter((e) => e.src && e.dst);
    }

    _startLoop() {
      if (prefersReduced()) {
        this.draw();
        return;
      }
      if (this.running) return;
      this.running = true;
      const tick = () => {
        if (!this.running) return;
        this.phase = (this.phase + 0.0085) % 1;
        if (this.enterProgress < 1) {
          this.enterProgress = Math.min(1, this.enterProgress + 0.065);
        }
        this.draw();
        this.rafId = requestAnimationFrame(tick);
      };
      this.rafId = requestAnimationFrame(tick);
    }

    stop() {
      this.running = false;
      if (this.rafId) cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    _cubicPoint(p0, p1, p2, p3, t) {
      const mt = 1 - t;
      return {
        x: mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x,
        y: mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y,
      };
    }

    draw() {
      const ctx = this.ctx;
      const w = this.w || this.canvas.clientWidth;
      const h = this.h || this.canvas.clientHeight;
      if (!w || !h) return;

      ctx.clearRect(0, 0, w, h);

      const cOk = cssVar("--color-ok", "#34d399");
      const cAccent = cssVar("--color-accent", "#38bdf8");
      const cWarm = cssVar("--color-warm", "#fbbf24");
      const cJade = cssVar("--color-jade", "#a78bfa");
      const cDanger = cssVar("--color-danger", "#f87171");
      const cInk = cssVar("--color-ink", "#eef2ff");
      const cMuted = cssVar("--color-ink-muted", "#94a3b8");
      const cSurf = cssVar("--color-surface-1", "#1e2230");
      const cRim = cssVar("--color-rim", "rgba(226,232,240,0.12)");

      if (!this.nodes.length) {
        ctx.fillStyle = cMuted;
        ctx.font = `13px ${cssVar("--font-sans", "sans-serif")}`;
        ctx.textAlign = "center";
        ctx.fillText("Select a function to trace its live callers, callees, APIs, and strings.", w / 2, h / 2);
        return;
      }

      const ease = 1 - Math.pow(1 - this.enterProgress, 3);
      const reduced = prefersReduced();

      // 1. Draw cubic Bezier edges + flowing signal pulses
      this.edges.forEach((e, idx) => {
        const p0 = { x: e.src.x + e.src.w / 2, y: e.src.y };
        const p3 = { x: e.dst.x - e.dst.w / 2, y: e.dst.y };
        const dx = Math.max(40, Math.abs(p3.x - p0.x) * 0.48);
        const p1 = { x: p0.x + dx, y: p0.y };
        const p2 = { x: p3.x - dx, y: p3.y };

        const isRelated =
          !this.hoverNode ||
          this.hoverNode.id === e.src.id ||
          this.hoverNode.id === e.dst.id;

        let stroke = cAccent;
        if (e.kind === "api") stroke = cOk;
        else if (e.kind === "str") stroke = cJade;
        else if (e.live) stroke = cOk;

        ctx.save();
        ctx.globalAlpha = (isRelated ? (e.live ? 0.85 : 0.52) : 0.12) * ease;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = isRelated && this.hoverNode ? 2.1 : 1.35;
        ctx.beginPath();
        ctx.moveTo(p0.x, p0.y);
        ctx.bezierCurveTo(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
        ctx.stroke();

        // Flowing signal particle along Bezier trajectory
        if (!reduced && isRelated) {
          const t = (this.phase + idx * 0.17) % 1;
          const pt = this._cubicPoint(p0, p1, p2, p3, t);
          ctx.globalAlpha = 0.95 * ease;
          ctx.fillStyle = stroke;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, e.live ? 3.2 : 2.3, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      });

      // 2. Draw glass nodes
      const monoFont = cssVar("--font-mono", "monospace");
      const sansFont = cssVar("--font-sans", "sans-serif");

      this.nodes.forEach((n) => {
        const isHover = this.hoverNode && this.hoverNode.id === n.id;
        const isCenter = n.kind === "center";

        let rim = cRim;
        let accent = cAccent;
        if (n.trapped) { rim = cDanger; accent = cDanger; }
        else if (n.kind === "api" || n.state === "V") { rim = cOk; accent = cOk; }
        else if (n.kind === "string" || n.state === "I") { rim = cJade; accent = cJade; }
        else if (isCenter) { rim = cAccent; accent = cAccent; }

        const x = n.x - n.w / 2;
        const y = n.y - n.h / 2 + (1 - ease) * 8;

        ctx.save();
        ctx.globalAlpha = ease;
        ctx.fillStyle = cSurf;
        ctx.strokeStyle = isHover || isCenter ? accent : rim;
        ctx.lineWidth = isCenter || isHover ? 1.8 : 1;

        ctx.beginPath();
        ctx.roundRect(x, y, n.w, n.h, 8);
        ctx.fill();
        ctx.stroke();

        // Left status indicator strip inside node
        ctx.fillStyle = accent;
        ctx.beginPath();
        ctx.roundRect(x + 1, y + 4, 3, n.h - 8, 2);
        ctx.fill();

        // Text clipping & rendering
        ctx.fillStyle = cInk;
        ctx.font = isCenter ? `600 12.5px ${sansFont}` : `500 11.5px ${monoFont}`;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        const maxChars = Math.floor((n.w - 20) / 7);
        const label = n.label.length > maxChars ? n.label.slice(0, maxChars - 1) + "…" : n.label;
        ctx.fillText(label, x + 12, isCenter ? y + n.h * 0.37 : y + n.h * 0.5);

        if (isCenter) {
          ctx.fillStyle = cMuted;
          ctx.font = `10.5px ${monoFont}`;
          ctx.fillText(n.id, x + 12, y + n.h * 0.72);
        }
        ctx.restore();
      });
    }
  }

  window.RecompCanvas = { BinaryMapCanvas, CallGraphCanvas };
})();
