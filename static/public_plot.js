/* MQTTPlot - Public Plot Page (slug-based)

   This script is intentionally minimal:
   - Fetches a published PlotSpec by slug
   - Renders multi-topic Plotly traces
   - Refreshes periodically if enabled

   Security note: the server enforces that only topics included
   in the published plot spec can be queried via public endpoints.
*/

function $(id) { return document.getElementById(id); }

function showError(msg) {
  const el = $('plot_error');
  if (!el) return;
  el.style.display = msg ? 'block' : 'none';
  el.textContent = msg || '';
}

async function fetchJson(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${text.slice(0, 200)}`);
  }
  return await r.json();
}

function buildTrace(series, topicSpec) {
  const x = series.map(p => p.ts);
  const y = series.map(p => p.value);
  return {
    x,
    y,
    type: 'scatter',
    mode: topicSpec?.mode || 'lines',
    name: topicSpec?.label || topicSpec?.name || 'series',
    yaxis: (topicSpec?.yAxis === 'y2') ? 'y2' : 'y'
  };
}

const WINDOW_OPTIONS_MS = [
  1 * 60 * 60 * 1000,
  6 * 60 * 60 * 1000,
  12 * 60 * 60 * 1000,
  24 * 60 * 60 * 1000,
  3 * 24 * 60 * 60 * 1000,
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

function formatRangeLabel(start, end) {
  if (!start || !end) return '';
  const s = start.toLocaleString();
  const e = end.toLocaleString();
  return `${s} ... ${e}`;
}

async function loadSeriesForPlot(slug, plotSpec, windowState) {
  const now = new Date();
  let start = windowState?.start ? new Date(windowState.start) : null;
  let end = windowState?.end ? new Date(windowState.end) : null;

  if (!end || isNaN(end.getTime())) end = now;
  if (end > now) end = now;

  if (!start || isNaN(start.getTime())) {
    const sec = Number(plotSpec?.time?.seconds || 3600);
    const ms = (isFinite(sec) && sec > 0 ? sec : 3600) * 1000;
    start = new Date(end.getTime() - ms);
  }

  const startIso = start.toISOString();
  const endIso = end.toISOString();

  const topics = Array.isArray(plotSpec.topics) ? plotSpec.topics : [];
  const traces = [];

  for (const t of topics) {
    const name = t?.name;
    if (!name) continue;

    const url = `/api/public/data?slug=${encodeURIComponent(slug)}&topic=${encodeURIComponent(name)}`
      + (startIso ? `&start=${encodeURIComponent(startIso)}` : '')
      + (endIso ? `&end=${encodeURIComponent(endIso)}` : '');

    const points = await fetchJson(url);
    traces.push(buildTrace(points, t));
  }

  return { traces, start, end };
}

async function renderOnce(slug, windowState) {
  showError('');
  const spec = await fetchJson(`/api/public/plots/${encodeURIComponent(slug)}`);
  const { traces, start, end } = await loadSeriesForPlot(slug, spec.spec || spec, windowState);

  const layout = {
    title: spec.title || spec.spec?.title || slug,
    margin: { t: 60, l: 60, r: 60, b: 40 },
    xaxis: { title: 'Time' },
    yaxis: { title: '', nticks: 6, ticks: 'outside' },
    // Align major tick marks on y2 with y
    yaxis2: { title: '', overlaying: 'y', side: 'right', tickmode: 'sync', nticks: 6, ticks: 'outside' },
    legend: { orientation: 'h' }
  };

  const config = { responsive: true, displaylogo: false };
  await Plotly.react('plot', traces, layout, config);

  return { spec, start, end };
}

document.addEventListener('DOMContentLoaded', async () => {
  const slug = document.body?.dataset?.slug;
  if (!slug) {
    showError('Missing plot slug.');
    return;
  }

  let windowState = { start: null, end: null };
  const rangeLabelEl = $('rangeLabel');
  const updateRangeLabel = (start, end) => {
    if (rangeLabelEl) rangeLabelEl.textContent = formatRangeLabel(start, end);
  };

  let result;
  try {
    result = await renderOnce(slug, windowState);
  } catch (e) {
    showError(`Failed to load plot: ${e.message}`);
    return;
  }
  windowState.start = result.start;
  windowState.end = result.end;
  updateRangeLabel(result.start, result.end);

  $('btnBack')?.addEventListener('click', async () => {
    const w = (windowState.end && windowState.start) ? Math.max(1000, windowState.end - windowState.start) : 3600 * 1000;
    const shift = w * 0.5;
    windowState.end = new Date(windowState.end.getTime() - shift);
    windowState.start = new Date(windowState.end.getTime() - w);
    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) { windowState.start = r.start; windowState.end = r.end; updateRangeLabel(r.start, r.end); }
  });

  $('btnFwd')?.addEventListener('click', async () => {
    const w = (windowState.end && windowState.start) ? Math.max(1000, windowState.end - windowState.start) : 3600 * 1000;
    const shift = w * 0.5;
    windowState.end = new Date(windowState.end.getTime() + shift);
    windowState.start = new Date(windowState.end.getTime() - w);
    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) { windowState.start = r.start; windowState.end = r.end; updateRangeLabel(r.start, r.end); }
  });

  $('btnZoomIn')?.addEventListener('click', async () => {
    const w = (windowState.end && windowState.start) ? Math.max(1000, windowState.end - windowState.start) : 3600 * 1000;
    const idx = nearestWindowIndex(w);
    const newIdx = Math.max(0, idx - 1);
    const newW = WINDOW_OPTIONS_MS[newIdx];
    windowState.start = new Date(windowState.end.getTime() - newW);
    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) { windowState.start = r.start; windowState.end = r.end; updateRangeLabel(r.start, r.end); }
  });

  $('btnZoomOut')?.addEventListener('click', async () => {
    const w = (windowState.end && windowState.start) ? Math.max(1000, windowState.end - windowState.start) : 3600 * 1000;
    const idx = nearestWindowIndex(w);
    const newIdx = Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1);
    const newW = WINDOW_OPTIONS_MS[newIdx];
    windowState.start = new Date(windowState.end.getTime() - newW);
    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) { windowState.start = r.start; windowState.end = r.end; updateRangeLabel(r.start, r.end); }
  });

  const refresh = (result.spec.spec || result.spec).refresh;
  if (refresh && refresh.enabled) {
    const intervalMs = Math.max(2000, Number(refresh.intervalMs || 5000));
    setInterval(() => {
      renderOnce(slug, windowState).then((r) => {
        windowState.start = r.start;
        windowState.end = r.end;
        updateRangeLabel(r.start, r.end);
      }).catch(() => {});
    }, intervalMs);
  }
});
