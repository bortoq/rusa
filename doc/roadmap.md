# rusa Roadmap

## Project Status

The project is stable after multiple refactoring phases. Current focus is **CLI-first hardening**: core pipeline, tests, docs, and cross-platform reliability. GUI and REST API are treated as experimental side paths until the CLI is fully polished.

- **PHASE 1** (CLI, cache, subs-mode, timing, exit codes): ✅ Complete
- **PHASE 2** (Module split): ✅ Complete
- **PHASE 3** (Assembly streaming): ✅ Complete
- **Gradio → FastAPI migration**: ✅ Complete
- **Python 3.8 dropped, 3.9+**: ✅ Complete

---

## Adoption Plan (Q3 2026) — Low-Risk Track

Streamlined 5-week plan focusing exclusively on low-risk items:
installation simplicity, TTS ecosystem docs, CI/CD integration, and onboarding.

### Week 1: Docker

**Goal:** One-command setup.

- `Dockerfile` + `.dockerignore` + `docker-compose.yml`
- Multi-stage build (pip install → runtime)
- `pyproject.toml` entrypoint update
- Install docs: `docker run --rm -v $(pwd):/data bortoq/rusa movie.mkv`

### Week 2: TTS Engine Documentation

**Goal:** Users can easily connect best open-source TTS models.

- Pre-tested `engines.yaml` examples for Chatterbox, XTTS v2, Kokoro, Piper
- Reference guide for the `engines.yaml` format
- Test each example on a real video

### Week 3: GitHub Action

**Goal:** CI/CD voiceover pipeline.

- `action.yml` with inputs: `video`, `srt`, `lang`, `voice`, `tts-cmd`
- Example workflow in `README.md`
- Timeout-aware (document 6h GitHub limit)

### Week 4: Onboarding

**Goal:** New users productive in 5 minutes.

- "Quick start in 5 minutes" guide in `README.md`
- 4–5 ready-to-run examples
- Comparison table with pyvideotrans, Pandrator
- Restructured `README.md` (better flow, less wall of text)

### Week 5: Presets

**Goal:** One-flag quality profiles.

- `--preset youtube`, `--preset tiktok`, `--preset podcast`, `--preset cinema`
- Default flags per preset (codec, bitrate, normalize, speed)
- Preset documentation in `README.md`

---

## Backlog (deferred)

These items are recorded for future consideration but NOT in current scope:

| Item | Reason deferred |
|------|----------------|
| Flet GUI | Conflicts with existing tkinter + adds Flutter dependency |
| Multi-speaker | Architecture change, needs separate design phase |
| Telegram bot | Requires job queue, long-running task infra |
| REST API improvements | Baseline already exists (`webui/server.py`) |
| Freemium / billing | Premature — no user base yet |

---

## Remaining Technical Debt

| # | Item | Priority | Risk |
|---|------|----------|------|
| 1 | Add built-in Edge TTS voices for: uk, hi, id, th, vi, el, ro, hr, sr, bg, ms, sk | medium | low |
| 2 | Add `--overwrite` / output file overwrite warning | medium | low |
| 3 | Consider removing `shell=True` from `CustomCmdBackend` | low | medium |
| 4 | Cache `EdgeTtsBackend.validate_voice` result | low | low |
| 5 | Unify `cache_bucket_stats` (recursive) and `_evict_oldest` (single-level) | low | low |
| 6 | Separate `print_cache_stats` / `clear_cache` logic from `sys.exit` | low | low |

---

## Milestones

| # | Description | Status |
|---|-------------|--------|
| 1 | `--subs-mode` (auto/copy/convert/drop) + preflight | ✅ |
| 2 | Parallel WAV conversion + WAV cache | ✅ |
| 3 | Cache management CLI (`--cache-stats`, `--cache-clear`, `--no-cache`) | ✅ |
| 4 | Timing summary / profiling | ✅ |
| 5 | Module split (monolith → 8 modules) | ✅ |
| 6 | Assembly streaming (single write pass) | ✅ |
| 7 | Error UX: stable exit codes | ✅ |
| 8 | Tests: offline/live markers, 205 tests | ✅ |
| 9 | Unified `--voice` (filtering by `--lang`) | ✅ |
| 10 | TTS Backend Abstraction (`TtsBackend`, `EdgeTtsBackend`, `CustomCmdBackend`) | ✅ |
| 11 | `--tts-cmd` — custom TTS command | ✅ |
| 12 | File suffix `_{backend}_{lang}` | ✅ |
| 13 | Drop Python 3.8, CI Python 3.9/3.11/3.13 | ✅ |
| 14 | Gradio → FastAPI REST API migration | ✅ |
| 15 | Fix: list_voices filter, lang aliases, missing-norwegian | ✅ |
| 16 | Fix: shell injection protection (shlex.quote) | ✅ |
| 17 | Fix: `--voice` required for `--tts-cmd`, lang_suffix sanitized | ✅ |
| 18 | Fix: `_split_text` — improved split at punctuation+space | ✅ |
| 19 | Fix: dead code removal (`if not output`, unused imports) | ✅ |
| 20 | Fix: `__all__` in all modules | ✅ |
| 21 | Fix: LRU cache eviction | ✅ |
| 22 | Docker image | ⏳ Week 1 |
| 23 | TTS engine docs + examples | ⏳ Week 2 |
| 24 | GitHub Action | ⏳ Week 3 |
| 25 | Onboarding + README restructure | ⏳ Week 4 |
| 26 | Quality presets (`--preset`) | ⏳ Week 5 |

---

## Notes

- Run full test suite: `pytest -q`
- Offline run: `pytest -q -m 'not slow and not live_tts'`
- Fixtures auto-generated; force regeneration: `python3 tests/generate_fixtures.py`
