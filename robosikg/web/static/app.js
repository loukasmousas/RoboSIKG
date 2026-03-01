const dom = {
  chipStream: document.getElementById("chipStream"),
  chipRtt: document.getElementById("chipRtt"),
  chipFps: document.getElementById("chipFps"),
  workspaceSelect: document.getElementById("workspaceSelect"),
  pauseBtn: document.getElementById("pauseBtn"),
  resetBtn: document.getElementById("resetBtn"),
  recordBtn: document.getElementById("recordBtn"),
  menuBtn: document.getElementById("menuBtn"),
  railPerceptionBtn: document.getElementById("railPerceptionBtn"),
  railReasoningBtn: document.getElementById("railReasoningBtn"),
  railWarehouseBtn: document.getElementById("railWarehouseBtn"),
  railGraphBtn: document.getElementById("railGraphBtn"),
  railPolicyBtn: document.getElementById("railPolicyBtn"),
  railSettingsBtn: document.getElementById("railSettingsBtn"),
  runSelect: document.getElementById("runSelect"),
  runBtn: document.getElementById("runBtn"),
  runStateBadge: document.getElementById("runStateBadge"),
  eventFeed: document.getElementById("eventFeed"),
  chatThread: document.getElementById("chatThread"),
  graphCanvas: document.getElementById("graphCanvas"),
  graphEmpty: document.getElementById("graphEmpty"),
  graphFilters: document.getElementById("graphFilters"),
  metricFrames: document.getElementById("metricFrames"),
  metricRegions: document.getElementById("metricRegions"),
  metricVectors: document.getElementById("metricVectors"),
  metricNodes: document.getElementById("metricNodes"),
  metricEdges: document.getElementById("metricEdges"),
  perfEffectiveFps: document.getElementById("perfEffectiveFps"),
  perfDetector: document.getElementById("perfDetector"),
  perfEmbedder: document.getElementById("perfEmbedder"),
  perfReasoning: document.getElementById("perfReasoning"),
  perfIO: document.getElementById("perfIO"),
  perfReasonInvocations: document.getElementById("perfReasonInvocations"),
  scrubProgress: document.getElementById("scrubProgress"),
  timelinePlay: document.getElementById("timelinePlay"),
  timelineStep: document.getElementById("timelineStep"),
  timelineFullscreen: document.getElementById("timelineFullscreen"),
  exportBtn: document.getElementById("exportBtn"),
  overlaysBtn: document.getElementById("overlaysBtn"),
  layerTimelineBtn: document.getElementById("layerTimelineBtn"),
  layerBoxesBtn: document.getElementById("layerBoxesBtn"),
  layerMasksBtn: document.getElementById("layerMasksBtn"),
  layerTracksBtn: document.getElementById("layerTracksBtn"),
  layerLabelsBtn: document.getElementById("layerLabelsBtn"),
  moduleVisionBtn: document.getElementById("moduleVisionBtn"),
  moduleSlamBtn: document.getElementById("moduleSlamBtn"),
  moduleLlmBtn: document.getElementById("moduleLlmBtn"),
  instructionInput: document.getElementById("instructionInput"),
  nodeSummary: document.getElementById("nodeSummary"),
  nodeProps: document.getElementById("nodeProps"),
  mp4PathInput: document.getElementById("mp4PathInput"),
  sourceIdInput: document.getElementById("sourceIdInput"),
  reasoningModeInput: document.getElementById("reasoningModeInput"),
  deviceInput: document.getElementById("deviceInput"),
  pretrainedInput: document.getElementById("pretrainedInput"),
  sampleFpsInput: document.getElementById("sampleFpsInput"),
  maxFramesInput: document.getElementById("maxFramesInput"),
  reasonEveryInput: document.getElementById("reasonEveryInput"),
  uploadBtn: document.getElementById("uploadBtn"),
  uploadInput: document.getElementById("uploadInput"),
  layoutBtn: document.getElementById("layoutBtn"),
  refreshGraphBtn: document.getElementById("refreshGraphBtn"),
  copyQueryBtn: document.getElementById("copyQueryBtn"),
  clearSparqlFocusBtn: document.getElementById("clearSparqlFocusBtn"),
  runQueryBtn: document.getElementById("runQueryBtn"),
  sparqlEditor: document.getElementById("sparqlEditor"),
  overlayMode: document.getElementById("overlayMode"),
  overlayDevice: document.getElementById("overlayDevice"),
  videoOverlay: document.getElementById("videoOverlay"),
  videoPreview: document.getElementById("videoPreview"),
  videoLayerCanvas: document.getElementById("videoLayerCanvas"),
  videoStage: document.getElementById("videoStage"),
  perceptionPanel: document.querySelector(".perception-panel"),
  graphPanel: document.querySelector(".graph-panel"),
  graphSection: document.querySelector(".graph-section"),
  instructionPanel: document.querySelector(".instruction-panel"),
  chatPanel: document.querySelector(".chat-panel"),
  inspectorPanel: document.querySelector(".inspector-panel"),
};

const state = {
  ws: null,
  reconnectTimer: null,
  pingTimer: null,
  startedAtMs: null,
  runs: [],
  selectedRunId: null,
  running: false,
  paused: false,
  recording: false,
  recordingPath: null,
  activeConfig: {
    max_frames: Number(dom.maxFramesInput.value) || 1,
  },
  console: {
    workspace: "default",
    rail: "Perception",
    overlays_visible: true,
    layers: {
      timeline: true,
      boxes: false,
      masks: false,
      tracks: false,
      labels: false,
    },
    modules: {
      vision: true,
      slam: true,
      llm: true,
    },
    menu_open: false,
  },
  graph: {
    nodes: [],
    edges: [],
    positions: new Map(),
    hiddenGroups: new Set(),
    filters: [],
    selectedNodeId: null,
    hitboxes: [],
    inspectorRequestSeq: 0,
    queryNodeIds: null,
  },
  metrics: {
    frames_seen: 0,
    regions_added: 0,
    vector_items: 0,
  },
  overlay: {
    sourceWidth: 0,
    sourceHeight: 0,
    frameIndex: null,
    boxes: [],
    tracks: [],
    trajectory: [],
    trackTrails: new Map(),
    historyByRun: new Map(),
    historyRunId: null,
    historySampleFps: 5,
    fullscreenHintShown: false,
    promotingFullscreen: false,
    nativeFsCandidate: false,
    queryFocus: null,
  },
  chatFilter: {
    frameUris: null,
    entityUris: null,
  },
  perf: {
    effectiveFps: null,
    detectorMsPerFrame: null,
    embeddingMsPerFrame: null,
    reasoningMsPerInvocation: null,
    ioMsPerFrame: null,
    reasoningInvocations: null,
  },
};

function bindEvent(el, eventName, handler) {
  if (!el) return;
  el.addEventListener(eventName, handler);
  if (el instanceof HTMLElement) {
    el.dataset.wired = "1";
  }
}

function bindButton(el, handler) {
  bindEvent(el, "click", handler);
}

const PALETTE = (() => {
  const css = getComputedStyle(document.documentElement);
  return {
    border: css.getPropertyValue("--border").trim(),
    textPrimary: css.getPropertyValue("--text-primary").trim(),
    textSecondary: css.getPropertyValue("--text-secondary").trim(),
    cyan: css.getPropertyValue("--cyan").trim(),
    green: css.getPropertyValue("--green").trim(),
    amber: css.getPropertyValue("--amber").trim(),
    red: css.getPropertyValue("--red").trim(),
    purple: css.getPropertyValue("--purple").trim(),
  };
})();

function groupColor(group) {
  const g = String(group || "").toLowerCase();
  if (g.includes("track")) return PALETTE.green;
  if (g.includes("hazard")) return PALETTE.red;
  if (g.includes("region")) return PALETTE.cyan;
  if (g.includes("policy")) return PALETTE.purple;
  if (g.includes("frame")) return PALETTE.amber;
  return PALETTE.textSecondary;
}

async function apiJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

async function postConsoleAction(action, payload = {}) {
  return apiJSON("/api/console/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, payload }),
  });
}

function clip(text, max = 120) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

function deriveSourceIdFromPath(path) {
  const raw = String(path || "").trim();
  const filename = raw.split("/").pop() || "";
  const stem = filename.replace(/\.[^.]+$/, "") || "web_demo";
  const normalized = stem.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "");
  return normalized || "web_demo";
}

function maybeAutofillSourceIdFromPath(path) {
  if (!dom.sourceIdInput) return;
  const current = String(dom.sourceIdInput.value || "").trim().toLowerCase();
  if (current && current !== "auto") return;
  dom.sourceIdInput.value = deriveSourceIdFromPath(path);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isIriLike(value) {
  return typeof value === "string" && /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value);
}

function shortUri(value) {
  const text = String(value || "");
  if (text.startsWith("urn:sha256:")) {
    return `#${text.slice(11, 21)}`;
  }
  if (text.includes("#")) {
    return text.split("#").pop() || text;
  }
  if (text.includes("/")) {
    return text.split("/").pop() || text;
  }
  return text;
}

function localName(value) {
  const text = String(value || "");
  if (text.includes("#")) return text.split("#").pop() || text;
  if (text.includes("/")) return text.split("/").pop() || text;
  return text;
}

function formatInspectorValue(value, maxLen = 160) {
  const text = String(value ?? "");
  return clip(text, maxLen);
}

function sparqlIri(value) {
  const text = String(value || "").trim();
  if (!text) throw new Error("Empty IRI");
  return `<${text.replaceAll("\\", "\\\\").replaceAll(">", "\\>")}>`;
}

function rowsToObjects(payload) {
  const columns = Array.isArray(payload?.columns) ? payload.columns : [];
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  return rows.map((cells) => {
    const row = {};
    columns.forEach((col, idx) => {
      row[col] = cells[idx] ?? "";
    });
    return row;
  });
}

async function runInspectorQuery(runId, query, limit = 120) {
  const out = await apiJSON("/api/sparql/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, query, limit }),
  });
  return rowsToObjects(out);
}

function ts() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setPill(btn, enabled) {
  if (!btn) return;
  btn.classList.toggle("active", Boolean(enabled));
}

function setRailActive(railName) {
  const mapping = {
    Perception: dom.railPerceptionBtn,
    Reasoning: dom.railReasoningBtn,
    Warehouse: dom.railWarehouseBtn,
    Graph: dom.railGraphBtn,
    Policy: dom.railPolicyBtn,
    Settings: dom.railSettingsBtn,
  };
  Object.values(mapping).forEach((btn) => btn && btn.classList.remove("active"));
  const target = mapping[railName] || dom.railPerceptionBtn;
  if (target) target.classList.add("active");
}

