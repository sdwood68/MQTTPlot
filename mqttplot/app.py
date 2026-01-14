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
    get_meta_db, close_meta_db, init_meta_db, record_app_version, init_admin_user,
    topic_root, get_data_db, enforce_retention_for_topic, ensure_topic_db
)
from .mqtt_client import mqtt_worker, get_status
from .auth import is_admin

PLOT_CONFIG = config.PLOT_CONFIG

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), 
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = config.SECRET_KEY or secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=ASYNC_MODE)

# --- MQTT worker lifecycle (do NOT start at import time) ---
_mqtt_started = False
_stop_event = None
_mqtt_thread = None

def start_mqtt_worker() -> None:
    """Start the MQTT worker thread once (safe to call multiple times)."""
    global _mqtt_started, _stop_event, _mqtt_thread

    if _mqtt_started:
        return

    _mqtt_started = True
    _stop_event = threading.Event()

    _mqtt_thread = threading.Thread(
        target=mqtt_worker,
        args=(app, socketio, _stop_event),
        daemon=True,
        name="mqtt_worker",
    )
    _mqtt_thread.start()


# stop_event = threading.Event()
# t = threading.Thread(target=mqtt_worker, 
#                      args=(app, socketio, stop_event,), 
#                      daemon=True)
# t.start()

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
def api_meta_topics():
    """
    Return topic metadata list, with admin filtering.
    :return: List of topic metadata dicts
    :rtype: list[dict]
    """
    admin = is_admin()
    db = get_meta_db()

    sql = """
    SELECT
        s.topic,
        s.message_count AS count,
        COALESCE(m.public, 1) AS public,
        s.first_seen_ts_epoch AS first_seen,
        s.last_seen_ts_epoch AS last_seen
    FROM topic_stats s
    LEFT JOIN topic_meta m ON s.topic = m.topic
    """

    if not admin:
        sql += " WHERE COALESCE(m.public,1)=1"

    sql += " ORDER BY s.message_count DESC"

    rows = db.execute(sql).fetchall()

    def iso_or_none(x):
        if x is None:
            return None
        try:
            return datetime.fromtimestamp(float(x)).isoformat()
        except Exception:
            return None

    out = []
    for r in rows:
        d = dict(r)
        # keep raw epochs if you want, but typical UI wants ISO
        d["first_seen_iso"] = iso_or_none(d.get("first_seen"))
        d["last_seen_iso"] = iso_or_none(d.get("last_seen"))
        out.append(d)

    return jsonify(out)

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
    cur = get_meta_db().execute(sql, params)
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

    start = request.args.get("start")
    end = request.args.get("end")

    def to_epoch(s: str):
        if not s:
            return None
        try:
            if s.isdigit():
                return float(s)
            return float(datetime.fromisoformat(s).timestamp())
        except Exception:
            return None

    start_epoch = to_epoch(start)
    end_epoch = to_epoch(end)

    limit = request.args.get("limit")
    try:
        limit = int(limit) if limit else None
    except Exception:
        limit = None
    if limit is not None:
        limit = max(1, min(limit, 200000))

    tl = topic_root(topic)
    db_path = os.path.join(config.DATA_DB_DIR, f"{tl}.db")
    if not os.path.exists(db_path):
        return jsonify([])

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_topic_db(con)

    row = con.execute("SELECT id FROM topics WHERE topic=?", (topic,)).fetchone()
    if not row:
        con.close()
        return jsonify([])

    topic_id = int(row["id"])

    clauses = ["topic_id=?"]
    params = [topic_id]

    if start_epoch is not None:
        clauses.append("ts_epoch >= ?")
        params.append(start_epoch)
    if end_epoch is not None:
        clauses.append("ts_epoch <= ?")
        params.append(end_epoch)

    where_sql = " AND ".join(clauses)

    sql = f"SELECT ts_epoch, value FROM messages WHERE {where_sql} ORDER BY ts_epoch ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()

    out = []
    for r in rows:
        out.append({
            "ts": datetime.fromtimestamp(float(r["ts_epoch"])).isoformat(),
            "value": float(r["value"]) if r["value"] is not None else None
        })
    return jsonify(out)

