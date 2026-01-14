# mqttplot/ingest.py
from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .storage import parse_topic_value
from .metadata_store import MetadataStore
from .data_store import DataStore

logger = logging.getLogger(__name__)


class StoreDecision(str, Enum):
    STORE = "store"          # store timeseries and update metadata
    DROP_STORE = "drop_store"  # update metadata only (topic disabled/rate too high)
    DROP_ALL = "drop_all"    # drop everything (rare; usually keep metadata)


@dataclass
class IngestResult:
    decision: StoreDecision
    reason: str | None = None
    value: float | None = None


class PolicyEngine:
    """
    Scaffolding only: supports future UI disable + rate limiting.
    For now, it only enforces the UI 'store_enabled' flag if present.
    """

    def __init__(self, meta: MetadataStore):
        self.meta = meta
        # Future: in-memory rate limiter state (token buckets / sliding windows)

    def decide(self, topic: str, ts_epoch: float) -> tuple[StoreDecision, str | None]:
        # UI-controlled storage enable/disable (future-proof)
        pol = self.meta.get_topic_policy(topic)  # cheap cached lookup
        if pol is not None:
            if pol.get("store_enabled") is False:
                return (StoreDecision.DROP_STORE, "disabled_by_ui")

        # Future: rate checks here. Example decisions:
        # - DROP_STORE with reason "rate_limit"
        # - optionally set auto_disabled in metadata

        return (StoreDecision.STORE, None)


class IngestService:
    """
    Single entry point for MQTT ingestion.
    - Always updates telemetry in metadata DB (topic seen, counts)
    - Conditionally stores time-series based on policy decisions
    """

    def __init__(self, meta: MetadataStore, data: DataStore):
        self.meta = meta
        self.data = data
        self.policy = PolicyEngine(meta)

    def ingest(self, topic: str, payload: bytes | str | None, ts_epoch: float | None = None) -> IngestResult:
        if ts_epoch is None:
            ts_epoch = time.time()

        # Parse value (float) if possible
        value = parse_topic_value(payload)

        # Decide policy (UI disable / future rate limiting)
        decision, reason = self.policy.decide(topic, ts_epoch)

        stored = False

        # STORE means: store numeric timeseries if possible
        if decision == StoreDecision.STORE and value is not None:
            self.data.store_timeseries(topic, ts_epoch, value)
            stored = True

        # DROP_STORE means: do NOT store timeseries, but still record metadata telemetry
        # DROP_ALL means: drop everything (including metadata)
        if decision != StoreDecision.DROP_ALL:
            self.meta.meta_observe_message(
                topic,
                ts_epoch,
                stored=stored,
                last_value=value if value is not None else None,
            )

        return IngestResult(decision=decision, reason=reason, value=value)
