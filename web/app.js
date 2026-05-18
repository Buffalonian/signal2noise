/**
 * SignalPath Intel — UI shell (vanilla JS)
 * States: idle | running | completed | error
 */

const PHASES = [
  { id: "resolve_cik", label: "Resolving ticker", step: 1 },
  { id: "fetch_sec_data", label: "Fetching SEC data", step: 2 },
  { id: "extract_evidence", label: "Extracting evidence", step: 3 },
  { id: "generate_report", label: "Generating report", step: 4 },
  { id: "evaluate_report", label: "Running evidence audit", step: 5 },
  { id: "finalize_response", label: "Complete", step: 6 },
];

const RING_C = 97.4;
const THEME_KEY = "spi-theme";
const THEME_COLORS = { dark: "#0b0f17", light: "#f4f5f7" };

const els = {
  form: document.getElementById("report-form"),
  submitBtn: document.getElementById("submit-btn"),
  error: document.getElementById("error"),
  headerStatus: document.getElementById("header-status"),
  headerElapsed: document.getElementById("header-elapsed"),
  phaseText: document.getElementById("phase-text"),
  phaseDetail: document.getElementById("phase-detail"),
  phaseSteps: document.getElementById("phase-steps"),
  progressFill: document.getElementById("progress-ring-fill"),
  progressPct: document.getElementById("progress-pct"),
  activityFeed: document.getElementById("activity-feed"),
  artifactsBlock: document.getElementById("run-artifacts"),
  artifactsList: document.getElementById("artifacts-list"),
  reportEmpty: document.getElementById("report-empty"),
  reportContent: document.getElementById("report-content"),
  popoutBtn: document.getElementById("popout-btn"),
  sessionList: document.getElementById("session-list"),
  refreshSessions: document.getElementById("refresh-sessions"),
  mobileSuccessBar: document.getElementById("mobile-success-bar"),
  mobileSuccessText: document.getElementById("mobile-success-text"),
  mobileSuccessMeta: document.getElementById("mobile-success-meta"),
  shareFab: document.getElementById("share-fab"),
  logExpand: document.getElementById("log-expand"),
  logModal: document.getElementById("log-modal"),
  logModalBody: document.getElementById("log-modal-body"),
  logModalClose: document.getElementById("log-modal-close"),
  advancedToggle: document.getElementById("advanced-toggle"),
  advancedSheet: document.getElementById("advanced-sheet"),
  sheetBackdrop: document.getElementById("sheet-backdrop"),
  sheetClose: document.getElementById("sheet-close"),
  themeToggle: document.getElementById("theme-toggle"),
  companyLookup: document.getElementById("company-lookup"),
  ticker: document.getElementById("ticker"),
  companyName: document.getElementById("company_name"),
  companySuggestions: document.getElementById("company-suggestions"),
  comboboxLookup: document.getElementById("combobox-lookup"),
  comboboxTicker: document.getElementById("combobox-ticker"),
  comboboxCompany: document.getElementById("combobox-company"),
  peerSuggestions: document.getElementById("peer-suggestions"),
  peerClusterLabel: document.getElementById("peer-cluster-label"),
  peerChips: document.getElementById("peer-chips"),
  peerSuggestionsEmpty: document.getElementById("peer-suggestions-empty"),
  peerUseAll: document.getElementById("peer-use-all"),
  competitors: document.getElementById("competitors"),
  stockChart: document.getElementById("stock-chart"),
  stockChartStatus: document.getElementById("stock-chart-status"),
  stockLatestPrice: document.getElementById("stock-latest-price"),
  stockChange: document.getElementById("stock-change"),
  stockRangeBtns: document.querySelectorAll(".stock-range-btn"),
  marketDisclaimer: document.getElementById("market-disclaimer"),
  marketRatingBadge: document.getElementById("market-rating-badge"),
  marketValidationBadge: document.getElementById("market-validation-badge"),
  marketSummary: document.getElementById("market-summary"),
  marketRationale: document.getElementById("market-rationale"),
};

function getTheme() {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_KEY, next);
  const meta = document.getElementById("meta-theme-color");
  if (meta) meta.content = THEME_COLORS[next];
  if (els.themeToggle) {
    const target = next === "dark" ? "light" : "dark";
    els.themeToggle.setAttribute("aria-label", `Switch to ${target} theme`);
    els.themeToggle.title = `Switch to ${target} theme`;
  }
}

function toggleTheme() {
  applyTheme(getTheme() === "dark" ? "light" : "dark");
  if (lastStockPoints.length) {
    drawStockChart(lastStockPoints, lastStockChangePct, lastTrendLines);
  }
}

let uiState = "idle";
let elapsedTimer = null;
let runStartedAt = 0;
let completedPhases = new Set();
let lastReportPayload = null;
let lastPopoutWindow = null;

function log(...args) {
  console.log("[SignalPath]", ...args);
}

