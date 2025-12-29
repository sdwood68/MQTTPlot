#!/bin/bash
set -e

# --- Ensure script is run as root ---
if [[ $EUID -ne 0 ]]; then
    echo "Error: This installer must be run as root."
    echo "Please run: sudo $0"
    exit 1
fi

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"
# USER="mqttplot"

echo "=== MQTTPlot Installer ==="

# --- Create system user ---
echo "Creating system user 'mqttplot' with home at $INSTALL_DIR..."
sudo id -u mqttplot &>/dev/null || sudo useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mqttplot

# --- Create directories ---
sudo mkdir -p "$INSTALL_DIR" "$LOG_DIR"

# --- Copy project files ---
echo "Copying project files..."
sudo cp -r ./* "$INSTALL_DIR"

# --- Set ownership and permissions ---
sudo chown -R mqttplot:mqttplot "$INSTALL_DIR"
sudo chmod -R 755 "$INSTALL_DIR"
sudo chown -R mqttplot:mqttplot "$LOG_DIR"

# --- Default values ---
DEFAULT_MQTT_BROKER="192.168.12.50"
DEFAULT_MQTT_PORT="1883"
DEFAULT_MQTT_USERNAME="Lock32Gauge"
DEFAULT_MQTT_PASSWORD="NeverGetWet"
DEFAULT_MQTT_TOPICS="watergauge/#"
DEFAULT_FLASK_PORT="5000"

# --- Prompt for settings ---
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

DB_PATH="$INSTALL_DIR/mqtt_data.db"

# --- Show configuration for verification ---
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

# --- Create secret.env with all variables ---
echo "Creating protected secret.env file..."
sudo bash -c "cat > $SECRET_FILE" <<EOF
MQTT_BROKER=$MQTT_BROKER
MQTT_PORT=$MQTT_PORT
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
MQTT_TOPICS=$MQTT_TOPICS
FLASK_PORT=$FLASK_PORT
DB_PATH=$DB_PATH
EOF

sudo chown root:mqttplot /opt/mqttplot/secret.env
sudo chmod 640 /opt/mqttplot/secret.env

# --- Create Python virtual environment ---
echo "Creating Python virtual environment..."
sudo -u mqttplot python3 -m venv "$INSTALL_DIR/venv"

# --- Install required Python packages ---
echo "Installing Python packages..."
sudo -u mqttplot bash -c "
source $INSTALL_DIR/venv/bin/activate
pip install --upgrade pip
pip install flask flask_socketio eventlet plotly paho-mqtt waitress
deactivate
"

# --- Write systemd service file ---
echo "Writing systemd service file..."
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network.target

[Service]
User=mqttplot
Group=mqttplot
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$SECRET_FILE
Environment="DB_PATH=$DB_PATH"
Environment="MQTT_BROKER=$MQTT_BROKER"
Environment="MQTT_PORT=$MQTT_PORT"
Environment="MQTT_TOPICS=$MQTT_TOPICS"
Environment="FLASK_PORT=$FLASK_PORT"

ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py

Restart=always
StandardOutput=append:$LOG_DIR/mqttplot.log
StandardError=append:$LOG_DIR/mqttplot.log

[Install]
WantedBy=multi-user.target
EOF

# --- Enable and start service ---
echo "Reloading systemd and starting MQTTPlot service..."
sudo systemctl daemon-reload
sudo systemctl enable mqttplot
sudo systemctl restart mqttplot

echo "=== Installation complete ==="
echo "Logs: sudo tail -f $LOG_DIR/mqttplot.log"
echo "Web UI: http://YOUR_SERVER_IP:$FLASK_PORT"