function syncConsoleState(consoleState) {
  if (!consoleState || typeof consoleState !== "object") return;
  state.console = {
    ...state.console,
    ...consoleState,
    layers: { ...state.console.layers, ...(consoleState.layers || {}) },
    modules: { ...state.console.modules, ...(consoleState.modules || {}) },
  };
  state.paused = Boolean(consoleState.run_paused);
  state.recording = Boolean(consoleState.recording);
  state.recordingPath = consoleState.recording_path || null;

  if (dom.workspaceSelect && consoleState.workspace) {
    dom.workspaceSelect.value = consoleState.workspace;
  }
  if (dom.instructionInput && consoleState.instruction && document.activeElement !== dom.instructionInput) {
    dom.instructionInput.value = consoleState.instruction;
  }
  setRailActive(state.console.rail);
  applyRailFocus(state.console.rail);
  setPill(dom.layerTimelineBtn, state.console.layers.timeline);
  setPill(dom.layerBoxesBtn, state.console.layers.boxes);
  setPill(dom.layerMasksBtn, state.console.layers.masks);
  setPill(dom.layerTracksBtn, state.console.layers.tracks);
  setPill(dom.layerLabelsBtn, state.console.layers.labels);
  setPill(dom.moduleVisionBtn, state.console.modules.vision);
  setPill(dom.moduleSlamBtn, state.console.modules.slam);
  setPill(dom.moduleLlmBtn, state.console.modules.llm);

  if (dom.videoOverlay) {
    dom.videoOverlay.style.display = state.console.overlays_visible ? "flex" : "none";
  }
  if (dom.menuBtn) {
    dom.menuBtn.textContent = state.console.menu_open ? "Close" : "•••";
  }
  drawVideoLayers();
  if (dom.pauseBtn) {
    dom.pauseBtn.textContent = state.paused ? "Resume" : "Pause";
  }
  if (dom.recordBtn) {
    dom.recordBtn.textContent = state.recording ? "Stop Rec" : "Record";
  }
}

