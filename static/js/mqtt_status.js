import { getMqttStatus } from './api.js';

function formatCountdownSeconds(nextRetryTs) {
  if (!nextRetryTs) return null;
  const now = Date.now() / 1000;
  const delta = Math.ceil(nextRetryTs - now);
  return delta > 0 ? delta : 0;
}

export function initMqttStatusPolling({ intervalMs = 5000 } = {}) {
  const el = document.getElementById('mqtt-status');
  if (!el) return;

  async function refresh() {
    try {
      const s = await getMqttStatus();

      if (s.connected) {
        el.className = 'mqtt-status mqtt-status--ok';
        el.textContent = 'MQTT: Connected';
        return;
      }

      const retryIn = formatCountdownSeconds(s.next_retry_ts);
      const parts = ['MQTT: Disconnected'];
      if (s.last_error) parts.push(`(${s.last_error})`);
      if (typeof retryIn === 'number') parts.push(`— retry in ${retryIn}s`);

      el.className = 'mqtt-status mqtt-status--down';
      el.textContent = parts.join(' ');
    } catch {
      el.className = 'mqtt-status mqtt-status--unknown';
      el.textContent = 'MQTT: Status unavailable';
    }
  }

  refresh();
  setInterval(refresh, intervalMs);
}
