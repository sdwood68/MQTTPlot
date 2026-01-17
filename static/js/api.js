// Shared API helpers for MQTTPlot

async function _fetchText(url, options) {
  const resp = await fetch(url, options);
  const text = await resp.text();
  return { resp, text };
}

export async function fetchJson(url, options) {
  const { resp, text } = await _fetchText(url, options);
  let js = null;
  try {
    js = text ? JSON.parse(text) : null;
  } catch {
    // leave null
  }
  if (!resp.ok) {
    const err = new Error(`HTTP ${resp.status} ${resp.statusText}`);
    err.status = resp.status;
    err.statusText = resp.statusText;
    err.body = text;
    err.json = js;
    throw err;
  }
  return js;
}

export async function getTopics() {
  return fetchJson('/api/topics');
}

export async function getBounds(topic) {
  return fetchJson(`/api/bounds?topic=${encodeURIComponent(topic)}`);
}

export async function getData(topic, startIso, endIso) {
  let url = `/api/data?topic=${encodeURIComponent(topic)}`;
  if (startIso) url += `&start=${encodeURIComponent(startIso)}`;
  if (endIso) url += `&end=${encodeURIComponent(endIso)}`;
  return fetchJson(url);
}

// --- Admin APIs ---

export async function setTopicVisibility(topic, isPublic) {
  return fetchJson('/api/admin/topic_visibility', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, public: !!isPublic })
  });
}

export async function getValidationRules() {
  return fetchJson('/api/admin/validation');
}

export async function saveValidationRule(payload) {
  return fetchJson('/api/admin/validation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function deleteTopic(topic) {
  const { resp, text } = await _fetchText(`/api/admin/topic/${encodeURIComponent(topic)}`, {
    method: 'DELETE'
  });
  if (!resp.ok) {
    const err = new Error(`HTTP ${resp.status} ${resp.statusText}`);
    err.status = resp.status;
    err.body = text;
    throw err;
  }
  return true;
}

export async function sendOTA(baseTopic, otaValue) {
  return fetchJson('/api/admin/ota', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_topic: baseTopic, ota: otaValue })
  });
}

export async function saveRetentionPolicy(payload) {
  return fetchJson('/api/admin/retention', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function listAdminPublicPlots() {
  return fetchJson('/api/admin/public_plots');
}

export async function getAdminPublicPlot(slug) {
  return fetchJson(`/api/admin/public_plots/${encodeURIComponent(slug)}`);
}

export async function saveAdminPublicPlot(payload) {
  return fetchJson('/api/admin/public_plots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function deleteAdminPublicPlot(slug) {
  const { resp, text } = await _fetchText(`/api/admin/public_plots/${encodeURIComponent(slug)}`, {
    method: 'DELETE'
  });
  if (!resp.ok) {
    const err = new Error(`HTTP ${resp.status} ${resp.statusText}`);
    err.status = resp.status;
    err.body = text;
    throw err;
  }
  return true;
}

export async function getMqttStatus() {
  // no-store to avoid stale UI
  return fetchJson('/api/mqtt/status', { cache: 'no-store' });
}
