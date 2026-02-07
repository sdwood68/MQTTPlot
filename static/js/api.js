// Shared API helpers for MQTTPlot


function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el ? el.getAttribute('content') : null;
}

async function _fetchText(url, options) {
  const opts = options ? { ...options } : {};
  if (!("credentials" in opts)) opts.credentials = "same-origin";
  // Add CSRF token automatically for admin state-changing calls
  const method = (opts.method || "GET").toUpperCase();
  if (url.startsWith("/api/admin/") && method !== "GET") {
    const t = getCsrfToken();
    if (t) {
      opts.headers = opts.headers ? { ...opts.headers } : {};
      if (!("X-CSRF-Token" in opts.headers)) opts.headers["X-CSRF-Token"] = t;
    }
  }
  const resp = await fetch(url, opts);
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

export async function getTopicMeta(topic) {
  // Try exact topic first; if metadata is missing and the topic starts with '/', retry without the leading slash.
  const t = (topic || '').toString();
  const meta = await fetchJson(`/api/topic_meta?topic=${encodeURIComponent(t)}`);
  if (meta && meta.units == null && meta.min_tick_size == null) {
    const t2 = t.replace(/^\/+/, '');
    if (t2 && t2 !== t) {
      const meta2 = await fetchJson(`/api/topic_meta?topic=${encodeURIComponent(t2)}`);
      // Preserve the original topic string for callers, but use any discovered metadata.
      if (meta2 && (meta2.units != null || meta2.min_tick_size != null)) {
        return { ...meta2, topic: t };
      }
    }
  }
  return meta;
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
  // Use JSON-body endpoint to avoid encoded-slash path issues on some servers/proxies.
  const { resp, text } = await _fetchText(`/api/admin/topic_delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic })
  });
  if (!resp.ok) {
    const err = new Error(`HTTP ${resp.status} ${resp.statusText}`);
    err.status = resp.status;
    err.body = text;
    throw err;
  }
  return true;
}

// Delete a root topic (e.g. "watergauge") and all its subtopics.
export async function deleteRootTopic(rootName) {
  const root = String(rootName || '').trim().replace(/^\/+|\/+$/g, '');
  if (!root) {
    throw new Error('Missing root topic');
  }
  const { resp, text } = await _fetchText(`/api/admin/root_delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ root })
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

export async function getRetentionPolicies() {
  return fetchJson('/api/admin/retention');
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


export async function getAdminSettings() {
  return fetchJson('/api/admin/settings');
}

export async function saveAdminSettings(payload) {
  return fetchJson('/api/admin/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function saveTopicMeta(payload) {
  return fetchJson('/api/admin/topic_meta', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}
