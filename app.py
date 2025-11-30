#!/usr/bin/env python3
"""MQTTPlot - app.py"""
import os, io, json, time, threading, sqlite3
from datetime import datetime
from flask import Flask, g, jsonify, request, render_template_string, send_file
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import plotly.graph_objects as go

MQTT_BROKER = os.environ.get('MQTT_BROKER','localhost')
MQTT_PORT = int(os.environ.get('MQTT_PORT','1883'))
MQTT_TOPICS = os.environ.get('MQTT_TOPICS','#')
MQTT_USERNAME = os.environ.get('MQTT_USERNAME','')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD','')
DB_PATH = os.environ.get('DB_PATH','mqtt_data.db')
FLASK_PORT = int(os.environ.get('FLASK_PORT','5000'))

PLOT_CONFIG = {'default_window_minutes':60,'max_points':10000,'update_interval_ms':2000}

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

def get_db():
    db = getattr(g,'_database',None)
    if db is None:
        db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g,'_database',None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        ts TIMESTAMP NOT NULL,
        payload TEXT,
        value REAL
    )""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_topic_ts ON messages(topic, ts)""")
    db.commit()
    db.close()

def parse_value(payload_text):
    try:
        data = json.loads(payload_text)
        if isinstance(data, dict):
            for k in ('value','val','v','temperature','temp','humidity','reading'):
                if k in data:
                    try:
                        return float(data[k])
                    except:
                        pass
        elif isinstance(data,(int,float)):
            return float(data)
    except:
        pass
    try:
        return float(payload_text.strip())
    except:
        return None

def store_message(topic,payload):
    payload_text = payload.decode(errors='replace')
    value = parse_value(payload_text)
    db = get_db()
    db.execute('INSERT INTO messages(topic, ts, payload, value) VALUES (?, ?, ?, ?)',
               (topic, datetime.now(), payload_text, value))
    db.commit()
    if value is not None:
        socketio.emit('new_data', {'topic':topic, 'ts': datetime.now().isoformat(), 'value': value})

def on_connect(client, userdata, flags, rc):
    if rc==0:
        print('MQTT connected')
        topics = [t.strip() for t in MQTT_TOPICS.split(',') if t.strip()]
        for t in topics:
            client.subscribe(t)
            print('Subscribed to', t)
    else:
        print('MQTT connect rc', rc)

def on_message(client, userdata, msg):
    try:
        store_message(msg.topic, msg.payload)
    except Exception as e:
        print('store error', e)

def mqtt_worker():
    client = mqtt.Client()
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT)
            client.loop_forever()
        except Exception as e:
            print('mqtt error', e)
            time.sleep(5)

def parse_time(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except:
        try:
            return datetime.fromtimestamp(float(s))
        except:
            raise ValueError('invalid time')

@app.route('/api/config', methods=['GET'])
def api_get_config():
    return jsonify(PLOT_CONFIG)

@app.route('/api/config', methods=['POST'])
def api_set_config():
    data = request.get_json(force=True, silent=True) or {}
    for k in PLOT_CONFIG:
        if k in data:
            PLOT_CONFIG[k] = data[k]
    return jsonify({'status':'ok','config':PLOT_CONFIG})

@app.route('/api/topics', methods=['GET'])
def api_topics():
    db = get_db()
    cur = db.execute('SELECT topic, COUNT(*) as count FROM messages GROUP BY topic ORDER BY count DESC')
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route('/api/data', methods=['GET'])
def api_data():
    topic = request.args.get('topic')
    if not topic:
        return jsonify({'error':'missing topic'}),400
    start = request.args.get('start')
    end = request.args.get('end')
    limit = int(request.args.get('limit', PLOT_CONFIG['max_points']))
    sql = 'SELECT ts, value FROM messages WHERE topic=? AND value IS NOT NULL'
    params = [topic]
    if start:
        sql += ' AND ts >= ?'; params.append(parse_time(start))
    if end:
        sql += ' AND ts <= ?'; params.append(parse_time(end))
    sql += ' ORDER BY ts ASC LIMIT ?'; params.append(limit)
    cur = get_db().execute(sql, params)
    rows = [{'ts': r['ts'], 'value': r['value']} for r in cur.fetchall()]
    for r in rows:
        if not isinstance(r['ts'], str):
            r['ts'] = r['ts'].isoformat(sep=' ')
    return jsonify(rows)

@app.route('/api/plot_image', methods=['GET'])
def api_plot_image():
    topic = request.args.get('topic'); 
    if not topic: return jsonify({'error':'missing topic'}),400
    start = request.args.get('start'); end = request.args.get('end')
    width = int(request.args.get('width',800)); height = int(request.args.get('height',500))
    fmt = request.args.get('format','png').lower()
    sql = 'SELECT ts, value FROM messages WHERE topic=? AND value IS NOT NULL'
    params = [topic]
    if start:
        sql += ' AND ts >= ?'; params.append(parse_time(start))
    if end:
        sql += ' AND ts <= ?'; params.append(parse_time(end))
    sql += ' ORDER BY ts ASC LIMIT ?'; params.append(PLOT_CONFIG['max_points'])
    cur = get_db().execute(sql, params)
    rows = [{'ts': r['ts'], 'value': r['value']} for r in cur.fetchall()]
    if not rows: return jsonify({'error':'no data'}),404
    x = [r['ts'] for r in rows]; y = [r['value'] for r in rows]
    fig = go.Figure(); fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name=topic))
    fig.update_layout(title=f'{topic} Data', xaxis_title='Timestamp', yaxis_title='Value', template='plotly_white')
    if fmt=='json': return jsonify(fig.to_plotly_json())
    buf = io.BytesIO()
    try:
        fig.write_image(buf, format='png', width=width, height=height)
    except Exception as e:
        return jsonify({'error':'image generation failed','detail':str(e)}),500
    buf.seek(0); return send_file(buf, mimetype='image/png')

INDEX_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"/><title>MQTTPlot</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<style>body{font-family:sans-serif;margin:20px;max-width:900px}input,button{margin:3px;padding:4px}#plot{width:100%;height:500px}.topic{cursor:pointer;color:blue;text-decoration:underline}</style>
</head><body>
<h2>MQTTPlot</h2><p><b>Broker:</b> {{ broker }}</p><div id="topics"></div>
<h3>Plot Data</h3><label>Topic:<input id="topicInput" list="topiclist"></label><label>From:<input id="start"></label><label>To:<input id="end"></label>
<button onclick="plot()">Plot</button><datalist id="topiclist"></datalist><div id="plot"></div>
<script>
const socket = io();
socket.on("new_data", msg=>{ if(currentTopic && msg.topic===currentTopic){ Plotly.extendTraces('plot',{y:[[msg.value]],x:[[msg.ts]]},[0]); }});
let currentTopic=null;
async function loadTopics(){ const res=await fetch('/api/topics'); const data=await res.json(); const div=document.getElementById('topics'); const list=document.getElementById('topiclist'); div.innerHTML=''; list.innerHTML=''; data.forEach(t=>{ const d=document.createElement('div'); d.innerHTML=`<span class="topic">${t.topic}</span> — ${t.count} msgs`; d.onclick=()=>{document.getElementById('topicInput').value=t.topic;plot();}; div.appendChild(d); const opt=document.createElement('option'); opt.value=t.topic; list.appendChild(opt); }); }
async function plot(){ const topic=document.getElementById('topicInput').value; if(!topic)return alert('Enter topic'); currentTopic=topic; const start=document.getElementById('start').value; const end=document.getElementById('end').value; let url=`/api/data?topic=${encodeURIComponent(topic)}`; if(start)url+=`&start=${encodeURIComponent(start)}`; if(end)url+=`&end=${encodeURIComponent(end)}`; const res=await fetch(url); const js=await res.json(); if(!js.length){document.getElementById('plot').innerHTML='No numeric data';return;} const trace={x:js.map(r=>r.ts),y:js.map(r=>r.value),mode:'lines+markers',name:topic}; const layout={title:topic,xaxis:{title:'Time'},yaxis:{title:'Value'}}; Plotly.newPlot('plot',[trace],layout); }
loadTopics(); setInterval(loadTopics,10000);
</script></body></html>"""

from flask import render_template_string
@app.route('/')
def index():
    return render_template_string(INDEX_HTML, broker=f"{MQTT_BROKER}:{MQTT_PORT}")

def main():
    init_db()
    t = threading.Thread(target=mqtt_worker, daemon=True)
    t.start()
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT)

if __name__ == '__main__':
    main()
