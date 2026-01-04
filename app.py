#!/usr/bin/env python3
"""MQTTPlot - app.py"""
import eventlet
eventlet.monkey_patch()
import sys, os, io, json, time, threading, sqlite3, logging
from datetime import datetime, timedelta
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
DATA_DB_DIR = os.environ.get('DATA_DB_DIR','/opt/mqttplot/data')
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

def top_level_topic(topic: str) -> str:
    """
    Returns the top-level topic segment.
    Examples:
      "/watergauge/temp" -> "watergauge"
      "watergauge/temp"  -> "watergauge"
      "/" or ""          -> "_root"
    """
    if not topic:
        return "_root"
    t = topic.strip()
    if t.startswith("/"):
        t = t[1:]
    if not t:
        return "_root"
    return t.split("/", 1)[0] or "_root"

def data_db_path_for_topic(topic: str) -> str:
    root = top_level_topic(topic)
    os.makedirs(DATA_DB_DIR, exist_ok=True)
    return os.path.join(DATA_DB_DIR, f"{root}.db")


def init_data_db(db_path: str) -> None:
    db = sqlite3.connect(db_path)
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_topic_ts ON messages(topic, ts)")
    db.commit()
    db.close()


def get_data_db(topic: str) -> sqlite3.Connection:
    """
    Opens (and initializes if needed) the per-top-level SQLite DB for the given topic.
    """
    path = data_db_path_for_topic(topic)
    if not os.path.exists(path):
        init_data_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def update_topic_stats(topic: str, ts: datetime, value) -> None:
    """
    Maintain a lightweight index in the MAIN DB so /api/topics is fast without
    scanning all per-topic databases.
    """
    db = get_db()
    db.execute("""
    INSERT INTO topic_stats(topic, top_level, count, first_ts, last_ts, last_value)
    VALUES (?, ?, 1, ?, ?, ?)
    ON CONFLICT(topic) DO UPDATE SET
        count = count + 1,
        last_ts = excluded.last_ts,
        last_value = excluded.last_value
    """, (topic, top_level_topic(topic), ts, ts, value))
    db.commit()

