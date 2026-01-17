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

### 0.8.x — Dashboards & Access Control
Focus: **composition and controlled sharing**

- Multi-plot dashboards (grid and vertical layouts)
- Dashboard-level slugs
- Optional authentication layer
- Per-plot and per-dashboard access controls
- Configurable auto-refresh intervals
- Admin UI improvements for plot grouping

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
