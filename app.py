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
    """
    Compact per-top-level DB schema (v2):
      - topics table stores unique topic strings once
      - messages stores (topic_id, ts_epoch, value)
      - ts stored as INTEGER epoch seconds
      - payload not stored to reduce size
    """
    db = sqlite3.connect(db_path)
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL UNIQUE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        topic_id INTEGER NOT NULL,
        ts INTEGER NOT NULL,
        value REAL NOT NULL,
        FOREIGN KEY(topic_id) REFERENCES topics(id)
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_topic_ts ON messages(topic_id, ts)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts)")

    db.commit()
    db.close()


def get_or_create_topic_id(con: sqlite3.Connection, topic: str) -> int:
    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    row = cur.fetchone()
    if row:
        return int(row["id"])

    con.execute("INSERT INTO topics(topic) VALUES (?)", (topic,))
    con.commit()

    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    return int(cur.fetchone()["id"])



def get_data_db(topic: str) -> sqlite3.Connection:
    os.makedirs(DATA_DB_DIR, exist_ok=True)
    tl = top_level_topic(topic)
    db_path = os.path.join(DATA_DB_DIR, f"{tl}.db")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    ensure_data_db_schema_v2(con)
    return con


def get_or_create_topic_id(con: sqlite3.Connection, topic: str) -> int:
    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    row = cur.fetchone()
    if row:
        return int(row["id"])

    con.execute("INSERT INTO topics(topic) VALUES (?)", (topic,))
    con.commit()
    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    return int(cur.fetchone()["id"])


