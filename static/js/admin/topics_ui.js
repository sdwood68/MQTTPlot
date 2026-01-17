import { getTopics, setTopicVisibility, deleteTopic, getValidationRules, saveValidationRule } from '../api.js';

// Topics list UI (admin-only)

export async function loadTopics({ onSelectTopic } = {}) {
  const res = await getTopics();
  const validationMap = await safeFetchValidationRules();

  const div = document.getElementById('topics');
  const list = document.getElementById('topiclist');
  if (!div || !list) return;

  div.innerHTML = '';
  list.innerHTML = '';

  for (const t of res) {
    const row = document.createElement('div');
    row.className = 'topic-row';

    const label = document.createElement('span');
    label.className = 'topic';
    label.textContent = t.topic;
    label.addEventListener('click', () => {
      document.getElementById('topicInput').value = t.topic;
      if (typeof onSelectTopic === 'function') onSelectTopic(t.topic);
    });

    row.appendChild(label);
    row.appendChild(document.createTextNode(` — ${t.count} msgs `));

    // Visibility toggle
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = t.public !== 0;
    chk.title = 'Publicly visible';
    chk.style.marginLeft = '10px';
    chk.addEventListener('change', async () => {
      try {
        await setTopicVisibility(t.topic, chk.checked);
      } catch {
        alert('Failed to update visibility (are you logged in as admin?)');
      }
    });
    row.appendChild(chk);

    // Delete button
    const del = document.createElement('button');
    del.textContent = 'Delete';
    del.style.marginLeft = '6px';
    del.addEventListener('click', async () => {
      if (!confirm(`Delete ALL data for topic "${t.topic}"?`)) return;
      try {
        await deleteTopic(t.topic);
        await loadTopics({ onSelectTopic });
      } catch {
        alert('Delete failed (are you logged in as admin?)');
      }
    });
    row.appendChild(del);

    // Validation controls
    const rule = validationMap[t.topic] || { min_value: null, max_value: null, enabled: true };

    const vLabel = document.createElement('span');
    vLabel.className = 'validation-label';
    vLabel.textContent = 'Valid range:';
    row.appendChild(vLabel);

    const minInput = document.createElement('input');
    minInput.className = 'validation-input';
    minInput.type = 'number';
    minInput.step = 'any';
    minInput.placeholder = rule.min_value === null || rule.min_value === undefined ? '' : String(rule.min_value);
    minInput.title = 'Min value (leave blank for no minimum)';
    row.appendChild(minInput);

    const maxInput = document.createElement('input');
    maxInput.className = 'validation-input';
    maxInput.type = 'number';
    maxInput.step = 'any';
    maxInput.placeholder = rule.max_value === null || rule.max_value === undefined ? '' : String(rule.max_value);
    maxInput.title = 'Max value (leave blank for no maximum)';
    row.appendChild(maxInput);

    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.checked = !!rule.enabled;
    enabled.title = 'Enable validation for this topic';
    enabled.style.marginLeft = '8px';
    row.appendChild(enabled);

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.marginLeft = '6px';
    row.appendChild(saveBtn);

    const status = document.createElement('span');
    status.className = 'validation-status';
    row.appendChild(status);

    saveBtn.addEventListener('click', async () => {
      await saveValidationForTopic(t.topic, minInput, maxInput, enabled, status);
    });

    div.appendChild(row);

    const opt = document.createElement('option');
    opt.value = t.topic;
    list.appendChild(opt);
  }
}

async function safeFetchValidationRules() {
  try {
    const rules = await getValidationRules();
    const map = {};
    (rules || []).forEach(r => {
      map[r.topic] = {
        min_value: r.min_value,
        max_value: r.max_value,
        enabled: r.enabled !== 0
      };
    });
    return map;
  } catch {
    return {};
  }
}

async function saveValidationForTopic(topic, minInputEl, maxInputEl, enabledEl, statusEl) {
  const min_value = minInputEl.value;
  const max_value = maxInputEl.value;
  const enabled = enabledEl.checked;

  statusEl.textContent = 'Saving...';

  try {
    const js = await saveValidationRule({ topic, min_value, max_value, enabled });

    const savedMin = js.min_value === null || js.min_value === undefined ? '' : String(js.min_value);
    const savedMax = js.max_value === null || js.max_value === undefined ? '' : String(js.max_value);

    minInputEl.placeholder = savedMin;
    maxInputEl.placeholder = savedMax;
    minInputEl.value = '';
    maxInputEl.value = '';

    statusEl.textContent = 'Saved.';
  } catch (e) {
    const msg = e?.json?.error || e?.message || 'request failed';
    statusEl.textContent = `Error: ${msg}`;
  }
}