@app.route("/api/bounds")
def api_topic_bounds():
    """
    Return min/max timestamp bounds for a given topic.
    :return: JSON with min_ts and max_ts in ISO format
    :rtype: dict
    """
    topic = request.args.get("topic")
    if not topic:
        return jsonify({"error": "missing topic"}), 400

    tl = topic_root(topic)
    db_path = os.path.join(config.DATA_DB_DIR, f"{tl}.db")
    if not os.path.exists(db_path):
        return jsonify({"error": "no data"}), 404

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_topic_db(con)

    row = con.execute("SELECT id FROM topics WHERE topic=?", (topic,)).fetchone()
    if not row:
        con.close()
        return jsonify({"error": "no data"}), 404

    topic_id = int(row["id"])

    r = con.execute(
        "SELECT MIN(ts_epoch) AS min_ts, MAX(ts_epoch) AS max_ts FROM messages WHERE topic_id=?",
        (topic_id,),
    ).fetchone()
    con.close()

    if r["min_ts"] is None or r["max_ts"] is None:
        return jsonify({"error": "no data"}), 404

    return jsonify({
        "min_ts": datetime.fromtimestamp(float(r["min_ts"])).isoformat(),
        "max_ts": datetime.fromtimestamp(float(r["max_ts"])).isoformat(),
    })


@app.route('/viewer')
def viewer():
    db = get_meta_db()

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
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        db = get_meta_db()
        row = db.execute(
            "SELECT password_hash FROM admin_users WHERE username=?",
            (username,),
        ).fetchone()

        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["is_admin"] = True
            session["admin_user"] = username
            return redirect("/")

        return render_template("admin_login.html", error="Invalid username or password")

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
    db = get_meta_db()
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

    db = get_meta_db()
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
    db = get_meta_db()
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

    db = get_meta_db()
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
        enforce_retention_for_topic(top_level)
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
    db = get_meta_db()
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

    db = get_meta_db()
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

@app.get("/api/admin/whoami")
def api_admin_whoami():
    return jsonify({
        "is_admin": bool(session.get("is_admin")),
        "admin_user": session.get("admin_user"),
    })

def main():
    # --- Startup / environment verification ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # Reduce logging noise from Flask and SocketIO
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)

    logging.info("MQTTPlot starting — version %s", __version__)
    logging.info("Python executable: %s", sys.executable)
    logging.info("Python prefix: %s", sys.prefix)
    logging.info("Working directory: %s", os.getcwd())

    # Optional hard guard to prevent wrong interpreter usage (cross-platform)
    expected_venv_prefix = os.environ.get("MQTTPLOT_VENV_PREFIX")

    if expected_venv_prefix:
        exe = os.path.normcase(os.path.abspath(sys.executable))
        expected = os.path.normcase(os.path.abspath(expected_venv_prefix))

        if not exe.startswith(expected):
            logging.critical(
                "NOT running inside expected virtualenv — aborting. exe=%s expected_prefix=%s",
                sys.executable, expected_venv_prefix
            )
            sys.exit(1)
    else:
        logging.info("MQTTPLOT_VENV_PREFIX not set — skipping interpreter guard")

    # --- Initialize metadata DB first ---
    init_meta_db()
    record_app_version(__version__)
    init_admin_user()

    # --- Start MQTT ingest thread (ONLY here) ---
    if getattr(config, "MQTT_ENABLED", True):
        start_mqtt_worker()
    else:
        logging.info("MQTT_ENABLED=0 — MQTT ingest disabled")

    # --- Start web server ---
    socketio.run(app, host="0.0.0.0", port=config.FLASK_PORT)

if __name__ == '__main__':
    main()
