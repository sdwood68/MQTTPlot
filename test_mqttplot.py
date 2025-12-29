#!/usr/bin/env python3
import os
import sqlite3
import importlib.util
import time
import json
import requests
import paho.mqtt.client as mqtt
import sys

INSTALL_DIR = "/opt/mqttplot"
DB_PATH = os.path.join(INSTALL_DIR, "mqtt_data.db")
SECRET_FILE = os.path.join(INSTALL_DIR, "secret.env")

TEST_TOPIC = "watergauge/test"
TEST_VALUE = 123.456

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

# ------------------ SAFETY CHECK ------------------
if "#" in TEST_TOPIC or "+" in TEST_TOPIC or not TEST_TOPIC.endswith("/test"):
    print("❌ Refusing to run with unsafe TEST_TOPIC:", TEST_TOPIC)
    sys.exit(1)

# ------------------ READ MQTT CREDENTIALS ------------------
mqtt_username = mqtt_password = None
with open(SECRET_FILE) as f:
    for line in f:
        if line.startswith("MQTT_USERNAME="):
            mqtt_username = line.strip().split("=", 1)[1]
        elif line.startswith("MQTT_PASSWORD="):
            mqtt_password = line.strip().split("=", 1)[1]

# ------------------ CHECK PYTHON PACKAGES ------------------
def check_packages(pkgs):
    missing = []
    for pkg in pkgs:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing

required_pkgs = [
    "flask",
    "flask_socketio",
    "plotly",
    "paho.mqtt",
    "eventlet",
    "waitress",
    "requests",
]

missing = check_packages(required_pkgs)
if missing:
    print("❌ Missing Python packages:", missing)
    sys.exit(1)
else:
    print("✅ All required Python packages are installed.")

# ------------------ DATABASE CHECK ------------------
if not os.path.exists(DB_PATH):
    print(f"❌ Database file not found: {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("✅ Database tables:", tables)

# ------------------ CLEAN OLD TEST DATA (SAFE) ------------------
cur.execute(
    "SELECT COUNT(*) FROM messages WHERE topic = ?",
    (TEST_TOPIC,),
)
before = cur.fetchone()[0]

print(f"🧹 Found {before} old test rows for topic '{TEST_TOPIC}'")

cur.execute(
    "DELETE FROM messages WHERE topic = ?",
    (TEST_TOPIC,),
)
conn.commit()

cur.execute(
    "SELECT COUNT(*) FROM messages WHERE topic = ?",
    (TEST_TOPIC,),
)
after = cur.fetchone()[0]

print(f"🧹 Removed {before - after} test rows; remaining test rows: {after}")

# Sanity check: prove other topics still exist (if any)
cur.execute(
    "SELECT DISTINCT topic FROM messages WHERE topic != ? LIMIT 5",
    (TEST_TOPIC,),
)
other_topics = [r[0] for r in cur.fetchall()]
if other_topics:
    print("📊 Sample preserved topics:", other_topics)
else:
    print("ℹ No other topics found (database may be empty).")

conn.close()

# ------------------ MQTT PUBLISH TEST ------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT broker connection successful")
    else:
        print("❌ MQTT connection failed rc=", rc)

client = mqtt.Client()
client.on_connect = on_connect

if mqtt_username:
    client.username_pw_set(mqtt_username, mqtt_password)

print("📡 Publishing test MQTT message...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

payload = json.dumps({"value": TEST_VALUE})
client.publish(TEST_TOPIC, payload)

time.sleep(2)
client.loop_stop()
client.disconnect()

# ------------------ WAIT FOR DB INSERT ------------------
print("⏳ Waiting for message to be stored in database...")
found = False

for _ in range(10):
    time.sleep(1)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT topic, value
        FROM messages
        WHERE topic = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (TEST_TOPIC,),
    )
    row = cur.fetchone()
    conn.close()

    if row and row[1] is not None and abs(row[1] - TEST_VALUE) < 0.0001:
        found = True
        break

if found:
    print("✅ Test message successfully stored in database!")
else:
    print("❌ Test message NOT found in database. Check MQTTPlot service logs.")

# ------------------ FLASK API TEST ------------------
try:
    url = f"http://localhost:{FLASK_PORT}/api/topics"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        print("✅ Flask API /api/topics OK. Topics:", resp.json())
    else:
        print("❌ Flask API returned status", resp.status_code)
except Exception as e:
    print("❌ Flask API test failed:", e)

print("=== MQTTPlot end-to-end test complete ===")
