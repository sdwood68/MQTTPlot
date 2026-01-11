# Changelog

All notable changes to this project will be documented in this file.

## [0.6.2] - 2026-01-09
### Added
- Maintenance milestone: 0.6.2 “Code cleaning / review / reorganization”
- Python package structure introduced under `mqttplot/` (incremental refactor; legacy entrypoint retained)

### Changed
- Phase 1 refactor: extracted persistence layer to `mqttplot/storage.py` and MQTT worker to `mqttplot/mqtt_client.py`
- Root `app.py` now acts as a compatibility wrapper that calls `mqttplot.app.main()`
- Documentation refresh: ROADMAP status annotations and README roadmap overview

### Notes
- 0.6.2 is intended as a maintenance-focused release to improve structure, clarity, and testability without changing user-facing behavior.

## [0.6.1] - 2026-01-08
### Added
- Interactive plot window navigation controls (zoom in/out, slide forward/backward)
- Persistent SQLite storage organized per top-level MQTT topic

### Changed
- Service scripts and operational hardening (install/uninstall, systemd service)
- Improved guardrails and retention handling (best-effort enforcement)

### Known Issues
- Pre-1.0 API stability
- Limited MQTT payload validation


## [0.5.0] - 2026-01-03
### Added
- Initial tagged baseline release
- Core MQTT ingestion and plotting functionality

### Changed
- Code organization and internal structure cleanup

### Known Issues
- Pre-1.0 API stability
- Limited MQTT payload validation
