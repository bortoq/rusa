# TTS Engines in rusa

rusa supports three ways to use text-to-speech:

1. **Built-in engines** (`--engine`) — declarative definitions in `engines.yaml`
2. **Custom command** (`--tts-cmd`) — arbitrary shell command with `{in}` `{out}` `{voice}`
3. **Default Edge TTS** (no flag) — Microsoft Edge cloud TTS

---

## 1. Built-in Engines (`--engine`)

| Engine | Quality | Speed | Offline | Languages | Install |
|--------|---------|-------|---------|-----------|---------|
| `edge` (default) | Good | Fast | ❌ | 33+ | `pip install edge-tts` |
| `piper` | Good | **Very fast** | ✅ | 10+ | [pip install piper-tts](https://github.com/rhasspy/piper) |
| `rhvoice` | Average | Fast | ✅ | ru, uk, en, etc. | `apt install rhvoice` |
| `espeak` | Low | **Ultra fast** | ✅ | 100+ | `apt install espeak-ng` |
| `gtts` | Good | Fast | ❌ | 30+ | `pip install gtts` |
| `festival` | Low | Medium | ✅ | en, ru | `apt install festival` |

### Examples

```bash
# Piper — local neural TTS
rusa --engine piper --voice ru_RU-dmitri-medium movie.mkv

# eSpeak — ultra fast, any language
rusa --engine espeak --voice ru movie.mkv

# Google TTS — cloud, many languages
rusa --engine gtts --voice ru movie.mkv
```

---

## 2. Custom Command (`--tts-cmd`)

Use **any** TTS engine not listed above via a template:

```bash
rusa --tts-cmd "python my_tts.py {in} {out} {voice}" --voice ru-RU-DmitryNeural movie.mkv
```

### Placeholders

| Placeholder | Replaced with | Quoted? |
|-------------|---------------|---------|
| `{in}` | Path to input text file | ✅ `shlex.quote` |
| `{out}` | Path to output audio file | ✅ `shlex.quote` |
| `{voice}` | Value of `--voice` | ✅ `shlex.quote` |

### Requirements

- `--voice` **is required** when using `--tts-cmd`
- `--lang` controls subtitle search and output metadata (not the voice)
- The command must be in `PATH` or specified as an absolute path
- Output format must be **WAV** (16-bit mono PCM)

### Pre-tested templates

#### Chatterbox (best quality)

```bash
# Install: pip install chatterbox-tts
rusa --tts-cmd "chatterbox --voice {voice} --input {in} --output {out}" \
     --voice /path/to/reference.wav \
     movie.mkv
```

#### Coqui XTTS v2 (voice cloning)

```bash
# Install: pip install TTS
rusa --tts-cmd "tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 \
     --speaker_wav {voice} --text_in {in} --out_path {out}" \
     --voice /path/to/speaker.wav \
     movie.mkv
```

#### Kokoro (very fast, good quality)

```bash
# Install: pip install kokoro-onnx
rusa --tts-cmd "python -m kokoro_tts --voice {voice} --input {in} --output {out}" \
     --voice af_bella \
     movie.mkv
```

#### Piper (via `--tts-cmd`, more control)

```bash
rusa --tts-cmd "piper --model {voice} --output_file {out} < {in}" \
     --voice en_US-lessac-medium \
     movie.mkv
```

---

## 3. Custom `engines.yaml`

For frequently used custom TTS engines, create `~/.config/rusa/engines.yaml`:

```yaml
engines:
  my_engine:
    display_name: My Engine
    binary: my_tts_bin          # must be in PATH
    output_format: wav
    default_voice: default
    static_voices: [default, alt]
    generate_cmd: "my_tts_bin --voice {voice} --input {in} --output {out}"
    voice_parser: static
```

Then use it:

```bash
rusa --engine my_engine --voice default movie.mkv
```

### YAML Reference

| Field | Required | Description |
|-------|----------|-------------|
| `display_name` | No | Human-readable name (used in output filename) |
| `binary` | **Yes** | Executable name (must be in `PATH`) |
| `output_format` | **Yes** | `wav` or `mp3` |
| `default_voice` | No | Used when no `--voice` is given |
| `static_voices` | No* | List of known voices |
| `list_voices_cmd` | No* | Shell command to list voices (e.g. `espeak-ng --voices`) |
| `generate_cmd` | **Yes** | Template with `{in}` `{out}` `{voice}` |
| `voice_parser` | No | `static`, `espeak`, or `one_per_line` (default: `static`) |

\* Either `static_voices` or `list_voices_cmd` must be present (or both).

### Voice Parsers

| Parser | Behaviour |
|--------|-----------|
| `static` | Uses `static_voices` list directly |
| `espeak` | Parses `espeak-ng --voices` format (Pty Language Age/Gender VoiceName) |
| `one_per_line` | Treats each output line as a voice name |

---

## Engine Comparison Table

| Engine | Quality (1-5) | Speed | Latency | Languages | Internet | Setup |
|--------|:------------:|:-----:|:-------:|:---------:|:--------:|:-----:|
| Edge TTS | ★★★★ | 🚀 Fast | 100-300ms | 33+ | Required | `pip install edge-tts` |
| Chatterbox | ★★★★★ | 🐢 Medium | 500ms-2s | Many | Optional | `pip install chatterbox-tts` |
| XTTS v2 | ★★★★★ | 🐢 Medium | 1-3s | 17+ | Optional | `pip install TTS` |
| Kokoro | ★★★★ | 🚀 Fast | 100-400ms | EN, JP, ZH, KO, FR | Optional | `pip install kokoro-onnx` |
| Piper | ★★★ | 🚀 Fast | 50-200ms | 10+ | No | `pip install piper-tts` |
| gTTS | ★★★ | 🚀 Fast | 200-500ms | 30+ | Required | `pip install gtts` |
| RHVoice | ★★★ | 🚀 Fast | 50-150ms | RU, UK, EN, etc. | No | `apt install rhvoice` |
| eSpeak | ★★ | ⚡ Ultra | 10-50ms | 100+ | No | `apt install espeak-ng` |

---

## Recommendations by Use Case

| Use Case | Recommended Engine | Reason |
|----------|-------------------|--------|
| Maximum quality | Chatterbox / XTTS v2 via `--tts-cmd` | Best naturalness |
| Fast + good quality | Edge TTS (default) | No setup, 33+ languages |
| Offline + fast | Piper via `--engine piper` | Local neural, CPU-friendly |
| Ultra-fast, any language | eSpeak via `--engine espeak` | 100+ languages, instant |
| Voice cloning | XTTS v2 via `--tts-cmd` | Clone from reference audio |
| Low-resource devices | Piper or Kokoro via `--tts-cmd` | Runs on Raspberry Pi |

---

## Verifying Engine Setup

```bash
# List available voices for an engine
rusa --voice --engine piper

# Quick test with first 3 subtitles (no full processing)
rusa --preview 3 --dry-run --engine piper --voice ru_RU-dmitri-medium movie.mkv

# Full run with preview limit
rusa --preview 10 --engine espeak --voice ru movie.mkv
```
