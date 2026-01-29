#!/bin/bash
set -euo pipefail

# --- Ensure script is run as root ---
if [[ $EUID -ne 0 ]]; then
  echo "Error: This installer must be run as root."
  echo "Please run: sudo $0"
  exit 1
fi

RESET_DB=0
if [[ "${1:-}" == "--reset-db" ]]; then
  RESET_DB=1
fi

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"

DB_PATH="$INSTALL_DIR/mqtt_data.db"
DB_BASENAME="$(basename "$DB_PATH")"

echo "=== MQTTPlot Installer ==="
echo "RESET_DB=$RESET_DB"

# --- Create system user ---
echo "Ensuring system user 'mqttplot' exists..."
id -u mqttplot &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mqttplot

# --- Create directories ---
mkdir -p "$INSTALL_DIR" "$LOG_DIR"
chown mqttplot:mqttplot "$INSTALL_DIR" "$LOG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$LOG_DIR"

# --- Handle existing DB before copying files ---
if [[ -f "$DB_PATH" ]]; then
  if [[ $RESET_DB -eq 1 ]]; then
    ts=$(date +%Y%m%d-%H%M%S)
    echo "⚠️  --reset-db specified. Backing up and recreating DB."
    cp -a "$DB_PATH" "$DB_PATH.bak-$ts"
    rm -f "$DB_PATH"
  else
    echo "✅ Existing database detected: $DB_PATH (will preserve)"
  fi
fi

# --- Copy project files WITHOUT overwriting preserved DB ---
echo "Copying project files to $INSTALL_DIR ..."
# If an old DB exists and we are not resetting, temporarily move it out of the way
TMP_DB=""
if [[ -f "$DB_PATH" && $RESET_DB -eq 0 ]]; then
  TMP_DB="/tmp/${DB_BASENAME}.$$"
  mv "$DB_PATH" "$TMP_DB"
fi

# Copy everything from current directory into INSTALL_DIR
# (This assumes you run the installer from your project directory)
# cp -a ./* "$INSTALL_DIR/"
rsync -a --delete ./ "$INSTALL_DIR"/


# Restore DB if we preserved it
if [[ -n "${TMP_DB:-}" ]]; then
  mv "$TMP_DB" "$DB_PATH"
fi

# --- Validate requirements.txt exists in installed location ---
if [[ ! -f "$INSTALL_DIR/requirements.txt" ]]; then
  echo "Error: $INSTALL_DIR/requirements.txt not found after copy."
  echo "Make sure requirements.txt exists in your project directory."
  exit 1
fi

# --- Ensure DB exists (create if missing) ---
if [[ ! -f "$DB_PATH" ]]; then
  echo "Creating new database file: $DB_PATH"
  install -o mqttplot -g mqttplot -m 664 /dev/null "$DB_PATH"
else
  chown mqttplot:mqttplot "$DB_PATH"
  chmod 664 "$DB_PATH"
fi

# --- Ownership for app files (do NOT chmod everything recursively) ---
chown -R mqttplot:mqttplot "$INSTALL_DIR"
chown -R mqttplot:mqttplot "$LOG_DIR"

# Ensure secret file permissions will be set later
# (Do NOT chmod -R 755 the whole install dir)

# --- Default values ---
DEFAULT_MQTT_BROKER="192.168.12.50"
DEFAULT_MQTT_PORT="1883"
DEFAULT_MQTT_USERNAME="Lock32Gauge"
DEFAULT_MQTT_PASSWORD="NeverGetWet"
DEFAULT_MQTT_TOPICS="watergauge/#"
DEFAULT_FLASK_PORT="5000"

echo
echo "=== Admin Account Setup ==="
while true; do
  read -s -p "Enter initial admin password: " ADMIN_PASS
  echo
  read -s -p "Confirm admin password: " ADMIN_PASS_CONFIRM
  echo
  if [[ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]]; then
    echo "Passwords do not match. Try again."
  elif [[ -z "$ADMIN_PASS" ]]; then
    echo "Password cannot be empty."
  else
    break
  fi
done

read -rp "Enter MQTT broker IP [$DEFAULT_MQTT_BROKER]: " MQTT_BROKER
MQTT_BROKER=${MQTT_BROKER:-$DEFAULT_MQTT_BROKER}

read -rp "Enter MQTT port [$DEFAULT_MQTT_PORT]: " MQTT_PORT
MQTT_PORT=${MQTT_PORT:-$DEFAULT_MQTT_PORT}

read -rp "Enter MQTT username [$DEFAULT_MQTT_USERNAME]: " MQTT_USERNAME
MQTT_USERNAME=${MQTT_USERNAME:-$DEFAULT_MQTT_USERNAME}

