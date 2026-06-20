# rusa — AI Voiceover for Movies

[![PyPI version](https://img.shields.io/pypi/v/rusa.svg)](https://pypi.org/project/rusa/)

**rusa** is a CLI tool that creates a translated voiceover track from subtitles and mixes it into a video or exports audio-only output.

## Project status

- **Primary interface:** CLI only
- **Current focus:** core pipeline, CLI UX, tests, docs, packaging
- **Best-tested environment:** Linux/macOS with `ffmpeg` and `ffprobe` in `PATH`
- **Windows:** best-effort support; use `py -m pip install rusa` and make sure `ffmpeg.exe` is in `PATH`

---

## Quick start

### Install

```bash
# Linux / macOS
pip install rusa
sudo apt install ffmpeg       # or: brew install ffmpeg

# Windows
py -m pip install rusa
# Download ffmpeg.exe from https://ffmpeg.org and add it to PATH
```

### Run

```bash
rusa movie.mkv
```

By default, rusa writes the result next to the source file, for example:

```text
movie_edge-tts_ru.mkv
```


### Quick health check

```bash
rusa --doctor
```

This prints a short report about:
- Python interpreter
- platform and console encoding
- `ffmpeg` / `ffprobe`
- `edge-tts`
- available TTS engines
- cache directory

---

## Common examples

```bash
# Basic run
rusa movie.mkv

# Use an external subtitle file
rusa -s subs.srt movie.mkv

# Choose subtitle language explicitly
rusa --lang he movie.mkv

# Use a specific voice
rusa --voice ru-RU-DmitryNeural movie.mkv

# Audio only
rusa --mp3 128 --audio-only movie.mkv

# Preview only the first 10 subtitle lines
rusa --preview 10 --dry-run movie.mkv

# Higher quality output for YouTube-style upload
rusa --preset youtube movie.mkv
```

---

## How it works

1. Load subtitles from the video or an external `.srt` file
2. Optionally synchronize them with `alass`
3. Generate TTS audio per subtitle line
4. Convert TTS output to WAV and trim silence
5. Assemble all subtitle segments into one voiceover track
6. Mix the voiceover with the original audio
7. Encode the final output

---

## CLI options

| Flag | Meaning | Default |
| --- | --- | --- |
| `video` | Input video file | required |
| `-o, --output FILE` | Output file path | auto-generated |
| `-s, --srt FILE` | External subtitle file | auto-detect / extract |
| `--voice [VOICE]` | TTS voice; without value, list voices | auto |
| `--lang LANG` | Subtitle language code | auto |
| `--speed SPEED` | TTS speech speed | `1.5` |
| `--orig-vol VOL` | Original audio volume | `0.65` |
| `--tts-vol VOL` | Voiceover volume | `0.93` |
| `--sync` | Synchronize subtitles with `alass` | off |
| `--keep-temp` | Keep temporary files | off |
| `--threads N` | TTS worker count | `6` |
| `--cache-stats` | Show cache statistics and exit | off |
| `--cache-clear` | Clear cache and exit | off |
| `--no-cache` | Disable cache for this run | off |
| `--dry-run` | Print plan only | off |
| `--preview N` | Process only first `N` subtitle lines | off |
| `--overwrite` | Overwrite existing output file | off |
| `--aac [BITRATE]` | Encode as AAC | off |
| `--mp3 [BITRATE]` | Encode as MP3 | off |
| `--opus [BITRATE]` | Encode as Opus | default codec |
| `--ac3 [BITRATE]` | Encode as AC3 | off |
| `--from N` | First subtitle index | all |
| `--to N` | Last subtitle index | all |
| `--audio-only` | Write audio output only | off |
| `--engine ENGINE` | TTS engine | `edge` |
| `--tts-cmd TEMPLATE` | Custom TTS command template | off |
| `--subs-mode MODE` | Subtitle handling: `auto`, `copy`, `convert`, `drop` | `auto` |
| `--normalize [fast\|fine]` | Normalize output loudness | off |
| `--preset NAME` | Quality preset: `youtube`, `tiktok`, `podcast`, `cinema` | off |
| `--doctor` | Check local runtime dependencies and environment, then exit | off |
| `--version` | Show version and exit | — |

---
## Docker

```bash
docker build -t rusa .
docker run --rm rusa --help
```

For real processing, mount a directory with your media files:

```bash
docker run --rm -v $(pwd):/data rusa movie.mkv
```


## Built-in TTS engines

| Engine | Online | Typical quality | Notes |
| --- | --- | --- | --- |
| `edge` | yes | good | default engine |
| `piper` | no | good | local neural TTS |
| `rhvoice` | no | average | local voices |
| `espeak` | no | basic | very fast |
| `gtts` | yes | good | simple cloud TTS |
| `festival` | no | basic | legacy local TTS |

You can also use any custom engine with `--tts-cmd`.

More details:
- [doc/TTS_ENGINES.md](doc/TTS_ENGINES.md)
- [doc/LANGUAGE_RECOMMENDATIONS.md](doc/LANGUAGE_RECOMMENDATIONS.md)

---

## Output modes

| Mode | Result |
| --- | --- |
| default | video + original audio + voiceover |
| `--audio-only` | audio file only |
| `--subs-mode auto` | try copy, then convert, then drop subtitles if needed |
| `--subs-mode copy` | keep subtitles as-is or fail |
| `--subs-mode convert` | convert subtitles to a compatible text format |
| `--subs-mode drop` | write output without subtitles |

---

## Cache

rusa uses two caches:

- **TTS cache**: generated speech files
- **WAV cache**: converted WAV files after speed change and silence trim

Defaults:

- cache root: `~/.cache/rusa`
- max size: `2 GiB`

Environment variables:

| Variable | Meaning | Default |
| --- | --- | --- |
| `RUSA_CACHE_DIR` | Cache root directory | `~/.cache/rusa` |
| `RUSA_CACHE_MAX_SIZE` | Max cache size in bytes | `2147483648` |

Commands:

```bash
rusa --cache-stats
rusa --cache-clear
rusa --no-cache movie.mkv
```

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | runtime error |
| `2` | usage error |
| `3` | missing dependency |
| `4` | subtitle error |
| `5` | codec / encoder error |

---

## Tests

```bash
# Offline tests
pytest -q -m 'not slow and not live_tts'

# Fast CLI smoke tests
pytest -q tests/test_cli_smoke.py

# Live tests (network access required for edge-tts)
pytest -q -m 'live_tts and not slow'

# Full suite
pytest -q

# Force local fixture generation (requires ffmpeg)
pytest -q --generate-fixtures
```

If generated fixtures are missing and `ffmpeg` is unavailable, unit and smoke tests still run. Only fixture-dependent integration tests are affected.

---

## Diagnostics

### Missing dependencies

If you see one of these errors:

- `ffmpeg was not found in PATH`
- `ffprobe was not found in PATH`
- `edge-tts is not installed`

check that:

1. `ffmpeg` and `ffprobe` are installed and available in `PATH`
2. `edge-tts` is installed in the same Python environment as `rusa`
3. on Windows, `ffmpeg.exe` is in `PATH`

### Subtitle codec error

If you see something like:

```text
Subtitle codec mov_text ... is not supported
```

then:

- `--subs-mode auto` will try fallback modes automatically
- `--subs-mode copy` fails early
- `--subs-mode convert` writes a compatible text subtitle format directly
- `--subs-mode drop` writes the file without subtitles

---

## Development and release docs

- [doc/roadmap.md](doc/roadmap.md)
- [doc/implementation_plan.md](doc/implementation_plan.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

---

## License

MIT

---

## README contract

This README is the behavioral contract for the project.

If code and documentation diverge, update the README together with the code change.
