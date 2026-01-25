import {
  getTopics,
  deleteTopic,
  deleteRootTopic,
  getValidationRules,
  saveValidationRule,
  getRetentionPolicies,
  saveRetentionPolicy,
  saveTopicMeta
} from '../api.js';

// Topics list UI (admin-only) — hierarchical root/subtopic table (0.8.x)

function topicRootName(topic) {
  const parts = String(topic || '').split('/').filter(Boolean);
  return parts.length ? parts[0] : '';
}

export async function loadTopics({ onSelectTopic } = {}) {
  const res = await getTopics();
  const validationMap = await safeFetchValidationRules();
  const retentionMap = await safeFetchRetentionPolicies();

  const div = document.getElementById('topics');
  if (!div) return;

  div.innerHTML = '';

  const table = document.createElement('table');
  table.className = 'topics-table';

  const thead = document.createElement('thead');
  thead.innerHTML = `
    <tr>
      <th style="width: 34%;">Topic</th>
      <th style="width: 9%;">Msgs</th>
      <th style="width: 47%;">Configuration</th>
      <th style="width: 10%;">Actions</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement('tbody');

  // Group by root
  const roots = {};
  for (const t of (res || [])) {
    const r = topicRootName(t.topic);
    if (!roots[r]) roots[r] = [];
    roots[r].push(t);
  }

  const rootNames = Object.keys(roots).sort((a, b) => a.localeCompare(b));
  for (const root of rootNames) {
    const items = roots[root].sort((a, b) => a.topic.localeCompare(b.topic));
    const rootTopicDisplay = `/${root}`;

    // Root row
    const rootRow = document.createElement('tr');

    const tdTopic = document.createElement('td');
    tdTopic.className = 'topic-root';
    tdTopic.textContent = rootTopicDisplay;
    rootRow.appendChild(tdTopic);

    const tdCount = document.createElement('td');
    const rootCount = items.reduce((acc, x) => acc + (Number(x.count) || 0), 0);
    tdCount.textContent = String(rootCount);
    rootRow.appendChild(tdCount);

    const tdConfig = document.createElement('td');
    const pol = retentionMap[root] || {};
    tdConfig.appendChild(retentionControls(root, pol));
    rootRow.appendChild(tdConfig);

    const tdActions = document.createElement('td');
    const delRoot = document.createElement('button');
    delRoot.textContent = 'Delete';
    delRoot.addEventListener('click', async () => {
      if (!confirm(`Delete ALL data for root "/${root}" and all subtopics?`)) return;
      try {
        await deleteRootTopic(root);
        await loadTopics({ onSelectTopic });
      } catch {
        alert('Delete failed (are you logged in as admin?)');
      }
    });
    tdActions.appendChild(delRoot);
    rootRow.appendChild(tdActions);

    tbody.appendChild(rootRow);

    // Subtopic rows
    for (const t of items) {
      const row = document.createElement('tr');

      const tdT = document.createElement('td');
      tdT.className = 'topic-sub';
      const label = document.createElement('span');
      label.className = 'topic';
      label.textContent = t.topic;
      label.style.cursor = 'pointer';
      label.addEventListener('click', () => {
        if (typeof onSelectTopic === 'function') onSelectTopic(t.topic);
      });
      tdT.appendChild(label);
      row.appendChild(tdT);

      const tdC = document.createElement('td');
      tdC.textContent = String(t.count ?? '');
      row.appendChild(tdC);

      const tdConfig2 = document.createElement('td');
      tdConfig2.appendChild(topicSettingsControls(t, validationMap));
      row.appendChild(tdConfig2);

      const tdA = document.createElement('td');
      const del = document.createElement('button');
      del.textContent = 'Delete';
      del.addEventListener('click', async () => {
        if (!confirm(`Delete ALL data for topic "${t.topic}"?`)) return;
        try {
          await deleteTopic(t.topic);
          await loadTopics({ onSelectTopic });
        } catch {
          alert('Delete failed (are you logged in as admin?)');
        }
      });
      tdA.appendChild(del);
      row.appendChild(tdA);

      tbody.appendChild(row);
    }
  }

  table.appendChild(tbody);
  div.appendChild(table);
}

function retentionControls(rootName, pol) {
  const wrap = document.createElement('div');
  wrap.style.display = 'flex';
  wrap.style.flexWrap = 'wrap';
  wrap.style.gap = '8px';
  wrap.style.alignItems = 'center';

  const age = document.createElement('input');
  age.type = 'number';
  age.min = '1';
  age.placeholder = 'Max age (days)';
  age.className = 'topic-input-compact';
  if (pol?.max_age_days) age.value = String(pol.max_age_days);

  const rows = document.createElement('input');
  rows.type = 'number';
  rows.min = '1';
  rows.placeholder = 'Max rows';
  rows.className = 'topic-input-compact';
  if (pol?.max_rows) rows.value = String(pol.max_rows);

  const btn = document.createElement('button');
  btn.textContent = 'Save';
  btn.addEventListener('click', async () => {
    try {
      await saveRetentionPolicy({
        top_level: rootName,
        max_age_days: age.value,
        max_rows: rows.value
      });
      btn.textContent = 'Saved';
      setTimeout(() => (btn.textContent = 'Save'), 1200);
    } catch {
      alert('Failed to save retention (are you logged in as admin?)');
    }
  });

  wrap.appendChild(age);
  wrap.appendChild(rows);
  wrap.appendChild(btn);
  return wrap;
}

function topicSettingsControls(topicRow, validationMap) {
  const topic = topicRow.topic;
  const rule = validationMap[topic] || { min_value: null, max_value: null, enabled: false };

  // Layout requirement:
  //  - Line 1: Min Value + Max Value
  //  - Line 2: Units dropdown + Min Tick
  //  - Save button to the right spanning both lines

  const wrap = document.createElement('div');
  wrap.style.display = 'flex';
  wrap.style.gap = '10px';
  wrap.style.alignItems = 'stretch';
  wrap.style.width = '100%';

  const left = document.createElement('div');
  left.style.display = 'flex';
  left.style.flexDirection = 'column';
  left.style.gap = '6px';
  left.style.flex = '1 1 auto';

  const row1 = document.createElement('div');
  row1.style.display = 'flex';
  row1.style.gap = '8px';
  row1.style.alignItems = 'center';

  const row2 = document.createElement('div');
  row2.style.display = 'flex';
  row2.style.gap = '8px';
  row2.style.alignItems = 'center';

  // Validation inputs — automatic enable if any entry exists
  const minInput = document.createElement('input');
  minInput.className = 'validation-input topic-input-compact';
  minInput.type = 'text';
  minInput.inputMode = 'decimal';
  minInput.placeholder = 'Min Value';
  minInput.value = rule.min_value === null || rule.min_value === undefined ? '' : String(rule.min_value);
  minInput.maxLength = 10;

  const maxInput = document.createElement('input');
  maxInput.className = 'validation-input topic-input-compact';
  maxInput.type = 'text';
  maxInput.inputMode = 'decimal';
  maxInput.placeholder = 'Max Value';
  maxInput.value = rule.max_value === null || rule.max_value === undefined ? '' : String(rule.max_value);
  maxInput.maxLength = 10;

  // Units dropdown
  const units = document.createElement('select');
  units.className = 'select-compact';
  units.innerHTML = `
    <option value="">Units (—)</option>
    <option value="distance_m">Distance (m)</option>
    <option value="distance_ftin">Distance (ft/in)</option>
    <option value="temp_f">Temperature (°F)</option>
    <option value="temp_c">Temperature (°C)</option>
    <option value="pressure_kpa">Pressure (kPa)</option>
    <option value="humidity_rh">Humidity (%RH)</option>
    <option value="voltage_v">Voltage (V)</option>
    <option value="other">Other</option>
  `;
  if (topicRow.units) units.value = topicRow.units;

  // Minimum tick size
  const minTick = document.createElement('input');
  minTick.type = 'text';
  minTick.inputMode = 'decimal';
  minTick.placeholder = 'Min tick';
  minTick.className = 'topic-input-compact';
  minTick.value = topicRow.min_tick_size === null || topicRow.min_tick_size === undefined ? '' : String(topicRow.min_tick_size);
  minTick.maxLength = 10;

  const saveBtn = document.createElement('button');
  saveBtn.textContent = 'Save';
  saveBtn.style.minWidth = '74px';
  saveBtn.style.height = '100%';

  const status = document.createElement('span');
  status.className = 'validation-status';
  status.style.display = 'block';
  status.style.marginTop = '6px';

  function clampLen(el) {
    el.addEventListener('input', () => {
      if (el.value && el.value.length > 10) el.value = el.value.slice(0, 10);
    });
  }
  clampLen(minInput);
  clampLen(maxInput);
  clampLen(minTick);

  saveBtn.addEventListener('click', async () => {
    status.textContent = '';
    await saveValidationForTopic(topic, minInput, maxInput, status);
    await saveTopicMetaForTopic(topic, units, minTick, status);
  });

  row1.appendChild(minInput);
  row1.appendChild(maxInput);
  row2.appendChild(units);
  row2.appendChild(minTick);
  left.appendChild(row1);
  left.appendChild(row2);

  const right = document.createElement('div');
  right.style.display = 'flex';
  right.style.flexDirection = 'column';
  right.style.justifyContent = 'center';
  right.style.alignItems = 'flex-start';
  right.appendChild(saveBtn);
  right.appendChild(status);

  wrap.appendChild(left);
  wrap.appendChild(right);

  return wrap;
}

async function saveValidationForTopic(topic, minInput, maxInput, statusEl) {
  const minStr = (minInput?.value || '').trim();
  const maxStr = (maxInput?.value || '').trim();
  const enabled = !!(minStr || maxStr);

  const payload = {
    topic,
    min_value: minStr === '' ? null : Number(minStr),
    max_value: maxStr === '' ? null : Number(maxStr),
    enabled
  };

  // Basic client-side validation
  if (payload.min_value !== null && Number.isNaN(payload.min_value)) {
    statusEl.textContent = 'Min invalid';
    return;
  }
  if (payload.max_value !== null && Number.isNaN(payload.max_value)) {
    statusEl.textContent = 'Max invalid';
    return;
  }
  if (payload.min_value !== null && payload.max_value !== null && payload.min_value > payload.max_value) {
    statusEl.textContent = 'Min > Max';
    return;
  }

  try {
    await saveValidationRule(payload);
    statusEl.textContent = 'Saved';
  } catch {
    statusEl.textContent = 'Save failed';
  }
}

async function saveTopicMetaForTopic(topic, unitsEl, minTickEl, statusEl) {
  const units = (unitsEl?.value || '').trim() || null;
  const mtsStr = (minTickEl?.value || '').trim();
  let mts = null;
  if (mtsStr !== '') {
    mts = Number(mtsStr);
    if (Number.isNaN(mts) || mts <= 0) {
      statusEl.textContent = 'Min tick invalid';
      return;
    }
  }
  try {
    await saveTopicMeta({ topic, units, min_tick_size: mts });
    // leave status as-is (validation may have set it)
  } catch {
    statusEl.textContent = 'Save failed';
  }
}

async function safeFetchValidationRules() {
  try {
    const rules = await getValidationRules();
    const map = {};
    (rules || []).forEach(r => {
      map[r.topic] = r;
    });
    return map;
  } catch {
    return {};
  }
}

async function safeFetchRetentionPolicies() {
  try {
    const rules = await getRetentionPolicies();
    const map = {};
    (rules || []).forEach(r => {
      map[r.top_level] = r;
    });
    return map;
  } catch {
    return {};
  }
}
