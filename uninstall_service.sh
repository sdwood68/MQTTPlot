#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/mqttplot"
SERVICE_FILE="/etc/systemd/system/mqttplot.service"
CLI_WRAPPER="/usr/local/bin/mqttplot"
LOG_DIR="/var/log/mqttplot"
USER="mqttplot"
DB_FILE="$INSTALL_DIR/mqtt_data.db"

KEEP_DATA=1
REMOVE_USER=0

usage() {
  echo "Usage: sudo $0 [--purge-data] [--remove-user]"
  echo "  --purge-data    Remove the SQLite databases as well"
  echo "  --remove-user   Remove the mqttplot system user"
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

if [[ -f "$DB_FILE" ]]; then
  backup="$DB_FILE.uninstall-bak-$(date +%F-%H%M%S)"
  echo "Backing up metadata DB to: $backup"
  cp -a "$DB_FILE" "$backup"
fi

if systemctl is-active --quiet mqttplot; then
  systemctl stop mqttplot
fi
if systemctl is-enabled --quiet mqttplot; then
  systemctl disable mqttplot
fi

rm -f "$SERVICE_FILE"
rm -f "$CLI_WRAPPER"
systemctl daemon-reload

rm -rf "$LOG_DIR"

if [[ $KEEP_DATA -eq 1 ]]; then
  echo "Preserving databases under $INSTALL_DIR"
  if [[ -d "$INSTALL_DIR" ]]; then
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
      ! -name "$(basename "$DB_FILE")" \
      ! -name "data" \
      ! -name "backups" \
      -exec rm -rf {} +
  fi
else
  rm -rf "$INSTALL_DIR"
fi

if [[ $REMOVE_USER -eq 1 ]] && id -u "$USER" >/dev/null 2>&1; then
  userdel -r "$USER" || true
fi

echo "=== Uninstallation complete ==="
