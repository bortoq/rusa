# rusa — AI Voiceover for Movies

**rusa** is a command-line tool that adds **full voiceover translation** to your video collection in a single command. Point it at a video file — rusa extracts subtitles, generates speech using TTS voices, and mixes it over the original audio.

Ideal for:
- 🎬 **Movies & TV series** — voiceover in any language from existing subtitles
- 🎙️ **Podcasts & lectures** — voiceover translation into any supported language

```bash
# One command — ready result
rusa movie.mkv
```

## Features

- 🎯 **One command** — rusa finds subtitles, generates voiceover, and assembles the final file automatically
- 🔊 **Natural voices** — supports 33+ languages via Microsoft Edge TTS; any TTS engine via `--tts-cmd`
- ✂️ **Smart silence trimming** — leading/trailing silence is removed; speech and inter-phrase pauses stay intact
- 🧩 **Intelligent assembly** — if entries overlap, rusa shifts them forward instead of clipping words
- 🌐 **Auto language detection** — rusa picks the right voice from the subtitle content or filename (`.ru.srt`, `.en.srt`, etc.)
- 🎚️ **Adjustable volume** — set original and TTS volume independently (0.0–1.0) to balance background and voiceover
- 🔄 **Normalization** — loudnorm (fine) or dynaudnorm (fast) for consistent volume across the whole movie
- 🎧 **Any audio codec** — AAC, MP3, Opus, AC3 — your choice
- 🧩 **Split-sentence merging** — broken subtitles (e.g. 1ms gap / lowercase continuation) are automatically merged for natural TTS intonation
- ⚡ **Parallel processing** — TTS generation and WAV conversion run in multiple threads
- ⏱️ **Stage timing summary** — after a successful run, rusa prints elapsed time per stage: subtitles, TTS, WAV, assemble, mux
- 💾 **Persistent cache** — TTS and WAV results are cached; repeated runs reuse cached data and skip network/ffmpeg calls. Automatic LRU eviction when cache exceeds 2 GiB
- 🔐 **Terminal state guard** — saves and restores terminal attributes on exit/signal, preventing corruption
- 🌐 **REST API server** — FastAPI-based processing server with Swagger docs
- 🖥️ **Native GUI** — desktop interface (tkinter) for a native experience

## Quick Start

**Linux / macOS:**

```bash
# Install
pip install rusa
# or from source:
# git clone ... && cd rusa && pip install .

# Make sure ffmpeg is installed
# Linux: apt install ffmpeg   (or brew install ffmpeg on macOS)

# Dub a movie
rusa movie.mkv
```

**Windows (PowerShell):**

```powershell
# Install
pip install rusa

# Make sure ffmpeg.exe is in your PATH (download from ffmpeg.org)

# Dub a movie
python rusa.py movie.mkv
```

The output file is created next to the source: `movie_edge_ru.mkv`.

Dependencies: `ffmpeg` + `ffprobe` (part of ffmpeg), `python3`.
`langdetect` is optional — it improves auto-detection from `.srt` content.

## Options

| Flag                         | Description                           | Default                             |
| ---------------------------- | ------------------------------------- | ----------------------------------- |
| `video`                      | Video file (.mkv, .mp4, .avi, …)      | required                            |
| `-o, --output FILE`          | Output file                           | `<video>_{backend}_{lang}.{ext}`     |
| `-s, --srt FILE`             | External subtitle file (.srt)         | extracted from video / found nearby |
| `--voice VOICE`              | TTS voice name; no arg = list voices  | auto-detected from subtitle language |
| `--lang LANG`                | Subtitle ISO 639-1 code (ru, en, he, de, fr, …) | from --voice / auto |
| `--speed SPEED`              | TTS speech speed                      | `1.5`                              |
| `--orig-vol VOL`             | Original audio volume (0.0–1.0)       | `0.65`                             |
| `--tts-vol VOL`              | TTS voice volume (0.0–1.0)            | `0.93`                             |
| `--sync`                     | Synchronize subtitles via alass       | off                                |
| `--merge-sentences`          | Merge split subtitle entries          | on                                 |
| `--no-merge-sentences`       | Disable sentence merging              | off                                |
| `--keep-temp`                | Keep temporary files                  | off                                |
| `--threads N`                | TTS thread count                      | `6`                                |
| `--cache-stats`              | Show cache statistics and exit        | off                                |
| `--cache-clear`              | Clear all caches and exit             | off                                |
| `--no-cache`                 | Disable cache for this run            | off                                |
| `--dry-run`                  | Show generation plan without running  | off                                |
| `--preview N`                | Generate only the first N subtitles   | off                                |
| `--version`                  | Show version and exit                 | —                                   |
| `--aac [BITRATE]`            | AAC codec (128, 192, …)               | off                                |
| `--mp3 [BITRATE]`            | MP3 codec (128, 192, …)               | off                                |
| `--opus [BITRATE]`           | Opus codec (64, 96, …)                | on (64k default)                   |
| `--ac3 [BITRATE]`            | AC3 codec (448, 640, …)               | off                                |
| `--from N`                   | First subtitle index                  | all                                |
| `--to N`                     | Last subtitle index                   | all                                |
| `--audio-only`               | Audio output only (no video)          | off                                |
| `--engine ENGINE`            | TTS engine (edge, piper, rhvoice, espeak, gtts, festival or custom from `~/.config/rusa/engines.yaml`) | `edge` |
| `--tts-cmd TEMPLATE`         | Custom TTS command (`{in}` `{out}` `{voice}`). Overrides `--engine` | — |
| `--subs-mode {auto,copy,convert,drop}` | Subtitle handling in output video | `auto`                 |
| `--normalize [{fast,fine}]`  | Volume normalization                  | off                                |
| `--webui`                    | Launch REST API server (FastAPI)      | off                                |