function escapeHtml(value) {
  const n = document.createElement("div");
  n.textContent = value;
  return n.innerHTML;
}

function parseCompetitors(raw) {
  return raw.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
}

function formatCompanyLabel(ticker, name) {
  if (!ticker) return "";
  return name ? `${ticker} — ${name}` : ticker;
}

function applyCompanySelection(hit) {
  els.ticker.value = hit.ticker;
  els.companyName.value = hit.name;
  els.companyLookup.value = formatCompanyLabel(hit.ticker, hit.name);
  loadPeerSuggestions(hit.ticker);
  loadStockChart(hit.ticker, currentStockRange);
}

let stockChartSeq = 0;
let currentStockRange = "6mo";
let lastStockPoints = [];
let lastTrendLines = [];
let lastStockChangePct = 0;

function ratingClass(rating) {
  return (rating || "hold").toLowerCase().replace(/_/g, "-");
}

function formatRatingLabel(rating) {
  return (rating || "HOLD").replace(/_/g, " ");
}

function renderMarketEntertainment(payload) {
  if (els.marketDisclaimer && payload.disclaimer) {
    els.marketDisclaimer.textContent = payload.disclaimer;
  }
  const analysis = payload.analysis || {};
  const validation = payload.validation || {};

  if (els.marketRatingBadge) {
    const rating = analysis.rating || "HOLD";
    els.marketRatingBadge.textContent = formatRatingLabel(rating);
    els.marketRatingBadge.className = `market-rating-badge ${ratingClass(rating)}`;
  }
  if (els.marketValidationBadge) {
    const ok = validation.passed;
    els.marketValidationBadge.textContent = ok
      ? `Audit OK (${Math.round((validation.consistency_score || 0) * 100)}%)`
      : `Audit flagged (${Math.round((validation.consistency_score || 0) * 100)}%)`;
    els.marketValidationBadge.className = `market-validation-badge ${ok ? "ok" : "warn"}`;
    const hint = [...(validation.warnings || []), ...(validation.unsupported_claims || [])]
      .slice(0, 2)
      .join(" · ");
    if (hint) els.marketValidationBadge.title = hint;
  }
  if (els.marketSummary) {
    els.marketSummary.textContent = analysis.summary || "";
  }
  if (els.marketRationale) {
    const lines = analysis.rationale || [];
    if (!lines.length) {
      els.marketRationale.hidden = true;
      els.marketRationale.innerHTML = "";
    } else {
      els.marketRationale.hidden = false;
      els.marketRationale.innerHTML = lines
        .map((line) => `<li>${escapeHtml(line)}</li>`)
        .join("");
    }
  }
}

function chartCssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function formatPrice(value, currency = "USD") {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `$${Number(value).toFixed(2)}`;
  }
}

