#!/bin/bash
set -e

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
LOG_DIR="/var/log/mqttplot"
USER="mqttplot"

DB_FILE="$INSTALL_DIR/mqtt_data.db"

KEEP_DATA=1
REMOVE_USER=0

usage() {
  echo "Usage: sudo $0 [--purge-data] [--remove-user]"
  echo "  --purge-data    Remove the SQLite database ($DB_FILE) as well"
  echo "  --remove-user   Remove the mqttplot system user (not recommended if keeping data)"
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

for arg in "$@"; do
  case "$arg" in
    --purge-data) KEEP_DATA=0 ;;
    --remove-user) REMOVE_USER=1 ;;
    *) ;;
  esac
done

echo "=== MQTTPlot Uninstaller ==="
echo "Keeping database: $KEEP_DATA (1=yes, 0=no)"
echo "Remove user:      $REMOVE_USER (1=yes, 0=no)"

# Backup DB if it exists
if [[ -f "$DB_FILE" ]]; then
  backup="$DB_FILE.uninstall-bak-$(date +%F-%H%M%S)"
  echo "Backing up database to: $backup"
  cp -a "$DB_FILE" "$backup"
else
  echo "No database found at $DB_FILE (skipping backup)"
fi

# Stop and disable service
if systemctl is-active --quiet mqttplot; then
  echo "Stopping MQTTPlot service..."
  systemctl stop mqttplot
fi

if systemctl is-enabled --quiet mqttplot; then
  echo "Disabling MQTTPlot service..."
  systemctl disable mqttplot
fi

# Remove systemd service file
if [[ -f "$SERVICE_FILE" ]]; then
  echo "Removing systemd service file..."
  rm -f "$SERVICE_FILE"
fi

systemctl daemon-reload

# Remove logs
if [[ -d "$LOG_DIR" ]]; then
  echo "Removing log directory..."
  rm -rf "$LOG_DIR"
fi

# Remove app files
if [[ $KEEP_DATA -eq 1 ]]; then
  echo "Preserving database: $DB_FILE"
  if [[ -d "$INSTALL_DIR" ]]; then
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
      ! -name "$(basename "$DB_FILE")" \
      -exec rm -rf {} +
  fi
else
  echo "Removing entire install directory including database..."
  rm -rf "$INSTALL_DIR"
fi

# Remove mqttplot user only if explicitly requested
if [[ $REMOVE_USER -eq 1 ]]; then
  if id -u "$USER" >/dev/null 2>&1; then
    echo "Deleting system user '$USER'..."
    userdel -r "$USER" || true
  fi
else
  echo "Keeping system user '$USER' (recommended)."
fi

echo "=== Uninstallation complete ==="
