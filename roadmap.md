# rusa Roadmap

## Status

### Уже сделано (Phase 1 + Phase 2 + Phase 3)

- [x] `--subs-mode` (`auto`/`copy`/`convert`/`drop`) + preflight subtitle/container strategy
- [x] Устойчивый mux fallback для несовместимых subtitle codecs
- [x] Parallel WAV conversion (`MP3 → WAV` в несколько потоков)
- [x] WAV cache (`tts_mp3_hash + speed + filter_version`)
- [x] Cache management CLI (`--cache-stats`, `--cache-clear`, `--no-cache`)
- [x] Timing summary / profiling (печать времени по этапам после сборки)
- [x] Module split: монолит `rusa.py` разделён на 8 модулей
- [x] Assembly streaming (один write pass, без переоткрытия файла, WAV header пишется в конце)
- [x] Error UX: стабильные exit-коды (`EXIT_RUNTIME_ERROR`, `EXIT_USAGE_ERROR`, `EXIT_DEPENDENCY_ERROR`, `EXIT_SUBTITLE_ERROR`, `EXIT_CODEC_ERROR`)
- [x] Тэсты: offline/live маркеры (`slow`, `live_tts`)
- [x] 81 тест → 122 теста, все проходят
- [x] RHVoice backend (`--tts-backend rhvoice`)
- [x] Unified `--voice` (показывает голоса edge-tts + RHVoice)
- [x] Фильтрация списка голосов по `--lang`

---

## Priorities

### ✅ 1. Исправить латентный crash при отсутствии `langdetect`

- Priority: **critical**
- Cost: low
- Risk: low

**Проблема:** `rusa_subtitle.py` делает `from rusa_shared import LangDetectException, detect`. Если `langdetect` не установлен, эти имена не определены в `rusa_shared` → `ImportError` при старте.

**Решение:**
- Вариант A: обернуть импорт в `try/except ImportError` в `rusa_subtitle.py`
- Вариант B: определить заглушки `LangDetectException = Exception` и `detect = None` в `rusa_shared` при отсутствии `langdetect`

**Проверка:** `python3 -c "from rusa_subtitle import detect_language_from_srt"` без `langdetect` в окружении.

---

### ✅ 2. Убрать мёртвый код и неиспользуемые импорты

- Priority: **high**
- Cost: low
- Risk: low

#### 2a. Мёртвые импорты в `rusa_shared.py`
- `import textwrap` (строка 10) — не используется
- `import wave` (строка 12) — не используется
- `from pathlib import Path` (строка 13) — не используется

#### 2b. Мёртвая фикстура `tmp_wav` в `conftest.py`
- Определена на строках 67–73, ни один тест не использует

#### 2c. Неиспользуемые импорты в `conftest.py`
- `import json` — не используется
- `import tempfile` — используется только мёртвой `tmp_wav`

#### 2d. `import textwrap` в конце файла `conftest.py`
- Строка 173, расположен после использования в фикстурах. Перенести в начало.

---

### ✅ 3. Убрать пустой фасад `rusa_cache.py`

- Priority: **high**
- Cost: low
- Risk: low

**Проблема:** `rusa_cache.py` (38 строк) — pass-through фасад, который только реэкспортирует функции из `rusa_shared`. Не добавляет ценности.

**Решение:**
- Удалить `rusa_cache.py`
- В `rusa.py` импортировать `_tts_cache_path`, `_wav_cache_path` напрямую из `rusa_shared`
- Обновить `__all__` в `rusa_shared`, если нужен публичный API

---

### ✅ 4. Заменить `from rusa_shared import *` на явные импорты

- Priority: **high**
- Cost: low
- Risk: low

**Файл:** `rusa.py`, строка 23

Wildcard import вытягивает всё, включая `_CACHE_DISABLED`, `HAS_TQDM`, `HAS_LANGDETECT`.

**Решение:** Перечислить только нужные имена.

---

### ✅ 5. Заменить `__import__()` на обычные import

- Priority: **high**
- Cost: low
- Risk: low

**Файлы:**
- `rusa.py` строка 197: `__import__("shutil").rmtree(...)`
- `rusa_tts.py` строки 28, 58, 127: `__import__("re").finditer(...)`, `__import__("shutil").copy2(...)`

**Решение:** Перенести `import re`, `import shutil` в начало файлов.

---

### ✅ 6. Закэшировать `_check_ffmpeg_codec()`

- Priority: **high**
- Cost: low
- Risk: low

**Файл:** `rusa_mux.py`, строки 30–34

Каждый вызов запускает `ffmpeg -hide_banner -encoders`. При выборе кодеков вызывается до 4 раз.

**Решение:** Использовать `functools.lru_cache(maxsize=1)`.

---

### ✅ 7. Добавить поддержку `.rus.srt` и `.russian.srt` в детекцию языка

- Priority: **medium**
- Cost: low
- Risk: low

**Файл:** `rusa_subtitle.py`, строка 27

```python
match = re.match(r".*\.([a-z]{2})\.srt$", name)
```

Регекс ловит только 2-буквенные коды (`.ru.srt`), но не `.rus.srt` (3 буквы).

**Решение:** Расширить до `r".*\.([a-z]{2,7})\.srt$"` и добавить маппинг: `rus → ru`, `russian → ru`, `english → en`, `hebrew → he` и т.д.

