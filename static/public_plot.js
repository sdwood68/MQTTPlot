/* MQTTPlot - Public Plot Page (slug-based)

   This script is intentionally minimal:
   - Fetches a published PlotSpec by slug
   - Renders multi-topic Plotly traces
   - Refreshes periodically if enabled

   Security note: the server should enforce that only topics included
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

async function loadSeriesForPlot(slug, plotSpec) {
  const now = new Date();

  // Only relative range is supported in this public page for now.
  // (We can add absolute later without changing the public URL.)
  let startIso = null;
  let endIso = null;

  if (plotSpec?.time?.kind === 'relative') {
    const sec = Number(plotSpec.time.seconds || 3600);
    const start = new Date(now.getTime() - sec * 1000);
    startIso = start.toISOString();
    endIso = now.toISOString();
  }

  const topics = Array.isArray(plotSpec.topics) ? plotSpec.topics : [];
  const traces = [];

  for (const t of topics) {
    const name = t?.name;
    if (!name) continue;

    // Public data endpoint: validates slug/topic association server-side.
    const url = `/api/public/data?slug=${encodeURIComponent(slug)}&topic=${encodeURIComponent(name)}`
      + (startIso ? `&start=${encodeURIComponent(startIso)}` : '')
      + (endIso ? `&end=${encodeURIComponent(endIso)}` : '');

    const points = await fetchJson(url);
    traces.push(buildTrace(points, t));
  }

  return traces;
}

async function renderOnce(slug) {
  try {
    showError('');

    const spec = await fetchJson(`/api/public/plots/${encodeURIComponent(slug)}`);
    const traces = await loadSeriesForPlot(slug, spec.spec || spec);

    const layout = {
      title: spec.title || spec.spec?.title || slug,
      margin: { t: 60, l: 60, r: 60, b: 40 },
      xaxis: { title: 'Time' },
      yaxis: { title: '' },
      yaxis2: { title: '', overlaying: 'y', side: 'right' },
      legend: { orientation: 'h' }
    };

    const config = { responsive: true, displaylogo: false };

    await Plotly.react('plot', traces, layout, config);

    return spec;
  } catch (e) {
    showError(`Failed to load plot: ${e.message}`);
    throw e;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  const slug = document.body?.dataset?.slug;
  if (!slug) {
    showError('Missing plot slug.');
    return;
  }

  let spec;
  try {
    spec = await renderOnce(slug);
  } catch {
    return;
  }

  const refresh = (spec.spec || spec).refresh;
  if (refresh && refresh.enabled) {
    const intervalMs = Math.max(2000, Number(refresh.intervalMs || 5000));
    setInterval(() => { renderOnce(slug).catch(() => {}); }, intervalMs);
  }
});
