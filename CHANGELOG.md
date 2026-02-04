# Changelog

## 0.8.1 - Admin Page Clean-up

- Top bar: move the app title to the center of the floating banner
(between MQTT status and Admin logout).
- Rename **Admin Settings** to **Broker Settings**.
- Broker Settings UI now shows current time zone and broker host/port/topics,
with a time zone dropdown selector.
- Remove the redundant "Admin Mode Enabled" banner.
- Topics table: root rows no longer display an auto-inserted leading `/`; root
labels now reflect the actual topic root name.
- Units dropdown: rename "Distance (ft/in)" → "feet" and "Distance (m)" → "meters".
- Ingestion: ignore device OTA control topics (any topic segment named `ota`).
- Styling: consolidate common inline admin styles into `static/mqttplot.css`.

## 0.8.0.2 - Bug Fixes

- Fix admin Topics auto-refresh: subtopic counts now update correctly by using
stable row references (no selector escaping issues).
- Restore live topic counts refresh without re-rendering the Topics table
(protects all input fields).
- Delete data now resets counts in-place instead of rebuilding the table.
- Admin topic delete now purges messages but keeps the topic visible by resetting
`topic_stats` counters instead of deleting the `topic_stats` row.
- Fix admin topic delete to match per-root SQLite schema (messages keyed by
topic_id; topics table stores topic strings).
- Admin "Delete data" now purges stored messages for a subtopic **without removing
the topic definition** from the topic list.
- Fix Jinja template syntax error in CSRF meta tag rendering.
- Fix admin delete actions by ensuring authenticated session cookies are included
in admin fetch requests and by using JSON-body endpoints for both topic and root
deletes.
- Add CSRF token protection for admin state-changing API calls.
- Installer now persists SECRET_KEY to avoid session invalidation across
multi-process/reloader scenarios.

## 0.8.0.1 - Bug Fixes

- Fix admin delete-data actions by using a POST-based API (avoids encoded-slash
issues and auth confusion).
- Improve ISO time parsing (accepts Z/UTC) and default time zone behavior for fresh
installs.
- Stop auto-refresh on admin pages that resets form inputs; retain auto-updates
only for live plots.
- Fix Dockerfile and document Docker usage in README.
- Update README version intro and remove redundant requirements.

## 0.8.0.10 - Installer + Diagnostics

- Fix `/api/version` to avoid metadata-table dependency (prevents 500 on installs
with older/newer schema).
- Installer now writes `DATA_DB_DIR` to `secret.env` and guards `DB_PATH`
against directory values.
- Add diagnostic logs for plot reads: resolved per-root DB path, time bounds,
and row counts.

## [0.8.0] - 2026-01-25

### Added

- Admin UI: hierarchical **Root/Subtopic** topics table (root retention
controls; subtopic configuration for validation limits, units, and **Min Tick**).
- Admin settings: configurable **time zone** and MQTT broker (host/port/topics).
- Plot system: canonical plot layout shared across public slug plots and admin
plot windows.
- Plot system: unified plot controller supporting **1–2 topics** with dual
Y-axis support.
- Plot controls: Back/Forward, Zoom In/Out, window-span label, and Live indicator.

### Changed

- Admin plotting workflow: removed embedded plot preview; plots open in a
dedicated admin-only window and slug previews open in a popup.
- Public plots: removed redundant Plotly title and broker address from the
public page.

### Fixed

- Flask startup crash caused by a duplicate admin topic-meta route.
- Admin topics table regressions that prevented the table from rendering.
- Plots: enforce deterministic y-axis ticks when **Min Tick** is set (linear
ticks aligned to tick size) and guarantee at least **two tick intervals** are
visible for near-flat data.
- Plots: when two topics share an axis, tick spacing uses the **LCM** of their
configured Min Tick sizes to keep labels aligned.

## [0.7.2.1] - 2026-01-23

- Public plot zoom controls: the current window span is now displayed between
the Zoom In/Zoom Out buttons, and each button label shows the span that will be
applied if clicked.

---

## [0.7.2] - 2026-01-23

### Added

- Public plot "Live" indicator shown when the view is pinned to the latest sample.
- Public endpoint to retrieve per-topic time bounds for published plots
(`/api/public/bounds`) to support navigation clamping.

### Changed

- Zoom buttons now display the current time-window span.
- Plotly chart title removed on public plot pages (title is shown in the fixed
top bar).

### Fixed

- Back button on public plots: when the dataset is smaller than the selected 
window (or already at the earliest sample), Back does nothing.

### Removed

- Broker address from the non-admin landing page.

## [0.7.1.1] - 2026-01-23

- Fix: Repair JavaScript syntax error in admin multi-topic preview module
(`plot_multi.js`) that prevented admin topics list from loading.

## [0.7.1] – 2026-01-23

### Fixed

- Enforced fixed time-span presets (2/4/8/12 hours; 1/3/5 days; 1/2/4 weeks) and
removed span drift during navigation.
- Clamped forward navigation to the latest available sample (no creeping past
the tail).
- When the plot window end is at the latest sample, it now remains pinned to the
latest sample as new data arrives (without changing the selected span).

### Changed

- Back/Forward navigation now slides by one full window span.
- Plotly mode bar (popup controls) disabled for both public plots and admin
preview plots.

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
