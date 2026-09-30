## Unreleased

### Fixed
- Stabilize CI lint across Ruff releases by selecting the intended rules and
  pinning the CI version.
- Detect KOI8-R Russian subtitles correctly when optional charset detection
  packages are unavailable, including uppercase text.
- Avoid false "voiceover packets are not interleaved" failures on long videos with
  distant keyframes. Probe a wider interval and compare packets nearest the
  requested playback time.
- Preserve all original video, audio, subtitle, attachment, and data streams when muxing. Subtitle `auto` now fails clearly when preservation is impossible; only `--subs-mode drop` removes subtitles.
- Check AV1 stream-copy packets before TTS, including large source files, and verify voiceover interleaving at several points in the film.
- Fix preset detection so `-o` no longer overrides the preset original-audio volume.
- Reject malformed speed and user configuration values with setting-specific errors.
- Preflight temporary disk space and assemble long voiceovers as RF64 when RIFF WAV would overflow.
- Use scoped OIDC Trusted Publishing in release CI and run full Ruff checks.
- Bundle default and engine YAML configuration in the wheel so installed releases
  can resolve audio codecs and built-in engines outside the source checkout.
- Allow `rusa_engines` to be imported before `rusa_shared` without a circular
  import failure.
- Pass GitHub Action inputs through environment variables so shell metacharacters
  in input paths cannot alter the action's Bash script.
- Install rusa from the GitHub Action's checked-out revision instead of fetching
  a potentially older PyPI release.
- Embedded Russian subtitle streams encoded in legacy single-byte encodings
  (Windows-1251 / cp866 / KOI8-R) are now extracted correctly. ffmpeg is retried
  with `-sub_charenc`, and the ffmpeg error is surfaced when a stream still
  cannot be converted to text (e.g. bitmap/PGS subtitles).
- Read legacy-encoded `.srt` files (e.g. cp1251) without crashing: subtitle
  files are detected as UTF-8 first, then via chardet / charset_normalizer, and
  normalized to UTF-8 before parsing and muxing.

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
