#!/usr/bin/env python3
"""MQTTPlot - app.py"""
import eventlet
eventlet.monkey_patch()
import sys, os, io, json, time, threading, sqlite3, logging
from datetime import datetime
from flask import Flask, g, jsonify, request, render_template, send_file
from flask import session, redirect, abort, url_for
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import plotly.graph_objects as go
from version import __version__
from werkzeug.security import generate_password_hash, check_password_hash
import secrets


# Register adapter and converter for datetime
sqlite3.register_adapter(datetime, lambda val: val.isoformat(sep=' '))
sqlite3.register_converter("TIMESTAMP", lambda val: datetime.fromisoformat(val.decode()))

DB_PATH = os.environ.get('DB_PATH','/opt/mqttplot/mqtt_data.db')
MQTT_BROKER = os.environ.get('MQTT_BROKER','192.168.12.50')
MQTT_PORT = int(os.environ.get('MQTT_PORT','1883'))
MQTT_TOPICS = os.environ.get('MQTT_TOPICS','#')
MQTT_USERNAME = os.environ.get('MQTT_USERNAME')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')
FLASK_PORT = int(os.environ.get('FLASK_PORT','5000'))

PLOT_CONFIG = {'default_window_minutes':60,'max_points':10000,'update_interval_ms':2000}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

print(f"MQTTPlot starting — version {__version__}")


def require_admin():
    if not is_admin():
        abort(403)

def get_db():
    db = getattr(g,'_database',None)
    if db is None:
        db = sqlite3.connect(DB_PATH, 
                             detect_types=sqlite3.PARSE_DECLTYPES |
                             sqlite3.PARSE_COLNAMES)
        db.row_factory = sqlite3.Row
        g._database = db
    return db

