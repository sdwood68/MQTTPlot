#!/bin/bash
set -e

SERVICE_FILE="/etc/systemd/system/mqttplot.service"
INSTALL_DIR="/opt/mqttplot"
LOG_DIR="/var/log/mqttplot"

echo "=== MQTTPlot Uninstaller ==="

# Stop the service if running
if systemctl is-active --quiet mqttplot; then
    echo "Stopping MQTTPlot service..."
    sudo systemctl stop mqttplot
fi

# Disable service
if systemctl is-enabled --quiet mqttplot; then
    echo "Disabling MQTTPlot service..."
    sudo systemctl disable mqttplot
fi

# Remove service file
if [ -f "$SERVICE_FILE" ]; then
    echo "Removing systemd service file..."
    sudo rm -f "$SERVICE_FILE"
fi

# Reload systemd
sudo systemctl daemon-reload

# Remove mqttplot user
if id "mqttplot" &>/dev/null; then
    echo "Removing mqttplot system user and home directory..."
    sudo userdel -r mqttplot 2>/dev/null || true
fi

# Remove installation directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing installation directory..."
    sudo rm -rf "$INSTALL_DIR"
fi

# Remove logs
if [ -d "$LOG_DIR" ]; then
    echo "Removing log directory..."
    sudo rm -rf "$LOG_DIR"
fi

echo "=== MQTTPlot completely removed ==="
