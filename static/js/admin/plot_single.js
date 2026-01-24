import { getBounds as apiGetBounds, getData, getTopicMeta } from '../api.js';

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



function formatUnitsLabel(units) {
  switch (units) {
    case 'distance_m': return 'Distance (m)';
    case 'distance_ftin': return 'Distance (ft/in)';
    case 'temp_f': return 'Temperature (°F)';
    case 'temp_c': return 'Temperature (°C)';
    case 'voltage_v': return 'Voltage (V)';
    case 'other': return 'Value';
    default: return 'Value';
  }
}

function metersToFtIn(m) {
  const inchesTotal = Math.round(Number(m) * 39.3700787);
  const feet = Math.floor(inchesTotal / 12);
  const inches = inchesTotal - (feet * 12);
  return `${feet}' ${inches}"`;
}



export class SingleTopicPlot {
  constructor({ plotDivId = 'plot' } = {}) {
    this.plotDivId = plotDivId;
    this.currentTopic = null;
    this.currentStart = null; // Date|null
    this.currentEnd = null;   // Date|null
    this.boundsCache = {};    // topic -> {min: Date, max: Date} | null
  }

  _plotIsReady() {
    const plotDiv = document.getElementById(this.plotDivId);
    return plotDiv && Array.isArray(plotDiv.data) && plotDiv.data.length > 0;
  }

  safeExtend(ts, value) {
    if (!this._plotIsReady()) return;
    try {
      Plotly.extendTraces(this.plotDivId, { x: [[ts]], y: [[value]] }, [0]);
    } catch (e) {
      console.error('extendTraces failed:', e);
    }
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

  setNavEnabled(enabled) {
    const ids = ['btnBack', 'btnFwd', 'btnZoomIn', 'btnZoomOut'];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) el.disabled = !enabled;
    }
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

  setInputsFromDates(start, end) {
    const startEl = document.getElementById('start');
    const endEl = document.getElementById('end');
    if (startEl) startEl.value = start ? start.toISOString() : '';
    if (endEl) endEl.value = end ? end.toISOString() : '';
  }