## Examples

```bash
# Basic usage
rusa movie.mkv

# Male voice + speed up
rusa --voice ru-RU-DmitryNeural --speed 1.8 movie.mkv

# Hebrew subtitles + Hila voice (auto-detect)
rusa --lang he movie.mkv

# Explicit voice + language
rusa --voice he-IL-HilaNeural --lang he movie.mkv

# External subtitles, double speed
rusa -s subs.srt --speed 2.0 movie.mkv

# AAC 192k with fine normalization, audio only
rusa --aac 192 --normalize fine --audio-only movie.mkv

# Subtitle range + MP3
rusa --from 1 --to 30 --mp3 128 movie.mkv

# Preview first 10 subtitles (dry run)
rusa --preview 10 --dry-run movie.mkv

# Disable sentence merging
rusa --no-merge-sentences movie.mkv

# Subtitle mode: convert to compatible format
rusa --subs-mode convert movie.mkv

# Cache management
rusa --cache-stats
rusa --cache-clear

# One-shot run without cache
rusa --no-cache movie.mkv

# List available voices
rusa --voice

# External subtitles + sync + Opus 96kbps
rusa -s subs.srt --sync --opus 96 movie.mkv

# Dry-run mode (show plan without executing)
rusa --dry-run movie.mkv

# Launch WebUI
rusa --webui
```

## Languages and Voice Quality

rusa is **not** a TTS engine. Voice quality and language support depend entirely on the TTS model you choose.

### Recommendations

For the best results, we recommend:

| Use Case                        | Recommended TTS                    | How to use                |
|--------------------------------|------------------------------------|---------------------------|
| Maximum quality                | Chatterbox, XTTS v2, Fish Speech   | `--tts-cmd`               |
| Good quality + simplicity      | Microsoft Edge TTS (default)       | `--lang`                  |
| High speed                     | Piper, Kokoro                      | `--tts-cmd`               |
| Rare languages                 | Modern open-source models          | `--tts-cmd`               |

See detailed recommendations in:

**[doc/LANGUAGE_RECOMMENDATIONS.md](doc/LANGUAGE_RECOMMENDATIONS.md)**

### Using a Custom TTS

rusa allows you to connect **any** TTS system:

```bash
rusa movie.mkv --tts-cmd "python my_tts.py {in} {out} {voice}"
```

This gives you maximum flexibility and access to the latest models.

## Voices

Current Russian Microsoft Edge TTS voices:

| Voice                  | Quality                       |
| ---------------------- | ----------------------------- |
| `ru-RU-SvetlanaNeural` | Female, neural (default)      |
| `ru-RU-DmitryNeural`   | Male, neural                  |

**33+ languages** are supported. Full list: `rusa --voice`.

Language is auto-detected: subtitle filename pattern (`.ru.srt`, `.en.srt`, …) or content analysis via `langdetect`.

### Custom TTS engine (--tts-cmd)

Have a TTS engine not supported by rusa out of the box? Use `--tts-cmd` to invoke any command:

```bash
# espeak-ng
rusa --tts-cmd 'espeak-ng -w {out} -f {in} -v {voice}' --voice ru movie.mkv

# RHVoice
rusa --tts-cmd 'RHVoice-test -p {voice} -i {in} -o {out}' --voice elena movie.mkv

# festival
rusa --tts-cmd 'text2wave -o {out} {in}' movie.mkv

# gtts-cli (Google TTS)
rusa --tts-cmd 'gtts-cli --lang ru -o {out} -f {in}' movie.mkv

# Silero TTS (requires /home/user/bin/tts_silero.py)
rusa --tts-cmd '/home/user/bin/tts_silero.py {in} {out} {voice}' --voice baya movie.mkv
```

