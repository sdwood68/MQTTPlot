import {
  getTopics,
  listAdminPublicPlots,
  getAdminPublicPlot,
  saveAdminPublicPlot,
  deleteAdminPublicPlot
} from '../api.js';

function $(id) { return document.getElementById(id); }

function setStatus(text) {
  const el = $('public_plots_status');
  if (el) el.textContent = text || '';
}

function yAxisSelect(value = 'y') {
  const sel = document.createElement('select');
  for (const v of ['y', 'y2']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === (value || 'y')) opt.selected = true;
    sel.appendChild(opt);
  }
  return sel;
}

function modeSelect(value = 'lines') {
  const sel = document.createElement('select');
  const modes = [
    { v: 'lines', t: 'lines' },
    { v: 'markers', t: 'markers' },
    { v: 'lines+markers', t: 'lines+markers' },
  ];
  for (const m of modes) {
    const opt = document.createElement('option');
    opt.value = m.v;
    opt.textContent = m.t;
    if (m.v === (value || 'lines')) opt.selected = true;
    sel.appendChild(opt);
  }
  return sel;
}

function createTopicRow(topicSpec = {}) {
  const tbody = $('pp_topics_tbody');
  if (!tbody) return;

  const tr = document.createElement('tr');

  const tdTopic = document.createElement('td');
  tdTopic.style.padding = '4px';
  const topicInput = document.createElement('input');
  topicInput.placeholder = '/watergauge/temp1';
  topicInput.style.width = '340px';
  topicInput.setAttribute('list', 'topiclist'); // reuse existing datalist
  topicInput.value = topicSpec?.name || '';
  topicInput.className = 'pp_topic_name';
  tdTopic.appendChild(topicInput);

  const tdLabel = document.createElement('td');
  tdLabel.style.padding = '4px';
  const labelInput = document.createElement('input');
  labelInput.placeholder = 'Legend label (optional)';
  labelInput.style.width = '220px';
  labelInput.value = topicSpec?.label || '';
  labelInput.className = 'pp_topic_label';
  tdLabel.appendChild(labelInput);

  const tdYAxis = document.createElement('td');
  tdYAxis.style.padding = '4px';
  const ySel = yAxisSelect(topicSpec?.yAxis || 'y');
  ySel.className = 'pp_topic_yaxis';
  tdYAxis.appendChild(ySel);

  const tdMode = document.createElement('td');
  tdMode.style.padding = '4px';
  const mSel = modeSelect(topicSpec?.mode || 'lines');
  mSel.className = 'pp_topic_mode';
  tdMode.appendChild(mSel);

  const tdActions = document.createElement('td');
  tdActions.style.padding = '4px';
  const btnDel = document.createElement('button');
  btnDel.textContent = 'Remove';
  btnDel.addEventListener('click', () => tr.remove());
  tdActions.appendChild(btnDel);

  tr.appendChild(tdTopic);
  tr.appendChild(tdLabel);
  tr.appendChild(tdYAxis);
  tr.appendChild(tdMode);
  tr.appendChild(tdActions);

  tbody.appendChild(tr);
}

function readTopicsFromTable() {
  const tbody = $('pp_topics_tbody');
  if (!tbody) return [];
  const topics = [];

  for (const tr of Array.from(tbody.querySelectorAll('tr'))) {
    const name = tr.querySelector('.pp_topic_name')?.value?.trim() || '';
    const label = tr.querySelector('.pp_topic_label')?.value?.trim() || '';
    const yAxis = tr.querySelector('.pp_topic_yaxis')?.value || 'y';
    const mode = tr.querySelector('.pp_topic_mode')?.value || 'lines';
    if (!name) continue;
    topics.push({
      name,
      label: label || null,
      yAxis: (yAxis === 'y2') ? 'y2' : 'y',
      mode
    });
  }

  return topics;
}

// Builds a PlotSpec-like object from the current form inputs (used for preview).
export function getPublicPlotSpecFromInputs() {
  const title = ($('pp_title')?.value || '').trim();
  const rangeSec = parseInt($('pp_range_sec')?.value || '3600', 10);
  const topics = readTopicsFromTable();
  return {
    title: title || 'Preview',
    topics,
    time: { kind: 'relative', seconds: isFinite(rangeSec) && rangeSec > 0 ? rangeSec : 3600 },
    refresh: { enabled: false, intervalMs: 5000 }
  };
}

function clearPublicPlotForm() {
  if ($('pp_slug')) $('pp_slug').value = '';
  if ($('pp_title')) $('pp_title').value = '';
  if ($('pp_description')) $('pp_description').value = '';
  if ($('pp_range_sec')) $('pp_range_sec').value = '3600';
  if ($('pp_published')) $('pp_published').checked = true;
  const tbody = $('pp_topics_tbody');
  if (tbody) tbody.innerHTML = '';
  createTopicRow();
  setStatus('');
}

