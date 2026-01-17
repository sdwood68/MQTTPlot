import { initMqttStatusPolling } from './mqtt_status.js';

document.addEventListener('DOMContentLoaded', () => {
  initMqttStatusPolling({ intervalMs: 5000 });
});
