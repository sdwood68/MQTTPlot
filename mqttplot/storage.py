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
from datetime import datetime
import time
from typing import Optional
from flask import g
from . import config

logger = logging.getLogger("mqttplot.storage")

def _convert_timestamp(val: bytes) -> datetime:
    """
    SQLite TIMESTAMP converter that supports both:
      - ISO strings (e.g., '2026-01-11 17:28:05')
      - epoch seconds stored as text/float (e.g., '1768170485.26089')
    """
    s = val.decode(errors="ignore").strip()
    if not s:
        # fallback; should not happen for non-null TIMESTAMP
        return datetime.fromtimestamp(0)

    # First try ISO
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass

    # Then try epoch seconds
    try:
        return datetime.fromtimestamp(float(s))
    except Exception:
        # last resort: raise a clear error
        raise ValueError(f"Invalid TIMESTAMP value in DB: {s!r}")


def get_meta_db() -> sqlite3.Connection:
    """Metadata database connection (Flask context cached)."""
    db = getattr(g, "_database", None)
    logger.debug("Using metadata DB: %s", os.path.abspath(config.DB_PATH))
    if db is None:
        db = g._database = sqlite3.connect(config.DB_PATH, timeout=10.0)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL;")
            db.execute("PRAGMA synchronous=NORMAL;")
            db.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
    return db


def topic_root(topic: str) -> str:
    """
    Return the top-level portion of a topic.
    Examples:
      "/watergauge/temp" -> "watergauge"
      "watergauge/temp"  -> "watergauge"
      "/" or ""          -> "_root"
    
    :param topic: Full MQTT topic string
    :type topic: str
    :return: Top-level topic string
    :rtype: str
    """
    if not topic:
        return "_root"
    t = topic.strip()
    if t.startswith("/"):
        t = t[1:]
    if not t:
        return "_root"
    return t.split("/", 1)[0] or "_root"

def topic_db_path(topic: str) -> str:
    """
    Map a full topic string to the per-top-level DB file path.
    Example: 'watergauge/other/temp' -> '<DATA_DB_DIR>/watergauge.db'

    You asked to store as: .\\data\\<topic_root>.db
    Ensure config.DATA_DB_DIR is set to '.\\data'.

    :param topic: Full MQTT topic string
    :type topic: str
    :return: Filesystem path to the per-top-level topic DB
    :rtype: str
    """
    root = topic_root(topic)
    os.makedirs(config.DATA_DB_DIR, exist_ok=True)
    return os.path.join(config.DATA_DB_DIR, f"{root}.db")

def init_topic_db(db_path: str) -> None:
    """
    Compact per-top-level DB schema initialization.
    Schema:
      - topics table stores unique topic strings once
      - messages stores (topic_id, ts_epoch, value)
    
    :param db_path: Filesystem path to the per-top-level topic DB
    :type db_path: str
    :return: None
    :rtype: None
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
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_topic_ts 
        ON messages(topic_id, ts_epoch);
        """)
    conn.commit()
    conn.close()


def get_data_db(topic: str) -> sqlite3.Connection:
    """Data database connection for a given topic's top-level namespace."""
    db_path = topic_db_path(topic)
    logger.info("DATA DB path for topic %s => %s", topic, db_path)

    if not os.path.exists(db_path):
        init_topic_db(db_path)

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


def close_meta_db(exc: Exception | None = None) -> None:
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

