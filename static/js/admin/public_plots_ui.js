import { listAdminPublicPlots, saveAdminPublicPlot, deleteAdminPublicPlot } from '../api.js';

export async function refreshPublicPlots() {
  const statusEl = document.getElementById('public_plots_status');
  const listEl = document.getElementById('public_plots_list');
  if (!listEl) return;

  listEl.innerHTML = '';
  if (statusEl) statusEl.textContent = '';

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

      const del = document.createElement('button');
      del.textContent = 'Delete';
      del.style.marginLeft = '10px';
      del.addEventListener('click', async () => {
        if (!confirm(`Delete public plot "${p.slug}"?`)) return;
        try {
          await deleteAdminPublicPlot(p.slug);
          await refreshPublicPlots();
        } catch (e) {
          alert(`Delete failed: ${e?.status || ''}`.trim());
        }
      });
      li.appendChild(del);

      ul.appendChild(li);
    }
    listEl.appendChild(ul);
  } catch (e) {
    if (statusEl) statusEl.textContent = `Error: ${e?.status || ''} ${e?.statusText || e?.message || ''}`.trim();
  }
}

export async function savePublicPlotFromInputs() {
  const statusEl = document.getElementById('public_plots_status');
  const slug = (document.getElementById('pp_slug')?.value || '').trim();
  const title = (document.getElementById('pp_title')?.value || '').trim();
  const topicsText = (document.getElementById('pp_topics')?.value || '').trim();
  const rangeSec = parseInt(document.getElementById('pp_range_sec')?.value || '3600', 10);
  const published = !!document.getElementById('pp_published')?.checked;

  if (!slug) {
    if (statusEl) statusEl.textContent = 'Error: slug is required.';
    return;
  }

  const topics = topicsText
    ? topicsText.split(',').map(s => s.trim()).filter(Boolean)
    : [];

  const spec = {
    title: title || null,
    topics: topics.map(t => ({ name: t, label: null, yAxis: 'y', mode: 'lines' })),
    time: { kind: 'relative', seconds: isFinite(rangeSec) && rangeSec > 0 ? rangeSec : 3600 },
    refresh: { enabled: true, intervalMs: 5000 }
  };

  try {
    const js = await saveAdminPublicPlot({ slug, title: title || null, published, spec });
    if (statusEl) statusEl.textContent = JSON.stringify(js, null, 2);
    await refreshPublicPlots();
  } catch (e) {
    const js = e?.json || null;
    if (statusEl) statusEl.textContent = JSON.stringify(js || { error: e?.message || 'request failed' }, null, 2);
  }
}
