## 0.2.0

### Added
- **`--speed auto`** — per-segment auto-speed tuning. Each subtitle is accelerated just enough to fit its timeslot, clamped between `auto_speed.max` (default `1.5`) and `auto_speed.min` (default `0.8`). Use `--speed auto:max=2.0` to set a custom upper limit.
- **`defaults.yaml`** — all default settings moved from Python code into a single YAML file shipped with the package. Users can override any value by creating `~/.config/rusa/config.yaml`.
- **Auto-speed CLI syntax**: `--speed auto`, `--speed auto:max=2.0`, `--speed auto:max=2.0:min=0.7`.

### Changed
- Hardcoded defaults (`DEFAULT_VOICE`, `DEFAULT_SPEED`, `PRESET_MAP`, `CODEC_MAP`, WAV constants, loudnorm params, etc.) externalized into `defaults.yaml`.
- `step_convert_wav` now accepts per-entry speed values (`str | dict[int, float]`) to support auto-speed.
- Silence removal threshold lowered from `0.0018` to `0.0001` — preserves soft-spoken voices (e.g. French neural TTS).
- `edge-tts` stderr is now logged on failure instead of being silently discarded.
- Corrupt WAV files are no longer cached; they return `None` instead of masquerading as zero-duration segments.
- Zero-duration segment skips in assembly are now logged with a warning.

### Fixed
- TTS retry loop now logs the failure reason (return code, timeout, or exception) instead of silent `pass`.
- Multi-part TTS errors also logged per part.
- `step_merge_srt_entries` reads its `max_gap_ms` default from config (was hardcoded `200`).

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
