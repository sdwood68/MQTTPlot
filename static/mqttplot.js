
const socket = io();
const adminMode =
  document.body.dataset.admin === "true";
let currentTopic = null;
let currentStart = null;   // Date or null
let currentEnd = null;     // Date or null
let boundsCache = {};      // topic -> {min: Date, max: Date}

// Discrete zoom window options (small -> large)
const WINDOW_OPTIONS_MS = [
  4 * 60 * 60 * 1000,        // 4 hours
  8 * 60 * 60 * 1000,        // 8 hours
  12 * 60 * 60 * 1000,       // 12 hours
  24 * 60 * 60 * 1000,       // 1 day
  3 * 24 * 60 * 60 * 1000,   // 3 days
  7 * 24 * 60 * 60 * 1000,   // 1 week
  14 * 24 * 60 * 60 * 1000,  // 2 weeks
  28 * 24 * 60 * 60 * 1000   // 4 weeks
];

function plotIsReady() {
  const plotDiv = document.getElementById('plot');
  return plotDiv && Array.isArray(plotDiv.data) && plotDiv.data.length > 0;
}

function safeExtend(ts, value) {
  if (!plotIsReady()) return;
  try {
    Plotly.extendTraces('plot', { x: [[ts]], y: [[value]] }, [0]);
  } catch (e) {
    // Do not let a live-update error break the rest of the UI
    console.error("extendTraces failed:", e);
  }
}


function nearestWindowIndex(windowMs) {
  let bestIdx = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < WINDOW_OPTIONS_MS.length; i++) {
    const diff = Math.abs(WINDOW_OPTIONS_MS[i] - windowMs);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIdx = i;
    }
  }
  return bestIdx;
}

async function fetchAllValidationRules() {
  if (!adminMode) return {};

  const res = await fetch('/api/admin/validation');
  if (!res.ok) return {};

  const rules = await res.json();
  const map = {};
  (rules || []).forEach(r => {
    map[r.topic] = {
      min_value: r.min_value,
      max_value: r.max_value,
      enabled: (r.enabled !== 0)
    };
  });
  return map;
}

/* Live updates (public stream) */
socket.on("new_data", msg => {
  if (!currentTopic || msg.topic !== currentTopic) return;

  safeExtend(msg.ts, msg.value);

  // Keep window/bounds in sync with latest data
  const ts = new Date(msg.ts);
  if (!isNaN(ts.getTime())) {
    // Update bounds cache max if present
    const b = boundsCache[currentTopic];
    if (b && b.max && ts > b.max) b.max = ts;

    // If we have an active window, advance end to latest only if the current end
    // is close to the previous max (i.e., user is "following" the tail).
    // This prevents hijacking the user's view when they are looking at history.
    if (currentEnd && b && b.max) {
      const prevMax = b.max;
      // NOTE: prevMax already updated above; compute "tail-following" by checking
      // whether currentEnd was within 5 seconds of the previous plotted end.
      // If you prefer, we can store a separate "following" flag later.
    }

    // Simple behavior (safe): always update currentEnd if user hasn't set a manual start
    // and end was previously equal to cached max (tailing).
    if (currentEnd && boundsCache[currentTopic] && boundsCache[currentTopic].max) {
      // If currentEnd was at the tail (within 5s), keep it at the tail
      const tail = boundsCache[currentTopic].max;
      if (Math.abs(tail.getTime() - currentEnd.getTime()) <= 5000) {
        currentEnd = new Date(tail);
        setInputsFromDates(currentStart, currentEnd);
      }
    }
  }
});


/* Optional: Admin-only stream for hidden topics (safe if server never emits it) */
socket.on("new_data_admin", msg => {
  if (!adminMode) return;
  if (currentTopic && msg.topic === currentTopic) {
    safeExtend(msg.ts, msg.value);
  }
});

