# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Changed
- Shifted project messaging to **CLI-first**; GUI and REST API are documented as experimental.
- README now has an explicit support-status section, dependency diagnostics, clearer Windows install guidance, and a local-only warning for the experimental API path.
- Added a minimal `CONTRIBUTING.md` describing the CLI-first maintenance policy.
- Added `RELEASE_CHECKLIST.md` for pre-release sanity checks.
- CI now installs the package itself and runs `compileall` before offline tests.
- GitHub Action argument handling now uses a bash array instead of string-concatenated shell arguments.
- Added subprocess-based CLI smoke tests for help/version/cache/dry-run/preview/overwrite/lang/engine/subs-mode flows.

### Fixed
- Replaced hard-coded `python3` subprocess invocations with the current interpreter for better cross-platform support.
- Made terminal restore logic tolerant of platforms without `termios`.
- Prevented silent truncation of long multi-part TTS lines when concat fails.
- Made subtitle extraction degrade more gracefully when `ffprobe`/`ffmpeg` is unavailable by falling back to nearby sidecar `.srt` files.
- Restored missing Namespace fields (`preset`, `overwrite`) for experimental GUI/WebUI adapters.
- Added an explicit MIT `LICENSE` file to the repository.
