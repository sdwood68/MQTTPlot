// Admin single-topic plot window (slug-style UI)
//
// This eliminates the embedded "preview" plot in the admin page. It is admin-only
// and intentionally not published publicly.

import { getBounds, getData, getTopicMeta } from '../api.js';

const Core = window.MQTTPlotCore || {};
function $(id) { return document.getElementById(id); }

function showError(msg) {
  const el = $('plot_error');
  if (!el) return;
  el.style.display = msg ? 'block' : 'none';
  el.textContent = msg || '';
}

// Discrete window presets (small -> large). Span is immutable unless the user changes presets.
const WINDOW_OPTIONS_MS = [
  2 * 60 * 60 * 1000,
  4 * 60 * 60 * 1000,
  8 * 60 * 60 * 1000,
  12 * 60 * 60 * 1000,
  24 * 60 * 60 * 1000,
  3 * 24 * 60 * 60 * 1000,
  5 * 24 * 60 * 60 * 1000,
  7 * 24 * 60 * 60 * 1000,
  14 * 24 * 60 * 60 * 1000,
  28 * 24 * 60 * 60 * 1000
];

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

function unitsLabel(units){ return (Core.unitsLabel ? Core.unitsLabel(units) : 'Value'); }
}

function addPlotAreaBorder(layout){ if(Core.addPlotAreaBorder) return Core.addPlotAreaBorder(layout); }

function formatSpan(ms) {
  const hour = 60 * 60 * 1000;
  const day = 24 * hour;
  const week = 7 * day;
  if (ms % week === 0) return `${ms / week}w`;
  if (ms % day === 0) return `${ms / day}d`;
  if (ms % hour === 0) return `${ms / hour}h`;
  return `${Math.round(ms / 1000)}s`;
}

function clampWindow(start, end, min, max) {
  if (start > end) {
    const tmp = start; start = end; end = tmp;
  }
  const windowMs = end - start;

  if ((max - min) <= windowMs) {
    return { start: new Date(min), end: new Date(max) };
  }

  if (start < min) {
    start = new Date(min);
    end = new Date(start.getTime() + windowMs);
  }

  if (end > max) {
    end = new Date(max);
    start = new Date(end.getTime() - windowMs);
  }

  if (start < min) start = new Date(min);
  if (end > max) end = new Date(max);
  return { start, end };
}

function updateZoomButtonLabels(spanMs) {
  const idx = nearestWindowIndex(spanMs);
  const currentLabel = formatSpan(WINDOW_OPTIONS_MS[idx]);
  const zinTarget = WINDOW_OPTIONS_MS[Math.max(0, idx - 1)];
  const zoutTarget = WINDOW_OPTIONS_MS[Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1)];

  const zin = $('btnZoomIn');
  const zout = $('btnZoomOut');
  const wlbl = $('windowLabel');
  if (wlbl) wlbl.textContent = `Window = ${currentLabel}`;
  if (zin) {
    zin.textContent = `Zoom In (${formatSpan(zinTarget)})`;
    zin.disabled = (idx === 0);
  }
  if (zout) {
    zout.textContent = `Zoom Out (${formatSpan(zoutTarget)})`;
    zout.disabled = (idx === WINDOW_OPTIONS_MS.length - 1);
  }
}

function updateLiveIndicator(end, tail, followTail) {
  const el = $('liveIndicator');
  if (!el) return;
  const isLive = !!(followTail && tail && end && Math.abs(tail.getTime() - end.getTime()) <= 5000);
  el.style.display = isLive ? 'inline-block' : 'none';
}

