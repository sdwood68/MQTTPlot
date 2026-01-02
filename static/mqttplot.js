
const socket = io();
const adminMode =
    document.body.dataset.admin === "true";
let currentTopic = null;

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

/* Plot data */
async function plot() {
    const topic = document.getElementById('topicInput').value;
    if (!topic) {
        alert('Enter topic');
        return;
    }
    currentTopic = topic;

    const start = document.getElementById('start').value;
    const end = document.getElementById('end').value;

    let url = `/api/data?topic=${encodeURIComponent(topic)}`;
    if (start) url += `&start=${encodeURIComponent(start)}`;
    if (end) url += `&end=${encodeURIComponent(end)}`;

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