# MQTTPlot

**MQTTPlot** is a lightweight MQTT data ingestion and visualization service designed for long-running IoT and telemetry systems. It subscribes to MQTT topics, persists time-series data to SQLite, and serves interactive Plotly-based graphs via a web interface.

---

## Key Features

### Core
- MQTT subscription with wildcard topic support
- Persistent SQLite storage per topic
- Automatic database creation and schema management
- Time-windowed queries optimized for plotting

### Plotting & UI
- Interactive Plotly graphs
- Multi-topic plots (multiple series per chart)
- Dual Y-axis support with aligned major units
- In-plot navigation and controls
- Preview thumbnails for plots

### Public Access
- Slug-based public plot URLs
- Read-only embedded plot views
- No exposure of MQTT topics, database paths, or credentials
- Suitable for dashboards, iframes, and wall displays

### Administration
- Admin-only configuration views
- Topic-to-plot mapping control
- Plot metadata management (titles, units, axes)
- Separation of admin and public concerns


## Architecture Overview

MQTTPlot consists of four layers:
1) **Ingestion** (MQTT client subscribes to topics)
2) **Persistence** (SQLite stores time-series samples)
3) **Plot definitions** (metadata describing what/how to graph)
4) **Presentation** (admin UI + public, slug-based routes)

```
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
                    │  (time-series per topic)  │
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
│                              │     │                              │
│ • Configure plots            │     │ • Slug-based URLs            │
│ • Select MQTT topics         │     │ • No topic names visible     │
│ • Assign axes & units        │     │ • No configuration access    │
│ • Manage slugs               │     │ • Safe iframe embedding      │
│ • Preview plots              │     │ • Plot navigation controls   │
│                              │     │                              │
└──────────────────────────────┘     └──────────────────────────────┘
```
### Data Flow
1. MQTT messages arrive on subscribed topics.
2. Messages are parsed and stored to the topic’s SQLite database.
3. Plot routes query the database for a time window.
4. Plotly renders interactive charts in the browser.

### Separation of Concerns
- **Admin** routes expose configuration tools and internal details (protected).
- **Public** routes expose only plots via **slugs** (no internal topic names).

---

## Slug-Based Plot URLs

A **slug** is a short, URL-safe identifier that represents a plot definition.

Examples:
```
/plot/watergauge/height
/plot/outdoor-temperature
```

Key properties:
- Slugs map internally to one or more MQTT topics (one plot, many series).
- Public users never see topic names, database paths, or credentials.
- Slugs are stable and suitable for bookmarks or embedding.

---

## Public vs Admin Views

### Public (Read-Only)
- Intended for sharing, embedding, and unattended displays
- Shows the plot title, axes labels, series legend, and navigation controls
- Does not expose configuration, topic names, or backend details

### Admin
- Configure plots (title, units, axis assignment, series selection)
- Control what becomes public (by enabling a slug)
- Manage topic/series definitions and presentation settings

---

## Installation

MQTTPlot 0.7.0 includes dedicated **service install and uninstall scripts** intended for
Linux systems using `systemd`. These scripts provide a repeatable, production-oriented
installation with a dedicated service user and persistent data storage.

---

### Prerequisites

- Linux system with `systemd`
- Root or sudo access
- Python 3.10+
- SQLite 3
- Reachable MQTT broker (Mosquitto recommended)

---

### Install

From the project root:

```bash
git clone https://github.com/sdwood68/MQTTPlot.git
cd MQTTPlot
chmod +x install.sh uninstall.sh
sudo ./install.sh
```

#### What the installer does:

- Installs MQTTPlot under: `/opt/mqttplot`
- Creates a dedicated system user: `mqttplot`
- Creates persistent directories:
```
/var/lib/mqttplot     # SQLite databases
/var/log/mqttplot     # Application logs
/etc/mqttplot         # Configuration
```
- Creates a Python virtual environment
- Installs required Python dependencies
- Installs and enables a systemd service: `mqttplot.service`

The service runs as the **mqttplot** user (not root).

### Optional Install Flags
```
sudo ./install_service.sh --reset-db
```
- `--reset-db`
removes any existing databases under `/var/lib/mqttplot` before starting.

Use with caution.
---
### Configuration

After Installation, edit the environment file created by the installer.
```
sudo nano /etc/mqttplot/mqttplot.env
```

Typical contents:
```
MQTTPLOT_MQTT_HOST=localhost
MQTTPLOT_MQTT_PORT=1883
MQTTPLOT_MQTT_USERNAME=
MQTTPLOT_MQTT_PASSWORD=

MQTTPLOT_DB_ROOT=/var/lib/mqttplot
MQTTPLOT_LOG_LEVEL=INFO

# Admin protection (project-specific)
MQTTPLOT_ADMIN_SECRET=changeme
```
---

### Service Control

#### Start / Stop (systemd)
```
sudo systemctl start mqttplot
sudo systemctl stop mqttplot
sudo systemctl status mqttplot
```

#### Enable at Boot
```
sudo systemctl enable mqttplot
```

---

### Logs

Log are available via `journalctl`:
```
sudo journalctl -u mqttplot -f
```


---
### Uninstall

To remove MQTTPlot installed via the installer:
```
sudo ./uninstall_service.sh
```
#### Uninstall Options
```
sudo ./uninstall_service.sh --purge-data
sudo ./uninstall_service.sh --remove-user
```
- `--purge-data`
Deletes `/var/lib/mqttplot` (all stored data)
- `--remove-user`
Removes the `mqttplot` system user

#### By default:
- Data is preserved
- The service user is retained.

---

### Manual / Development Mode (Optional)

For development or testing without system installation, MQTTPlot can still be run directly via Python. See app.py and inline comments for details.

Production deployments should use the service installer.


## Embedded Plots
Public plots can be embedded using an iframe:

```
<iframe
  src="https://yourhost/plot/water-tank-level"
  width="100%"
  height="420"
  frameborder="0">
</iframe>
```

Recommendations:
- Use a fixed height for stable dashboard layouts.
- Prefer a reverse proxy (nginx/Caddy) for TLS termination in production.

## Operational Notes
### Storage Layout

MQTTPlot persists data under the configured MQTTPLOT_DB_ROOT directory. Typically:
- One SQLite database per topic (or per logical channel), depending on configuration.
- Schema is created automatically if missing.

#### Performance
- Plot routes query by time window.
- Multi-topic plots issue one query per series (unless optimized in your build).
- For high-frequency sensors, plan for retention/downsampling in a future release.

### Security Model
- MQTT credentials are server-side only; never returned to clients.
- Public endpoints are strictly read-only.
- Admin endpoints are protected and should not be exposed without authentication controls.
- Slugs are the only public identifiers; internal topic names remain private.

##  Versioning

MQTTPlot follows semantic versioning:

- 0.6.x – Single-topic plots, admin-centric UI
- 0.7.0 – Public slugs, multi-topic plots, embedding
- 0.8.x (planned) – Auth, dashboards, retention policies
