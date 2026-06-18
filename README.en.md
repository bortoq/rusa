# rusa — AI Voiceover for Movies

**rusa** is a command-line tool that adds **full voiceover translation** to your video collection in a single command. Point it at a video file — rua extracts subtitles, generates speech using Microsoft Edge TTS neural voices, and mixes it over the original audio.

Ideal for:
- 🎬 **Movies & TV series** — Russian voiceover from existing subtitles
- 🎙️ **Podcasts & lectures** — voiceover translation into any supported language

```bash
# One command — ready result
rusa movie.mkv
```

## Features

- 🎯 **One command** — rusa finds subtitles, generates voiceover, and assembles the final file automatically
- 🔊 **Natural neural voices** — Microsoft Edge TTS (Svetlana and Dmitry for Russian, 80+ languages supported)
- ✂️ **Smart silence trimming** — leading/trailing silence is removed; speech and inter-phrase pauses stay intact
- 🧩 **Intelligent assembly** — if entries overlap, rusa shifts them forward instead of clipping words
- 🌐 **Auto language detection** — rusa picks the right voice from the subtitle content. Supports Russian, English, German, French, Spanish, Italian, Portuguese, Japanese, Korean, Chinese, Arabic, Turkish, Dutch, Polish, Swedish, Danish, Finnish, Norwegian, Czech, Hungarian, Hebrew, and more; other languages via explicit `--voice`
- 🎚️ **Adjustable volume** — set original and TTS volume independently (0.0–1.0) to balance background and voiceover
- 🔄 **Normalization** — loudnorm (fine) or dynaudnorm (fast) for consistent volume across the whole movie
- 🎧 **Any audio codec** — AAC, MP3, Opus, AC3 — your choice
- 🧩 **Split-sentence merging** — broken subtitles (e.g. 1ms gap / lowercase continuation) are automatically merged for natural TTS intonation
- ⚡ **Parallel processing** — MP3→WAV conversion runs in multiple threads
- ⏱️ **Stage timing summary** — after a successful run, rusa prints elapsed time per stage: subtitles, TTS, WAV, assemble, mux
- 💾 **Persistent cache** — TTS and WAV results are cached; repeated runs reuse cached data and skip network/ffmpeg calls
- 🔐 **Terminal state guard** — saves and restores terminal attributes on exit/signal, preventing mc and terminal corruption

## Quick Start

**Linux / macOS:**

```bash
# Install dependencies
pip install edge-tts tqdm langdetect

# Make sure ffmpeg is installed
# Linux: apt install ffmpeg   (or brew install ffmpeg on macOS)

# Dub a movie
rusa movie.mkv
```

**Windows (PowerShell):**

```powershell
# Install dependencies
pip install edge-tts tqdm langdetect

# Make sure ffmpeg.exe is in your PATH (download from ffmpeg.org)

# Dub a movie
python rusa.py movie.mkv
```

The output file is placed next to the source: `movie_dubbed.mkv`.

Dependencies: `ffmpeg` + `ffprobe` (part of ffmpeg), `python3`.
`langdetect` is optional — it improves auto-detection from `.srt` content.

## Options

| Flag                         | Description                           | Default                             |
| ---------------------------- | ------------------------------------- | ----------------------------------- |
| `video`                      | Video file (.mkv, .mp4, .avi, …)      | required                            |
| `-o, --output FILE`          | Output file                           | `<video>_dubbed.mkv`                |
| `-s, --srt FILE`             | External subtitle file (.srt)         | extracted from video / found nearby |
| `--voice VOICE`              | edge-tts voice name                   | auto-detected from subtitle language |
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
| `--no-cache` | Disable cache for this run | off |
| `--dry-run` | Show generation plan without running TTS or rendering | off |
| `--preview N` | Generate only the first N subtitles | off |
| `--version`                  | Show version (1.0.0) and exit         | —                                   |
| `--aac [BITRATE]`            | AAC codec (128, 192, …)               | off                                |
| `--mp3 [BITRATE]`            | MP3 codec (128, 192, …)               | off                                |
| `--opus [BITRATE]`           | Opus codec (64, 96, …)                | on (64k default)                   |
| `--ac3 [BITRATE]`            | AC3 codec (448, 640, …)               | off                                |
| `--from N`                   | First subtitle index                  | all                                |
| `--to N`                     | Last subtitle index                   | all                                |
| `--audio-only`               | Audio output only (no video)          | off                                |
| `--engine ENGINE` | TTS engine (edge, piper, rhvoice, espeak, gtts, festival or a custom engine from `~/.config/rusa/engines.yaml`) | `edge` |
| `--tts-cmd TEMPLATE` | Arbitrary TTS command (`{in}` `{out}` `{voice}`). When used, overrides `--engine` | —                                |
| `--subs-mode {auto,copy,convert,drop}` | Subtitle handling in output video | `auto`                 |
| `--normalize [{fast,fine}]`  | Volume normalization                  | off                                |

