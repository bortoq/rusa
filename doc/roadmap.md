# rusa Roadmap

## Status

### Completed (Phase 1 + Phase 2 + Phase 3)

- [x] `--subs-mode` (`auto`/`copy`/`convert`/`drop`) + preflight subtitle/container strategy
- [x] Robust mux fallback for incompatible subtitle codecs
- [x] Parallel WAV conversion (`MP3 → WAV` в несколько потоков)
- [x] WAV cache (`tts_mp3_hash + speed + filter_version`)
- [x] Cache management CLI (`--cache-stats`, `--cache-clear`, `--no-cache`)
- [x] Timing summary / profiling (prints stage timing after assembly)
- [x] Module split: monolithic `rusa.py` split into 8 modules
- [x] Assembly streaming (single write pass, no file reopen, WAV header written at the end)
- [x] Error UX: stable exit codes (`EXIT_RUNTIME_ERROR`, `EXIT_USAGE_ERROR`, `EXIT_DEPENDENCY_ERROR`, `EXIT_SUBTITLE_ERROR`, `EXIT_CODEC_ERROR`)
- [x] Tests: offline/live markers (`slow`, `live_tts`)
- [x] 81 tests → 122 tests, all passing
- [x] Unified `--voice` (filtering by `--lang`)
- [x] TTS Backend Abstraction — `BACKEND_REGISTRY`, `TtsBackend`, `EdgeTtsBackend`, `CustomCmdBackend`
- [x] `--tts-cmd` — custom TTS command (`{in}` `{out}` `{voice}`)
- [x] `_{backend}_{lang}` replaces `_dubbed` in output filename

---

## Priorities

### ✅ 1. Fix latent crash when `langdetect` is missing

- Priority: **critical**
- Cost: low
- Risk: low

**Problem:** `rusa_subtitle.py` делает `from rusa_shared import LangDetectException, detect`. Если `langdetect` не установлен, эти имена не определены в `rusa_shared` → `ImportError` при старте.

**Solution:**
- Вариант A: обернуть импорт в `try/except ImportError` в `rusa_subtitle.py`
- Вариант B: определить заглушки `LangDetectException = Exception` и `detect = None` в `rusa_shared` при отсутствии `langdetect`

**Check:** `python3 -c "from rusa_subtitle import detect_language_from_srt"` без `langdetect` в окружении.

---

### ✅ 2. Remove dead code and unused imports

- Priority: **high**
- Cost: low
- Risk: low

#### 2a. Dead imports in `rusa_shared.py`
- `import textwrap` (строка 10) — не используется
- `import wave` (строка 12) — не используется
- `from pathlib import Path` (строка 13) — не используется

#### 2b. Dead fixture `tmp_wav` in `conftest.py`
- Определена на строках 67–73, ни один тест не использует

#### 2c. Unused imports in `conftest.py`
- `import json` — не используется
- `import tempfile` — используется только мёртвой `tmp_wav`

#### 2d. `import textwrap` at end of `conftest.py`
- Строка 173, расположен после использования в фикстурах. Перенести в начало.

---

### ✅ 3. Remove empty facade `rusa_cache.py`

- Priority: **high**
- Cost: low
- Risk: low

**Problem:** `rusa_cache.py` (38 строк) — pass-through фасад, который только реэкспортирует функции из `rusa_shared`. Не добавляет ценности.

**Solution:**
- Удалить `rusa_cache.py`
- В `rusa.py` импортировать `_tts_cache_path`, `_wav_cache_path` напрямую из `rusa_shared`
- Обновить `__all__` в `rusa_shared`, если нужен публичный API

---

### ✅ 4. Replace `from rusa_shared import *` with explicit imports

- Priority: **high**
- Cost: low
- Risk: low

**File:** `rusa.py`, строка 23

Wildcard import pulls everything, включая `_CACHE_DISABLED`, `HAS_TQDM`, `HAS_LANGDETECT`.

**Solution:** Перечислить только нужные имена.

---

### ✅ 5. Replace `__import__()` with regular imports

- Priority: **high**
- Cost: low
- Risk: low

**Files:**
- `rusa.py` строка 197: `__import__("shutil").rmtree(...)`
- `rusa_tts.py` строки 28, 58, 127: `__import__("re").finditer(...)`, `__import__("shutil").copy2(...)`

**Solution:** Перенести `import re`, `import shutil` в начало файлов.