def record_app_version(version: str):
    db = sqlite3.connect(DB_PATH)
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        db.execute("""
            INSERT INTO metadata (key, value)
            VALUES ('app_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (version,))
        db.commit()
    finally:
        db.close()

def init_admin_user():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur = db.execute("SELECT COUNT(*) FROM admin_users")
    count = cur.fetchone()[0]

    if count == 0:
        # default admin user (must change password later)
        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin"))
        )
        print("⚠️  Default admin user created: admin / admin")

    db.commit()
    db.close()

# def init_visibility():
#     db = sqlite3.connect(DB_PATH)
#     db.execute("""
#         CREATE TABLE IF NOT EXISTS topic_visibility (
#             topic TEXT PRIMARY KEY,
#             public INTEGER NOT NULL DEFAULT 1
#         )
#     """)
#     db.commit()
#     db.close()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g,'_database',None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        ts TIMESTAMP NOT NULL,
        payload TEXT,
        value REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS topic_meta (
        topic TEXT PRIMARY KEY,
        public INTEGER DEFAULT 1
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_topic_ts ON messages(topic, ts)")
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

def store_message(topic, payload):
    payload_text = payload.decode(errors='replace')
    value = parse_value(payload_text)

    db = get_db()
    ts = datetime.now()
    
    db.execute(
        'INSERT INTO messages(topic, ts, payload, value) VALUES (?, ?, ?, ?)',
        (topic, ts, payload_text, value)
    )
    db.commit()

    if value is not None:
        socketio.emit(
            'new_data',
            {
                'topic': topic,
                'ts': ts.isoformat(sep=' '),
                'value': value
            }
        )

def on_connect(client, userdata, flags, rc, properties=None):
    if rc==0:
        print('MQTT connected')
        topics = [t.strip() for t in MQTT_TOPICS.split(',') if t.strip()]
        for t in topics:
            client.subscribe(t)
            print('Subscribed to', t)
    else:
        print('MQTT connect rc', rc)

def on_message(client, userdata, msg):
    print("MQTT message received:", msg.topic, msg.payload)
    try:
        with app.app_context():
            store_message(msg.topic, msg.payload)
    except Exception as e:
        print('store error', e, file=sys.stderr)

def is_admin():
    return session.get("is_admin", False)

def mqtt_worker():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT)
            client.loop_forever()
        except Exception as e:
            print('mqtt error', e, file=sys.stderr)
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

@app.route('/api/topics')
def api_topics():
    admin = is_admin()
    db = get_db()

    sql = """
    SELECT m.topic,
           COUNT(*) AS count,
           COALESCE(t.public, 1) AS public
    FROM messages m
    LEFT JOIN topic_meta t ON m.topic = t.topic
    """

    if not admin:
        sql += " WHERE COALESCE(t.public,1)=1"

    sql += " GROUP BY m.topic ORDER BY count DESC"

    cur = db.execute(sql)
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route('/api/data', methods=['GET'])
def api_data():
    topic = request.args.get('topic')
    if not topic:
        return jsonify({'error':'missing topic'}),400
    
    db = get_db()

    if not is_admin():
        cur = db.execute(
            "SELECT COALESCE(public,1) FROM topic_meta WHERE topic=?",
            (topic,)
        )
        row = cur.fetchone()
        if row and row[0] == 0:
            return jsonify({'error': 'topic not public'}), 403

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
    if not topic:
        return jsonify({'error':'missing topic'}),400

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

@app.route('/viewer')
def viewer():
    conn = get_db()
    cursor = conn.cursor()

    topic = request.args.get("topic")
    limit = int(request.args.get("limit", 100))

    if topic:
        cursor.execute("""
            SELECT topic, payload, ts
            FROM messages
            WHERE topic = ?
            ORDER BY ts DESC
            LIMIT ?
        """, (topic, limit))
    else:
        cursor.execute("""
            SELECT topic, payload, ts
            FROM messages
            ORDER BY ts DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/version")
def api_version():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("SELECT value FROM metadata WHERE key='app_version'")
    row = cur.fetchone()
    db.close()
    return {"version": row[0] if row else "unknown"}

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = sqlite3.connect(DB_PATH)
        cur = db.execute(
            "SELECT password_hash FROM admin_users WHERE username=?",
            (username,)
        )
        row = cur.fetchone()
        db.close()

        if row and check_password_hash(row[0], password):
            session["is_admin"] = True
            session["admin_user"] = username
            return redirect("/")

        return render_template(
            "admin_login.html",
            error="Invalid username or password"
        )

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/")

@app.route('/')
def index():
    return render_template(
        "index.html",
        broker=f"{MQTT_BROKER}:{MQTT_PORT}",
        admin=is_admin(),
        admin_user=session.get("admin_user")
    )

@app.route("/api/admin/topic/<path:topic>", methods=["DELETE"])
def admin_delete_topic(topic):
    require_admin()
    if not is_admin():
        return jsonify({"error": "admin required"}), 403

    db = get_db()
    cur = db.execute("DELETE FROM messages WHERE topic = ?", (topic,))
    db.commit()

    return jsonify({
        "status": "ok",
        "topic": topic,
        "deleted_rows": cur.rowcount
    })

def publish_mqtt(topic, payload):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.publish(topic, payload, qos=1, retain=False)
    client.disconnect()

@app.route("/api/admin/ota", methods=["POST"])
def admin_ota():
    require_admin()
    if not is_admin():
        return jsonify({"error": "admin required"}), 403

    data = request.get_json(force=True)
    base_topic = data.get("base_topic")
    ota_value = data.get("ota")

    if ota_value not in (0, 1):
        return jsonify({"error": "ota must be 0 or 1"}), 400

    ota_topic = f"{base_topic}/ota"
    publish_mqtt(ota_topic, str(ota_value))

    return jsonify({
        "status": "ok",
        "topic": ota_topic,
        "value": ota_value
    })

@app.route('/api/admin/topic_visibility', methods=['POST'])
def admin_topic_visibility():
    require_admin()
    data = request.get_json()
    topic = data['topic']
    public = 1 if data['public'] else 0

    db = get_db()
    db.execute("""
    INSERT INTO topic_meta(topic, public)
    VALUES (?,?)
    ON CONFLICT(topic) DO UPDATE SET public=excluded.public
    """, (topic, public))
    db.commit()

    return jsonify({'status': 'ok'})


def main():
    # --- Startup / environment verification ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logging.info("MQTTPlot starting — version %s", __version__)
    logging.info("Python executable: %s", sys.executable)
    logging.info("Python prefix: %s", sys.prefix)
    logging.info("Working directory: %s", os.getcwd())

    # Optional hard guard to prevent wrong interpreter usage
    if not sys.executable.startswith("/opt/mqttplot/venv/"):
        logging.critical("NOT running inside mqttplot virtualenv — aborting")
        sys.exit(1)


    init_db()
    record_app_version(__version__)
    init_admin_user()
    t = threading.Thread(target=mqtt_worker, daemon=True)
    t.start()
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT)

if __name__ == '__main__':
    main()
