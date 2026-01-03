
const socket = io();
const adminMode =
    document.body.dataset.admin === "true";
let currentTopic = null;
let currentStart = null;   // Date or null
let currentEnd = null;     // Date or null
let boundsCache = {};      // topic -> {min: Date, max: Date}

/* Live updates (public stream) */
socket.on("new_data", msg => {
    if (currentTopic && msg.topic === currentTopic) {
        Plotly.extendTraces('plot', { x: [[msg.ts]], y: [[msg.value]] }, [0]);
    }
});

/* Optional: Admin-only stream for hidden topics (safe if server never emits it) */
socket.on("new_data_admin", msg => {
    if (!adminMode) return;
    if (currentTopic && msg.topic === currentTopic) {
        Plotly.extendTraces('plot', { x: [[msg.ts]], y: [[msg.value]] }, [0]);
    }
});

/* Load topic list */
async function loadTopics() {
    const res = await fetch('/api/topics');
    const data = await res.json();

    const div = document.getElementById('topics');
    const list = document.getElementById('topiclist');
    div.innerHTML = '';
    list.innerHTML = '';

    data.forEach(t => {
        const row = document.createElement('div');
        row.className = 'topic-row';

        const label = document.createElement('span');
        label.className = 'topic';
        label.textContent = t.topic;
        label.onclick = () => {
            document.getElementById('topicInput').value = t.topic;
            plot();
        };

        row.appendChild(label);
        row.appendChild(document.createTextNode(` — ${t.count} msgs `));

        if (adminMode) {
            /* Visibility toggle */
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.checked = t.public !== 0;
            chk.title = 'Publicly visible';
            chk.style.marginLeft = "10px";
            chk.onchange = async () => {
                const r = await fetch('/api/admin/topic_visibility', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        topic: t.topic,
                        public: chk.checked
                    })
                });
                if (!r.ok) alert('Failed to update visibility (are you logged in as admin?)');
            };
            row.appendChild(chk);

            /* Delete button */
            const del = document.createElement('button');
            del.textContent = 'Delete';
            del.style.marginLeft = "6px";
            del.onclick = async () => {
                if (!confirm(`Delete ALL data for topic "${t.topic}"?`)) return;
                const r = await fetch(`/api/admin/topic/${encodeURIComponent(t.topic)}`, {
                    method: 'DELETE'
                });
                if (!r.ok) {
                    alert('Delete failed (are you logged in as admin?)');
                    return;
                }
                loadTopics();
            };
            row.appendChild(del);
        }

        div.appendChild(row);

        const opt = document.createElement('option');
        opt.value = t.topic;
        list.appendChild(opt);
    });
}

/* v0.6.0 plot window controls */
async function getBounds(topic) {
    if (boundsCache[topic]) return boundsCache[topic];

    const res = await fetch(`/api/bounds?topic=${encodeURIComponent(topic)}`);
    if (!res.ok) return null;

    const js = await res.json();
    // Backend returns ISO strings; Date parsing is reliable with ISO 8601
    const b = { min: new Date(js.min_ts), max: new Date(js.max_ts) };
    boundsCache[topic] = b;
    return b;
}

function clampWindow(start, end, min, max) {
    // Ensure start <= end
    if (start > end) {
        const tmp = start; start = end; end = tmp;
    }

    const windowMs = end - start;

    // If data bounds are smaller than the window, clamp to the full bounds
    if ((max - min) <= windowMs) {
        return { start: new Date(min), end: new Date(max) };
    }

    // Clamp left
    if (start < min) {
        start = new Date(min);
        end = new Date(start.getTime() + windowMs);
    }

    // Clamp right
    if (end > max) {
        end = new Date(max);
        start = new Date(end.getTime() - windowMs);
    }

    // Final safety clamp
    if (start < min) start = new Date(min);
    if (end > max) end = new Date(max);

    return { start, end };
}

function setInputsFromDates(start, end) {
    document.getElementById('start').value = start ? start.toISOString() : '';
    document.getElementById('end').value = end ? end.toISOString() : '';
}

