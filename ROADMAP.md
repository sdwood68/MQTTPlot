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
- Plot control bar standardized (Back/Forward, Zoom In/Out, window-span label, Live indicator)
- Y-axis tick enforcement based on Min Tick (including LCM alignment for two-topic axes)

---

## Planned

### 0.8.1 — Dashboards and Access Control
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
