#!/usr/bin/env python3
"""MQTTPlot - app.py"""

import sys, os, socket
ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE")

# Default behavior:
# - In VS Code/debugpy on Windows: use "threading"
# - Otherwise: use "eventlet"
if not ASYNC_MODE:
    if os.name == "nt" and ("debugpy" in sys.modules or 
                            sys.gettrace() is not None):
        ASYNC_MODE = "threading"
    else:
        ASYNC_MODE = "eventlet"

if ASYNC_MODE == "eventlet":
    import eventlet
    eventlet.monkey_patch()

import io, json, time, threading, sqlite3, logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, send_file
from flask import session, redirect, abort, url_for
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import plotly.graph_objects as go
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from version import __version__

from . import config
from .storage import (
    get_db, close_db, init_db, record_app_version, init_admin_user,
    get_validation_rule, get_retention_policy, top_level_topic, 
    get_data_db, enforce_retention_for_top_level
)
from .mqtt_client import mqtt_worker, get_status
from .auth import is_admin

PLOT_CONFIG = config.PLOT_CONFIG

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), 
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = config.SECRET_KEY or secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=ASYNC_MODE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True
)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("engineio").setLevel(logging.ERROR)
logging.getLogger("socketio").setLevel(logging.ERROR)


print(f"MQTTPlot starting — version {__version__}")

stop_event = threading.Event()
t = threading.Thread(target=mqtt_worker, 
                     args=(app, socketio, stop_event,), 
                     daemon=True)
t.start()

def require_admin(): 
    if not is_admin():
        abort(403)

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
    Recompute topic_stats entries for all topics stored in <config.DATA_DB_DIR>/<top_level>.db
    using v2 compact schema:
      - topics(id, topic)
      - messages(topic_id, ts, value)   # ts is epoch seconds

    Updates the main metadata DB so the UI counts reflect retention purges.

    Canonical columns written:
      - topic, top_level, message_count, first_seen, last_seen, min_val, max_val
    """
    db_path = os.path.join(config.DATA_DB_DIR, f"{top_level}.db")
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
            COUNT(*) AS message_count,
            MIN(m.ts) AS first_seen,
            MAX(m.ts) AS last_seen,
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

    # Insert refreshed stats (canonical)
    for r in rows:
        topic = r["topic"]
        main.execute("""
            INSERT INTO topic_stats(topic, top_level, message_count, first_seen, last_seen, min_val, max_val)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                top_level=excluded.top_level,
                message_count=excluded.message_count,
                first_seen=excluded.first_seen,
                last_seen=excluded.last_seen,
                min_val=excluded.min_val,
                max_val=excluded.max_val
        """, (
            topic,
            top_level,
            int(r["message_count"]),
            float(r["first_seen"]) if r["first_seen"] is not None else None,
            float(r["last_seen"]) if r["last_seen"] is not None else None,
            float(r["min_val"]) if r["min_val"] is not None else None,
            float(r["max_val"]) if r["max_val"] is not None else None,
        ))

        # Ensure topic_meta exists for the topic (public defaults to 1)
        main.execute("""
            INSERT INTO topic_meta(topic, public)
            VALUES (?, 1)
            ON CONFLICT(topic) DO NOTHING
        """, (topic,))

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

@app.get("/api/mqtt/status")
def api_mqtt_status():
    return jsonify(get_status())

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

@app.route("/api/topics")
def api_topics():
    admin = is_admin()
    db = get_db()

    sql = """
    SELECT
        s.topic,
        s.message_count AS count,
        COALESCE(m.public, 1) AS public,
        s.first_seen,
        s.last_seen
    FROM topic_stats s
    LEFT JOIN topic_meta m ON s.topic = m.topic
    """

    if not admin:
        sql += " WHERE COALESCE(m.public,1)=1"

    sql += " ORDER BY s.message_count DESC"

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
    db_path = os.path.join(config.DATA_DB_DIR, f"{tl}.db")
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
    db_path = os.path.join(config.DATA_DB_DIR, f"{tl}.db")
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
    db = get_db()

    # Safe default + clamp
    DEFAULT_LIMIT = 200
    MAX_LIMIT = 2000

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    limit = max(1, min(limit, MAX_LIMIT))

    topic = request.args.get("topic")

    if topic:
        cur = db.execute("""
            SELECT topic, payload, ts
            FROM messages
            WHERE topic = ?
            ORDER BY ts DESC
            LIMIT ?
        """, (topic, limit))
    else:
        cur = db.execute("""
            SELECT topic, payload, ts
            FROM messages
            ORDER BY ts DESC
            LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/version")
def api_version():
    db = sqlite3.connect(config.DB_PATH)
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

        db = sqlite3.connect(config.DB_PATH)
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
        broker=f"{config.MQTT_BROKER}:{config.MQTT_PORT}",
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
    if config.MQTT_USERNAME:
        client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
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
    # t = threading.Thread(target=mqtt_worker, daemon=True)
    # t.start()
    socketio.run(app, host='0.0.0.0', port=config.FLASK_PORT)

if __name__ == '__main__':
    main()
