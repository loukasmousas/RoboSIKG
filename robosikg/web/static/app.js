const dom = {
  chipStream: document.getElementById("chipStream"),
  chipRtt: document.getElementById("chipRtt"),
  chipFps: document.getElementById("chipFps"),
  pauseBtn: document.getElementById("pauseBtn"),
  resetBtn: document.getElementById("resetBtn"),
  recordBtn: document.getElementById("recordBtn"),
  menuBtn: document.getElementById("menuBtn"),
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
  scrubProgress: document.getElementById("scrubProgress"),
  timelinePlay: document.getElementById("timelinePlay"),
  timelineStep: document.getElementById("timelineStep"),
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
  runQueryBtn: document.getElementById("runQueryBtn"),
  sparqlEditor: document.getElementById("sparqlEditor"),
  overlayMode: document.getElementById("overlayMode"),
  overlayDevice: document.getElementById("overlayDevice"),
  videoPreview: document.getElementById("videoPreview"),
  videoStage: document.getElementById("videoStage"),
};

const state = {
  ws: null,
  reconnectTimer: null,
  pingTimer: null,
  runs: [],
  selectedRunId: null,
  running: false,
  activeConfig: {
    max_frames: Number(dom.maxFramesInput.value) || 1,
  },
  graph: {
    nodes: [],
    edges: [],
    positions: new Map(),
    hiddenGroups: new Set(),
    filters: [],
    selectedNodeId: null,
    hitboxes: [],
  },
  metrics: {
    frames_seen: 0,
    regions_added: 0,
    vector_items: 0,
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

function clip(text, max = 120) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

function ts() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setRunState(stateName, detail = "") {
  const normalized = stateName || "idle";
  dom.runStateBadge.textContent = normalized;
  dom.runStateBadge.className = `badge ${normalized === "failed" ? "failed" : normalized === "running" ? "running" : "idle"}`;

  if (normalized === "running" || normalized === "starting") {
    dom.chipStream.textContent = "Streaming";
  } else if (normalized === "failed") {
    dom.chipStream.textContent = "Error";
  } else {
    dom.chipStream.textContent = "Idle";
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

function pushChat(role, body, timestamp = ts()) {
  const row = document.createElement("div");
  row.className = "chat-row";
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
}

function updateMetrics(patch) {
  state.metrics = { ...state.metrics, ...patch };
  dom.metricFrames.textContent = String(state.metrics.frames_seen ?? 0);
  dom.metricRegions.textContent = String(state.metrics.regions_added ?? 0);
  dom.metricVectors.textContent = String(state.metrics.vector_items ?? 0);
}

function updateScrub(framesSeen = 0) {
  const maxFrames = Math.max(1, Number(state.activeConfig.max_frames) || 1);
  const pct = Math.min(100, (framesSeen / maxFrames) * 100);
  dom.scrubProgress.style.width = `${pct.toFixed(2)}%`;
}

function setVideoFromPath(path) {
  const p = String(path || "").trim();
  if (!p || !p.endsWith(".mp4")) {
    dom.videoPreview.removeAttribute("src");
    dom.videoPreview.load();
    dom.videoStage.classList.remove("has-video");
    return;
  }
  const filename = p.split("/").pop();
  if (!filename) return;
  dom.videoPreview.src = `/media/${encodeURIComponent(filename)}`;
  dom.videoStage.classList.add("has-video");
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
  drawGraph();
  pushEvent("Dashboard selection reset", "ui");
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
  if (!state.graph.hiddenGroups.size) return state.graph.nodes;
  return state.graph.nodes.filter((n) => !state.graph.hiddenGroups.has(n.group));
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
    const label = node.label || "node";
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

function updateNodeInspector(node) {
  if (!node) {
    dom.nodeSummary.innerHTML = `
      <div class="summary-title">Select a graph node</div>
      <div class="summary-meta">Type and properties will appear here.</div>
    `;
    dom.nodeProps.innerHTML = "";
    return;
  }

  dom.nodeSummary.innerHTML = `
    <div class="summary-title">${node.label}</div>
    <div class="summary-meta">Type: ${node.group} · Confidence: --</div>
  `;

  const rows = [
    ["id", node.id],
    ["label", node.label],
    ["group", node.group],
  ];
  dom.nodeProps.innerHTML = rows
    .map(
      ([k, v]) => `
        <div class="prop-row">
          <div class="prop-key">${k}</div>
          <div class="prop-value">${v}</div>
        </div>
      `
    )
    .join("");
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
  const [summary, graph] = await Promise.all([
    apiJSON(`/api/runs/${encodeURIComponent(runId)}`),
    apiJSON(`/api/runs/${encodeURIComponent(runId)}/graph`),
  ]);

  state.graph.nodes = graph.nodes || [];
  state.graph.edges = graph.edges || [];
  state.graph.positions = new Map();
  rebuildFilters();
  drawGraph();

  const counts = summary.counts || {};
  updateMetrics({
    frames_seen: counts.frames_seen || 0,
    regions_added: counts.regions_added || 0,
    vector_items: counts.vector_items || 0,
  });
  updateScrub(counts.frames_seen || 0);
  dom.overlayMode.textContent = summary?.config?.reasoning?.mode || "?";
  dom.overlayDevice.textContent = summary?.config?.perception?.device || "?";

  pushEvent(`Loaded ${runId}`, "run", `${counts.frames_seen || 0} frames`);
  const events = summary.events || [];
  for (const event of events.slice(-8)) {
    if (event.type === "reasoning_summary") {
      pushChat("reasoner", clip(event.summary || "", 260));
    }
  }
}

async function startRun() {
  const payload = {
    mp4_path: dom.mp4PathInput.value.trim(),
    source_id: dom.sourceIdInput.value.trim() || "web_demo",
    reasoning_mode: dom.reasoningModeInput.value,
    device: dom.deviceInput.value,
    pretrained: dom.pretrainedInput.checked,
    sample_fps: Number(dom.sampleFpsInput.value || 5),
    max_frames: Number(dom.maxFramesInput.value || 300),
    reason_every_n_frames: Number(dom.reasonEveryInput.value || 25),
  };

  state.activeConfig.max_frames = payload.max_frames;
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
    if ((evt.frames_seen || 0) % 15 === 0) {
      pushEvent(`Frame ${evt.frame_index} · ${evt.detections} detections`, "frame");
    }
    return;
  }

  if (evt.type === "reasoning") {
    const summary = clip(evt.summary || "(empty summary)", 220);
    pushEvent(`Reasoning ${evt.backend} · ${evt.claims} claims`, "reasoning");
    pushChat("reasoner", summary);
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
    state.running = stateName === "running" || stateName === "starting";
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
    if (health.running) {
      dom.chipStream.textContent = "Streaming";
    }
  } catch (_err) {
    dom.chipRtt.textContent = "offline";
  }
}

function wirePlaceholderButtons() {
  const buttons = document.querySelectorAll("button");
  for (const btn of buttons) {
    if (!(btn instanceof HTMLElement)) continue;
    if (btn.dataset.wired === "1") continue;
    bindButton(btn, () => {
      const label = clip((btn.textContent || "Button").trim(), 28);
      pushEvent(`${label} is UI-only in this build`, "ui");
    });
  }
}

function bindUI() {
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
    if (!state.selectedRunId) return;
    loadRun(state.selectedRunId).catch((err) => pushChat("error", `Graph refresh failed: ${err.message}`));
  });

  bindButton(dom.layoutBtn, relayoutGraph);
  bindButton(dom.timelinePlay, toggleVideoPlayback);
  bindButton(dom.timelineStep, () => stepVideo(0.25));
  bindButton(dom.pauseBtn, toggleVideoPlayback);
  bindButton(dom.resetBtn, resetDashboardView);
  bindButton(dom.recordBtn, () => pushEvent("Record pipeline not implemented yet", "ui"));
  bindButton(dom.menuBtn, () => pushEvent("Menu actions not implemented yet", "ui"));

  bindButton(dom.copyQueryBtn, async () => {
    try {
      await navigator.clipboard.writeText(dom.sparqlEditor.value);
      pushEvent("SPARQL copied to clipboard", "query");
    } catch (_err) {
      pushEvent("Clipboard unavailable", "query");
    }
  });

  bindButton(dom.runQueryBtn, () => {
    pushChat("query", "Query preview mode: use selected node properties and graph filters.");
  });

  bindEvent(window, "resize", () => drawGraph());
  installGraphInteractions();
  wirePlaceholderButtons();
}

async function init() {
  bindUI();
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
