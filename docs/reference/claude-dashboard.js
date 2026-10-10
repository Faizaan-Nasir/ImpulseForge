
/* Presentation layer. Reads the form, calls Calc (adapter), renders the view model. No physics here. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const { sig, fmtOhm, pct } = Calc;

  // ---------------------------------------------------------------- presets
  const inv = (vals, q) => vals.map((ohm) => ({ ohm, qty: q }));
  const WB_FRONT = [10, 20, 30, 50, 75, 100, 150, 200, 300, 500], WB_TAIL = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200];
  const PROFILES = {
    workbook: {
      gen: { nMax: 15, uMax: 200, cStage: 3, wStage: null, cBo: 0, includeCbo: false },
      inventories: { lightning: { front: inv(WB_FRONT, 4), tail: inv(WB_TAIL, 4) }, switching: { front: inv(WB_FRONT, 4), tail: inv(WB_TAIL, 4) } },
      selection: "combo", maxUnits: 4,
    },
    haefely: {
      gen: { nMax: 12, uMax: 200, cStage: 0.125, wStage: 2.5, cBo: 545, includeCbo: true },
      inventories: { lightning: { front: inv([30, 465, 3700], 1), tail: inv([520], 1) }, switching: { front: inv([30, 465, 3700], 1), tail: inv([22000], 1) } },
      selection: "single", maxUnits: 1,
    },
  };
  const GEN_FIELDS = ["nMax", "uMax", "cStage", "wStage", "cBo", "includeCbo"];
  const DEFAULT_V = { lightning: 1425, switching: 1050 };
  const clone = (x) => JSON.parse(JSON.stringify(x));

  const S = {
    form: {
      impulse: "lightning", vTest: 1425, cLoad: 850, cDiv: 500, cStray: 150, lStray: 18.5, eta: 0.82,
      ...PROFILES.workbook.gen, mode: "exact", tFront: 1.2, tTail: 50, tolProfile: "iec", tolCrest: 3, tolFront: 30, tolTail: 20,
      selection: "combo", maxUnits: 4, ranking: "balanced",
    },
    profile: "workbook",
    inventories: clone(PROFILES.workbook.inventories),
    invSide: "front",
    vm: null, stale: false, busy: false, showErrors: false, selected: 1,
    chart: { view: "full", domain: null },
  };
  const formWithInventory = () => ({ ...S.form, inventory: S.inventories[S.form.impulse] });

  // ---------------------------------------------------------------- form <-> state
  function fillForm() {
    document.querySelectorAll("[data-field]").forEach((el) => {
      const v = S.form[el.dataset.field];
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v === null || v === undefined || Number.isNaN(v) ? "" : v;
    });
    $("profile").value = S.profile;
    $("tolProfile").value = S.form.tolProfile;
    setPressed("impulseSeg", "impulse", S.form.impulse);
    setPressed("modeSeg", "mode", S.form.mode);
    setPressed("selSeg", "sel", S.form.selection);
    const li = S.form.impulse === "lightning";
    $("tFrontLbl").textContent = li ? "Target front time T1" : "Target time to peak Tp";
    $("tolFrontLbl").textContent = li ? "T1 ±" : "Tp ±";
    $("maxUnits").disabled = S.form.selection === "single";
    $("etaHint").textContent = S.form.mode === "calculator" ? "Used by Calculator mode to set the charging voltage." : "Not used in Exact mode, which computes η from the circuit.";
    renderInventory();
  }
  function setPressed(groupId, key, value) {
    document.querySelectorAll(`#${groupId} [data-${key}]`).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset[key] === value)));
  }
  function applyTolProfile() {
    if (S.form.tolProfile === "custom") return;
    const t = Calc.PROFILES[S.form.tolProfile][S.form.impulse];
    Object.assign(S.form, { tolCrest: t.crest, tolFront: t.front, tolTail: t.tail });
  }

  function onFieldInput(el) {
    const k = el.dataset.field;
    let v;
    if (el.type === "checkbox") v = el.checked;
    else if (el.tagName === "SELECT") v = el.value;
    else if (el.value.trim() === "") v = el.dataset.optional ? null : NaN;
    else v = Number(el.value);
    S.form[k] = v;
    if (GEN_FIELDS.includes(k) && S.profile !== "custom") { S.profile = "custom"; $("profile").value = "custom"; }
    if (el.dataset.tol && S.form.tolProfile !== "custom") { S.form.tolProfile = "custom"; $("tolProfile").value = "custom"; }
    changed();
  }

  function changed() {
    if (S.vm) S.stale = true;
    validateLive();
    renderBanners();
  }

  // ---------------------------------------------------------------- validation display
  function validateLive() {
    const { errors, list } = Calc.validate(formWithInventory());
    document.querySelectorAll(".field[data-for]").forEach((f) => {
      const k = f.dataset.for, msg = errors[k];
      f.classList.toggle("invalid", !!msg);
      let e = f.querySelector(".err");
      if (msg) {
        if (!e) { e = document.createElement("span"); e.className = "err"; e.id = `err-${k}`; f.appendChild(e); }
        e.textContent = msg;
        f.querySelector("input,select")?.setAttribute("aria-describedby", e.id);
        f.querySelector("input")?.setAttribute("aria-invalid", "true");
      } else if (e) {
        e.remove(); f.querySelector("input")?.removeAttribute("aria-invalid");
      }
    });
    // inventory errors
    document.querySelectorAll("#invPanel [data-err]").forEach((e) => {
      const msg = errors[e.dataset.err];
      e.textContent = msg || ""; e.hidden = !msg;
    });
    const invErr = errors[`inv-${S.invSide}`];
    $("invHint").textContent = invErr || `Inventory for ${S.form.impulse} tests. Quantities are available units per stage.`;
    $("invHint").style.color = invErr ? "var(--bad)" : "";
    const otherSide = S.invSide === "front" ? "tail" : "front";
    const otherBad = Object.keys(errors).some((k) => k.startsWith(`inv-${otherSide}`));
    $(`tab-${otherSide}`).style.color = otherBad ? "var(--bad)" : "";
    $(`tab-${S.invSide}`).style.color = "";
    $("calcBtn").disabled = S.busy;
    if (!S.busy) $("calcStatus").textContent = list.length ? `${list.length} input${list.length > 1 ? "s need" : " needs"} fixing before calculating.` : (S.stale ? "Inputs changed. Calculate to update the results." : $("calcStatus").textContent);
    return list;
  }

  // ---------------------------------------------------------------- inventory editor
  function renderInventory() {
    const rows = S.inventories[S.form.impulse][S.invSide];
    const panel = $("invPanel");
    panel.setAttribute("aria-labelledby", `tab-${S.invSide}`);
    let h = `<div class="inv-head"><span>Value (Ω)</span><span>Qty per stage</span><span class="sr-only">Remove</span></div>`;
    rows.forEach((r, i) => {
      const id = `inv-${S.invSide}-${i}`;
      h += `<div class="inv-row">
        <div class="field"><label class="sr-only" for="${id}-ohm">Resistance ${i + 1} in ohms</label>
          <div class="ctl"><input id="${id}-ohm" data-inv="${i}" data-k="ohm" type="number" inputmode="decimal" step="any" value="${Number.isFinite(r.ohm) ? r.ohm : ""}"><span class="unit">Ω</span></div>
          <span class="err" data-err="${id}-ohm" hidden></span></div>
        <div class="field"><label class="sr-only" for="${id}-qty">Quantity ${i + 1}</label>
          <div class="ctl"><input id="${id}-qty" data-inv="${i}" data-k="qty" type="number" inputmode="numeric" step="1" min="1" value="${Number.isFinite(r.qty) ? r.qty : ""}"></div>
          <span class="err" data-err="${id}-qty" hidden></span></div>
        <button type="button" class="iconbtn" data-remove="${i}" aria-label="Remove ${Number.isFinite(r.ohm) ? esc(fmtOhm(r.ohm)) : "this"} resistor">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
      </div>`;
    });
    panel.innerHTML = h;
    for (const side of ["front", "tail"]) {
      $(`tab-${side}`).setAttribute("aria-selected", String(side === S.invSide));
      $(`tab-${side}`).tabIndex = side === S.invSide ? 0 : -1;
      $(`cnt-${side}`).textContent = `(${S.inventories[S.form.impulse][side].length})`;
    }
  }
  $("invPanel").addEventListener("input", (e) => {
    const el = e.target; if (!el.dataset.inv) return;
    const row = S.inventories[S.form.impulse][S.invSide][Number(el.dataset.inv)];
    row[el.dataset.k] = el.value.trim() === "" ? NaN : Number(el.value);
    if (S.profile !== "custom") { S.profile = "custom"; $("profile").value = "custom"; }
    changed();
  });
  $("invPanel").addEventListener("click", (e) => {
    const b = e.target.closest("[data-remove]"); if (!b) return;
    S.inventories[S.form.impulse][S.invSide].splice(Number(b.dataset.remove), 1);
    if (S.profile !== "custom") { S.profile = "custom"; $("profile").value = "custom"; }
    renderInventory(); changed();
  });
  $("addRes").addEventListener("click", () => {
    const rows = S.inventories[S.form.impulse][S.invSide];
    rows.push({ ohm: NaN, qty: 1 });
    if (S.profile !== "custom") { S.profile = "custom"; $("profile").value = "custom"; }
    renderInventory(); changed();
    $(`inv-${S.invSide}-${rows.length - 1}-ohm`).focus();
  });
  document.querySelectorAll(".tabs [data-side]").forEach((b) => {
    b.addEventListener("click", () => { S.invSide = b.dataset.side; renderInventory(); validateLive(); });
    b.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      S.invSide = S.invSide === "front" ? "tail" : "front"; renderInventory(); validateLive(); $(`tab-${S.invSide}`).focus();
    });
  });

  // ---------------------------------------------------------------- control wiring
  $("rail").addEventListener("input", (e) => { if (e.target.dataset.field) onFieldInput(e.target); });
  $("rail").addEventListener("change", (e) => { if (e.target.dataset.field && (e.target.type === "checkbox" || e.target.tagName === "SELECT")) onFieldInput(e.target); });
  $("impulseSeg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-impulse]"); if (!b || b.dataset.impulse === S.form.impulse) return;
    const old = S.form.impulse, nu = b.dataset.impulse;
    S.form.impulse = nu;
    const d = Calc.DEFAULT_TARGETS;
    if (S.form.tFront === d[old].front) S.form.tFront = d[nu].front;
    if (S.form.tTail === d[old].tail) S.form.tTail = d[nu].tail;
    if (S.form.vTest === DEFAULT_V[old]) S.form.vTest = DEFAULT_V[nu];
    applyTolProfile();
    fillForm(); changed();
  });
  $("modeSeg").addEventListener("click", (e) => { const b = e.target.closest("[data-mode]"); if (!b) return; S.form.mode = b.dataset.mode; fillForm(); changed(); });
  $("selSeg").addEventListener("click", (e) => { const b = e.target.closest("[data-sel]"); if (!b) return; S.form.selection = b.dataset.sel; fillForm(); changed(); });
  $("profile").addEventListener("change", () => {
    const p = $("profile").value; S.profile = p;
    if (p !== "custom") {
      const pr = PROFILES[p];
      Object.assign(S.form, clone(pr.gen), { selection: pr.selection, maxUnits: pr.maxUnits });
      S.inventories = clone(pr.inventories);
    }
    fillForm(); changed();
  });
  $("tolProfile").addEventListener("change", () => { S.form.tolProfile = $("tolProfile").value; applyTolProfile(); fillForm(); changed(); });
  $("rail").addEventListener("submit", (e) => { e.preventDefault(); calculate(); });

  // ---------------------------------------------------------------- calculation
  const CALC_LABEL = $("calcBtn").innerHTML;
  function calculate() {
    const errs = validateLive();
    if (errs.length) { S.showErrors = true; renderBanners(); $("banners").scrollIntoView({ block: "nearest" }); return; }
    S.showErrors = false; S.busy = true;
    $("calcBtn").disabled = true; $("calcBtn").innerHTML = `<span class="spin" aria-hidden="true"></span>Calculating…`;
    $("calcStatus").textContent = "Calculating…";
    $("results").classList.add("busy"); $("results").setAttribute("aria-busy", "true");
    renderBanners();
    setTimeout(() => {
      let vm;
      try { vm = Calc.run(formWithInventory()); }
      catch (err) { vm = { status: "invalid", list: [`The calculation stopped: ${err.message}. Check for extreme input values.`] }; }
      S.busy = false;
      $("calcBtn").disabled = false; $("calcBtn").innerHTML = CALC_LABEL;
      $("results").classList.remove("busy"); $("results").removeAttribute("aria-busy");
      if (vm.status === "invalid") { S.showErrors = true; S.runErrors = vm.list; renderBanners(); return; }
      S.runErrors = null; S.vm = vm; S.stale = false; S.selected = 1; S.chart = { view: "full", domain: null };
      $("calcStatus").textContent = vm.cases.length
        ? `Calculated in ${(vm.ms / 1000).toFixed(1)} s · ${vm.cases.length} feasible setting${vm.cases.length > 1 ? "s" : ""}`
        : `Calculated in ${(vm.ms / 1000).toFixed(1)} s · no feasible setting`;
      setPressed("viewSeg", "view", "full");
      render();
    }, 40);
  }

  // ---------------------------------------------------------------- rendering helpers
  const icon = {
    ok: `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    bad: `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
    info: `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 7.2v4M8 4.8v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
    warn: `<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2l6.5 11.5h-13z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6.5v3.2M8 11.6v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  };
  const statusPill = (ok) => ok ? `<span class="pill good">${icon.ok}Within limits</span>` : `<span class="pill bad">${icon.bad}Outside limits</span>`;
  const kv = (v, d = 1) => `${(v / 1e3).toFixed(d)}`;
  const isLI = () => S.vm.form.impulse === "lightning";
  function us(t, which) {
    const x = t * 1e6, li = isLI();
    if (!Number.isFinite(x)) return "–";
    if (which === "front") return li ? x.toFixed(3) : x.toFixed(1);
    if (which === "tail") return li ? x.toFixed(2) : x.toFixed(0);
    return Math.abs(x) < 10 ? x.toFixed(3) : Math.abs(x) < 1000 ? x.toFixed(1) : x.toFixed(0);
  }
  const caseLabel = (k) => k === 1 ? "Best match" : k === 2 ? "Runner-up" : k === 3 ? "Third option" : "Alternative";
  const selCase = () => S.vm.cases.find((c) => c.rank === S.selected) || S.vm.cases[0];
  const metricName = (k) => k === "crest" ? "crest voltage" : k === "tail" ? "tail time T2" : (isLI() ? "front time T1" : "time to peak Tp");
  function worst(c) {
    let best = null;
    for (const [k, m] of Object.entries(c.metrics)) if (!best || m.norm > best.m.norm) best = { k, m };
    return best;
  }

  function render() {
    renderBanners();
    const vm = S.vm;
    if (!vm) return;
    const empty = vm.status === "no_feasible";
    for (const id of ["sec-settings", "sec-nets", "sec-wave", "sec-table", "sec-summary"]) $(id).hidden = empty;
    $("sec-empty").hidden = !empty;
    if (empty) {
      $("emptyList").innerHTML = (vm.explain.length ? vm.explain : ["No combination passed the hard limits."]).map((x) => `<li>${esc(x)}</li>`).join("");
      return;
    }
    renderCase(); renderNets(); renderChart(); renderMetrics(); renderTable(); renderSummary();
  }

  function renderBanners() {
    const b = [];
    if (S.showErrors) {
      const list = S.runErrors || Calc.validate(formWithInventory()).list;
      if (list.length) b.push(`<div class="banner error" role="alert"><div><strong>Fix these inputs to calculate.</strong><ul>${list.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`);
    }
    if (S.stale && S.vm && !S.busy) b.push(`<div class="banner stale"><span><strong>Results are out of date.</strong> Inputs changed after the last calculation.</span><button type="button" class="btn small" data-recalc>Recalculate</button></div>`);
    if (S.busy) b.push(`<div class="banner info"><span><strong>Calculating…</strong> Searching stage counts and resistor networks.</span></div>`);
    if (S.vm && S.vm.status === "ok" && !S.vm.cases[0].compliant) {
      b.push(`<div class="banner error"><div><strong>No candidate meets every limit.</strong> The best settings are shown, with the limits they miss.<ul>${S.vm.explain.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`);
    }
    $("banners").innerHTML = b.join("");
    $("banners").hidden = !b.length;
  }
  $("banners").addEventListener("click", (e) => { if (e.target.closest("[data-recalc]")) calculate(); });

  // ---------------------------------------------------------------- section 1
  function renderCase() {
    const vm = S.vm, c = selCase();
    const top = vm.cases.slice(0, 3).map((x) => x.rank);
    $("caseSel").innerHTML = top.map((r) => `<button type="button" data-case="${r}" aria-pressed="${r === c.rank}">Case #${r}</button>`).join("");
    $("caseTitle").textContent = `Selected case: #${c.rank} · ${caseLabel(c.rank)}`;
    $("casePill").innerHTML = statusPill(c.compliant);
    const w = worst(c);
    $("caseWhy").textContent = `Ranked ${c.rank} of ${vm.cases.length} feasible settings (${vm.ranking.name.toLowerCase()} priority). Its largest deviation is the ${metricName(w.k)}, at ${(w.m.norm * 100).toFixed(1)} % of the allowed band.`;
    const g = vm.form;
    const units = (net) => `${net.units} resistor${net.units > 1 ? "s" : ""} per stage`;
    $("settingsRow").innerHTML = `
      <div><span class="k">Generator stages</span><span class="big">${c.n}</span>
        <span class="support">of ${g.nMax} available · C1 = ${sig(c.c1 * 1e6, 4)} µF</span></div>
      <div><span class="k">Charging voltage</span><span class="big">${kv(c.u0, 2)}<small>kV/stage</small></span>
        <span class="support">${Math.round(c.u0 / (g.uMax * 1e3) * 100)} % of the ${g.uMax} kV limit · ${sig(c.energyStage / 1e3, 3)} kJ per stage</span></div>
      <div><span class="k">Front equivalent resistance</span><span class="big">${esc(sig(c.front.value, 5))}<small>Ω/stage</small></span>
        <span class="support">${esc(fmtOhm(c.front.total, 5))} across ${c.n} stages · ${units(c.front)}</span></div>
      <div><span class="k">Tail equivalent resistance</span><span class="big">${esc(sig(c.tail.value, 5))}<small>Ω/stage</small></span>
        <span class="support">${esc(fmtOhm(c.tail.total, 5))} across ${c.n} stages · ${units(c.tail)}</span></div>`;
  }
  $("caseSel").addEventListener("click", (e) => { const b = e.target.closest("[data-case]"); if (b) select(Number(b.dataset.case)); });
  function select(rank) {
    if (rank === S.selected) return;
    S.selected = rank; S.chart.domain = null;
    renderCase(); renderNets(); renderChart(); renderMetrics(); renderTable(); renderSummary();
  }

  // ---------------------------------------------------------------- section 2: networks
  function expression(net) {
    const t = net.topo, f = (x) => sig(x, 4);
    if (t.kind === "single") return `Req = ${f(t.parts[0])} Ω`;
    if (t.kind === "series") return `Req = ${t.parts.map(f).join(" + ")} = ${f(net.value)} Ω`;
    if (t.kind === "parallel") return `Req = 1 / (${t.parts.map((x) => `1/${f(x)}`).join(" + ")}) = ${f(net.value)} Ω`;
    const [b, c] = t.parallel;
    return `Req = ${f(t.series)} + (${f(b)} × ${f(c)}) / (${f(b)} + ${f(c)}) = ${f(net.value)} Ω`;
  }

  function schematic(net, title) {
    const t = net.topo;
    const blocks = t.kind === "series" ? t.parts.map((v) => ({ type: "r", v })) :
      t.kind === "parallel" ? [{ type: "p", vs: t.parts }] :
      t.kind === "mixed" ? [{ type: "r", v: t.series }, { type: "p", vs: t.parallel }] : [{ type: "r", v: t.parts[0] }];
    const SP = 70;                              // branch spacing
    const maxBr = Math.max(1, ...blocks.filter((b) => b.type === "p").map((b) => b.vs.length));
    const H = Math.max(150, 120 + (maxBr - 1) * SP + 40);
    const mid = H / 2 + 4;
    const widths = blocks.map((b) => (b.type === "r" ? 112 : 186));
    const total = widths.reduce((a, b) => a + b, 0);
    const W = Math.max(440, total + 120);
    const xA = 34, xB = W - 34;
    let x = (W - total) / 2;
    let id = 0;
    const ink = "#23272b", soft = "#7d8389";
    const resistor = (cx, y, v) => {
      const label = net.ids[id++];
      return `<line x1="${cx - 27}" x2="${cx + 27}" y1="${y}" y2="${y}" stroke="#fcfbf9" stroke-width="4"/>
        <rect x="${cx - 27}" y="${y - 10}" width="54" height="20" rx="2" fill="#ffffff" stroke="${ink}" stroke-width="1.6"/>
        <text x="${cx}" y="${y - 17}" text-anchor="middle" font-size="14" font-weight="600" fill="${ink}">${label}</text>
        <text x="${cx}" y="${y + 30}" text-anchor="middle" font-size="13.5" fill="#4a5056" font-family="IBM Plex Mono, monospace">${esc(fmtOhm(v))}</text>`;
    };
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}: ${esc(net.recipe)} ohms per stage">`;
    s += `<line x1="${xA}" x2="${x}" y1="${mid}" y2="${mid}" stroke="${ink}" stroke-width="1.6"/>`;
    blocks.forEach((b, i) => {
      const w = widths[i];
      if (b.type === "r") {
        s += `<line x1="${x}" x2="${x + w}" y1="${mid}" y2="${mid}" stroke="${ink}" stroke-width="1.6"/>` + resistor(x + w / 2, mid, b.v);
      } else {
        const k = b.vs.length, xl = x + 24, xr = x + w - 24;
        const ys = b.vs.map((_, j) => mid + (j - (k - 1) / 2) * SP);
        s += `<rect x="${xl - 14}" y="${ys[0] - 56}" width="${xr - xl + 28}" height="${ys[k - 1] - ys[0] + 98}" rx="8" fill="#f1f6f5" stroke="#9dc4bf" stroke-dasharray="4 3"/>`;
        s += `<text x="${xl - 4}" y="${ys[0] - 40}" font-size="11.5" fill="#2e7a74" font-weight="600" letter-spacing=".06em">PARALLEL</text>`;
        s += `<line x1="${x}" x2="${xl}" y1="${mid}" y2="${mid}" stroke="${ink}" stroke-width="1.6"/><line x1="${xr}" x2="${x + w}" y1="${mid}" y2="${mid}" stroke="${ink}" stroke-width="1.6"/>`;
        s += `<line x1="${xl}" x2="${xl}" y1="${ys[0]}" y2="${ys[k - 1]}" stroke="${ink}" stroke-width="1.6"/><line x1="${xr}" x2="${xr}" y1="${ys[0]}" y2="${ys[k - 1]}" stroke="${ink}" stroke-width="1.6"/>`;
        ys.forEach((y, j) => { s += `<line x1="${xl}" x2="${xr}" y1="${y}" y2="${y}" stroke="${ink}" stroke-width="1.6"/>` + resistor((xl + xr) / 2, y, b.vs[j]); });
        s += `<circle cx="${xl}" cy="${mid}" r="4" fill="${ink}"/><circle cx="${xr}" cy="${mid}" r="4" fill="${ink}"/>`;
      }
      x += w;
    });
    s += `<line x1="${x}" x2="${xB}" y1="${mid}" y2="${mid}" stroke="${ink}" stroke-width="1.6"/>`;
    s += `<circle cx="${xA}" cy="${mid}" r="5.5" fill="#ffffff" stroke="${ink}" stroke-width="1.6"/><circle cx="${xB}" cy="${mid}" r="5.5" fill="#ffffff" stroke="${ink}" stroke-width="1.6"/>`;
    s += `<text x="${xA}" y="${mid + 26}" text-anchor="middle" font-size="13" fill="${soft}">a</text><text x="${xB}" y="${mid + 26}" text-anchor="middle" font-size="13" fill="${soft}">b</text>`;
    s += `</svg>`;
    return s;
  }

  function renderNets() {
    const c = selCase();
    for (const side of ["front", "tail"]) {
      const net = c[side], title = side === "front" ? "Front resistor network" : "Tail resistor network";
      $(`${side}Sub`).textContent = `Case #${c.rank} · one stage of ${c.n}`;
      const devCls = Math.abs(net.dev) < 0.005 ? "var(--good)" : Math.abs(net.dev) < 0.03 ? "var(--ink)" : "var(--warn)";
      const chips = net.bom.map((b) => `<span class="chip ${b.ok ? "" : "bad"}">${b.ok ? icon.ok : icon.bad}${esc(fmtOhm(b.ohm))} · ${b.perStage} of ${b.stockPerStage} used</span>`).join("");
      $(`net-${side}`).innerHTML = `
        <div class="schem">${schematic(net, title)}</div>
        <p class="hint" style="margin-top:8px">Terminals a–b of one stage. The same network is fitted in each of the ${c.n} stages.</p>
        <dl class="facts">
          <dt>Equivalent Req</dt><dd><b class="num">${esc(fmtOhm(net.value, 5))}</b> per stage · <span class="num">${esc(fmtOhm(net.total, 5))}</span> total</dd>
          <dt>Expression</dt><dd class="num">${esc(expression(net))}</dd>
          <dt>Components</dt><dd>${net.units} per stage · ${net.units * c.n} in total (${net.ids.join(", ")})</dd>
          <dt>Ideal required</dt><dd><span class="num">${esc(fmtOhm(net.ideal, 5))}</span> per stage · deviation <b class="num" style="color:${devCls}">${esc(pct(net.dev, 2))}</b></dd>
          <dt>Inventory</dt><dd><div class="chips">${chips}</div></dd>
        </dl>`;
    }
  }

  // ---------------------------------------------------------------- section 3: waveform
  function niceTicks(lo, hi, count = 6) {
    const span = hi - lo, raw = span / count, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12));
    return out;
  }
  function defaultDomain(view) {
    const vm = S.vm, c = selCase(), m = c.markers;
    if (view === "front") return [0, Math.max(4 * vm.target.front, 1.4 * (m.t90 || 0), 1.15 * (m.tPeak || 0))];
    return [0, Math.max(2.5 * vm.target.tail, 1.3 * (m.t50 || 0))];
  }

  function renderChart() {
    const vm = S.vm, c = selCase(), cv = Calc.curves(vm, c), m = cv.markers;
    const host = $("plot");
    const W = Math.max(300, Math.round(host.clientWidth || 700));
    const H = window.innerWidth < 640 ? 300 : 330;
    const ml = 62, mr = 22, mt = 58, mb = 48, pw = W - ml - mr, ph = H - mt - mb;
    const [t0, t1] = S.chart.domain || defaultDomain(S.chart.view);
    const vMax = 1.15 * Math.max(vm.setup.vTest, m.vPeak);
    const X = (t) => ml + (t - t0) / (t1 - t0) * pw, Y = (v) => mt + ph - (v / vMax) * ph;
    const N = Math.min(1200, Math.round(pw * 1.5));
    const pathOf = (fn) => {
      let d = "";
      for (let i = 0; i < N; i++) { const t = t0 + (t1 - t0) * i / (N - 1); d += `${i ? "L" : "M"}${X(t).toFixed(1)} ${Y(Math.max(fn(t), 0)).toFixed(1)}`; }
      return d;
    };
    const xt = niceTicks(t0 * 1e6, t1 * 1e6, W < 500 ? 4 : 7), yt = niceTicks(0, vMax / 1e3, 5);
    const inX = (t) => t >= t0 && t <= t1;
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Target and predicted impulse waveforms, voltage in kilovolts against time in microseconds">`;
    s += `<defs><clipPath id="clipPlot"><rect x="${ml}" y="${mt - 2}" width="${pw}" height="${ph + 4}"/></clipPath></defs>`;
    // recorder graticule: minor divisions (5 per major) under the major grid
    const minor = (ticks) => { const st = ticks.length > 1 ? ticks[1] - ticks[0] : 0, out = []; if (!st) return out;
      for (let v = ticks[0] - st; v <= ticks[ticks.length - 1] + st; v += st / 5) out.push(+v.toPrecision(12)); return out; };
    for (const y of minor(yt)) if (y * 1e3 >= 0 && y * 1e3 <= vMax) s += `<line x1="${ml}" x2="${ml + pw}" y1="${Y(y * 1e3)}" y2="${Y(y * 1e3)}" stroke="var(--grid-minor)"/>`;
    for (const x of minor(xt)) if (x / 1e6 >= t0 && x / 1e6 <= t1) s += `<line x1="${X(x / 1e6)}" x2="${X(x / 1e6)}" y1="${mt}" y2="${mt + ph}" stroke="var(--grid-minor)"/>`;
    for (const y of yt) s += `<line x1="${ml}" x2="${ml + pw}" y1="${Y(y * 1e3)}" y2="${Y(y * 1e3)}" stroke="var(--grid)"/><text x="${ml - 10}" y="${Y(y * 1e3) + 4}" text-anchor="end" font-size="12" fill="var(--ink-3)" font-family="IBM Plex Mono, monospace">${y}</text>`;
    for (const x of xt) s += `<line x1="${X(x / 1e6)}" x2="${X(x / 1e6)}" y1="${mt}" y2="${mt + ph}" stroke="var(--grid)"/><text x="${X(x / 1e6)}" y="${mt + ph + 18}" text-anchor="middle" font-size="12" fill="var(--ink-3)" font-family="IBM Plex Mono, monospace">${x}</text>`;
    s += `<rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="none" stroke="var(--line-strong)"/>`;
    s += `<text x="${ml + pw / 2}" y="${H - 8}" text-anchor="middle" font-size="13" font-weight="600" letter-spacing=".06em" fill="var(--ink-2)" font-family="Barlow Semi Condensed, Arial Narrow, sans-serif">TIME (µs)</text>`;
    s += `<text transform="translate(16 ${mt + ph / 2}) rotate(-90)" text-anchor="middle" font-size="13" font-weight="600" letter-spacing=".06em" fill="var(--ink-2)" font-family="Barlow Semi Condensed, Arial Narrow, sans-serif">VOLTAGE (kV)</text>`;
    // threshold levels of the predicted peak
    const levels = [[0.9, "90 %"], [0.5, "50 %"], [0.3, "30 %"]];
    for (const [f, lab] of levels) {
      const y = Y(f * m.vPeak);
      s += `<line x1="${ml}" x2="${ml + pw}" y1="${y}" y2="${y}" stroke="#b9bfc6" stroke-dasharray="2 4"/><text x="${ml + pw - 4}" y="${y - 5}" text-anchor="end" font-size="11" fill="var(--ink-3)">${lab}</text>`;
    }
    s += `<g clip-path="url(#clipPlot)">`;
    s += `<path d="${pathOf(cv.predicted)}" fill="none" stroke="var(--pred)" stroke-width="2.5" stroke-linejoin="round"/>`;
    s += `<path d="${pathOf(cv.target)}" fill="none" stroke="var(--target)" stroke-width="2" stroke-dasharray="7 6" stroke-linecap="round"/>`;
    // vertical timing markers
    const verts = [];
    if (m.t30 !== undefined) verts.push({ t: m.t30, lab: "t30" }, { t: m.t90, lab: "t90" });
    if (isLI() && m.virtualOrigin !== undefined) verts.push({ t: m.virtualOrigin, lab: "O1" });
    if (m.t50 !== undefined) verts.push({ t: m.t50, lab: "t50" });
    verts.push({ t: m.tPeak, lab: isLI() ? "peak" : "peak (Tp ref.)" });
    for (const v of verts) if (inX(v.t)) s += `<line x1="${X(v.t)}" x2="${X(v.t)}" y1="${mt}" y2="${mt + ph}" stroke="#9aa3ad" stroke-dasharray="3 3"/>`;
    s += `</g>`;
    // crest marker
    if (inX(m.tPeak)) {
      const px = X(m.tPeak), py = Y(m.vPeak);
      const right = px + 150 < ml + pw;
      s += `<circle cx="${px}" cy="${py}" r="5" fill="var(--pred)" stroke="#fff" stroke-width="2"/>`;
      s += `<text x="${right ? px + 10 : px - 10}" y="${py - 9}" text-anchor="${right ? "start" : "end"}" font-size="12" font-weight="600" fill="var(--ink)">Crest ${kv(m.vPeak, 1)} kV</text>`;
    }
    // label band above the plot, rows assigned so labels never overlap
    const rows = [[], [], []];
    const placed = [];
    for (const v of verts.filter((v) => inX(v.t)).sort((a, b) => a.t - b.t)) {
      const w = v.lab.length * 6.6 + 10, cx = Math.min(Math.max(X(v.t), ml + w / 2), ml + pw - w / 2);
      let r = rows.findIndex((row) => row.every(([a, b]) => cx - w / 2 > b + 4 || cx + w / 2 < a - 4));
      if (r < 0) continue;
      rows[r].push([cx - w / 2, cx + w / 2]);
      placed.push({ ...v, cx, r });
    }
    for (const p of placed) s += `<text x="${p.cx}" y="${mt - 38 + p.r * 14}" text-anchor="middle" font-size="11.5" fill="var(--ink-2)" font-family="IBM Plex Mono, monospace">${p.lab}</text>`;
    // hover + zoom layers
    s += `<g class="hov" visibility="hidden"><line class="xh" y1="${mt}" y2="${mt + ph}" stroke="var(--ink-3)"/><circle class="dp" r="4.5" fill="var(--pred)" stroke="#fff" stroke-width="2"/><circle class="dt" r="4" fill="var(--target)" stroke="#fff" stroke-width="2"/></g>`;
    s += `<rect class="selbox" y="${mt}" height="${ph}" fill="rgba(46,122,116,.12)" stroke="var(--teal)" visibility="hidden"/>`;
    s += `<rect class="hit" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent"/>`;
    s += `</svg>`;
    host.innerHTML = s + `<div class="tip" hidden></div>`;

    const svg = host.querySelector("svg"), hov = svg.querySelector(".hov"), tip = host.querySelector(".tip"), box = svg.querySelector(".selbox");
    const toT = (clientX) => { const r = svg.getBoundingClientRect(); const sx = (clientX - r.left) / r.width * W; return t0 + Math.max(0, Math.min(1, (sx - ml) / pw)) * (t1 - t0); };
    let drag = null;
    svg.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; drag = { t: toT(e.clientX) }; svg.setPointerCapture(e.pointerId); });
    svg.addEventListener("pointermove", (e) => {
      const t = toT(e.clientX), vp = cv.predicted(t), vt = cv.target(t);
      hov.setAttribute("visibility", "visible");
      hov.querySelector(".xh").setAttribute("x1", X(t)); hov.querySelector(".xh").setAttribute("x2", X(t));
      const dp = hov.querySelector(".dp"), dt = hov.querySelector(".dt");
      dp.setAttribute("cx", X(t)); dp.setAttribute("cy", Y(Math.max(vp, 0)));
      dt.setAttribute("cx", X(t)); dt.setAttribute("cy", Y(Math.max(vt, 0)));
      tip.innerHTML = `<div class="t">t = ${esc(us(t))} µs</div>
        <div class="r"><svg width="18" height="4" aria-hidden="true"><line x1="0" x2="18" y1="2" y2="2" stroke="#a9c1e4" stroke-width="2.5"/></svg><b>${kv(vp, 1)} kV</b><span>Predicted</span></div>
        <div class="r"><svg width="18" height="4" aria-hidden="true"><line x1="0" x2="18" y1="2" y2="2" stroke="#f0b27a" stroke-width="2" stroke-dasharray="5 3"/></svg><b>${kv(vt, 1)} kV</b><span>Target</span></div>
        <div class="r"><span style="width:18px"></span><b>${(vp - vt) >= 0 ? "+" : "−"}${kv(Math.abs(vp - vt), 1)} kV</b><span>Difference</span></div>`;
      tip.hidden = false;
      const hr = host.getBoundingClientRect();
      let left = e.clientX - hr.left + 16;
      if (left + tip.offsetWidth > hr.width) left = e.clientX - hr.left - tip.offsetWidth - 16;
      tip.style.left = `${Math.max(0, left)}px`; tip.style.top = `${Math.max(0, e.clientY - hr.top - tip.offsetHeight - 12)}px`;
      if (drag) {
        const a = Math.min(X(drag.t), X(t)), b = Math.max(X(drag.t), X(t));
        box.setAttribute("x", a); box.setAttribute("width", b - a); box.setAttribute("visibility", "visible");
      }
    });
    svg.addEventListener("pointerup", (e) => {
      if (!drag) return;
      const t = toT(e.clientX), a = Math.min(drag.t, t), b = Math.max(drag.t, t);
      drag = null; box.setAttribute("visibility", "hidden");
      if ((b - a) / (t1 - t0) > 0.02) { S.chart.domain = [a, b]; renderChart(); }
    });
    svg.addEventListener("pointerleave", () => { if (!drag) { hov.setAttribute("visibility", "hidden"); tip.hidden = true; } });

    $("legend").innerHTML = `<span><span class="ln target"></span>Target · ${isLI() ? "1.2/50" : "250/2500"} µs reference${Math.abs(vm.target.front * 1e6 / (isLI() ? 1.2 : 250) - 1) > 1e-9 || Math.abs(vm.target.tail * 1e6 / (isLI() ? 50 : 2500) - 1) > 1e-9 ? " (custom times)" : ""}, ${kv(vm.setup.vTest, 0)} kV</span><span><span class="ln"></span>Predicted · Case #${c.rank}</span>`;
    $("waveSub").textContent = `Case #${c.rank} · ${S.chart.domain ? "zoomed" : S.chart.view === "front" ? "front detail" : "full impulse"}`;
    const mk = [`t30 ${us(m.t30)} µs`, `t90 ${us(m.t90)} µs`];
    if (isLI()) mk.push(`O1 ${us(m.virtualOrigin)} µs`);
    mk.push(`t50 ${us(m.t50)} µs`, `peak ${us(m.tPeak)} µs`);
    $("plotNote").innerHTML = `Markers on the predicted curve: ${esc(mk.join(" · "))}. Drag across the plot to zoom.` +
      (vm.form.mode === "calculator" ? `<br><strong style="color:var(--warn)">Calculator mode:</strong> the curve and markers are the exact circuit response. The metric values use closed-form formulas and can differ from the curve.` : "");
  }
  $("viewSeg").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (!b || !S.vm) return; S.chart = { view: b.dataset.view, domain: null }; setPressed("viewSeg", "view", b.dataset.view); renderChart(); });
  const zoomBy = (f) => {
    if (!S.vm) return;
    const [a, b] = S.chart.domain || defaultDomain(S.chart.view), mid = (a + b) / 2, half = (b - a) / 2 * f;
    S.chart.domain = [Math.max(0, mid - half), Math.max(0, mid - half) + 2 * half]; renderChart();
  };
  $("zoomIn").addEventListener("click", () => zoomBy(0.5));
  $("zoomOut").addEventListener("click", () => zoomBy(2));
  $("zoomReset").addEventListener("click", () => { if (!S.vm) return; S.chart.domain = null; renderChart(); });

  // ---------------------------------------------------------------- section 3: metrics
  function renderMetrics() {
    const vm = S.vm, c = selCase(), li = isLI();
    $("perfPill").innerHTML = statusPill(c.compliant);
    const row = (name, val, detail, chip) => `<div class="metric"><div class="row"><span class="name">${name}</span>${chip}</div><div class="val">${val}</div><div class="detail">${detail}</div></div>`;
    const comp = (key, name, valTxt, tgtTxt) => {
      const mm = c.metrics[key];
      const chip = mm.ok ? `<span class="status-chip good">${icon.ok}Within</span>` : `<span class="status-chip bad">${icon.bad}Outside</span>`;
      return row(name, valTxt, `Target <b>${tgtTxt}</b> · deviation <b>${esc(pct(mm.dev, 2))}</b> · allowed <b>±${(mm.tol * 100).toFixed(0)} %</b>`, chip);
    };
    const info = `<span class="status-chip info">${icon.info}Info</span>`;
    let h = comp("crest", "Predicted crest voltage", `${kv(c.metrics.crest.pred, 1)} kV`, `${kv(vm.setup.vTest, 1)} kV`);
    h += comp("front", li ? "Front time T1" : "Time to peak Tp", `${us(c.metrics.front.pred, "front")} µs`, `${us(vm.target.front, "front")} µs`);
    if (li) h += row("Peak time (time of maximum)", `${us(c.tPeak)} µs`, "Informational; not a compliance limit for lightning impulses.", info);
    else h += row("Time of maximum", `${us(c.tPeak)} µs`, "True time of the voltage maximum. IEC Tp above is K × (t90 − t30).", info);
    h += comp("tail", "Tail time T2", `${us(c.metrics.tail.pred, "tail")} µs`, `${us(vm.target.tail, "tail")} µs`);
    h += row(`Predicted efficiency <span class="nc">η</span>`, `${c.etaExact.toFixed(3)}`, vm.form.mode === "calculator" ? `Circuit value. Calculator mode assumed η = ${vm.form.eta} to set the charging voltage.` : "Crest voltage ÷ total charging voltage (n × U0).", info);
    h += row("Waveform fit error", `${(c.fit * 100).toFixed(2)} %`, `RMS difference from the target waveform over 0–${us(2.5 * vm.target.tail)} µs, as a share of crest voltage.`, info);
    if (li) h += row("Overshoot", `${(c.overshoot * 100).toFixed(1)} %`, "Limit 10 %. Measured against the same circuit without inductance.", c.overshoot <= 0.1 ? `<span class="status-chip good">${icon.ok}Within</span>` : `<span class="status-chip bad">${icon.bad}Outside</span>`);
    $("metrics").innerHTML = h;
    $("defs").innerHTML = (li
      ? `<span>T1 = 1.67 × (t90 − t30). T2 is measured from the virtual origin O1 to the 50 % point on the tail (IEC 60060-1).</span>`
      : `<span>Tp = K × (t90 − t30) with the IEC 60060-1 K factor. T2 is measured from the true origin to the 50 % point on the tail.</span>`) +
      `<span>Tolerance profile: ${esc(vm.profileName)} (crest ±${vm.form.tolCrest} %, ${li ? "T1" : "Tp"} ±${vm.form.tolFront} %, T2 ±${vm.form.tolTail} %). Mode: ${vm.form.mode === "exact" ? "Exact" : "Calculator"}.</span>`;
  }

  // ---------------------------------------------------------------- section 4: comparison (top 3)
  function renderTable() {
    const vm = S.vm, li = isLI(), fl = li ? "T1" : "Tp";
    const top = vm.cases.slice(0, 3);
    const cls = (c) => (c.rank === S.selected ? "sel" : "");
    const head = `<thead><tr><th class="l rowhead"><span class="sr-only">Metric</span></th>${top.map((c) =>
      `<th class="${cls(c)}" scope="col"><button type="button" class="colbtn" data-rank="${c.rank}" aria-pressed="${c.rank === S.selected}">
        <span class="cname">Case #${c.rank}</span><span class="ctag">${caseLabel(c.rank)}</span></button></th>`).join("")}</tr></thead>`;
    const devTxt = (m) => `<span class="dev ${m.ok ? "" : "out"}">${esc(pct(m.dev))}</span>`;
    const group = (title) => `<tr class="grp"><th class="l" colspan="${top.length + 1}" scope="colgroup">${title}</th></tr>`;
    const row = (label, fn) => `<tr><th class="l rowhead" scope="row">${label}</th>${top.map((c) => `<td class="${cls(c)}" data-rank="${c.rank}">${fn(c)}</td>`).join("")}</tr>`;
    const body = [
      group("Settings"),
      row("Generator stages", (c) => `${c.n}`),
      row("Charging voltage", (c) => `${kv(c.u0, 2)} <span class="u">kV/stage</span>`),
      row("Front Req", (c) => `${esc(sig(c.front.value, 5))} <span class="u">Ω/stage</span>`),
      row("Tail Req", (c) => `${esc(sig(c.tail.value, 5))} <span class="u">Ω/stage</span>`),
      row("Resistors per stage", (c) => `${c.front.units} + ${c.tail.units}`),
      group("Predicted waveform"),
      row(li ? "Front time T1" : "Time to peak Tp", (c) => `${us(c.metrics.front.pred, "front")} <span class="u">µs</span>${devTxt(c.metrics.front)}`),
      row("Tail time T2", (c) => `${us(c.metrics.tail.pred, "tail")} <span class="u">µs</span>${devTxt(c.metrics.tail)}`),
      row("Crest voltage", (c) => `${kv(c.metrics.crest.pred, 1)} <span class="u">kV</span>${devTxt(c.metrics.crest)}`),
      group("Result"),
      row("Status", (c) => c.compliant ? `<span class="status-chip good">${icon.ok}Within limits</span>` : `<span class="status-chip bad">${icon.bad}Outside limits</span>`),
      row("Score", (c) => `${c.score.toFixed(4)}`),
    ].join("");
    $("candTable").innerHTML = `<caption class="sr-only">Top ${top.length} candidate settings, one column per case</caption>${head}<tbody>${body}</tbody>`;
    $("tableSub").textContent = `Top ${top.length} of ${vm.cases.length} feasible settings`;
    $("rankNote").textContent = `Ranked by ${vm.ranking.text}. Score = largest |deviation| ÷ allowed band, plus small tie-breakers. Deviations are against the targets for ${fl}, T2 and crest.`;
  }
  $("candTable").addEventListener("click", (e) => { const el = e.target.closest("[data-rank]"); if (el) select(Number(el.dataset.rank)); });

  // ---------------------------------------------------------------- section 5: decision summary (brief)
  const COMP = [
    { k: "worst", name: "Accuracy" },
    { k: "units", name: "Resistor count" },
    { k: "stages", name: "Stage count" },
    { k: "voltage", name: "Voltage use" },
  ];
  const f4 = (x) => x.toFixed(4);
  const sgn4 = (x) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x).toFixed(4)}`;

  function whyLower(o, base) {
    const parts = COMP.map((p) => ({ name: p.name.toLowerCase(), d: o.breakdown[p.k] - base.breakdown[p.k] })).filter((x) => Math.abs(x.d) >= 5e-5);
    const worse = parts.filter((x) => x.d > 0).sort((a, b) => b.d - a.d), better = parts.filter((x) => x.d < 0);
    const w = worse.map((x) => `${x.name} <span class="num up">${sgn4(x.d)}</span>`).join(", ");
    const b = better.map((x) => `${x.name} <span class="num down">${sgn4(x.d)}</span>`).join(", ");
    return `<li><b>Case #${o.rank}</b> <span class="num">${sgn4(o.score - base.score)}</span> — worse on ${w || "nothing"}${b ? `; better on ${b}` : ""}.</li>`;
  }

  function renderSummary() {
    const vm = S.vm, c = selCase(), g = vm.form, M = c.metrics, wts = vm.ranking.w;
    const top = vm.cases.slice(0, 3), best = top[0];
    $("summarySub").textContent = `Recommended: Case #${best.rank}`;
    const maxBand = Math.max(...top.map((x) => x.breakdown.worst)) * 100;
    const allIn = top.every((x) => x.compliant);

    let lead = `<p class="lead"><b>Case #${best.rank}</b> is recommended: lowest score (${f4(best.score)}).`;
    if (top.length > 1) lead += allIn && maxBand < 10 ? ` All top ${top.length} are within ${maxBand.toFixed(2)} % of their tolerance bands, so the differences are marginal.`
      : allIn ? ` Accuracy decides the ranking.` : ` No case meets every limit; this one comes closest.`;
    lead += `</p>`;

    const cell = (x, v, strong) => `<td class="${x.rank === c.rank ? "sel" : ""}">${strong ? `<b>${f4(v)}</b>` : f4(v)}</td>`;
    const table = `
      <div class="tablewrap"><table class="score-tbl">
        <thead><tr><th class="l">Score part</th>${top.map((x) => `<th class="${x.rank === c.rank ? "sel" : ""}">#${x.rank}</th>`).join("")}</tr></thead>
        <tbody>${COMP.map((p) => `<tr><th class="l" scope="row">${p.name}</th>${top.map((x) => cell(x, x.breakdown[p.k])).join("")}</tr>`).join("")}
        <tr class="total"><th class="l" scope="row">Total</th>${top.map((x) => cell(x, x.score, true)).join("")}</tr></tbody>
      </table></div>
      <p class="formula-line">Score = largest |deviation| ÷ band + ${wts.units}·resistors + ${wts.stages}·stages + ${wts.voltage}·U0/U<sub>max</sub>. Lower is better.</p>`;

    const why = top.length > 1 ? `<ul class="why">${top.slice(1).map((o) => whyLower(o, best)).join("")}</ul>` : "";

    // only what needs attention
    const attn = [];
    const failing = Object.entries(M).filter(([, m]) => !m.ok);
    if (failing.length) attn.push(`<li class="bad">${esc(failing.map(([k, m]) => `${metricName(k)} ${pct(m.dev)} (allowed ±${(m.tol * 100).toFixed(0)} %)`).join("; "))}</li>`);
    if (c.u0 > g.uMax * 1e3) attn.push(`<li class="bad">Charging voltage above the limit.</li>`);
    const short = [...c.front.bom, ...c.tail.bom].filter((b) => !b.ok);
    if (short.length) attn.push(`<li class="bad">Short of ${esc(short.map((b) => fmtOhm(b.ohm)).join(", "))} resistors.</li>`);
    if (g.selection === "combo" && Math.max(c.front.units, c.tail.units) > 1) attn.push(`<li class="warn">Uses up to ${Math.max(c.front.units, c.tail.units)} resistors per stage network; confirm combining is allowed.</li>`);
    if (g.mode === "calculator") attn.push(`<li class="warn">Calculator mode: timing values are approximate.</li>`);

    $("summary").innerHTML = `${lead}
      <div class="rep-row">
        <section class="rep-sec"><h3>Score breakdown</h3>${table}</section>
        <section class="rep-sec"><h3>Why the others rank lower</h3>${why || `<p class="muted">Only one feasible setting.</p>`}
          ${attn.length ? `<h3 style="margin-top:6px">Needs attention</h3><ul class="attn">${attn.join("")}</ul>` : ""}</section>
      </div>`;
  }

  // ---------------------------------------------------------------- export
  function reportText() {
    const vm = S.vm;
    if (!vm) return "No results yet. Calculate recommendations first.";
    const g = vm.form, li = g.impulse === "lightning";
    const L = [];
    L.push(`# Impulse Physics Engine report`, ``, `Model output from the deterministic physics engine. Not validated against laboratory measurements.`, ``);
    L.push(`## Inputs`, `- Impulse: ${li ? "Lightning" : "Switching"}, target ${g.tFront}/${g.tTail} µs, crest ${g.vTest} kV`);
    L.push(`- Test object ${g.cLoad} pF, divider ${g.cDiv} pF, stray ${g.cStray} pF, loop inductance ${g.lStray} µH${g.mode === "calculator" ? `, η ${g.eta}` : ""}`);
    L.push(`- Generator: ${g.nMax} stages, ${g.cStage} µF per stage, max ${g.uMax} kV per stage${g.wStage !== null ? `, ${g.wStage} kJ per stage` : ""}${g.includeCbo ? `, C_bo ${g.cBo} pF` : ""}`);
    L.push(`- Mode: ${g.mode}; tolerances (${vm.profileName}): crest ±${g.tolCrest} %, ${li ? "T1" : "Tp"} ±${g.tolFront} %, T2 ±${g.tolTail} %`);
    L.push(`- Resistor selection: ${g.selection === "single" ? "single resistor" : `series–parallel, up to ${g.maxUnits} per stage`}; ranking: ${vm.ranking.name}`, ``);
    if (!vm.cases.length) { L.push(`## Result`, `No feasible setting.`, ...vm.explain.map((x) => `- ${x}`)); return L.join("\n"); }
    const c = selCase(), M = c.metrics;
    L.push(`## Selected case #${c.rank} (${c.compliant ? "within limits" : "outside limits"})`);
    L.push(`- Stages: ${c.n}`, `- Charging voltage: ${kv(c.u0, 2)} kV per stage (total ${kv(c.v0, 1)} kV)`);
    L.push(`- Front: ${c.front.recipe} Ω = ${sig(c.front.value, 5)} Ω per stage (ideal ${sig(c.front.ideal, 5)} Ω, ${pct(c.front.dev, 2)})`);
    L.push(`- Tail: ${c.tail.recipe} Ω = ${sig(c.tail.value, 5)} Ω per stage (ideal ${sig(c.tail.ideal, 5)} Ω, ${pct(c.tail.dev, 2)})`);
    L.push(`- Crest ${kv(M.crest.pred, 1)} kV (${pct(M.crest.dev, 2)}), ${li ? "T1" : "Tp"} ${us(M.front.pred, "front")} µs (${pct(M.front.dev, 2)}), T2 ${us(M.tail.pred, "tail")} µs (${pct(M.tail.dev, 2)})`);
    L.push(`- Efficiency ${c.etaExact.toFixed(3)}, fit error ${(c.fit * 100).toFixed(2)} % RMS`, ``);
    L.push(`## Top candidates`, `| Rank | Stages | U0 kV | Front Ω | Tail Ω | ${li ? "T1" : "Tp"} µs | T2 µs | Status |`, `|---|---|---|---|---|---|---|---|`);
    for (const x of vm.cases.slice(0, 5)) L.push(`| ${x.rank} | ${x.n} | ${kv(x.u0, 2)} | ${sig(x.front.value, 5)} | ${sig(x.tail.value, 5)} | ${us(x.metrics.front.pred, "front")} | ${us(x.metrics.tail.pred, "tail")} | ${x.compliant ? "within" : "outside"} |`);
    return L.join("\n");
  }
  $("exportBtn").addEventListener("click", () => {
    $("reportText").value = reportText();
    $("copyMsg").textContent = "Copy the report and paste it into your notes or a document.";
    const d = $("reportDlg");
    if (typeof d.showModal === "function") d.showModal(); else d.setAttribute("open", "");
  });
  $("dlgClose").addEventListener("click", () => { const d = $("reportDlg"); if (d.close) d.close(); else d.removeAttribute("open"); });
  $("copyBtn").addEventListener("click", () => {
    const ta = $("reportText");
    const fallback = () => { ta.focus(); ta.select(); $("copyMsg").textContent = "Text selected. Press Ctrl+C (or ⌘C) to copy."; };
    try { navigator.clipboard.writeText(ta.value).then(() => { $("copyMsg").textContent = "Copied to the clipboard."; }, fallback); }
    catch { fallback(); }
  });

  // ---------------------------------------------------------------- layout helpers
  function updateSticky() {
    const rail = $("rail");
    rail.classList.toggle("sticky", window.innerWidth > 1100 && rail.offsetHeight + 32 <= window.innerHeight);
  }
  let rz = null;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { updateSticky(); if (S.vm && S.vm.cases.length) renderChart(); }, 150); });

  // ---------------------------------------------------------------- start
  fillForm();
  validateLive();
  updateSticky();
  calculate();
})();