function applyRailFocus(railName) {
  const panels = [dom.perceptionPanel, dom.graphPanel, dom.instructionPanel, dom.chatPanel, dom.inspectorPanel];
  panels.forEach((panel) => panel && panel.classList.remove("focused"));
  const mapping = {
    Perception: dom.perceptionPanel,
    Reasoning: dom.chatPanel,
    Warehouse: dom.instructionPanel,
    Graph: dom.graphPanel,
    Policy: dom.inspectorPanel,
    Settings: dom.instructionPanel,
  };
  const target = mapping[railName];
  if (!target) return;
  target.classList.add("focused");

  const visibility = {
    Perception: [dom.perceptionPanel, dom.graphSection, dom.instructionPanel, dom.chatPanel, dom.inspectorPanel],
    Reasoning: [dom.perceptionPanel, dom.chatPanel, dom.inspectorPanel],
    Warehouse: [dom.perceptionPanel, dom.instructionPanel],
    Graph: [dom.graphSection, dom.inspectorPanel],
    Policy: [dom.graphSection, dom.inspectorPanel, dom.chatPanel],
    Settings: [dom.instructionPanel],
  };
  const allSections = [dom.perceptionPanel, dom.graphSection, dom.instructionPanel, dom.chatPanel, dom.inspectorPanel];
  const visibleSet = new Set((visibility[railName] || visibility.Perception).filter(Boolean));
  allSections.forEach((el) => {
    if (!el) return;
    el.classList.toggle("is-hidden", !visibleSet.has(el));
  });

  if (window.innerWidth <= 1180) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function setRunState(stateName, detail = "") {
  const normalized = stateName || "idle";
  dom.runStateBadge.textContent = normalized;
  dom.runStateBadge.className = `badge ${
    normalized === "failed" ? "failed" : normalized === "running" || normalized === "starting" ? "running" : normalized
  }`;

  if (normalized === "running" || normalized === "starting") {
    if (state.startedAtMs === null) {
      state.startedAtMs = performance.now();
    }
    dom.chipStream.textContent = "Streaming";
  } else if (normalized === "paused") {
    dom.chipStream.textContent = "Paused";
    state.paused = true;
  } else if (normalized === "failed") {
    dom.chipStream.textContent = "Error";
    state.startedAtMs = null;
  } else if (normalized === "completed" || normalized === "stopped") {
    dom.chipStream.textContent = normalized === "stopped" ? "Stopped" : "Idle";
    state.startedAtMs = null;
  } else {
    dom.chipStream.textContent = "Idle";
    state.startedAtMs = null;
  }
  if (dom.pauseBtn) {
    dom.pauseBtn.textContent = normalized === "paused" ? "Resume" : "Pause";
  }

  if (detail) {
    pushEvent(`Run ${normalized}: ${clip(detail, 110)}`, "system");
  }
}

function pushEvent(message, kind = "event", meta = "") {
  const li = document.createElement("li");
  li.innerHTML = `
    <div class="event-title">${message}</div>
    <div class="event-meta">${meta || ts()} · ${kind}</div>
  `;
  dom.eventFeed.prepend(li);
  while (dom.eventFeed.children.length > 80) {
    dom.eventFeed.removeChild(dom.eventFeed.lastChild);
  }
}

function pushChat(role, body, timestamp = ts(), meta = {}) {
  const row = document.createElement("div");
  row.className = "chat-row";
  row.dataset.chatRole = String(role || "");
  if (meta && typeof meta === "object") {
    if (meta.frameUri) row.dataset.frameUri = String(meta.frameUri);
    if (Array.isArray(meta.entityUris) && meta.entityUris.length) {
      row.dataset.entityUris = meta.entityUris.map((v) => String(v)).join("|");
    }
  }
  row.innerHTML = `
    <div class="chat-meta">
      <span class="chat-role">${role}</span>
      <span>${timestamp}</span>
    </div>
    <div class="chat-body">${body}</div>
  `;
  dom.chatThread.prepend(row);
  while (dom.chatThread.children.length > 120) {
    dom.chatThread.removeChild(dom.chatThread.lastChild);
  }
  applyChatFilter(state.chatFilter.frameUris, state.chatFilter.entityUris);
}

function intersectsAny(haystackValues, needleSet) {
  if (!needleSet || !needleSet.size) return true;
  for (const val of haystackValues) {
    if (needleSet.has(val)) return true;
  }
  return false;
}

function applyChatFilter(frameUris, entityUris) {
  state.chatFilter.frameUris = frameUris && frameUris.size ? frameUris : null;
  state.chatFilter.entityUris = entityUris && entityUris.size ? entityUris : null;
  const hasFrameFilter = Boolean(state.chatFilter.frameUris && state.chatFilter.frameUris.size);
  const hasEntityFilter = Boolean(state.chatFilter.entityUris && state.chatFilter.entityUris.size);

  const rows = dom.chatThread ? [...dom.chatThread.children] : [];
  for (const row of rows) {
    const role = row.dataset.chatRole || "";
    if (!hasFrameFilter && !hasEntityFilter) {
      row.classList.remove("is-hidden");
      continue;
    }
    if (role === "query") {
      row.classList.remove("is-hidden");
      continue;
    }

    const rowFrame = row.dataset.frameUri || "";
    const rowEntityUris = String(row.dataset.entityUris || "")
      .split("|")
      .map((v) => v.trim())
      .filter(Boolean);

    let visible = true;
    if (hasFrameFilter) {
      visible = Boolean(rowFrame && state.chatFilter.frameUris.has(rowFrame));
    }
    if (visible && hasEntityFilter && rowEntityUris.length) {
      visible = intersectsAny(rowEntityUris, state.chatFilter.entityUris);
    }
    row.classList.toggle("is-hidden", !visible);
  }
}

function updateMetrics(patch) {
  state.metrics = { ...state.metrics, ...patch };
  dom.metricFrames.textContent = String(state.metrics.frames_seen ?? 0);
  dom.metricRegions.textContent = String(state.metrics.regions_added ?? 0);
  dom.metricVectors.textContent = String(state.metrics.vector_items ?? 0);
  if (state.startedAtMs !== null && state.running) {
    const elapsedS = Math.max(0.001, (performance.now() - state.startedAtMs) / 1000);
    dom.chipFps.textContent = (Number(state.metrics.frames_seen || 0) / elapsedS).toFixed(2);
  }
}

function formatPerfValue(value, suffix = "") {
  if (!Number.isFinite(Number(value))) return "--";
  return `${Number(value).toFixed(2)}${suffix}`;
}

function updatePerfPanel(patch = {}) {
  state.perf = { ...state.perf, ...patch };
  if (dom.perfEffectiveFps) dom.perfEffectiveFps.textContent = formatPerfValue(state.perf.effectiveFps);
  if (dom.perfDetector) dom.perfDetector.textContent = formatPerfValue(state.perf.detectorMsPerFrame, " ms/f");
  if (dom.perfEmbedder) dom.perfEmbedder.textContent = formatPerfValue(state.perf.embeddingMsPerFrame, " ms/f");
  if (dom.perfReasoning) dom.perfReasoning.textContent = formatPerfValue(state.perf.reasoningMsPerInvocation, " ms/call");
  if (dom.perfIO) dom.perfIO.textContent = formatPerfValue(state.perf.ioMsPerFrame, " ms/f");
  if (dom.perfReasonInvocations) {
    dom.perfReasonInvocations.textContent = Number.isFinite(Number(state.perf.reasoningInvocations))
      ? String(Math.round(Number(state.perf.reasoningInvocations)))
      : "--";
  }
}

function applyPerfFromSummary(summary) {
  const elapsedS = Number(summary?.timing?.elapsed_s);
  const effectiveFps = Number(summary?.timing?.effective_fps);
  const counts = summary?.counts || {};
  const stages = summary?.timing?.stages_s || {};
  const framesSeen = Number(counts.frames_seen || 0);
  const reasonCalls = Number(counts.reasoning_invocations || 0);

  const detectorMsPerFrame = framesSeen > 0 ? (1000 * Number(stages.detector_s || 0)) / framesSeen : NaN;
  const embeddingMsPerFrame = framesSeen > 0 ? (1000 * Number(stages.embedding_s || 0)) / framesSeen : NaN;
  const reasoningMsPerInvocation = reasonCalls > 0 ? (1000 * Number(stages.reasoning_s || 0)) / reasonCalls : NaN;
  const ioMsPerFrame = framesSeen > 0 ? (1000 * Number(stages.io_s || 0)) / framesSeen : NaN;

  updatePerfPanel({
    effectiveFps: Number.isFinite(effectiveFps) ? effectiveFps : framesSeen > 0 && elapsedS > 0 ? framesSeen / elapsedS : NaN,
    detectorMsPerFrame,
    embeddingMsPerFrame,
    reasoningMsPerInvocation,
    ioMsPerFrame,
    reasoningInvocations: reasonCalls,
  });
}

function updateScrub(framesSeen = 0) {
  const maxFrames = Math.max(1, Number(state.activeConfig.max_frames) || 1);
  const pct = Math.min(100, (framesSeen / maxFrames) * 100);
  dom.scrubProgress.style.width = `${pct.toFixed(2)}%`;
}

function setVideoFromPath(path) {
  const p = String(path || "").trim();
  if (!p || !/\.mp4$/i.test(p)) {
    dom.videoPreview.removeAttribute("src");
    dom.videoPreview.load();
    dom.videoStage.classList.remove("has-video");
    return;
  }
  const filename = p.split("/").pop();
  if (!filename) return;
  dom.videoPreview.src = `/media/${encodeURIComponent(filename)}`;
  dom.videoStage.classList.add("has-video");
  clearVideoLayers();
  maybeAutofillSourceIdFromPath(p);
}

function videoFilenameFromPath(path) {
  const p = String(path || "").trim();
  if (!p || !/\.mp4$/i.test(p)) return null;
  const filename = p.split("/").pop();
  return filename || null;
}

async function mediaPathExists(path) {
  const filename = videoFilenameFromPath(path);
  if (!filename) return false;
  try {
    const res = await fetch(`/media/${encodeURIComponent(filename)}`, { method: "HEAD" });
    return Boolean(res.ok);
  } catch (_err) {
    return false;
  }
}

function collectRunVideoCandidates(runId, summary) {
  const candidates = [
    summary?.input_mp4_path,
    summary?.mp4_path,
    summary?.input?.mp4_path,
    summary?.config?.input?.mp4_path,
    summary?.config?.ingest?.mp4_path,
    summary?.config?.mp4_path,
  ];

  const rid = String(runId || "");
  if (rid.startsWith("out_")) {
    const stem = rid.slice(4);
    if (stem && !stem.startsWith("web_")) {
      candidates.push(`data/scratch/${stem}.mp4`);
      const firstToken = stem.split("_")[0];
      if (firstToken && firstToken !== stem) {
        candidates.push(`data/scratch/${firstToken}.mp4`);
      }
    }
  }

  const out = [];
  const seen = new Set();
  for (const row of candidates) {
    const p = String(row || "").trim();
    if (!/\.mp4$/i.test(p)) continue;
    if (seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  return out;
}

async function resolveRunVideoPath(runId, summary) {
  const candidates = collectRunVideoCandidates(runId, summary);
  if (!candidates.length) return null;
  let fallback = null;
  for (const candidate of candidates) {
    if (fallback === null) fallback = candidate;
    if (await mediaPathExists(candidate)) return candidate;
  }
  return fallback;
}

function clearVideoLayers() {
  state.overlay.frameIndex = null;
  state.overlay.boxes = [];
  state.overlay.tracks = [];
  state.overlay.trajectory = [];
  state.overlay.trackTrails = new Map();
  drawVideoLayers();
}

function toNumberOr(defaultValue, value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : defaultValue;
}

function updateOverlayFrame(evt) {
  const frameIndex = toNumberOr(state.overlay.frameIndex ?? 0, evt.frame_index);
  state.overlay.sourceWidth = toNumberOr(state.overlay.sourceWidth || dom.videoPreview.videoWidth || 0, evt.frame_width);
  state.overlay.sourceHeight = toNumberOr(state.overlay.sourceHeight || dom.videoPreview.videoHeight || 0, evt.frame_height);
  applyOverlayFrameData(frameIndex, {
    boxes: Array.isArray(evt.boxes) ? evt.boxes : [],
    tracks: Array.isArray(evt.tracks) ? evt.tracks : [],
  });
}

function applyOverlayFrameData(frameIndex, data) {
  if (frameIndex === null || frameIndex === undefined) return;
  const previousIndex = state.overlay.frameIndex;
  const normalizedFrameIndex = Number(frameIndex);
  if (!Number.isFinite(normalizedFrameIndex)) return;
  if (previousIndex !== null && Math.abs(normalizedFrameIndex - Number(previousIndex)) > 30) {
    state.overlay.trackTrails = new Map();
  }
  const boxes = Array.isArray(data?.boxes) ? data.boxes : [];
  const tracks = Array.isArray(data?.tracks) ? data.tracks : [];
  if (previousIndex !== null && Number(previousIndex) === normalizedFrameIndex) {
    state.overlay.boxes = boxes;
    state.overlay.tracks = tracks;
    drawVideoLayers();
    return;
  }
  state.overlay.frameIndex = normalizedFrameIndex;
  state.overlay.boxes = boxes;
  state.overlay.tracks = tracks;

  for (const track of tracks) {
    const id = String(track.track_id ?? "");
    if (!id || !Array.isArray(track.bbox) || track.bbox.length < 4) continue;
    const center = {
      x: (Number(track.bbox[0]) + Number(track.bbox[2])) / 2,
      y: (Number(track.bbox[1]) + Number(track.bbox[3])) / 2,
    };
    const hist = state.overlay.trackTrails.get(id) || [];
    hist.push(center);
    if (hist.length > 14) hist.shift();
    state.overlay.trackTrails.set(id, hist);
  }
  drawVideoLayers();
}

function applyTrajectoryPoints(points) {
  if (!Array.isArray(points) || !points.length) {
    state.overlay.trajectory = [];
    drawVideoLayers();
    return;
  }

  state.overlay.trajectory = points
    .map((row, idx) => {
      const point = Array.isArray(row?.point_2d) ? row.point_2d : null;
      if (!point || point.length < 2) return null;
      const x = Number(point[0]);
      const y = Number(point[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return {
        point_2d: [Math.min(1000, Math.max(0, x)), Math.min(1000, Math.max(0, y))],
        label: String(row?.label || `p${idx}`),
      };
    })
    .filter(Boolean);
  drawVideoLayers();
}

function medianFrameStep(frameKeys) {
  if (!Array.isArray(frameKeys) || frameKeys.length < 2) return 1;
  const gaps = [];
  for (let i = 1; i < frameKeys.length; i += 1) {
    const gap = Number(frameKeys[i]) - Number(frameKeys[i - 1]);
    if (Number.isFinite(gap) && gap > 0) gaps.push(gap);
  }
  if (!gaps.length) return 1;
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)];
}

function findNearestFrameAtOrBefore(sortedFrameKeys, target) {
  if (!sortedFrameKeys.length) return null;
  let lo = 0;
  let hi = sortedFrameKeys.length - 1;
  let out = sortedFrameKeys[0];
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const cur = sortedFrameKeys[mid];
    if (cur <= target) {
      out = cur;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return out;
}

function syncHistoricalOverlayForCurrentTime() {
  if (state.overlay.queryFocus && state.overlay.queryFocus.active) {
    applyOverlayFrameData(state.overlay.queryFocus.frameIndex, {
      boxes: state.overlay.queryFocus.boxes,
      tracks: state.overlay.queryFocus.tracks,
    });
    return;
  }
  if (state.running) return;
  const runId = state.overlay.historyRunId;
  if (!runId) return;
  const overlayPack = state.overlay.historyByRun.get(runId);
  if (!overlayPack) return;
  const frameKeys = overlayPack.frameKeys || [];
  if (!frameKeys.length) return;

  const sampleFps = Math.max(0.001, Number(state.overlay.historySampleFps || 5));
  const step = Math.max(1, Number(overlayPack.frameStep || 1));
  const sourceFps = Math.max(
    0.001,
    Number(overlayPack.sourceFpsGuess || sampleFps),
    step * sampleFps
  );

  const targetFrameIndex = Math.max(0, (dom.videoPreview.currentTime || 0) * sourceFps);
  const selectedFrameKey = findNearestFrameAtOrBefore(frameKeys, targetFrameIndex);
  if (selectedFrameKey === null) return;
  const data = overlayPack.frameMap.get(String(selectedFrameKey)) || { boxes: [], tracks: [] };
  applyOverlayFrameData(selectedFrameKey, data);
}

async function loadRunOverlays(runId, sampleFps) {
  if (!runId) return;
  const out = await apiJSON(`/api/runs/${encodeURIComponent(runId)}/overlays`);
  const frameObj = out.frames || {};
  const frameMap = new Map(Object.entries(frameObj));
  const frameKeys = Object.keys(frameObj)
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b);
  const sample = Math.max(0.001, Number(sampleFps || 5) || 5);
  const step = medianFrameStep(frameKeys);
  const sourceFpsGuess = Math.max(sample, step * sample);
  state.overlay.historyByRun.set(runId, {
    frameMap,
    frameKeys,
    sourceFpsGuess,
    frameStep: step,
  });
  state.overlay.historyRunId = runId;
  state.overlay.historySampleFps = sample;
  syncHistoricalOverlayForCurrentTime();
}

function canvasContext2d() {
  if (!dom.videoLayerCanvas) return null;
  return dom.videoLayerCanvas.getContext("2d");
}

function ensureVideoCanvasSize() {
  if (!dom.videoLayerCanvas || !dom.videoStage) return null;
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(dom.videoStage.clientWidth));
  const height = Math.max(1, Math.floor(dom.videoStage.clientHeight));
  dom.videoLayerCanvas.width = Math.floor(width * dpr);
  dom.videoLayerCanvas.height = Math.floor(height * dpr);
  dom.videoLayerCanvas.style.width = `${width}px`;
  dom.videoLayerCanvas.style.height = `${height}px`;
  return { width, height, dpr };
}

function videoTransform(canvasWidth, canvasHeight) {
  const srcW = state.overlay.sourceWidth || dom.videoPreview.videoWidth || canvasWidth;
  const srcH = state.overlay.sourceHeight || dom.videoPreview.videoHeight || canvasHeight;
  if (!srcW || !srcH) {
    return { scale: 1, offsetX: 0, offsetY: 0, srcW: canvasWidth, srcH: canvasHeight };
  }
  const fitMode = String(getComputedStyle(dom.videoPreview).objectFit || "contain").toLowerCase();
  const scale =
    fitMode === "cover"
      ? Math.max(canvasWidth / srcW, canvasHeight / srcH)
      : Math.min(canvasWidth / srcW, canvasHeight / srcH);
  const renderedW = srcW * scale;
  const renderedH = srcH * scale;
  const offsetX = (canvasWidth - renderedW) / 2;
  const offsetY = (canvasHeight - renderedH) / 2;
  return { scale, offsetX, offsetY, srcW, srcH };
}

function drawVideoLayers() {
  const ctx = canvasContext2d();
  const size = ensureVideoCanvasSize();
  if (!ctx || !size) return;
  const { width, height, dpr } = size;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!state.console.overlays_visible) return;

  const showBoxes = Boolean(state.console.layers.boxes);
  const showMasks = Boolean(state.console.layers.masks);
  const showTracks = Boolean(state.console.layers.tracks);
  const showLabels = Boolean(state.console.layers.labels);
  if (!showBoxes && !showMasks && !showTracks && !showLabels) return;

  const { scale, offsetX, offsetY, srcW, srcH } = videoTransform(width, height);
  const toCanvasRect = (bbox) => {
    const x1 = Number(bbox[0]) * scale + offsetX;
    const y1 = Number(bbox[1]) * scale + offsetY;
    const x2 = Number(bbox[2]) * scale + offsetX;
    const y2 = Number(bbox[3]) * scale + offsetY;
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  };
  const toCanvasPointFromNorm = (point2d) => {
    const nx = Number(point2d[0]);
    const ny = Number(point2d[1]);
    const px = (Math.min(1000, Math.max(0, nx)) / 1000) * srcW;
    const py = (Math.min(1000, Math.max(0, ny)) / 1000) * srcH;
    return {
      x: px * scale + offsetX,
      y: py * scale + offsetY,
    };
  };

  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.font = "12px Inter";

  for (const box of state.overlay.boxes) {
    if (!Array.isArray(box.bbox) || box.bbox.length < 4) continue;
    const rect = toCanvasRect(box.bbox);

    if (showMasks) {
      ctx.fillStyle = "rgba(59, 199, 245, 0.16)";
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    }
    if (showBoxes) {
      ctx.strokeStyle = "rgba(59, 199, 245, 0.95)";
      ctx.lineWidth = 2;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    }
    if (showLabels) {
      const cls = String(box.cls || "obj");
      const score = Number.isFinite(Number(box.score)) ? ` ${(Number(box.score) * 100).toFixed(0)}%` : "";
      const label = `${cls}${score}`;
      const tx = rect.x + 4;
      const ty = Math.max(14, rect.y - 6);
      const tw = ctx.measureText(label).width + 8;
      ctx.fillStyle = "rgba(10, 14, 22, 0.92)";
      ctx.fillRect(tx - 3, ty - 11, tw, 14);
      ctx.fillStyle = PALETTE.textPrimary;
      ctx.fillText(label, tx, ty);
    }
  }

  for (const tr of state.overlay.tracks) {
    if (!showTracks || !Array.isArray(tr.bbox) || tr.bbox.length < 4) continue;
    const rect = toCanvasRect(tr.bbox);
    ctx.strokeStyle = "rgba(124, 245, 140, 0.95)";
    ctx.lineWidth = 2;
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

    const centerX = rect.x + rect.w / 2;
    const centerY = rect.y + rect.h / 2;
    const trackId = String(tr.track_id ?? "?");
    const trail = state.overlay.trackTrails.get(trackId) || [];
    if (trail.length > 1) {
      ctx.beginPath();
      trail.forEach((pt, idx) => {
        const x = Number(pt.x) * scale + offsetX;
        const y = Number(pt.y) * scale + offsetY;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "rgba(124, 245, 140, 0.55)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.arc(centerX, centerY, 2.6, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(124, 245, 140, 0.95)";
    ctx.fill();

    if (showLabels) {
      const lbl = `T${trackId}${tr.cls ? ` ${tr.cls}` : ""}`;
      const tx = rect.x + 4;
      const ty = rect.y + rect.h + 14;
      ctx.fillStyle = "rgba(10, 14, 22, 0.92)";
      ctx.fillRect(tx - 3, ty - 11, ctx.measureText(lbl).width + 8, 14);
      ctx.fillStyle = PALETTE.textPrimary;
      ctx.fillText(lbl, tx, ty);
    }
  }

  if (showTracks && Array.isArray(state.overlay.trajectory) && state.overlay.trajectory.length) {
    const points = state.overlay.trajectory
      .map((row) => (Array.isArray(row?.point_2d) ? toCanvasPointFromNorm(row.point_2d) : null))
      .filter(Boolean);
    if (points.length) {
      ctx.beginPath();
      points.forEach((pt, idx) => {
        if (idx === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      });
      ctx.strokeStyle = "rgba(247, 201, 72, 0.92)";
      ctx.lineWidth = 2.4;
      ctx.stroke();

      for (let i = 0; i < points.length; i += 1) {
        const pt = points[i];
        const lbl = String(state.overlay.trajectory[i]?.label || `p${i}`);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(247, 201, 72, 0.95)";
        ctx.fill();
        if (showLabels) {
          ctx.fillStyle = "rgba(10, 14, 22, 0.92)";
          ctx.fillRect(pt.x + 5, pt.y - 13, ctx.measureText(lbl).width + 8, 14);
          ctx.fillStyle = PALETTE.textPrimary;
          ctx.fillText(lbl, pt.x + 9, pt.y - 2);
        }
      }
    }
  }
}

function toggleVideoPlayback() {
  if (!dom.videoPreview || !dom.videoPreview.src) {
    pushEvent("No video loaded for playback control", "video");
    return;
  }
  if (dom.videoPreview.paused) {
    dom.videoPreview.play().then(() => {
      pushEvent("Video playback resumed", "video");
    }).catch((err) => {
      pushChat("error", `Video playback failed: ${err.message}`);
    });
  } else {
    dom.videoPreview.pause();
    pushEvent("Video playback paused", "video");
  }
}

function stepVideo(seconds = 0.25) {
  if (!dom.videoPreview || !dom.videoPreview.src) {
    pushEvent("No video loaded for stepping", "video");
    return;
  }
  const duration = Number.isFinite(dom.videoPreview.duration) ? dom.videoPreview.duration : 0;
  const next = dom.videoPreview.currentTime + seconds;
  dom.videoPreview.currentTime = duration > 0 ? Math.min(duration, next) : Math.max(0, next);
  pushEvent(`Stepped video by ${seconds.toFixed(2)}s`, "video");
}

async function requestVideoStageFullscreen() {
  if (!dom.videoStage || typeof dom.videoStage.requestFullscreen !== "function") {
    throw new Error("Fullscreen is not supported in this browser.");
  }
  await dom.videoStage.requestFullscreen();
}

async function exitFullscreenIfNeeded() {
  if (document.fullscreenElement && typeof document.exitFullscreen === "function") {
    await document.exitFullscreen();
  }
}

function isVideoStageFullscreen() {
  return document.fullscreenElement === dom.videoStage;
}

function syncFullscreenButton() {
  if (!dom.timelineFullscreen) return;
  dom.timelineFullscreen.textContent = isVideoStageFullscreen() ? "Exit Full" : "Full";
}

function toggleVideoStageFullscreen() {
  if (isVideoStageFullscreen()) {
    exitFullscreenIfNeeded().catch((err) => {
      pushChat("error", `Exit fullscreen failed: ${err.message}`);
    });
    return;
  }
  if (document.fullscreenElement === dom.videoPreview) {
    requestVideoStageFullscreen().catch((err) => {
      pushChat("error", `Fullscreen failed: ${err.message}`);
    });
    return;
  }
  requestVideoStageFullscreen().catch((err) => {
    pushChat("error", `Fullscreen failed: ${err.message}`);
  });
}

async function promoteNativeVideoFullscreen() {
  if (state.overlay.promotingFullscreen) return;
  if (document.fullscreenElement !== dom.videoPreview) return;
  state.overlay.promotingFullscreen = true;
  try {
    await requestVideoStageFullscreen();
  } catch (_err) {
    if (!state.overlay.fullscreenHintShown) {
      state.overlay.fullscreenHintShown = true;
      pushEvent("Native video fullscreen may hide overlays. Use Full for overlay fullscreen.", "video");
    }
  } finally {
    state.overlay.promotingFullscreen = false;
    syncFullscreenButton();
    drawVideoLayers();
  }
}

function promoteNativeVideoFullscreenFromGesture() {
  if (document.fullscreenElement !== dom.videoPreview) return;
  requestVideoStageFullscreen().catch(() => {});
}

function isLikelyNativeFullscreenControlHit(ev) {
  if (!ev || !dom.videoPreview) return false;
  const rect = dom.videoPreview.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;
  const hotW = Math.max(44, rect.width * 0.06);
  const hotH = Math.max(44, rect.height * 0.12);
  return x >= rect.width - hotW && y >= rect.height - hotH;
}

function handleFullscreenChange() {
  if (document.fullscreenElement === dom.videoPreview) {
    promoteNativeVideoFullscreen().catch(() => {});
    return;
  }
  syncFullscreenButton();
  drawVideoLayers();
}

function relayoutGraph() {
  const nodes = state.graph.nodes || [];
  if (!nodes.length) {
    pushEvent("No graph loaded to relayout", "graph");
    return;
  }
  ensureCanvasSize();
  const dpr = window.devicePixelRatio || 1;
  const w = dom.graphCanvas.width / dpr;
  const h = dom.graphCanvas.height / dpr;
  state.graph.positions = buildInitialPositions(state.graph.nodes, w, h);
  relaxLayout(state.graph.nodes, state.graph.edges, state.graph.positions, w, h);
  drawGraph();
  pushEvent("Graph layout recomputed", "graph");
}

function resetDashboardView() {
  state.graph.selectedNodeId = null;
  updateNodeInspector(null);
  clearSparqlFocus(false);
  pushEvent("Dashboard selection reset", "ui");
}

async function applyConsoleAction(action, payload = {}, pushActionEvent = false) {
  const out = await postConsoleAction(action, payload);
  syncConsoleState(out.state || {});
  if (pushActionEvent && out.message) {
    pushEvent(out.message, "control");
  }
  return out;
}

function bindConsoleActionButton(btn, action, payload = {}) {
  bindButton(btn, () => {
    applyConsoleAction(action, payload).catch((err) => {
      pushChat("error", `Action ${action} failed: ${err.message}`);
    });
  });
}

function hashCode(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
  }
  return hash >>> 0;
}

function buildInitialPositions(nodes, width, height) {
  const map = new Map();
  for (const node of nodes) {
    const h = hashCode(node.id || "");
    const x = 40 + (h % Math.max(100, width - 80));
    const y = 40 + ((Math.floor(h / 997) % Math.max(100, height - 80)));
    map.set(node.id, { x, y, vx: 0, vy: 0 });
  }
  return map;
}

function relaxLayout(nodes, edges, positions, width, height) {
  const nodeIds = nodes.map((n) => n.id);
  const iterations = Math.min(90, Math.max(30, Math.floor(3000 / Math.max(1, nodes.length))));
  const repel = 2400;
  const attract = 0.006;

  for (let step = 0; step < iterations; step += 1) {
    for (let i = 0; i < nodeIds.length; i += 1) {
      const a = positions.get(nodeIds[i]);
      if (!a) continue;
      for (let j = i + 1; j < nodeIds.length; j += 1) {
        const b = positions.get(nodeIds[j]);
        if (!b) continue;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const d2 = Math.max(40, dx * dx + dy * dy);
        const f = repel / d2;
        const inv = 1 / Math.sqrt(d2);
        dx *= inv;
        dy *= inv;
        a.vx += dx * f;
        a.vy += dy * f;
        b.vx -= dx * f;
        b.vy -= dy * f;
      }
    }

    for (const edge of edges) {
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const force = (dist - 90) * attract;
      const ux = dx / dist;
      const uy = dy / dist;
      a.vx += ux * force;
      a.vy += uy * force;
      b.vx -= ux * force;
      b.vy -= uy * force;
    }

    for (const id of nodeIds) {
      const p = positions.get(id);
      if (!p) continue;
      p.vx *= 0.82;
      p.vy *= 0.82;
      p.x = Math.min(width - 26, Math.max(26, p.x + p.vx));
      p.y = Math.min(height - 20, Math.max(20, p.y + p.vy));
    }
  }
}

function visibleNodes() {
  let nodes = state.graph.nodes;
  if (state.graph.queryNodeIds && state.graph.queryNodeIds.size) {
    nodes = nodes.filter((n) => state.graph.queryNodeIds.has(n.id));
  }
  if (!state.graph.hiddenGroups.size) return nodes;
  return nodes.filter((n) => !state.graph.hiddenGroups.has(n.group));
}

function visibleEdges(nodeSet) {
  const allowed = new Set(nodeSet.map((n) => n.id));
  return state.graph.edges.filter((e) => allowed.has(e.source) && allowed.has(e.target));
}

function ensureCanvasSize() {
  const wrap = dom.graphCanvas.parentElement;
  if (!wrap) return;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(300, Math.floor(wrap.clientWidth));
  const h = Math.max(220, Math.floor(wrap.clientHeight));
  dom.graphCanvas.width = Math.floor(w * dpr);
  dom.graphCanvas.height = Math.floor(h * dpr);
  dom.graphCanvas.style.width = `${w}px`;
  dom.graphCanvas.style.height = `${h}px`;
}

function roundedRectPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h - radius);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
  ctx.lineTo(x + radius, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function drawGraph() {
  ensureCanvasSize();
  const dpr = window.devicePixelRatio || 1;
  const ctx = dom.graphCanvas.getContext("2d");
  if (!ctx) return;

  const w = dom.graphCanvas.width / dpr;
  const h = dom.graphCanvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  state.graph.hitboxes = [];

  const nodes = visibleNodes();
  const edges = visibleEdges(nodes);

  dom.metricNodes.textContent = String(nodes.length);
  dom.metricEdges.textContent = String(edges.length);

  if (!nodes.length) {
    dom.graphEmpty.style.display = "grid";
    return;
  }
  dom.graphEmpty.style.display = "none";

  if (state.graph.positions.size !== state.graph.nodes.length) {
    state.graph.positions = buildInitialPositions(state.graph.nodes, w, h);
    relaxLayout(state.graph.nodes, state.graph.edges, state.graph.positions, w, h);
  }

  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(166, 185, 220, 0.24)";
  for (const edge of edges) {
    const a = state.graph.positions.get(edge.source);
    const b = state.graph.positions.get(edge.target);
    if (!a || !b) continue;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  ctx.font = "12px Inter";
  ctx.textBaseline = "middle";

  for (const node of nodes) {
    const pos = state.graph.positions.get(node.id);
    if (!pos) continue;
    const label = clip(node.label || "node", 34);
    const padX = 10;
    const padY = 7;
    const textWidth = Math.max(28, ctx.measureText(label).width);
    const bw = textWidth + padX * 2;
    const bh = 28;
    const x = pos.x - bw / 2;
    const y = pos.y - bh / 2;
    const selected = state.graph.selectedNodeId === node.id;

    roundedRectPath(ctx, x, y, bw, bh, 8);
    ctx.fillStyle = selected ? "rgba(59, 199, 245, 0.28)" : "rgba(18, 24, 36, 0.92)";
    ctx.fill();
    ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeStyle = selected ? "rgba(59, 199, 245, 0.95)" : groupColor(node.group);
    ctx.stroke();

    ctx.fillStyle = PALETTE.textPrimary;
    ctx.fillText(label, x + padX, y + bh / 2);

    state.graph.hitboxes.push({ x, y, w: bw, h: bh, node });
  }
}

function rebuildFilters() {
  const groups = new Set(state.graph.nodes.map((n) => n.group || "Entity"));
  state.graph.filters = [...groups].sort();
  dom.graphFilters.innerHTML = "";
  for (const group of state.graph.filters) {
    const id = `filter-${group.replace(/[^a-zA-Z0-9]/g, "-")}`;
    const row = document.createElement("label");
    row.className = "filter-item";
    row.innerHTML = `
      <span>${group}</span>
      <input id="${id}" type="checkbox" ${state.graph.hiddenGroups.has(group) ? "" : "checked"}>
    `;
    const input = row.querySelector("input");
    input.addEventListener("change", () => {
      if (input.checked) {
        state.graph.hiddenGroups.delete(group);
      } else {
        state.graph.hiddenGroups.add(group);
      }
      drawGraph();
    });
    dom.graphFilters.appendChild(row);
  }
}

function renderNodeProps(rows) {
  dom.nodeProps.innerHTML = rows
    .map(
      ([key, value]) => `
        <div class="prop-row">
          <div class="prop-key">${escapeHtml(key)}</div>
          <div class="prop-value">${escapeHtml(value)}</div>
        </div>
      `
    )
    .join("");
}

function renderNodeSummary(title, meta) {
  dom.nodeSummary.innerHTML = `
    <div class="summary-title">${escapeHtml(title)}</div>
    <div class="summary-meta">${escapeHtml(meta)}</div>
  `;
}

function relationCount(relMap) {
  let total = 0;
  for (const values of relMap.values()) {
    total += values.length;
  }
  return total;
}

function summarizePredicateMix(relMap, maxPredicates = 6) {
  const rows = [...relMap.entries()].map(([pred, values]) => [pred, values.length]);
  rows.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return rows
    .slice(0, maxPredicates)
    .map(([pred, count]) => `${pred}(${count})`)
    .join(", ");
}

function summarizeRelationTargets(relMap, predicate, maxItems = 4) {
  const values = relMap.get(predicate) || [];
  if (!values.length) return "";
  const shown = values.slice(0, maxItems).map((v) => shortUri(v));
  const suffix = values.length > maxItems ? ` +${values.length - maxItems} more` : "";
  return `${shown.join(", ")}${suffix}`;
}

function confidenceSummary(confidenceRows, dir) {
  const values = confidenceRows
    .filter((row) => row.dir === dir && Number.isFinite(row.confidence))
    .map((row) => Number(row.confidence));
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return `avg ${avg.toFixed(3)} | min ${min.toFixed(3)} | max ${max.toFixed(3)}`;
}

function topConfidenceEdges(confidenceRows, dir, maxItems = 4) {
  const rows = confidenceRows
    .filter((row) => row.dir === dir && Number.isFinite(row.confidence))
    .sort((a, b) => b.confidence - a.confidence);
  if (!rows.length) return "";
  return rows
    .slice(0, maxItems)
    .map((row) => `${row.predicate}->${shortUri(row.other)} (${row.confidence.toFixed(3)})`)
    .join(", ");
}

async function fetchNodeInspectorDetails(runId, nodeId) {
  const iri = sparqlIri(nodeId);
  const prefix = "PREFIX kg: <https://example.org/robosikg#>\n";

  const outgoingQuery = `${prefix}
SELECT ?p ?o
WHERE {
  ${iri} ?p ?o .
}
LIMIT 180`;

  const incomingQuery = `${prefix}
SELECT ?s ?p
WHERE {
  ?s ?p ${iri} .
}
LIMIT 180`;

  const confidenceQuery = `${prefix}
SELECT ?dir ?pred ?other ?confidence
WHERE {
  {
    BIND("out" AS ?dir)
    ?edge a kg:Edge ;
          kg:edgeSubject ${iri} ;
          kg:edgePredicate ?pred ;
          kg:edgeObject ?other ;
          kg:edgeConfidence ?confidence .
  }
  UNION
  {
    BIND("in" AS ?dir)
    ?edge a kg:Edge ;
          kg:edgeSubject ?other ;
          kg:edgePredicate ?pred ;
          kg:edgeObject ${iri} ;
          kg:edgeConfidence ?confidence .
  }
}
LIMIT 120`;

  const [outgoingRows, incomingRows, confidenceRowsRaw] = await Promise.all([
    runInspectorQuery(runId, outgoingQuery, 180),
    runInspectorQuery(runId, incomingQuery, 180),
    runInspectorQuery(runId, confidenceQuery, 120),
  ]);

  const literalProps = new Map();
  const outgoingRelations = new Map();
  for (const row of outgoingRows) {
    const pred = localName(row.p || "");
    const obj = String(row.o || "");
    if (!pred || !obj) continue;
    if (isIriLike(obj)) {
      const values = outgoingRelations.get(pred) || [];
      values.push(obj);
      outgoingRelations.set(pred, values);
    } else {
      const values = literalProps.get(pred) || [];
      values.push(obj);
      literalProps.set(pred, values);
    }
  }

  const incomingRelations = new Map();
  for (const row of incomingRows) {
    const pred = localName(row.p || "");
    const subj = String(row.s || "");
    if (!pred || !subj) continue;
    const values = incomingRelations.get(pred) || [];
    values.push(subj);
    incomingRelations.set(pred, values);
  }

  const confidenceRows = confidenceRowsRaw
    .map((row) => {
      const confidence = Number(row.confidence);
      return {
        dir: String(row.dir || ""),
        predicate: localName(row.pred || ""),
        other: String(row.other || ""),
        confidence: Number.isFinite(confidence) ? confidence : NaN,
      };
    })
    .filter((row) => row.dir && row.predicate && row.other && Number.isFinite(row.confidence));

  return { literalProps, outgoingRelations, incomingRelations, confidenceRows };
}

function buildInspectorRows(node, details, status) {
  const rows = [
    ["id", formatInspectorValue(node.id, 180)],
    ["short_id", node.short_id || shortUri(node.id)],
    ["label", formatInspectorValue(node.label, 120)],
    ["group", node.group || "Entity"],
  ];
  if (node.cls) {
    rows.push(["cls", node.cls]);
  }

  if (status.loading) {
    rows.push(["inspector_status", "Loading graph details..."]);
    return rows;
  }

  if (status.error) {
    rows.push(["inspector_status", formatInspectorValue(status.error, 140)]);
    return rows;
  }

  if (!details) {
    return rows;
  }

  const { literalProps, outgoingRelations, incomingRelations, confidenceRows } = details;
  const one = (key) => {
    const values = literalProps.get(key) || [];
    return values.length ? values[0] : "";
  };

  const frameIndex = one("frameIndex");
  const timeNs = one("timeNs");
  const sourceId = one("sourceId");
  const score = one("score");
  const edgeConfidence = one("edgeConfidence");
  const bboxX1 = one("bboxX1");
  const bboxY1 = one("bboxY1");
  const bboxX2 = one("bboxX2");
  const bboxY2 = one("bboxY2");

  if (sourceId) rows.push(["source_id", sourceId]);
  if (frameIndex) rows.push(["frame_index", frameIndex]);
  if (timeNs) rows.push(["time_ns", timeNs]);
  if (score) rows.push(["score", score]);
  if (edgeConfidence) rows.push(["edge_confidence", edgeConfidence]);
  if (bboxX1 && bboxY1 && bboxX2 && bboxY2) {
    rows.push(["bbox_xyxy", `${bboxX1}, ${bboxY1}, ${bboxX2}, ${bboxY2}`]);
  }

  const outCount = relationCount(outgoingRelations);
  const inCount = relationCount(incomingRelations);
  rows.push(["out_relations", String(outCount)]);
  rows.push(["in_relations", String(inCount)]);

  const outMix = summarizePredicateMix(outgoingRelations);
  if (outMix) rows.push(["out_predicates", outMix]);
  const inMix = summarizePredicateMix(incomingRelations);
  if (inMix) rows.push(["in_predicates", inMix]);

  const nearTo = summarizeRelationTargets(outgoingRelations, "near");
  if (nearTo) rows.push(["near_to", nearTo]);
  const nearFrom = summarizeRelationTargets(incomingRelations, "near");
  if (nearFrom) rows.push(["near_from", nearFrom]);
  const insideOf = summarizeRelationTargets(outgoingRelations, "inside");
  if (insideOf) rows.push(["inside_of", insideOf]);
  const contains = summarizeRelationTargets(incomingRelations, "inside");
  if (contains) rows.push(["contains", contains]);
  const overlaps = summarizeRelationTargets(outgoingRelations, "overlaps");
  if (overlaps) rows.push(["overlaps_with", overlaps]);
  const trackParent = summarizeRelationTargets(outgoingRelations, "trackOf");
  if (trackParent) rows.push(["parent_track", trackParent]);
  const trackChildren = summarizeRelationTargets(incomingRelations, "trackOf");
  if (trackChildren) rows.push(["child_nodes", trackChildren]);
  const seenIn = summarizeRelationTargets(outgoingRelations, "seenIn");
  if (seenIn) rows.push(["seen_in", seenIn]);

  const outConfidence = confidenceSummary(confidenceRows, "out");
  if (outConfidence) rows.push(["confidence_out", outConfidence]);
  const inConfidence = confidenceSummary(confidenceRows, "in");
  if (inConfidence) rows.push(["confidence_in", inConfidence]);

  const topOut = topConfidenceEdges(confidenceRows, "out");
  if (topOut) rows.push(["top_conf_out", topOut]);
  const topIn = topConfidenceEdges(confidenceRows, "in");
  if (topIn) rows.push(["top_conf_in", topIn]);

  return rows;
}

function updateNodeInspector(node) {
  state.graph.inspectorRequestSeq += 1;
  const requestSeq = state.graph.inspectorRequestSeq;

  if (!node) {
    renderNodeSummary("Select a graph node", "Type and properties will appear here.");
    renderNodeProps([]);
    return;
  }

  renderNodeSummary(node.label || shortUri(node.id), `Type: ${node.group}${node.cls ? ` · Class: ${node.cls}` : ""}`);
  renderNodeProps(buildInspectorRows(node, null, { loading: true }));

  const runId = state.selectedRunId || dom.runSelect.value;
  if (!runId) {
    renderNodeProps(buildInspectorRows(node, null, { error: "Select a run to inspect graph details." }));
    return;
  }

  fetchNodeInspectorDetails(runId, node.id)
    .then((details) => {
      if (requestSeq !== state.graph.inspectorRequestSeq) return;
      if (state.graph.selectedNodeId !== node.id) return;
      renderNodeProps(buildInspectorRows(node, details, {}));
    })
    .catch((err) => {
      if (requestSeq !== state.graph.inspectorRequestSeq) return;
      if (state.graph.selectedNodeId !== node.id) return;
      renderNodeProps(buildInspectorRows(node, null, { error: `Inspector query failed: ${err.message}` }));
    });
}

function installGraphInteractions() {
  dom.graphCanvas.addEventListener("click", (ev) => {
    const rect = dom.graphCanvas.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    const hit = state.graph.hitboxes.find((h) => x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h);
    state.graph.selectedNodeId = hit ? hit.node.id : null;
    updateNodeInspector(hit ? hit.node : null);
    drawGraph();
  });
}

function formatRunOption(run) {
  const fps = Number(run?.timing?.effective_fps || 0).toFixed(2);
  return `${run.run_id} · ${run.reasoning_backend || "?"} · ${fps}fps`;
}

async function refreshRuns(preferredRun = null) {
  const data = await apiJSON("/api/runs");
  state.runs = data.items || [];
  dom.runSelect.innerHTML = "";
  for (const run of state.runs) {
    const opt = document.createElement("option");
    opt.value = run.run_id;
    opt.textContent = formatRunOption(run);
    dom.runSelect.appendChild(opt);
  }

  const target = preferredRun || state.selectedRunId || (state.runs[0] && state.runs[0].run_id);
  if (target) {
    dom.runSelect.value = target;
    await loadRun(target);
  }
}

async function loadRun(runId) {
  if (!runId) return;
  state.selectedRunId = runId;
  state.graph.queryNodeIds = null;
  state.overlay.queryFocus = null;
  applyChatFilter(null, null);
  applyTrajectoryPoints([]);
  const [summary, graph] = await Promise.all([
    apiJSON(`/api/runs/${encodeURIComponent(runId)}`),
    apiJSON(`/api/runs/${encodeURIComponent(runId)}/graph`),
  ]);

  const videoPath = await resolveRunVideoPath(runId, summary);
  if (videoPath) {
    dom.mp4PathInput.value = videoPath;
    setVideoFromPath(videoPath);
  }

  state.graph.nodes = graph.nodes || [];
  state.graph.edges = graph.edges || [];
  state.graph.positions = new Map();
  state.graph.selectedNodeId = null;
  updateNodeInspector(null);
  rebuildFilters();
  drawGraph();

  const counts = summary.counts || {};
  updateMetrics({
    frames_seen: counts.frames_seen || 0,
    regions_added: counts.regions_added || 0,
    vector_items: counts.vector_items || 0,
  });
  applyPerfFromSummary(summary);
  updateScrub(counts.frames_seen || 0);
  dom.overlayMode.textContent = summary?.config?.reasoning?.mode || "?";
  dom.overlayDevice.textContent = summary?.config?.perception?.device || "?";
  const sampleFps = summary?.config?.ingest?.sample_fps || summary?.timing?.effective_fps || 5;
  loadRunOverlays(runId, sampleFps).catch((err) => pushChat("error", `Overlay load failed: ${err.message}`));

  pushEvent(`Loaded ${runId}`, "run", `${counts.frames_seen || 0} frames`);
  const events = summary.events || [];
  for (const event of events.slice(-8)) {
    if (event.type === "reasoning_summary") {
      pushChat("reasoner", clip(event.summary || "", 260), ts(), { frameUri: event.frame || "" });
    }
  }
}

async function exportSelectedRun() {
  if (!state.selectedRunId) {
    pushEvent("Select a run before exporting", "export");
    return;
  }
  const out = await apiJSON(`/api/runs/${encodeURIComponent(state.selectedRunId)}/export`, { method: "POST" });
  pushEvent(`Exported ${out.archive_path}`, "export", `${out.size_bytes} bytes`);
  pushChat("export", `Bundle ready: ${out.archive_path} (${(out.files || []).join(", ")})`);
}

function parseFrameHint(columnName, cellValue) {
  const col = String(columnName || "").toLowerCase();
  const val = String(cellValue || "").trim();
  if (!val) return null;
  if (!col.includes("frame")) return null;
  const n = Number(val);
  if (!Number.isFinite(n)) return null;
  return Math.floor(n);
}

function extractSparqlContext(columns, rows) {
  const entityUris = new Set();
  const frameUris = new Set();
  const frameIndices = new Set();
  let hasExplicitFrameBinding = false;
  let firstFrameIndex = null;
  for (const row of rows || []) {
    if (!Array.isArray(row)) continue;
    for (let i = 0; i < columns.length; i += 1) {
      const col = columns[i] || "";
      const isFrameCol = String(col).toLowerCase().includes("frame");
      const raw = String(row[i] ?? "").trim();
      if (!raw) continue;
      const frameHint = parseFrameHint(col, raw);
      if (frameHint !== null) {
        frameIndices.add(frameHint);
        hasExplicitFrameBinding = true;
        if (firstFrameIndex === null) {
          firstFrameIndex = frameHint;
        }
      }
      if (isIriLike(raw)) {
        entityUris.add(raw);
        if (isFrameCol) {
          frameUris.add(raw);
          hasExplicitFrameBinding = true;
        }
      } else if (isFrameCol) {
        hasExplicitFrameBinding = true;
      }
    }
  }
  return { entityUris, frameUris, frameIndices, hasExplicitFrameBinding, firstFrameIndex };
}

function parseFiniteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function addUniqueByKey(map, frameIdx, item, keyFn) {
  const list = map.get(frameIdx) || [];
  const itemKey = keyFn(item);
  if (!list.some((row) => keyFn(row) === itemKey)) {
    list.push(item);
    map.set(frameIdx, list);
  }
}

function addOverlayBox(map, frameIdx, box) {
  addUniqueByKey(map, frameIdx, box, (row) => `${row.bbox.join(",")}::${row.cls || ""}`);
}

function addOverlayTrack(map, frameIdx, track) {
  addUniqueByKey(map, frameIdx, track, (row) => `${row.track_id}::${row.bbox.join(",")}::${row.cls || ""}`);
}

function mergeResolvedRow(target, row) {
  const uri = String(row.uri || "").trim();
  const frameUri = String(row.frameUri || "").trim();
  const trackUri = String(row.track || "").trim();
  const frameIdx = parseFiniteNumber(row.frameIdx);
  const cls = String(row.cls || "").trim() || "obj";
  const score = parseFiniteNumber(row.score);
  const x1 = parseFiniteNumber(row.x1);
  const y1 = parseFiniteNumber(row.y1);
  const x2 = parseFiniteNumber(row.x2);
  const y2 = parseFiniteNumber(row.y2);

  if (uri) target.nodeIds.add(uri);
  if (frameUri) {
    target.frameUris.add(frameUri);
    target.nodeIds.add(frameUri);
  }
  if (trackUri) target.nodeIds.add(trackUri);
  if (frameIdx !== null) target.frameIndices.add(frameIdx);
  if (uri && frameUri) target.entityUrisByFrameUri.set(uri, frameUri);

  if (frameIdx === null) return;
  if (x1 === null || y1 === null || x2 === null || y2 === null) return;
  addOverlayBox(target.boxesByFrame, frameIdx, {
    bbox: [x1, y1, x2, y2],
    cls,
    score,
  });
  if (trackUri) {
    addOverlayTrack(target.tracksByFrame, frameIdx, {
      track_id: shortUri(trackUri).replace(/^#/, ""),
      bbox: [x1, y1, x2, y2],
      cls,
    });
  }
}

async function resolveSparqlVisualTargets(runId, context) {
  const uriList = [...context.entityUris].slice(0, 80);
  const graphNodeById = new Map((state.graph.nodes || []).map((n) => [n.id, n]));
  const trackUris = uriList.filter((uri) => {
    const node = graphNodeById.get(uri);
    return Boolean(node && String(node.group || "").toLowerCase().includes("track"));
  });

  const target = {
    nodeIds: new Set(uriList),
    frameIndices: new Set(context.frameIndices),
    frameUris: new Set(context.frameUris),
    boxesByFrame: new Map(),
    tracksByFrame: new Map(),
    entityUrisByFrameUri: new Map(),
  };

  if (uriList.length) {
    const values = uriList.map((u) => sparqlIri(u)).join(" ");
    const query = `
PREFIX kg: <https://example.org/robosikg#>
SELECT ?uri ?frameUri ?frameIdx ?cls ?score ?x1 ?y1 ?x2 ?y2 ?track
WHERE {
  VALUES ?uri { ${values} }
  OPTIONAL {
    ?uri kg:seenIn ?frameUri .
    ?frameUri kg:frameIndex ?frameIdx .
    OPTIONAL { ?uri kg:cls ?cls }
    OPTIONAL { ?uri kg:score ?score }
    OPTIONAL {
      ?uri kg:bboxX1 ?x1 ;
           kg:bboxY1 ?y1 ;
           kg:bboxX2 ?x2 ;
           kg:bboxY2 ?y2 .
    }
    OPTIONAL { ?uri kg:trackOf ?track }
  }
  OPTIONAL {
    ?uri kg:frameIndex ?frameIdxSelf .
    BIND(?uri AS ?frameUriSelf)
  }
  BIND(COALESCE(?frameUri, ?frameUriSelf) AS ?frameUri)
  BIND(COALESCE(?frameIdx, ?frameIdxSelf) AS ?frameIdx)
}
LIMIT 500`;
    const rows = await runInspectorQuery(runId, query, 500);
    rows.forEach((row) => mergeResolvedRow(target, row));
  }

  if (trackUris.length) {
    const values = trackUris.slice(0, 40).map((u) => sparqlIri(u)).join(" ");
    const trackQuery = `
PREFIX kg: <https://example.org/robosikg#>
SELECT ?uri ?frameUri ?frameIdx ?cls ?score ?x1 ?y1 ?x2 ?y2 ?track
WHERE {
  VALUES ?track { ${values} }
  ?uri kg:trackOf ?track ;
       kg:seenIn ?frameUri .
  ?frameUri kg:frameIndex ?frameIdx .
  OPTIONAL { ?uri kg:cls ?cls }
  OPTIONAL { ?uri kg:score ?score }
  OPTIONAL {
    ?uri kg:bboxX1 ?x1 ;
         kg:bboxY1 ?y1 ;
         kg:bboxX2 ?x2 ;
         kg:bboxY2 ?y2 .
  }
}
LIMIT 500`;
    const rows = await runInspectorQuery(runId, trackQuery, 500);
    rows.forEach((row) => mergeResolvedRow(target, row));
  }

  return target;
}

function overlayPackForSelectedRun() {
  const runId = state.overlay.historyRunId || state.selectedRunId;
  if (!runId) return null;
  return state.overlay.historyByRun.get(runId) || null;
}

function estimateSourceFps(pack) {
  if (!pack) return null;
  const sampleFps = Math.max(0.001, Number(state.overlay.historySampleFps || 5));
  const step = Math.max(1, Number(pack.frameStep || 1));
  return Math.max(0.001, Number(pack.sourceFpsGuess || sampleFps), step * sampleFps);
}

function seekVideoToFrame(frameIndex) {
  const pack = overlayPackForSelectedRun();
  const sourceFps = estimateSourceFps(pack);
  if (!Number.isFinite(sourceFps) || sourceFps <= 0) return;
  if (!dom.videoPreview) return;
  const t = Math.max(0, Number(frameIndex) / sourceFps);
  if (Number.isFinite(t)) {
    dom.videoPreview.currentTime = t;
  }
}

function clearSparqlFocus(pushNotice = false) {
  state.graph.queryNodeIds = null;
  state.overlay.queryFocus = null;
  applyChatFilter(null, null);
  drawGraph();
  syncHistoricalOverlayForCurrentTime();
  if (pushNotice) {
    pushEvent("SPARQL focus cleared", "query");
  }
}

async function applySparqlFocus(runId, out) {
  const columns = Array.isArray(out?.columns) ? out.columns : [];
  const rows = Array.isArray(out?.rows) ? out.rows : [];
  if (!rows.length) {
    clearSparqlFocus(true);
    return;
  }

  const context = extractSparqlContext(columns, rows);
  if (!context.entityUris.size && !context.frameUris.size && !context.frameIndices.size) {
    clearSparqlFocus(false);
    pushEvent("SPARQL returned rows but no URI/frame bindings to focus", "query");
    return;
  }

  const resolved = await resolveSparqlVisualTargets(runId, context);
  const nodeFilter = resolved.nodeIds.size ? resolved.nodeIds : null;
  state.graph.queryNodeIds = nodeFilter;
  if (state.graph.selectedNodeId && nodeFilter && !nodeFilter.has(state.graph.selectedNodeId)) {
    state.graph.selectedNodeId = null;
    updateNodeInspector(null);
  }
  drawGraph();

  applyChatFilter(resolved.frameUris, resolved.nodeIds);

  const frameCandidates = context.hasExplicitFrameBinding
    ? [...resolved.frameIndices].filter((n) => Number.isFinite(n))
    : [];
  const frameIndex = Number.isFinite(Number(context.firstFrameIndex))
    ? Number(context.firstFrameIndex)
    : frameCandidates.length
      ? frameCandidates[0]
      : null;
  if (context.hasExplicitFrameBinding && frameIndex !== null) {
    const pack = overlayPackForSelectedRun();
    const historyData = pack?.frameMap?.get(String(frameIndex)) || { boxes: [], tracks: [] };
    const boxes = resolved.boxesByFrame.get(frameIndex) || historyData.boxes || [];
    const tracks = resolved.tracksByFrame.get(frameIndex) || historyData.tracks || [];
    state.overlay.queryFocus = {
      active: true,
      frameIndex,
      boxes,
      tracks,
    };
    seekVideoToFrame(frameIndex);
    applyOverlayFrameData(frameIndex, { boxes, tracks });
    pushEvent(`SPARQL focus applied to frame ${frameIndex}`, "query");
  } else {
    state.overlay.queryFocus = null;
    pushEvent(
      context.hasExplicitFrameBinding
        ? "SPARQL focus applied (graph/chat), frame index could not be resolved"
        : "SPARQL focus applied (graph/chat), no explicit frame binding in query",
      "query"
    );
  }

  const urisPreview = [...resolved.nodeIds].slice(0, 8);
  const previewBody = urisPreview.length ? `Focused URIs: ${urisPreview.map((u) => shortUri(u)).join(", ")}` : "Focus applied.";
  pushChat("query", previewBody, ts(), {
    frameUri: [...resolved.frameUris][0] || "",
    entityUris: urisPreview,
  });
}

async function runSparqlEditorQuery() {
  const runId = state.selectedRunId || dom.runSelect.value;
  if (!runId) {
    pushChat("query", "Select a run first.");
    return;
  }
  const query = dom.sparqlEditor.value.trim();
  if (!query) {
    pushChat("query", "Query editor is empty.");
    return;
  }
  const out = await apiJSON("/api/sparql/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, query, limit: 50 }),
  });
  const previewRows = (out.rows || [])
    .slice(0, 5)
    .map((r) => r.map((v) => clip(v, 48)).join(" | "))
    .join("\n");
  pushEvent(`SPARQL rows: ${out.row_count}${out.truncated ? " (truncated)" : ""}`, "query");
  pushChat(
    "query",
    out.row_count
      ? `<pre>${clip((out.columns || []).join(" | "), 240)}\n${clip(previewRows, 1200)}</pre>`
      : "No rows returned."
  );
  await applySparqlFocus(runId, out);
}

async function startRun() {
  clearSparqlFocus(false);
  const payload = {
    mp4_path: dom.mp4PathInput.value.trim(),
    source_id: dom.sourceIdInput.value.trim() || "auto",
    reasoning_mode: dom.reasoningModeInput.value,
    device: dom.deviceInput.value,
    pretrained: dom.pretrainedInput.checked,
    sample_fps: Number(dom.sampleFpsInput.value || 5),
    max_frames: Number(dom.maxFramesInput.value || 300),
    reason_every_n_frames: Number(dom.reasonEveryInput.value || 25),
  };

  state.activeConfig.max_frames = payload.max_frames;
  applyTrajectoryPoints([]);
  dom.overlayMode.textContent = payload.reasoning_mode;
  dom.overlayDevice.textContent = payload.device;
  setVideoFromPath(payload.mp4_path);

  dom.runBtn.disabled = true;
  try {
    const out = await apiJSON("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.selectedRunId = out.run_id;
    pushEvent(`Started ${out.run_id}`, "run");
    pushChat("system", `Run ${out.run_id} started.`);
    setRunState("starting");
  } catch (err) {
    pushChat("error", `Run failed to start: ${err.message}`);
    setRunState("failed", err.message);
    dom.runBtn.disabled = false;
  }
}

async function uploadVideo(file) {
  const fd = new FormData();
  fd.append("file", file);
  const out = await apiJSON("/api/upload", { method: "POST", body: fd });
  dom.mp4PathInput.value = out.path;
  setVideoFromPath(out.path);
  pushEvent(`Uploaded ${out.path}`, "upload", `${out.size_bytes} bytes`);
}

function handleRunEvent(evt) {
  if (!evt || typeof evt !== "object") return;
  if (evt.type === "frame") {
    updateMetrics({
      frames_seen: evt.frames_seen ?? state.metrics.frames_seen,
      regions_added: evt.regions_added ?? state.metrics.regions_added,
      vector_items: evt.vector_items ?? state.metrics.vector_items,
    });
    updateScrub(evt.frames_seen || 0);
    updateOverlayFrame(evt);
    if ((evt.frames_seen || 0) % 15 === 0) {
      pushEvent(`Frame ${evt.frame_index} · ${evt.detections} detections`, "frame");
    }
    return;
  }

  if (evt.type === "reasoning") {
    const summary = clip(evt.summary || "(empty summary)", 220);
    pushEvent(`Reasoning ${evt.backend} · ${evt.claims} claims`, "reasoning");
    applyTrajectoryPoints(evt.trajectory_2d_norm_0_1000);
    pushChat("reasoner", summary, ts(), { frameUri: evt.frame_uri || "" });
    return;
  }

  if (evt.type === "complete") {
    pushEvent("Run completed", "complete");
  }
}

function handleSocketMessage(msg) {
  if (!msg || typeof msg !== "object") return;
  if (msg.type === "hello" && msg.snapshot) {
    setRunState(msg.snapshot.state || "idle");
    return;
  }

  if (msg.type === "run_state") {
    const stateName = msg.state || "idle";
    state.running = stateName === "running" || stateName === "starting" || stateName === "paused";
    state.paused = stateName === "paused";
    setRunState(stateName, msg.detail || "");
    dom.runBtn.disabled = state.running;
    if (msg.config) {
      state.activeConfig.max_frames = Number(msg.config.max_frames || state.activeConfig.max_frames);
    }
    if (msg.run_id) {
      state.selectedRunId = msg.run_id;
    }
    if (stateName === "completed" && msg.run_id) {
      refreshRuns(msg.run_id).catch((err) => pushChat("error", `Failed to refresh runs: ${err.message}`));
    }
    return;
  }

  if (msg.type === "run_event") {
    handleRunEvent(msg.event);
    return;
  }

  if (msg.type === "console_state") {
    syncConsoleState(msg.state || {});
    if (msg.message) {
      pushEvent(msg.message, "control");
    }
  }
}

function connectSocket() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${proto}://${window.location.host}/ws/live`;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.addEventListener("open", () => {
    pushEvent("WebSocket connected", "socket");
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
    }
    state.pingTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 5000);
  });

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      handleSocketMessage(msg);
    } catch (_err) {
      return;
    }
  });

  ws.addEventListener("close", () => {
    pushEvent("WebSocket disconnected, reconnecting...", "socket");
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
      state.pingTimer = null;
    }
    state.reconnectTimer = setTimeout(connectSocket, 1800);
  });
}