---

### ✅ 6. Cache `_check_ffmpeg_codec()`

- Priority: **high**
- Cost: low
- Risk: low

**File:** `rusa_mux.py`, строки 30–34

Each call runs `ffmpeg -hide_banner -encoders`. Up to 4 calls when selecting codecs.

**Solution:** Использовать `functools.lru_cache(maxsize=1)`.

---

### ✅ 7. Add `.rus.srt` and `.russian.srt` support to language detection

- Priority: **medium**
- Cost: low
- Risk: low

**File:** `rusa_subtitle.py`, строка 27

```python
match = re.match(r".*\.([a-z]{2})\.srt$", name)
```

Regex matches only 2-letter codes (`.ru.srt`), not `.rus.srt` (3 letters).

**Solution:** Расширить до `r".*\.([a-z]{2,7})\.srt$"` и добавить маппинг: `rus → ru`, `russian → ru`, `english → en`, `hebrew → he` и т.д.

---

### ✅ 8. Add `--version` to CLI

- Priority: **medium**
- Cost: low
- Risk: low

**Files:** `rusa_cli.py`, `pyproject.toml`

Version `1.0.0` exists in `pyproject.toml`, but CLI doesn't expose it.

**Solution:** `parser.add_argument("--version", action="version", version="rusa 1.0.0")`

---

### ✅ 9. Fix legacy build-backend in `pyproject.toml`

- Priority: **medium**
- Cost: low
- Risk: low

```toml
build-backend = "setuptools.backends._legacy:_Backend"
```

Должно быть:
```toml
build-backend = "setuptools.build_meta"
```

---

### ✅ 10. TypedDict for Entry instead of `dict`

- Priority: **medium**
- Cost: low
- Risk: low

**File:** `rusa_subtitle.py`, строка 22

```python
Entry = dict  # {"idx": int, "start_ms": int, "end_ms": int, "text": str}
```

**Solution:** Заменить на `TypedDict`:

```python
from typing import TypedDict
class Entry(TypedDict):
    idx: int
    start_ms: int
    end_ms: int
    text: str
```

---

### ✅ 11. Eliminate `make_sine_wav` duplication

- Priority: **medium**
- Cost: low
- Risk: low

**Files:** `conftest.py` (строки 75–97) и `test_assembly.py` (строки 8–29)

Two identical copies of the function.

**Solution:** Удалить из `test_assembly.py`, все импорты перенаправить на `conftest.make_sine_wav`. Или вынести в отдельный helper-модуль.

---

### ✅ 12. Add `__all__` to all modules

- Priority: **medium**
- Cost: low
- Risk: low

**Files:** Все `.py` модули (кроме `rusa_cache.py`, который будет удалён).

`from rusa_shared import *` currently pulls private variables.

**Solution:** В каждом модуле определить `__all__` с явным списком публичных имён.

---

### ✅ 13. Add LRU eviction for cache

- Priority: **low**
- Cost: medium
- Risk: low

**File:** `rusa_shared.py` (cache helpers)

Currently cache only grows. Need automatic cleanup when size exceeds limit.

**Возможные решения:**
- `RUSA_CACHE_MAX_SIZE` переменная окружения (по умолч. 2GB)
- При записи нового файла проверять общий размер; если превышен — удалять самые старые файлы по mtime
- Или делегировать очистку `--cache-clear` / внешнему cron

---

### ✅ 14. Add unit tests for `_run_loudnorm`, `_run_dynaudnorm`, `_check_ffmpeg_codec`, `list_voices`, `shell`, `which`, `die`

- Priority: **low**
- Cost: medium
- Risk: low

**Files:** `tests/`

Currently these functions are only covered indirectly (via regression tests). Прямые unit-тесты с fake-subprocess повысят надёжность при рефакторинге.

---

### ✅ 15. Fix `_get_codec()` fallback for unknown codec

- Priority: **low**
- Cost: low
- Risk: low

**File:** `rusa_mux.py`, строка 24–27

If codec not found in `CODEC_MAP`, returns `("libopus", "64k", ".opus")` вне зависимости от запроса.

**Solution:** Лучше вернуть `None` и дать понятную ошибку на стороне вызова, либо выкинуть `KeyError` с внятным сообщением.

---

### ✅ 16. Move documentation to `doc/`

- Priority: **low**
- Cost: low
- Risk: low

