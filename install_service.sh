#!/bin/bash
set -e

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"

echo "=== MQTTPlot Installer ==="

# Create mqttplot system user (no login)
echo "Creating system user 'mqttplot'..."
sudo id -u mqttplot &>/dev/null || sudo useradd -r -s /usr/sbin/nologin mqttplot

# Create directories
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOG_DIR"

echo "Copying project files..."
sudo cp -r ./* "$INSTALL_DIR"

# Set correct permissions BEFORE venv install
sudo chown -R mqttplot:mqttplot "$INSTALL_DIR"
sudo chmod -R 755 "$INSTALL_DIR"
sudo chown -R mqttplot:mqttplot "$LOG_DIR"

echo "=== MQTT Settings ==="
read -rp "Enter MQTT broker IP: " MQTT_BROKER
read -rp "Enter MQTT port [1883]: " MQTT_PORT
MQTT_PORT=${MQTT_PORT:-1883}

read -rp "Enter MQTT username: " MQTT_USERNAME
read -rp "Enter MQTT password (visible): " MQTT_PASSWORD

read -rp "Enter MQTT topic filter (e.g. watergauge/#): " MQTT_TOPICS

echo "=== Flask Settings ==="
read -rp "Enter Flask port [5000]: " FLASK_PORT
FLASK_PORT=${FLASK_PORT:-5000}

DB_PATH="$INSTALL_DIR/mqtt_data.db"

echo "=== Writing protected credential file ==="
sudo bash -c "cat > $SECRET_FILE" <<EOF
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
EOF

sudo chown root:root "$SECRET_FILE"
sudo chmod 600 "$SECRET_FILE"

echo "=== Creating Python virtual environment ==="
sudo -u mqttplot python3 -m venv "$INSTALL_DIR/venv"

source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip
pip install flask paho-mqtt plotly waitress
deactivate

echo "=== Writing systemd service file (running as mqttplot) ==="

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network.target

[Service]
User=mqttplot
Group=mqttplot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py

# Secure password file loaded by systemd as root
EnvironmentFile=$SECRET_FILE

# Other variables
Environment="MQTT_BROKER=$MQTT_BROKER"
Environment="MQTT_PORT=$MQTT_PORT"
Environment="MQTT_TOPICS=$MQTT_TOPICS"
Environment="FLASK_PORT=$FLASK_PORT"
Environment="DB_PATH=$DB_PATH"

Restart=always
StandardOutput=append:$LOG_DIR/mqttplot.log
StandardError=append:$LOG_DIR/mqttplot.log

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable mqttplot
sudo systemctl restart mqttplot

echo "=== Installation complete ==="
echo "Logs: sudo tail -f $LOG_DIR/mqttplot.log"
echo "Web UI: http://YOUR_SERVER_IP:$FLASK_PORT"
