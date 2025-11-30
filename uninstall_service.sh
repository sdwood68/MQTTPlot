#!/bin/bash
SERVICE_NAME="mqttplot.service"
PROJECT_DIR="/opt/mqttplot"
LOG_DIR="/var/log/mqttplot"

if [ "$EUID" -ne 0 ]; then echo "Run as root"; exit 1; fi

systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl disable $SERVICE_NAME 2>/dev/null || true
rm -f /etc/systemd/system/$SERVICE_NAME
systemctl daemon-reload

rm -rf $LOG_DIR
rm -rf $PROJECT_DIR

echo "Uninstalled MQTTPlot and removed all files."
