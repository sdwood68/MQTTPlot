// UnifiedPlot
//
// v0.8.0 admin popup plots should support 1 or 2 topics with a single implementation.
// Rather than duplicating the multi-topic preview logic, we delegate to the existing
// MultiTopicPlotPreview and normalize the PlotSpec to 1–2 topics.

import { MultiTopicPlotPreview } from './plot_multi.js';

function normalizeSpec(spec) {
  const s = spec ? JSON.parse(JSON.stringify(spec)) : {};
  const topics = Array.isArray(s.topics) ? s.topics : [];

  // Keep at most 2 topics.
  const cleaned = topics
    .map((t) => ({
      name: String(t?.name || '').trim(),
      label: String(t?.label || '').trim() || null,
      yAxis: (t?.yAxis === 'y2') ? 'y2' : 'y',
      mode: String(t?.mode || 'lines')
    }))
    .filter((t) => t.name.length > 0)
    .slice(0, 2);

  // If 2 topics were provided but both target the same axis, default the second to y2.
  if (cleaned.length === 2 && cleaned[0].yAxis === cleaned[1].yAxis) {
    cleaned[1].yAxis = 'y2';
  }

  s.topics = cleaned;

  // Default time window (4h) if missing.
  if (!s.time) s.time = { kind: 'relative', seconds: 4 * 60 * 60 };
  if (!s.time.seconds) s.time.seconds = 4 * 60 * 60;

  return s;
}

export class UnifiedPlot {
  constructor({ plotDivId = 'plot' } = {}) {
    this.impl = new MultiTopicPlotPreview({ plotDivId });
  }

  async plotFromSpec(spec) {
    return this.impl.plotFromSpec(normalizeSpec(spec));
  }

  handleLiveMessage(msg) {
    return this.impl.handleLiveMessage(msg);
  }

  slideWindow(dir) {
    return this.impl.slideWindow(dir);
  }

  zoomIn() {
    return this.impl.zoomIn();
  }

  zoomOut() {
    return this.impl.zoomOut();
  }
}