---

### ✅ 8. Добавить `--version` в CLI

- Priority: **medium**
- Cost: low
- Risk: low

**Файлы:** `rusa_cli.py`, `pyproject.toml`

Версия `1.0.0` есть в `pyproject.toml`, но CLI не отдаёт её.

**Решение:** `parser.add_argument("--version", action="version", version="rusa 1.0.0")`

---

### ✅ 9. Исправить legacy build-backend в `pyproject.toml`

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

### ✅ 10. TypedDict для Entry вместо `dict`

- Priority: **medium**
- Cost: low
- Risk: low

**Файл:** `rusa_subtitle.py`, строка 22

```python
Entry = dict  # {"idx": int, "start_ms": int, "end_ms": int, "text": str}
```

**Решение:** Заменить на `TypedDict`:

```python
from typing import TypedDict
class Entry(TypedDict):
    idx: int
    start_ms: int
    end_ms: int
    text: str
```

---

### ✅ 11. Устранить дублирование `make_sine_wav`

- Priority: **medium**
- Cost: low
- Risk: low

**Файлы:** `conftest.py` (строки 75–97) и `test_assembly.py` (строки 8–29)

Две идентичные копии функции.

**Решение:** Удалить из `test_assembly.py`, все импорты перенаправить на `conftest.make_sine_wav`. Или вынести в отдельный helper-модуль.

---

### ✅ 12. Добавить `__all__` во все модули

- Priority: **medium**
- Cost: low
- Risk: low

**Файлы:** Все `.py` модули (кроме `rusa_cache.py`, который будет удалён).

`from rusa_shared import *` сейчас вытягивает приватные переменные.

**Решение:** В каждом модуле определить `__all__` с явным списком публичных имён.

---

### ✅ 13. Добавить LRU-eviction для кэша

- Priority: **low**
- Cost: medium
- Risk: low

**Файл:** `rusa_shared.py` (cache helpers)

Сейчас кэш только растёт. Нужна автоматическая очистка при превышении лимита.

**Возможные решения:**
- `RUSA_CACHE_MAX_SIZE` переменная окружения (по умолч. 2GB)
- При записи нового файла проверять общий размер; если превышен — удалять самые старые файлы по mtime
- Или делегировать очистку `--cache-clear` / внешнему cron

---

### ✅ 14. Добавить unit-тесты на `_run_loudnorm`, `_run_dynaudnorm`, `_check_ffmpeg_codec`, `list_voices`, `shell`, `which`, `die`

- Priority: **low**
- Cost: medium
- Risk: low

**Файлы:** `tests/`

Сейчас эти функции покрыты только косвенно (через регрессионные тесты). Прямые unit-тесты с fake-subprocess повысят надёжность при рефакторинге.

---

### ✅ 15. Исправить fallback `_get_codec()` при неизвестном кодеке

- Priority: **low**
- Cost: low
- Risk: low

**Файл:** `rusa_mux.py`, строка 24–27

Если кодек не найден в `CODEC_MAP`, возвращается `("libopus", "64k", ".opus")` вне зависимости от запроса.

**Решение:** Лучше вернуть `None` и дать понятную ошибку на стороне вызова, либо выкинуть `KeyError` с внятным сообщением.

---

### ✅ 16. Перенести документацию в `doc/`

- Priority: **low**
- Cost: low
- Risk: low

**Текущая структура:**
```
/rusa/
  roadmap.md          ← здесь
  implementation_plan.md
  README.md
```

**Цель:**
```
/rusa/
  doc/
    roadmap.md
    implementation_plan.md
  README.md
```

**Решение:**
- Создать `doc/`
- Перенести `roadmap.md` → `doc/roadmap.md`
- Перенести `implementation_plan.md` → `doc/implementation_plan.md`
- В корневом `README.md` добавить секцию со ссылками: `См. doc/roadmap.md и doc/implementation_plan.md`
- Удалить исходные файлы из корня

---

### ✅ 17. Добавить `.gitignore` для артефактов сборки и дистрибуции

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

### ✅ 18. RHVoice backend — локальный TTS

- `--tts-backend rhvoice` — RHVoice через subprocess
- Унифицированный `--voice` показывает голоса всех установленных бэкэндов
- Фильтрация по `--lang` для показа голосов
- Кэш разделён по бэкэнду
- 122 теста, все проходят

---

## Suggested Next Order

1. 🔴 **langdetect crash fix** — критическая регрессия
2. 🟡 **Мёртвый код, `rusa_cache.py`, wildcard import, `__import__()`** — быстрые чистки
3. 🟡 **Кэш `_check_ffmpeg_codec`** — микро-оптимизация
4. 🟠 **`.rus.srt` / `--version` / `TypedDict` / build-backend** — средний приоритет
5. 🟠 **Deduplicate `make_sine_wav`, `__all__`** — гигиена кода
6. 🟢 **LRU eviction, doc/, тесты, fallback, .gitignore** — низкий приоритет

## Notes

- После каждого изменения — полный прогон тестов: `PYTHONDONTWRITEBYTECODE=1 pytest -q tests/`
- Офлайн-прогон: `PYTHONDONTWRITEBYTECODE=1 pytest -q -m 'not slow and not live_tts' tests/`
- Фикстуры генерируются автоматически; принудительно: `python3 tests/generate_fixtures.py`
