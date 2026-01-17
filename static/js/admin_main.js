import { initMqttStatusPolling } from './mqtt_status.js';
import { loadTopics } from './admin/topics_ui.js';
import { SingleTopicPlot } from './admin/plot_single.js';
import { sendOTAFromInputs, saveRetentionFromInputs } from './admin/ota_retention.js';
import { refreshPublicPlots, savePublicPlotFromInputs } from './admin/public_plots_ui.js';

// Admin entrypoint: wires UI, socket.io, and periodic refresh.

document.addEventListener('DOMContentLoaded', () => {
  initMqttStatusPolling({ intervalMs: 5000 });

  const plotController = new SingleTopicPlot({ plotDivId: 'plot' });

  // Socket.IO live updates (public stream)
  const socket = io();
  socket.on('new_data', (msg) => {
    plotController.handleLiveMessage(msg);
  });
  // Optional admin-only stream
  socket.on('new_data_admin', (msg) => {
    plotController.handleLiveMessage(msg);
  });

  // --- Button wiring (replaces inline onclicks) ---
  document.getElementById('btnPlot')?.addEventListener('click', () => {
    plotController.plotFromInputs();
  });
  document.getElementById('btnBack')?.addEventListener('click', () => {
    plotController.slideWindow(-0.5);
  });
  document.getElementById('btnFwd')?.addEventListener('click', () => {
    plotController.slideWindow(0.5);
  });
  document.getElementById('btnZoomIn')?.addEventListener('click', () => {
    plotController.zoomIn();
  });
  document.getElementById('btnZoomOut')?.addEventListener('click', () => {
    plotController.zoomOut();
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
  document.getElementById('btnRefreshPublicPlots')?.addEventListener('click', () => {
    refreshPublicPlots();
  });

  // --- Topics list load + periodic refresh ---
  const refreshTopics = () => loadTopics({
    onSelectTopic: (topic) => {
      plotController.invalidateBounds(topic);
      plotController.plotFromInputs();
    }
  });

  refreshTopics();
  setInterval(refreshTopics, 10000);

  // --- Public plot list ---
  if (document.getElementById('public_plots_list')) {
    refreshPublicPlots();
  }
});