/* Load topic list */
async function loadTopics() {
  const res = await fetch('/api/topics');
  const data = await res.json();
  const validationMap = await fetchAllValidationRules();

  const div = document.getElementById('topics');
  const list = document.getElementById('topiclist');
  div.innerHTML = '';
  list.innerHTML = '';

  data.forEach(t => {
    const row = document.createElement('div');
    row.className = 'topic-row';

    const label = document.createElement('span');
    label.className = 'topic';
    label.textContent = t.topic;
    label.onclick = () => {
      document.getElementById('topicInput').value = t.topic;
      boundsCache[t.topic] = undefined; // force refresh bounds on selection
      plot();
    };


    row.appendChild(label);
    row.appendChild(document.createTextNode(` — ${t.count} msgs `));

    if (adminMode) {
      /* Visibility toggle */
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.checked = t.public !== 0;
      chk.title = 'Publicly visible';
      chk.style.marginLeft = "10px";
      chk.onchange = async () => {
        const r = await fetch('/api/admin/topic_visibility', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: t.topic,
            public: chk.checked
          })
        });
        if (!r.ok) alert('Failed to update visibility (are you logged in as admin?)');
      };
      row.appendChild(chk);

      /* Delete button */
      const del = document.createElement('button');
      del.textContent = 'Delete';
      del.style.marginLeft = "6px";
      del.onclick = async () => {
        if (!confirm(`Delete ALL data for topic "${t.topic}"?`)) return;
        const r = await fetch(`/api/admin/topic/${encodeURIComponent(t.topic)}`, {
          method: 'DELETE'
        });
        if (!r.ok) {
          alert('Delete failed (are you logged in as admin?)');
          return;
        }
        loadTopics();
      };
      row.appendChild(del);
      // --- Validation controls (per topic) ---
      const rule = validationMap[t.topic] || { min_value: null, max_value: null, enabled: true };

      const vLabel = document.createElement('span');
      vLabel.className = 'validation-label';
      vLabel.textContent = 'Valid range:';
      row.appendChild(vLabel);

      const minInput = document.createElement('input');
      minInput.className = 'validation-input';
      minInput.type = 'number';
      minInput.step = 'any';
      minInput.placeholder = (rule.min_value === null || rule.min_value === undefined) ? "" : String(rule.min_value);
      minInput.title = "Min value (leave blank for no minimum)";
      row.appendChild(minInput);

      const maxInput = document.createElement('input');
      maxInput.className = 'validation-input';
      maxInput.type = 'number';
      maxInput.step = 'any';
      maxInput.placeholder = (rule.max_value === null || rule.max_value === undefined) ? "" : String(rule.max_value);
      maxInput.title = "Max value (leave blank for no maximum)";
      row.appendChild(maxInput);

      const enabled = document.createElement('input');
      enabled.type = 'checkbox';
      enabled.checked = !!rule.enabled;
      enabled.title = "Enable validation for this topic";
      enabled.style.marginLeft = "8px";
      row.appendChild(enabled);

      const saveBtn = document.createElement('button');
      saveBtn.textContent = 'Save';
      saveBtn.style.marginLeft = "6px";
      row.appendChild(saveBtn);

      const status = document.createElement('span');
      status.className = 'validation-status';
      row.appendChild(status);

      saveBtn.onclick = async () => {
        await saveValidationForTopic(t.topic, minInput, maxInput, enabled, status);
      };

    }

    div.appendChild(row);

    const opt = document.createElement('option');
    opt.value = t.topic;
    list.appendChild(opt);
  });
}

/* v0.6.0 plot window controls */
async function getBounds(topic) {
  if (boundsCache[topic] !== undefined) return boundsCache[topic];

  const res = await fetch(`/api/bounds?topic=${encodeURIComponent(topic)}`);
  if (!res.ok) {
    // Cache "no bounds" result to avoid spamming requests/alerts
    boundsCache[topic] = null;
    return null;
  }

  const js = await res.json();
  const b = { min: new Date(js.min_ts), max: new Date(js.max_ts) };
  boundsCache[topic] = b;
  return b;
}

function setNavEnabled(enabled) {
  const ids = ["btnBack", "btnFwd", "btnZoomIn", "btnZoomOut"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) el.disabled = !enabled;
  }
}

function clampWindow(start, end, min, max) {
  // Ensure start <= end
  if (start > end) {
    const tmp = start; start = end; end = tmp;
  }

  const windowMs = end - start;

  // If data bounds are smaller than the window, clamp to the full bounds
  if ((max - min) <= windowMs) {
    return { start: new Date(min), end: new Date(max) };
  }

  // Clamp left
  if (start < min) {
    start = new Date(min);
    end = new Date(start.getTime() + windowMs);
  }

  // Clamp right
  if (end > max) {
    end = new Date(max);
    start = new Date(end.getTime() - windowMs);
  }

  // Final safety clamp
  if (start < min) start = new Date(min);
  if (end > max) end = new Date(max);

  return { start, end };
}

function setInputsFromDates(start, end) {
  // Start remains visible
  document.getElementById('start').value = start ? start.toISOString() : '';

  // End is hidden but still used for API calls and navigation
  document.getElementById('end').value = end ? end.toISOString() : '';
}