def get_validation_rule(topic: str):
    db = get_db()
    cur = db.execute(
        "SELECT min_value, max_value, enabled FROM validation_rules WHERE topic=?",
        (topic,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "min": row["min_value"],
        "max": row["max_value"],
        "enabled": bool(row["enabled"])
    }

def value_is_valid(topic: str, value) -> bool:
    """
    Returns True if value passes the validation rules for the topic.
    If no rule exists, treat as valid.
    """
    if value is None:
        return False  # keep current behavior: we only store numeric values

    rule = get_validation_rule(topic)
    if not rule or not rule["enabled"]:
        return True

    vmin = rule["min"]
    vmax = rule["max"]

    if vmin is not None and value < vmin:
        return False
    if vmax is not None and value > vmax:
        return False

    return True

def get_retention_policy(top_level: str):
    db = get_db()
    cur = db.execute(
        "SELECT max_age_days, max_rows FROM retention_policies WHERE top_level=?",
        (top_level,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "max_age_days": row["max_age_days"],
        "max_rows": row["max_rows"]
    }

def enforce_retention_for_top_level(top_level: str) -> None:
    """
    Enforce retention policy for a single top-level topic database.
    Deletes old rows based on max_age_days and/or trims to max_rows.
    """
    policy = get_retention_policy(top_level)
    if not policy:
        return

    # Open the per-top-level DB directly
    db_path = os.path.join(DATA_DB_DIR, f"{top_level}.db")
    if not os.path.exists(db_path):
        return

    data_db = sqlite3.connect(db_path)
    data_db.row_factory = sqlite3.Row
    cur = data_db.cursor()

    # 1) Age-based retention
    max_age_days = policy["max_age_days"]
    if max_age_days is not None and max_age_days > 0:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        cur.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
        data_db.commit()

    # 2) Row-count retention (keep newest N rows)
    max_rows = policy["max_rows"]
    if max_rows is not None and max_rows > 0:
        # count total
        cur.execute("SELECT COUNT(*) AS n FROM messages")
        n = cur.fetchone()["n"]
        if n > max_rows:
            excess = n - max_rows
            # delete oldest 'excess' rows by timestamp/id
            cur.execute("""
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    ORDER BY ts ASC, id ASC
                    LIMIT ?
                )
            """, (excess,))
            data_db.commit()

    data_db.close()

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
        password = os.environ.get("ADMIN_INIT_PASSWORD")
        if not password:
            raise RuntimeError(
                "ADMIN_INIT_PASSWORD not set during first initialization"
            )

        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash(password))
        )
        print("✔ Admin user created")

    db.commit()
    db.close()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g,'_database',None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # Main DB no longer needs the big messages table for queries,
    # but we keep topic_meta + add topic_stats for fast topic listing.
    c.execute("""
    CREATE TABLE IF NOT EXISTS topic_meta (
        topic TEXT PRIMARY KEY,
        public INTEGER DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS topic_stats (
        topic TEXT PRIMARY KEY,
        top_level TEXT,
        count INTEGER DEFAULT 0,
        first_ts TIMESTAMP,
        last_ts TIMESTAMP,
        last_value REAL
    )
    """)

    # Retention policies per top-level topic
    c.execute("""
    CREATE TABLE IF NOT EXISTS retention_policies (
        top_level TEXT PRIMARY KEY,
        max_age_days INTEGER,   -- NULL means no age-based retention
        max_rows INTEGER        -- NULL means no row-count retention
    )
    """)

    # Validation rules per full topic (subtopic)
    c.execute("""
    CREATE TABLE IF NOT EXISTS validation_rules (
        topic TEXT PRIMARY KEY,
        min_value REAL,         -- NULL means no min
        max_value REAL,         -- NULL means no max
        enabled INTEGER DEFAULT 1
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_topic_stats_count ON topic_stats(count)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_topic_stats_top_level ON topic_stats(top_level)")
    db.commit()
    db.close()

    # Ensure the data directory exists
    os.makedirs(DATA_DB_DIR, exist_ok=True)

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
    ts = datetime.now()

    # Validate numeric value before storing
    if value is None:
        return

    if not value_is_valid(topic, value):
        logging.warning("Dropped out-of-range value: topic=%s value=%s payload=%s", topic, value, payload_text)
        return

    # 1) Write time-series data into per-top-level DB
    data_db = get_data_db(topic)
    data_db.execute(
        'INSERT INTO messages(topic, ts, payload, value) VALUES (?, ?, ?, ?)',
        (topic, ts, payload_text, value)
    )
    data_db.commit()
    data_db.close()

    # 2) Ensure topic exists in metadata (main DB)
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO topic_meta(topic, public) VALUES (?, 1)",
        (topic,)
    )
    db.commit()

    # 3) Update lightweight stats (main DB)
    update_topic_stats(topic, ts, value)

    # 4) Enforce retention policy for the top-level DB (best-effort)
    try:
        enforce_retention_for_top_level(top_level_topic(topic))
    except Exception:
        logging.exception("Retention enforcement failed for top-level=%s", top_level_topic(topic))

    # 5) Emit live update (strict ISO 8601)
    socketio.emit(
        'new_data',
        {
            'topic': topic,
            'ts': ts.isoformat(),
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
    SELECT s.topic,
           s.count AS count,
           COALESCE(m.public, 1) AS public
    FROM topic_stats s
    LEFT JOIN topic_meta m ON s.topic = m.topic
    """

    if not admin:
        sql += " WHERE COALESCE(m.public,1)=1"

    sql += " ORDER BY s.count DESC"

    cur = db.execute(sql)
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route('/api/data', methods=['GET'])
def api_data():
    topic = request.args.get('topic')
    if not topic:
        return jsonify({'error':'missing topic'}), 400

    # Visibility check uses main DB
    if not is_admin():
        db = get_db()
        cur = db.execute(
            "SELECT COALESCE(public,1) AS public FROM topic_meta WHERE topic=?",
            (topic,)
        )
        row = cur.fetchone()
        if row and row["public"] == 0:
            return jsonify({'error': 'topic not public'}), 403

    start = request.args.get('start')
    end = request.args.get('end')
    limit = int(request.args.get('limit', PLOT_CONFIG['max_points']))

    sql = 'SELECT ts, value FROM messages WHERE topic=? AND value IS NOT NULL'
    params = [topic]
    if start:
        sql += ' AND ts >= ?'
        params.append(parse_time(start))
    if end:
        sql += ' AND ts <= ?'
        params.append(parse_time(end))
    sql += ' ORDER BY ts ASC LIMIT ?'
    params.append(limit)

    data_db = get_data_db(topic)
    cur = data_db.execute(sql, params)
    rows = [{'ts': r['ts'], 'value': r['value']} for r in cur.fetchall()]
    data_db.close()

    # Normalize timestamps for JS (strict ISO 8601)
    for r in rows:
        if not isinstance(r['ts'], str):
            r['ts'] = r['ts'].isoformat()

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

@app.route('/api/bounds', methods=['GET'])
def api_bounds():
    topic = request.args.get('topic')
    if not topic:
        return jsonify({'error': 'missing topic'}), 400

    # Same visibility rule as /api/data
    if not is_admin():
        db = get_db()
        cur = db.execute(
            "SELECT COALESCE(public,1) AS public FROM topic_meta WHERE topic=?",
            (topic,)
        )
        row = cur.fetchone()
        if row and row["public"] == 0:
            return jsonify({'error': 'topic not public'}), 403

    data_db = get_data_db(topic)
    cur = data_db.execute(
        "SELECT MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM messages WHERE topic=? AND value IS NOT NULL",
        (topic,)
    )
    row = cur.fetchone()
    data_db.close()

    if not row or (row["min_ts"] is None) or (row["max_ts"] is None):
        return jsonify({'error': 'no data'}), 404

    min_ts = row["min_ts"].isoformat() if not isinstance(row["min_ts"], str) else row["min_ts"]
    max_ts = row["max_ts"].isoformat() if not isinstance(row["max_ts"], str) else row["max_ts"]

    return jsonify({'min_ts': min_ts, 'max_ts': max_ts})

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

    data_db = get_data_db(topic)
    cur = data_db.execute("DELETE FROM messages WHERE topic = ?", (topic,))
    data_db.commit()
    data_db.close()

    # Remove from topic_stats (main DB), keep topic_meta (visibility) unless you prefer to remove it too
    db = get_db()
    db.execute("DELETE FROM topic_stats WHERE topic = ?", (topic,))
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

@app.route("/api/admin/retention", methods=["GET"])
def admin_get_retention():
    require_admin()
    db = get_db()
    cur = db.execute("SELECT top_level, max_age_days, max_rows FROM retention_policies ORDER BY top_level")
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/admin/retention", methods=["POST"])
def admin_set_retention():
    require_admin()
    body = request.get_json(force=True) or {}
    top_level = body.get("top_level")
    if not top_level:
        return jsonify({"error": "missing top_level"}), 400

    # Allow nulls to mean "no retention"
    max_age_days = body.get("max_age_days")
    max_rows = body.get("max_rows")

    def norm_int(x):
        if x is None or x == "":
            return None
        try:
            return int(x)
        except Exception:
            return None

    max_age_days = norm_int(max_age_days)
    max_rows = norm_int(max_rows)

    db = get_db()
    db.execute("""
        INSERT INTO retention_policies(top_level, max_age_days, max_rows)
        VALUES (?, ?, ?)
        ON CONFLICT(top_level) DO UPDATE SET
            max_age_days=excluded.max_age_days,
            max_rows=excluded.max_rows
    """, (top_level, max_age_days, max_rows))
    db.commit()

    return jsonify({"status": "ok", "top_level": top_level, "max_age_days": max_age_days, "max_rows": max_rows})

@app.route("/api/admin/validation", methods=["GET"])
def admin_get_validation():
    require_admin()
    topic = request.args.get("topic")
    db = get_db()
    if topic:
        cur = db.execute("SELECT topic, min_value, max_value, enabled FROM validation_rules WHERE topic=?", (topic,))
        row = cur.fetchone()
        return jsonify(dict(row) if row else None)

    cur = db.execute("SELECT topic, min_value, max_value, enabled FROM validation_rules ORDER BY topic")
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/admin/validation", methods=["POST"])
def admin_set_validation():
    require_admin()
    body = request.get_json(force=True) or {}
    topic = body.get("topic")
    if not topic:
        return jsonify({"error": "missing topic"}), 400

    def norm_float(x):
        if x is None or x == "":
            return None
        try:
            return float(x)
        except Exception:
            return None

    min_value = norm_float(body.get("min_value"))
    max_value = norm_float(body.get("max_value"))
    enabled = 1 if bool(body.get("enabled", True)) else 0

    db = get_db()
    db.execute("""
        INSERT INTO validation_rules(topic, min_value, max_value, enabled)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(topic) DO UPDATE SET
            min_value=excluded.min_value,
            max_value=excluded.max_value,
            enabled=excluded.enabled
    """, (topic, min_value, max_value, enabled))
    db.commit()

    return jsonify({"status": "ok", "topic": topic, "min_value": min_value, "max_value": max_value, "enabled": bool(enabled)})

    @app.route("/api/admin/retention/apply", methods=["POST"])
    def admin_apply_retention():
        require_admin()
        body = request.get_json(force=True) or {}
        top_level = body.get("top_level")
        if not top_level:
            return jsonify({"error": "missing top_level"}), 400

        try:
            enforce_retention_for_top_level(top_level)
        except Exception as e:
            logging.exception("Retention apply failed for %s", top_level)
            return jsonify({"error": str(e)}), 500

        return jsonify({"status": "ok", "top_level": top_level})

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

    # Optional hard guard to prevent wrong interpreter usage (cross-platform)
    expected_venv_prefix = os.environ.get("MQTTPLOT_VENV_PREFIX")

    if expected_venv_prefix:
        # Normalize slashes and case for Windows paths
        exe = os.path.normcase(os.path.abspath(sys.executable))
        expected = os.path.normcase(os.path.abspath(expected_venv_prefix))

        if not exe.startswith(expected):
            logging.critical(
                "NOT running inside expected virtualenv — aborting. exe=%s expected_prefix=%s",
                sys.executable, expected_venv_prefix
            )
            sys.exit(1)
    else:
        # No guard configured; allow normal development workflows
        logging.info("MQTTPLOT_VENV_PREFIX not set — skipping interpreter guard")

    init_db()
    record_app_version(__version__)
    init_admin_user()
    t = threading.Thread(target=mqtt_worker, daemon=True)
    t.start()
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT)

if __name__ == '__main__':
    main()