async function pollHealth() {
  const t0 = performance.now();
  try {
    const health = await apiJSON("/api/health");
    const dt = performance.now() - t0;
    dom.chipRtt.textContent = `${dt.toFixed(0)} ms`;
    state.running = Boolean(health.running);
    state.paused = Boolean(health.paused);
    if (health.running && health.paused) {
      dom.chipStream.textContent = "Paused";
    } else if (health.running) {
      dom.chipStream.textContent = "Streaming";
    } else if (!state.running) {
      dom.chipFps.textContent = "--";
    }
  } catch (_err) {
    dom.chipRtt.textContent = "offline";
  }
}

function bindUI() {
  bindEvent(dom.workspaceSelect, "change", () => {
    applyConsoleAction("select_workspace", { workspace: dom.workspaceSelect.value }).catch((err) => {
      pushChat("error", `Workspace change failed: ${err.message}`);
    });
  });
  bindEvent(dom.instructionInput, "change", () => {
    applyConsoleAction("set_instruction", { text: dom.instructionInput.value }).catch((err) => {
      pushChat("error", `Instruction update failed: ${err.message}`);
    });
  });

  bindButton(dom.runBtn, () => {
    startRun().catch((err) => {
      pushChat("error", `Failed to start run: ${err.message}`);
      dom.runBtn.disabled = false;
    });
  });

  bindEvent(dom.runSelect, "change", () => {
    loadRun(dom.runSelect.value).catch((err) => pushChat("error", `Failed to load run: ${err.message}`));
  });

  bindButton(dom.uploadBtn, () => dom.uploadInput.click());
  bindEvent(dom.uploadInput, "change", () => {
    const [file] = dom.uploadInput.files || [];
    if (!file) return;
    uploadVideo(file).catch((err) => pushChat("error", `Upload failed: ${err.message}`));
  });

  bindEvent(dom.mp4PathInput, "change", () => setVideoFromPath(dom.mp4PathInput.value));

  bindButton(dom.refreshGraphBtn, () => {
    applyConsoleAction("refresh_graph", {}, false).catch(() => {});
    if (!state.selectedRunId) return;
    loadRun(state.selectedRunId).catch((err) => pushChat("error", `Graph refresh failed: ${err.message}`));
  });

  bindButton(dom.exportBtn, () => {
    exportSelectedRun().catch((err) => pushChat("error", `Export failed: ${err.message}`));
  });
  bindButton(dom.overlaysBtn, () => {
    applyConsoleAction("toggle_overlays").catch((err) => pushChat("error", `Overlay toggle failed: ${err.message}`));
  });

  bindConsoleActionButton(dom.railPerceptionBtn, "select_rail", { rail: "Perception" });
  bindConsoleActionButton(dom.railReasoningBtn, "select_rail", { rail: "Reasoning" });
  bindConsoleActionButton(dom.railWarehouseBtn, "select_rail", { rail: "Warehouse" });
  bindConsoleActionButton(dom.railGraphBtn, "select_rail", { rail: "Graph" });
  bindConsoleActionButton(dom.railPolicyBtn, "select_rail", { rail: "Policy" });
  bindConsoleActionButton(dom.railSettingsBtn, "select_rail", { rail: "Settings" });

  bindConsoleActionButton(dom.layerTimelineBtn, "toggle_layer", { layer: "timeline" });
  bindConsoleActionButton(dom.layerBoxesBtn, "toggle_layer", { layer: "boxes" });
  bindConsoleActionButton(dom.layerMasksBtn, "toggle_layer", { layer: "masks" });
  bindConsoleActionButton(dom.layerTracksBtn, "toggle_layer", { layer: "tracks" });
  bindConsoleActionButton(dom.layerLabelsBtn, "toggle_layer", { layer: "labels" });

  bindConsoleActionButton(dom.moduleVisionBtn, "toggle_module", { module: "vision" });
  bindConsoleActionButton(dom.moduleSlamBtn, "toggle_module", { module: "slam" });
  bindConsoleActionButton(dom.moduleLlmBtn, "toggle_module", { module: "llm" });

  bindButton(dom.layoutBtn, () => {
    applyConsoleAction("layout_graph").catch(() => {}).finally(() => relayoutGraph());
  });
  bindButton(dom.timelinePlay, () => {
    applyConsoleAction("timeline_play").catch(() => {}).finally(() => toggleVideoPlayback());
  });
  bindButton(dom.timelineStep, () => {
    applyConsoleAction("timeline_step").catch(() => {}).finally(() => stepVideo(0.25));
  });
  bindButton(dom.timelineFullscreen, () => {
    toggleVideoStageFullscreen();
  });
  bindButton(dom.pauseBtn, () => {
    applyConsoleAction("toggle_pause").catch((err) => pushChat("error", `Pause/resume failed: ${err.message}`));
  });
  bindButton(dom.resetBtn, () => {
    applyConsoleAction("reset_console").then(() => {
      resetDashboardView();
    }).catch((err) => pushChat("error", `Reset failed: ${err.message}`));
  });
  bindButton(dom.recordBtn, () => {
    applyConsoleAction("toggle_record").catch((err) => pushChat("error", `Record toggle failed: ${err.message}`));
  });
  bindButton(dom.menuBtn, () => {
    applyConsoleAction("toggle_menu").catch((err) => pushChat("error", `Menu toggle failed: ${err.message}`));
  });

  bindButton(dom.copyQueryBtn, async () => {
    try {
      await navigator.clipboard.writeText(dom.sparqlEditor.value);
      pushEvent("SPARQL copied to clipboard", "query");
    } catch (_err) {
      pushEvent("Clipboard unavailable", "query");
    }
  });

  bindButton(dom.runQueryBtn, () => {
    runSparqlEditorQuery().catch((err) => pushChat("error", `SPARQL query failed: ${err.message}`));
  });
  bindButton(dom.clearSparqlFocusBtn, () => clearSparqlFocus(true));

  bindEvent(window, "resize", () => drawGraph());
  bindEvent(window, "resize", () => drawVideoLayers());
  bindEvent(dom.videoPreview, "loadedmetadata", () => {
    state.overlay.sourceWidth = dom.videoPreview.videoWidth || state.overlay.sourceWidth;
    state.overlay.sourceHeight = dom.videoPreview.videoHeight || state.overlay.sourceHeight;
    drawVideoLayers();
    syncHistoricalOverlayForCurrentTime();
  });
  bindEvent(dom.videoPreview, "seeked", () => {
    drawVideoLayers();
    syncHistoricalOverlayForCurrentTime();
  });
  bindEvent(dom.videoPreview, "pointerdown", (ev) => {
    state.overlay.nativeFsCandidate = isLikelyNativeFullscreenControlHit(ev);
  });
  bindEvent(dom.videoPreview, "click", () => {
    // Native controls are in UA shadow DOM; click often retargets to <video>.
    // If click is likely on native fullscreen control, route to stage fullscreen directly.
    if (state.overlay.nativeFsCandidate) {
      state.overlay.nativeFsCandidate = false;
      toggleVideoStageFullscreen();
      return;
    }
    state.overlay.nativeFsCandidate = false;
    setTimeout(() => promoteNativeVideoFullscreenFromGesture(), 0);
  });
  bindEvent(dom.videoPreview, "dblclick", (ev) => {
    ev.preventDefault();
    toggleVideoStageFullscreen();
  });
  bindEvent(dom.videoPreview, "timeupdate", () => syncHistoricalOverlayForCurrentTime());
  bindEvent(dom.videoPreview, "play", () => syncHistoricalOverlayForCurrentTime());
  bindEvent(document, "fullscreenchange", () => handleFullscreenChange());
  syncFullscreenButton();
  installGraphInteractions();
}

async function init() {
  bindUI();
  await apiJSON("/api/console/state")
    .then((snapshot) => syncConsoleState(snapshot))
    .catch((err) => pushChat("error", `Failed to load console state: ${err.message}`));
  connectSocket();
  setVideoFromPath(dom.mp4PathInput.value);
  await refreshRuns().catch((err) => pushChat("error", `Failed to load runs: ${err.message}`));
  await pollHealth();
  setInterval(() => {
    pollHealth().catch(() => {});
  }, 6000);
}

init().catch((err) => {
  pushChat("error", `UI bootstrap failed: ${err.message}`);
});
