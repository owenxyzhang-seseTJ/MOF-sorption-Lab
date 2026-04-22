const state = {
  adsorbates: [],
  results: {
    isotherm: null,
    qst: null,
    iast: null,
    bet: null,
  },
  plotRegistry: {},
  traceStyles: {},
  importSession: null,
};

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5055" : "";
const DEFAULT_STYLE = {
  fontFamily: '"SF Pro Text", -apple-system, sans-serif',
  fontSize: 14,
  markerSymbol: "circle",
  markerSize: 8,
  markerColor: "#1974d2",
  lineColor: "#0d425d",
  lineWidth: 3,
  xAxisType: "linear",
  yAxisType: "linear",
  xAxisTitle: "",
  yAxisTitle: "",
};
const TRACE_PALETTE = ["#0A84FF", "#30D158", "#FF9F0A", "#FF375F", "#64D2FF", "#BF5AF2", "#FFD60A"];

const samples = {
  isotherm: `0.01\t0.52
0.03\t1.02
0.05\t1.34
0.10\t1.86
0.20\t2.43
0.40\t3.11
0.80\t3.85
1.20\t4.13
1.80\t4.33`,
  qst: [
    {
      temperature: 298.15,
      text: `0.01\t0.42
0.03\t0.88
0.05\t1.17
0.10\t1.72
0.20\t2.45
0.40\t3.12
0.80\t3.88`,
    },
    {
      temperature: 308.15,
      text: `0.01\t0.35
0.03\t0.77
0.05\t1.02
0.10\t1.50
0.20\t2.11
0.40\t2.78
0.80\t3.48`,
    },
    {
      temperature: 318.15,
      text: `0.01\t0.28
0.03\t0.65
0.05\t0.90
0.10\t1.33
0.20\t1.88
0.40\t2.50
0.80\t3.16`,
    },
  ],
  iast: [
    {
      label: "CO2",
      adsorbate: "carbon dioxide",
      model: "Dual-site Langmuir",
      text: `0.01\t0.61
0.03\t1.22
0.05\t1.65
0.10\t2.38
0.20\t3.18
0.40\t3.95
0.80\t4.60
1.50\t5.01`,
    },
    {
      label: "N2",
      adsorbate: "nitrogen",
      model: "Langmuir",
      text: `0.01\t0.08
0.03\t0.15
0.05\t0.21
0.10\t0.35
0.20\t0.57
0.40\t0.88
0.80\t1.22
1.50\t1.58`,
    },
  ],
  bet: `0.01\t42.7
0.03\t68.1
0.05\t79.5
0.08\t91.4
0.10\t98.8
0.15\t111.5
0.20\t123.2
0.25\t131.7
0.30\t138.1
0.40\t149.2
0.50\t161.3
0.60\t174.8
0.70\t192.4
0.80\t214.6
0.90\t243.1
0.97\t271.4`,
};

function qs(selector, root = document) {
  return root.querySelector(selector);
}

function qsa(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

function setStatus(element, message = "", type = "") {
  if (!element) return;
  element.textContent = message;
  element.className = `status-text ${type}`.trim();
}

function chemicalFormulaToHtml(formula = "") {
  return formula.replace(/([A-Za-z\)])(\d+)/g, "$1<sub>$2</sub>");
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

function parseDelimitedText(text) {
  const rows = text
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/[\t,\s;]+/).filter(Boolean);
      return parts.slice(0, 2).map(Number);
    })
    .filter((parts) => parts.length === 2 && parts.every((value) => Number.isFinite(value)));
  return {
    pressure: rows.map((row) => row[0]),
    loading: rows.map((row) => row[1]),
  };
}