read -rp "Enter MQTT password [$DEFAULT_MQTT_PASSWORD]: " MQTT_PASSWORD
MQTT_PASSWORD=${MQTT_PASSWORD:-$DEFAULT_MQTT_PASSWORD}

read -rp "Enter MQTT topic filter [$DEFAULT_MQTT_TOPICS]: " MQTT_TOPICS
MQTT_TOPICS=${MQTT_TOPICS:-$DEFAULT_MQTT_TOPICS}

read -rp "Enter Flask port [$DEFAULT_FLASK_PORT]: " FLASK_PORT
FLASK_PORT=${FLASK_PORT:-$DEFAULT_FLASK_PORT}

echo
echo "=== Configuration ==="
echo "MQTT_BROKER=$MQTT_BROKER"
echo "MQTT_PORT=$MQTT_PORT"
echo "MQTT_USERNAME=$MQTT_USERNAME"
echo "MQTT_PASSWORD=$MQTT_PASSWORD"
echo "MQTT_TOPICS=$MQTT_TOPICS"
echo "FLASK_PORT=$FLASK_PORT"
echo "DB_PATH=$DB_PATH"
echo "INSTALL_DIR=$INSTALL_DIR"
echo "LOG_DIR=$LOG_DIR"
echo "SECRET_FILE=$SECRET_FILE"
echo "====================="

# --- Create secret.env ---
echo "Creating protected secret.env file..."
# Generate a persistent SECRET_KEY for Flask sessions (required for stable admin auth)
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > "$SECRET_FILE" <<EOF
MQTT_BROKER=$MQTT_BROKER
MQTT_PORT=$MQTT_PORT
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
MQTT_TOPICS=$MQTT_TOPICS
FLASK_PORT=$FLASK_PORT
DB_PATH=$DB_PATH
SECRET_KEY=$SECRET_KEY
EOF

chown root:mqttplot "$SECRET_FILE"
chmod 640 "$SECRET_FILE"

# --- Create / recreate Python virtual environment ---
echo "Creating Python virtual environment..."
# If venv exists, keep it unless you want to force rebuild; simplest is rebuild:
rm -rf "$INSTALL_DIR/venv"
sudo -u mqttplot python3 -m venv "$INSTALL_DIR/venv"

# --- Install Python packages from requirements.txt ---
echo "Installing Python packages from requirements.txt..."
sudo -u mqttplot bash -c "
set -e
source '$INSTALL_DIR/venv/bin/activate'
pip install --upgrade pip
pip install -r '$INSTALL_DIR/requirements.txt'
"

echo "Initializing database schema and admin account..."

sudo -u mqttplot env \
  ADMIN_INIT_PASSWORD="$ADMIN_PASS" \
  DB_PATH="$DB_PATH" \
  bash -c '
set -e
source "/opt/mqttplot/venv/bin/activate"
python3 - <<'"'"'PY'"'"'
import os, sqlite3
from werkzeug.security import generate_password_hash

db_path = os.environ.get("DB_PATH", "/opt/mqttplot/mqtt_data.db")
admin_pass = os.environ.get("ADMIN_INIT_PASSWORD")
if not admin_pass:
    raise SystemExit("ADMIN_INIT_PASSWORD not set")

db = sqlite3.connect(db_path)
c = db.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    ts TIMESTAMP NOT NULL,
    payload TEXT,
    value REAL
)""")
c.execute("""CREATE TABLE IF NOT EXISTS topic_meta (
    topic TEXT PRIMARY KEY,
    public INTEGER DEFAULT 1
)""")
c.execute("CREATE INDEX IF NOT EXISTS idx_topic_ts ON messages(topic, ts)")

c.execute("""CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

ph = generate_password_hash(admin_pass)
c.execute("""INSERT INTO admin_users (username, password_hash)
             VALUES ("admin", ?)
             ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash""", (ph,))

db.commit()
db.close()
print("Admin user initialized/updated: admin")
PY
'


# --- Write systemd service file ---
echo "Writing systemd service file..."
tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network.target

[Service]
User=mqttplot
Group=mqttplot
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$SECRET_FILE
ExecStart=$INSTALL_DIR/venv/bin/python3 -u $INSTALL_DIR/app.py
Restart=always
StandardOutput=append:$LOG_DIR/mqttplot.log
StandardError=append:$LOG_DIR/mqttplot.log

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd and starting MQTTPlot service..."
systemctl daemon-reload
systemctl enable mqttplot
systemctl restart mqttplot

echo "=== Installation complete ==="
echo "Logs: sudo tail -f $LOG_DIR/mqttplot.log"
echo "Web UI: http://YOUR_SERVER_IP:$FLASK_PORT"
