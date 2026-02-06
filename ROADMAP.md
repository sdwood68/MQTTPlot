# MQTTPlot Roadmap

This document outlines the planned evolution of MQTTPlot following the 0.8.0 release.

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

---

## Planned

### 0.8.1 — Admin Page Clean-up

- Move the app title 'MQTTPlot' to the senter of the floating bannor with the
connection status and Admin: admin Logout
- rename the 'Admin Settings' to Broker Settings
- In the 'Broker Settings' on row 1 show the cuurent timezone and then the
Timezone Entry box should be a pull down menue to select the timezone.
- In the 'Broker Settings' on row 2 show the current host URL/IP address and
port Followed by the host entry and port. Host entry should support Ip address
and URLs
- Remove the 'Admin Mode Enable' that is self evident.
- Under 'Topics'
  - The root topic has a forward slach in fron of it, but the root topic does
  not use the '/'. Make sure it reflect the actual topic name and does not
  automaticly insert '/' if it is not used.
  - Change units 'Distance (ft/in)' to just 'feet'
  - Change units 'Distance (m)' to just 'meters'
- Never Store the subtopic 'ota' That is a controll channel for the device.
- Consolidate css inline styles into mqttplot.css
- Move the current Topic's values from row 2 to row 3
- Move teh topics Topics' entry to two 4 and extend its length by two.

### 0.8.2 - Small plot preview

- create a plot preview that is 50% smaller than the normal plot.
  - The slug will link to the plot preview.
  - The plot preview shows the lastest two hours.
  - It update as new data comes in.
  - It does not have plot controlls
  - clicking on it opens a pop-up window with the full plot with controls.  

### 0.8.3 - Ignore Topics, Flooding and bad data

- On the Admin Page
  - Add a check box per subtopic to ignore incoming data. When checked the app
  will stop storing data.
  - Add an entry at the top level topic for Max Maessages per hour per subtopic.
- Add protection form excessive message flooding. If the messaage rate is
greater than than the Max Messages per hour. Than set the ignore incoming data
check box for the subtopic that is exceding the rate and stop storing the data.
Example if it is set to 45 messages per hour and if I get 46 messages within 15
miniute it will trigger protection.
- drop any data points that fall outside of the min / max limits set for the
topic.

### 0.8.4 - MQTT Jason Data Payloads

- Add support for reveciving MQTT data with Jason load that includes the value
and units for the data received.
- Automaticly assignment plot units from the the Jason data if specified.

### Dashboards and Access Control

Focus: composition and controlled sharing

- Multi-plot dashboards (grid and vertical layouts)
- Dashboard-level slugs
- Optional authentication layer
- Per-plot and per-dashboard access controls
- Configurable auto-refresh intervals

### 0.9.x — Data Management and Scale

Focus: long-term operation and performance

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
