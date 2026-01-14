# mqttplot/metadata_store.py
from __future__ import annotations

import sqlite3
import time
import json
import logging
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class MetadataStore:
    """
    Thread-owned metadata DB access. Do NOT use flask.g here.
    This supports topic discovery, UI controls, and future rate limiting flags.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DB_PATH

        self._con = sqlite3.connect(
            self.db_path,
            timeout=10.0,
            check_same_thread=False,
        )
        self._con.row_factory = sqlite3.Row

        cur = self._con.cursor()
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA wal_autocheckpoint=1000")
        self._con.commit()

        # Ensure required columns exist for your planned architecture
        self._ensure_meta_schema()

        # policy cache
        self._policy_cache: dict[str, dict] = {}
        self._policy_cache_ts: float = 0.0
        self._policy_cache_ttl: float = 2.0  # seconds

    def _ensure_meta_schema(self) -> None:
        """
        Ensure metadata tables have the columns needed for:
        - epoch timestamps
        - stored/dropped counters
        - per-topic storage policy scaffolding
        Safe to run on startup.
        """
        cur = self._con.cursor()

        # topic_meta policy columns
        cols = {r["name"] for r in cur.execute("PRAGMA table_info(topic_meta)").fetchall()}
        if "store_enabled" not in cols:
            cur.execute("ALTER TABLE topic_meta ADD COLUMN store_enabled INTEGER NOT NULL DEFAULT 1")
        if "max_msgs_per_min" not in cols:
            cur.execute("ALTER TABLE topic_meta ADD COLUMN max_msgs_per_min INTEGER")
        if "auto_disabled" not in cols:
            cur.execute("ALTER TABLE topic_meta ADD COLUMN auto_disabled INTEGER NOT NULL DEFAULT 0")
        if "enabled" not in cols:
            cur.execute("ALTER TABLE topic_meta ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")

        # topic_stats counters
        cols = {r["name"] for r in cur.execute("PRAGMA table_info(topic_stats)").fetchall()}
        if "stored_count" not in cols:
            cur.execute("ALTER TABLE topic_stats ADD COLUMN stored_count INTEGER NOT NULL DEFAULT 0")
        if "dropped_count" not in cols:
            cur.execute("ALTER TABLE topic_stats ADD COLUMN dropped_count INTEGER NOT NULL DEFAULT 0")

        self._con.commit()


    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass


    def meta_observe_message(
        self,
        topic: str,
        ts_epoch: float,
        *,
        stored: bool,
        last_value: float | None = None,
        last_payload_text: str | None = None,
    ) -> None:
        """
        Atomically update metadata for one observed MQTT message.

        Effects (single transaction):
        - Ensures topic_meta row exists (default public=1)
        - Upserts topic_stats:
            * first_seen_ts_epoch (set once)
            * last_seen_ts_epoch (always moves forward)
            * message_count (+1)
            * last_value (optional; only if numeric provided)
        - Optional counters:
            * stored_count (+1) if stored=True
            * dropped_count (+1) if stored=False
            (only applied if those columns exist)
        """
        cur = self._con.cursor()

        # Ensure topic_meta exists (public defaults to 1)
        cur.execute(
            """
            INSERT INTO topic_meta(topic, public)
            VALUES(?, 1)
            ON CONFLICT(topic) DO NOTHING
            """,
            (topic,),
        )

        # Base upsert for stats: first_seen set once, last_seen always updated, count increments
        # last_value is only set if provided (numeric); otherwise keep prior.
        cur.execute(
            """
            INSERT INTO topic_stats(
                topic,
                message_count,
                first_seen_ts_epoch,
                last_seen_ts_epoch,
                last_value
            )
            VALUES(?, 1, ?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                message_count = topic_stats.message_count + 1,
                first_seen_ts_epoch = COALESCE(topic_stats.first_seen_ts_epoch, excluded.first_seen_ts_epoch),
                last_seen_ts_epoch  = CASE
                    WHEN topic_stats.last_seen_ts_epoch IS NULL THEN excluded.last_seen_ts_epoch
                    WHEN excluded.last_seen_ts_epoch > topic_stats.last_seen_ts_epoch THEN excluded.last_seen_ts_epoch
                    ELSE topic_stats.last_seen_ts_epoch
                END,
                last_value = CASE
                    WHEN excluded.last_value IS NOT NULL THEN excluded.last_value
                    ELSE topic_stats.last_value
                END
            """,
            (topic, float(ts_epoch), float(ts_epoch), last_value),
        )

        # Optional counters (only if columns exist)
        try:
            if stored:
                cur.execute(
                    "UPDATE topic_stats SET stored_count = COALESCE(stored_count, 0) + 1 WHERE topic=?",
                    (topic,),
                )
            else:
                cur.execute(
                    "UPDATE topic_stats SET dropped_count = COALESCE(dropped_count, 0) + 1 WHERE topic=?",
                    (topic,),
                )
        except sqlite3.OperationalError:
            pass

        self._commit_with_retry()
    

    def get_topic_policy(self, topic: str) -> dict:
        """
        Policy lookup with safe defaults.
        Returned dict always contains:
        - store_enabled: bool
        - max_msgs_per_min: int|None
        - auto_disabled: bool
        """
        now = time.time()
        if (now - self._policy_cache_ts) > self._policy_cache_ttl:
            self._policy_cache.clear()
            self._policy_cache_ts = now

        if topic in self._policy_cache:
            return self._policy_cache[topic]

        cur = self._con.cursor()

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
            pol = {"store_enabled": True, "max_msgs_per_min": None, "auto_disabled": False}
            self._policy_cache[topic] = pol
            return pol

        if row is None:
            pol = {"store_enabled": True, "max_msgs_per_min": None, "auto_disabled": False}
            self._policy_cache[topic] = pol
            return pol

        pol = {
            "store_enabled": bool(row["store_enabled"]) if row["store_enabled"] is not None else True,
            "max_msgs_per_min": row["max_msgs_per_min"],
            "auto_disabled": bool(row["auto_disabled"]) if row["auto_disabled"] is not None else False,
        }
        self._policy_cache[topic] = pol
        return pol


    def _commit_with_retry(self, attempts: int = 5, base_sleep: float = 0.05) -> None:
        """
        SQLite can briefly lock under concurrent access. WAL + busy_timeout helps,
        but add a small retry to eliminate spurious failures.
        """
        import time as _time

        last_err = None
        for i in range(attempts):
            try:
                self._con.commit()
                return
            except sqlite3.OperationalError as e:
                last_err = e
                msg = str(e).lower()
                if "locked" not in msg:
                    raise
                _time.sleep(base_sleep * (i + 1))
        raise last_err