**Current structure:**
```
/rusa/
  roadmap.md          ← здесь
  implementation_plan.md
  README.md
```

**Target:**
```
/rusa/
  doc/
    roadmap.md
    implementation_plan.md
  README.md
```

**Solution:**
- Создать `doc/`
- Перенести `roadmap.md` → `doc/roadmap.md`
- Перенести `implementation_plan.md` → `doc/implementation_plan.md`
- Add a section in root `README.md` with links: `See doc/roadmap.md and doc/implementation_plan.md`
- Удалить исходные файлы из корня

---

### ✅ 17. Add `.gitignore` for build artifacts и дистрибуции

- Priority: **low**
- Cost: low
- Risk: low

Добавить в `.gitignore`:
```
dist/
*.egg-info/
*.egg
build/
```

---

### ✅ 18. CustomCmdBackend + remove RHVoice + remove --tts-backend

- `--tts-cmd` — custom TTS command с плейсхолдерами `{in}` `{out}` `{voice}`
- `CustomCmdBackend` — класс для пользовательских TTS-движков
- RHVoice removed from built-in backends (available via `--tts-cmd`)
- `--tts-backend` removed (only built-in backend is edge)

---

### ✅ 19. TTS Backend Abstraction + file suffix

- Introduced base class `TtsBackend` с методами `is_available()`, `list_voices()`, `get_default_voice()`, `lang_from_voice()`, `validate_voice()`, `generate()`
- `BACKEND_REGISTRY` — backend registration by name
- `EdgeTtsBackend` — concrete implementation
- `rusa.py` has no `if backend == "rhvoice"` — all via registry
- Output filename suffix: `_{backend}_{lang}` (например, `_edge_ru`)

- (removed)
- Unified `--voice` shows voices from all installed backends
- Filtering by `--lang` for voice display
- Cache separated by backend
- 122 tests, all passing

---

## Suggested Next Order

Все пункты выполнены. Проект в стабильном состоянии:
- Поддерживаемый бэкенд: `edge` (облачный, встроенный)
- Произвольные TTS-движки: `--tts-cmd` (любой внешний бинарник)
- Дальнейшее развитие: добавление новых бэкендов через `class NewBackend(TtsBackend)` + `register_backend()`



---

## Audit 2026-06-18 — Full Project Audit

**Status:** APPROVED ✅. 129 offline tests + 4 live tests, all passing.

### Completed (by previous auditor)

- [x] `shlex.quote` for `{in}` `{out}` `{voice}` placeholders in `CustomCmdBackend.generate` — shell injection protection
- [x] `_sanitize_filename_part()` for `lang_suffix` in `CustomCmdBackend` — safe filenames
- [x] `voiceover_lang = "und"` for `--tts-cmd` without `--lang` — valid ISO codes in metadata
- [x] Language aliases: `norwegian` → `nb`, `norsk` → `nb`, `no` → `nb`
- [x] `__all__` in all modules (8/8)
- [x] `lru_cache` for `_check_ffmpeg_codec` — eliminate duplicate `ffmpeg -encoders` calls
- [x] `_get_codec` returns `None` instead of opus-fallback for unknown codecs
- [x] Language detection regex: `[a-z]{2,7}` + mapping `rus→ru`, `russian→ru`, `english→en`, `hebrew→he`
- [x] `make_sine_wav` moved to `conftest.py`, deduplicated from `test_assembly.py`
- [x] `import textwrap` moved to top of `conftest.py`
- [x] Dead code `if not output` removed from `step_mix_output`
- [x] `_split_text` improved: split after `[.!?…](\s|$)` instead of any character
- [x] `list_voices` filter fixed: `startswith(f"{lang}-")` instead of `"-{lang}-" not in`
- [x] Test `test_voice_resolution_with_external_srt` fixed (no longer depends on `langdetect`)
- [x] `README.en.md` — removed `--tts-backend` flag

### New Priorities

#### ✅ 20. Remove duplicate roadmap.md and implementation_plan.md from root

- Priority: **high**
- Cost: low
- Risk: low

**Problem:** `roadmap.md` и `implementation_plan.md` лежат и в корне, и в `doc/`. Это дублирование, нарушающее roadmap #16.

**Solution:** Удалить root-копии. Каноничные файлы — `doc/roadmap.md` и `doc/implementation_plan.md`.

---

#### ✅ 21. Add overwrite warning for output file