**Placeholders:** `{in}` = text file, `{out}` = output audio file, `{voice}` = `--voice` value.

**Note:** The command must be in PATH or an absolute path. When using `--tts-cmd`, `--voice` is mandatory. Use `--lang` to control subtitle search and output track language metadata.

### Built-in engines (`--engine`)

In addition to `edge` (Microsoft Edge TTS), rusa supports local/alternative engines through a single declarative backend:

```bash
# Piper (local neural TTS)
rusa --engine piper --voice ru_RU-dmitri-medium movie.mkv

# RHVoice
rusa --engine rhvoice --voice elena movie.mkv

# espeak-ng
rusa --engine espeak --voice ru movie.mkv

# Google TTS (gtts-cli)
rusa --engine gtts --voice ru movie.mkv

# Festival
rusa --engine festival movie.mkv

# List voices for a specific engine
rusa --voice --engine piper
```

Engines are described in the bundled `engines.yaml`. Users can add custom engines in `~/.config/rusa/engines.yaml`:

```yaml
engines:
  my_tts:
    display_name: my_tts
    binary: my_tts_bin
    output_format: wav
    default_voice: default
    static_voices: [default, alt]
    generate_cmd: "my_tts_bin --voice {voice} --input {in} --output {out}"
    voice_parser: static
```

### Language auto-detection priority

1. Explicit `--voice` (if specified)
2. Subtitle filename extension: `movie.ru.srt` → `ru-RU-SvetlanaNeural`
3. Content analysis via `langdetect` (if installed)
4. If nothing works — rusa will exit and ask for an explicit `--voice`

### `--lang` and explicit voice

- `--lang he` means: find Hebrew subtitles and, if the language is supported by rusa's voice map, pick a voice automatically.
- If the language is not in the auto-voice map, rusa will exit with a clear message asking for `--voice`.
- The combination `--lang xx --voice some-VoiceNeural` is valid: `--lang` controls subtitle search and output track metadata, `--voice` controls the actual TTS voice.

## How It Works

1. **Subtitles** — extracted from the video or loaded from an external `.srt` file
2. **Sync** (optional) — aligned with the original soundtrack via `alass`
3. **TTS** — each subtitle is generated by Microsoft Edge TTS; long phrases (>3000 chars) are split at punctuation
4. **Conversion** — atempo + silence trimming (double-pass `areverse` trick)
5. **Assembly** — each segment written at its timestamp; overlapping segments are cascaded forward (never clipped)
6. **Mux** — original audio + voiceover are mixed into the output file; subtitle handling controlled by `--subs-mode`

### `--subs-mode` Details

The `--subs-mode` flag controls how rusa handles subtitles in the output video.
It does not affect `--audio-only` mode.

- `--subs-mode auto` (default) — smart behavior: rusa tries `copy → convert → drop`, but may skip a step if preflight checks show it's impossible for the target container.
- `--subs-mode copy` — copy original subtitles as-is. If the target container doesn't support the subtitle codec, rusa exits with an error and suggests `--subs-mode convert` or `--subs-mode drop`.
- `--subs-mode convert` — always re-encode subtitles to a compatible text format. For `.mkv`, rusa uses `srt`.
- `--subs-mode drop` — do not add subtitles to the output file.

Examples:

```bash
# Default: smart copy -> convert -> drop
rusa --subs-mode auto movie.mkv

# Force copy
rusa --subs-mode copy movie.mp4

# Always convert
rusa --subs-mode convert movie.mkv

# Strip subtitles
rusa --subs-mode drop movie.mkv
```

### Assembly Algorithm

The voiceover assembly works on a **cascade shift** principle:

1. **Silence trimming** — each WAV file has its leading and trailing silence removed
   using the `areverse` trick: `silenceremove=start_periods=1` → `areverse` →
   `silenceremove=start_periods=1` → `areverse`. This reliably separates silence from speech.
2. **Precise insertion** — each segment is written at its subtitle timestamp (`start_ms`).
3. **Cascade shift** — if the previous segment hasn't finished yet, the next segment is **shifted forward**.
4. **No gap?** — the segment is inserted exactly on time.

**Segments are never truncated at end_ms** — they always play in full.

Pseudo-code:

```
cur_frame = 0
for each segment in sorted(segments):
    sf = segment.start_ms * sample_rate / 1000
    target = max(cur_frame, sf)       // cascade forward if overlapping
    write segment.audio at position target
    cur_frame = target + segment.duration_in_frames
```

Example: if subtitle A takes 1800ms after speed+trim and subtitle B starts at 1500ms:

```
A: |———— speech (1800ms) ————|
B:               |———— speech ————|
                  ↑ B should go here (1500ms), but A isn't done
                  ↓ B gets shifted
A: |———— speech (1800ms) ————|
B:                         |———— speech ————|
                            B starts at 1800ms, not 1500ms
```