## Examples

```bash
# Basic usage
rusa movie.mkv

# Male voice + speed
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

# Disable sentence merging
rusa --no-merge-sentences movie.mkv

# Cache management
rusa --cache-stats
rusa --cache-clear

# List available voices
rusa --voice
```

## Voices

Current Russian Microsoft Edge TTS voices:

| Voice                  | Quality                       |
| ---------------------- | ----------------------------- |
| `ru-RU-SvetlanaNeural` | Female, neural (default)      |
| `ru-RU-DmitryNeural`   | Male, neural                  |

**80+ languages** are supported — from English and German to Japanese and Hebrew. Full list: `rusa --voice`.

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

---

## How It Works

1. **Subtitles** — extracted from the video or loaded from an external `.srt` file
2. **Sync** (optional) — aligned with the original soundtrack via `alass`
3. **TTS** — each subtitle is generated by Microsoft Edge TTS; long phrases (>3000 chars) are split at punctuation
4. **Conversion** — atempo + silence trimming (double-pass `areverse` trick)
5. **Assembly** — each segment written at its timestamp; overlapping segments are cascaded forward (never clipped)
6. **Mux** — original audio + voiceover are mixed into the output file; subtitle handling controlled by `--subs-mode`

### Assembly Algorithm

```
cur_frame = 0
for each segment in sorted(segments):
    sf = segment.start_ms * sample_rate / 1000
    target = max(cur_frame, sf)       // cascade forward if overlapping
    write segment.audio at position target
    cur_frame = target + segment.duration_in_frames
```

Segments are **never** truncated at `end_ms` — they always play in full.

## Caching

- **TTS cache**: MP3 files from edge-tts are cached by `voice + text`. Repeated runs skip network calls.
- **WAV cache**: WAV files after `atempo + silenceremove` are cached by content hash + speed + filter version. Repeated runs skip ffmpeg.
- Default location: `~/.cache/rusa/{tts,wav}`
- Override via `RUSA_CACHE_DIR`
- Max cache size: `RUSA_CACHE_MAX_SIZE` (bytes, default 2 GiB, min 1 MiB)

Management:
```
rusa --cache-stats     # show size and entry count
rusa --cache-clear     # delete all cached files
rusa --no-cache        # disable cache for one run
```

## Exit Codes

| Code | Meaning                           |
| ---- | --------------------------------- |
| 0    | Success                           |
| 1    | Runtime error                     |
| 2    | Usage error (invalid args)        |
| 3    | Missing dependency (ffmpeg, etc.) |
| 4    | Subtitle error                    |
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

Full suite (requires edge-tts network access):
```bash
pytest -q
```

Regenerate test fixtures:
```bash
python3 tests/generate_fixtures.py
```

## Timing Summary

After a successful build, rusa prints stage timing:

```
Timing:
  subtitles: 2.1s
  tts: 401.3s
  wav: 60.8s
  assemble: 14.0s
  mux: 9.5s
```

## Documentation
- [roadmap](doc/roadmap.md) — refactoring roadmap and status
- [implementation_plan](doc/implementation_plan.md) — phased implementation plan

## License

MIT

---

## README CONTRACT

**This document is the specification of the project.** Any behavioral change to rusa must be reflected in this README. Code must strictly match the described logic.

If code and documentation diverge, the documentation takes precedence.

**For contributors:** before submitting a pull request, ensure all code changes are reflected in this README. Pull requests that alter behavior without updating this README will be rejected.
