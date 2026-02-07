
/* MQTTPlot - Unified Plot Page Controller
   Single canonical plot controller used by:
   - Public slug plot page
   - Admin preview plot window (localStorage spec)
   - Admin single-topic plot window

   Requires:
   - Plotly loaded
   - /static/plot_core.js loaded (window.MQTTPlotCore)
*/
(function(){
  const Core = window.MQTTPlotCore || {};
  const $ = Core.$ || function(id){ return document.getElementById(id); };

  const WINDOW_OPTIONS_MS = [
    2*3600*1000, 4*3600*1000, 8*3600*1000, 12*3600*1000,
    1*24*3600*1000, 3*24*3600*1000, 5*24*3600*1000,
    7*24*3600*1000, 14*24*3600*1000, 28*24*3600*1000
  ];

  function humanSpan(ms){
    const h = Math.round(ms/3600000);
    if (ms < 24*3600000) return `${h}h`;
    const d = Math.round(ms/(24*3600000));
    if (d % 7 === 0) return `${d/7}w`;
    return `${d}d`;
  }

  function nearestWindowIndex(ms){
    let best=0, bestDiff=Infinity;
    for(let i=0;i<WINDOW_OPTIONS_MS.length;i++){
      const d=Math.abs(WINDOW_OPTIONS_MS[i]-ms);
      if(d<bestDiff){ bestDiff=d; best=i; }
    }
    return best;
  }

  function clampTopics(spec){
    const topics = Array.isArray(spec?.topics) ? spec.topics.filter(t=>t && t.name) : [];
    return topics.slice(0,2);
  }

  function showError(msg){
    const el = $('plot_error');
    if(!el) return;
    el.style.display = msg ? 'block' : 'none';
    el.textContent = msg || '';
  }

  function setStatus(msg){
    const el = $('plotStatus');
    if(el) el.textContent = msg || '';
  }

  function setLive(on){
    const el = $('liveIndicator');
    if(!el) return;
    el.style.display = 'inline-block';
    el.disabled = false;
    el.textContent = on ? 'Live' : 'Not Live';
    el.classList.toggle('live-on', !!on);
  }

  function buildTrace(points, topicSpec){
    const x = (points||[]).map(p=>p.ts);
    const y = (points||[]).map(p=>p.value);
    return {
      x, y,
      type: 'scatter',
      mode: topicSpec?.mode || 'lines',
      name: topicSpec?.label || topicSpec?.name || 'series',
      yaxis: (topicSpec?.yAxis === 'y2') ? 'y2' : 'y'
    };
  }

  function axisKeyFromTrace(trace){ return (trace && trace.yaxis === 'y2') ? 'y2' : 'y'; }

  function computeYExtentsByAxis(traces){
    const ext = { y: {min: null, max: null}, y2: {min:null, max:null} };
    for(const tr of (traces||[])){
      const key = axisKeyFromTrace(tr);
      const ys = Array.isArray(tr.y) ? tr.y : [];
      for(const v of ys){
        const n = Number(v);
        if(!Number.isFinite(n)) continue;
        if(ext[key].min===null || n<ext[key].min) ext[key].min=n;
        if(ext[key].max===null || n>ext[key].max) ext[key].max=n;
      }
    }
    return ext;
  }

  function applyAxisRangeAndTicks(axis, dtick, minVal, maxVal){
    if(!axis) return;
    const d = Number(dtick);
    if(!(Number.isFinite(d) && d>0)) return;

    let lo = Number(minVal), hi = Number(maxVal);
    if(!Number.isFinite(lo) || !Number.isFinite(hi)){
      lo = -d; hi = d;
    }
    if(lo === hi){
      lo = lo - d;
      hi = hi + d;
    }

    // Pad a bit, then snap to dtick multiples.
    const span = hi - lo;
    const pad = span * 0.05;
    lo -= pad; hi += pad;

    lo = Math.floor(lo / d) * d;
    hi = Math.ceil(hi / d) * d;

    // Ensure at least 3 ticks: hi - lo >= 2*dtick
    if((hi - lo) < 2*d){
      const mid = (hi + lo)/2;
      const midTick = Math.round(mid / d) * d;
      lo = midTick - d;
      hi = midTick + d;
    }

    axis.range = [lo, hi];
    Core.enforceLinearTicks(axis, d);
  }

  function resolveAxisTitle(unitsSet){
    const arr = Array.from(unitsSet||[]).filter(u=>u);
    if(arr.length===1) return Core.unitsLabel(arr[0]);
    return 'Value';
  }

  function ensureY2Assignment(topics){
    // If two topics but no explicit y2 assignment, default second to y2 for readability.
    if(topics.length===2){
      if(!topics[0].yAxis) topics[0].yAxis = 'y';
      if(!topics[1].yAxis) topics[1].yAxis = 'y2';
    } else if(topics.length===1){
      topics[0].yAxis = topics[0].yAxis || 'y';
    }
  }

  function makeEndpointBuilder(ctx){
    if(ctx.mode === 'public'){
      return {
        boundsUrl: (topic)=>`/api/public/bounds?slug=${encodeURIComponent(ctx.slug)}&topic=${encodeURIComponent(topic)}`,
        dataUrl: (topic, startIso, endIso)=>`/api/public/data?slug=${encodeURIComponent(ctx.slug)}&topic=${encodeURIComponent(topic)}&start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
      };
    }
    // admin
    if(ctx.usePublic && ctx.slug){
      return {
        boundsUrl: (topic)=>`/api/public/bounds?slug=${encodeURIComponent(ctx.slug)}&topic=${encodeURIComponent(topic)}`,
        dataUrl: (topic, startIso, endIso)=>`/api/public/data?slug=${encodeURIComponent(ctx.slug)}&topic=${encodeURIComponent(topic)}&start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
      };
    }
    return {
      boundsUrl: (topic)=>`/api/bounds?topic=${encodeURIComponent(topic)}`,
      dataUrl: (topic, startIso, endIso)=>`/api/data?topic=${encodeURIComponent(topic)}&start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
    };
  }

  async function loadPlotSpec(ctx){
    if(ctx.mode === 'public'){
      // Public plot API returns {slug,title,description,spec:{...}}.
      // The unified renderer expects a *flat* spec object with .topics and .time.
      const resp = await Core.fetchJson(`/api/public/plots/${encodeURIComponent(ctx.slug)}`);
      const inner = (resp && typeof resp === 'object') ? (resp.spec || {}) : {};
      return {
        ...(inner || {}),
        slug: resp?.slug || ctx.slug,
        title: resp?.title || inner?.title || ctx.slug,
        description: resp?.description || inner?.description || ''
      };
    }
    if(ctx.source === 'topic'){
      return {
        title: ctx.topic,
        description: '',
        time: { seconds: 4*3600 },
        topics: [{ name: ctx.topic, label: ctx.topic, mode: 'lines', yAxis: 'y' }]
      };
    }
    // spec from localStorage
    const raw = localStorage.getItem('mqttplot.plotSpec') || '{}';
    let spec = {};
    try{ spec = JSON.parse(raw) || {}; }catch{ spec = {}; }
    return spec;
  }

  async function loadBounds(topics, endpoints){
    let minTs=null, maxTs=null;
    for(const t of topics){
      try{
        const b = await Core.fetchJson(endpoints.boundsUrl(t.name));
        const mn = b?.min_ts ? new Date(b.min_ts) : null;
        const mx = b?.max_ts ? new Date(b.max_ts) : null;
        if(mn && !isNaN(mn.getTime())) minTs = (!minTs || mn<minTs) ? mn : minTs;
        if(mx && !isNaN(mx.getTime())) maxTs = (!maxTs || mx>maxTs) ? mx : maxTs;
      }catch{
        // ignore topics with no data yet
      }
    }
    return {minTs, maxTs};
  }

  async function loadSeries(topics, endpoints, start, end){
    const traces=[];
    let tail=null;
    for(const t of topics){
      const pts = await Core.fetchJson(endpoints.dataUrl(t.name, start.toISOString(), end.toISOString()));
      traces.push(buildTrace(pts, t));
      if(Array.isArray(pts) && pts.length){
        const last = new Date(pts[pts.length-1].ts);
        if(!isNaN(last.getTime())) tail = (!tail || last>tail) ? last : tail;
      }
    }
    return {traces, tail};
  }

  async function render(ctx, spec, state, endpoints){
    showError('');
    const topics = clampTopics(spec);
    ensureY2Assignment(topics);

    // Window span from spec, snapped to supported options
    const specSec = Number(spec?.time?.seconds || 0);
    const specMs = (Number.isFinite(specSec) && specSec>0) ? specSec*1000 : null;
    if(!state.spanMs){
      state.spanMs = specMs ? WINDOW_OPTIONS_MS[nearestWindowIndex(specMs)] : WINDOW_OPTIONS_MS[1];
    }

    const bounds = await loadBounds(topics, endpoints);
    const now = new Date();
    let latest = bounds.maxTs || now;

    // Determine end
    let end = state.followTail ? latest : (state.end || latest);
    if(end > latest) end = latest;

    let start = new Date(end.getTime() - state.spanMs);

    // Clamp to minimum
    if(bounds.minTs && start < bounds.minTs){
      start = new Date(bounds.minTs);
      end = new Date(start.getTime() + state.spanMs);
      if(end > latest) end = latest;
    }

    // Store
    state.start = start;
    state.end = end;

    $('start') && ($('start').value = start.toISOString());
    $('end') && ($('end').value = end.toISOString());

    // Display window label
    const wl = $('windowLabel');
    if(wl) wl.textContent = `Window = ${humanSpan(state.spanMs)}`;

    // Load data
    const {traces, tail} = await loadSeries(topics, endpoints, start, end);

    // If following tail, pin to real tail timestamp if returned
    if(state.followTail && tail){
      const newEnd = new Date(tail);
      const newStart = new Date(newEnd.getTime() - state.spanMs);
      state.end = newEnd;
      state.start = newStart;
    }

    // Topic meta -> axis titles & dticks
    const metas = await Promise.all(topics.map(t=>Core.getTopicMeta(t.name)));
    const unitsByAxis = { y: new Set(), y2: new Set() };
    const ticksByAxis = { y: new Set(), y2: new Set() };

    for(let i=0;i<topics.length;i++){
      const axis = (topics[i].yAxis === 'y2') ? 'y2' : 'y';
      const mu = metas[i]?.units;
      const mt = metas[i]?.min_tick_size;
      if(mu) unitsByAxis[axis].add(mu);
      if(mt!=null) ticksByAxis[axis].add(Number(mt));
    }

    const layout = {
      margin: { l: 60, r: 60, t: 10, b: 40 },
      xaxis: { type: 'date' },
      yaxis: { title: { text: resolveAxisTitle(unitsByAxis.y) } },
      yaxis2: { title: { text: resolveAxisTitle(unitsByAxis.y2) }, overlaying: 'y', side: 'right' },
      showlegend: true
    };

    // Apply y ranges and ticks
    const ext = computeYExtentsByAxis(traces);
    const dtY = Core.lcmFromSet(ticksByAxis.y);
    const dtY2 = Core.lcmFromSet(ticksByAxis.y2);

    if(dtY) applyAxisRangeAndTicks(layout.yaxis, dtY, ext.y.min, ext.y.max);
    if(dtY2 && topics.length===2) applyAxisRangeAndTicks(layout.yaxis2, dtY2, ext.y2.min, ext.y2.max);

    // Border rectangle
    Core.addPlotAreaBorder(layout);

    const config = { displayModeBar: false, responsive: true };
    await Plotly.react('plot', traces, layout, config);

    // Per UX request, keep the control window clean: do not display topic names or time span.
    setStatus('');
  }

  function wireControls(ctx, spec, state, endpoints){
    function rerender(){ render(ctx, spec, state, endpoints).catch(e=>showError(e.message||String(e))); }

    const back = $('btnBack');
    const fwd = $('btnFwd');
    const zin = $('btnZoomIn');
    const zout = $('btnZoomOut');
    const live = $('liveIndicator');

    if(back) back.onclick = ()=>{
      state.followTail = false;
      const end = state.end ? new Date(state.end) : new Date();
      state.end = new Date(end.getTime() - Math.round(state.spanMs * 0.5));
      rerender();
    };
    if(fwd) fwd.onclick = ()=>{
      state.followTail = false;
      const end = state.end ? new Date(state.end) : new Date();
      state.end = new Date(end.getTime() + Math.round(state.spanMs * 0.5));
      rerender();
    };
    if(zin) zin.onclick = ()=>{
      const idx = nearestWindowIndex(state.spanMs);
      const newIdx = Math.max(0, idx-1);
      state.spanMs = WINDOW_OPTIONS_MS[newIdx];
      rerender();
    };
    if(zout) zout.onclick = ()=>{
      const idx = nearestWindowIndex(state.spanMs);
      const newIdx = Math.min(WINDOW_OPTIONS_MS.length-1, idx+1);
      state.spanMs = WINDOW_OPTIONS_MS[newIdx];
      rerender();
    };
    if(live){
      live.style.display = 'inline-block';
      live.onclick = ()=>{
        state.followTail = !state.followTail;
        setLive(state.followTail);
        rerender();
      };
    }

    // When admin preview spec changes, refresh
    window.addEventListener('storage', (ev)=>{
      if(ctx.mode==='admin' && ctx.source==='spec' && ev.key==='mqttplot.plotSpec'){
        loadPlotSpec(ctx).then(s=>{
          spec = s;
          endpoints = makeEndpointBuilder({ ...ctx, slug: spec.slug, usePublic: !!spec.slug });
          rerender();
        });
      }
    });

    // Socket.IO live refresh (admin pages)
    if(typeof window.io === 'function'){
      try{
        const socket = window.io();
        socket.on('new_data', ()=>{ if(state.followTail) rerender(); });
        socket.on('new_data_admin', ()=>{ if(state.followTail) rerender(); });
      }catch{}
    }

    // Poll as fallback when Live is active (reduced to 15s for scale)
    setInterval(()=>{ if(state.followTail) rerender(); }, 15000);
  }

  async function main(){
    if(!Core.fetchJson){
      console.error('MQTTPlotCore not loaded');
      return;
    }
    const body = document.body || {};
    const ds = body.dataset || {};

    const ctx = {
      mode: ds.mode || (ds.slug ? 'public' : 'admin'),
      slug: ds.slug || '',
      source: ds.source || (ds.topic ? 'topic' : 'spec'),
      topic: ds.topic || '',
      usePublic: false
    };

    const spec = await loadPlotSpec(ctx);

    // Update header title/subtitle if present
    const titleEl = $('plotTitle');
    if(titleEl && spec?.title) titleEl.textContent = spec.title;
    const subtitleEl = $('plotSubtitle');
    if(subtitleEl){
      // Avoid duplicating description on public slug pages where the template already renders it.
      if(ctx.mode === 'public'){
        subtitleEl.textContent = '';
      }else{
        subtitleEl.textContent = spec?.description ? spec.description : (spec?.slug ? spec.slug : '');
      }
    }

    // Use public endpoints in admin preview when spec carries a slug (previewing slug plot)
    ctx.usePublic = (ctx.mode==='admin' && ctx.source==='spec' && !!spec.slug);
    ctx.slug = spec.slug || ctx.slug;

    const endpoints = makeEndpointBuilder(ctx);
    const state = { spanMs: null, start: null, end: null, followTail: true };

    setLive(true);

    await render(ctx, spec, state, endpoints);
    wireControls(ctx, spec, state, endpoints);
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    
    // Close button (admin popups). Note: window.close() only succeeds for script-opened windows.
    const btnClose = document.getElementById('btnClose');
    if(btnClose){
      btnClose.addEventListener('click', (ev)=>{
        ev.preventDefault();
        try{ window.close(); }catch(_e){}
        // Fallback: if browser refuses, show a helpful message.
        setTimeout(()=>{
          if(!window.closed){
            showError('This window was not opened by script, so the browser blocked Close. You can close this tab/window normally.');
          }
        }, 200);
      });
    }
main().catch(e=>showError(e.message||String(e)));
  });
})();
