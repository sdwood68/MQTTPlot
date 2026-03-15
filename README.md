# MQTTPlot

MQTTPlot is a lightweight MQTT data ingestion and visualization service for
long-running IoT and telemetry systems. It subscribes to MQTT topics, stores
time-series data in SQLite, and serves interactive Plotly-based charts through
a web interface.

Version **0.8.3** focuses on release hardening and operational tooling. It adds
a small admin/ops CLI, service health reporting, installer improvements, and a
working Broker Settings time-zone selector in the admin UI.

---

## What is new in 0.8.3

- Installer now installs `sqlite3` and `rsync` automatically.
- Installer adds a UFW allow rule for the configured Flask port when UFW is
  installed and active.
- New operational CLI commands:
  - `mqttplot status`
  - `mqttplot db-info`
  - `mqttplot backup`
  - `mqttplot reset-admin-password`
  - `mqttplot reload`
- Added `/api/health` for basic service health checks.
- Fixed the Broker Settings time-zone dropdown so the admin can select and save
  an IANA time zone.

---

## Key features

### Core

- MQTT subscription with wildcard topic support
- Persistent SQLite storage
  - one metadata DB for admin/app state
  - one data DB per top-level MQTT topic under `DATA_DB_DIR`
- Automatic database creation and schema management
- Time-windowed queries optimized for plotting

### Plotting and UI

- Interactive Plotly graphs
- Multi-topic plots with one or two Y axes
- In-plot navigation controls
- Preview thumbnails for plots
- Admin and public plot pages share the same plot window behavior

### Public access

- Slug-based public plot URLs
- Read-only plot views suitable for dashboards and wall displays
- Public pages do not expose internal MQTT topic names or credentials
- Suitable for iframe embedding

### Administration

- Password-protected admin views
- Topic-to-plot mapping control
- Plot metadata management
- Broker Settings for time zone, broker host, broker port, and topic filter
- Operational CLI for backup, service status, and password reset

---

## Architecture overview

MQTTPlot has four primary layers:

1. **Ingestion**: MQTT client subscribes to topics and receives messages.
2. **Persistence**: SQLite stores metadata and per-topic time-series data.
3. **Plot definitions**: metadata describes what to graph and how to present it.
4. **Presentation**: admin UI and public slug-based routes render plots.

```text
                    ┌──────────────────────────┐
                    │        MQTT Broker       │
                    │   (sensors, devices)     │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │     1) MQTT Ingestion    │
                    │   (subscriber / parser)  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌───────────────────────────┐
                    │    2) SQLite Persistence  │
                    │  meta DB + per-root DBs   │
                    └────────────┬──────────────┘
                                 │
               ┌─────────────────┴─────────────────┐
               │      3) Plot Definition Layer     │
               │  (topics → series → axes → slug)  │
               └─────────────────┬─────────────────┘
                                 │
                ┌────────────────┴─────────────────┐
                │                                  │
                ▼                                  ▼
┌──────────────────────────────┐     ┌──────────────────────────────┐
│       4A) ADMIN UI           │     │      4B) PUBLIC PLOTS        │
│   (authenticated / private)  │     │     (read-only / shared)     │
└──────────────────────────────┘     └──────────────────────────────┘
```

---

## Installation

The supported Linux install path uses the provided systemd installer scripts.

### Prerequisites

- Linux system with `systemd`
- Root or sudo access
- Python 3.10+
- Reachable MQTT broker

### Install

From the project root:

```bash
git clone https://github.com/sdwood68/MQTTPlot.git
cd MQTTPlot
chmod +x install_service.sh uninstall_service.sh
sudo ./install_service.sh
```

### Optional install flag

```bash
sudo ./install_service.sh --reset-db
```

Use `--reset-db` only when you want the installer to discard the existing
metadata DB at `/opt/mqttplot/mqtt_data.db` before first start.

### What the installer does

- Installs MQTTPlot under `/opt/mqttplot`
- Creates the `mqttplot` system user if needed
- Creates these persistent paths:

```text
/opt/mqttplot/mqtt_data.db   metadata DB
/opt/mqttplot/data/          per-top-level-topic SQLite DB files
/opt/mqttplot/backups/       ZIP backups from mqttplot backup
/opt/mqttplot/secret.env     runtime configuration
/var/log/mqttplot/           service log output
```

- Creates a Python virtual environment in `/opt/mqttplot/venv`
- Installs Python dependencies from `requirements.txt`
- Installs `/etc/systemd/system/mqttplot.service`
- Installs the `/usr/local/bin/mqttplot` operational CLI wrapper
- Opens the configured Flask port in UFW when UFW is active

---

## Configuration

The installer creates `/opt/mqttplot/secret.env`. Edit that file to change the
runtime configuration that is loaded by the service and the CLI.

```bash
sudo nano /opt/mqttplot/secret.env
```

Typical contents:

```text
MQTT_BROKER=192.168.12.50
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TOPICS=watergauge/#
FLASK_PORT=5000
DB_PATH=/opt/mqttplot/mqtt_data.db
DATA_DB_DIR=/opt/mqttplot/data
SECRET_KEY=change-me
```

### Applying configuration changes

After editing `secret.env`, restart the service or use:

```bash
sudo mqttplot reload
```

`mqttplot reload` currently performs a service restart so the new values in
`secret.env` are reloaded immediately.

---

## Service usage

### systemd

```bash
sudo systemctl status mqttplot
sudo systemctl restart mqttplot
sudo journalctl -u mqttplot -f
```

### mqttplot operational CLI

The installer places a wrapper at `/usr/local/bin/mqttplot`.

