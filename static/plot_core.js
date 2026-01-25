/* MQTTPlot - Shared Plot Core
   Canonical helpers used by ALL plot pages (public slug, admin preview, admin topic).
   Exposes window.MQTTPlotCore.
*/
(function(){
  function $(id){ return document.getElementById(id); }

  async function fetchJson(url){
    const r = await fetch(url, { cache: 'no-store' });
    if(!r.ok){
      const text = await r.text();
      throw new Error(`${r.status} ${r.statusText}: ${text.slice(0,200)}`);
    }
    return await r.json();
  }

  function unitsLabel(units){
    switch (units) {
      case 'distance_m': return 'Distance (m)';
      case 'distance_ftin': return 'Distance (ft/in)';
      case 'temp_f': return 'Temperature (°F)';
      case 'temp_c': return 'Temperature (°C)';
      case 'pressure_kpa': return 'Pressure (kPa)';
      case 'humidity_rh': return 'Humidity (%RH)';
      case 'voltage_v': return 'Voltage (V)';
      case 'other': return 'Value';
      default: return 'Value';
    }
  }

  async function getTopicMeta(topic){
    const t = (topic || '').toString();
    try{
      const meta = await fetchJson(`/api/topic_meta?topic=${encodeURIComponent(t)}`);
      if (meta && meta.units == null && meta.min_tick_size == null) {
        const t2 = t.replace(/^\/+/, '');
        if (t2 && t2 !== t) {
          const meta2 = await fetchJson(`/api/topic_meta?topic=${encodeURIComponent(t2)}`);
          if (meta2 && (meta2.units != null || meta2.min_tick_size != null)) return { ...meta2, topic: t };
        }
      }
      return meta;
    }catch{
      return { topic: t, units: null, min_tick_size: null };
    }
  }

  function tickDecimals(dtick){
    if(!dtick) return 0;
    const x = Number(dtick);
    if(!Number.isFinite(x) || x<=0) return 0;
    return Math.max(0, Math.min(6, Math.ceil(-Math.log10(x))));
  }

  function gcdInt(a,b){
    a=Math.abs(a); b=Math.abs(b);
    while(b){ const t=b; b=a%b; a=t; }
    return a;
  }
  function lcmInt(a,b){
    if(!a||!b) return 0;
    return Math.abs((a/gcdInt(a,b))*b);
  }
  function lcmFloat(a,b){
    const x=Number(a), y=Number(b);
    if(!Number.isFinite(x)||!Number.isFinite(y)||x<=0||y<=0) return null;
    const ax=x.toString(), ay=y.toString();
    const dx=ax.includes('.')?ax.split('.')[1].length:0;
    const dy=ay.includes('.')?ay.split('.')[1].length:0;
    const d=Math.min(6, Math.max(dx,dy));
    const scale=Math.pow(10,d);
    const ix=Math.round(x*scale);
    const iy=Math.round(y*scale);
    if(ix<=0||iy<=0) return null;
    return lcmInt(ix,iy)/scale;
  }
  function lcmFromSet(values){
    const arr = Array.from(values||[]).map(Number).filter(v=>Number.isFinite(v)&&v>0);
    if(arr.length===0) return null;
    let out=arr[0];
    for(let i=1;i<arr.length;i++){
      const nxt=lcmFloat(out, arr[i]);
      if(!nxt) return out;
      out=nxt;
    }
    return out;
  }

  function enforceLinearTicks(axis, dtick){
    if(!axis || !dtick) return;
    const d = Number(dtick);
    if(!Number.isFinite(d) || d<=0) return;

    axis.tickmode = 'linear';
    axis.dtick = d;

    // Anchor ticks to a clean multiple of dtick at the visible range start (when possible).
    let t0 = 0;
    if (axis.range && axis.range.length === 2) {
      const lo = Number(axis.range[0]);
      if (Number.isFinite(lo)) t0 = Math.floor(lo / d) * d;
    }
    axis.tick0 = t0;
    axis.tickformat = `.${tickDecimals(d)}f`;
  }

  function addPlotAreaBorder(layout){
    if(!layout) return;
    const shapes = Array.isArray(layout.shapes) ? layout.shapes.slice() : [];
    shapes.push({
      type: 'rect',
      xref: 'paper',
      yref: 'paper',
      x0: 0, x1: 1, y0: 0, y1: 1,
      line: { width: 1 },
      fillcolor: 'rgba(0,0,0,0)'
    });
    layout.shapes = shapes;
  }

  window.MQTTPlotCore = {
    $, fetchJson, unitsLabel, getTopicMeta,
    tickDecimals, lcmFloat, lcmFromSet,
    enforceLinearTicks, addPlotAreaBorder
  };
})();