- Priority: **medium**
- Cost: low
- Risk: low

**File:** `rusa.py`, `main()`

**Problem:** `rusa` перезаписывает выходной файл с `-y` ffmpeg без предупреждения.

**Solution:** Перед запуском ffmpeg проверять, существует ли `output`; если да — выводить предупреждение и спрашивать подтверждение (или просто предупреждать, если не `--yes`/`--overwrite`).

---

#### ✅ 22. Expand `LANG_VOICE_MAP` for unsupported languages

- Priority: **medium**
- Cost: low
- Risk: low

**File:** `rusa_shared.py`

**Problem:** Алиасы `ukrainian`, `hindi`, `indonesian`, `thai`, `vietnamese`, `greek`, `romanian`, `croatian`, `serbian`, `bulgarian`, `malay`, `slovak` ведут на ISO-коды, отсутствующие в `LANG_VOICE_MAP`, что вызывает ошибку "Язык не поддерживается".

**Solution:** Добавить соответствующие голоса Edge TTS для этих языков. Если голос неизвестен — убрать алиас или выдавать понятное сообщение.

---

#### 23. Consider removing `shell=True` from `CustomCmdBackend`

- Priority: **low**
- Cost: medium
- Risk: medium

**File:** `rusa_shared.py`, `CustomCmdBackend.generate`

**Problem:** `shlex.quote` снижает риск shell-инъекций, но не устраняет его полностью. `shell=True` позволяет пайпы и редиректы в шаблоне пользователя, что удобно, но опасно.

**Solution:** 
- Option A: keep `shell=True` + `shlex.quote` (current)
- Option B: parse template into argument list, run with `shell=False` (safer, but breaks pipes)
- Option C: document risks and recommend against pipe-based templates

---

## Remaining Items (from previous audit)

These items are recorded in `audit_report.md` and remain relevant for future iterations:

1. Add built-in Edge TTS voices for: uk, hi, id, th, vi, el, ro, hr, sr, bg, ms, sk
2. Add `--overwrite` / output file overwrite warning
3. Consider removing `shell=True` from `CustomCmdBackend`
4. Cache `EdgeTtsBackend.validate_voice` result (currently calls `--list-voices` every time)
5. Unify `cache_bucket_stats` (recursive) and `_evict_oldest` (single level)
6. Separate `print_cache_stats`/`clear_cache` logic from `sys.exit`



---

## 24. WebUI — migrated from Gradio to FastAPI REST API

- Priority: **medium**
- Status: **completed** (migrated from Gradio to FastAPI)
- Difficulty: 15–19 person-days (original) + 3 days (migration)

### Change

The old Gradio-based WebUI was replaced with a lightweight FastAPI REST API server.
The Gradio frontend (, ) was removed.
The server now provides HTTP endpoints instead of a browser GUI.

### Current Architecture

```
rusa/
├── rusa.py                 # CLI entrypoint (--webui → FastAPI server)
├── webui/
│   ├── __init__.py          # run() → launches uvicorn
│   ├── server.py            # FastAPI app, /api/process, /health, /api/download
│   ├── config.py            # Shared configuration constants
│   └── utils.py             # build_args(), pick_output_file()
├── engines.yaml
└── pyproject.toml
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET |  | Health check |
| POST |  | Upload video + params, stream log via SSE |
| GET |  | Download processed file |
| GET |  | Swagger UI |

### Dependencies

- Removed: 
- Added: ,  (optional dep `[webui]`)

### Status

- [x] FastAPI server with streaming SSE response
- [x] File upload, processing, download
- [x] Path traversal protection
- [x] CORS for local development
- [x] Tests: 22 server tests + 19 config/utils tests


### 25. Drop Python 3.8 support

- Priority: **high**
- Status: **completed**

**Reason:** aiohttp dropped Python 3.8 support in v3.11 (Nov 2024). Python 3.8 is EOL (Oct 2024). CI consistently failed on 3.8.

**Change:** `pyproject.toml` requires-python updated to `>=3.9`. CI matrix updated from `["3.8", "3.11"]` to `["3.9", "3.11", "3.13"]`.

## Notes

- After each change — run full test suite: `PYTHONDONTWRITEBYTECODE=1 pytest -q tests/`
- Offline run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -m 'not slow and not live_tts' tests/`
- Fixtures generated automatically; force regeneration: `python3 tests/generate_fixtures.py`
