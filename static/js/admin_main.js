import { initMqttStatusPolling } from './mqtt_status.js';
import { loadTopics } from './admin/topics_ui.js';
import { SingleTopicPlot } from './admin/plot_single.js';
import { MultiTopicPlotPreview } from './admin/plot_multi.js';
import { sendOTAFromInputs } from './admin/ota_retention.js';
import { getAdminSettings, saveAdminSettings } from './api.js';
import { refreshPublicPlots, savePublicPlotFromInputs, initPublicPlotsUI, getPublicPlotSpecFromInputs } from './admin/public_plots_ui.js';

// Admin entrypoint: wires UI, socket.io, and periodic refresh.

document.addEventListener('DOMContentLoaded', () => {
  initMqttStatusPolling({ intervalMs: 5000 });


  // --- Admin settings (time zone, broker) ---
  initAdminSettings();

  async function initAdminSettings() {
    const tzEl = document.getElementById('admin_tz');
    const hostEl = document.getElementById('broker_host');
    const portEl = document.getElementById('broker_port');
    const topicsEl = document.getElementById('broker_topics');
    const tzStatus = document.getElementById('tz_status');
    const brokerStatus = document.getElementById('broker_status');

    try {
      const s = await getAdminSettings();
      if (tzEl && s?.timezone) tzEl.value = s.timezone;
      if (hostEl && s?.broker?.host) hostEl.value = s.broker.host;
      if (portEl && s?.broker?.port) portEl.value = s.broker.port;
      if (topicsEl && s?.broker?.topics) topicsEl.value = s.broker.topics;
    } catch (e) {
      // Non-fatal
      if (tzStatus) tzStatus.textContent = 'Unable to load settings';
      if (brokerStatus) brokerStatus.textContent = 'Unable to load settings';
    }

    document.getElementById('btnSaveTz')?.addEventListener('click', async () => {
      if (!tzEl) return;
      const timezone = (tzEl.value || '').trim();
      try {
        await saveAdminSettings({ timezone });
        if (tzStatus) tzStatus.textContent = 'Saved';
      } catch {
        if (tzStatus) tzStatus.textContent = 'Save failed';
        alert('Failed to save time zone (are you logged in as admin?)');
      }
    });

    document.getElementById('btnSaveBroker')?.addEventListener('click', async () => {
      const broker_host = (hostEl?.value || '').trim();
      const broker_port = portEl?.value;
      const broker_topics = (topicsEl?.value || '').trim();
      try {
        await saveAdminSettings({ broker_host, broker_port, broker_topics });
        if (brokerStatus) brokerStatus.textContent = 'Saved';
      } catch {
        if (brokerStatus) brokerStatus.textContent = 'Save failed';
        alert('Failed to save broker settings (are you logged in as admin?)');
      }
    });
  }

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
    activePlot.slideWindow?.(-1.0);
  });
  document.getElementById('btnFwd')?.addEventListener('click', () => {
    activePlot.slideWindow?.(1.0);
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
