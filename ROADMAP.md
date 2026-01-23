# MQTTPlot Roadmap

This document outlines the planned evolution of MQTTPlot following the 0.7.0 release.
It reflects the architectural separation introduced in 0.7.0 between **ingestion,
configuration (admin)**, and **public presentation (slug-based plots)**.

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
- Dual Y-axis support with aligned major units
- Plot preview thumbnails
- In-plot navigation and control widgets
- Decoupling of plot definitions from MQTT topic names
- Safe embedding via iframe for dashboards and wall displays

---

## Planned

### 0.7.1 - Bug Fixes, minor tweak to graphs
- Plot time spans are not adhereing to the 2, 4, 8, 12 hour, 1, 3, 5 day, 1, 2, 4 weeks with 4 ours as the default. 
- pressing the forward keeps zooming when you reach the lastest sample date instead of just stopping. It should not change the time span.
- remove the plotly pop-up controlls for the graph 
- remove the redundant plot start and stop date times

### 0.7.2 - Minor UI and scalling tweek to graphs
- Add a 'Live' indicator when the plot is at the tail/end and is following the tail.
- Display the time span to the right on the Zoom buttons
- Remove the redundant plot title as it is the same as the one on the same row as the control buttons.
- Fix the back button. If the data set is less than the window size it should do nothing.
- Remove the Broker address from the public page


### 0.8.0 — Admin User Interface
Focus: **Admin Interface Improvements**
- hierarchical topics table
  - List the Root Topic and its Subtopics.
  - Root Topic Row: 
    - Retension policy for that Root Topic; Max age. Max rows, ave button 
  - Subtopic rows: 
    - Display the number of messages
    - Remove the public visibility checkbox, we will migrate to just display plots configure with slugs.
    - Data Validation Limits:
      - Entries should display 'Min Value' and 'Max Value' when no data is in them.
      - Entries should be limited to 10 characters each to reduce size.
      - Data Validation should be automatic if there is an entry.
      - Delete Button. No functional change.
    - Add units’ dropdown to include
      - Distance; meter or feet and inches
      - Temperature; Fahrenheit or Celsius
      - Voltage
      - Other
    - Add minimum y-axis tick size.
    - Y-axis tickes need to be hole sizes of the minimum tick size. If min tick size is 1 then tick labels should should be rounded to the min tick size.
- Plot Data:
  - remove the From [ISO time or epoch] field
  - Plot control buttons should only be shown when there is a plot displayed. 
- Time Zone
  - Add time zone setting in admin mode
  - Displayed times should be to local time zone
- Add broker configuration to the admin page
should be in feet and inches with no decimals

### 0.8.1 — Dashboards & Access Control
Focus: **composition and controlled sharing**
- Multi-plot dashboards (grid and vertical layouts)
- Dashboard-level slugs
- Optional authentication layer
- Per-plot and per-dashboard access controls
- Configurable auto-refresh intervals

---

### 0.9.x — Data Management & Scale
Focus: **long-term operation and performance**

- Retention policies (per topic / per plot)
- Automatic downsampling and aggregation
- Database compaction and maintenance tools
- Export utilities (CSV, JSON)
- Storage statistics and health reporting

---

### 1.0.0 — Stable Platform
Focus: **API stability and production readiness**

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
- Real-time control or actuation of devices
- MQTT broker management
- Heavy analytics, ML, or forecasting workloads