function drawStockChart(points, changePct, trendLines = []) {
  const canvas = els.stockChart;
  if (!canvas || !points.length) return;

  const wrap = canvas.parentElement;
  const width = Math.max(wrap?.clientWidth || 320, 280);
  const height = 160;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const pad = { top: 12, right: 10, bottom: 22, left: 44 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const closes = points.map((p) => p.close);
  const dateIndex = new Map(points.map((p, i) => [p.date, i]));
  const allValues = [...closes];
  (trendLines || []).forEach((line) => {
    (line.points || []).forEach((p) => allValues.push(p.close));
  });
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max - min || 1;

  const accent = chartCssVar("--accent-strong", "#4f8cff");
  const muted = chartCssVar("--muted", "#8b9ab5");
  const border = chartCssVar("--border", "#2a3548");
  const positive = chartCssVar("--pass", "#3dd68c");
  const negative = chartCssVar("--fail", "#ff6b6b");
  const lineColor = changePct >= 0 ? positive : negative;
  const fillTop = changePct >= 0 ? "rgba(61, 214, 140, 0.22)" : "rgba(255, 107, 107, 0.18)";

  const xForIndex = (i) => pad.left + (i / Math.max(points.length - 1, 1)) * plotW;
  const yForValue = (v) => pad.top + plotH - ((v - min) / span) * plotH;

  ctx.clearRect(0, 0, width, height);

  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top + plotH);
  ctx.lineTo(pad.left + plotW, pad.top + plotH);
  ctx.stroke();

  ctx.fillStyle = muted;
  ctx.font = "10px JetBrains Mono, monospace";
  ctx.textAlign = "right";
  ctx.fillText(max.toFixed(0), pad.left - 6, pad.top + 8);
  ctx.fillText(min.toFixed(0), pad.left - 6, pad.top + plotH);

  const trendColors = [accent, "#c5a3ff"];
  (trendLines || []).forEach((line, idx) => {
    const series = line.points || [];
    if (!series.length) return;
    ctx.beginPath();
    let started = false;
    series.forEach((pt) => {
      const i = dateIndex.get(pt.date);
      if (i === undefined) return;
      const x = xForIndex(i);
      const y = yForValue(pt.close);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.strokeStyle = trendColors[idx % trendColors.length];
    ctx.lineWidth = 1.25;
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
  });

  const coords = closes.map((close, i) => ({
    x: xForIndex(i),
    y: yForValue(close),
  }));

  ctx.beginPath();
  coords.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.lineTo(coords[coords.length - 1].x, pad.top + plotH);
  ctx.lineTo(coords[0].x, pad.top + plotH);
  ctx.closePath();
  ctx.fillStyle = fillTop;
  ctx.fill();

  ctx.beginPath();
  coords.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.strokeStyle = lineColor;
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.stroke();
}

async function loadStockChart(ticker, range = currentStockRange) {
  const symbol = (ticker || "").trim().toUpperCase();
  if (!symbol || !els.stockChart) return;

  currentStockRange = range || "6mo";
  const seq = ++stockChartSeq;

  if (els.stockChartStatus) {
    els.stockChartStatus.hidden = false;
    els.stockChartStatus.textContent = "Loading chart…";
  }
  if (els.stockLatestPrice) els.stockLatestPrice.textContent = "—";
  if (els.stockChange) els.stockChange.textContent = "";

  els.stockRangeBtns?.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.range === currentStockRange);
  });

  try {
    const res = await fetch(
      `/api/companies/${encodeURIComponent(symbol)}/market-entertainment?range=${encodeURIComponent(currentStockRange)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(typeof err.detail === "string" ? err.detail : `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (seq !== stockChartSeq) return;

    const history = data.history || {};
    lastStockPoints = history.points || [];
    lastTrendLines = data.trend_lines || [];
    lastStockChangePct = history.change_pct || 0;
    if (!lastStockPoints.length) throw new Error("No price data");

    renderMarketEntertainment(data);

    if (els.stockLatestPrice) {
      els.stockLatestPrice.textContent = formatPrice(history.latest_close, history.currency);
    }
    if (els.stockChange) {
      const sign = history.change >= 0 ? "+" : "";
      const cls = history.change >= 0 ? "up" : "down";
      els.stockChange.className = `stock-change ${cls}`;
      els.stockChange.textContent = `${sign}${history.change.toFixed(2)} (${sign}${history.change_pct.toFixed(2)}%)`;
    }

    drawStockChart(lastStockPoints, lastStockChangePct, lastTrendLines);
    if (els.stockChartStatus) {
      const first = lastStockPoints[0]?.date || "";
      const last = lastStockPoints[lastStockPoints.length - 1]?.date || "";
      els.stockChartStatus.hidden = false;
      const src = data.data_source || "Yahoo Finance";
      els.stockChartStatus.textContent = `${first} → ${last}${history.exchange ? ` · ${history.exchange}` : ""} · ${src}`;
    }
  } catch (e) {
    if (seq !== stockChartSeq) return;
    lastStockPoints = [];
    lastTrendLines = [];
    const ctx = els.stockChart?.getContext("2d");
    if (ctx && els.stockChart) {
      ctx.clearRect(0, 0, els.stockChart.width, els.stockChart.height);
    }
    if (els.stockChartStatus) {
      els.stockChartStatus.hidden = false;
      els.stockChartStatus.textContent = e.message || "Chart unavailable";
    }
  }
}

let peerSuggestionsSeq = 0;
let lastPeerTickers = [];

function getSelectedCompetitors() {
  return new Set(parseCompetitors(els.competitors.value));
}

function setCompetitorsFromSet(tickers) {
  els.competitors.value = [...tickers].join(", ");
}

function toggleCompetitor(ticker) {
  const selected = getSelectedCompetitors();
  if (selected.has(ticker)) selected.delete(ticker);
  else selected.add(ticker);
  setCompetitorsFromSet(selected);
  renderPeerChips(lastPeerTickers);
}

function renderPeerChips(peers) {
  if (!els.peerChips) return;
  const selected = getSelectedCompetitors();
  els.peerChips.innerHTML = peers
    .map((peer) => {
      const active = selected.has(peer.ticker);
      return `<button
        type="button"
        class="peer-chip${active ? " active" : ""}"
        data-ticker="${escapeHtml(peer.ticker)}"
        role="listitem"
        title="${escapeHtml(peer.name)}"
      >${escapeHtml(peer.ticker)}</button>`;
    })
    .join("");
  els.peerChips.querySelectorAll(".peer-chip").forEach((btn) => {
    btn.addEventListener("click", () => toggleCompetitor(btn.dataset.ticker));
  });
}

function clearPeerSuggestions() {
  if (!els.peerSuggestions) return;
  els.peerSuggestions.hidden = true;
  if (els.peerChips) els.peerChips.innerHTML = "";
  if (els.peerClusterLabel) els.peerClusterLabel.textContent = "";
  if (els.peerSuggestionsEmpty) els.peerSuggestionsEmpty.hidden = true;
  if (els.peerUseAll) els.peerUseAll.hidden = true;
  lastPeerTickers = [];
}

