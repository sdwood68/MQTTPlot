import { UnifiedPlot } from './plot_unified.js';

const SPEC_KEY = 'mqttplot.plotSpec';

function readSpec() {
  const raw = localStorage.getItem(SPEC_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function setTitle(spec) {
  const title = (spec?.title || 'Plot').toString();
  document.title = `MQTTPlot - ${title}`;
  const tEl = document.getElementById('plotTitle');
  if (tEl) tEl.textContent = title;

  const topics = Array.isArray(spec?.topics) ? spec.topics : [];
  const names = topics.map(t => t?.label || t?.name).filter(Boolean);
  const sub = document.getElementById('plotSubtitle');
  if (sub) sub.textContent = names.length ? names.join('  |  ') : '';
}

async function renderFromSpec(plot) {
  const spec = readSpec();
  if (!spec) {
    const st = document.getElementById('plotStatus');
    if (st) st.textContent = 'No plot spec was provided. Open this window from the Admin page.';
    return;
  }
  setTitle(spec);
  await plot.plotFromSpec(spec);
}

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('btnClose')?.addEventListener('click', () => window.close());

  const plot = new UnifiedPlot({ plotDivId: 'plot' });

  // Wire nav controls in this window
  document.getElementById('btnBack')?.addEventListener('click', () => plot.slideWindow?.(-1.0));
  document.getElementById('btnFwd')?.addEventListener('click', () => plot.slideWindow?.(1.0));
  document.getElementById('btnZoomIn')?.addEventListener('click', () => plot.zoomIn?.());
  document.getElementById('btnZoomOut')?.addEventListener('click', () => plot.zoomOut?.());

  // Live updates in the plot window
  try {
    const socket = io();
    socket.on('new_data', (msg) => plot.handleLiveMessage?.(msg));
    socket.on('new_data_admin', (msg) => plot.handleLiveMessage?.(msg));
  } catch (e) {
    console.warn('socket.io not available in plot window:', e);
  }

  await renderFromSpec(plot);

  // If the admin page updates SPEC_KEY, refresh in-place.
  window.addEventListener('storage', (evt) => {
    if (evt.key === SPEC_KEY) {
      renderFromSpec(plot);
    }
  });
});
