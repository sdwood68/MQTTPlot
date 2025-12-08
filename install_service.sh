#!/bin/bash
set -e

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"

echo "=== MQTTPlot Installer ==="

# Create mqttplot system user with home directory
echo "Creating system user 'mqttplot' with home at $INSTALL_DIR..."
sudo id -u mqttplot &>/dev/null || sudo useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" mqttplot

# Create directories
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOG_DIR"

# Copy project files
echo "Copying project files..."
sudo cp -r ./* "$INSTALL_DIR"

# Set ownership and permissions
sudo chown -R mqttplot:mqttplot "$INSTALL_DIR"
sudo chmod -R 755 "$INSTALL_DIR"
sudo chown -R mqttplot:mqttplot "$LOG_DIR"

# === MQTT settings ===
read -rp "Enter MQTT broker IP: " MQTT_BROKER
read -rp "Enter MQTT port [1883]: " MQTT_PORT
MQTT_PORT=${MQTT_PORT:-1883}

read -rp "Enter MQTT username: " MQTT_USERNAME
read -rp "Enter MQTT password (visible): " MQTT_PASSWORD

read -rp "Enter MQTT topic filter (e.g. watergauge/#): " MQTT_TOPICS

# === Flask settings ===
read -rp "Enter Flask port [5000]: " FLASK_PORT
FLASK_PORT=${FLASK_PORT:-5000}

DB_PATH="$INSTALL_DIR/mqtt_data.db"

# === Create protected credential file ===
echo "Creating protected credential file..."
sudo bash -c "cat > $SECRET_FILE" <<EOF
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
EOF

sudo chown root:root "$SECRET_FILE"
sudo chmod 600 "$SECRET_FILE"

# === Create Python virtual environment ===
echo "Creating Python virtual environment..."
sudo -u mqttplot python3 -m venv "$INSTALL_DIR/venv"

# === Install required Python packages inside venv as mqttplot user ===
echo "Installing Python packages..."
sudo -u mqttplot bash -c "
source $INSTALL_DIR/venv/bin/activate
pip install --upgrade pip
pip install flask flask_socketio eventlet plotly paho-mqtt waitress
deactivate
"

# === Write systemd service file ===
echo "Writing systemd service file..."
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network.target

[Service]
User=mqttplot
Group=mqttplot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py

# Load secure credentials
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

# Reload and start service
echo "Reloading and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable mqttplot
sudo systemctl restart mqttplot

echo "=== Installation complete ==="
echo "Logs: sudo tail -f $LOG_DIR/mqttplot.log"
echo "Web UI: http://YOUR_SERVER_IP:$FLASK_PORT"
