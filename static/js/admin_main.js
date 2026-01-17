import { initMqttStatusPolling } from './mqtt_status.js';
import { loadTopics } from './admin/topics_ui.js';
import { SingleTopicPlot } from './admin/plot_single.js';
import { MultiTopicPlotPreview } from './admin/plot_multi.js';
import { sendOTAFromInputs, saveRetentionFromInputs } from './admin/ota_retention.js';
import { refreshPublicPlots, savePublicPlotFromInputs, initPublicPlotsUI, getPublicPlotSpecFromInputs } from './admin/public_plots_ui.js';

// Admin entrypoint: wires UI, socket.io, and periodic refresh.

document.addEventListener('DOMContentLoaded', () => {
  initMqttStatusPolling({ intervalMs: 5000 });

  const singlePlot = new SingleTopicPlot({ plotDivId: 'plot' });
  const previewPlot = new MultiTopicPlotPreview({ plotDivId: 'plot' });
  let activePlot = singlePlot;

  // Socket.IO live updates (public stream)
  const socket = io();
  socket.on('new_data', (msg) => {
    activePlot.handleLiveMessage?.(msg);
  });
  // Optional admin-only stream
  socket.on('new_data_admin', (msg) => {
    activePlot.handleLiveMessage?.(msg);
  });

  // --- Button wiring (replaces inline onclicks) ---
  document.getElementById('btnPlot')?.addEventListener('click', () => {
    activePlot = singlePlot;
    singlePlot.plotFromInputs();
  });
  document.getElementById('btnBack')?.addEventListener('click', () => {
    activePlot.slideWindow?.(-0.5);
  });
  document.getElementById('btnFwd')?.addEventListener('click', () => {
    activePlot.slideWindow?.(0.5);
  });
  document.getElementById('btnZoomIn')?.addEventListener('click', () => {
    activePlot.zoomIn?.();
  });
  document.getElementById('btnZoomOut')?.addEventListener('click', () => {
    activePlot.zoomOut?.();
  });

  document.getElementById('btnOtaEnter')?.addEventListener('click', () => {
    sendOTAFromInputs(1);
  });
  document.getElementById('btnOtaExit')?.addEventListener('click', () => {
    sendOTAFromInputs(0);
  });

  document.getElementById('btnSaveRetention')?.addEventListener('click', () => {
    saveRetentionFromInputs();
  });

  document.getElementById('btnSavePublicPlot')?.addEventListener('click', () => {
    savePublicPlotFromInputs();
  });
  document.getElementById('btnPreviewPublicPlot')?.addEventListener('click', () => {
    const spec = getPublicPlotSpecFromInputs();
    if (!spec || !Array.isArray(spec.topics) || spec.topics.length === 0) {
      alert('Add at least one topic to preview.');
      return;
    }
    activePlot = previewPlot;
    previewPlot.plotFromSpec(spec);
  });
  document.getElementById('btnRefreshPublicPlots')?.addEventListener('click', () => {
    refreshPublicPlots();
  });

  // Public plots structured editor
  initPublicPlotsUI();

  // --- Topics list load + periodic refresh ---
  const refreshTopics = () => loadTopics({
    onSelectTopic: (topic) => {
      singlePlot.invalidateBounds(topic);
      activePlot = singlePlot;
      singlePlot.plotFromInputs();
    }
  });

  refreshTopics();
  setInterval(refreshTopics, 10000);

  // --- Public plot list ---
  if (document.getElementById('public_plots_list')) refreshPublicPlots();
});
