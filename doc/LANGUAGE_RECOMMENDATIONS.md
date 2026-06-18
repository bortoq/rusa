# TTS Recommendations by Language

rusa is an orchestration tool, not a TTS engine.  
**Voice quality depends primarily on the TTS model you choose**, not on rusa.

This document contains up-to-date recommendations for 2026.

## General Principle

- For **maximum quality** — use modern open-source models via `--tts-cmd`.
- For **simplicity and speed** — use Microsoft Edge TTS (default).
- For **rare languages** — connecting specialized TTS models almost always yields better results.

## Top TTS Recommendations (2026)

| Priority | TTS Model               | Quality  | Speed         | Voice Cloning | Best For                       | License      | Rating  |
|----------|-------------------------|----------|---------------|---------------|--------------------------------|--------------|---------|
| 1        | **Chatterbox**          | Excellent| Good          | Excellent     | Most languages                 | MIT          | ★★★★★   |
| 2        | **Coqui XTTS v2**       | Excellent| Average       | Excellent     | Multilingual + cloning         | MPL 2.0      | ★★★★★   |
| 3        | **Fish Speech S2**      | Excellent| Average       | Good          | Rare languages                 | Research     | ★★★★☆   |
| 4        | **Kokoro**              | Very Good| **Excellent** | No            | Fast processing                | Apache 2.0   | ★★★★☆   |
| 5        | **Piper**               | Good     | **Excellent** | No            | CPU-only, edge devices         | MIT          | ★★★★    |
| 6        | Microsoft Edge TTS      | Good     | Excellent     | No            | Quick start                    | —            | ★★★☆    |

## Recommendations by Language

### Excellent Quality Available

These languages sound good on both Edge TTS and modern open-source models:

- Russian
- English (US/UK)
- German
- French
- Spanish
- Italian
- Portuguese
- Chinese (Mandarin)
- Japanese
- Korean

**Recommendation:** Start with Edge TTS. For maximum quality, use Chatterbox or XTTS v2.

### Good Quality

- Arabic
- Dutch
- Polish
- Swedish
- Czech
- Hungarian
- Turkish
- Hebrew

**Recommendation:** Edge TTS provides acceptable quality. For higher requirements, switch to XTTS v2 or Chatterbox.

### Average / Unstable Quality

- Norwegian (`nb`)
- Danish
- Finnish
- Greek
- Romanian
- Bulgarian
- Ukrainian

**Recommendation:** Use `--tts-cmd` with modern open-source models.

### Languages Where Edge TTS Often Disappoints

- Hindi
- Thai
- Vietnamese
- Indonesian
- Malay
- Most African and South Asian languages

**Recommendation:** Always use `--tts-cmd` with modern open-source models.

## How to Connect Recommended TTS

### Example with Chatterbox / XTTS v2

```bash
rusa movie.mkv \
  --tts-cmd "python -m tts_server --model chatterbox --ref {voice} --input {in} --output {out}" \
  --voice /path/to/reference.wav
```

### Example with Piper (maximum speed)

```bash
rusa movie.mkv \
  --tts-cmd "piper --model en_US-lessac-medium --output_file {out} < {in}"
```

### Example with Kokoro

```bash
rusa movie.mkv \
  --tts-cmd "python kokoro_tts.py --voice af_bella --input {in} --output {out}"
```

## Useful Tips

- For **maximum speed** on weak hardware: **Piper** or **Kokoro**.
- For **voice cloning**: use XTTS v2 or Chatterbox.
- Always test the voice on a short clip before processing the full video.

## Want to Add Your Own TTS?

rusa is designed so you can connect **any** TTS system via the `--tts-cmd` parameter.  
This is the most powerful and recommended way to work with rare languages and custom voices.
