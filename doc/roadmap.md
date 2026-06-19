# rusa Roadmap

## Status

The project is stable after multiple refactoring phases:

- **Phase 1** (CLI, cache, subs-mode, timing, exit codes): ✅ Complete
- **Phase 2** (Module split): ✅ Complete
- **Phase 3** (Assembly streaming): ✅ Complete
- **Gradio → FastAPI migration**: ✅ Complete
- **Python 3.8 dropped, 3.9+**: ✅ Complete
- **CI**: 205 tests pass on Python 3.9, 3.11, 3.13

Built-in TTS backend: `edge` (cloud). Custom TTS engines: `--tts-cmd`.

---

## Remaining Items

### 1. Add built-in Edge TTS voices for missing languages

- Priority: **medium** | Cost: low | Risk: low
- Languages: `uk`, `hi`, `id`, `th`, `vi`, `el`, `ro`, `hr`, `sr`, `bg`, `ms`, `sk`
- Current behaviour: aliases exist (e.g. `ukrainian → uk`) but no voice in `LANG_VOICE_MAP` → "Language not supported" error
- Solution: Add actual voice names from Edge TTS for these languages. If no voice is known, remove the alias or give a clear error asking for `--voice`.

### 2. Add `--overwrite` / output file overwrite warning

- Priority: **medium** | Cost: low | Risk: low
- File: `rusa.py`, `main()`
- Problem: `rusa` silently overwrites the output file with ffmpeg `-y` flag
- Solution: Before launching ffmpeg, check if `output` exists; warn user (or skip warning if `--yes`/`--overwrite` is passed)

### 3. Consider removing `shell=True` from `CustomCmdBackend`

- Priority: **low** | Cost: medium | Risk: medium
- File: `rusa_shared.py`, `CustomCmdBackend.generate`
- Problem: `shlex.quote` reduces shell injection risk but doesn't eliminate it. `shell=True` allows pipes and redirects in user templates (convenient but dangerous)
- Options:
  - A: keep `shell=True` + `shlex.quote` (current)
  - B: parse template into argument list, run with `shell=False` (safer, breaks pipes)
  - C: document risks and recommend against pipe-based templates

### 4. Cache `EdgeTtsBackend.validate_voice` result

- Priority: **low** | Cost: low | Risk: low
- Problem: Each `validate_voice()` call runs `edge-tts --list-voices` (network/subprocess). This slows down every run when `--voice` is specified.
- Solution: Cache the result at session level (e.g. `lru_cache` or class-level cache)

### 5. Unify `cache_bucket_stats` (recursive) and `_evict_oldest` (single-level)

- Priority: **low** | Cost: low | Risk: low
- Problem: Stats walk the directory tree recursively, eviction only cleans one level. If subdirectories ever appear in the cache, stats and eviction will disagree.

### 6. Separate `print_cache_stats` / `clear_cache` logic from `sys.exit`

- Priority: **low** | Cost: low | Risk: low
- Problem: These functions call `sys.exit(0)` directly, making them hard to reuse from the REST API
- Solution: Extract return-value logic; CLI wrapper calls `sys.exit`

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

---

## Notes

- Run full test suite: `pytest -q`
- Offline run: `pytest -q -m 'not slow and not live_tts'`
- Fixtures auto-generated; force regeneration: `python3 tests/generate_fixtures.py`
