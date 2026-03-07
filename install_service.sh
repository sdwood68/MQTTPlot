#!/bin/bash
set -euo pipefail

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
CLI_WRAPPER="/usr/local/bin/mqttplot"
LOG_DIR="/var/log/mqttplot"
BACKUP_DIR="$INSTALL_DIR/backups"
SECRET_FILE="$INSTALL_DIR/secret.env"
DB_PATH="$INSTALL_DIR/mqtt_data.db"
DATA_DB_DIR="$INSTALL_DIR/data"
DB_BASENAME="$(basename "$DB_PATH")"

DEFAULT_MQTT_BROKER="192.168.12.50"
DEFAULT_MQTT_PORT="1883"
DEFAULT_MQTT_USERNAME="Lock32Gauge"
DEFAULT_MQTT_PASSWORD="NeverGetWet"
DEFAULT_MQTT_TOPICS="watergauge/#"
DEFAULT_FLASK_PORT="5000"

apt_get_install() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    sqlite3 \
    rsync
}

write_cli_wrapper() {
  cat > "$CLI_WRAPPER" <<EOF
#!/bin/bash
set -euo pipefail
if [[ -f "$SECRET_FILE" ]]; then
  set -a
  source "$SECRET_FILE"
  set +a
fi
export MQTTPLOT_SECRET_FILE="$SECRET_FILE"
exec "$INSTALL_DIR/venv/bin/python3" -m mqttplot.cli "\$@"
EOF
  chmod 755 "$CLI_WRAPPER"
}

configure_firewall() {
  if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
      ufw allow "${FLASK_PORT}/tcp" >/dev/null || true
      echo "UFW rule ensured for tcp/${FLASK_PORT}"
    else
      echo "UFW installed but inactive; skipping firewall rule."
    fi
  else
    echo "UFW not installed; skipping firewall configuration."
  fi
}

echo "=== MQTTPlot Installer ==="
echo "RESET_DB=$RESET_DB"

echo "Installing required OS packages..."
apt_get_install

echo "Ensuring system user 'mqttplot' exists..."
id -u mqttplot &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mqttplot

mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$DATA_DB_DIR" "$BACKUP_DIR"
chown mqttplot:mqttplot "$INSTALL_DIR" "$LOG_DIR" "$DATA_DB_DIR" "$BACKUP_DIR"
chmod 755 "$INSTALL_DIR" "$LOG_DIR" "$DATA_DB_DIR" "$BACKUP_DIR"

if [[ -f "$DB_PATH" ]]; then
  if [[ $RESET_DB -eq 1 ]]; then
    ts=$(date +%Y%m%d-%H%M%S)
    echo "--reset-db specified. Backing up and recreating DB."
    cp -a "$DB_PATH" "$DB_PATH.bak-$ts"
    rm -f "$DB_PATH"
  else
    echo "Existing metadata DB detected: $DB_PATH (will preserve)"
  fi
fi

TMP_DB=""
TMP_SECRET=""
if [[ -f "$DB_PATH" && $RESET_DB -eq 0 ]]; then
  TMP_DB="/tmp/${DB_BASENAME}.$$"
  mv "$DB_PATH" "$TMP_DB"
fi
if [[ -f "$SECRET_FILE" ]]; then
  TMP_SECRET="/tmp/secret.env.$$"
  mv "$SECRET_FILE" "$TMP_SECRET"
fi

echo "Copying project files to $INSTALL_DIR ..."
rsync -a --delete \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'venv/' \
  --exclude 'backups/' \
  ./ "$INSTALL_DIR/"

if [[ -n "$TMP_SECRET" && -f "$TMP_SECRET" ]]; then
  mv "$TMP_SECRET" "$SECRET_FILE"
fi
if [[ -n "$TMP_DB" && -f "$TMP_DB" ]]; then
  mv "$TMP_DB" "$DB_PATH"
fi

if [[ ! -f "$INSTALL_DIR/requirements.txt" ]]; then
  echo "Error: $INSTALL_DIR/requirements.txt not found after copy."
  exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "Creating metadata DB file: $DB_PATH"
  install -o mqttplot -g mqttplot -m 664 /dev/null "$DB_PATH"
