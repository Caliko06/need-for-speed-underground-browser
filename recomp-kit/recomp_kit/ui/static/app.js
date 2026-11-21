/* recomp-kit Workbench Controller — Real REA, Call-Graph, Strings, Unicorn & Live WASM */

(function () {
  const state = {
    lang: "es",
    eli5: true,
    tab: "overview",
    filter: "all",
    streamFilter: "all",
    streamEvents: [],
    streamSource: null,
    search: "",
    selectedAddr: null,
    compareAddr: null,
    codeView: "split",
    status: null,
    fnDetail: null,
    binMapCanvas: null,
    callGraphCanvas: null,
  };

  const I18N = {
    es: {
      brandSub: "x86-32 ⇄ C / WASM Compare & Live Telemetry",
      loadExe: "Cargar .exe",
      eli5On: "Guía ELI5",
      eli5Off: "Sin ELI5",
      tabOverview: "Compare & Telemetry",
      tabLab: "Laboratorio REA",
      tabWasm: "Ejecutor WASM",
      tabApis: "APIs de Windows",
      step1: "Inspeccionar PE",
      step1d: "Lee cabeceras x86, secciones y DLLs importadas del .exe.",
      step2: "Descubrir código",
      step2d: "Encuentra cada función real dentro de la sección .text.",
      step3: "Traducir a C",
      step3d: "Convierte instrucciones x86-32 a código C portable sin traps.",
      step4: "Verificar Unicorn",
      step4d: "Prueba que el C generado iguala bit a bit al CPU x86 real.",
      step5: "Compilar WASM",
      step5d: "Empaqueta el binario traducido para correrlo en tu navegador.",
      eli5Overview:
        "Este mapa muestra todo el código máquina del .exe. Cada barra vertical es una zona de memoria: verde significa verificada, ámbar significa que ya corrió en vivo, rojo significa que tiene un trap por resolver. Haz clic en cualquier barra o cadena para saltar directo al Laboratorio REA.",
      eli5Lab:
        "Aquí haces ingeniería inversa real (REA): arriba ves el grafo animado de quién llama a esta función y qué APIs o textos usa; abajo comparas el ensamblador x86 con el C generado, Ghidra y Hopper. Cuando sepas qué hace, ponle nombre con evidencia binaria (V).",
      eli5Wasm:
        "Esto ejecuta el .exe original traducido a WebAssembly directamente dentro de esta pestaña del navegador. Capturamos su consola, sus ventanas MessageBoxA y guardamos qué funciones corrieron (RN_COV) para priorizarlas en el laboratorio.",
      eli5Apis:
        "Un programa de Windows pide ayuda al sistema operativo mediante DLLs (kernel32, user32, d3d9). Aquí ves exactamente qué funciones ya están traducidas al navegador y cuáles faltan para que el programa corra completo.",
      btnDiscover: "Descubrir",
      btnLift: "Traducir",
      btnVerify: "Verificar",
      btnBuildWasm: "Compilar WASM",
      btnRunWasm: "Correr .exe en navegador",
      btnRunNative: "Correr nativo (macOS)",
      btnVerifyOne: "Probar en Unicorn",
      btnSaveTag: "Guardar en ledger",
      btnCopyEvidence: "Copiar evidencia JSON",
      streamTitle: "Stream interactivo en tiempo real",
      btnRunPipeline: "Correr pipeline en vivo",
      btnOpenBatch: "Cola multi-.exe",
      btnStopStream: "Detener",
      btnClearStream: "Limpiar",
    },
    en: {
      brandSub: "x86-32 ⇄ C / WASM Compare & Live Telemetry",
      loadExe: "Load .exe",
      eli5On: "ELI5 guide",
      eli5Off: "ELI5 off",
      tabOverview: "Compare & Telemetry",
      tabLab: "REA Function Lab",
      tabWasm: "WASM Live Runner",
      tabApis: "Windows APIs",
      step1: "Inspect PE",
      step1d: "Reads x86 headers, sections, and imported Windows DLLs.",
      step2: "Discover code",
      step2d: "Finds every reachable function inside the .text section.",
      step3: "Lift to C",
      step3d: "Translates x86-32 instructions into portable C functions.",
      step4: "Verify Unicorn",
      step4d: "Proves lifted C matches a real x86 CPU bit for bit.",
      step5: "Build WASM",
      step5d: "Compiles the lifted C and runtime into browser WebAssembly.",
      eli5Overview:
        "This strip maps the entire .text machine code of the .exe. Each bar is a memory region: green is verified, amber ran live, terracotta has a translation trap. Click any bar or binary string to jump straight into the REA Function Lab.",
      eli5Lab:
        "Real reverse-engineering workbench: the live canvas traces callers, callees, Win32 APIs, and referenced strings. Compare raw x86 against lifted C, Ghidra, and Hopper, verify bit-exactness with Unicorn, and record a Verified (V) name backed by binary evidence.",
      eli5Wasm:
        "Runs the translated .exe as WebAssembly right inside this browser tab. Captures console output, intercepted MessageBoxA dialogs, Win32 API traces, and syncs live RN_COV coverage back to your project.",
      eli5Apis:
        "Windows executables rely on system DLLs (kernel32, user32, d3d9). This radar shows which imported APIs are already implemented in our browser runtime and which ones remain.",
      btnDiscover: "Discover",
      btnLift: "Lift C",
      btnVerify: "Verify",
      btnBuildWasm: "Build WASM",
      btnRunWasm: "Run .exe in browser",
      btnRunNative: "Run native (macOS)",
      btnVerifyOne: "Verify in Unicorn",
      btnSaveTag: "Save to ledger",
      btnCopyEvidence: "Copy evidence JSON",
      streamTitle: "Interactive real-time stream",
      btnRunPipeline: "Run live pipeline",
      btnOpenBatch: "Multi-.exe queue",
      btnStopStream: "Stop",
      btnClearStream: "Clear",
    },
  };

  const $ = (id) => document.getElementById(id);
  const t = (k) => (I18N[state.lang] && I18N[state.lang][k]) || k;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let toastTimer = null;
  function notify(msg, isError = false) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.toggle("is-error", isError);
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), isError ? 5200 : 3200);
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    const data = await res.json();
    if (!res.ok || data.error) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    $("eli5Toggle").textContent = state.eli5 ? t("eli5On") : t("eli5Off");
    $("eli5Toggle").classList.toggle("is-on", state.eli5);
    $("langToggle").textContent = state.lang === "es" ? "ES / EN" : "EN / ES";
  }

  function setTab(tabName) {
    state.tab = tabName;
    if (window.location.hash !== `#${tabName}`) {
      history.replaceState(null, "", `#${tabName}`);
    }
    document.querySelectorAll(".tab-btn").forEach((b) => {
      const active = b.dataset.tab === tabName;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll(".view-panel").forEach((p) => {
      p.classList.toggle("is-active", p.id === `panel-${tabName}`);
    });
    if (tabName === "overview") loadBinaryMap();
    if (tabName === "lab") {
      loadFunctions();
      if (state.selectedAddr) loadFunctionDetail(state.selectedAddr);
    }
    if (tabName === "apis") loadImports();
  }

  function jumpToFunction(addr) {
    state.selectedAddr = addr;
    setTab("lab");
    loadFunctionDetail(addr);
  }

  /* -----------------------------------------------------------------------
   * Status & Pipeline Stepper
   * ----------------------------------------------------------------------- */
  async function loadStatus() {
    const s = await api("/api/status");
    state.status = s;

    // Project selector
    const sel = $("projectSelect");
    sel.innerHTML = "";
    (s.projects || []).forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.path;
      opt.textContent = `${p.name} (${p.binary})`;
      if (p.path === s.root) opt.selected = true;
      sel.appendChild(opt);
    });

    // Binary metadata strip
    const kb = s.binary_size ? `${(s.binary_size / 1024).toFixed(1)} KB` : "—";
    $("metaBinary").textContent = `${s.binary_name} (${kb})`;
    $("metaArch").textContent = `${s.arch} ${s.format}`;
    $("metaMd5").textContent = s.binary_md5 ? `md5 ${s.binary_md5.slice(0, 12)}` : "md5 —";

    // Pipeline steps (normalize nested discovery/difftest shapes)
    const rawDiscF = s.discovery && s.discovery.functions;
    const nDisc =
      (s.discovery && typeof s.discovery.functions_total === "number" ? s.discovery.functions_total : null) ??
      (rawDiscF && typeof rawDiscF === "object" ? Number(rawDiscF.total || 0) : Number(rawDiscF || 0));
    const nLift = Number((s.lift && s.lift.functions) || 0);
    const diffGate = (s.difftest && s.difftest.gate) || "";
    const diffOk = diffGate === "pass";
    const diffComp = Number((s.difftest && (s.difftest.compared ?? s.difftest.functions_compared)) || 0);
    const diffMatch = Number((s.difftest && (s.difftest.all_match ?? s.difftest.functions_all_match ?? diffComp)) || 0);
    const wasmReady = s.builds && s.builds.wasm_ready;
    const wasmKb = wasmReady ? `${(s.builds.wasm_bytes / 1024).toFixed(1)} KB` : "not built";

    $("step1").classList.add("is-done");
    $("step1Metric").textContent = s.binary_name;
    $("step2").classList.toggle("is-done", nDisc > 0);
    $("step2Metric").textContent = nDisc ? `${nDisc.toLocaleString()} funcs` : "pending";
    $("step3").classList.toggle("is-done", nLift > 0);
    $("step3Metric").textContent = nLift ? `${nLift.toLocaleString()} lifted` : "pending";
    $("step4").classList.toggle("is-done", diffOk);
    $("step4Metric").textContent = diffOk
      ? diffComp > 0
        ? `${diffMatch}/${diffComp} pass`
        : "pass"
      : diffGate || "pending";
    $("step5").classList.toggle("is-done", Boolean(wasmReady));
    $("step5Metric").textContent = wasmKb;

    // Overview stats
    const q = s.queue || {};
    const lc = s.ledger_counts || {};
    const covPctVal =
      s.discovery && s.discovery.text_coverage_pct != null
        ? s.discovery.text_coverage_pct
        : s.discovery && typeof s.discovery.text_coverage === "number"
        ? (s.discovery.text_coverage * 100).toFixed(1)
        : null;
    const covPct = covPctVal != null ? `${covPctVal}% .text decoded` : "PE32";
    $("statFuncs").textContent = nDisc.toLocaleString();
    $("statFuncsNote").textContent = covPct;

    const liveN = q.ran_count || 0;
    $("statLive").textContent = liveN.toLocaleString();
    $("statLiveNote").textContent = liveN ? "Confirmed via RN_COV" : "Run WASM or Native to record";

    const vCount = lc.V || 0;
    $("statVerified").textContent = vCount.toLocaleString();
    $("statVerifiedNote").textContent = `${lc.I || 0} inferred, ${lc.total_named || 0} total named`;

    const trapsN = (s.lift && s.lift.blocked_count) || 0;
    $("statTraps").textContent = trapsN.toLocaleString();
    $("statTraps").className = `stat-value ${trapsN === 0 ? "is-ok" : "is-danger"}`;
    $("statTrapsNote").textContent = trapsN === 0 ? "Zero translation traps" : "Blocked x86 instructions";

    renderQueue(q);
    renderSections(s.sections || []);
    renderToolchain(s.toolchain || {});
  }

  function renderToolchain(tc) {
    const host = $("toolchainChips");
    if (!host) return;
    const order = ["capstone", "lifter", "unicorn", "emcc", "rea", "ghidra", "hopper"];
    host.innerHTML = order
      .map((k) => {
        const it = tc[k];
        if (!it) return "";
        const cls = it.installed ? "is-ready" : "";
        return `<span class="tool-chip ${cls}" data-tool="${esc(k)}" title="${esc(it.path || it.role)}"><span class="tool-dot"></span>${esc(it.name)}</span>`;
      })
      .join("");
  }

  function highlightActiveTool(running, stage) {
    const map = { discover: "capstone", lift: "lifter", verify: "unicorn", build: "emcc", ghidra: "ghidra", rea: "rea" };
    const activeKey = running ? map[stage] || "" : "";
    document.querySelectorAll(".tool-chip").forEach((el) => {
      el.classList.toggle("is-running", Boolean(activeKey && el.dataset.tool === activeKey));
    });
  }

  function renderSections(sections) {
    const host = $("sectionsList");
    if (!sections.length) {
      host.innerHTML = `<span class="panel-sub">No PE section metadata</span>`;
      return;
    }
    host.innerHTML = sections
      .map(
        (sec) =>
          `<span class="badge ${sec.exec ? "badge-live" : ""}">${esc(sec.name)}&nbsp;·&nbsp;<span class="mono">${esc(sec.va)}</span></span>`
      )
      .join("");
  }

  function renderQueue(q) {
    const tbody = $("queueBody");
    const rows = [];
    const pushTier = (list, tier, badgeCls, desc) => {
      (list || []).slice(0, 6).forEach((item) => {
        const addr = typeof item === "string" ? item : item.addr;
        const detail = typeof item === "object" && item.traps ? item.traps.join(", ") : desc;
        rows.push({ addr, tier, badgeCls, detail });
      });
    };
    pushTier(q.t1_live_traps, "T1 live trap", "badge-trap", "Runtime trap");
    pushTier(q.t2_live_unnamed, "T2 live unnamed", "badge-live", "Executed, needs V name");
    pushTier(q.t3_static_traps, "T3 static trap", "badge-i", "Static trap");

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="panel-sub">Queue clear. Run Discover, Lift, or WASM to populate priorities.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(
        (r) => `
      <tr>
        <td class="mono">${esc(r.addr)}</td>
        <td><span class="badge ${r.badgeCls}">${esc(r.tier)}</span></td>
        <td class="panel-sub">${esc(r.detail)}</td>
        <td><button type="button" class="btn-sm" data-jump="${esc(r.addr)}">Inspect</button></td>
      </tr>`
      )
      .join("");

    tbody.querySelectorAll("[data-jump]").forEach((btn) => {
      btn.addEventListener("click", () => jumpToFunction(btn.dataset.jump));
    });
  }

  /* -----------------------------------------------------------------------
   * Interactive Binary Map & Global Strings Explorer
   * ----------------------------------------------------------------------- */
  async function loadBinaryMap() {
    try {
      const data = await api("/api/binary-map");
      if (!state.binMapCanvas) {
        state.binMapCanvas = new window.RecompCanvas.BinaryMapCanvas(
          $("binaryMapCanvas"),
          $("binaryMapHud"),
          (addr) => jumpToFunction(addr)
        );
      }
      state.binMapCanvas.setData(data);
    } catch (err) {
      $("binaryMapHud").textContent = err.message;
    }
  }

  async function loadStrings() {
    const q = $("stringsSearch").value.trim();
    const tbody = $("stringsBody");
    try {
      const data = await api(`/api/strings?q=${encodeURIComponent(q)}&limit=40`);
      $("stringsCount").textContent = `${data.total.toLocaleString()} strings`;
      if (!data.items.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="panel-sub">No matching ASCII strings in .rdata / .data.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.items
        .map((it) => {
          const xrefs = (it.xrefs || [])
            .slice(0, 2)
            .map((x) => `<button type="button" class="btn-sm mono" data-jump="${esc(x)}">${esc(x)}</button>`)
            .join(" ");
          return `
        <tr>
          <td class="mono">${esc(it.va)}</td>
          <td><span class="badge">${esc(it.section)}</span></td>
          <td class="mono">${esc(it.text)}</td>
          <td>${xrefs || '<span class="panel-sub">data</span>'}</td>
        </tr>`;
        })
        .join("");
      tbody.querySelectorAll("[data-jump]").forEach((b) => {
        b.addEventListener("click", () => jumpToFunction(b.dataset.jump));
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="3" class="panel-sub">${esc(err.message)}</td></tr>`;
    }
  }

  /* -----------------------------------------------------------------------
   * REA Function Lab
   * ----------------------------------------------------------------------- */
  async function loadFunctions() {
    const data = await api(
      `/api/functions?filter=${encodeURIComponent(state.filter)}&q=${encodeURIComponent(state.search)}&limit=180`
    );
    $("funcCount").textContent = `${data.count} shown`;
    const list = $("funcList");
    if (!data.items.length) {
      list.innerHTML = `<div class="empty-state">No functions match this filter.</div>`;
      return;
    }
    list.innerHTML = data.items
      .map((f) => {
        const badge = f.traps.length
          ? `<span class="badge badge-trap">trap</span>`
          : f.state === "V"
          ? `<span class="badge badge-v">V</span>`
          : f.state === "I"
          ? `<span class="badge badge-i">I</span>`
          : f.ran
          ? `<span class="badge badge-live">live</span>`
          : `<span class="badge">U</span>`;
        const sel = state.selectedAddr === f.addr ? "is-selected" : "";
        return `
        <button type="button" class="func-row ${sel}" data-addr="${esc(f.addr)}">
          <span class="func-row-main">
            <span class="func-row-name">${esc(f.name || `sub_${f.addr.slice(2)}`)}</span>
            <span class="func-row-addr">${esc(f.addr)}</span>
          </span>
          ${badge}
        </button>`;
      })
      .join("");

    list.querySelectorAll(".func-row").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedAddr = btn.dataset.addr;
        list.querySelectorAll(".func-row").forEach((b) => b.classList.toggle("is-selected", b === btn));
        loadFunctionDetail(btn.dataset.addr);
      });
    });

    if (!state.selectedAddr && data.items.length) {
      state.selectedAddr = data.items[0].addr;
      loadFunctionDetail(state.selectedAddr);
    }
  }

  async function loadFunctionDetail(addr) {
    $("fnTitle").textContent = `Loading ${addr}...`;
    try {
      const [detail, graph] = await Promise.all([
        api(`/api/function?addr=${encodeURIComponent(addr)}`),
        api(`/api/callgraph?addr=${encodeURIComponent(addr)}`),
      ]);
      state.fnDetail = detail;

      const led = detail.ledger || {};
      $("fnTitle").textContent = led.name ? `${led.name} (${detail.addr})` : `sub_${detail.addr.slice(2)} (${detail.addr})`;

      const badges = [];
      badges.push(`<span class="badge">${esc(detail.seed)}</span>`);
      if (detail.ran) badges.push(`<span class="badge badge-live">live RN_COV</span>`);
      if (led.confidence === "V") badges.push(`<span class="badge badge-v">Verified V</span>`);
      else if (led.confidence === "I") badges.push(`<span class="badge badge-i">Inferred I</span>`);
      if (detail.traps && detail.traps.length) {
        badges.push(`<span class="badge badge-trap">${esc(detail.traps.join(", "))}</span>`);
      }
      $("fnBadges").innerHTML = badges.join("");

      // Interactive Call-Graph Canvas
      if (!state.callGraphCanvas) {
        state.callGraphCanvas = new window.RecompCanvas.CallGraphCanvas(
          $("callGraphCanvas"),
          $("callGraphHud"),
          (targetAddr) => jumpToFunction(targetAddr)
        );
      }
      state.callGraphCanvas.setGraph(graph);

      // ELI5 Summary
      const eli5 = detail.eli5 || {};
      $("fnEli5Text").textContent = `${eli5.headline || ""} ${eli5.next_step || ""}`.trim();

      // Xrefs & Strings bar
      renderXrefChips("xrefsIn", detail.xrefs_in || [], true);
      renderXrefChips("xrefsOut", detail.xrefs_out || [], true);
      renderStringChips("xrefsStr", detail.strings || []);

      // Code tabs availability
      $("codeTabGhidra").disabled = !detail.ghidra_c;
      $("codeTabHopper").disabled = !detail.hopper_c;
      if ((state.codeView === "ghidra" && !detail.ghidra_c) || (state.codeView === "hopper" && !detail.hopper_c)) {
        state.codeView = "disasm";
      }
      renderCodeView();

      // Pre-fill V/I/U tagger form with binary-proven evidence
      $("tagName").value = led.name || "";
      $("tagSystem").value = led.system || (state.status && state.status.subsystems[0]) || "core";
      $("tagState").value = led.confidence || "V";
      const evPack = detail.evidence_pack || {};
      $("tagEvidence").value = led.evidence || evPack.suggested_evidence_line || `${detail.addr}`;
    } catch (err) {
      notify(err.message, true);
    }
  }

  function renderXrefChips(containerId, items, clickable) {
    const el = $(containerId);
    if (!items.length) {
      el.innerHTML = `<span class="panel-sub">none</span>`;
      return;
    }
    el.innerHTML = items
      .slice(0, 10)
      .map((it) => {
        const label = it.name ? `${it.name} (${it.addr})` : it.addr;
        return clickable
          ? `<button type="button" class="btn-sm mono" data-jump="${esc(it.addr)}">${esc(label)}</button>`
          : `<span class="badge mono">${esc(label)}</span>`;
      })
      .join("");
    el.querySelectorAll("[data-jump]").forEach((b) => {
      b.addEventListener("click", () => jumpToFunction(b.dataset.jump));
    });
  }

  function renderStringChips(containerId, items) {
    const el = $(containerId);
    if (!items.length) {
      el.innerHTML = `<span class="panel-sub">none</span>`;
      return;
    }
    el.innerHTML = items
      .slice(0, 8)
      .map((s) => `<span class="badge badge-i mono">${esc(s.va)}: "${esc(s.text.slice(0, 48))}"</span>`)
      .join("");
  }

  function formatDisasmHtml(lines, compact = false) {
    if (!lines || !lines.length) return "No disassembly available.";
    return lines
      .map((ln) => {
        const m = ln.mnemonic;
        const mCls = m === "call" ? "is-call" : m.startsWith("j") ? "is-branch" : "";
        const cmt = ln.comment ? `<span class="d-comment">; ${esc(ln.comment)}</span>` : "";
        if (compact) {
          return `<div class="disasm-line is-compact"><span class="d-addr">${esc(ln.addr)}</span><span class="d-mnem ${mCls}">${esc(m)}</span><span>${esc(ln.op_str)}${cmt}</span></div>`;
        }
        return `<div class="disasm-line"><span class="d-addr">${esc(ln.addr)}</span><span class="d-bytes">${esc(ln.bytes)}</span><span class="d-mnem ${mCls}">${esc(m)}</span><span>${esc(ln.op_str)}${cmt}</span></div>`;
      })
      .join("");
  }

  async function loadCompareDeck(preferredAddr) {
    const sel = $("compareFnSelect");
    const x86Pane = $("compareX86Pane");
    const cPane = $("compareCPane");
    if (!sel || !x86Pane || !cPane) return;
    try {
      const list = await api("/api/functions?filter=all&limit=40");
      const items = list.items || [];
      if (!items.length) {
        sel.innerHTML = `<option value="">No functions discovered</option>`;
        x86Pane.textContent = "Run Discover to populate x86-32 disassembly.";
        cPane.textContent = "Run Lift to generate portable C.";
        return;
      }
      const target =
        preferredAddr && items.some((i) => i.addr === preferredAddr)
          ? preferredAddr
          : state.compareAddr && items.some((i) => i.addr === state.compareAddr)
          ? state.compareAddr
          : items[0].addr;
      state.compareAddr = target;

      sel.innerHTML = items
        .map((f) => {
          const lbl = f.name ? `${f.name} (${f.addr})` : `sub_${f.addr.slice(2)} (${f.addr})`;
          return `<option value="${esc(f.addr)}"${f.addr === target ? " selected" : ""}>${esc(lbl)}</option>`;
        })
        .join("");

      const detail = await api(`/api/function?addr=${encodeURIComponent(target)}`);
      const lines = (detail.disasm && detail.disasm.lines) || [];
      const led = detail.ledger || {};
      $("compareX86Meta").textContent = `${detail.addr} · ${lines.length} insns`;
      const cStatus = detail.traps && detail.traps.length ? `trap: ${detail.traps.length}` : led.confidence === "V" ? "Verified V" : "C99 lifted";
      const cMeta = $("compareCMeta");
      cMeta.textContent = cStatus;
      cMeta.className = `badge ${detail.traps && detail.traps.length ? "badge-trap" : "badge-v"}`;
      x86Pane.innerHTML = formatDisasmHtml(lines, true);
      cPane.textContent = detail.lifted_c || "// Not lifted yet. Click Lift in the pipeline bar.";
    } catch (err) {
      x86Pane.textContent = err.message;
    }
  }

  function renderCodeView() {
    const d = state.fnDetail;
    document.querySelectorAll(".code-tab-btn").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.view === state.codeView);
    });
    const host = $("codeFrameContainer");
    if (!d) {
      host.innerHTML = `<div class="code-frame" id="codeFrame">Select a function from the left list.</div>`;
      return;
    }
    if (state.codeView === "split") {
      const lines = (d.disasm && d.disasm.lines) || [];
      const cSrc = d.lifted_c || "// Not lifted yet. Run Lift in the top pipeline.";
      host.innerHTML = `
        <div class="compare-grid">
          <div class="compare-pane">
            <div class="compare-pane-head">
              <span>x86-32 Disassembly</span>
              <span class="badge">${esc(d.addr)} · ${lines.length} insns</span>
            </div>
            <div class="compare-code">${formatDisasmHtml(lines, true)}</div>
          </div>
          <div class="compare-pane">
            <div class="compare-pane-head">
              <span>Lifted Portable C</span>
              <span class="badge ${d.traps && d.traps.length ? "badge-trap" : "badge-v"}">${d.traps && d.traps.length ? `${d.traps.length} traps` : "clean C99"}</span>
            </div>
            <div class="compare-code">${esc(cSrc)}</div>
          </div>
        </div>`;
      return;
    }

    host.innerHTML = `<div class="code-frame" id="codeFrame"></div>`;
    const frame = $("codeFrame");
    if (state.codeView === "disasm") {
      const lines = (d.disasm && d.disasm.lines) || [];
      frame.innerHTML = formatDisasmHtml(lines, false);
    } else if (state.codeView === "c") {
      frame.textContent = d.lifted_c || "// Not lifted yet. Run Lift in the top pipeline.";
    } else if (state.codeView === "ghidra") {
      frame.textContent = d.ghidra_c || "// No Ghidra export found in census/ghidra/.";
    } else if (state.codeView === "hopper") {
      frame.textContent = d.hopper_c || "// No Hopper export found in census/hopper/decomp.c.";
    } else if (state.codeView === "evidence") {
      frame.textContent = JSON.stringify(d.evidence_pack || {}, null, 2);
    }
  }

  /* -----------------------------------------------------------------------
   * Interactive Live SSE Stream Engine
   * ----------------------------------------------------------------------- */
  let refreshTimer = null;
  function scheduleLiveRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      try {
        await loadStatus();
        if (state.tab === "overview") {
          await loadBinaryMap();
          await loadCompareDeck();
          await loadStrings();
        }
        if (state.tab === "lab") await loadFunctions();
        if (state.tab === "apis") await loadImports();
      } catch (_) {}
    }, 180);
  }

  function updateActiveStageCard(running, stage, elapsedSec) {
    const map = { discover: "step2", lift: "step3", verify: "step4", build: "step5" };
    ["step2", "step3", "step4", "step5"].forEach((id) => {
      const el = $(id);
      if (el) el.classList.toggle("is-active", Boolean(running && map[stage] === id));
    });
    if (running && map[stage]) {
      const mEl = $(`${map[stage]}Metric`);
      if (mEl && typeof elapsedSec === "number") {
        mEl.textContent = `${stage} · ${Math.floor(elapsedSec)}s`;
      }
    }
  }

  function updateStreamChrome(running, stage, done, total, rate, project, elapsedSec, beat) {
    const pill = $("streamStatusPill");
    const lbl = $("streamStatusLabel");
    const fill = $("streamMeterFill");
    const bar = $("streamProgressBar");
    const txt = $("streamMeterText");
    const stopBtn = $("btnStopStream");

    pill.classList.toggle("is-live", Boolean(running));
    if (running) {
      const tPart = typeof elapsedSec === "number" ? ` · ${Math.floor(elapsedSec)}s` : "";
      const bPart = beat ? ` · hb #${beat}` : "";
      lbl.textContent = `${stage || "live"} · ${project || ""}${tPart}${bPart}`;
    } else {
      lbl.textContent = "idle · SSE OK";
    }
    stopBtn.disabled = !running;
    updateActiveStageCard(running, stage, elapsedSec);
    highlightActiveTool(running, stage);
    if (state.binMapCanvas) {
      if (running) {
        const ratio = total > 0 ? Math.min(1, Math.max(0.04, done / total)) : 0.15;
        state.binMapCanvas.setScanProgress(ratio, `${stage || "live"} · ${done.toLocaleString()}/${total.toLocaleString()}`);
      } else {
        state.binMapCanvas.setScanProgress(-1, "");
      }
    }

    const pct = total > 0 ? Math.min(1, Math.max(0, done / total)) : running ? 0.12 : 0;
    fill.style.transform = `scaleX(${pct})`;
    bar.setAttribute("aria-valuenow", String(Math.round(pct * 100)));

    if (running) {
      const rTxt = rate > 0 ? ` · ${Math.round(rate)} fn/s` : "";
      const eTxt = typeof elapsedSec === "number" ? ` · ${Math.floor(elapsedSec)}s alive` : "";
      txt.textContent =
        total > 1
          ? `${done.toLocaleString()} / ${total.toLocaleString()} (${Math.round(pct * 100)}%)${rTxt}${eTxt}`
          : `${stage || "working"}…${eTxt}`;
    } else if (total > 0) {
      txt.textContent = `Done (${done.toLocaleString()} / ${total.toLocaleString()})`;
    } else {
      txt.textContent = "Ready · SSE ping OK";
    }
  }

  function renderBatchQueue(items) {
    const row = $("batchQueueRow");
    if (!items || !items.length) {
      row.classList.remove("is-visible");
      row.innerHTML = "";
      return;
    }
    row.classList.add("is-visible");
    row.innerHTML = items
      .map((it) => {
        const cls =
          it.state === "done"
            ? "badge-v"
            : it.state === "running"
            ? "badge-live"
            : it.state === "error"
            ? "badge-trap"
            : "";
        return `<span class="badge ${cls} mono">${esc(it.name)}: ${esc(it.state)}</span>`;
      })
      .join("");
  }

  function renderStreamFeed() {
    const feed = $("streamFeed");
    const flt = state.streamFilter;
    const filtered = state.streamEvents.filter((ev) => {
      if (flt === "all") return true;
      if (flt === "stage") return ev.kind === "stage" || ev.kind === "done" || ev.kind === "error";
      return ev.kind === flt;
    });
    if (!filtered.length) {
      feed.innerHTML = `<div class="stream-row"><span class="stream-ts">ready</span><span class="badge">sse</span><span class="stream-msg">No events for this filter yet.</span></div>`;
      return;
    }
    feed.innerHTML = filtered
      .slice(-80)
      .map((ev) => {
        const bCls =
          ev.kind === "unicorn" || ev.kind === "done"
            ? "badge-v"
            : ev.kind === "trap" || ev.kind === "error"
            ? "badge-trap"
            : ev.kind === "fn"
            ? "badge-i"
            : "badge-live";
        const jumpBtn = ev.addr
          ? `<button type="button" class="btn-sm mono" data-jump="${esc(ev.addr)}">${esc(ev.addr)}</button>`
          : "";
        return `
        <div class="stream-row">
          <span class="stream-ts">${esc(ev.ts || "")}</span>
          <span class="badge ${bCls}">${esc(ev.kind || "ev")}</span>
          ${jumpBtn}
          <span class="stream-msg" title="${esc(ev.msg || "")}">${esc(ev.msg || "")}</span>
        </div>`;
      })
      .join("");

    feed.querySelectorAll("[data-jump]").forEach((b) => {
      b.addEventListener("click", () => jumpToFunction(b.dataset.jump));
    });
    feed.scrollTop = feed.scrollHeight;
  }

  function handleStreamEvent(ev) {
    if (!ev) return;
    updateStreamChrome(ev.running, ev.stage, ev.done || 0, ev.total || 0, ev.rate || 0, ev.project || "", ev.elapsed_sec, ev.beat);
    if (ev.batch_queue) renderBatchQueue(ev.batch_queue);

    // Update live Proof-of-Work bar (shows real CLI PID + command or active WEB UI tool)
    const proofBar = $("streamProofBar");
    const proofSrc = $("streamProofSource");
    const proofCmd = $("streamProofCmd");
    if (proofBar && proofSrc && proofCmd) {
      if (ev.source === "cli") {
        proofBar.classList.add("is-cli");
        proofSrc.textContent = `CLI pid ${ev.pid || "?"} · ${ev.tool || ev.stage || "job"} · ${ev.project || ""}`;
        proofCmd.textContent = ev.cmd ? `$ ${ev.cmd}` : "";
      } else if (ev.running) {
        proofBar.classList.remove("is-cli");
        proofSrc.textContent = `WEB UI · active: ${ev.tool || ev.stage || "running"} · ${ev.project || ""}`;
        proofCmd.textContent = ev.elapsed_sec != null ? `alive ${ev.elapsed_sec}s` : "";
      } else if (ev.kind === "done" || ev.kind === "refresh") {
        proofBar.classList.remove("is-cli");
        proofSrc.textContent = `IDLE · last: ${ev.stage || "done"} (${ev.source === "cli" ? "CLI" : "WEB UI"})`;
      }
    }

    if (ev.kind === "heartbeat") {
      return;
    }
    if (ev.kind === "progress") {
      if (ev.msg) $("streamMeterText").textContent = ev.msg;
      if (ev.stage === "discover" && ev.done > 0) {
        $("statFuncs").textContent = Number(ev.done).toLocaleString();
        $("step2Metric").textContent = `${Number(ev.done).toLocaleString()} funcs…`;
      } else if (ev.stage === "lift" && ev.done > 0) {
        $("step3Metric").textContent = `${Number(ev.done).toLocaleString()} lifted…`;
      }
      return;
    }
    if (ev.kind === "refresh") {
      scheduleLiveRefresh();
      return;
    }
    state.streamEvents.push(ev);
    if (state.streamEvents.length > 220) state.streamEvents.shift();
    renderStreamFeed();

    // Live Compare Auto-Follow: flip real x86 <-> C functions as they get lifted or verified
    if ((ev.kind === "fn" || ev.kind === "unicorn") && ev.addr && state.tab === "overview") {
      const now = Date.now();
      if (!state._lastCompareFollow || now - state._lastCompareFollow >= 1400) {
        state._lastCompareFollow = now;
        loadCompareDeck(ev.addr);
      }
    }

    if (ev.native_result) {
      const res = ev.native_result;
      const out = $("wasmConsole");
      out.textContent = `[Native macOS run] ok=${res.ok} exit=${res.exit_code} why=${res.halt_why}\n${res.stdout || ""}\n`;
      if (res.msgbox_text) out.textContent += `[MessageBoxA] ${res.msgbox_title}: ${res.msgbox_text}\n`;
    }
    if (ev.kind === "error") notify(ev.msg || "Stream error", true);
  }

  function connectLiveStream() {
    if (state.streamSource) {
      try { state.streamSource.close(); } catch (_) {}
    }
    const es = new EventSource("/api/stream");
    state.streamSource = es;

    es.addEventListener("snapshot", (e) => {
      try {
        const snap = JSON.parse(e.data);
        state.streamEvents = snap.events || [];
        updateStreamChrome(snap.running, snap.stage, snap.done || 0, snap.total || 0, snap.rate || 0, snap.project || "");
        renderBatchQueue(snap.batch_queue || []);
        renderStreamFeed();
      } catch (_) {}
    });

    ["stage", "progress", "heartbeat", "fn", "unicorn", "trap", "done", "error", "refresh"].forEach((evType) => {
      es.addEventListener(evType, (e) => {
        try {
          handleStreamEvent(JSON.parse(e.data));
        } catch (_) {}
      });
    });

    es.addEventListener("ping", (e) => {
      try {
        const p = JSON.parse(e.data);
        if (!p.running) {
          $("streamStatusLabel").textContent = `idle · pong #${p.ping}`;
        }
      } catch (_) {}
    });

    es.onerror = () => {
      $("streamStatusLabel").textContent = "reconnecting SSE…";
    };
  }

  async function triggerStream(action, payload) {
    // Immediate 0ms visual feedback before server even finishes starting the worker thread
    const proj = (state.status && state.status.project) || "";
    updateStreamChrome(true, action === "pipeline" ? "discover" : action, 0, 1, 0, proj, 0, 0);
    $("streamMeterText").textContent = `Starting ${action}…`;
    try {
      await api("/api/stream/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(payload || {}) }),
      });
    } catch (err) {
      updateStreamChrome(false, "idle", 0, 0, 0, proj);
      notify(err.message, true);
    }
  }

  /* -----------------------------------------------------------------------
   * Pipeline Actions
   * ----------------------------------------------------------------------- */
  async function runAction(endpoint, payload, btnEl, label) {
    const oldText = btnEl.textContent;
    btnEl.disabled = true;
    btnEl.textContent = `${label}...`;
    try {
      const res = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      await loadStatus();
      if (state.tab === "overview") await loadBinaryMap();
      if (state.tab === "lab") await loadFunctions();
      return res;
    } catch (err) {
      notify(err.message, true);
      throw err;
    } finally {
      btnEl.disabled = false;
      btnEl.textContent = oldText;
    }
  }

  /* -----------------------------------------------------------------------
   * Live WASM Runner
   * ----------------------------------------------------------------------- */
  async function runWasmInBrowser() {
    const out = $("wasmConsole");
    const traceBody = $("wasmTraceBody");
    const s = state.status;
    if (!s || !s.builds || !s.builds.wasm_ready) {
      out.textContent = "WASM binary is not built yet. Click 'Build WASM' first.";
      return;
    }
    out.textContent = `Fetching ${s.builds.wasm_js_url} and ${s.builds.wasm_exe_url}...\n`;
    try {
      const exeBuf = new Uint8Array(await (await fetch(s.builds.wasm_exe_url)).arrayBuffer());
      await new Promise((resolve, reject) => {
        const sc = document.createElement("script");
        sc.src = `${s.builds.wasm_js_url}?t=${Date.now()}`;
        sc.onload = resolve;
        sc.onerror = () => reject(new Error("Failed to load Emscripten JS glue"));
        document.head.appendChild(sc);
      });

      const mod = await window.RecompModule({
        locateFile: (p) => `/wasm/${p}`,
        print: (txt) => {
          out.textContent += txt + "\n";
        },
        printErr: (txt) => {
          out.textContent += `[stderr] ${txt}\n`;
        },
      });

      const ptr = mod._malloc(exeBuf.length);
      mod.HEAPU8.set(exeBuf, ptr);
      const rc = mod.ccall("rn_wasm_run", "number", ["number", "number"], [ptr, exeBuf.length]);
      mod._free(ptr);

      const jsonPtr = mod.ccall("rn_wasm_last_json", "number", [], []);
      const rawJson = mod.UTF8ToString(jsonPtr);
      const report = JSON.parse(rawJson || "{}");

      out.textContent += `\n--- Execution finished (rc=${rc}, exit=${report.exit_code}, why=${report.halt_why}) ---\n`;
      if (report.stdout) out.textContent += report.stdout + "\n";
      if (report.msgbox_title || report.msgbox_text) {
        out.textContent += `[MessageBoxA] ${report.msgbox_title}: ${report.msgbox_text}\n`;
      }

      const calls = report.api_trace || [];
      traceBody.innerHTML = calls.length
        ? calls
            .map(
              (c) => `
            <tr>
              <td class="mono">${esc(c.dll)}</td>
              <td class="mono">${esc(c.name)}</td>
              <td><span class="badge ${c.implemented ? "badge-v" : "badge-trap"}">${c.implemented ? "implemented" : "auto-stub"}</span></td>
            </tr>`
            )
            .join("")
        : `<tr><td colspan="3" class="panel-sub">No API calls recorded.</td></tr>`;

      if (report.cov_addrs && report.cov_addrs.length) {
        await api("/api/save-cov", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ addrs: report.cov_addrs }),
        });
        await loadStatus();
        notify(`WASM finished: synced ${report.cov_addrs.length} live functions to RN_COV.`);
      }
    } catch (err) {
      out.textContent += `\nError: ${err.message}\n`;
      notify(err.message, true);
    }
  }

  /* -----------------------------------------------------------------------
   * Windows APIs Radar
   * ----------------------------------------------------------------------- */
  async function loadImports() {
    const data = await api("/api/imports");
    $("apiSummary").textContent = `${data.implemented} / ${data.total} imported APIs implemented`;
    const tbody = $("apisBody");
    if (!data.dlls.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="panel-sub">No Windows imports found.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.dlls
      .map((d) => {
        const pct = d.total ? Math.round((d.implemented / d.total) * 100) : 0;
        const missing = d.apis
          .filter((a) => !a.implemented)
          .slice(0, 6)
          .map((a) => a.name)
          .join(", ");
        return `
        <tr>
          <td class="mono">${esc(d.dll)}</td>
          <td class="panel-sub">${esc(d.eli5)}</td>
          <td>
            <div class="mono">${d.implemented} / ${d.total} (${pct}%)</div>
            <div class="progress-track"><div class="progress-fill" style="transform: scaleX(${pct / 100})"></div></div>
          </td>
          <td class="mono panel-sub">${esc(missing || "all ready")}</td>
        </tr>`;
      })
      .join("");
  }

  /* -----------------------------------------------------------------------
   * Event Binding & Init
   * ----------------------------------------------------------------------- */
  function bindEvents() {
    $("langToggle").addEventListener("click", () => {
      state.lang = state.lang === "es" ? "en" : "es";
      applyTranslations();
    });

    $("eli5Toggle").addEventListener("click", () => {
      state.eli5 = !state.eli5;
      document.body.classList.toggle("hide-eli5", !state.eli5);
      applyTranslations();
    });

    $("projectSelect").addEventListener("change", async (e) => {
      try {
        await api("/api/switch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: e.target.value }),
        });
        state.selectedAddr = null;
        state.compareAddr = null;
        await loadStatus();
        await loadBinaryMap();
        await loadCompareDeck();
        await loadStrings();
        if (state.tab === "lab") await loadFunctions();
        if (state.tab === "apis") await loadImports();
      } catch (err) {
        notify(err.message, true);
      }
    });

    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.addEventListener("click", () => setTab(b.dataset.tab));
    });

    // Pipeline buttons -> Live SSE Stream
    $("btnDiscover").addEventListener("click", () => triggerStream("discover", {}));
    $("btnLift").addEventListener("click", () => triggerStream("lift", { force: false }));
    $("btnVerify").addEventListener("click", () => triggerStream("verify", { cases: 4, limit: 40 }));
    $("btnBuildWasm").addEventListener("click", () => triggerStream("build", { target: "web" }));
    if ($("btnRunGhidra")) $("btnRunGhidra").addEventListener("click", () => triggerStream("ghidra", {}));
    if ($("btnRunRea")) $("btnRunRea").addEventListener("click", () => triggerStream("rea", {}));

    // Interactive Stream Studio controls
    $("btnRunPipeline").addEventListener("click", () => triggerStream("pipeline", { with_wasm: false, cases: 4, limit: 40 }));
    $("btnOpenBatch").addEventListener("click", () => $("newProjModal").classList.add("is-open"));
    $("btnStopStream").addEventListener("click", async () => {
      try {
        await api("/api/stream/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      } catch (err) {
        notify(err.message, true);
      }
    });
    $("btnClearStream").addEventListener("click", () => {
      state.streamEvents = [];
      renderStreamFeed();
    });
    document.querySelectorAll(".stream-filter-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.streamFilter = chip.dataset.sfilter;
        document.querySelectorAll(".stream-filter-chip").forEach((c) => c.classList.toggle("is-active", c === chip));
        renderStreamFeed();
      });
    });

    // Strings search
    let strTimer = null;
    $("stringsSearch").addEventListener("input", () => {
      clearTimeout(strTimer);
      strTimer = setTimeout(loadStrings, 180);
    });

    // Function Lab search & filters
    let fnTimer = null;
    $("funcSearch").addEventListener("input", (e) => {
      state.search = e.target.value;
      clearTimeout(fnTimer);
      fnTimer = setTimeout(loadFunctions, 160);
    });

    // Overview Live Compare Deck controls
    if ($("compareFnSelect")) {
      $("compareFnSelect").addEventListener("change", (e) => {
        state.compareAddr = e.target.value;
        loadCompareDeck(state.compareAddr);
      });
    }
    if ($("btnCompareVerify")) {
      $("btnCompareVerify").addEventListener("click", () => {
        if (state.compareAddr) triggerStream("verify", { addr: state.compareAddr, cases: 8 });
      });
    }
    if ($("btnCompareOpenLab")) {
      $("btnCompareOpenLab").addEventListener("click", () => {
        if (state.compareAddr) jumpToFunction(state.compareAddr);
      });
    }

    document.querySelectorAll("#panel-lab .func-sidebar .filter-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.filter = chip.dataset.filter;
        document.querySelectorAll("#panel-lab .func-sidebar .filter-chip").forEach((c) => c.classList.toggle("is-active", c === chip));
        loadFunctions();
      });
    });

    document.querySelectorAll(".code-tab-btn").forEach((b) => {
      b.addEventListener("click", () => {
        state.codeView = b.dataset.view;
        renderCodeView();
      });
    });

    $("btnVerifyOne").addEventListener("click", async (e) => {
      if (!state.selectedAddr) return;
      const res = await runAction("/api/action/verify", { addr: state.selectedAddr, cases: 8 }, e.currentTarget, "Testing");
      notify(`Unicorn ${state.selectedAddr}: gate=${res.gate}, mismatches=${(res.mismatches || []).length}`);
    });

    $("btnCopyEvidence").addEventListener("click", async () => {
      if (!state.fnDetail || !state.fnDetail.evidence_pack) return;
      await navigator.clipboard.writeText(JSON.stringify(state.fnDetail.evidence_pack, null, 2));
      notify("Evidence JSON copied to clipboard.");
    });

    $("tagForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.selectedAddr) return;
      try {
        await api("/api/tag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            addr: state.selectedAddr,
            name: $("tagName").value.trim(),
            system: $("tagSystem").value.trim() || "core",
            state: $("tagState").value,
            evidence: $("tagEvidence").value.trim(),
          }),
        });
        await loadStatus();
        await loadFunctions();
        await loadFunctionDetail(state.selectedAddr);
      } catch (err) {
        notify(err.message, true);
      }
    });

    // WASM Runner buttons
    $("btnRunWasm").addEventListener("click", runWasmInBrowser);
    $("btnRunNative").addEventListener("click", async (e) => {
      const res = await runAction("/api/action/run-native", {}, e.currentTarget, "Running");
      const out = $("wasmConsole");
      out.textContent = `[Native macOS run] ok=${res.ok} exit=${res.exit_code} why=${res.halt_why}\n${res.stdout || ""}\n`;
      if (res.msgbox_text) out.textContent += `[MessageBoxA] ${res.msgbox_title}: ${res.msgbox_text}\n`;
    });

    // New Project Modal
    const modal = $("newProjModal");
    $("btnOpenModal").addEventListener("click", () => modal.classList.add("is-open"));
    $("btnCloseModal").addEventListener("click", () => modal.classList.remove("is-open"));
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.remove("is-open");
    });

    $("newProjForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const raw = $("newExePaths").value || "";
      const paths = raw
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean);
      const projName = $("newProjName").value.trim();
      const autoStream = $("newAutoStream").checked;
      const withWasm = $("newWithWasm").checked;
      if (!paths.length) return;
      try {
        modal.classList.remove("is-open");
        $("newExePaths").value = "";
        $("newProjName").value = "";
        state.selectedAddr = null;

        if (paths.length > 1) {
          await api("/api/stream/batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ binaries: paths, with_wasm: withWasm }),
          });
          notify(`Queued ${paths.length} executables in live stream.`);
        } else {
          await api("/api/new-project", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ binary: paths[0], name: projName }),
          });
          await loadStatus();
          await loadBinaryMap();
          await loadStrings();
          if (autoStream) {
            await triggerStream("pipeline", { with_wasm: withWasm, cases: 4, limit: 40 });
          } else {
            notify("Project created and loaded.");
          }
        }
      } catch (err) {
        notify(err.message, true);
      }
    });
  }

  async function init() {
    applyTranslations();
    bindEvents();
    connectLiveStream();
    const initialTab = window.location.hash.replace("#", "");
    if (["overview", "lab", "wasm", "apis"].includes(initialTab)) {
      state.tab = initialTab;
    }
    try {
      await loadStatus();
      setTab(state.tab);
      await loadCompareDeck();
      await loadStrings();
    } catch (err) {
      notify(err.message, true);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