async function loadPeerSuggestions(ticker) {
  if (!els.peerSuggestions || !ticker) return;
  const seq = ++peerSuggestionsSeq;
  els.peerSuggestions.hidden = false;
  if (els.peerClusterLabel) els.peerClusterLabel.textContent = "Loading peer suggestions…";
  if (els.peerChips) els.peerChips.innerHTML = "";
  if (els.peerSuggestionsEmpty) els.peerSuggestionsEmpty.hidden = true;
  if (els.peerUseAll) els.peerUseAll.hidden = true;

  try {
    const res = await fetch(
      `/api/companies/${encodeURIComponent(ticker)}/peer-suggestions`
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (seq !== peerSuggestionsSeq) return;

    lastPeerTickers = data.peers || [];
    if (!lastPeerTickers.length) {
      if (els.peerClusterLabel) {
        els.peerClusterLabel.textContent = data.cluster_label || "Similar companies";
      }
      if (els.peerSuggestionsEmpty) els.peerSuggestionsEmpty.hidden = false;
      return;
    }

    const label =
      data.cluster_label ||
      (data.source === "sic" ? "Peers by industry (SEC SIC)" : "Suggested peers");
    if (els.peerClusterLabel) els.peerClusterLabel.textContent = label;
    renderPeerChips(lastPeerTickers);
    if (els.peerUseAll) {
      els.peerUseAll.hidden = false;
      els.peerUseAll.onclick = () => {
        const selected = getSelectedCompetitors();
        lastPeerTickers.forEach((p) => selected.add(p.ticker));
        setCompetitorsFromSet(selected);
        renderPeerChips(lastPeerTickers);
      };
    }
  } catch (e) {
    if (seq !== peerSuggestionsSeq) return;
    if (els.peerClusterLabel) els.peerClusterLabel.textContent = "Peer suggestions unavailable";
    if (els.peerSuggestionsEmpty) {
      els.peerSuggestionsEmpty.textContent = e.message || "Could not load suggestions";
      els.peerSuggestionsEmpty.hidden = false;
    }
  }
}

let companySearchTimer = null;
let companySearchSeq = 0;
let companyActiveIndex = -1;
let companyHits = [];
let companyAnchor = els.comboboxLookup;

function closeCompanySuggestions() {
  els.companySuggestions.hidden = true;
  els.companyLookup.setAttribute("aria-expanded", "false");
  companyActiveIndex = -1;
}

function anchorCompanySuggestions(container) {
  companyAnchor = container || els.comboboxLookup;
  companyAnchor.appendChild(els.companySuggestions);
}

function renderCompanySuggestions(hits, statusText) {
  companyHits = hits;
  companyActiveIndex = -1;
  if (statusText) {
    els.companySuggestions.innerHTML = `<li class="combobox-status">${escapeHtml(statusText)}</li>`;
    els.companySuggestions.hidden = false;
    return;
  }
  if (!hits.length) {
    els.companySuggestions.innerHTML = `<li class="combobox-status">No matches</li>`;
    els.companySuggestions.hidden = false;
    return;
  }
  els.companySuggestions.innerHTML = hits
    .map(
      (hit, i) => `<li>
        <button type="button" class="combobox-option" role="option" data-index="${i}">
          <span class="opt-ticker">${escapeHtml(hit.ticker)}</span>
          <span class="opt-name">${escapeHtml(hit.name)}</span>
        </button>
      </li>`
    )
    .join("");
  els.companySuggestions.hidden = false;
  els.companySuggestions.querySelectorAll(".combobox-option").forEach((btn) => {
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const hit = companyHits[Number(btn.dataset.index)];
      if (hit) {
        applyCompanySelection(hit);
        closeCompanySuggestions();
      }
    });
  });
}

function highlightCompanyOption(index) {
  const options = els.companySuggestions.querySelectorAll(".combobox-option");
  options.forEach((el, i) => el.classList.toggle("active", i === index));
  companyActiveIndex = index;
  if (options[index]) options[index].scrollIntoView({ block: "nearest" });
}

