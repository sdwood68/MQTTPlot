import { getBounds as apiGetBounds, getData } from '../api.js';

// Same discrete window presets used by SingleTopicPlot
// Discrete window presets (small -> large). Span is immutable unless the user changes presets.
// v0.7.1 presets:
//   2, 4, 8, 12 hours (default = 4 hours)
//   1, 3, 5 days
//   1, 2, 4 weeks
const WINDOW_OPTIONS_MS = [
  2 * 60 * 60 * 1000,        // 2 hours
  4 * 60 * 60 * 1000,        // 4 hours (default)
  8 * 60 * 60 * 1000,        // 8 hours
  12 * 60 * 60 * 1000,       // 12 hours
  24 * 60 * 60 * 1000,       // 1 day
  3 * 24 * 60 * 60 * 1000,   // 3 days
  5 * 24 * 60 * 60 * 1000,   // 5 days
  7 * 24 * 60 * 60 * 1000,   // 1 week
  14 * 24 * 60 * 60 * 1000,  // 2 weeks
  28 * 24 * 60 * 60 * 1000   // 4 weeks
];

export class MultiTopicPlotPreview {
  constructor({ plotDivId = 'plot' } = {}) {
    this.plotDivId = plotDivId;
    this.currentSpec = null;
    this.currentStart = null;
    this.currentEnd = null;
    this.boundsCache = {}; // topic -> {min: Date, max: Date} | undefined
    this.topicToTraceIndex = new Map();
  }    this.overallMax = null;
  })

  _plotDiv() {
    return document.getElementById(this.plotDivId);
  }

  _plotIsReady() {
    const plotDiv = this._plotDiv();
    return plotDiv && Array.isArray(plotDiv.data) && plotDiv.data.length > 0;
  }

  setNavEnabled(enabled) {
    const ids = ['btnBack', 'btnFwd', 'btnZoomIn', 'btnZoomOut'];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) el.disabled = !enabled;
    }
  }

  showPlotStatus(msg) {
    const plotDiv = this._plotDiv();
    if (!plotDiv) return;
    plotDiv.innerHTML = msg ? `<div class="plot-status">${msg}</div>` : '';
  }

  setInputsFromDates(start, end) {
    const startEl = document.getElementById('start');
    const endEl = document.getElementById('end');
    if (startEl) startEl.value = start ? start.toISOString() : '';
    if (endEl) endEl.value = end ? end.toISOString() : '';
  }

  clampWindow(start, end, min, max) {
    if (start > end) {
      const tmp = start; start = end; end = tmp;
    }
    const windowMs = end - start;

    if ((max - min) <= windowMs) {
      return { start: new Date(min), end: new Date(max) };
    }

    if (start < min) {
      start = new Date(min);
      end = new Date(start.getTime() + windowMs);
    }

    if (end > max) {
      end = new Date(max);
      start = new Date(end.getTime() - windowMs);
    }

    if (start < min) start = new Date(min);
    if (end > max) end = new Date(max);
    return { start, end };
  }

  nearestWindowIndex(windowMs) {
    let bestIdx = 0;
    let bestDiff = Infinity;
    for (let i = 0; i < WINDOW_OPTIONS_MS.length; i++) {
      const diff = Math.abs(WINDOW_OPTIONS_MS[i] - windowMs);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestIdx = i;
      }
    }
    return bestIdx;
  }

  async getBounds(topic) {
    if (this.boundsCache[topic] !== undefined) return this.boundsCache[topic];
    const js = await apiGetBounds(topic);
    const b = { min: new Date(js.min_ts), max: new Date(js.max_ts) };
    this.boundsCache[topic] = b;
    return b;
  }

  invalidateBounds(topic) {
    this.boundsCache[topic] = undefined;
  }

  _getTopicsFromSpec(spec) {
    const topics = Array.isArray(spec?.topics) ? spec.topics : [];
    return topics.filter(t => (t?.name || '').trim().length > 0);
  }

  async _getOverallBounds(spec) {
    const topics = this._getTopicsFromSpec(spec);
    if (topics.length === 0) return null;

    const boundsList = await Promise.all(
      topics.map(t => this.getBounds(t.name).catch(() => null))
    );

    const ok = boundsList.filter(Boolean);
    if (ok.length === 0) return null;

    let min = ok[0].min;
    let max = ok[0].max;
    for (const b of ok) {
      if (b.min < min) min = b.min;
      if (b.max > max) max = b.max;
    }
    return { min, max };
  }

  _buildTraces(seriesByTopic, spec) {
    const traces = [];
    this.topicToTraceIndex = new Map();
    const topics = this._getTopicsFromSpec(spec);

    topics.forEach((t, idx) => {
      const rows = seriesByTopic.get(t.name) || [];
      const trace = {
        x: rows.map(r => r.ts),
        y: rows.map(r => r.value),
        type: 'scatter',
        mode: t.mode || 'lines',
        name: t.label || t.name,
        yaxis: (t.yAxis === 'y2') ? 'y2' : 'y'
      };
      traces.push(trace);
      this.topicToTraceIndex.set(t.name, idx);
    });

    return traces;
  }

  _buildLayout(spec) {
    return {
      title: spec?.title || 'Preview',
      margin: { t: 60, l: 60, r: 60, b: 40 },
      xaxis: { title: 'Time' },
      yaxis: { title: '', nticks: 6, ticks: 'outside' },
      // Align major tick marks on the secondary axis with the primary axis
      yaxis2: { title: '', overlaying: 'y', side: 'right', tickmode: 'sync', nticks: 6, ticks: 'outside' },
      legend: { orientation: 'h' }
    };
  }

  async plotFromSpec(spec) {
    if (!spec) {
      alert('No plot spec to preview.');
      return;
    }
    this.currentSpec = spec;

    const overall = await this._getOverallBounds(spec).catch(() => null);
    this.setNavEnabled(!!overall);
    this.overallMax = overall ? new Date(overall.max) : null;
    if (!overall) {
      this.currentStart = null;
      this.currentEnd = null;
      this.setInputsFromDates(null, null);
      this.showPlotStatus('No numeric data available for selected topics yet.');
      return;
    }

    // Inputs override if provided
    const startStr = document.getElementById('start')?.value || '';
    const endStr = document.getElementById('end')?.value || '';
    const startFromInputs = startStr ? new Date(startStr) : null;
    const endFromInputs = endStr ? new Date(endStr) : null;

    this.currentEnd = endFromInputs || this.currentEnd || new Date(overall.max);
    this.currentStart = startFromInputs || this.currentStart;

    if (!this.currentStart) {
      const sec = Number(spec?.time?.seconds || 3600);
      const windowMs = (isFinite(sec) && sec > 0 ? sec : 3600) * 1000;
      this.currentStart = new Date(this.currentEnd.getTime() - windowMs);
    }

    const clamped = this.clampWindow(this.currentStart, this.currentEnd, overall.min, overall.max);
    this.currentStart = clamped.start;
    this.currentEnd = clamped.end;
    this.setInputsFromDates(this.currentStart, this.currentEnd);

    const topics = this._getTopicsFromSpec(spec);
    const seriesByTopic = new Map();

    await Promise.all(topics.map(async (t) => {
      const rows = await getData(t.name, this.currentStart.toISOString(), this.currentEnd.toISOString()).catch(() => []);
      seriesByTopic.set(t.name, rows || []);
    }));

    const traces = this._buildTraces(seriesByTopic, spec);

    if (traces.every(tr => (tr.x?.length || 0) === 0)) {
      this.showPlotStatus('No numeric data in this time range.');
      return;
    }

    const layout = this._buildLayout(spec);
    const config = { responsive: true, displaylogo: false, displayModeBar: false };
    await Plotly.react(this.plotDivId, traces, layout, config);
  }  handleLiveMessage(msg) {
    if (!this.currentSpec) return;
    const idx = this.topicToTraceIndex.get(msg.topic);
    if (idx === undefined) return;
    if (!this._plotIsReady()) return;

    try {
      Plotly.extendTraces(this.plotDivId, { x: [[msg.ts]], y: [[msg.value]] }, [idx]);
    } catch (e) {
      console.error('extendTraces failed:', e);
    }

    const ts = new Date(msg.ts);
    if (isNaN(ts.getTime())) return;

    // Preserve previous overall tail so we can detect "tail-following".
    const prevOverallMax = this.overallMax ? new Date(this.overallMax) : null;

    // Update per-topic bounds cache.
    const b = this.boundsCache[msg.topic];
    if (b && b.max && ts > b.max) b.max = ts;

    // Update overall tail to the newest sample observed.
    if (!this.overallMax || ts > this.overallMax) this.overallMax = new Date(ts);

    // v0.7.1: If the window end is at the overall tail, keep it pinned to the
    // newest sample as data arrives, WITHOUT changing the selected span.
    if (this.currentEnd && this.overallMax && prevOverallMax) {
      const wasAtTail = Math.abs(prevOverallMax.getTime() - this.currentEnd.getTime()) <= 5000;
      if (wasAtTail && this.overallMax.getTime() >= prevOverallMax.getTime()) {
        const windowMs = (this.currentStart && this.currentEnd)
          ? Math.max(1000, this.currentEnd - this.currentStart)
          : WINDOW_OPTIONS_MS[1];

        this.currentEnd = new Date(this.overallMax);
        this.currentStart = new Date(this.currentEnd.getTime() - windowMs);

        this.setInputsFromDates(this.currentStart, this.currentEnd);
      }
    }
  }


  async applyWindowSize(newWindowMs) {
    if (!this.currentSpec) {
      alert('Preview a plot first.');
      return;
    }
    const overall = await this._getOverallBounds(this.currentSpec).catch(() => null);
    if (!overall) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for selected topics yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(overall.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(overall.max);
    const centerMs = (start.getTime() + end.getTime()) / 2;
    start = new Date(centerMs - newWindowMs / 2);
    end = new Date(centerMs + newWindowMs / 2);

    const clamped = this.clampWindow(start, end, overall.min, overall.max);
    this.currentStart = clamped.start;
    this.currentEnd = clamped.end;
    this.setInputsFromDates(this.currentStart, this.currentEnd);
    await this.plotFromSpec(this.currentSpec);
  }

  async zoomIn() {
    if (!this.currentSpec) { alert('Preview a plot first.'); return; }
    const windowMs = (this.currentEnd && this.currentStart) ? Math.max(1000, this.currentEnd - this.currentStart) : WINDOW_OPTIONS_MS[1];
    const idx = this.nearestWindowIndex(windowMs);
    const newIdx = Math.max(0, idx - 1);
    await this.applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
  }

  async zoomOut() {
    if (!this.currentSpec) { alert('Preview a plot first.'); return; }
    const windowMs = (this.currentEnd && this.currentStart) ? Math.max(1000, this.currentEnd - this.currentStart) : WINDOW_OPTIONS_MS[1];
    const idx = this.nearestWindowIndex(windowMs);
    const newIdx = Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1);
    await this.applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
  }

  async slideWindow(fraction) {
    if (!this.currentSpec) { alert('Preview a plot first.'); return; }
    const overall = await this._getOverallBounds(this.currentSpec).catch(() => null);
    if (!overall) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for selected topics yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(overall.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(overall.max);
    const windowMs = Math.max(1000, end - start);
    const shiftMs = windowMs * fraction;
    start = new Date(start.getTime() + shiftMs);
    end = new Date(end.getTime() + shiftMs);

    const clamped = this.clampWindow(start, end, overall.min, overall.max);
    this.currentStart = clamped.start;
    this.currentEnd = clamped.end;
    this.setInputsFromDates(this.currentStart, this.currentEnd);
    await this.plotFromSpec(this.currentSpec);
  }
}
