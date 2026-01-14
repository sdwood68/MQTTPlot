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

        # timeout + WAL reduces locking problems between Flask and ingest thread
        self._con = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=True)
        self._con.row_factory = sqlite3.Row

        try:
            self._con.execute("PRAGMA journal_mode=WAL;")
            self._con.execute("PRAGMA synchronous=NORMAL;")
            self._con.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass

        # cache for policies (future-proof)
        self._policy_cache: dict[str, dict] = {}
        self._policy_cache_ts: float = 0.0
        self._policy_cache_ttl: float = 2.0  # seconds


    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass

    def record_seen(self, topic: str, ts_epoch: float) -> None:
        cur = self._con.cursor()

        cur.execute(
            """
            INSERT INTO topic_stats(topic, message_count, first_seen_ts_epoch, last_seen_ts_epoch)
            VALUES(?, 0, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                first_seen_ts_epoch = MIN(topic_stats.first_seen_ts_epoch, excluded.first_seen_ts_epoch),
                last_seen_ts_epoch  = MAX(topic_stats.last_seen_ts_epoch,  excluded.last_seen_ts_epoch)
            """,
            (topic, float(ts_epoch), float(ts_epoch)),
        )

        cur.execute(
            """
            INSERT INTO topic_meta(topic, public)
            VALUES(?, 1)
            ON CONFLICT(topic) DO NOTHING
            """,
            (topic,),
        )

        self._commit_with_retry()

    def increment_counts(self, topic: str, ts_epoch: float, stored: bool) -> None:
        cur = self._con.cursor()

        cur.execute(
            """
            INSERT INTO topic_stats(topic, message_count, first_seen_ts_epoch, last_seen_ts_epoch)
            VALUES(?, 1, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                message_count = topic_stats.message_count + 1,
                last_seen_ts_epoch = MAX(topic_stats.last_seen_ts_epoch, excluded.last_seen_ts_epoch)
            """,
            (topic, float(ts_epoch), float(ts_epoch)),
        )

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


    def get_topic_policy(self, topic: str) -> Optional[dict]:
        """
        Future-proof policy lookup.
        For now, this returns {'store_enabled': bool} if column exists,
        otherwise None (meaning default allow store).
        """
        now = time.time()
        if (now - self._policy_cache_ts) > self._policy_cache_ttl:
            self._policy_cache.clear()
            self._policy_cache_ts = now

        if topic in self._policy_cache:
            return self._policy_cache[topic]

        cur = self._con.cursor()

        # Default allow store. If schema does not include store_enabled yet,
        # we treat it as not configured.
        try:
            row = cur.execute(
                "SELECT store_enabled FROM topic_meta WHERE topic=?",
                (topic,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None

        if row is None:
            return None

        pol = {"store_enabled": bool(row["store_enabled"]) if row["store_enabled"] is not None else True}
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
