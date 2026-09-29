# rusa Roadmap

## Current direction

rusa is maintained as a **CLI-first** project.

Current priorities:

1. core pipeline correctness
2. simple English CLI UX
3. tests and regressions
4. documentation and packaging
5. release discipline

## Completed foundations

- CLI pipeline
- subtitle extraction and sync support
- TTS backend abstraction
- WAV cache and TTS cache
- timing summary
- output codec selection
- subtitle handling modes (`auto`, `copy`, `convert`, `drop`)
- Docker support
- GitHub Action support
- subprocess-based CLI smoke tests
- **all defaults extracted into `rusa_data/defaults.yaml`** — users can override them via `~/.config/rusa/config.yaml`
- **auto-fit TTS speed per subtitle line** (`--speed auto[:max=N][:min=M]`) — each segment accelerated just enough to fit its timeslot

## Current technical debt

- continue simplifying user-facing output into plain English
- keep README examples aligned with real CLI behavior
- keep cross-platform behavior stable
- keep fixture-dependent integration tests separate from fast offline checks

## Audit backlog (2026-09-29)

### Critical: release correctness

- [x] Ship `defaults.yaml` and `engines.yaml` inside the wheel. Test the installed wheel from outside the checkout and assert that codecs and bundled engines load. A wheel without defaults has an empty codec map and cannot process a video.
- [x] Remove the circular import between `rusa_shared` and `rusa_engines` found by the isolated wheel smoke test; both import orders must register bundled engines.

### High: media correctness and CI security

- [x] Preserve every source stream by default. Map all source video, audio, subtitle, attachment, and data streams; fail if a stream cannot be kept. Subtitle removal requires `--subs-mode drop`.
- [x] Pass composite GitHub Action inputs through environment variables instead of interpolating expressions directly into Bash. Test paths containing shell metacharacters.
- [x] Install the action's own checked-out revision instead of an unrelated PyPI release, so its workflow exercises the matching code.
- [x] Redesign AV1 copy preflight before TTS. Validate video packet count and the first five seconds of packet timestamps; test a source larger than 50 MiB.

### Medium: reliability and usability

- [x] Exercise muxing with long video and sparse subtitles, and measure peak memory with `-max_interleave_delta 0`. Check voiceover packet placement at several timestamps rather than only one point.
- [x] Fix preset flag detection: `-o` no longer counts as an explicit `orig_vol` option; exact-argument tests cover the precedence.
- [x] Validate user configuration and `--speed` values with actionable errors, including malformed auto-speed settings.
- [x] Preflight temporary disk space for long films and use RF64 when assembled PCM exceeds the 32-bit WAV size limit.
- [x] Expand installed-wheel CI smoke beyond `--version` and `--help` with an offline processing check.
- [x] Keep the changelog aligned with these fixes and require an update in the release checklist.
- [x] Replace the long-lived PyPI API token in release CI with a job-scoped OIDC Trusted Publisher workflow. PyPI account-side publisher configuration remains a release setup step.

### Low: maintenance

- [x] Address the existing full-Ruff findings and run the complete default Ruff check in CI.

## Nice-to-have later

- broader engine examples and tuning guides
- more real-world CLI smoke scenarios
- optional packaging polish for public release
- incremental regeneration of individual subtitle entries (`--remake 5,8-12` / `--remake-failed`)
- export per-entry WAV segments for manual replacement, then reassemble (`--export-wavs DIR` / `--import-wavs DIR --reassemble`)

## Out of focus for now

- GUI layers
- REST API layers
- hosted service features
- billing or account features