function renderSimplePreview(tbody, pressure = [], loading = []) {
  tbody.innerHTML = "";
  pressure.slice(0, 12).forEach((p, index) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${formatNumber(p, 6)}</td><td>${formatNumber(loading[index], 6)}</td>`;
    tbody.appendChild(tr);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function activateRoute(routeName) {
  qsa(".route-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.routeTarget === routeName);
  });
  qsa(".route-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `route-${routeName}`);
  });
}

function serializeTableBody(tbodyId) {
  const tbody = qs(`#${tbodyId}`);
  if (!tbody) return "";
  const rows = [...tbody.querySelectorAll("tr")].map((tr) =>
    [...tr.children].map((cell) => cell.textContent.trim()).join("\t")
  );
  return rows.join("\n");
}

async function copyTableBody(tbodyId) {
  const text = serializeTableBody(tbodyId);
  if (!text) return;
  await navigator.clipboard.writeText(text);
}

function renderAdsorbates(items) {
  const tbody = qs("#adsorbate-results");
  const count = qs("#adsorbate-count");
  tbody.innerHTML = "";
  count.textContent = `${items.length} 条记录`;
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="formula-chip">${chemicalFormulaToHtml(item.formula_display || item.formula)}</span></td>
      <td>${item.zh}</td>
      <td>${item.en}</td>
      <td>${formatNumber(item.molecular_size_a, 2)}</td>
      <td>${formatNumber(item.kinetic_diameter_a, 2)}</td>
      <td>${formatNumber(item.melting_point_c, 1)}</td>
      <td>${formatNumber(item.boiling_point_c, 1)}</td>
      <td>${formatNumber(item.dipole_moment_d, 3)}</td>
      <td>${formatNumber(item.quadrupole_moment, 3)}${item.note ? `<br><span class="helper-text">${item.note}</span>` : ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadAdsorbates(query = "") {
  const result = await fetchJson(`/api/adsorbates?q=${encodeURIComponent(query)}`);
  state.adsorbates = result.items;
  renderAdsorbates(result.items);
}

async function parseFileToData(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  if (options.sheet) formData.append("sheet", options.sheet);
  return fetchJson("/api/parse-file", { method: "POST", body: formData });
}

function populateTextareaFromParsed(panel, parsed) {
  const textarea = qs(".dataset-textarea", panel) || panel.querySelector('textarea[name="rawData"]');
  const pressureSelect = qs(".pressure-unit-select", panel) || panel.querySelector('[name="pressureUnit"]');
  const loadingSelect = qs(".loading-unit-select", panel) || panel.querySelector('[name="loadingUnit"]');
  textarea.value = parsed.pressure.map((value, index) => `${value}\t${parsed.loading[index]}`).join("\n");
  if (pressureSelect && parsed.detected_units.pressure_unit) pressureSelect.value = parsed.detected_units.pressure_unit;
  if (loadingSelect && parsed.detected_units.loading_unit) loadingSelect.value = parsed.detected_units.loading_unit;
  const branchSelect = panel.querySelector('[name="branch"]');
  if (branchSelect && parsed.selected_columns?.loading_branch) {
    branchSelect.value = parsed.selected_columns.loading_branch === "desorption" ? "des" : "ads";
  }
  const previewBody = qs(".dataset-preview", panel) || panel.querySelector("#isotherm-preview") || panel.querySelector("#bet-preview");
  if (previewBody) renderSimplePreview(previewBody, parsed.pressure, parsed.loading);
}

function statusTargetForPanel(panel) {
  return qs(".status-text", panel) || panel.querySelector("#isotherm-status") || panel.querySelector("#bet-status");
}

function reportImportError(panel, message) {
  const target = statusTargetForPanel(panel);
  if (target) {
    setStatus(target, message, "error");
  } else {
    window.alert(message);
  }
}

function selectedCandidate(parsed, candidateId) {
  return (parsed.candidate_columns || []).find((item) => item.id === candidateId);
}

function buildConfirmedImport(parsed, pressureId, loadingId, pressureUnit, loadingUnit) {
  const pressureCandidate = selectedCandidate(parsed, pressureId);
  const loadingCandidate = selectedCandidate(parsed, loadingId);
  if (!pressureCandidate || !loadingCandidate) {
    throw new Error("请选择有效的压力列和吸附量列。");
  }
  const pressure = [];
  const loading = [];
  for (let index = 0; index < Math.max(pressureCandidate.values.length, loadingCandidate.values.length); index += 1) {
    const p = pressureCandidate.values[index];
    const l = loadingCandidate.values[index];
    if (Number.isFinite(Number(p)) && Number.isFinite(Number(l))) {
      pressure.push(Number(p));
      loading.push(Number(l));
    }
  }
  if (pressure.length < 3) {
    throw new Error("所选列的有效重叠数据不足，至少需要 3 个点。");
  }
  return {
    pressure,
    loading,
    preview: pressure.slice(0, 12).map((value, index) => [value, loading[index]]),
    detected_units: {
      pressure_unit: pressureUnit,
      loading_unit: loadingUnit,
    },
    selected_columns: {
      pressure: pressureId,
      loading: loadingId,
      loading_branch: loadingCandidate.branch_guess,
    },
  };
}

function updateImportPreview() {
  const modal = qs("#import-modal");
  const session = state.importSession;
  if (!modal || !session?.parsed) return;
  const parsed = session.parsed;
  const pressureId = qs("#import-pressure-column").value;
  const loadingId = qs("#import-loading-column").value;
  const pressureCandidate = selectedCandidate(parsed, pressureId);
  const loadingCandidate = selectedCandidate(parsed, loadingId);
  if (!pressureCandidate || !loadingCandidate) return;
  const guessedPressureUnit = pressureCandidate.unit_guess || "bar";
  const guessedLoadingUnit = loadingCandidate.unit_guess || "mmol/g";
  if (!modal.dataset.unitsLocked) {
    qs("#import-pressure-unit").value = guessedPressureUnit;
    qs("#import-loading-unit").value = guessedLoadingUnit;
  }
  const branchText = {
    adsorption: "吸附支路",
    desorption: "脱附支路",
    unknown: "未识别支路",
  }[loadingCandidate.branch_guess || "unknown"];
  qs("#import-branch-guess").textContent = `${branchText} · 列名：${loadingCandidate.label}`;
  try {
    const selected = buildConfirmedImport(
      parsed,
      pressureId,
      loadingId,
      qs("#import-pressure-unit").value,
      qs("#import-loading-unit").value,
    );
    renderSimplePreview(qs("#import-preview-body"), selected.pressure, selected.loading);
  } catch (error) {
    qs("#import-preview-body").innerHTML = "";
    qs("#import-branch-guess").textContent = error.message;
  }
}

function renderImportWarnings(parsed) {
  const list = qs("#import-warning-list");
  list.innerHTML = "";
  const rows = [];
  if (parsed.detected_window) {
    const header = parsed.detected_window.header_row_1based ? `表头第 ${parsed.detected_window.header_row_1based} 行` : "未检测到明确表头";
    rows.push(`已定位数值数据区：第 ${parsed.detected_window.data_start_row_1based} 到 ${parsed.detected_window.data_end_row_1based} 行，${header}。`);
  }
  (parsed.warnings || []).forEach((warning) => rows.push(warning));
  rows.forEach((warning) => {
    const li = document.createElement("li");
    li.textContent = warning;
    list.appendChild(li);
  });
}

async function refreshImportSheet(sheet) {
  const session = state.importSession;
  if (!session?.file) return;
  const parsed = await parseFileToData(session.file, { sheet });
  session.parsed = parsed;
  fillImportDialog(parsed);
}

function fillImportDialog(parsed) {
  const modal = qs("#import-modal");
  const sheetSelect = qs("#import-sheet");
  const pressureSelect = qs("#import-pressure-column");
  const loadingSelect = qs("#import-loading-column");
  modal.dataset.unitsLocked = "";
  sheetSelect.innerHTML = (parsed.sheet_names || []).map((sheet) => `<option value="${sheet}">${sheet}</option>`).join("");
  sheetSelect.value = parsed.selected_sheet || (parsed.sheet_names || [])[0] || "";
  const pressureCandidates = (parsed.candidate_columns || []).filter((item) => item.role_guess === "pressure");
  const loadingCandidates = (parsed.candidate_columns || []).filter((item) => item.role_guess !== "pressure");
  pressureSelect.innerHTML = pressureCandidates.map((item) => `<option value="${item.id}">${item.label}</option>`).join("");
  loadingSelect.innerHTML = loadingCandidates.map((item) => {
    const branch = item.branch_guess === "unknown" ? "" : ` · ${item.branch_guess}`;
    return `<option value="${item.id}">${item.label}${branch}</option>`;
  }).join("");
  pressureSelect.value = parsed.selected_columns?.pressure || pressureCandidates[0]?.id || "";
  loadingSelect.value = parsed.selected_columns?.loading || loadingCandidates[0]?.id || "";
  renderImportWarnings(parsed);
  updateImportPreview();
}

async function openImportDialog(file, panel) {
  const parsed = await parseFileToData(file);
  state.importSession = { file, panel, parsed };
  fillImportDialog(parsed);
  const modal = qs("#import-modal");
  modal.hidden = false;
  document.body.classList.add("modal-open");
}

function closeImportDialog() {
  const modal = qs("#import-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  state.importSession = null;
}

function previewRootDataset(target) {
  if (target === "isotherm") {
    const form = qs("#isotherm-form");
    const data = parseDelimitedText(form.rawData.value);
    renderSimplePreview(qs("#isotherm-preview"), data.pressure, data.loading);
  }
  if (target === "bet") {
    const form = qs("#bet-form");
    const data = parseDelimitedText(form.rawData.value);
    renderSimplePreview(qs("#bet-preview"), data.pressure, data.loading);
  }
}

function attachDynamicDatasetActions(panel) {
  qs(".remove-block", panel)?.addEventListener("click", () => panel.remove());
  qs(".block-preview", panel)?.addEventListener("click", () => {
    const parsed = parseDelimitedText(qs(".dataset-textarea", panel).value);
    renderSimplePreview(qs(".dataset-preview", panel), parsed.pressure, parsed.loading);
  });
  qs(".block-import", panel)?.addEventListener("click", async () => {
    const fileInput = qs(".dataset-file", panel);
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      await openImportDialog(file, panel);
    } catch (error) {
      reportImportError(panel, error.message);
    }
  });
}

function addQstDataset(values = {}) {
  const fragment = qs("#qst-dataset-template").content.cloneNode(true);
  const panel = fragment.querySelector(".dataset-card");
  qs(".dataset-temperature", panel).value = values.temperature || "298.15";
  qs(".dataset-textarea", panel).value = values.text || "";
  attachDynamicDatasetActions(panel);
  qs("#qst-datasets").appendChild(fragment);
  if (values.text) {
    const parsed = parseDelimitedText(values.text);
    renderSimplePreview(qs(".dataset-preview", qs("#qst-datasets").lastElementChild), parsed.pressure, parsed.loading);
  }
}

function addIastComponent(values = {}) {
  const fragment = qs("#iast-component-template").content.cloneNode(true);
  const panel = fragment.querySelector(".dataset-card");
  qs(".component-label", panel).value = values.label || "CO2";
  qs(".component-adsorbate", panel).value = values.adsorbate || "carbon dioxide";
  qs(".component-model", panel).value = values.model || "Langmuir";
  qs(".dataset-textarea", panel).value = values.text || "";
  attachDynamicDatasetActions(panel);
  qs("#iast-components").appendChild(fragment);
  if (values.text) {
    const parsed = parseDelimitedText(values.text);
    renderSimplePreview(qs(".dataset-preview", qs("#iast-components").lastElementChild), parsed.pressure, parsed.loading);
  }
}

function explanationHtml(explanation, extra = "") {
  if (!explanation) return "";
  const equations = (explanation.equations && explanation.equations.length)
    ? explanation.equations
    : (explanation.formula ? [{ label: "Core equation", latex: explanation.formula }] : []);
  const equationsHtml = equations.map((equation) => `
    <article class="formula-card">
      ${equation.label ? `<p class="formula-caption">${equation.label}</p>` : ""}
      <div class="formula-block">${wrapMathBlock(equation.latex || "")}</div>
    </article>
  `).join("");
  const notes = (explanation.notes || []).map((note) => `<li>${note}</li>`).join("");
  return `
    <h4>${explanation.title || "方法说明"}</h4>
    <p>${explanation.summary || ""}</p>
    ${equationsHtml ? `<div class="formula-stack">${equationsHtml}</div>` : ""}
    ${notes ? `<ul>${notes}</ul>` : ""}
    ${extra}
  `;
}

function renderExplanation(containerId, explanation, extra = "") {
  const container = qs(`#${containerId}`);
  if (!container) return;
  container.innerHTML = explanationHtml(explanation, extra);
  typesetMath(container);
}

function wrapMathBlock(latex = "") {
  const trimmed = String(latex || "").trim();
  if (!trimmed) return "";
  if (/\\\[|\\\(|^\$/.test(trimmed)) return trimmed;
  return `\\[${trimmed}\\]`;
}

function typesetMath(root) {
  if (!root || !window.MathJax?.typesetPromise) return;
  if (window.MathJax.typesetClear) {
    window.MathJax.typesetClear([root]);
  }
  window.MathJax.typesetPromise([root]).catch(() => {});
}

function getStyleConfig(scope) {
  const root = qs(`.plot-style-panel[data-style-scope="${scope}"]`);
  if (!root) return { ...DEFAULT_STYLE };
  const config = { ...DEFAULT_STYLE };
  qsa("[data-style-key]", root).forEach((node) => {
    config[node.dataset.styleKey] = node.value;
  });
  config.fontSize = Number(config.fontSize || 14);
  config.markerSize = Number(config.markerSize || 8);
  config.lineWidth = Number(config.lineWidth || 3);
  return config;
}

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function defaultTraceColor(index) {
  return TRACE_PALETTE[index % TRACE_PALETTE.length];
}

function getTraceOverride(scope, plotId, traceIndex) {
  return state.traceStyles?.[scope]?.[plotId]?.[traceIndex] || {};
}

function setTraceOverride(scope, plotId, traceIndex, key, value) {
  state.traceStyles[scope] ||= {};
  state.traceStyles[scope][plotId] ||= {};
  state.traceStyles[scope][plotId][traceIndex] ||= {};
  if (value === "" || value === null || value === undefined) {
    delete state.traceStyles[scope][plotId][traceIndex][key];
  } else {
    state.traceStyles[scope][plotId][traceIndex][key] = value;
  }
}

function effectiveTraceColor(trace, style, override, index, traceCount, channel) {
  const traceColor = channel === "marker" ? trace.marker?.color : trace.line?.color;
  const overrideColor = channel === "marker" ? override.markerColor : override.lineColor;
  if (overrideColor) return overrideColor;
  if (traceColor) return traceColor;
  const shouldUsePalette = traceCount > 1
    && style.markerColor === DEFAULT_STYLE.markerColor
    && style.lineColor === DEFAULT_STYLE.lineColor;
  if (shouldUsePalette) return defaultTraceColor(index);
  return channel === "marker" ? style.markerColor : style.lineColor;
}

function resolveTraceAppearance(trace, style, override, index, traceCount) {
  const markerEnabled = trace.mode?.includes("markers");
  const lineEnabled = trace.mode?.includes("lines");
  return {
    markerEnabled,
    lineEnabled,
    markerSymbol: override.markerSymbol || trace.marker?.symbol || style.markerSymbol,
    markerSize: Number(override.markerSize || trace.marker?.size || style.markerSize),
    markerColor: effectiveTraceColor(trace, style, override, index, traceCount, "marker"),
    lineColor: effectiveTraceColor(trace, style, override, index, traceCount, "line"),
    lineWidth: Number(override.lineWidth || trace.line?.width || style.lineWidth),
    lineDash: override.lineDash || trace.line?.dash || "solid",
  };
}

function withPlotStyle(traces, style, plotId, scope) {
  return traces.map((trace, index) => {
    const next = { ...trace };
    const override = getTraceOverride(scope, plotId, index);
    const appearance = resolveTraceAppearance(trace, style, override, index, traces.length);
    if (appearance.markerEnabled) {
      next.marker = {
        ...(trace.marker || {}),
        symbol: appearance.markerSymbol,
        size: appearance.markerSize,
        color: appearance.markerColor,
      };
    }
    if (appearance.lineEnabled) {
      next.line = {
        ...(trace.line || {}),
        width: appearance.lineWidth,
        color: appearance.lineColor,
        dash: appearance.lineDash,
      };
    }
    return next;
  });
}

function plotTitleFor(divId) {
  const labels = {
    "isotherm-plot": "等温线拟合图",
    "qst-plot": "Qst 主图",
    "qst-fit-plot": "多温拟合图",
    "iast-selectivity-plot": "选择性图",
    "iast-uptake-plot": "组分吸附量图",
    "bet-plot": "BET 线性图",
    "psd-plot": "孔径分布图",
  };
  return labels[divId] || divId;
}

function renderRegisteredPlot(divId) {
  const target = qs(`#${divId}`);
  const definition = state.plotRegistry[divId];
  if (!target || !window.Plotly || !definition) return;
  const style = getStyleConfig(definition.scope);
  const finalTraces = withPlotStyle(definition.traces, style, divId, definition.scope);
  const finalLayout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: style.fontFamily, color: "#10233a", size: style.fontSize },
    margin: { l: 58, r: 22, t: 44, b: 58 },
    xaxis: {
      showgrid: true,
      gridcolor: "rgba(15, 23, 42, 0.08)",
      zeroline: false,
      linecolor: "rgba(77, 96, 122, 0.22)",
      tickcolor: "rgba(77, 96, 122, 0.22)",
      titlefont: { color: "#14304a" },
    },
    yaxis: {
      showgrid: true,
      gridcolor: "rgba(15, 23, 42, 0.08)",
      zeroline: false,
      linecolor: "rgba(77, 96, 122, 0.22)",
      tickcolor: "rgba(77, 96, 122, 0.22)",
      titlefont: { color: "#14304a" },
    },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
      bgcolor: "rgba(255,255,255,0.52)",
      bordercolor: "rgba(255,255,255,0.6)",
      borderwidth: 1,
    },
    ...definition.layout,
  };
  if (finalLayout.xaxis) {
    finalLayout.xaxis = {
      ...finalLayout.xaxis,
      type: style.xAxisType || finalLayout.xaxis.type || "linear",
      title: style.xAxisTitle || finalLayout.xaxis.title,
    };
  }
  if (finalLayout.yaxis) {
    finalLayout.yaxis = {
      ...finalLayout.yaxis,
      type: style.yAxisType || finalLayout.yaxis.type || "linear",
      title: style.yAxisTitle || finalLayout.yaxis.title,
    };
  }
  Plotly.react(target, finalTraces, finalLayout, { responsive: true, displaylogo: false });
  syncTraceEditor(definition.scope);
}

function makePlot(divId, traces, layout, styleScope) {
  state.plotRegistry[divId] = {
    scope: styleScope,
    traces: deepCopy(traces),
    layout: deepCopy(layout),
  };
  renderRegisteredPlot(divId);
}

function traceEditorHtml() {
  return `
    <section class="trace-style-shell">
      <div class="trace-style-header">
        <div>
          <h5>单条曲线样式</h5>
          <p>先选图，再选中某一条曲线或数据点，单独设置它的显示方式。</p>
        </div>
        <span class="pill subtle-pill">Per trace</span>
      </div>
      <div class="style-grid trace-grid">
        <label class="field">
          <span>图像</span>
          <select data-trace-plot></select>
        </label>
        <label class="field">
          <span>曲线</span>
          <select data-trace-index></select>
        </label>
        <label class="field" data-trace-role="marker">
          <span>点形状</span>
          <select data-trace-style-key="markerSymbol">
            <option value="">follow global</option>
            <option value="circle">circle</option>
            <option value="square">square</option>
            <option value="diamond">diamond</option>
            <option value="cross">cross</option>
            <option value="triangle-up">triangle-up</option>
          </select>
        </label>
        <label class="field" data-trace-role="marker">
          <span>点大小</span>
          <input data-trace-style-key="markerSize" type="number" step="1" min="1" />
        </label>
        <label class="field" data-trace-role="marker">
          <span>点颜色</span>
          <input data-trace-style-key="markerColor" type="color" value="#0A84FF" />
        </label>
        <label class="field" data-trace-role="line">
          <span>线颜色</span>
          <input data-trace-style-key="lineColor" type="color" value="#0A84FF" />
        </label>
        <label class="field" data-trace-role="line">
          <span>线宽</span>
          <input data-trace-style-key="lineWidth" type="number" step="0.5" min="0.5" />
        </label>
        <label class="field" data-trace-role="line">
          <span>线型</span>
          <select data-trace-style-key="lineDash">
            <option value="">follow global</option>
            <option value="solid">solid</option>
            <option value="dot">dot</option>
            <option value="dash">dash</option>
            <option value="dashdot">dashdot</option>
          </select>
        </label>
      </div>
      <p class="helper-text trace-style-note"></p>
    </section>
  `;
}

function ensureStylePanelChrome(panel) {
  if (qs(".plot-style-head", panel)) return;
  const scopeLabel = {
    isotherm: "等温线绘图格式",
    qst: "Qst 绘图格式",
    iast: "IAST 绘图格式",
    bet: "BET / PSD 绘图格式",
  }[panel.dataset.styleScope] || "绘图格式";
  const children = [...panel.childNodes];
  panel.innerHTML = `
    <div class="plot-style-head">
      <div>
        <h4>${scopeLabel}</h4>
        <p>默认隐藏，需要时再展开。</p>
      </div>
      <button type="button" class="style-toggle-button">显示格式设置</button>
    </div>
    <div class="style-section-body"></div>
  `;
  const body = qs(".style-section-body", panel);
  children.forEach((child) => body.appendChild(child));
  panel.classList.add("collapsed");
  qs(".style-toggle-button", panel).addEventListener("click", () => {
    const collapsed = panel.classList.toggle("collapsed");
    qs(".style-toggle-button", panel).textContent = collapsed ? "显示格式设置" : "隐藏格式设置";
  });
}

function ensureTraceEditor(panel) {
  if (qs(".trace-style-shell", panel)) return;
  const body = qs(".style-section-body", panel) || panel;
  body.insertAdjacentHTML("beforeend", traceEditorHtml());
  const scope = panel.dataset.styleScope;
  const plotSelect = qs("[data-trace-plot]", panel);
  const traceSelect = qs("[data-trace-index]", panel);
  plotSelect.addEventListener("change", () => {
    panel.dataset.selectedPlotId = plotSelect.value;
    panel.dataset.selectedTraceIndex = "0";
    syncTraceEditor(scope);
  });
  traceSelect.addEventListener("change", () => {
    panel.dataset.selectedTraceIndex = traceSelect.value;
    syncTraceEditor(scope);
  });
  qsa("[data-trace-style-key]", panel).forEach((input) => {
    const apply = () => {
      if (panel.dataset.syncing === "1") return;
      const plotId = panel.dataset.selectedPlotId;
      const traceIndex = Number(panel.dataset.selectedTraceIndex || 0);
      if (!plotId || Number.isNaN(traceIndex)) return;
      setTraceOverride(scope, plotId, traceIndex, input.dataset.traceStyleKey, input.value);
      renderRegisteredPlot(plotId);
    };
    input.addEventListener("change", apply);
    input.addEventListener("input", apply);
  });
}

function syncTraceEditor(scope) {
  const panel = qs(`.plot-style-panel[data-style-scope="${scope}"]`);
  if (!panel) return;
  ensureTraceEditor(panel);
  const plotEntries = Object.entries(state.plotRegistry).filter(([, definition]) => definition.scope === scope);
  const shell = qs(".trace-style-shell", panel);
  if (!shell) return;
  if (!plotEntries.length) {
    shell.hidden = true;
    return;
  }
  shell.hidden = false;
  const plotSelect = qs("[data-trace-plot]", panel);
  const traceSelect = qs("[data-trace-index]", panel);
  const currentPlotId = plotEntries.some(([plotId]) => plotId === panel.dataset.selectedPlotId)
    ? panel.dataset.selectedPlotId
    : plotEntries[0][0];
  panel.dataset.selectedPlotId = currentPlotId;
  plotSelect.innerHTML = plotEntries.map(([plotId]) => `<option value="${plotId}">${plotTitleFor(plotId)}</option>`).join("");
  plotSelect.value = currentPlotId;
  const currentPlot = state.plotRegistry[currentPlotId];
  const traceList = currentPlot.traces || [];
  const selectedTraceIndex = traceList[Number(panel.dataset.selectedTraceIndex || 0)] ? Number(panel.dataset.selectedTraceIndex) : 0;
  panel.dataset.selectedTraceIndex = String(selectedTraceIndex);
  traceSelect.innerHTML = traceList.length
    ? traceList.map((trace, index) => `<option value="${index}">${trace.name || `Trace ${index + 1}`}</option>`).join("")
    : `<option value="0">暂无曲线</option>`;
  traceSelect.value = String(selectedTraceIndex);
  const note = qs(".trace-style-note", panel);
  if (!traceList.length) {
    note.textContent = "当前图还没有可单独编辑的曲线。";
    return;
  }
  const trace = traceList[selectedTraceIndex];
  const globalStyle = getStyleConfig(scope);
  const override = getTraceOverride(scope, currentPlotId, selectedTraceIndex);
  const appearance = resolveTraceAppearance(trace, globalStyle, override, selectedTraceIndex, traceList.length);
  panel.dataset.syncing = "1";
  qsa("[data-trace-style-key]", panel).forEach((input) => {
    const key = input.dataset.traceStyleKey;
    const effectiveValue = {
      markerSymbol: appearance.markerSymbol,
      markerSize: appearance.markerSize,
      markerColor: appearance.markerColor,
      lineColor: appearance.lineColor,
      lineWidth: appearance.lineWidth,
      lineDash: appearance.lineDash,
    }[key];
    input.value = effectiveValue ?? "";
  });
  qsa("[data-trace-role='marker']", panel).forEach((field) => {
    field.classList.toggle("field-disabled", !appearance.markerEnabled);
    qsa("input, select", field).forEach((control) => {
      control.disabled = !appearance.markerEnabled;
    });
  });
  qsa("[data-trace-role='line']", panel).forEach((field) => {
    field.classList.toggle("field-disabled", !appearance.lineEnabled);
    qsa("input, select", field).forEach((control) => {
      control.disabled = !appearance.lineEnabled;
    });
  });
  note.textContent = `${plotTitleFor(currentPlotId)}: ${trace.name || `Trace ${selectedTraceIndex + 1}`}。如果这一条是数据点与拟合线中的某一条，现在可以单独改颜色、点形和线型。`;
  panel.dataset.syncing = "0";
}

function qstPayload() {
  const adsorbate = qs("#qst-adsorbate").value.trim();
  return {
    method: qs("#qst-method").value,
    datasets: qsa("#qst-datasets .dataset-card").map((panel) => {
      const parsed = parseDelimitedText(qs(".dataset-textarea", panel).value);
      return {
        adsorbate,
        temperature: Number(qs(".dataset-temperature", panel).value),
        pressureUnit: qs(".pressure-unit-select", panel).value,
        loadingUnit: qs(".loading-unit-select", panel).value,
        pressure: parsed.pressure,
        loading: parsed.loading,
      };
    }),
  };
}

function iastPayload() {
  const components = qsa("#iast-components .dataset-card").map((panel) => {
    const parsed = parseDelimitedText(qs(".dataset-textarea", panel).value);
    return {
      label: qs(".component-label", panel).value.trim(),
      adsorbate: qs(".component-adsorbate", panel).value.trim(),
      model: qs(".component-model", panel).value,
      temperature: Number(qs(".dataset-temperature", panel).value),
      pressureUnit: qs(".pressure-unit-select", panel).value,
      loadingUnit: qs(".loading-unit-select", panel).value,
      pressure: parsed.pressure,
      loading: parsed.loading,
    };
  });
  return {
    components,
    gasFractions: qs("#iast-fractions").value.split(/[,;\s]+/).filter(Boolean).map(Number),
    totalPressures: qs("#iast-total-pressures").value.split(/[,;\s]+/).filter(Boolean).map(Number),
    totalPressureUnit: qs("#iast-total-pressure-unit").value,
  };
}

function buildCsv(rows) {
  if (!rows || !rows.length) return "";
  const headers = Object.keys(rows[0]);
  const escape = (value) => {
    if (value === null || value === undefined) return "";
    const stringValue = String(value);
    if (/[",\n]/.test(stringValue)) {
      return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
  };
  return [headers.join(","), ...rows.map((row) => headers.map((header) => escape(row[header])).join(","))].join("\n");
}

function downloadText(filename, text, mimeType = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function getModuleExportRows(moduleName) {
  const result = state.results[moduleName];
  if (!result) return [];
  if (moduleName === "isotherm") {
    const length = Math.max(result.data.x.length, result.fit.x.length);
    return Array.from({ length }, (_, index) => ({
      pressure_data: result.data.x[index] ?? null,
      loading_data: result.data.y[index] ?? null,
      pressure_fit: result.fit.x[index] ?? null,
      loading_fit: result.fit.y[index] ?? null,
    }));
  }
  if (moduleName === "qst") return result.table || [];
  if (moduleName === "iast") return result.results || [];
  if (moduleName === "bet") {
    if (result.classical_psd) {
      return result.classical_psd.pore_widths_nm.map((value, index) => ({
        pore_width_nm: value,
        distribution: result.classical_psd.distribution[index],
      }));
    }
    if (result.dft_psd) {
      return result.dft_psd.pore_widths_nm.map((value, index) => ({
        pore_width_nm: value,
        distribution: result.dft_psd.distribution[index],
      }));
    }
  }
  return [];
}

function exportModuleCsv(moduleName) {
  const rows = getModuleExportRows(moduleName);
  if (!rows.length) return;
  downloadText(`${moduleName}-result.csv`, buildCsv(rows), "text/csv;charset=utf-8");
}

function exportModuleJson(moduleName) {
  const result = state.results[moduleName];
  if (!result) return;
  downloadText(`${moduleName}-result.json`, JSON.stringify(result, null, 2), "application/json;charset=utf-8");
}

async function runIsotherm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = qs("#isotherm-status");
  setStatus(status, "正在拟合…");
  try {
    const parsed = parseDelimitedText(form.rawData.value);
    renderSimplePreview(qs("#isotherm-preview"), parsed.pressure, parsed.loading);
    const payload = {
      adsorbate: form.adsorbate.value.trim(),
      temperature: Number(form.temperature.value),
      model: form.model.value,
      pressureUnit: form.pressureUnit.value,
      loadingUnit: form.loadingUnit.value,
      pressure: parsed.pressure,
      loading: parsed.loading,
    };
    const result = await fetchJson("/api/isotherm-fit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.results.isotherm = result;
    qs("#isotherm-r2").textContent = formatNumber(result.r2, 5);
    qs("#isotherm-rmse").textContent = formatNumber(result.rmse, 5);
    qs("#isotherm-units").textContent = `${result.pressure_unit} / ${result.loading_unit}`;
    qs("#isotherm-model-label").textContent = result.model;
    const tbody = qs("#isotherm-params");
    tbody.innerHTML = "";
    Object.entries(result.parameters || {}).forEach(([key, value]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${key}</td><td>${formatNumber(value, 8)}</td>`;
      tbody.appendChild(tr);
    });
    makePlot("isotherm-plot", [
      { x: result.data.x, y: result.data.y, mode: "markers", name: "Data" },
      { x: result.fit.x, y: result.fit.y, mode: "lines", name: "Fit" },
    ], {
      title: `${result.model} fit`,
      xaxis: { title: `Pressure (${result.pressure_unit})` },
      yaxis: { title: `Loading (${result.loading_unit})` },
    }, "isotherm");
    renderExplanation("isotherm-explanation", result.explanation);
    setStatus(status, "拟合完成。", "success");
  } catch (error) {
    setStatus(status, error.message, "error");
  }
}

async function runQst() {
  const status = qs("#qst-status");
  setStatus(status, "正在计算 Qst…");
  try {
    const payload = qstPayload();
    qsa("#qst-datasets .dataset-card").forEach((panel) => {
      const parsed = parseDelimitedText(qs(".dataset-textarea", panel).value);
      renderSimplePreview(qs(".dataset-preview", panel), parsed.pressure, parsed.loading);
    });
    const result = await fetchJson("/api/qst", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.results.qst = result;
    const tbody = qs("#qst-table");
    tbody.innerHTML = "";
    result.table.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${formatNumber(row.loading_mmol_g, 5)}</td>
        <td>${formatNumber(row.qst_kj_mol, 5)}</td>
        <td>${row.linearity_r2 !== undefined ? formatNumber(row.linearity_r2, 5) : "Virial fit"}</td>
      `;
      tbody.appendChild(tr);
    });
    makePlot("qst-plot", [
      { x: result.curve.x, y: result.curve.y, mode: "lines+markers", name: "Qst" },
    ], {
      title: `${result.method} Qst`,
      xaxis: { title: "Loading (mmol/g)" },
      yaxis: { title: "Qst (kJ/mol)" },
    }, "qst");
    if (result.fit_traces) {
      const traces = result.fit_traces.flatMap((item) => [
        { x: item.data.x, y: item.data.y, mode: "markers", name: `${item.temperature} K data` },
        { x: item.fit.x, y: item.fit.y, mode: "lines", name: `${item.temperature} K fit` },
      ]);
      makePlot("qst-fit-plot", traces, {
        title: "Pressure fit",
        xaxis: { title: "Loading (mmol/g)" },
        yaxis: { title: "Pressure (bar)" },
      }, "qst");
    } else {
      makePlot("qst-fit-plot", [], { title: "该方法不需要统一 Virial 压力拟合图。" }, "qst");
    }
    renderExplanation("qst-explanation", result.explanation);
    setStatus(status, "Qst 计算完成。", "success");
  } catch (error) {
    setStatus(status, error.message, "error");
  }
}

async function runIast() {
  const status = qs("#iast-status");
  setStatus(status, "正在运行 IAST…");
  try {
    const payload = iastPayload();
    qsa("#iast-components .dataset-card").forEach((panel) => {
      const parsed = parseDelimitedText(qs(".dataset-textarea", panel).value);
      renderSimplePreview(qs(".dataset-preview", panel), parsed.pressure, parsed.loading);
    });
    const result = await fetchJson("/api/iast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.results.iast = result;
    const keys = Object.keys(result.results[0] || {});
    qs("#iast-table-head").innerHTML = `<tr>${keys.map((key) => `<th>${key}</th>`).join("")}</tr>`;
    const body = qs("#iast-table");
    body.innerHTML = "";
    result.results.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = keys.map((key) => `<td>${formatNumber(row[key], 6)}</td>`).join("");
      body.appendChild(tr);
    });
    if (result.selectivity_curve.y.length) {
      makePlot("iast-selectivity-plot", [
        { x: result.selectivity_curve.x, y: result.selectivity_curve.y, mode: "lines+markers", name: "Selectivity" },
      ], {
        title: "IAST selectivity",
        xaxis: { title: "Total pressure (bar)" },
        yaxis: { title: "Selectivity" },
      }, "iast");
    } else {
      makePlot("iast-selectivity-plot", [], { title: "当前选择性图仅对二元体系输出。" }, "iast");
    }
    makePlot("iast-uptake-plot", result.uptake_curves.map((curve) => ({
      x: curve.x,
      y: curve.y,
      mode: "lines+markers",
      name: curve.label,
    })), {
      title: "Component uptake",
      xaxis: { title: "Total pressure (bar)" },
      yaxis: { title: "Loading (mmol/g)" },
    }, "iast");
    const extra = result.components?.length
      ? `<h5>纯组分拟合</h5><ul>${result.components.map((component) => `<li>${component.label}: ${component.model}</li>`).join("")}</ul>`
      : "";
    renderExplanation("iast-explanation", result.explanation, extra);
    setStatus(status, "IAST 计算完成。", "success");
  } catch (error) {
    setStatus(status, error.message, "error");
  }
}

async function runBet(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = qs("#bet-status");
  setStatus(status, "正在计算 BET 与 PSD…");
  try {
    const parsed = parseDelimitedText(form.rawData.value);
    renderSimplePreview(qs("#bet-preview"), parsed.pressure, parsed.loading);
    const payload = {
      adsorbate: form.adsorbate.value,
      temperature: Number(form.temperature.value),
      pressureUnit: form.pressureUnit.value,
      loadingUnit: form.loadingUnit.value,
      branch: form.branch.value,
      thicknessModel: form.thicknessModel.value,
      psdMode: form.psdMode.value,
      poreFamily: form.poreFamily.value,
      classicalModel: form.classicalModel.value,
      microGeometry: form.microGeometry.value,
      mesoGeometry: form.mesoGeometry.value,
      meniscusGeometry: form.meniscusGeometry.value,
      mesoBranch: form.mesoBranch.value,
      dftKernel: form.dftKernel.value,
      customKernelPath: form.customKernelPath.value.trim(),
      pressure: parsed.pressure,
      loading: parsed.loading,
    };
    const result = await fetchJson("/api/bet-psd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.results.bet = result;
    qs("#bet-area").textContent = `${formatNumber(result.bet.area_m2_g, 4)} m²/g`;
    qs("#bet-c").textContent = formatNumber(result.bet.c_const, 4);
    qs("#bet-r2").textContent = formatNumber(result.bet.r2, 5);
    qs("#bet-avg-pore").textContent = result.tplot.selected_average_pore_diameter_nm ? `${formatNumber(result.tplot.selected_average_pore_diameter_nm, 4)} nm` : "—";
    makePlot("bet-plot", [
      { x: result.bet.plot.x, y: result.bet.plot.y, mode: "markers", name: "BET plot" },
    ], {
      title: "BET linearization",
      xaxis: { title: "p/p0" },
      yaxis: { title: "p / n(1 - p/p0)" },
    }, "bet");
    const psdTraces = [];
    if (result.classical_psd) {
      psdTraces.push({
        x: result.classical_psd.pore_widths_nm,
        y: result.classical_psd.distribution,
        mode: "lines",
        name: result.classical_psd.model,
      });
    }
    if (result.dft_psd) {
      psdTraces.push({
        x: result.dft_psd.pore_widths_nm,
        y: result.dft_psd.distribution,
        mode: "lines",
        name: result.dft_psd.kernel,
        line: { dash: "dot" },
      });
    }
    makePlot("psd-plot", psdTraces, {
      title: result.psd_mode === "dft" ? "NLDFT pore size distribution" : "Classical pore size distribution",
      xaxis: { title: "Pore width (nm)" },
      yaxis: { title: "Distribution" },
    }, "bet");
    const summaryRows = [
      ["BET area (m²/g)", result.bet.area_m2_g],
      ["BET C", result.bet.c_const],
      ["BET R²", result.bet.r2],
      ["Monolayer loading (mmol/g)", result.bet.n_monolayer_mmol_g],
      ["BET window", (result.bet.p_limits || []).join(" - ")],
      ["经典 PSD 峰位 (nm)", result.classical_psd?.peak_pore_width_nm],
      ["NLDFT 峰位 (nm)", result.dft_psd?.peak_pore_width_nm],
      ["平均孔径 (nm)", result.tplot.selected_average_pore_diameter_nm],
    ];
    const tbody = qs("#bet-summary-table");
    tbody.innerHTML = "";
    summaryRows.forEach(([label, value]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${label}</td><td>${typeof value === "string" ? value : formatNumber(value, 6)}</td>`;
      tbody.appendChild(tr);
    });
    const warnings = qs("#bet-warnings");
    warnings.innerHTML = "";
    (result.warnings || []).forEach((warning) => {
      const li = document.createElement("li");
      li.textContent = warning;
      warnings.appendChild(li);
    });
    renderExplanation("bet-explanation", result.explanation, result.psd_mode === "dft"
      ? "<p>本次输出的是 NLDFT 模式结果；经典 PSD 未同时计算。</p>"
      : "<p>本次输出的是经典 PSD 模式结果；NLDFT 未同时计算。</p>");
    setStatus(status, "BET / PSD 计算完成。", "success");
  } catch (error) {
    setStatus(status, error.message, "error");
  }
}

function syncBetTemperature() {
  const form = qs("#bet-form");
  form.adsorbate.addEventListener("change", () => {
    const map = { nitrogen: 77, argon: 87, "carbon dioxide": 273 };
    form.temperature.value = map[form.adsorbate.value];
    updatePsdControls();
  });
}

function updatePsdControls() {
  const form = qs("#bet-form");
  const mode = form.psdMode.value;
  const family = form.poreFamily.value;
  const isClassical = mode === "classical";
  form.classicalModel.disabled = !isClassical;
  form.poreFamily.disabled = !isClassical;
  form.microGeometry.disabled = !isClassical || family !== "micro";
  form.mesoGeometry.disabled = !isClassical || family !== "meso";
  form.meniscusGeometry.disabled = !isClassical || family !== "meso";
  form.mesoBranch.disabled = !isClassical || family !== "meso";
  form.dftKernel.disabled = isClassical;
  form.customKernelPath.disabled = isClassical;
}

function syncClassicalModels() {
  const familySelect = qs("#pore-family-select");
  const modelSelect = qs("#classical-model-select");
  const sync = () => {
    const options = familySelect.value === "micro"
      ? [["HK", "HK"], ["SF", "SF"], ["RY", "RY"], ["RY-CY", "RY-CY"], ["HK-CY", "HK-CY"]]
      : [["BJH", "BJH"], ["DH", "DH"], ["pygaps-DH", "pygaps-DH"]];
    modelSelect.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
    updatePsdControls();
  };
  familySelect.addEventListener("change", sync);
  qs("#psd-mode-select").addEventListener("change", updatePsdControls);
  sync();
}

function rerenderIfPossible(scope) {
  Object.entries(state.plotRegistry)
    .filter(([, definition]) => definition.scope === scope)
    .forEach(([plotId]) => renderRegisteredPlot(plotId));
}

function initStylePanels() {
  qsa(".plot-style-panel").forEach((panel) => {
    ensureStylePanelChrome(panel);
    ensureTraceEditor(panel);
    panel.addEventListener("change", (event) => {
      if (event.target.closest(".trace-style-shell")) return;
      rerenderIfPossible(panel.dataset.styleScope);
    });
    panel.addEventListener("input", (event) => {
      if (event.target.closest(".trace-style-shell")) return;
      rerenderIfPossible(panel.dataset.styleScope);
    });
  });
}

function initHomeRouting() {
  qsa(".route-tab, .jump-button").forEach((button) => {
    button.addEventListener("click", () => activateRoute(button.dataset.routeTarget));
  });
}

function initRootFileImport(target, inputId, formSelector) {
  qs(`.parse-file-button[data-target="${target}"]`)?.addEventListener("click", async () => {
    const file = qs(inputId).files?.[0];
    if (!file) return;
    try {
      await openImportDialog(file, qs(formSelector));
    } catch (error) {
      reportImportError(qs(formSelector), error.message);
    }
  });
}

function initSampleButtons() {
  qsa(".sample-button").forEach((button) => {
    button.addEventListener("click", () => {
      const type = button.dataset.sample;
      if (type === "isotherm") {
        qs("#isotherm-form textarea").value = samples.isotherm;
        previewRootDataset("isotherm");
      }
      if (type === "qst") {
        qs("#qst-datasets").innerHTML = "";
        samples.qst.forEach((item) => addQstDataset(item));
      }
      if (type === "iast") {
        qs("#iast-components").innerHTML = "";
        samples.iast.forEach((item) => addIastComponent(item));
      }
      if (type === "bet") {
        qs("#bet-form textarea").value = samples.bet;
        previewRootDataset("bet");
      }
    });
  });
}

function initPreviewButtons() {
  qsa(".preview-button").forEach((button) => {
    button.addEventListener("click", () => previewRootDataset(button.dataset.target));
  });
}

function initCopyButtons() {
  qsa(".copy-table-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await copyTableBody(button.dataset.copyTarget);
    });
  });
}

function initExportButtons() {
  qsa(".export-csv-button").forEach((button) => {
    button.addEventListener("click", () => exportModuleCsv(button.dataset.module));
  });
  qsa(".export-json-button").forEach((button) => {
    button.addEventListener("click", () => exportModuleJson(button.dataset.module));
  });
}

function initImportDialog() {
  qs("#import-close")?.addEventListener("click", closeImportDialog);
  qs("#import-cancel")?.addEventListener("click", closeImportDialog);
  qs("#import-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "import-modal") closeImportDialog();
  });
  qs("#import-sheet")?.addEventListener("change", async (event) => {
    await refreshImportSheet(event.currentTarget.value);
  });
  ["#import-pressure-column", "#import-loading-column"].forEach((selector) => {
    qs(selector)?.addEventListener("change", updateImportPreview);
  });
  ["#import-pressure-unit", "#import-loading-unit"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => {
      const modal = qs("#import-modal");
      modal.dataset.unitsLocked = "1";
      updateImportPreview();
    });
  });
  qs("#import-confirm")?.addEventListener("click", () => {
    const session = state.importSession;
    if (!session?.parsed || !session.panel) return;
    try {
      const confirmed = buildConfirmedImport(
        session.parsed,
        qs("#import-pressure-column").value,
        qs("#import-loading-column").value,
        qs("#import-pressure-unit").value,
        qs("#import-loading-unit").value,
      );
      populateTextareaFromParsed(session.panel, confirmed);
      closeImportDialog();
    } catch (error) {
      window.alert(error.message);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initHomeRouting();
  initImportDialog();
  initRootFileImport("isotherm", "#isotherm-file", "#isotherm-form");
  initRootFileImport("bet", "#bet-file", "#bet-form");
  initSampleButtons();
  initPreviewButtons();
  initCopyButtons();
  initExportButtons();
  initStylePanels();
  syncBetTemperature();
  syncClassicalModels();
  updatePsdControls();

  qs("#adsorbate-search-button").addEventListener("click", () => loadAdsorbates(qs("#adsorbate-search").value));
  qs("#adsorbate-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadAdsorbates(event.currentTarget.value);
  });

  qs("#isotherm-form").addEventListener("submit", runIsotherm);
  qs("#run-qst").addEventListener("click", runQst);
  qs("#run-iast").addEventListener("click", runIast);
  qs("#bet-form").addEventListener("submit", runBet);
  qs("#add-qst-dataset").addEventListener("click", () => addQstDataset());
  qs("#add-iast-component").addEventListener("click", () => addIastComponent());

  addQstDataset({ temperature: 298.15 });
  addQstDataset({ temperature: 308.15 });
  addIastComponent({ label: "CO2", adsorbate: "carbon dioxide", model: "Dual-site Langmuir" });
  addIastComponent({ label: "N2", adsorbate: "nitrogen", model: "Langmuir" });

  await loadAdsorbates();
});