#### Show service status

```bash
sudo mqttplot status
```

This runs `systemctl status mqttplot` with `--no-pager --full`.

#### Reload configuration

```bash
sudo mqttplot reload
```

Use this after editing `/opt/mqttplot/secret.env`.

#### Reset the admin password

Interactive mode:

```bash
sudo mqttplot reset-admin-password
```

Non-interactive mode:

```bash
sudo mqttplot reset-admin-password --password 'NewStrongPassword'
```

This updates the password for the built-in `admin` user in the metadata DB.

#### Show database locations and sizes

```bash
sudo mqttplot db-info
```

This reports:

- the running MQTTPlot version
- the metadata DB path and size
- the data DB directory
- the number of per-topic DB files and their sizes

#### Create a backup ZIP

```bash
sudo mqttplot backup
```

Optional arguments:

```bash
sudo mqttplot backup --output /opt/mqttplot/backups --keep 5
```

Behavior:

- copies the metadata DB and the full data DB directory into a timestamped
  staging directory
- packages the staging directory into a ZIP archive
- removes the staging directory
- rotates older archives and keeps the newest `--keep` ZIP files

Backups are written to `/opt/mqttplot/backups` by default.

> Note: in 0.8.3, backups are file copies of live SQLite databases. A later
> roadmap item tracks moving this to the SQLite backup API for cleaner hot
> snapshots.

### Restore from backup

A manual restore is straightforward:

1. Stop the service.
2. Unzip the backup archive to a temporary directory.
3. Copy `mqtt_data.db` back to `/opt/mqttplot/`.
4. Copy the saved `data/` directory back to `/opt/mqttplot/data/`.
5. Ensure ownership is `mqttplot:mqttplot` for restored DB files.
6. Start the service.

Example:

```bash
sudo systemctl stop mqttplot
cd /tmp
unzip /opt/mqttplot/backups/mqttplot-backup-YYYYMMDD-HHMMSS.zip -d mqttplot-restore
sudo cp -f mqttplot-restore/mqtt_data.db /opt/mqttplot/
sudo rsync -a --delete mqttplot-restore/data/ /opt/mqttplot/data/
sudo chown mqttplot:mqttplot /opt/mqttplot/mqtt_data.db
sudo chown -R mqttplot:mqttplot /opt/mqttplot/data
sudo systemctl start mqttplot
```

---

## Admin UI notes

### Broker Settings

In admin mode, the **Broker Settings** panel lets you update:

- **Time zone**
- **Broker host**
- **Broker port**
- **Topic filter**

The time-zone dropdown is populated with IANA time-zone names such as:

- `UTC`
- `America/New_York`
- `America/Chicago`
- `America/Denver`
- `America/Los_Angeles`

The selected time zone is used when the UI formats timestamps for plots and
other time-related displays.

Broker Settings are stored in the metadata DB. If broker host, port, or topic
settings are changed, use `sudo mqttplot reload` to restart the service so the
MQTT client reconnects using the updated values.

### Public versus admin views

**Public views** are intended for shared, read-only access.

- show plots by slug
- do not expose internal topic names or credentials
- suitable for embedding

**Admin views** expose configuration and operational controls.

- manage plot definitions and topic metadata
- edit Broker Settings
- access admin-only APIs

---

## Health endpoint

MQTTPlot 0.8.3 includes a basic health endpoint:

```text
GET /api/health
```

Example:

```bash
curl http://127.0.0.1:5000/api/health
```

Typical response fields:

- `ok`
- `version`
- `mqtt`
- `meta_db.path`
- `meta_db.exists`
- `data_db_dir.path`
- `data_db_dir.exists`

This endpoint is useful for simple service monitoring and deployment checks.

---

## Embedded plots

Public plots can be embedded using an iframe:

```html
<iframe
  src="https://yourhost/plot/water-tank-level"
  width="100%"
  height="420"
  frameborder="0">
</iframe>
```

Recommendations:

- use a fixed height for stable dashboard layouts
- prefer a reverse proxy such as nginx or Caddy for TLS termination in
  production

---

## Uninstall

To remove MQTTPlot installed via the service installer:

```bash
sudo ./uninstall_service.sh
```

Options:

```bash
sudo ./uninstall_service.sh --purge-data
sudo ./uninstall_service.sh --remove-user
```

- `--purge-data` removes `/opt/mqttplot`, including DB files and backups
- `--remove-user` removes the `mqttplot` system user

By default, the uninstaller preserves `/opt/mqttplot/mqtt_data.db`,
`/opt/mqttplot/data`, and `/opt/mqttplot/backups`.

---

## Docker

Build and run MQTTPlot with Docker:

```bash
docker build -t mqttplot:0.8.3 .

mkdir -p ./data

docker run --rm -it   -p 5000:5000   -e MQTT_BROKER=192.168.12.50   -e MQTT_PORT=1883   -e MQTT_TOPICS=watergauge/#   -e DB_PATH=/data/mqtt_data.db   -e DATA_DB_DIR=/data/topics   -v "$(pwd)/data:/data"   mqttplot:0.8.3
```

Notes:

- `DB_PATH` is the metadata/admin database.
- `DATA_DB_DIR` holds the per-top-level-topic SQLite DB files.

---

## Versioning

MQTTPlot follows semantic versioning.

Recent milestones:

- 0.8.0: admin UI and unified plot system
- 0.8.1: admin page cleanup and Broker Settings UI changes
- 0.8.2: version display and reduced polling behavior
- 0.8.3: operational tooling, `/api/health`, installer improvements, and the
  Broker Settings time-zone dropdown fix
