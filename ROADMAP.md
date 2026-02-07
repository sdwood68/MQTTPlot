# MQTTPlot Roadmap

This document outlines the planned evolution of MQTTPlot following the 0.8.x releases.

---

## Released

### 0.6.x — Foundation

- MQTT topic subscription and ingestion
- Persistent SQLite storage
- Single-topic plots
- Admin-centric UI
- Manual topic configuration
- Time-window navigation controls

### 0.7.0 — Public Visualization Layer

- Slug-based public plot URLs
- Strict separation of admin and public views
- Read-only public plot rendering
- Multi-topic plots (multiple series per chart)
- Dual Y-axis support
- In-plot navigation controls
- Safe embedding via iframe for dashboards and wall displays

### 0.7.2 — Public Plot UX Improvements

- Live indicator when the plot is pinned to the latest sample
- Zoom buttons display the current time-window span
- Public endpoint for per-topic bounds for published plots
- Removed redundant Plotly title on public plot pages
- Back button clamping when dataset is smaller than the selected window

### 0.8.0 — Admin UI and Unified Plot System

- Hierarchical topics table (Root/Subtopic)
  - Root rows: retention policy controls
  - Subtopic rows: message counts, validation limits, units dropdown, and Min Tick
  - Root-level delete action
- Admin settings: time zone and broker configuration
- Unified plot layout and controller shared across:
  - Public slug plots
  - Admin slug preview popup
  - Admin single-topic popup
- Plot control bar standardized (Back/Forward, Zoom In/Out, window-span label,
Live indicator)
- Y-axis tick enforcement based on Min Tick (including LCM alignment for
two-topic axes)

### 0.8.1 — Admin Page Cleanup

- Move the app title “MQTTPlot” to the center of the floating banner with:
  - connection status
  - “Admin: \<user\> Logout”
- Rename “Admin Settings” to “Broker Settings”
- Broker Settings layout:
  - Row 1: show current timezone; timezone control becomes a dropdown selector
  - Row 2: show current broker host (URL/IP) and port, followed by editable
  host + port fields
    - Host entry supports both IP addresses and URLs
- Remove “Admin Mode Enable” (self-evident)
- Topics table:
  - Root topic display reflects the actual topic name (do not automatically
  insert a leading “/”)
  - Change units:
    - “Distance (ft/in)” → “feet”
    - “Distance (m)” → “meters”
  - Never store the “ota” subtopic (control channel for device)
- Consolidate CSS inline styles into mqttplot.css
- Re-layout Topics UI:
  - Move current topic values from row 2 to row 3
  - Move Topics entry to row 4 and extend its length by two

---

### 0.8.2 — Version Display + Reduced Polling

- Display the app version next to “MQTTPlot” in the banner (e.g., “MQTTPlot v0.8.2”)

- Polling policy (support 10–20 concurrent clients)
  - Admin mode: poll message counts every 15 seconds even when no plot is displayed
  - Plot pages (admin and public): poll every 15 seconds **only when “Live” is active**

- Diagnostics (development)
  - Ensure the Flask/Werkzeug debug reloader does not start the MQTT client twice
    (prevents duplicate RX logs and duplicate ingestion during debug)

## Planned

### 0.9.x — MQTT JSON Data Payloads

- Add support for receiving MQTT data as a JSON payload that includes:
  - value
  - units
- Automatically assign plot units from the JSON payload when specified

### 0.10.x — Data Management and Scale

- Admin Page
  - Add a checkbox per subtopic to ignore incoming data (stop storing when checked)
  - Add a root-level setting: Max Messages per Hour (per subtopic)
- Add protection against message flooding:
  - If message rate exceeds Max Messages per Hour, automatically set “ignore
  incoming data”
  - Example: if set to 45/hour and 46 messages arrive within 15 minutes, trigger
  protection
- Drop any data points that fall outside the per-topic min/max limits

### 0.11.x — Small Plot Preview Windows

- Create a plot preview that is ~50% smaller than the normal plot
- The slug links to the plot preview
- Preview shows the latest two hours
- Preview updates as new data arrives
- Preview has no plot controls
- Clicking the preview opens a popup window with the full plot (with controls)

## Focus: long-term operation and performance

### Dashboards and Access Control

Focus: composition and controlled sharing

- Multi-plot dashboards (grid and vertical layouts)
- Dashboard-level slugs
- Optional authentication layer
- Per-plot and per-dashboard access controls
- Configurable auto-refresh intervals
- Retention policies (per topic / per plot)
- Automatic downsampling and aggregation
- Database compaction and maintenance tools
- Export utilities (CSV, JSON)
- Storage statistics and health reporting

### 1.0.0 — Stable Platform

Focus: API stability and production readiness

- Stable REST API for plots and metadata
- Backward compatibility guarantees
- Formal plugin/extension hooks
- Production deployment documentation
- Reference systemd and container configurations

---

## Under Consideration

- WebSocket or SSE-based live updates
- Prometheus-compatible metrics export
- Alert thresholds and annotations
- Mobile-optimized public views
- Theme and branding customization
- Plot templates for common sensor types

---

## Non-Goals

- Full MQTT broker management (MQTTPlot assumes an external broker)