/* Plot data */
async function plot() {
    const topic = document.getElementById('topicInput').value;
    if (!topic) {
        alert('Enter topic');
        return;
    }
    currentTopic = topic;

    const startStr = document.getElementById('start').value;
    const endStr = document.getElementById('end').value;

    // Track current window as Dates if present
    currentStart = startStr ? new Date(startStr) : null;
    currentEnd = endStr ? new Date(endStr) : null;

    let url = `/api/data?topic=${encodeURIComponent(topic)}`;
    if (startStr) url += `&start=${encodeURIComponent(startStr)}`;
    if (endStr) url += `&end=${encodeURIComponent(endStr)}`;

    const res = await fetch(url);
    if (!res.ok) {
        const err = await res.json().catch(()=>({error:"request failed"}));
        document.getElementById('plot').innerHTML = `Error: ${err.error || res.status}`;
        return;
    }

    const js = await res.json();
    if (!js.length) {
        document.getElementById('plot').innerHTML = 'No numeric data';
        return;
    }

    const trace = {
        x: js.map(r => r.ts),
        y: js.map(r => r.value),
        mode: 'lines+markers',
        name: topic
    };

    Plotly.newPlot('plot', [trace], {
        title: topic,
        xaxis: { title: 'Time' },
        yaxis: { title: 'Value' }
    });

    // If user didn't specify start/end, set a sensible default window based on returned data
    // so the navigation buttons work immediately.
    if (!currentStart || !currentEnd) {
        const first = new Date(js[0].ts);
        const last = new Date(js[js.length - 1].ts);
        currentStart = first;
        currentEnd = last;
        setInputsFromDates(currentStart, currentEnd);
    }
}

async function zoomWindow(factor) {
    if (!currentTopic) {
        alert("Plot a topic first.");
        return;
    }

    const b = await getBounds(currentTopic);
    if (!b) {
        alert("No bounds available (no data?).");
        return;
    }

    // If no current window yet, default to full bounds
    let start = currentStart ? new Date(currentStart) : new Date(b.min);
    let end = currentEnd ? new Date(currentEnd) : new Date(b.max);

    const center = new Date((start.getTime() + end.getTime()) / 2);
    const windowMs = Math.max(1000, (end - start)); // at least 1 second
    const newWindowMs = Math.max(60 * 1000, windowMs * factor); // floor: 1 minute

    start = new Date(center.getTime() - newWindowMs / 2);
    end = new Date(center.getTime() + newWindowMs / 2);

    const clamped = clampWindow(start, end, b.min, b.max);
    currentStart = clamped.start;
    currentEnd = clamped.end;

    setInputsFromDates(currentStart, currentEnd);
    await plot();
}

async function slideWindow(fraction) {
    if (!currentTopic) {
        alert("Plot a topic first.");
        return;
    }

    const b = await getBounds(currentTopic);
    if (!b) {
        alert("No bounds available (no data?).");
        return;
    }

    let start = currentStart ? new Date(currentStart) : new Date(b.min);
    let end = currentEnd ? new Date(currentEnd) : new Date(b.max);

    const windowMs = Math.max(1000, (end - start));
    const shiftMs = windowMs * fraction;

    start = new Date(start.getTime() + shiftMs);
    end = new Date(end.getTime() + shiftMs);

    const clamped = clampWindow(start, end, b.min, b.max);
    currentStart = clamped.start;
    currentEnd = clamped.end;

    setInputsFromDates(currentStart, currentEnd);
    await plot();
}

/* OTA */
async function sendOTA(val) {
    const base = document.getElementById('otaBase').value;
    if (!base) {
        alert('Enter base topic');
        return;
    }
    const r = await fetch('/api/admin/ota', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            base_topic: base,
            ota: val
        })
    });
    if (!r.ok) {
        alert('OTA failed (are you logged in as admin?)');
        return;
    }
    alert('OTA command sent');
}

loadTopics();
setInterval(loadTopics, 10000);