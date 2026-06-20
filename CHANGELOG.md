# Changelog

## 0.1.0

### Added
- Added `rusa --doctor` for local dependency and environment diagnostics.
- Simplified the Docker image so it installs the current CLI package directly.

### Changed
- Repositioned the project as a CLI-first tool.
- Translated the main user-facing CLI layer and documentation toward simple English.
- Simplified the README and release documentation.
- Downgraded the development version from `1.0.0` to `0.1.0` before public release.
- Expanded CI to include Linux offline tests, cross-platform CLI smoke tests, package build checks, Docker smoke checks, and lightweight linting.

### Fixed
- Replaced hard-coded `python3` subprocess calls with the current Python interpreter.
- Made terminal restore logic tolerant of platforms without `termios`.
- Prevented silent truncation of long multi-part TTS output when concat fails.
- Improved subtitle extraction fallback when `ffprobe` is unavailable.
- Removed the last user-facing Russian strings from the core CLI flow.

### Removed
- Removed GUI and WebUI code from the project.
- Removed GUI and WebUI tests and packaging hooks.
