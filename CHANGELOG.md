# Changelog

## 0.8.0.6

### Fixed
- Plots: when **Min Tick** is defined, the y-axis now guarantees at least **two tick intervals** are visible by enforcing a deterministic linear axis (`tickmode=linear`, `tick0` aligned to range start) and a minimum y-range of `2 * Min Tick`. This prevents near-flat data (e.g., 69–70 with Min Tick=1) from collapsing to a single tick line.

## 0.8.0.5

### Changed
- Plots: when a topic defines **Min Tick**, the y-axis is forced to span at least **2 divisions** (≥ `2 * Min Tick`), even when values are flat or nearly flat.

## 0.8.0.4

### Fixed
- Admin Topics table regression: restored table rendering (0.8.0.3 had a broken `topics_ui.js` that prevented the table from loading).

### Changed
- Subtopic **Configuration** cell layout: Min/Max on the first line; Units + Min Tick on the second line; Save button on the right spanning both lines.

## 0.8.0.3

- Admin Topics table: subtopic Configuration cell now uses a 2-line layout (Min/Max on first line, Units + Min Tick on second) with Save button to the right spanning both lines.

All notable changes to MQTTPlot are documented in this file.

The format is based on Keep a Changelog and follows semantic versioning.

---

## [0.8.0.2] - 2026-01-24

### Changed
- Admin Topics table: consolidated the 3rd column into **Configuration** (root rows show retention controls; subtopic rows show validation/units/min-tick controls).

### Added
- Root-level **Delete** button: deletes the root topic and all subtopic data via `/api/admin/root/<root>`.

## [0.8.0.1] - 2026-01-24

### Fixed
- Flask startup crash: removed duplicate route definition for `/api/admin/topic_meta` (duplicate endpoint function name `api_admin_topic_meta`).

## 0.8.0
- Admin UI: hierarchical root/subtopic topics table
- Root-topic retention controls integrated into the topics table
- Admin settings: configurable time zone and MQTT broker (host/port/topics)
- Plot controls only render when a plot is displayed; window span shown between zoom buttons
- Topic settings: validation placeholders/limits, units dropdown, minimum y-axis tick size
- Times returned with timezone offsets based on admin time zone setting

## [0.7.2.1] - 2026-01-23

### Changed
- Public plot zoom controls: the current window span is now displayed between the Zoom In/Zoom Out buttons, and each button label shows the span that will be applied if clicked.

---

## [0.7.2] - 2026-01-23

### Added
- Public plot "Live" indicator shown when the view is pinned to the latest sample.
- Public endpoint to retrieve per-topic time bounds for published plots (`/api/public/bounds`) to support navigation clamping.

### Changed
- Zoom buttons now display the current time-window span.
- Plotly chart title removed on public plot pages (title is shown in the fixed top bar).

### Fixed
- Back button on public plots: when the dataset is smaller than the selected window (or already at the earliest sample), Back does nothing.

### Removed
- Broker address from the non-admin landing page.

## [0.7.1.1] - 2026-01-23

- Fix: Repair JavaScript syntax error in admin multi-topic preview module (`plot_multi.js`) that prevented admin topics list from loading.

## [0.7.1] – 2026-01-23

### Fixed
- Enforced fixed time-span presets (2/4/8/12 hours; 1/3/5 days; 1/2/4 weeks) and removed span drift during navigation.
- Clamped forward navigation to the latest available sample (no creeping past the tail).
- When the plot window end is at the latest sample, it now remains pinned to the latest sample as new data arrives (without changing the selected span).

### Changed
- Back/Forward navigation now slides by one full window span.
- Plotly mode bar (popup controls) disabled for both public plots and admin preview plots.

### Removed
- Redundant public plot start/end range display.

---

## [0.7.0] – 2026-01-XX

### Added
- Slug-based public plot URLs
- Read-only public plot rendering
- Multi-topic plot support (multiple series per plot)
- Embeddable plots suitable for iframes
- Plot preview thumbnails
- In-plot navigation and control widgets

### Changed
- JavaScript restructured to support multi-series plots
- HTML templates separated for admin vs public rendering
- Plot definitions decoupled from MQTT topic names
- Dual Y-axis major unit alignment improved
- Clear separation between ingestion, configuration, and presentation layers

### Removed
- Implicit assumption of one topic per plot
- Exposure of MQTT topic names in public-facing views
- Leakage of internal configuration details to anonymous users

### Security
- Public routes are strictly read-only
- MQTT credentials remain server-side only
- Admin-only functionality isolated from public endpoints

---

## [0.6.2]
### Changed
- Code cleanup and module reorganization
- Logging improvements
- Minor UI consistency fixes

---

## [0.6.1]
### Fixed
- MQTT reconnect handling edge cases
- Minor persistence issues during broker restarts

---

## [0.6.0]
### Added
- Time-window navigation controls
- Plot interaction buttons
- Initial admin UI improvements

---

## [0.5.x]
### Added
- Initial MQTT ingestion pipeline
- SQLite-based time-series persistence
- Basic Plotly visualization