import { initMqttStatusPolling } from './mqtt_status.js';
import { loadTopics } from './admin/topics_ui.js';
import { sendOTAFromInputs, saveRetentionFromInputs } from './admin/ota_retention.js';
import { getAdminSettings, saveAdminSettings } from './api.js';
import {
  refreshPublicPlots,
  savePublicPlotFromInputs,
  initPublicPlotsUI,
  getPublicPlotSpecFromInputs
} from './admin/public_plots_ui.js';

// Admin entrypoint: wires UI and periodic refresh.

const SPEC_KEY = 'mqttplot.plotSpec';

function openPlotWindow(spec) {
  if (!spec) return;

  try {
    localStorage.setItem(SPEC_KEY, JSON.stringify(spec));
  } catch (e) {
    console.error('Failed to persist plot spec:', e);
    alert('Failed to open plot window (could not store plot spec).');
    return;
  }

  // Reuse the same named window to avoid spam.
  const w = window.open('/admin/plot_window', 'mqttplot_plot', 'width=1200,height=800');
  if (!w) {
    alert('Popup blocked. Allow popups for this site to preview plots.');
    return;
  }
  try { w.focus(); } catch {}
}

function openTopicPlotWindow(topic) {
  const t = String(topic || '').trim();
  if (!t) return;
  const url = `/admin/topic_plot?topic=${encodeURIComponent(t)}`;
  const w = window.open(url, 'mqttplot_plot', 'width=1200,height=800');
  if (!w) {
    alert('Popup blocked. Allow popups for this site to view plots.');
    return;
  }
  try { w.focus(); } catch {}
}

// Single-topic plotting is initiated by clicking a topic in the Topics table.

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
      const settings = await getAdminSettings();
      if (tzEl && settings.timezone) tzEl.value = settings.timezone;
      if (hostEl && settings.broker_host) hostEl.value = settings.broker_host;
      if (portEl && settings.broker_port) portEl.value = settings.broker_port;
      if (topicsEl && settings.broker_topics) topicsEl.value = settings.broker_topics;
    } catch {
      // ignore; admin settings optional
    }

    document.getElementById('btnSaveTz')?.addEventListener('click', async () => {
      const timezone = (tzEl?.value || '').trim();
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

  // --- Plot wiring (popup windows) ---

  document.getElementById('btnPreviewPublicPlot')?.addEventListener('click', () => {
    const spec = getPublicPlotSpecFromInputs();
    if (!spec || !Array.isArray(spec.topics) || spec.topics.length === 0) {
      alert('Add at least one topic to preview.');
      return;
    }
    openPlotWindow(spec);
  });

  // --- OTA / retention / public plots ---
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

  // Public plots structured editor
  initPublicPlotsUI();

  // --- Topics list load + periodic refresh ---
  const refreshTopics = () => loadTopics({
    onSelectTopic: (topic) => {
      openTopicPlotWindow(topic);
    }
  });

  refreshTopics();
  // No periodic refresh here: it resets form inputs. UI updates are event-driven.
  // --- Public plot list ---
  if (document.getElementById('public_plots_list')) refreshPublicPlots();
});
