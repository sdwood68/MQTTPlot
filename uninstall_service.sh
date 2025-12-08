#!/bin/bash
set -e

SERVICE_FILE="/etc/systemd/system/mqttplot.service"
INSTALL_DIR="/opt/mqttplot"
LOG_DIR="/var/log/mqttplot"
SECRET_FILE="$INSTALL_DIR/secret.env"

echo "=== MQTTPlot Uninstaller ==="

if systemctl is-active --quiet mqttplot; then
    echo "Stopping service..."
    sudo systemctl stop mqttplot
fi

if systemctl is-enabled --quiet mqttplot; then
    echo "Disabling service..."
    sudo systemctl disable mqttplot
fi

if [ -f "$SERVICE_FILE" ]; then
    echo "Removing service file..."
    sudo rm -f "$SERVICE_FILE"
fi

sudo systemctl daemon-reload

if id "mqttplot" &>/dev/null; then
    echo "Removing mqttplot user..."
    sudo userdel -r mqttplot 2>/dev/null || true
fi

if [ -d "$INSTALL_DIR" ]; then
    echo "Removing app directory..."
    sudo rm -rf "$INSTALL_DIR"
fi

if [ -d "$LOG_DIR" ]; then
    echo "Removing logs..."
    sudo rm -rf "$LOG_DIR"
fi

echo "=== MQTTPlot completely removed ==="
