/* MQTTPlot - Public Plot Page (slug-based)

   v0.7.1 behavior:
   - Fixed window presets (2/4/8/12h, 1/3/5d, 1/2/4w; default 4h)
   - Back/Forward slides by one full window span (no implicit zoom)
   - Forward clamps at the latest sample (no "creeping" past the tail)
   - If the window is at the tail, it stays pinned to the tail as new samples arrive
   - Plotly mode bar disabled
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

// Discrete window presets (small -> large). Span is immutable unless the user changes presets.
// v0.7.1 presets:
//   2, 4, 8, 12 hours (default = 4 hours)
//   1, 3, 5 days
//   1, 2, 4 weeks
const WINDOW_OPTIONS_MS = [
  2 * 60 * 60 * 1000,        // 2 hours
  4 * 60 * 60 * 1000,        // 4 hours (default)
  8 * 60 * 60 * 1000,        // 8 hours
  12 * 60 * 60 * 1000,       // 12 hours
  24 * 60 * 60 * 1000,       // 1 day
  3 * 24 * 60 * 60 * 1000,   // 3 days
  5 * 24 * 60 * 60 * 1000,   // 5 days
  7 * 24 * 60 * 60 * 1000,   // 1 week
  14 * 24 * 60 * 60 * 1000,  // 2 weeks
  28 * 24 * 60 * 60 * 1000   // 4 weeks
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

function clampEndToTail(end, tail) {
  if (!end || !tail) return end;
  return (end.getTime() > tail.getTime()) ? new Date(tail) : end;
}

function formatSpan(ms) {
  const hour = 60 * 60 * 1000;
  const day = 24 * hour;
  const week = 7 * day;

  if (ms % week === 0) {
    const w = ms / week;
    return `${w}w`;
  }
  if (ms % day === 0) {
    const d = ms / day;
    return `${d}d`;
  }
  if (ms % hour === 0) {
    const h = ms / hour;
    return `${h}h`;
  }
  // Fallback
  return `${Math.round(ms / 1000)}s`;
}

function updateZoomButtonLabels(windowState) {
  const spanMs = windowState?.spanMs || WINDOW_OPTIONS_MS[1];
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

function updateLiveIndicator(windowState) {
  const el = $('liveIndicator');
  if (!el) return;
  const isLive = !!(windowState?.followTail && windowState?.tail && windowState?.end &&
    Math.abs(windowState.tail.getTime() - windowState.end.getTime()) <= 5000);
  el.style.display = isLive ? 'inline-block' : 'none';
}

async function loadBoundsForPlot(slug, plotSpec) {
  const topics = Array.isArray(plotSpec?.topics) ? plotSpec.topics : [];
  let minTs = null;
  let maxTs = null;

  for (const t of topics) {
    const name = t?.name;
    if (!name) continue;
    try {
      const b = await fetchJson(`/api/public/bounds?slug=${encodeURIComponent(slug)}&topic=${encodeURIComponent(name)}`);
      const min = b?.min_ts ? new Date(b.min_ts) : null;
      const max = b?.max_ts ? new Date(b.max_ts) : null;
      if (min && !isNaN(min.getTime())) {
        if (!minTs || min < minTs) minTs = min;
      }
      if (max && !isNaN(max.getTime())) {
        if (!maxTs || max > maxTs) maxTs = max;
      }
    } catch (e) {
      // ignore missing bounds for a topic (no data yet)
    }
  }
  return { minTs, maxTs };
}

// Returns { traces, start, end, tail }
async function loadSeriesForPlot(slug, plotSpec, windowState) {
  const now = new Date();

  // Determine the span (immutable unless changed via zoom buttons).
  const specSec = Number(plotSpec?.time?.seconds || 0);
  const specMs = (isFinite(specSec) && specSec > 0) ? specSec * 1000 : null;
  if (!windowState.spanMs) {
    windowState.spanMs = specMs ? WINDOW_OPTIONS_MS[nearestWindowIndex(specMs)] : WINDOW_OPTIONS_MS[1]; // default 4h
  }

  // If we're following the tail, request up to "now" and later pin end to the latest sample seen.
  // If not following the tail, request up to the user's chosen end.
  let requestedEnd = windowState.followTail ? now : (windowState.end ? new Date(windowState.end) : now);
  if (requestedEnd > now) requestedEnd = now;

  // Derive start from end and the immutable span.
  let requestedStart = new Date(requestedEnd.getTime() - windowState.spanMs);

  const topics = Array.isArray(plotSpec.topics) ? plotSpec.topics : [];
  const traces = [];

  let tail = null; // max timestamp actually observed in returned data

  for (const t of topics) {
    const name = t?.name;
    if (!name) continue;

    const url = `/api/public/data?slug=${encodeURIComponent(slug)}&topic=${encodeURIComponent(name)}`
      + `&start=${encodeURIComponent(requestedStart.toISOString())}`
      + `&end=${encodeURIComponent(requestedEnd.toISOString())}`;

    const points = await fetchJson(url);
    traces.push(buildTrace(points, t));

    if (Array.isArray(points) && points.length > 0) {
      const last = new Date(points[points.length - 1].ts);
      if (!isNaN(last.getTime())) {
        if (!tail || last > tail) tail = last;
      }
    }
  }

  // Pin end to the latest sample if following.
  let end = windowState.followTail && tail ? new Date(tail) : new Date(requestedEnd);

  // If not following, still ensure we never run past the known tail we last observed.
  if (!windowState.followTail && tail) end = clampEndToTail(end, tail);

  let start = new Date(end.getTime() - windowState.spanMs);

  return { traces, start, end, tail };
}

async function renderOnce(slug, windowState) {
  showError('');
  const specResp = await fetchJson(`/api/public/plots/${encodeURIComponent(slug)}`);
  const spec = specResp.spec || specResp;

  const { traces, start, end, tail } = await loadSeriesForPlot(slug, spec, windowState);

  const layout = {
    // Title is rendered in the fixed top bar; avoid duplicating it inside the plot.
    title: '',
    margin: { t: 20, l: 60, r: 60, b: 40 },
    xaxis: { title: 'Time' },
    yaxis: { title: '', nticks: 6, ticks: 'outside' },
    // Align major tick marks on y2 with y
    yaxis2: { title: '', overlaying: 'y', side: 'right', tickmode: 'sync', nticks: 6, ticks: 'outside' },
    legend: { orientation: 'h' }
  };

  const config = { responsive: true, displaylogo: false, displayModeBar: false };
  await Plotly.react('plot', traces, layout, config);

  updateZoomButtonLabels(windowState);
  updateLiveIndicator(windowState);

  return { specResp, spec, start, end, tail };
}

document.addEventListener('DOMContentLoaded', async () => {
  const slug = document.body?.dataset?.slug;
  if (!slug) {
    showError('Missing plot slug.');
    return;
  }

  // Window state:
  // - spanMs: immutable selected span
  // - start/end: current displayed window
  // - tail: latest sample timestamp observed
  // - followTail: whether the window is pinned to the tail
  const windowState = {
    spanMs: null,
    start: null,
    end: null,
    tail: null,
    minTs: null,
    maxTs: null,
    followTail: true
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
  windowState.tail = result.tail;

  // Fetch overall bounds once to support navigation clamping.
  // (If some topics have no data yet, they are ignored.)
  try {
    const b = await loadBoundsForPlot(slug, result.specResp.spec || result.specResp);
    windowState.minTs = b.minTs;
    windowState.maxTs = b.maxTs;
  } catch (e) {
    windowState.minTs = null;
    windowState.maxTs = null;
  }

  updateZoomButtonLabels(windowState);
  updateLiveIndicator(windowState);

  $('btnBack')?.addEventListener('click', async () => {
    const spanMs = windowState.spanMs || WINDOW_OPTIONS_MS[1];

    // If the total dataset is smaller than the window, do nothing.
    if (windowState.minTs && windowState.tail) {
      const totalMs = windowState.tail.getTime() - windowState.minTs.getTime();
      if (totalMs <= spanMs + 1000) {
        updateLiveIndicator(windowState);
        return;
      }
    }

    // If we're already at the earliest possible window, do nothing.
    if (windowState.minTs && windowState.start && windowState.start.getTime() <= windowState.minTs.getTime() + 1000) {
      updateLiveIndicator(windowState);
      return;
    }

    windowState.followTail = false;
    windowState.end = new Date((windowState.end || new Date()).getTime() - spanMs);
    windowState.start = new Date(windowState.end.getTime() - spanMs);

    // Clamp to earliest bound if known.
    if (windowState.minTs && windowState.start < windowState.minTs) {
      updateLiveIndicator(windowState);
      return;
    }

    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) {
      windowState.start = r.start;
      windowState.end = r.end;
      windowState.tail = r.tail;
      updateLiveIndicator(windowState);
    }
  });

  $('btnFwd')?.addEventListener('click', async () => {
    const spanMs = windowState.spanMs || WINDOW_OPTIONS_MS[1];
    let proposedEnd = new Date((windowState.end || new Date()).getTime() + spanMs);

    // Clamp to last known tail (if known).
    if (windowState.tail && proposedEnd > windowState.tail) {
      proposedEnd = new Date(windowState.tail);
      windowState.followTail = true;
    }

    windowState.end = proposedEnd;
    windowState.start = new Date(windowState.end.getTime() - spanMs);

    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) {
      windowState.start = r.start;
      windowState.end = r.end;
      windowState.tail = r.tail;

      // If we've reached the tail, keep following it as new samples arrive.
      if (windowState.tail && Math.abs(windowState.tail.getTime() - windowState.end.getTime()) <= 5000) {
        windowState.followTail = true;
      }

      updateLiveIndicator(windowState);
    }
  });

  $('btnZoomIn')?.addEventListener('click', async () => {
    const spanMs = windowState.spanMs || WINDOW_OPTIONS_MS[1];
    const idx = nearestWindowIndex(spanMs);
    const newIdx = Math.max(0, idx - 1);
    windowState.spanMs = WINDOW_OPTIONS_MS[newIdx];

    // Keep end fixed; recompute start from the new span.
    windowState.start = new Date(windowState.end.getTime() - windowState.spanMs);

    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) {
      windowState.start = r.start;
      windowState.end = r.end;
      windowState.tail = r.tail;
      updateZoomButtonLabels(windowState);
      updateLiveIndicator(windowState);
    }
  });

  $('btnZoomOut')?.addEventListener('click', async () => {
    const spanMs = windowState.spanMs || WINDOW_OPTIONS_MS[1];
    const idx = nearestWindowIndex(spanMs);
    const newIdx = Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1);
    windowState.spanMs = WINDOW_OPTIONS_MS[newIdx];

    windowState.start = new Date(windowState.end.getTime() - windowState.spanMs);

    const r = await renderOnce(slug, windowState).catch(() => null);
    if (r) {
      windowState.start = r.start;
      windowState.end = r.end;
      windowState.tail = r.tail;
      updateZoomButtonLabels(windowState);
      updateLiveIndicator(windowState);
    }
  });

  const refresh = (result.specResp.spec || result.specResp).refresh;
  if (refresh && refresh.enabled) {
    const intervalMs = Math.max(2000, Number(refresh.intervalMs || 5000));
    setInterval(() => {
      // If pinned to tail, re-render with followTail = true (window advances to newest sample).
      // If not pinned, keep the user's selected end (no hijacking).
      renderOnce(slug, windowState).then((r) => {
        windowState.start = r.start;
        windowState.end = r.end;
        windowState.tail = r.tail;
        updateLiveIndicator(windowState);
      }).catch(() => {});
    }, intervalMs);
  }
});
