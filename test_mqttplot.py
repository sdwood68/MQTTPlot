#!/usr/bin/env python3
import os
import sqlite3
import importlib.util
import time
import json
import requests
import paho.mqtt.client as mqtt

# --- Configuration ---
INSTALL_DIR = "/opt/mqttplot"
DB_PATH = os.path.join(INSTALL_DIR, "mqtt_data.db")
SECRET_FILE = os.path.join(INSTALL_DIR, "secret.env")

# Read MQTT credentials from secret file
mqtt_username = mqtt_password = None
with open(SECRET_FILE) as f:
    for line in f:
        if line.startswith("MQTT_USERNAME="):
            mqtt_username = line.strip().split("=",1)[1]
        elif line.startswith("MQTT_PASSWORD="):
            mqtt_password = line.strip().split("=",1)[1]

MQTT_BROKER = os.environ.get("MQTT_BROKER","localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPICS = os.environ.get("MQTT_TOPICS", "#")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

# --- Helper functions ---
def check_packages(pkgs):
    missing = []
    for pkg in pkgs:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing

def check_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        return tables
    except Exception as e:
        return str(e)

# --- 1. Check Python packages ---
required_pkgs = ["flask", "flask_socketio", "plotly", "paho.mqtt", "eventlet", "waitress"]
missing = check_packages(required_pkgs)
if missing:
    print("Missing Python packages:", missing)
else:
    print("All required Python packages are installed.")

# --- 2. Check database ---
if os.path.exists(DB_PATH):
    tables = check_db(DB_PATH)
    if isinstance(tables, list):
        print(f"Database {DB_PATH} exists and contains tables:", tables)
    else:
        print("Database error:", tables)
else:
    print(f"Database file {DB_PATH} does not exist!")

# --- 3. Test MQTT broker connection and write test message ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT broker connection successful")
    else:
        print("MQTT broker connection failed, rc =", rc)

def on_publish(client, userdata, mid):
    print("Test message published successfully")

client = mqtt.Client()
if mqtt_username:
    client.username_pw_set(mqtt_username, mqtt_password)
client.on_connect = on_connect
client.on_publish = on_publish

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    # Publish a test message
    test_topic = "mqttplot/test"
    test_payload = json.dumps({"value": 123.456})
    client.publish(test_topic, test_payload)
    time.sleep(2)
    client.loop_stop()
except Exception as e:
    print("MQTT test failed:", e)

# --- 4. Test Flask API ---
try:
    url = f"http://localhost:{FLASK_PORT}/api/topics"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        print("Flask API /api/topics OK. Topics:", resp.json())
    else:
        print("Flask API /api/topics returned status", resp.status_code)
except Exception as e:
    print("Flask API test failed:", e)

print("=== MQTTPlot test script finished ===")