  showPlotStatus(msg) {
    const plotDiv = document.getElementById(this.plotDivId);
    if (!plotDiv) return;
    plotDiv.innerHTML = msg ? `<div class="plot-status">${msg}</div>` : '';
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

  setCurrentTopic(topic) {
    this.currentTopic = topic || null;
  } handleLiveMessage(msg) {
    if (!this.currentTopic || msg.topic !== this.currentTopic) return;
    this.safeExtend(msg.ts, msg.value);

    const ts = new Date(msg.ts);
    if (isNaN(ts.getTime())) return;

    const b = this.boundsCache[this.currentTopic];

    // Preserve the previous tail so we can detect whether the user is "following"
    // the latest sample (i.e., currentEnd was at the tail before this update).
    const prevTail = (b && b.max) ? new Date(b.max) : null;

    // Update cached max bound (tail) if this sample is newer.
    if (b && b.max && ts > b.max) b.max = ts;

    const tail = (b && b.max) ? new Date(b.max) : null;

    // v0.7.1: If the window is currently at the tail, keep it pinned to the tail as
    // new samples arrive, WITHOUT changing the selected span.
    if (this.currentEnd && tail && prevTail) {
      const wasAtTail = Math.abs(prevTail.getTime() - this.currentEnd.getTime()) <= 5000;
      if (wasAtTail && tail.getTime() >= prevTail.getTime()) {
        const windowMs = (this.currentStart && this.currentEnd) ? Math.max(1000, this.currentEnd - this.currentStart) : WINDOW_OPTIONS_MS[1];
        this.currentEnd = new Date(tail);
        this.currentStart = new Date(this.currentEnd.getTime() - windowMs);

        // Clamp to min bound if available.
        if (b && b.min && this.currentStart < b.min) this.currentStart = new Date(b.min);

        this.setInputsFromDates(this.currentStart, this.currentEnd);
      }
    }
  }


  async plotFromInputs() {
    const topic = (document.getElementById('topicInput')?.value || '').trim();
    if (!topic) {
      alert('Enter topic');
      return;
    }

    this.setCurrentTopic(topic);

    const startStr = document.getElementById('start')?.value || '';
    const endStrHidden = document.getElementById('end')?.value || '';

    this.currentStart = startStr ? new Date(startStr) : null;
    this.currentEnd = endStrHidden ? new Date(endStrHidden) : null;

    const b = await this.getBounds(topic).catch(() => null);
    this.setNavEnabled(!!b);

    if (!b) {
      const pc = document.getElementById('plotControls');
      if (pc) pc.style.display = 'none';
      this.currentStart = null;
      this.currentEnd = null;
      this.setInputsFromDates(null, null);
      this.showPlotStatus('No numeric data available for this topic yet.');
      return;
    }

    if (!this.currentEnd) this.currentEnd = new Date(b.max);

    if (b && this.currentEnd && !this.currentStart) {
      const defaultMs = WINDOW_OPTIONS_MS[1];
      this.currentStart = new Date(this.currentEnd.getTime() - defaultMs);
      const clamped = this.clampWindow(this.currentStart, this.currentEnd, b.min, b.max);
      this.currentStart = clamped.start;
      this.currentEnd = clamped.end;
      this.setInputsFromDates(this.currentStart, this.currentEnd);
    }

    const js = await getData(topic, this.currentStart?.toISOString(), this.currentEnd?.toISOString());

    if (!js || js.length === 0) {
      const pc = document.getElementById('plotControls');
      if (pc) pc.style.display = 'none';
      const plotDiv = document.getElementById(this.plotDivId);
      if (plotDiv) plotDiv.innerHTML = 'No numeric data';
      return;
    }

    const trace = {
      x: js.map(r => r.ts),
      y: js.map(r => r.value),
      mode: 'lines+markers',
      name: topic
    };

    const meta = await getTopicMeta(topic).catch(() => null);

    let yTitle = 'Value';
    let dtick = null;
    let units = null;
    if (meta) {
      units = meta.units || null;
      if (units) yTitle = formatUnitsLabel(units);
      if (meta.min_tick_size !== null && meta.min_tick_size !== undefined && meta.min_tick_size !== '') {
        const mts = Number(meta.min_tick_size);
        if (!Number.isNaN(mts) && mts > 0) dtick = mts;
      }
    }

    // If a minimum tick size is defined, force a deterministic linear y-axis with:
    //   - tick spacing = dtick
    //   - a y-range that shows at least TWO intervals (=> at least 3 tick lines)
    let yRange = null;
    if (dtick) {
      const ysAll = js.map(r => r.value).filter(v => typeof v === 'number' && !Number.isNaN(v));
      if (ysAll.length) {
        const minY = Math.min(...ysAll);
        const maxY = Math.max(...ysAll);
        const span = maxY - minY;

        const desiredSpan = Math.max(span, 2 * dtick); // two intervals minimum
        const mid = (minY + maxY) / 2;

        let lo = mid - (desiredSpan / 2);
        let hi = mid + (desiredSpan / 2);

        // Align to dtick multiples so ticks land on clean divisions.
        lo = Math.floor(lo / dtick) * dtick;
        hi = Math.ceil(hi / dtick) * dtick;

        // Guard: ensure we truly have >= 2*dtick span after alignment.
        if ((hi - lo) < (2 * dtick)) hi = lo + (2 * dtick);

        yRange = [lo, hi];
      }
    }


    const yaxis = { title: yTitle };
    if (dtick) {
      yaxis.dtick = dtick;
      yaxis.tickmode = 'linear';
      if (yRange) yaxis.tick0 = yRange[0];
      // Choose a sensible decimal precision so tick labels land on multiples of dtick.
      const dec = Math.max(0, Math.min(6, Math.ceil(-Math.log10(dtick))));
      yaxis.tickformat = dec === 0 ? 'd' : `.${dec}f`;
      if (yRange) yaxis.range = yRange;
    }

    // Distance (ft/in) display: keep numeric axis in meters but render tick labels as ft/in when dtick is set.
    if (units === 'distance_ftin' && dtick) {
      const ys = js.map(r => r.value).filter(v => typeof v === 'number' && !Number.isNaN(v));
      if (ys.length) {
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);

        // Prefer the computed linear yRange so we guarantee >= 2 intervals on the axis.
        let start;
        let end;
        if (yRange) {
          start = yRange[0];
          end = yRange[1];
        } else {
          start = Math.floor(minY / dtick) * dtick;
          end = Math.ceil(maxY / dtick) * dtick;
          if ((end - start) < (2 * dtick)) {
            const mid = (minY + maxY) / 2;
            const lo = mid - dtick;
            const hi = mid + dtick;
            start = Math.floor(lo / dtick) * dtick;
            end = Math.ceil(hi / dtick) * dtick;
          }
        }
        const tickvals = [];
        const ticktext = [];
        const maxTicks = 200;
        for (let v = start, i = 0; v <= end + (dtick / 2) && i < maxTicks; v += dtick, i++) {
          tickvals.push(v);
          ticktext.push(metersToFtIn(v));
        }
        yaxis.tickmode = 'array';
        yaxis.tickvals = tickvals;
        yaxis.ticktext = ticktext;
        yaxis.range = [start, end];
      }
    }

    Plotly.newPlot(this.plotDivId, [trace], {
      title: topic,
      xaxis: { title: 'Time' },
      yaxis
    }, { responsive: true, displaylogo: false, displayModeBar: false });

    // Show controls only when a plot is present
    const pc = document.getElementById('plotControls');
    if (pc) pc.style.display = 'block';
    this.updateWindowUi();

    if (!this.currentStart || !this.currentEnd) {
      const first = new Date(js[0].ts);
      const last = new Date(js[js.length - 1].ts);
      this.currentStart = first;
      this.currentEnd = last;
      this.setInputsFromDates(this.currentStart, this.currentEnd);
    }
  }