async function renderPlot(topic, state) {
  showError('');

  const b = await getBounds(topic).catch(() => null);
  if (!b) {
    showError('No numeric data available for this topic yet.');
    return;
  }

  const minTs = new Date(b.min_ts);
  const maxTs = new Date(b.max_ts);
  state.tail = maxTs;

  if (!state.end) state.end = new Date(maxTs);
  if (!state.start) state.start = new Date(state.end.getTime() - state.spanMs);

  // Keep the end clamped to the tail if followTail is enabled
  if (state.followTail && state.tail) {
    state.end = new Date(state.tail);
    state.start = new Date(state.end.getTime() - state.spanMs);
  }

  const clamped = clampWindow(state.start, state.end, minTs, maxTs);
  state.start = clamped.start;
  state.end = clamped.end;

  const rows = await getData(topic, state.start.toISOString(), state.end.toISOString()).catch(() => []);
  if (!rows || rows.length === 0) {
    showError('No numeric data in this time range.');
    return;
  }

  const trace = {
    x: rows.map(r => r.ts),
    y: rows.map(r => r.value),
    type: 'scatter',
    mode: 'lines',
    name: topic,
  };

  const meta = await getTopicMeta(topic).catch(() => null);
  const units = meta?.units ? String(meta.units).trim() : '';
  const yTitle = units ? unitsLabel(units) : 'Value';

  const layout = {
    title: '',
    margin: { t: 20, l: 60, r: 60, b: 40 },
    xaxis: { title: 'Time' },
    yaxis: { title: { text: yTitle }, nticks: 6, ticks: 'outside' },
    legend: { orientation: 'h' }
  };
  addPlotAreaBorder(layout);
  const config = { responsive: true, displaylogo: false, displayModeBar: false };
  await Plotly.react('plot', [trace], layout, config);

  updateZoomButtonLabels(state.spanMs);
  updateLiveIndicator(state.end, state.tail, state.followTail);
}

document.addEventListener('DOMContentLoaded', async () => {
  const topic = (document.body?.dataset?.topic || '').trim();
  if (!topic) {
    showError('No topic provided.');
    return;
  }

  const state = {
    spanMs: WINDOW_OPTIONS_MS[1],
    start: null,
    end: null,
    tail: null,
    followTail: true,
  };

  $('btnClose')?.addEventListener('click', () => {
    try { window.close(); } catch {}
    // Fallback for browsers that refuse to close windows
    if (!window.closed) {
      showError('You can close this window/tab from the browser controls.');
    }
  });

  $('btnBack')?.addEventListener('click', async () => {
    state.followTail = false;
    state.start = new Date(state.start.getTime() - state.spanMs);
    state.end = new Date(state.end.getTime() - state.spanMs);
    await renderPlot(topic, state);
  });

  $('btnFwd')?.addEventListener('click', async () => {
    state.start = new Date(state.start.getTime() + state.spanMs);
    state.end = new Date(state.end.getTime() + state.spanMs);
    // If we hit (or exceed) the tail, pin to tail.
    if (state.tail && state.end.getTime() >= state.tail.getTime()) {
      state.followTail = true;
    }
    await renderPlot(topic, state);
  });

  $('btnZoomIn')?.addEventListener('click', async () => {
    const idx = nearestWindowIndex(state.spanMs);
    if (idx === 0) return;
    state.spanMs = WINDOW_OPTIONS_MS[idx - 1];
    state.start = new Date(state.end.getTime() - state.spanMs);
    await renderPlot(topic, state);
  });

  $('btnZoomOut')?.addEventListener('click', async () => {
    const idx = nearestWindowIndex(state.spanMs);
    if (idx >= WINDOW_OPTIONS_MS.length - 1) return;
    state.spanMs = WINDOW_OPTIONS_MS[idx + 1];
    state.start = new Date(state.end.getTime() - state.spanMs);
    await renderPlot(topic, state);
  });

  // Live updates
  try {
    const socket = io();
    socket.on('new_data', async (msg) => {
      if (msg?.topic !== topic) return;
      // If pinned to tail, re-render using the existing window span (keeps UI deterministic)
      if (state.followTail) {
        state.end = null; // force refresh to tail
        state.start = null;
        await renderPlot(topic, state);
      }
    });
    socket.on('new_data_admin', async (msg) => {
      if (msg?.topic !== topic) return;
      if (state.followTail) {
        state.end = null;
        state.start = null;
        await renderPlot(topic, state);
      }
    });
  } catch {
    // ignore
  }

  await renderPlot(topic, state);
});