async function saveValidationForTopic(topic, minInputEl, maxInputEl, enabledEl, statusEl) {
  const min_value = minInputEl.value;  // blank allowed
  const max_value = maxInputEl.value;  // blank allowed
  const enabled = enabledEl.checked;

  statusEl.textContent = "Saving...";

  const res = await fetch('/api/admin/validation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, min_value, max_value, enabled })
  });

  const js = await res.json().catch(() => ({ error: "request failed" }));
  if (!res.ok) {
    statusEl.textContent = `Error: ${js.error || res.status}`;
    return;
  }

  // Update placeholder values to reflect saved state; clear typed values (so black text indicates unsaved edits)
  const savedMin = (js.min_value === null || js.min_value === undefined) ? "" : String(js.min_value);
  const savedMax = (js.max_value === null || js.max_value === undefined) ? "" : String(js.max_value);

  minInputEl.placeholder = savedMin;
  maxInputEl.placeholder = savedMax;
  minInputEl.value = "";
  maxInputEl.value = "";

  // Update local cache
  boundsCache[topic] = undefined; // bounds may change if values were previously polluting min/max
  statusEl.textContent = "Saved.";
}

/* Plot data */
async function plot() {
  const topic = document.getElementById('topicInput').value;
  if (!topic) {
    alert('Enter topic');
    return;
  }
  currentTopic = topic;

  const startStr = document.getElementById('start').value || "";
  const endStrHidden = document.getElementById('end').value || "";

  // Track current window as Dates if present
  currentStart = startStr ? new Date(startStr) : null;
  currentEnd = endStrHidden ? new Date(endStrHidden) : null;

  // If end isn't set yet, default to topic max bound (latest)
  const b = await getBounds(topic);
  setNavEnabled(!!b);

  if (!b) {
    // No data for this topic yet (or topic has no numeric values)
    currentStart = null;
    currentEnd = null;
    setInputsFromDates(null, null);
    showPlotStatus("No numeric data available for this topic yet.");
    return;
  }

  if (!currentEnd) {
    currentEnd = new Date(b.max);
  }

  // If start isn't set yet but we have an end and bounds, default to 1-day window
  // (or clamp to bounds)
  if (b && currentEnd && !currentStart) {
    const defaultMs = 24 * 60 * 60 * 1000; // 1 day default for initial plot
    currentStart = new Date(currentEnd.getTime() - defaultMs);
    const clamped = clampWindow(currentStart, currentEnd, b.min, b.max);
    currentStart = clamped.start;
    currentEnd = clamped.end;
    setInputsFromDates(currentStart, currentEnd);
  }

  // Build request URL
  let url = `/api/data?topic=${encodeURIComponent(topic)}`;
  if (currentStart) url += `&start=${encodeURIComponent(currentStart.toISOString())}`;
  if (currentEnd) url += `&end=${encodeURIComponent(currentEnd.toISOString())}`;

  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    document.getElementById('plot').innerHTML =
      `Error fetching data (${res.status} ${res.statusText})<pre style="white-space:pre-wrap">${text}</pre>`;
    return;
  }

  const js = await res.json();
  if (!js.length) {
    document.getElementById('plot').innerHTML = 'No numeric data';
    return;
  }

  const trace = {
    x: js.map(r => r.ts),
    y: js.map(r => r.value),
    mode: 'lines+markers',
    name: topic
  };

  Plotly.newPlot('plot', [trace], {
    title: topic,
    xaxis: { title: 'Time' },
    yaxis: { title: 'Value' }
  });

  // If we still don't have a usable window, derive from returned data
  if (!currentStart || !currentEnd) {
    const first = new Date(js[0].ts);
    const last = new Date(js[js.length - 1].ts);
    currentStart = first;
    currentEnd = last;
    setInputsFromDates(currentStart, currentEnd);
  }
}

async function applyWindowSize(newWindowMs) {
  if (!currentTopic) {
    alert("Plot a topic first.");
    return;
  }

  const b = await getBounds(currentTopic);
  if (!b) {
    setNavEnabled(false);
    showPlotStatus("No numeric data available for this topic yet.");
    return;
  }


  // Ensure we have a current window
  let start = currentStart ? new Date(currentStart) : new Date(b.min);
  let end = currentEnd ? new Date(currentEnd) : new Date(b.max);

  // Zoom around the current center to preserve context
  const centerMs = (start.getTime() + end.getTime()) / 2;
  start = new Date(centerMs - newWindowMs / 2);
  end = new Date(centerMs + newWindowMs / 2);

  const clamped = clampWindow(start, end, b.min, b.max);
  currentStart = clamped.start;
  currentEnd = clamped.end;

  setInputsFromDates(currentStart, currentEnd);
  await plot();
}

async function zoomIn() {
  if (!currentTopic) {
    alert("Plot a topic first.");
    return;
  }

  const b = await getBounds(currentTopic);
  if (!b) {
    setNavEnabled(false);
    showPlotStatus("No numeric data available for this topic yet.");
    return;
  }


  // Ensure window exists
  let start = currentStart ? new Date(currentStart) : new Date(b.min);
  let end = currentEnd ? new Date(currentEnd) : new Date(b.max);
  const windowMs = Math.max(1000, end - start);

  const idx = nearestWindowIndex(windowMs);
  const newIdx = Math.max(0, idx - 1);
  await applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
}

