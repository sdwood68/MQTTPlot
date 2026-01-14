"""MQTT client worker.

Refactor note: extracted from legacy root app.py as part of 0.6.2 code reorganization.
"""
from __future__ import annotations

import sys, time, random
from datetime import datetime, timezone
import logging
import time
import threading
from typing import Optional
from dataclasses import dataclass
import paho.mqtt.client as mqtt

from . import config
from .storage import store_topic_msg

logger = logging.getLogger(__name__)

@dataclass
class MqttStatus:
    connected: bool = False
    last_error: str | None = None
    last_attempt_ts: float | None = None
    next_retry_ts: float | None = None
    retry_count: int = 0

STATUS = MqttStatus()
STATUS_LOCK = threading.Lock()

def get_status() -> dict:
    with STATUS_LOCK:
        s = STATUS
        return {
            "connected": s.connected,
            "last_error": s.last_error,
            "retry_count": s.retry_count,
            "last_attempt_iso": (
                datetime.fromtimestamp(s.last_attempt_ts, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                if s.last_attempt_ts else None
            ),
            "next_retry_iso": (
                datetime.fromtimestamp(s.next_retry_ts, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                if s.next_retry_ts else None
            ),
            # "last_attempt_iso": datetime.fromtimestamp(s.last_attempt_ts).isoformat() if s.last_attempt_ts else None,
            # "next_retry_iso": datetime.fromtimestamp(s.next_retry_ts).isoformat() if s.next_retry_ts else None,
        }

def mqtt_worker(app, socketio, stop_event):
    # backoff parameters (tweak as desired)
    base_delay = float(getattr(config, "MQTT_RETRY_BASE_SECONDS", 2.0))
    max_delay  = float(getattr(config, "MQTT_RETRY_MAX_SECONDS", 60.0))

    # Use explicit callback API version for stability across paho-mqtt versions
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    # Optional: if you use username/password
    if getattr(config, "MQTT_USERNAME", None):
        client.username_pw_set(config.MQTT_USERNAME, getattr(config, "MQTT_PASSWORD", None))

    # Instantiate ingestion services ONCE per worker thread (thread-owned connections)
    from .metadata_store import MetadataStore
    from .data_store import DataStore
    from .ingest import IngestService

    meta = MetadataStore(config.DB_PATH)
    data = DataStore()
    ingest = IngestService(meta, data)

    def on_connect(c, userdata, flags, rc, properties=None):
        ok = (rc == 0)

        with STATUS_LOCK:
            STATUS.connected = ok

            if ok:
                STATUS.last_error = None
                STATUS.retry_count = 0
                STATUS.next_retry_ts = None
                STATUS.last_attempt_ts = time.time()
            else:
                STATUS.last_error = f"connect rc={rc}"

        if ok:
            logger.info("MQTT subscribing to %s", config.MQTT_TOPICS)
            c.subscribe(config.MQTT_TOPICS)

            try:
                socketio.emit("mqtt_status", get_status())
            except Exception:
                pass
        else:
            logger.warning("MQTT connect failed (rc=%s)", rc)

    def on_disconnect(c, userdata, rc, properties=None):
        with STATUS_LOCK:
            STATUS.connected = False
            if rc != 0:
                STATUS.last_error = f"unexpected disconnect rc={rc}"
        logger.warning("MQTT disconnected (rc=%s)", rc)
        try:
            socketio.emit("mqtt_status", get_status())
        except Exception:
            pass

    def _on_message(c, userdata, msg):
        logger.info("MQTT RX %s %r", msg.topic, msg.payload)
        try:
            # App context is fine for logging/config; ingestion itself is thread-owned
            with app.app_context():
                ingest.ingest(msg.topic, msg.payload, ts_epoch=time.time())
        except Exception:
            logger.exception("Failed ingesting message for topic %s", msg.topic)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = _on_message

    client.reconnect_delay_set(min_delay=1, max_delay=int(max_delay))

    delay = base_delay

    while not stop_event.is_set():
        with STATUS_LOCK:
            connected = STATUS.connected

        if not connected:
            now = time.time()
            with STATUS_LOCK:
                STATUS.last_attempt_ts = now

            try:
                logger.info("MQTT attempting connect to %s:%s", config.MQTT_BROKER, config.MQTT_PORT)

                client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)

                # Pump loop so on_connect fires
                client.loop(timeout=1.0)

                with STATUS_LOCK:
                    if STATUS.connected:
                        delay = base_delay
                        STATUS.retry_count = 0
                        STATUS.next_retry_ts = None

            except (TimeoutError, OSError) as e:
                with STATUS_LOCK:
                    STATUS.connected = False
                    STATUS.last_error = str(e)
                    STATUS.retry_count += 1
                    jitter = random.uniform(0, 0.25 * delay)
                    STATUS.next_retry_ts = time.time() + delay + jitter

                logger.warning("MQTT connect failed: %s (retry in ~%.1fs)", e, delay)
                try:
                    socketio.emit("mqtt_status", get_status())
                except Exception:
                    pass

                stop_event.wait(delay)
                delay = min(max_delay, delay * 2)
                continue

            except Exception as e:
                with STATUS_LOCK:
                    STATUS.connected = False
                    STATUS.last_error = f"{type(e).__name__}: {e}"
                    STATUS.retry_count += 1
                    STATUS.next_retry_ts = time.time() + delay

                logger.exception("MQTT unexpected error (will retry in ~%.1fs)", delay)
                try:
                    socketio.emit("mqtt_status", get_status())
                except Exception:
                    pass

                stop_event.wait(delay)
                delay = min(max_delay, delay * 2)
                continue

        try:
            client.loop(timeout=1.0)
        except Exception as e:
            with STATUS_LOCK:
                STATUS.connected = False
                STATUS.last_error = f"loop error: {type(e).__name__}: {e}"
            logger.warning("MQTT loop error: %s", e)

        stop_event.wait(0.2)

    # shutdown
    try:
        client.disconnect()
    except Exception:
        pass

    # Close thread-owned DB connections cleanly
    try:
        meta.close()
    except Exception:
        pass
    try:
        data.close()
    except Exception:
        pass