def init_meta_db() -> None:
    """
    Initialize metadata DB.
    Creates tables if they do not already exist.
    """
    logging.getLogger(__name__).info("Using metadata DB: %s", os.path.abspath(config.DB_PATH))
    conn = sqlite3.connect(config.DB_PATH, timeout=10.0)
    cur = conn.cursor()

    # Better concurrency between Flask and ingest thread
    try:
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass

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
            created_ts_epoch REAL DEFAULT (strftime('%s','now'))
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

    # Epoch seconds are smaller and faster to compare
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topic_stats (
            topic TEXT PRIMARY KEY,
            first_seen_ts_epoch REAL,
            last_seen_ts_epoch REAL,
            message_count INTEGER NOT NULL DEFAULT 0,
            last_value TEXT,

            -- Optional future-proof counters
            stored_count INTEGER,
            dropped_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topic_meta (
            topic TEXT PRIMARY KEY,
            public INTEGER NOT NULL DEFAULT 1,

            -- Future-proof policy controls (optional)
            store_enabled INTEGER NOT NULL DEFAULT 1,
            max_msgs_per_min REAL,
            auto_disabled INTEGER NOT NULL DEFAULT 0,
            disabled_reason TEXT,
            updated_ts_epoch REAL
        )
    """)

    conn.commit()
    conn.close()

def record_app_version(version: str) -> None:
    """
    Record the current application version in the metadata DB.
    Metadata DB must already exist.
    """
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO app_meta(key,value) VALUES(?,?)",
        ("app_version", version),
    )
    conn.commit()
    conn.close()


def init_admin_user() -> None:
    """
    Initialize the default admin user if ADMIN_INIT_PASSWORD is set.
    Metadata DB must already exist.
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
    """
    Fetch the validation rule JSON for a given topic, if any.
    Metadata DB must already exist.
    Returns None if no rule exists or on error.
    """
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
    """
    Retrieve the retention policy (in days) for a given top-level topic.
    Stored in the metadata DB.
    
    Docstring for get_retention_policy
    
    :param top_level: Description
    :type top_level: str
    :return: Description
    :rtype: int | None
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        "SELECT days FROM retention_policies WHERE top_level = ?", (top_level,)
    ).fetchone()
    conn.close()
    return int(row["days"]) if row else None


def parse_topic_value(payload_text) -> Optional[float]:
    """
    Parse a payload into a float, if feasible.
    
    :param payload_text: Raw payload (bytes or str)
    :type payload_text: str
    :return: Parsed float value, or None if not parseable
    :rtype: float | None"""
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


def get_topic_id(conn: sqlite3.Connection, topic: str) -> int:
    """
    Retrieve or create the topic ID for a given topic string

    Docstring for get_topic_id
    
    :param conn: Description
    :type conn: sqlite3.Connection
    :param topic: Description
    :type topic: str
    :return: Description
    :rtype: int
    """
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO topics(topic) VALUES(?)", (topic,))
    conn.commit()
    row = cur.execute("SELECT id FROM topics WHERE topic = ?", (topic,)).fetchone()
    return int(row[0])

def store_topic_msg(topic: str, payload: str) -> None:
    """
    Store an incoming MQTT message.

    Architecture:
      - Always updates metadata telemetry (topic_stats/topic_meta)
      - Conditionally stores time-series based on topic_meta.store_enabled
      - Provides a single decision point to later add rate limiting suppression

    Note: Full rate limiting is not implemented here yet; only scaffolding.

    :param topic: Full MQTT topic string
    :type topic: str
    :param payload: Raw payload (bytes or str)
    :type payload: str
    :return: None
    :rtype: None
    """
    ts = time.time()
    value = parse_topic_value(payload)

    # Always update metadata telemetry, even if we later drop storage
    value_text = None
    try:
        if isinstance(payload, (bytes, bytearray)):
            value_text = payload.decode("utf-8", errors="ignore")
        else:
            value_text = str(payload)
    except Exception:
        value_text = None

    pol = meta_get_storage_policy(topic)

    # UI / policy-based disable (scaffolding)
    if not pol.get("store_enabled", True):
        meta_touch_topic(topic, ts, value_text, stored=False)
        return

    # Validation rules (optional; applies only if a numeric value exists)
    rule = get_validation_rule(topic)
    if rule and value is not None:
        try:
            mn = rule.get("min")
            mx = rule.get("max")
            if mn is not None and value < float(mn):
                logging.warning("Value below min for %s: %s < %s", topic, value, mn)
                meta_touch_topic(topic, ts, value_text, stored=False)
                return
            if mx is not None and value > float(mx):
                logging.warning("Value above max for %s: %s > %s", topic, value, mx)
                meta_touch_topic(topic, ts, value_text, stored=False)
                return
        except Exception:
            # malformed rule; do not block ingestion
            pass

    # If not numeric, we still count it but do not store timeseries
    if value is None:
        meta_touch_topic(topic, ts, value_text, stored=False)
        return

    # Store timeseries (background-safe)
    data_store_timeseries(topic, ts, value)

    # Metadata telemetry: stored=True
    meta_touch_topic(topic, ts, value_text, stored=True)

    # Retention enforcement (optional)
    days = get_retention_policy(topic_root(topic))
    if days:
        cutoff = ts - (days * 86400.0)
        db_path = topic_db_path(topic)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Resolve topic_id again (cheap, and avoids long-lived connections for now)
        row = cur.execute("SELECT id FROM topics WHERE topic = ?", (topic,)).fetchone()
        if row:
            tid = int(row[0])
            cur.execute(
                "DELETE FROM messages WHERE topic_id = ? AND ts_epoch < ?",
                (tid, cutoff),
            )
            conn.commit()
        conn.close()


def enforce_retention_for_topic(top_level: str) -> int:
    """
    Delete old rows for a top-level topic DB per retention policies stored 
    in the metadata DB.
    Returns number of rows deleted.

    :param top_level: Top-level topic string
    :type top_level: str
    :return: Number of deleted rows
    :rtype: int
    """
    policy_days = get_retention_policy(top_level)
    if not policy_days or policy_days <= 0:
        return 0

    cutoff_epoch = time.time() - (policy_days * 86400.0)

    # We want the DB for this top_level -> use any topic string with that root
    conn = sqlite3.connect(topic_db_path(top_level))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure the per-top-level DB exists
    init_topic_db(topic_db_path(top_level))

    cur.execute("DELETE FROM messages WHERE ts_epoch < ?", (cutoff_epoch,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted

def meta_touch_topic(topic: str, ts_epoch: float, value_text: str | None, stored: bool) -> None:
    """
    Background-safe metadata update for topic listing/telemetry.
    - Always updates first_seen/last_seen and increments message_count
    - Tracks stored vs dropped counts (if columns exist)
    - Ensures topic_meta row exists
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure topic_meta exists (public defaults to 1)
    cur.execute(
        """
        INSERT INTO topic_meta(topic, public)
        VALUES(?, 1)
        ON CONFLICT(topic) DO NOTHING
        """,
        (topic,),
    )

    # Upsert stats row and bump counts
    cur.execute(
        """
        INSERT INTO topic_stats(topic, first_seen, last_seen, message_count, last_value)
        VALUES(?, ?, ?, 1, ?)
        ON CONFLICT(topic) DO UPDATE SET
            first_seen = COALESCE(topic_stats.first_seen, excluded.first_seen),
            last_seen  = excluded.last_seen,
            message_count = topic_stats.message_count + 1,
            last_value = excluded.last_value
        """,
        (topic, datetime.fromtimestamp(ts_epoch), datetime.fromtimestamp(ts_epoch), value_text),
    )

    # Optional counters: stored_count / dropped_count
    try:
        if stored:
            cur.execute(
                "UPDATE topic_stats SET stored_count = COALESCE(stored_count,0) + 1 WHERE topic=?",
                (topic,),
            )
        else:
            cur.execute(
                "UPDATE topic_stats SET dropped_count = COALESCE(dropped_count,0) + 1 WHERE topic=?",
                (topic,),
            )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def meta_get_storage_policy(topic: str) -> dict:
    """
    Background-safe fetch of per-topic storage policy from topic_meta.
    Returns defaults if not present.
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        row = cur.execute(
            """
            SELECT store_enabled, max_msgs_per_min, auto_disabled
            FROM topic_meta
            WHERE topic=?
            """,
            (topic,),
        ).fetchone()
    except sqlite3.OperationalError:
        conn.close()
        return {"store_enabled": True, "max_msgs_per_min": None, "auto_disabled": False}

    conn.close()

    if not row:
        return {"store_enabled": True, "max_msgs_per_min": None, "auto_disabled": False}

    return {
        "store_enabled": bool(row["store_enabled"]),
        "max_msgs_per_min": row["max_msgs_per_min"],
        "auto_disabled": bool(row["auto_disabled"]),
    }

def data_store_timeseries(topic: str, ts_epoch: float, value: float) -> None:
    """
    Background-safe write to the per-top-level data DB, without flask.g.
    """
    db_path = topic_db_path(topic)
    if not os.path.exists(db_path):
        init_topic_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure topic_id exists
    cur.execute("INSERT OR IGNORE INTO topics(topic) VALUES(?)", (topic,))
    row = cur.execute("SELECT id FROM topics WHERE topic = ?", (topic,)).fetchone()
    tid = int(row[0])

    cur.execute(
        "INSERT INTO messages(topic_id, ts_epoch, value) VALUES(?,?,?)",
        (tid, float(ts_epoch), float(value)),
    )
    conn.commit()
    conn.close()

def ensure_topic_db(con: sqlite3.Connection) -> None:
    """
    Ensure per-top-level DB schema matches storage.py init_data_db():
      topics(id, topic)
      messages(id, topic_id, ts_epoch, value)
    """
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            ts_epoch REAL NOT NULL,
            value REAL,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_topic_ts ON messages(topic_id, ts_epoch)")
    con.commit()