def update_topic_stats(topic: str, ts: datetime, value) -> None:
    """
    Maintain a lightweight index in the MAIN DB so /api/topics is fast without
    scanning all per-top-level databases.

    Assumes topic_stats schema includes:
      topic, top_level, count, first_ts, last_ts, min_val, max_val, last_value
    """
    db = get_db()

    # First insert a new row if needed
    db.execute("""
        INSERT INTO topic_stats(topic, top_level, count, first_ts, last_ts, min_val, max_val, last_value)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
        ON CONFLICT(topic) DO UPDATE SET
            -- always keep the topic's top_level current (in case parsing changes)
            top_level = excluded.top_level,

            -- count increments on every accepted message
            count = topic_stats.count + 1,

            -- first_ts should remain the earliest seen
            first_ts = CASE
                WHEN topic_stats.first_ts IS NULL THEN excluded.first_ts
                WHEN excluded.first_ts < topic_stats.first_ts THEN excluded.first_ts
                ELSE topic_stats.first_ts
            END,

            -- last_ts and last_value always update to newest seen
            last_ts = excluded.last_ts,
            last_value = excluded.last_value,

            -- expand numeric bounds
            min_val = CASE
                WHEN topic_stats.min_val IS NULL THEN excluded.min_val
                WHEN excluded.min_val < topic_stats.min_val THEN excluded.min_val
                ELSE topic_stats.min_val
            END,
            max_val = CASE
                WHEN topic_stats.max_val IS NULL THEN excluded.max_val
                WHEN excluded.max_val > topic_stats.max_val THEN excluded.max_val
                ELSE topic_stats.max_val
            END
    """, (
        topic,
        top_level_topic(topic),
        ts,
        ts,
        float(value),
        float(value),
        float(value)
    ))

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
    policy = get_retention_policy(top_level)
    if not policy:
        return

    db_path = os.path.join(DATA_DB_DIR, f"{top_level}.db")
    if not os.path.exists(db_path):
        return

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_data_db_schema_v2(con)
    cur = con.cursor()

    # Age-based retention
    max_age_days = policy.get("max_age_days")
    if max_age_days is not None and max_age_days > 0:
        cutoff_epoch = int(time.time() - (int(max_age_days) * 86400))
        cur.execute("DELETE FROM messages WHERE ts < ?", (cutoff_epoch,))
        con.commit()

    # Row-count retention (overall for the top-level DB)
    max_rows = policy.get("max_rows")
    if max_rows is not None and max_rows > 0:
        cur.execute("SELECT COUNT(*) AS n FROM messages")
        n = int(cur.fetchone()["n"])
        if n > max_rows:
            excess = n - max_rows
            cur.execute("""
                DELETE FROM messages
                WHERE rowid IN (
                    SELECT rowid FROM messages
                    ORDER BY ts ASC, rowid ASC
                    LIMIT ?
                )
            """, (excess,))
            con.commit()

    con.close()

    # Optional: refresh stats after retention (keep if you want UI counts accurate)
    try:
        refresh_topic_stats_for_top_level(top_level)
    except Exception:
        logging.exception("Failed to refresh topic_stats after retention for top_level=%s", top_level)


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
        top_level TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        first_ts TIMESTAMP,
        last_ts TIMESTAMP,
        min_val REAL,
        max_val REAL,
        last_value REAL
    );
    """)

    # --- Schema migration: ensure topic_stats has min_val/max_val columns (v0.6.0) ---
    cur = db.execute("PRAGMA table_info(topic_stats)")
    cols = {row[1] for row in cur.fetchall()}  # row[1] is column name

    if "min_val" not in cols:
        db.execute("ALTER TABLE topic_stats ADD COLUMN min_val REAL")
    if "max_val" not in cols:
        db.execute("ALTER TABLE topic_stats ADD COLUMN max_val REAL")

    db.commit()

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

import time  # add at top if not present

import time

def store_message(topic, payload):
    payload_text = payload.decode(errors='replace')
    value = parse_value(payload_text)

    # Validate numeric value before storing
    if value is None:
        return

    if not value_is_valid(topic, value):
        logging.warning("Dropped out-of-range value: topic=%s value=%s payload=%s", topic, value, payload_text)
        return

    ts_epoch = int(time.time())
    ts_dt = datetime.fromtimestamp(ts_epoch)

    # 1) Write compact time-series data into per-top-level DB
    data_db = get_data_db(topic)
    topic_id = get_or_create_topic_id(data_db, topic)

    data_db.execute(
        "INSERT INTO messages(topic_id, ts, value) VALUES (?, ?, ?)",
        (topic_id, ts_epoch, float(value))
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
    update_topic_stats(topic, ts_dt, float(value))

    # 4) Enforce retention policy for the top-level DB (best-effort)
    try:
        enforce_retention_for_top_level(top_level_topic(topic))
    except Exception:
        logging.exception("Retention enforcement failed for top-level=%s", top_level_topic(topic))

    # 5) Emit live update (ISO for browser)
    socketio.emit(
        'new_data',
        {
            'topic': topic,
            'ts': ts_dt.isoformat(),
            'value': float(value)
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

def refresh_topic_stats_for_top_level(top_level: str) -> None:
    """
    Recompute topic_stats entries for all topics stored in <DATA_DB_DIR>/<top_level>.db
    using v2 compact schema:
      - topics(id, topic)
      - messages(topic_id, ts_epoch, value)

    Updates the main DB so the UI counts reflect retention purges.
    """
    db_path = os.path.join(DATA_DB_DIR, f"{top_level}.db")
    if not os.path.exists(db_path):
        return

    data_db = sqlite3.connect(db_path)
    data_db.row_factory = sqlite3.Row
    ensure_data_db_schema_v2(data_db)
    cur = data_db.cursor()

    # Aggregate remaining data by full topic via join on topics
    cur.execute("""
        SELECT
            t.topic AS topic,
            COUNT(*) AS count,
            MIN(m.ts) AS first_ts_epoch,
            MAX(m.ts) AS last_ts_epoch,
            MIN(m.value) AS min_val,
            MAX(m.value) AS max_val
        FROM messages m
        JOIN topics t ON t.id = m.topic_id
        GROUP BY t.topic
        ORDER BY t.topic
    """)
    rows = cur.fetchall()
    data_db.close()

    main = get_db()

    # Remove existing stats for this top-level (topics have NO leading slash in your system)
    prefix = f"{top_level}/%"
    exact = f"{top_level}"
    main.execute("DELETE FROM topic_stats WHERE topic LIKE ? OR topic = ?", (prefix, exact))

    # Insert refreshed stats
    for r in rows:
        first_ts_iso = datetime.fromtimestamp(int(r["first_ts_epoch"])).isoformat()
        last_ts_iso = datetime.fromtimestamp(int(r["last_ts_epoch"])).isoformat()

        main.execute("""
            INSERT INTO topic_stats(topic, count, first_ts, last_ts, min_val, max_val)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                count=excluded.count,
                first_ts=excluded.first_ts,
                last_ts=excluded.last_ts,
                min_val=excluded.min_val,
                max_val=excluded.max_val
        """, (
            r["topic"],
            int(r["count"]),
            first_ts_iso,
            last_ts_iso,
            float(r["min_val"]) if r["min_val"] is not None else None,
            float(r["max_val"]) if r["max_val"] is not None else None,
        ))

    main.commit()


def ensure_data_db_schema_v2(con: sqlite3.Connection) -> None:
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            topic_id INTEGER NOT NULL,
            ts INTEGER NOT NULL,      -- epoch seconds
            value REAL NOT NULL,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_topic_ts ON messages(topic_id, ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts)")

    con.commit()


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

@app.route("/api/data")
def api_data():
    topic = request.args.get("topic")
    if not topic:
        return jsonify({"error": "missing topic"}), 400

    # (keep your visibility checks here)

    # Parse optional start/end (ISO strings)
    start = request.args.get("start")
    end = request.args.get("end")

    def to_epoch(s: str):
        if not s:
            return None
        try:
            # allow epoch numeric too
            if s.isdigit():
                return int(s)
            return int(datetime.fromisoformat(s).timestamp())
        except Exception:
            return None

    start_epoch = to_epoch(start)
    end_epoch = to_epoch(end)

    # Optional limit (if you still support it)
    limit = request.args.get("limit")
    try:
        limit = int(limit) if limit else None
    except Exception:
        limit = None
    if limit is not None:
        limit = max(1, min(limit, 200000))  # safety cap

    # Open per-top-level DB
    tl = top_level_topic(topic)
    db_path = os.path.join(DATA_DB_DIR, f"{tl}.db")
    if not os.path.exists(db_path):
        return jsonify([])

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_data_db_schema_v2(con)

    # Resolve topic_id
    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    row = cur.fetchone()
    if not row:
        con.close()
        return jsonify([])

    topic_id = int(row["id"])

    clauses = ["topic_id=?"]
    params = [topic_id]

    if start_epoch is not None:
        clauses.append("ts >= ?")
        params.append(start_epoch)
    if end_epoch is not None:
        clauses.append("ts <= ?")
        params.append(end_epoch)

    where_sql = " AND ".join(clauses)

    sql = f"SELECT ts, value FROM messages WHERE {where_sql} ORDER BY ts ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    cur = con.execute(sql, tuple(params))
    rows = cur.fetchall()
    con.close()

    # Convert epoch -> ISO for frontend
    out = []
    for r in rows:
        out.append({
            "ts": datetime.fromtimestamp(int(r["ts"])).isoformat(),
            "value": float(r["value"])
        })
    return jsonify(out)


@app.route("/api/bounds")
def api_bounds():
    topic = request.args.get("topic")
    if not topic:
        return jsonify({"error": "missing topic"}), 400

    # (keep your visibility checks here)

    tl = top_level_topic(topic)
    db_path = os.path.join(DATA_DB_DIR, f"{tl}.db")
    if not os.path.exists(db_path):
        return jsonify({"error": "no data"}), 404

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_data_db_schema_v2(con)

    cur = con.execute("SELECT id FROM topics WHERE topic=?", (topic,))
    row = cur.fetchone()
    if not row:
        con.close()
        return jsonify({"error": "no data"}), 404

    topic_id = int(row["id"])

    cur = con.execute("SELECT MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM messages WHERE topic_id=?", (topic_id,))
    r = cur.fetchone()
    con.close()

    if r["min_ts"] is None or r["max_ts"] is None:
        return jsonify({"error": "no data"}), 404

    return jsonify({
        "min_ts": datetime.fromtimestamp(int(r["min_ts"])).isoformat(),
        "max_ts": datetime.fromtimestamp(int(r["max_ts"])).isoformat(),
    })


@app.route('/viewer')
def viewer():
    conn = get_db()
    cursor = conn.cursor()

    topic = request.args.get("topic")

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

    # Allow null/blank to mean "no retention"
    def norm_int(x):
        if x is None:
            return None
        if isinstance(x, str) and x.strip() == "":
            return None
        try:
            return int(x)
        except Exception:
            return None

    max_age_days = norm_int(body.get("max_age_days"))
    max_rows = norm_int(body.get("max_rows"))

    db = get_db()
    db.execute("""
        INSERT INTO retention_policies(top_level, max_age_days, max_rows)
        VALUES (?, ?, ?)
        ON CONFLICT(top_level) DO UPDATE SET
            max_age_days=excluded.max_age_days,
            max_rows=excluded.max_rows
    """, (top_level, max_age_days, max_rows))
    db.commit()

    # Apply immediately so the UI reflects the change without waiting for new MQTT messages
    try:
        enforce_retention_for_top_level(top_level)
    except Exception:
        logging.exception("Retention enforcement failed on save for top_level=%s", top_level)
        # Keep returning ok for the save itself; enforcement failures are logged

    return jsonify({
        "status": "ok",
        "top_level": top_level,
        "max_age_days": max_age_days,
        "max_rows": max_rows
    })

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

    # @app.route("/api/admin/retention/apply", methods=["POST"])
    # def admin_apply_retention(): 
    #     require_admin()
    #     body = request.get_json(force=True) or {}
    #     top_level = body.get("top_level")
    #     if not top_level:
    #         return jsonify({"error": "missing top_level"}), 400

    #     try:
    #         enforce_retention_for_top_level(top_level)
    #     except Exception as e:
    #         logging.exception("Retention apply failed for %s", top_level)
    #         return jsonify({"error": str(e)}), 500

    #     return jsonify({"status": "ok", "top_level": top_level})

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