async function fetchCompanySuggestions(query) {
  const seq = ++companySearchSeq;
  if (query.length < 1) {
    closeCompanySuggestions();
    return;
  }
  renderCompanySuggestions([], "Searching…");
  try {
    const res = await fetch(
      `/api/companies/search?q=${encodeURIComponent(query)}&limit=12`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(typeof err.detail === "string" ? err.detail : `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (seq !== companySearchSeq) return;
    renderCompanySuggestions(data.results || []);
    els.companyLookup.setAttribute("aria-expanded", "true");
  } catch (e) {
    if (seq !== companySearchSeq) return;
    renderCompanySuggestions([], e.message || "Search failed");
  }
}

function queryForSearch(raw) {
  const text = raw.trim();
  const sep = text.indexOf(" — ");
  return sep > 0 ? text.slice(0, sep).trim() : text;
}

function scheduleCompanySearch(query, anchor) {
  anchorCompanySuggestions(anchor);
  clearTimeout(companySearchTimer);
  const q = queryForSearch(query);
  companySearchTimer = setTimeout(() => fetchCompanySuggestions(q), 180);
}

function initCompanyTypeahead() {
  const inputs = [
    { el: els.companyLookup, anchor: els.comboboxLookup, useRaw: false },
    { el: els.ticker, anchor: els.comboboxTicker, useRaw: true },
    { el: els.companyName, anchor: els.comboboxCompany, useRaw: true },
  ];

  inputs.forEach(({ el, anchor, useRaw }) => {
    if (!el) return;
    el.addEventListener("focus", () => anchorCompanySuggestions(anchor));
    el.addEventListener("input", () => {
      const q = useRaw ? el.value.trim() : el.value.trim();
      if (useRaw && el === els.ticker) {
        els.companyLookup.value = el.value.trim().toUpperCase();
      }
      scheduleCompanySearch(q, anchor);
    });
    el.addEventListener("keydown", (e) => {
      if (els.companySuggestions.hidden) return;
      const options = els.companySuggestions.querySelectorAll(".combobox-option");
      if (!options.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        highlightCompanyOption(Math.min(companyActiveIndex + 1, options.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        highlightCompanyOption(Math.max(companyActiveIndex - 1, 0));
      } else if (e.key === "Enter" && companyActiveIndex >= 0) {
        e.preventDefault();
        const hit = companyHits[companyActiveIndex];
        if (hit) {
          applyCompanySelection(hit);
          closeCompanySuggestions();
        }
      } else if (e.key === "Escape") {
        closeCompanySuggestions();
      }
    });
    el.addEventListener("blur", () => {
      setTimeout(() => {
        if (!els.companySuggestions.matches(":hover")) closeCompanySuggestions();
      }, 150);
    });
  });

  document.addEventListener("click", (e) => {
    if (
      e.target.closest(".combobox") ||
      e.target.closest("#company-suggestions")
    ) {
      return;
    }
    closeCompanySuggestions();
  });
}

function setUiState(state) {
  uiState = state;
  document.body.dataset.uiState = state;

  const statusLabel =
    state === "idle"
      ? "Idle"
      : state === "running"
        ? "Running"
        : state === "completed"
          ? "Succeeded"
          : "Failed";

  els.headerStatus.textContent = statusLabel;
  els.headerStatus.className = `status-pill ${state === "completed" ? "succeeded" : state}`;

  if (state === "running") {
    setMobileTab("job");
    els.mobileSuccessBar.hidden = true;
    els.shareFab.hidden = true;
  }

  if (state === "completed") {
    els.mobileSuccessBar.hidden = window.innerWidth >= 1024;
    els.shareFab.hidden = window.innerWidth >= 1024;
    els.mobileSuccessText.textContent = "Report complete";
    if (lastReportPayload?.evals) {
      const e = lastReportPayload.evals;
      els.mobileSuccessMeta.textContent = `Score ${e.claim_support_score.toFixed(2)} · ${e.passed ? "passed" : "failed"}`;
    }
    setPhase("finalize_response", "Report ready");
    updateProgress(100);
  }

  if (state === "error") {
    els.shareFab.hidden = true;
  }
}

function setMobileTab(tab) {
  document.body.dataset.mobileTab = tab;
  document.querySelectorAll(".mobile-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
}

document.querySelectorAll(".mobile-tab").forEach((btn) => {
  btn.addEventListener("click", () => setMobileTab(btn.dataset.tab));
});

function updateProgress(pct) {
  const p = Math.min(100, Math.max(0, pct));
  els.progressFill.style.strokeDashoffset = String(RING_C * (1 - p / 100));
  els.progressPct.textContent = `${Math.round(p)}%`;
}

function setPhase(phaseId, detail) {
  const phase = PHASES.find((p) => p.id === phaseId) || PHASES[0];
  els.phaseText.textContent = phase.label;
  els.phaseDetail.textContent = detail || "";

  els.phaseSteps.querySelectorAll("li").forEach((li) => {
    const id = li.dataset.phase;
    li.classList.remove("active", "done");
    if (completedPhases.has(id)) li.classList.add("done");
    if (id === phaseId) li.classList.add("active");
  });

  updateProgress((phase.step / 6) * 100);
}

function resetMonitor() {
  completedPhases.clear();
  updateProgress(0);
  els.phaseText.textContent = "Ready to generate";
  els.phaseDetail.textContent = "Configure inputs and start a run";
  els.phaseSteps.querySelectorAll("li").forEach((li) => {
    li.classList.remove("active", "done");
  });
}

function scrollFeedToEnd() {
  els.activityFeed.scrollTop = els.activityFeed.scrollHeight;
}

function appendLog(ts, level, message) {
  const placeholder = els.activityFeed.querySelector(".feed-placeholder");
  if (placeholder) placeholder.remove();

  const line = document.createElement("div");
  line.className = `log-line log-${level}`;
  line.innerHTML = `<span class="log-ts">[${escapeHtml(ts || "")}]</span> ${escapeHtml(message)}`;
  els.activityFeed.appendChild(line);
  scrollFeedToEnd();
}

function resetActivity() {
  els.activityFeed.innerHTML = '<p class="feed-placeholder">Run logs and artifacts appear here.</p>';
  els.artifactsList.innerHTML = "";
  els.artifactsBlock.hidden = true;
}

function updateElapsed() {
  const s = Math.floor((Date.now() - runStartedAt) / 1000);
  els.headerElapsed.textContent = `${s}s`;
}

function startRun(meta) {
  if (elapsedTimer) clearInterval(elapsedTimer);
  resetMonitor();
  resetActivity();
  runStartedAt = Date.now();
  setUiState("running");
  updateElapsed();
  elapsedTimer = setInterval(updateElapsed, 1000);
  setPhase("resolve_cik", `Starting ${meta.ticker} · ${meta.llm_provider}`);
  appendLog(meta.ts, "info", `Run started — ${meta.company_name} (${meta.ticker})`);
  appendLog(meta.ts, "info", `LLM: ${meta.llm_provider}`);
}

function markPhaseDone(nodeId) {
  completedPhases.add(nodeId);
  const phase = PHASES.find((p) => p.id === nodeId);
  if (phase) updateProgress((phase.step / 6) * 100);
}

function inferPhaseFromLog(message) {
  if (message.includes("resolve") || message.includes("CIK")) return "resolve_cik";
  if (message.includes("SEC") || message.includes("EDGAR")) return "fetch_sec_data";
  if (message.includes("evidence")) return "extract_evidence";
  if (message.includes("Generate") || message.includes("report")) return "generate_report";
  if (message.includes("audit") || message.includes("Eval")) return "evaluate_report";
  if (message.includes("Finalize") || message.includes("complete")) return "finalize_response";
  return null;
}

function onStepEvent(data) {
  if (data.node && PHASES.some((p) => p.id === data.node)) {
    setPhase(data.node);
    if (data.status === "done") markPhaseDone(data.node);
  }
}

function onLogEvent(data) {
  appendLog(data.ts, data.level, data.message);
  const inferred = inferPhaseFromLog(data.message);
  if (inferred && uiState === "running") {
    setPhase(inferred, data.message.replace(/^Step \d\/\d [^—]+— /, "").slice(0, 80));
  }
}

function addArtifact(artifact) {
  els.artifactsBlock.hidden = false;
  const details = document.createElement("details");
  details.className = "artifact-item";
  details.open = artifact.id === "evidence";
  const summary = document.createElement("summary");
  summary.textContent = artifact.title;
  details.appendChild(summary);
  const pre = document.createElement("pre");
  pre.className = "artifact-body";
  pre.textContent = artifact.body;
  details.appendChild(pre);
  els.artifactsList.appendChild(details);
}

async function consumeEventStream(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      if (!chunk.trim()) continue;
      let eventType = "message";
      let dataStr = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;
      const handler = handlers[eventType];
      if (handler) handler(JSON.parse(dataStr));
    }
  }
}

function renderSignalCards(container, items) {
  if (!items?.length) {
    container.innerHTML = '<p class="muted">None</p>';
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
    <div class="signal-card">
      <div class="card-head"><h4>${escapeHtml(item.claim)}</h4><span class="badge">${escapeHtml(item.confidence)}</span></div>
      <p>${escapeHtml(item.why_it_matters)}</p>
      <p class="refs">refs: ${(item.evidence_refs || []).join(", ") || "—"}</p>
    </div>`
    )
    .join("");
}

function renderBulletList(container, items) {
  container.innerHTML = (items?.length ? items : ["None"])
    .map((i) => `<li>${escapeHtml(i)}</li>`)
    .join("");
}

function renderEvidenceTable(rows) {
  const tbody = document.querySelector("#evidence-table tbody");
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="muted">None</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map(
      (r) => `<tr>
      <td>${escapeHtml(r.claim)}</td><td>${escapeHtml(r.evidence)}</td>
      <td>${escapeHtml(r.source)}</td><td>${escapeHtml(r.confidence)}</td></tr>`
    )
    .join("");
}

function renderReport(data) {
  const { report, evals } = data;
  lastReportPayload = data;

  document.getElementById("executive-summary").textContent = report.executive_summary || "";
  renderSignalCards(document.getElementById("top-signals"), report.top_signals);
  renderBulletList(document.getElementById("noise"), report.noise);
  renderSignalCards(document.getElementById("risks"), report.risks);
  renderBulletList(document.getElementById("recommended-actions"), report.recommended_actions);
  renderEvidenceTable(report.evidence_table);

  const passedEl = document.getElementById("eval-passed");
  passedEl.textContent = evals.passed ? "true" : "false";
  passedEl.className = evals.passed ? "pass" : "fail";
  document.getElementById("eval-section").classList.toggle("eval-failed", !evals.passed);
  document.getElementById("eval-score").textContent = evals.claim_support_score?.toFixed(2) ?? "—";
  renderBulletList(
    document.getElementById("unsupported-claims"),
    evals.unsupported_claims?.length ? evals.unsupported_claims : ["None"]
  );
  renderBulletList(
    document.getElementById("eval-warnings"),
    evals.warnings?.length ? evals.warnings : ["None"]
  );

  els.reportEmpty.hidden = true;
  els.reportContent.hidden = false;
  els.popoutBtn.disabled = false;

  if (window.innerWidth < 1024) {
    setMobileTab("results");
  }
}

function buildReportPlainText(data) {
  if (!data?.report) return "";
  const r = data.report;
  const lines = [
    `SignalPath Intel — ${data.ticker || ""} ${data.company_name || ""}`,
    "",
    "EXECUTIVE SUMMARY",
    r.executive_summary,
    "",
    "TOP SIGNALS",
    ...(r.top_signals || []).map((s) => `• ${s.claim}: ${s.why_it_matters}`),
    "",
    "NOISE",
    ...(r.noise || []).map((n) => `• ${n}`),
    "",
    "RISKS",
    ...(r.risks || []).map((s) => `• ${s.claim}`),
    "",
    "RECOMMENDED ACTIONS",
    ...(r.recommended_actions || []).map((a) => `• ${a}`),
  ];
  return lines.join("\n");
}

function buildPopoutHtml() {
  const clone = els.reportContent.cloneNode(true);
  clone.hidden = false;
  const light = getTheme() === "light";
  const bg = light ? "#f4f5f7" : "#0b0f17";
  const text = light ? "#1a1f2e" : "#e8edf5";
  const cardBg = light ? "#ffffff" : "#141b28";
  const border = light ? "#d4dae6" : "#2a3548";
  const execBg = light ? "rgba(45,95,199,.1)" : "rgba(79,140,255,.12)";
  const execBorder = light ? "rgba(45,95,199,.3)" : "rgba(79,140,255,.3)";
  return `<!DOCTYPE html><html data-theme="${getTheme()}"><head><meta charset="utf-8"><title>SignalPath Report</title>
  <style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;line-height:1.6;background:${bg};color:${text}}
  .exec-text{font-size:1.15rem}.result-card{border:1px solid ${border};border-radius:8px;padding:1rem;margin:1rem 0;background:${cardBg}}
  .exec-card{background:${execBg};border-color:${execBorder}}</style></head>
  <body><h1>SignalPath Intel Report</h1>${clone.outerHTML}</body></html>`;
}

function openPopout() {
  if (!lastReportPayload) return;
  if (lastPopoutWindow && !lastPopoutWindow.closed) {
    lastPopoutWindow.focus();
    return;
  }
  lastPopoutWindow = window.open("", "_blank", "width=800,height=900");
  if (!lastPopoutWindow) {
    alert("Pop-up blocked. Allow pop-ups for this site.");
    return;
  }
  lastPopoutWindow.document.write(buildPopoutHtml());
  lastPopoutWindow.document.close();
}

async function shareReport() {
  const text = buildReportPlainText(lastReportPayload);
  if (!text) return;
  if (navigator.share) {
    try {
      await navigator.share({ title: "SignalPath Report", text });
      return;
    } catch (e) {
      if (e.name === "AbortError") return;
    }
  }
  try {
    await navigator.clipboard.writeText(text);
    alert("Report copied to clipboard.");
  } catch {
    alert("Share unavailable. Use Pop-out on desktop or copy from the report panel.");
  }
}

function showError(msg) {
  els.error.textContent = msg;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
}

function formatSessionTime(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

async function loadSessionList() {
  try {
    const res = await fetch("/api/sessions?limit=30");
    if (!res.ok) return;
    const sessions = await res.json();
    if (!sessions.length) {
      els.sessionList.innerHTML = '<li class="muted">No saved runs</li>';
      return;
    }
    els.sessionList.innerHTML = sessions
      .map(
        (s) => `<li><button type="button" class="session-item" data-id="${escapeHtml(s.id)}">
        <span class="session-ticker">${escapeHtml(s.ticker)}</span>
        <span class="session-meta">${escapeHtml(formatSessionTime(s.created_at))} · ${s.elapsed_seconds.toFixed(0)}s · ${s.eval_passed ? "pass" : "fail"}</span>
        <span class="session-lens">${escapeHtml(s.lens)}</span></button></li>`
      )
      .join("");
    els.sessionList.querySelectorAll(".session-item").forEach((btn) => {
      btn.addEventListener("click", () => loadSession(btn.dataset.id));
    });
  } catch (e) {
    log("sessions", e);
  }
}

async function loadSession(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}`);
  if (!res.ok) {
    showError("Session not found");
    return;
  }
  const session = await res.json();
  els.ticker.value = session.request.ticker;
  els.companyName.value = session.request.company_name;
  els.companyLookup.value = formatCompanyLabel(
    session.request.ticker,
    session.request.company_name
  );
  document.getElementById("lens").value = session.request.lens;
  document.getElementById("competitors").value = (session.request.competitors || []).join(", ");
  loadPeerSuggestions(session.request.ticker);
  loadStockChart(session.request.ticker, currentStockRange);

  resetActivity();
  (session.run_log || []).forEach((e) => appendLog(e.ts, e.level, e.message));
  renderReport(session.response);
  setUiState("completed");
  clearError();
  els.headerElapsed.textContent = `${session.elapsed_seconds.toFixed(0)}s`;
}

els.popoutBtn.addEventListener("click", openPopout);
els.shareFab.addEventListener("click", shareReport);
els.refreshSessions.addEventListener("click", loadSessionList);

els.logExpand.addEventListener("click", () => {
  els.logModalBody.innerHTML = els.activityFeed.innerHTML;
  els.logModal.hidden = false;
});
els.logModalClose.addEventListener("click", () => {
  els.logModal.hidden = true;
});
els.logModal.addEventListener("click", (e) => {
  if (e.target === els.logModal) els.logModal.hidden = true;
});

els.advancedToggle.addEventListener("click", () => {
  els.advancedSheet.hidden = false;
});
els.sheetClose.addEventListener("click", () => {
  els.advancedSheet.hidden = true;
});
els.sheetBackdrop.addEventListener("click", () => {
  els.advancedSheet.hidden = true;
});

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  els.submitBtn.disabled = true;

  const payload = {
    ticker: els.ticker.value.trim().toUpperCase(),
    company_name: els.companyName.value.trim(),
    lens: document.getElementById("lens").value.trim(),
    competitors: parseCompetitors(document.getElementById("competitors").value),
  };

  let finalResponse = null;

  try {
    const response = await fetch("/reports/company-signal/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(typeof err.detail === "string" ? err.detail : `HTTP ${response.status}`);
    }

    await consumeEventStream(response, {
      run_start: (data) => startRun(data),
      log: (data) => onLogEvent(data),
      step: (data) => onStepEvent(data),
      artifact: (data) => addArtifact(data),
      session_saved: () => loadSessionList(),
      complete: (data) => {
        finalResponse = data.response;
      },
      error: (data) => {
        throw new Error(data.message);
      },
      run_end: (data) => {
        if (elapsedTimer) clearInterval(elapsedTimer);
        if (data.status === "succeeded") {
          setUiState("completed");
          appendLog(data.ts, "info", "Run succeeded");
        } else {
          setUiState("error");
          appendLog(data.ts, "error", "Run failed");
        }
      },
    });

    if (!finalResponse) throw new Error("No report returned");
    renderReport(finalResponse);
    loadSessionList();
  } catch (err) {
    if (elapsedTimer) clearInterval(elapsedTimer);
    setUiState("error");
    setPhase("resolve_cik", err.message || "Run failed");
    appendLog("", "error", err.message || "Run failed");
    showError(err.message || "Something went wrong");
  } finally {
    els.submitBtn.disabled = false;
  }
});

els.themeToggle?.addEventListener("click", toggleTheme);
applyTheme(getTheme());
initCompanyTypeahead();

els.stockRangeBtns?.forEach((btn) => {
  btn.addEventListener("click", () => {
    const range = btn.dataset.range || "6mo";
    loadStockChart(els.ticker?.value?.trim(), range);
  });
});

let stockChartResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(stockChartResizeTimer);
  stockChartResizeTimer = setTimeout(() => {
    if (!lastStockPoints.length) return;
    drawStockChart(lastStockPoints, lastStockChangePct, lastTrendLines);
  }, 120);
});

els.ticker?.addEventListener("change", () => {
  const t = els.ticker.value.trim().toUpperCase();
  if (t) loadStockChart(t, currentStockRange);
});

const footerYear = document.getElementById("footer-year");
if (footerYear) footerYear.textContent = String(new Date().getFullYear());

els.competitors?.addEventListener("input", () => {
  if (lastPeerTickers.length) renderPeerChips(lastPeerTickers);
});

loadSessionList();
setUiState("idle");
loadPeerSuggestions(els.ticker?.value?.trim() || "MSFT");
loadStockChart(els.ticker?.value?.trim() || "MSFT", currentStockRange);
