import { sendOTA as apiSendOTA, saveRetentionPolicy } from '../api.js';

export async function sendOTAFromInputs(otaValue) {
  const base = (document.getElementById('otaBase')?.value || '').trim();
  if (!base) {
    alert('Enter base topic');
    return;
  }
  try {
    await apiSendOTA(base, otaValue);
    alert('OTA command sent');
  } catch {
    alert('OTA failed (are you logged in as admin?)');
  }
}

export async function saveRetentionFromInputs() {
  const top_level = (document.getElementById('ret_top_level')?.value || '').trim();
  const max_age_days = document.getElementById('ret_max_age_days')?.value;
  const max_rows = document.getElementById('ret_max_rows')?.value;
  const statusEl = document.getElementById('retention_status');
  if (!statusEl) return;

  if (!top_level) {
    statusEl.textContent = 'Error: top_level is required.';
    return;
  }

  try {
    const js = await saveRetentionPolicy({ top_level, max_age_days, max_rows });
    statusEl.textContent = JSON.stringify(js, null, 2);
  } catch (e) {
    statusEl.textContent = JSON.stringify(e?.json || { error: e?.message || 'request failed' }, null, 2);
  }
}