else
  chown mqttplot:mqttplot "$DB_PATH"
  chmod 664 "$DB_PATH"
fi

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

echo "Creating protected secret.env file..."
if [[ -f "$SECRET_FILE" ]]; then
  EXISTING_SECRET_KEY=$(grep -E '^SECRET_KEY=' "$SECRET_FILE" | head -n1 | cut -d= -f2- || true)
else
  EXISTING_SECRET_KEY=""
fi
if [[ -n "$EXISTING_SECRET_KEY" ]]; then
  SECRET_KEY="$EXISTING_SECRET_KEY"
else
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
fi

cat > "$SECRET_FILE" <<EOF
MQTT_BROKER=$MQTT_BROKER
MQTT_PORT=$MQTT_PORT
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
MQTT_TOPICS=$MQTT_TOPICS
FLASK_PORT=$FLASK_PORT
DB_PATH=$DB_PATH
DATA_DB_DIR=$DATA_DB_DIR
MQTTPLOT_BACKUP_DIR=$BACKUP_DIR
MQTTPLOT_BACKUP_KEEP=10
SECRET_KEY=$SECRET_KEY
EOF

chown root:mqttplot "$SECRET_FILE"
chmod 640 "$SECRET_FILE"

echo "Creating Python virtual environment..."
rm -rf "$INSTALL_DIR/venv"
sudo -u mqttplot python3 -m venv "$INSTALL_DIR/venv"

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
  MQTTPLOT_SECRET_FILE="$SECRET_FILE" \
  DB_PATH="$DB_PATH" \
  DATA_DB_DIR="$DATA_DB_DIR" \
  bash -c "
set -e
source '$INSTALL_DIR/venv/bin/activate'
cd '$INSTALL_DIR'
python3 - <<'PY'
import os
from werkzeug.security import generate_password_hash
from mqttplot.storage import init_meta_db, record_app_version, init_admin_user, get_meta_db
from version import __version__

init_meta_db()
record_app_version(__version__)
init_admin_user()

admin_pass = os.environ.get('ADMIN_INIT_PASSWORD')
if not admin_pass:
    raise SystemExit('ADMIN_INIT_PASSWORD not set')

db = get_meta_db()
password_hash = generate_password_hash(admin_pass)
db.execute(
    '''
    INSERT INTO admin_users(username, password_hash, created_ts_epoch)
    VALUES(?, ?, strftime('%s','now'))
    ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash
    ''',
    ('admin', password_hash),
)
db.commit()
print('Admin user initialized/updated: admin')
PY
"

SRC_SERVICE_FILE="$INSTALL_DIR/deploy/mqttplot.service"
echo "Installing systemd service file..."
if [[ -f "$SRC_SERVICE_FILE" ]]; then
  cp -f "$SRC_SERVICE_FILE" "$SERVICE_FILE"
else
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mqttplot
Group=mqttplot
WorkingDirectory=$INSTALL_DIR
Environment=FLASK_ENV=production
Environment=FLASK_DEBUG=0
Environment=PYTHONUNBUFFERED=1
Environment=MQTTPLOT_LOG_LEVEL=INFO
EnvironmentFile=$SECRET_FILE
ExecStart=$INSTALL_DIR/venv/bin/python3 -u $INSTALL_DIR/app.py
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/mqttplot.log
StandardError=append:$LOG_DIR/mqttplot.log

[Install]
WantedBy=multi-user.target
EOF
fi
chmod 644 "$SERVICE_FILE"

write_cli_wrapper
configure_firewall

chown -R mqttplot:mqttplot "$INSTALL_DIR" "$LOG_DIR"
chmod 755 "$BACKUP_DIR"

systemctl daemon-reload
systemctl enable mqttplot
systemctl restart mqttplot

echo "=== Installation complete ==="
echo "CLI: $CLI_WRAPPER"
echo "Logs: sudo tail -f $LOG_DIR/mqttplot.log"
echo "Web UI: http://YOUR_SERVER_IP:$FLASK_PORT"
