# MQTTPlot Roadmap

This document outlines planned and aspirational features for MQTTPlot.
Items listed here represent intent, not commitment, and may change as the
project evolves.

---

## 0.6.0 — Interactive Navigation & Persistence

### Interactive Plot Window Control
- Add **four-button control** for navigating the plot time window:
  - **Increase time window** (zoom out)
  - **Decrease time window** (zoom in)
  - **Slide window forward by 50%** of the current window width
  - **Slide window backward by 50%** of the current window width
- Enforce **clear boundary conditions**:
  - Forward/backward sliding stops cleanly at the beginning or end of
    available stored data
  - No wrap-around or ambiguous behavior at data limits
- Ensure controls provide intuitive, predictable interaction suitable for
  real-time monitoring use cases

### Persistent Data Storage by Topic
- Implement **persistent storage** of time-series data
- Storage is organized **per top-level MQTT topic**
  - Example: `/watergauge/*` stored independently from `/weather/*`
- Stored data survives application restart
- Persistence layer designed to support:
  - Efficient time-window queries
  - Future export functionality (CSV, images)
- Define clear limits or policies for:
  - Maximum retained history
  - Disk usage growth

---

## 0.7.0 — Sharing & Embedding

### Embeddable Plot URLs
- Provide **stable URLs** for individual plot windows
- URLs encode or reference:
  - Topic selection
  - Time window size and position
  - Plot configuration (series visibility, scaling, etc.)
- Plots rendered in a form suitable for **embedding in third-party webpages**
  (e.g., `<iframe>` or equivalent)
- Support **read-only access** for embedded views by default
- Ensure embedded plots:
  - Respect data bounds and retention limits
  - Update automatically as new data arrives (where applicable)
- Multiple plt variables

### Access and Safety Considerations
- Define clear separation between:
  - Local/owner views
  - Public or shared embedded views
- Provide configuration options to:
  - Enable Disable topic storage.
  - Enable or disable embedding
  - Restrict which topics are shareable
- Lay groundwork for future authentication or access controls

### Security Improvements
- Black List topics to avoid database size runaway
  - Identify and stop logging runaway topics that exceed:
    - Certain message rate
    - data size
    - Invalid data types
-
---

## Future (Tentative)

### 0.8.x+
- Multiple plot panes or dashboard layouts
- Topic discovery and dynamic subscription management
- Export plots to image and/or CSV
- TLS and authentication support for MQTT brokers
- Optional full web-based UI

---

## Notes
- MQTTPlot is pre-1.0; APIs, configuration formats, and internal structures
  may change without notice.
- Roadmap items may be implemented incrementally across patch releases.
