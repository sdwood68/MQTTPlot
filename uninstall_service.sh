#!/bin/bash
set -e

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
USER="mqttplot"

echo "=== MQTTPlot Uninstaller ==="

# Stop and disable service
if systemctl is-active --quiet mqttplot; then
    echo "Stopping MQTTPlot service..."
    sudo systemctl stop mqttplot
fi

if systemctl is-enabled --quiet mqttplot; then
    echo "Disabling MQTTPlot service..."
    sudo systemctl disable mqttplot
fi

# Remove systemd service file
if [ -f "$SERVICE_FILE" ]; then
    echo "Removing systemd service file..."
    sudo rm -f "$SERVICE_FILE"
fi

# Reload systemd daemon
sudo systemctl daemon-reload

# Remove application directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing application directory and database..."
    sudo rm -rf "$INSTALL_DIR"
fi

# Remove log directory
if [ -d "$LOG_DIR" ]; then
    echo "Removing log directory..."
    sudo rm -rf "$LOG_DIR"
fi

# Remove mqttplot user
if id -u $USER >/dev/null 2>&1; then
    echo "Deleting system user '$USER'..."
    sudo userdel -r $USER || true
fi

echo "=== Uninstallation complete ==="
