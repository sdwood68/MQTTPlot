#!/bin/bash
set -e

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"
USER="mqttplot"

echo "=== MQTTPlot Installer ==="

# --- Create system user ---
if ! id -u $USER >/dev/null 2>&1; then
    echo "Creating system user '$USER' with home at $INSTALL_DIR..."
    sudo useradd -r -m -d "$INSTALL_DIR" -s /usr/sbin/nologin $USER
fi

# --- Create directories ---
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOG_DIR"

# --- Copy project files ---
echo "Copying project files..."
sudo cp -r ./* "$INSTALL_DIR"
sudo chown -R $USER:$USER "$INSTALL_DIR"
sudo chmod -R 755 "$INSTALL_DIR"
sudo chown -R $USER:$USER "$LOG_DIR"

# --- Prompt for settings ---
read -rp "Enter MQTT broker IP: " MQTT_BROKER
read -rp "Enter MQTT port [1883]: " MQTT_PORT
MQTT_PORT=${MQTT_PORT:-1883}
read -rp "Enter MQTT username: " MQTT_USERNAME
read -rp "Enter MQTT password (visible): " MQTT_PASSWORD
read -rp "Enter MQTT topic filter (e.g. watergauge/#): " MQTT_TOPICS

read -rp "Enter Flask port [5000]: " FLASK_PORT
FLASK_PORT=${FLASK_PORT:-5000}

DB_PATH="$INSTALL_DIR/mqtt_data.db"

# --- Create secret.env with all variables ---
echo "Creating protected secret.env file..."
sudo bash -c "cat > $SECRET_FILE" <<EOF
MQTT_BROKER=$MQTT_BROKER
MQTT_PORT=$MQTT_PORT
MQTT_TOPICS=$MQTT_TOPICS
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
DB_PATH=$DB_PATH
FLASK_PORT=$FLASK_PORT
EOF

sudo chown root:root "$SECRET_FILE"
sudo chmod 600 "$SECRET_FILE"

# --- Create Python virtual environment ---
echo "Creating Python virtual environment..."
sudo -u $USER python3 -m venv "$INSTALL_DIR/venv"

# --- Install Python dependencies ---
echo "Installing Python packages..."
sudo -u $USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u $USER "$INSTALL_DIR/venv/bin/pip" install flask flask_socketio eventlet plotly paho-mqtt waitress

# --- Write systemd service file ---
echo "Writing systemd service file..."
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=MQTTPlot Data Collector and Web Server
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$SECRET_FILE
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
