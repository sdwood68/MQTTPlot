# Changelog

All notable changes to MQTTPlot are documented in this file.

The format is based on Keep a Changelog and follows semantic versioning.

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