B is heard with a delay but **fully**, without clipping words.

## REST API Server

rusa includes a lightweight REST API server for remote video processing.
It replaces the old Gradio WebUI with a FastAPI-based headless server.

To launch:

```bash
rusa --webui
# or
python -m webui
```

The server starts at `http://127.0.0.1:7860` and provides:

- `POST /api/process` — upload a video + optional SRT, stream real-time logs via SSE, download result
- `GET /api/download/{path}` — download a processed file
- `GET /health` — health check
- `GET /docs` — interactive Swagger API documentation

### API Usage Example

```bash
# Process a video
curl -X POST http://127.0.0.1:7860/api/process   -F "video=@movie.mkv"   -F "lang=ru"   -F "speed=1.5"

# Stream logs (SSE format)
curl -N http://127.0.0.1:7860/api/process   -F "video=@movie.mkv"
```

Install server dependencies: `pip install rusa[webui]` or `pip install fastapi uvicorn`

### Native GUI (tkinter)

A desktop GUI is also available:

```bash
python rusa_gui.py
```

It provides the same controls in a native tkinter window with a notebook interface (Basic, Audio, Subtitles tabs).

## Caching

- **TTS cache**: MP3 files from edge-tts are cached by `voice + text`. Repeated runs skip network calls.
- **WAV cache**: WAV files after `atempo + silenceremove` are cached by content hash + speed + filter version. Repeated runs skip ffmpeg.
- Default location: `~/.cache/rusa/{tts,wav}`
- Override via `RUSA_CACHE_DIR` environment variable
- Max cache size: `RUSA_CACHE_MAX_SIZE` (bytes, default 2 GiB, min 1 MiB) — LRU eviction deletes oldest files when exceeded
- If cache root is not writable, rusa works without persistent cache

Management:

```bash
rusa --cache-stats     # show size and entry count
rusa --cache-clear     # delete all cached files
rusa --no-cache        # disable cache for one run
```

## Timing Summary

After a successful build, rusa prints stage timing:

```text
Timing:
  subtitles: 2.1s
  tts: 401.3s
  wav: 60.8s
  assemble: 14.0s
  mux: 9.5s
```

This is useful for practical optimization: you can see where time is spent and whether cache, thread count, or container/codec changes make a difference.

## Exit Codes

| Code | Meaning                           |
| ---- | --------------------------------- |
| 0    | Success                           |
| 1    | Runtime error                     |
| 2    | Usage error (invalid arguments)   |
| 3    | Missing dependency (ffmpeg, etc.) |
| 4    | Subtitle error (not found, empty, broken) |
| 5    | Codec / encoder error             |

## Environment Variables

| Variable               | Description                          | Default          |
| ---------------------- | ------------------------------------ | ---------------- |
| `RUSA_CACHE_DIR`       | Cache root directory                 | `~/.cache/rusa`  |
| `RUSA_CACHE_MAX_SIZE`  | Maximum cache size in bytes          | `2147483648` (2 GiB) |

## Tests

Offline run (no network, no live TTS):

```bash
pytest -q -m 'not slow and not live_tts'
```

Live smoke run (requires edge-tts network access):

```bash
pytest -q -m 'live_tts and not slow'
```

Full suite:

```bash
pytest -q
```

Important:

- `tests/generate_fixtures.py` generates local offline fixtures using ffmpeg and doesn't require network.
- Live TTS tests are marked with `live_tts`; slow end-to-end tests are marked with `slow`.
- If `edge-tts` is not available, live tests are automatically skipped.
- To regenerate fixtures: `python3 tests/generate_fixtures.py`

## Diagnostics

### Subtitle codec error

If you see: `Subtitle codec mov_text ... is not supported`:

- In `--subs-mode auto`, rusa first tries to copy subtitles, then switches to a compatible text format, then drops subtitles if needed. If preflight knows `copy` is impossible, that step is skipped.
- In `--subs-mode copy`, rusa exits with an error early (no hidden fallback).
- In `--subs-mode convert`, rusa directly muxes a compatible text format (SRT for `.mkv`).

## Documentation
- [roadmap](doc/roadmap.md) — development roadmap and status
- [implementation_plan](doc/implementation_plan.md) — implementation plan (all phases complete)
- [TTS recommendations](doc/LANGUAGE_RECOMMENDATIONS.md) — voice quality by language

## License

MIT

---

## README CONTRACT

**This document is the specification of the project.** Any behavioral change to rusa must be reflected in this README. Code must strictly match the described logic.

If code and documentation diverge, the documentation takes precedence.

**For contributors:** before submitting a pull request, ensure all code changes are reflected in this README. Pull requests that alter behavior without updating this README will be rejected.
