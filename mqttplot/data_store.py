# mqttplot/data_store.py
from __future__ import annotations

import os
import sqlite3
import logging
from typing import Dict

from . import config
from .storage import topic_db_path, init_topic_db

logger = logging.getLogger(__name__)


class DataStore:
    """
    Thread-owned per-top-level data DB access. Do NOT use flask.g here.
    """

    def __init__(self):
        self._cache: Dict[str, sqlite3.Connection] = {}

    def close(self) -> None:
        for con in self._cache.values():
            try:
                con.close()
            except Exception:
                pass
        self._cache.clear()

    def _get_conn(self, topic: str) -> sqlite3.Connection:
        db_path = topic_db_path(topic)

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        if not os.path.exists(db_path):
            init_topic_db(db_path)

        con = self._cache.get(db_path)
        if con is None:
            con = sqlite3.connect(db_path, check_same_thread=True)
            con.row_factory = sqlite3.Row
            self._cache[db_path] = con
        return con

    def store_timeseries(self, topic: str, ts_epoch: float, value: float) -> None:
        con = self._get_conn(topic)
        cur = con.cursor()

        # Ensure topic_id exists in this per-top-level DB
        cur.execute("INSERT OR IGNORE INTO topics(topic) VALUES(?)", (topic,))
        row = cur.execute("SELECT id FROM topics WHERE topic=?", (topic,)).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to resolve topic_id for topic={topic}")
        tid = int(row[0])

        cur.execute(
            "INSERT INTO messages(topic_id, ts_epoch, value) VALUES(?,?,?)",
            (tid, float(ts_epoch), float(value)),
        )
        con.commit()