async function zoomOut() {
  if (!currentTopic) {
    alert("Plot a topic first.");
    return;
  }

  const b = await getBounds(currentTopic);
  if (!b) {
    setNavEnabled(false);
    showPlotStatus("No numeric data available for this topic yet.");
    return;
  }


  // Ensure window exists
  let start = currentStart ? new Date(currentStart) : new Date(b.min);
  let end = currentEnd ? new Date(currentEnd) : new Date(b.max);
  const windowMs = Math.max(1000, end - start);

  const idx = nearestWindowIndex(windowMs);
  const newIdx = Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1);
  await applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
}

async function slideWindow(fraction) {
  if (!currentTopic) {
    alert("Plot a topic first.");
    return;
  }

  const b = await getBounds(currentTopic);
  if (!b) {
    setNavEnabled(false);
    showPlotStatus("No numeric data available for this topic yet.");
    return;
  }


  let start = currentStart ? new Date(currentStart) : new Date(b.min);
  let end = currentEnd ? new Date(currentEnd) : new Date(b.max);

  const windowMs = Math.max(1000, (end - start));
  const shiftMs = windowMs * fraction;

  start = new Date(start.getTime() + shiftMs);
  end = new Date(end.getTime() + shiftMs);

  const clamped = clampWindow(start, end, b.min, b.max);
  currentStart = clamped.start;
  currentEnd = clamped.end;

  setInputsFromDates(currentStart, currentEnd);
  await plot();
}

/* OTA */
async function sendOTA(val) {
  const base = document.getElementById('otaBase').value;
  if (!base) {
    alert('Enter base topic');
    return;
  }
  const r = await fetch('/api/admin/ota', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      base_topic: base,
      ota: val
    })
  });
  if (!r.ok) {
    alert('OTA failed (are you logged in as admin?)');
    return;
  }
  alert('OTA command sent');
}
async function saveRetention() {
  const top_level = document.getElementById('ret_top_level').value.trim();
  const max_age_days = document.getElementById('ret_max_age_days').value;
  const max_rows = document.getElementById('ret_max_rows').value;
  const statusEl = document.getElementById('retention_status');

  if (!statusEl) return;

  if (!top_level) {
    statusEl.textContent = "Error: top_level is required.";
    return;
  }

  let res;
  try {
    const applyRes = await fetch('/api/admin/retention/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ top_level })
    });
    if (!applyRes.ok) {
      console.warn("Retention apply failed:", applyRes.status);
    }
  } catch (e) {
    console.warn("Retention apply request error:", e);
  }

  const text = await res.text();

  // Try JSON, but fall back to raw text for debugging
  let js;
  try {
    js = JSON.parse(text);
  } catch {
    js = { http_status: res.status, http_status_text: res.statusText, raw_response: text.slice(0, 500) };
  }

  statusEl.textContent = JSON.stringify(js, null, 2);

  await fetch('/api/admin/retention/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ top_level })
  });
}


function showPlotStatus(msg) {
  const plotDiv = document.getElementById('plot');
  if (plotDiv) {
    plotDiv.innerHTML = msg ? `<div class="plot-status">${msg}</div>` : '';
  }
}

loadTopics();
setInterval(loadTopics, 10000);

function formatCountdownSeconds(nextRetryTs) {
  if (!nextRetryTs) return null;
  const now = Date.now() / 1000;
  const delta = Math.ceil(nextRetryTs - now);
  return delta > 0 ? delta : 0;
}

async function refreshMqttStatus() {
  const el = document.getElementById("mqtt-status");
  if (!el) return;

  try {
    const resp = await fetch("/api/mqtt/status", { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const s = await resp.json();

    if (s.connected) {
      el.className = "mqtt-status mqtt-status--ok";
      el.textContent = "MQTT: Connected";
      return;
    }

    // Disconnected
    const retryIn = formatCountdownSeconds(s.next_retry_ts);
    const parts = ["MQTT: Disconnected"];

    if (s.last_error) parts.push(`(${s.last_error})`);
    if (typeof retryIn === "number") parts.push(`— retry in ${retryIn}s`);

    el.className = "mqtt-status mqtt-status--down";
    el.textContent = parts.join(" ");
  } catch (e) {
    el.className = "mqtt-status mqtt-status--unknown";
    el.textContent = "MQTT: Status unavailable";
  }
}

// Call once at startup and then poll every 5 seconds.
document.addEventListener("DOMContentLoaded", () => {
  refreshMqttStatus();
  setInterval(refreshMqttStatus, 5000);
});

label.onclick = () => {
  document.getElementById('topicInput').value = t.topic;
  boundsCache[t.topic] = undefined; // force refresh bounds on selection
  plot();
};