  async applyWindowSize(newWindowMs) {
    if (!this.currentTopic) {
      alert('Plot a topic first.');
      return;
    }

    const b = await this.getBounds(this.currentTopic).catch(() => null);
    if (!b) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for this topic yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(b.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(b.max);

    const centerMs = (start.getTime() + end.getTime()) / 2;
    start = new Date(centerMs - newWindowMs / 2);
    end = new Date(centerMs + newWindowMs / 2);

    const clamped = this.clampWindow(start, end, b.min, b.max);
    this.currentStart = clamped.start;
    this.currentEnd = clamped.end;

    this.setInputsFromDates(this.currentStart, this.currentEnd);
    await this.plotFromInputs();
  }

  async zoomIn() {
    if (!this.currentTopic) {
      alert('Plot a topic first.');
      return;
    }
    const b = await this.getBounds(this.currentTopic).catch(() => null);
    if (!b) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for this topic yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(b.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(b.max);
    const windowMs = Math.max(1000, end - start);

    const idx = this.nearestWindowIndex(windowMs);
    const newIdx = Math.max(0, idx - 1);
    await this.applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
  }

  async zoomOut() {
    if (!this.currentTopic) {
      alert('Plot a topic first.');
      return;
    }
    const b = await this.getBounds(this.currentTopic).catch(() => null);
    if (!b) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for this topic yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(b.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(b.max);
    const windowMs = Math.max(1000, end - start);

    const idx = this.nearestWindowIndex(windowMs);
    const newIdx = Math.min(WINDOW_OPTIONS_MS.length - 1, idx + 1);
    await this.applyWindowSize(WINDOW_OPTIONS_MS[newIdx]);
  }

  async slideWindow(fraction) {
    if (!this.currentTopic) {
      alert('Plot a topic first.');
      return;
    }
    const b = await this.getBounds(this.currentTopic).catch(() => null);
    if (!b) {
      this.setNavEnabled(false);
      this.showPlotStatus('No numeric data available for this topic yet.');
      return;
    }

    let start = this.currentStart ? new Date(this.currentStart) : new Date(b.min);
    let end = this.currentEnd ? new Date(this.currentEnd) : new Date(b.max);

    const windowMs = Math.max(1000, end - start);
    const shiftMs = windowMs * fraction;

    start = new Date(start.getTime() + shiftMs);
    end = new Date(end.getTime() + shiftMs);

    const clamped = this.clampWindow(start, end, b.min, b.max);
    this.currentStart = clamped.start;
    this.currentEnd = clamped.end;

    this.setInputsFromDates(this.currentStart, this.currentEnd);
    await this.plotFromInputs();
  }
}