async function ensureTopicsDatalistPopulated() {
  const dl = $('topiclist');
  if (!dl) return;
  if (dl.dataset.populated === '1') return;

  try {
    const topics = await getTopics();
    dl.innerHTML = '';
    for (const t of topics) {
      const opt = document.createElement('option');
      opt.value = t.topic;
      dl.appendChild(opt);
    }
    dl.dataset.populated = '1';
  } catch {
    // ignore; admin can still type manually
  }
}

export async function refreshPublicPlots() {
  const listEl = $('public_plots_list');
  if (!listEl) return;
  listEl.innerHTML = '';
  setStatus('');

  try {
    const plots = await listAdminPublicPlots();
    const ul = document.createElement('ul');
    for (const p of plots) {
      const li = document.createElement('li');

      const a = document.createElement('a');
      a.href = `/p/${p.slug}`;
      a.textContent = p.title ? `${p.title} (/p/${p.slug})` : `/p/${p.slug}`;
      a.target = '_blank';
      li.appendChild(a);

      const meta = document.createElement('span');
      meta.style.marginLeft = '10px';
      meta.style.opacity = '0.85';
      meta.textContent = p.published ? 'published' : 'unpublished';
      li.appendChild(meta);

      const btnEdit = document.createElement('button');
      btnEdit.textContent = 'Edit';
      btnEdit.style.marginLeft = '10px';
      btnEdit.addEventListener('click', async () => {
        try {
          const full = await getAdminPublicPlot(p.slug);
          await loadPublicPlotIntoForm(full);
          setStatus(`Loaded ${p.slug} for editing.`);
        } catch (e) {
          setStatus(`Edit failed: ${e?.status || ''} ${e?.statusText || e?.message || ''}`.trim());
        }
      });
      li.appendChild(btnEdit);

      const del = document.createElement('button');
      del.textContent = 'Delete';
      del.style.marginLeft = '10px';
      del.addEventListener('click', async () => {
        if (!confirm(`Delete public plot "${p.slug}"?`)) return;
        try {
          await deleteAdminPublicPlot(p.slug);
          await refreshPublicPlots();
        } catch (e) {
          setStatus(`Delete failed: ${e?.status || ''} ${e?.statusText || e?.message || ''}`.trim());
        }
      });
      li.appendChild(del);

      ul.appendChild(li);
    }
    listEl.appendChild(ul);
  } catch (e) {
    setStatus(`Error: ${e?.status || ''} ${e?.statusText || e?.message || ''}`.trim());
  }
}

async function loadPublicPlotIntoForm(plot) {
  await ensureTopicsDatalistPopulated();

  if ($('pp_slug')) $('pp_slug').value = plot.slug || '';
  if ($('pp_title')) $('pp_title').value = plot.title || '';
  if ($('pp_description')) $('pp_description').value = plot.description || '';
  if ($('pp_published')) $('pp_published').checked = !!plot.published;

  const rangeSec = plot?.spec?.time?.seconds;
  if ($('pp_range_sec')) $('pp_range_sec').value = String(Number(rangeSec || 3600));

  const tbody = $('pp_topics_tbody');
  if (tbody) tbody.innerHTML = '';

  const topics = Array.isArray(plot?.spec?.topics) ? plot.spec.topics : [];
  if (topics.length === 0) {
    createTopicRow();
  } else {
    for (const t of topics) createTopicRow(t);
  }
}

export async function savePublicPlotFromInputs() {
  const slug = ($('pp_slug')?.value || '').trim();
  const title = ($('pp_title')?.value || '').trim();
  const description = ($('pp_description')?.value || '').trim();
  const rangeSec = parseInt($('pp_range_sec')?.value || '3600', 10);
  const published = !!$('pp_published')?.checked;

  if (!slug) {
    setStatus('Error: slug is required.');
    return;
  }

  const topics = readTopicsFromTable();
  if (topics.length === 0) {
    setStatus('Error: add at least one topic.');
    return;
  }

  const spec = {
    title: title || null,
    topics,
    time: { kind: 'relative', seconds: isFinite(rangeSec) && rangeSec > 0 ? rangeSec : 3600 },
    refresh: { enabled: true, intervalMs: 5000 }
  };

  try {
    const js = await saveAdminPublicPlot({
      slug,
      title: title || null,
      description: description || null,
      published,
      spec
    });
    setStatus(JSON.stringify(js, null, 2));
    await refreshPublicPlots();
  } catch (e) {
    setStatus(JSON.stringify(e?.json || { error: e?.message || 'request failed' }, null, 2));
  }
}

export function initPublicPlotsUI() {
  // Add at least one row on load
  if ($('pp_topics_tbody') && $('pp_topics_tbody').children.length === 0) {
    createTopicRow();
  }

  $('btnAddPublicPlotTopic')?.addEventListener('click', () => createTopicRow());
  $('btnClearPublicPlot')?.addEventListener('click', () => clearPublicPlotForm());

  // Populate datalist used by topic inputs if possible
  ensureTopicsDatalistPopulated();
}
