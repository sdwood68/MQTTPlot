"""SQLite persistence layer for MQTTPlot.

This module contains:
- the *metadata* DB (admin users, validation rules, app version)
- per-top-level-topic *data* DBs (time series values)

Refactor note: extracted from legacy root app.py as part of 0.6.2 code reorganization.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timedelta
import time
from typing import Any, Optional, Tuple
from flask import g
from . import config

logger = logging.getLogger("mqttplot.storage")

# Register adapter and converter for datetime
sqlite3.register_adapter(datetime, lambda val: val.isoformat(sep=" "))
sqlite3.register_converter("TIMESTAMP", lambda val: datetime.fromisoformat(val.decode()))


def get_db() -> sqlite3.Connection:
    """Metadata database connection (Flask context cached)."""
    db = getattr(g, "_database", None)
    logger.debug("Using metadata DB: %s", os.path.abspath(config.DB_PATH))
    if db is None:
        db = g._database = sqlite3.connect(
            config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES
        )
        db.row_factory = sqlite3.Row
    return db


def top_level_topic(topic: str) -> str:
    """Return the top-level portion of a topic.

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
    os.makedirs(config.DATA_DB_DIR, exist_ok=True)
    return os.path.join(config.DATA_DB_DIR, f"{root}.db")


def init_data_db(db_path: str) -> None:
    """
    Compact per-top-level DB schema (v2):
      - topics table stores unique topic strings once
      - messages stores (topic_id, ts_epoch, value)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT UNIQUE NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            ts_epoch REAL NOT NULL,
            value REAL,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_topic_ts ON messages(topic_id, ts_epoch)")
    conn.commit()
    conn.close()


def get_data_db(topic: str) -> sqlite3.Connection:
    """Data database connection for a given topic's top-level namespace."""
    db_path = data_db_path_for_topic(topic)
    if not os.path.exists(db_path):
        init_data_db(db_path)

    # Cache per-request, keyed by db_path, to avoid re-opening within one HTTP request.
    cache = getattr(g, "_data_dbs", None)
    if cache is None:
        cache = g._data_dbs = {}

    conn = cache.get(db_path)
    if conn is None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cache[db_path] = conn
    return conn


def close_db(exc: Exception | None = None) -> None:
    """Close any open DB connections for this Flask request."""
    db = getattr(g, "_database", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

    data_dbs = getattr(g, "_data_dbs", None)
    if data_dbs:
        for conn in data_dbs.values():
            try:
                conn.close()
            except Exception:
                pass


def init_db() -> None:
    """Initialize metadata DB schema."""
    logging.getLogger(__name__).info("Using metadata DB: %s", os.path.abspath(config.DB_PATH))
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS validation_rules (
            topic TEXT PRIMARY KEY,
            rule_json TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS retention_policies (
            top_level TEXT PRIMARY KEY,
            days INTEGER NOT NULL
        )
        """
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topic_stats (
            topic TEXT PRIMARY KEY,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            message_count INTEGER NOT NULL DEFAULT 0,
            last_value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topic_meta (
            topic TEXT PRIMARY KEY,
            public INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


def record_app_version(version: str) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)",
        ("app_version", version),
    )
    conn.commit()
    conn.close()


def init_admin_user() -> None:
    """Initialize the default admin user if ADMIN_INIT_PASSWORD is set.

    Behavior:
      - If env var ADMIN_INIT_PASSWORD is NOT set: do nothing.
      - If set and no 'admin' user exists: create user 'admin' with that password.
      - If set and 'admin' exists: do nothing.
    """
    import os
    from werkzeug.security import generate_password_hash

    init_pw = os.environ.get("ADMIN_INIT_PASSWORD")
    if not init_pw:
        return

    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()

    # Ensure schema exists (safe if already called elsewhere)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("SELECT 1 FROM admin_users WHERE username = ?", ("admin",))
    exists = cur.fetchone() is not None

    if not exists:
        pw_hash = generate_password_hash(init_pw)
        cur.execute(
            "INSERT INTO admin_users(username, password_hash) VALUES(?, ?)",
            ("admin", pw_hash),
        )
        conn.commit()

    conn.close()


def get_validation_rule(topic: str) -> Optional[dict]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        "SELECT rule_json FROM validation_rules WHERE topic = ?", (topic,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        import json
        return json.loads(row["rule_json"])
    except Exception:
        return None


def get_retention_policy(top_level: str) -> Optional[int]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        "SELECT days FROM retention_policies WHERE top_level = ?", (top_level,)
    ).fetchone()
    conn.close()
    return int(row["days"]) if row else None


def parse_value(payload_text) -> Optional[float]:
    """Parse a payload into a float, if feasible."""
    if payload_text is None:
        return None
    if isinstance(payload_text, (bytes, bytearray)):
        try:
            payload_text = payload_text.decode('utf-8', errors='ignore')
        except Exception:
            payload_text = payload_text.decode(errors='ignore')
    s = str(payload_text).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        # JSON payloads: try to parse {"value": ...} or similar
        try:
            import json
            obj = json.loads(s)
            if isinstance(obj, dict):
                for k in ("value", "val", "v"):
                    if k in obj:
                        return float(obj[k])
            return None
        except Exception:
            return None


def _topic_id(conn: sqlite3.Connection, topic: str) -> int:
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO topics(topic) VALUES(?)", (topic,))
    conn.commit()
    row = cur.execute("SELECT id FROM topics WHERE topic = ?", (topic,)).fetchone()
    return int(row[0])


def store_message(topic: str, payload: str) -> None:
    """Store an incoming MQTT message."""
    rule = get_validation_rule(topic)
    value = parse_value(payload)

    # If a validation rule exists, enforce it for numeric values.
    if rule and value is not None:
        try:
            mn = rule.get("min")
            mx = rule.get("max")
            if mn is not None and value < float(mn):
                logging.warning("Value below min for %s: %s < %s", topic, value, mn)
                return
            if mx is not None and value > float(mx):
                logging.warning("Value above max for %s: %s > %s", topic, value, mx)
                return
        except Exception:
            # rule malformed; do not block ingestion
            pass

    conn = get_data_db(topic)
    tid = _topic_id(conn, topic)
    ts = time.time()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages(topic_id, ts_epoch, value) VALUES(?,?,?)",
        (tid, ts, value),
    )
    conn.commit()

    # Apply retention for this namespace if configured.
    days = get_retention_policy(top_level_topic(topic))
    if days:
        cutoff = ts - (days * 86400.0)
        cur.execute(
            "DELETE FROM messages WHERE topic_id = ? AND ts_epoch < ?",
            (tid, cutoff),
        )
        conn.commit()


def enforce_retention_for_top_level(top_level: str) -> int:
    """Delete old rows for a top-level topic DB per retention policy.
    Returns number of rows deleted.
    """
    policy_days = get_retention_policy(top_level)
    if not policy_days or policy_days <= 0:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=policy_days)
    conn = get_data_db(top_level)
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE ts < ?", (cutoff.timestamp(),))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
