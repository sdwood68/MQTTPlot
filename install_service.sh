#!/bin/bash
SERVICE_NAME="mqttplot.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
PROJECT_DIR="/opt/mqttplot"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_BIN="/usr/bin/python3"
LOG_DIR="/var/log/mqttplot"

if [ "$EUID" -ne 0 ]; then echo "Run as root"; exit 1; fi

read -p "Run service as user [ubuntu]: " SERVICE_USER
SERVICE_USER=${SERVICE_USER:-ubuntu}
read -p "MQTT broker [localhost]: " MQTT_BROKER; MQTT_BROKER=${MQTT_BROKER:-localhost}
read -p "MQTT topics [sensors/#]: " MQTT_TOPICS; MQTT_TOPICS=${MQTT_TOPICS:-sensors/#}
read -p "Flask port [5000]: " FLASK_PORT; FLASK_PORT=${FLASK_PORT:-5000}

mkdir -p $PROJECT_DIR
chown -R $SERVICE_USER:$SERVICE_USER $PROJECT_DIR

if [ ! -d "$VENV_DIR" ]; then
  sudo -u $SERVICE_USER $PYTHON_BIN -m venv $VENV_DIR
fi

sudo -u $SERVICE_USER bash -c "source $VENV_DIR/bin/activate && pip install --upgrade pip setuptools"
sudo -u $SERVICE_USER bash -c "source $VENV_DIR/bin/activate && pip install flask flask-socketio eventlet paho-mqtt plotly kaleido"

mkdir -p $LOG_DIR
touch $LOG_DIR/mqttplot.log $LOG_DIR/mqttplot-error.log
chmod 666 $LOG_DIR/mqttplot*.log

cat <<EOF > $SERVICE_PATH
[Unit]
Description=MQTTPlot - MQTT Data Dashboard and API
After=network.target

[Service]
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/app.py

Environment=MQTT_BROKER=$MQTT_BROKER
Environment=MQTT_PORT=1883
Environment=MQTT_TOPICS=$MQTT_TOPICS
Environment=FLASK_PORT=$FLASK_PORT
Environment=DB_PATH=$PROJECT_DIR/mqtt_data.db

Restart=always
RestartSec=5
User=$SERVICE_USER
Group=$SERVICE_USER

StandardOutput=append:$LOG_DIR/mqttplot.log
StandardError=append:$LOG_DIR/mqttplot-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo "Installed mqttplot service"
