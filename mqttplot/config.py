"""Configuration and defaults for MQTTPlot."""
from __future__ import annotations

import os

# Primary (legacy) metadata DB (admin users, rules, app version, etc.)
DB_PATH: str = os.environ.get("DB_PATH", "/opt/mqttplot/mqtt_data.db")

# Directory containing per-top-level-topic SQLite databases.
DATA_DB_DIR: str = os.environ.get("DATA_DB_DIR", "/opt/mqttplot/data")

# MQTT connection settings
MQTT_BROKER: str = os.environ.get("MQTT_BROKER", "192.168.12.50")
MQTT_PORT: int = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPICS: str = os.environ.get("MQTT_TOPICS", "#")
MQTT_USERNAME: str | None = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD: str | None = os.environ.get("MQTT_PASSWORD")

# Flask settings
FLASK_PORT: int = int(os.environ.get("FLASK_PORT", "5000"))
SECRET_KEY: str | None = os.environ.get("SECRET_KEY")

# Plot defaults (mutable at runtime via API)
PLOT_CONFIG = {
    "default_window_minutes": 60,
    "max_points": 10000,
    "update_interval_ms": 2000,
}

MQTT_RETRY_BASE_SECONDS = float(os.getenv("MQTT_RETRY_BASE_SECONDS", "2"))
MQTT_RETRY_MAX_SECONDS  = float(os.getenv("MQTT_RETRY_MAX_SECONDS", "60"))
MQTT_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MQTT_CONNECT_TIMEOUT_SECONDS", "5"))
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "1") not in ("0", "false", "False", "no", "NO")

