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
- [x] Unified `--voice` (фильтрация по `--lang`)
- [x] TTS Backend Abstraction — `BACKEND_REGISTRY`, `TtsBackend`, `EdgeTtsBackend`, `CustomCmdBackend`
- [x] `--tts-cmd` — произвольная TTS-команда (`{in}` `{out}` `{voice}`)
- [x] `_{backend}_{lang}` вместо `_dubbed` в имени выходного файла

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

### ✅ 18. CustomCmdBackend + удаление RHVoice + удаление --tts-backend

- `--tts-cmd` — произвольная TTS-команда с плейсхолдерами `{in}` `{out}` `{voice}`
- `CustomCmdBackend` — класс для пользовательских TTS-движков
- RHVoice удалён из встроенных бэкендов (доступен через `--tts-cmd`)
- `--tts-backend` удалён (единственный встроенный бэкенд — edge)

---

### ✅ 19. TTS Backend Abstraction + суффикс файла

- Введён базовый класс `TtsBackend` с методами `is_available()`, `list_voices()`, `get_default_voice()`, `lang_from_voice()`, `validate_voice()`, `generate()`
- `BACKEND_REGISTRY` — регистрация бэкендов по имени
- `EdgeTtsBackend` и `RhvoiceBackend` — конкретные реализации
- `rusa.py` не содержит `if backend == "rhvoice"` — всё через registry
- Суффикс выходного файла: `_{backend}_{lang}` (например, `_edge_ru`)

- `--tts-backend rhvoice` — RHVoice через subprocess
- Унифицированный `--voice` показывает голоса всех установленных бэкэндов
- Фильтрация по `--lang` для показа голосов
- Кэш разделён по бэкэнду
- 122 теста, все проходят

---

## Suggested Next Order

Все пункты выполнены. Проект в стабильном состоянии:
- Поддерживаемый бэкенд: `edge` (облачный, встроенный)
- Произвольные TTS-движки: `--tts-cmd` (любой внешний бинарник)
- Дальнейшее развитие: добавление новых бэкендов через `class NewBackend(TtsBackend)` + `register_backend()`



---

## Audit 2026-06-18 — Полный аудит проекта

**Статус:** APPROVED ✅. 129 офлайн-тестов + 4 live-теста, все проходят.

### Уже сделано (предыдущим аудитором)

- [x] `shlex.quote` для плейсхолдеров `{in}` `{out}` `{voice}` в `CustomCmdBackend.generate` — защита от shell-инъекций
- [x] `_sanitize_filename_part()` для `lang_suffix` в `CustomCmdBackend` — безопасные имена файлов
- [x] `voiceover_lang = "und"` для `--tts-cmd` без `--lang` — валидные ISO-коды в метаданных
- [x] Языковые алиасы: `norwegian` → `nb`, `norsk` → `nb`, `no` → `nb`
- [x] `__all__` во всех модулях (8/8)
- [x] `lru_cache` для `_check_ffmpeg_codec` — устранение множественных вызовов `ffmpeg -encoders`
- [x] `_get_codec` возвращает `None` вместо opus-fallback при неизвестном кодеке
- [x] Регекс детекции языка: `[a-z]{2,7}` + маппинг `rus→ru`, `russian→ru`, `english→en`, `hebrew→he`
- [x] `make_sine_wav` вынесена в `conftest.py`, удалено дублирование из `test_assembly.py`
- [x] `import textwrap` перенесён в начало `conftest.py`
- [x] Мёртвый код `if not output` удалён из `step_mix_output`
- [x] `_split_text` улучшен: разбиение после `[.!?…](\s|$)` вместо любого знака
- [x] `list_voices` фильтр исправлен: `startswith(f"{lang}-")` вместо `"-{lang}-" not in`
- [x] Тест `test_voice_resolution_with_external_srt` исправлен (не зависит от `langdetect`)
- [x] `README.en.md` — удалён флаг `--tts-backend`

### Priorities (новые)

#### ✅ 20. Удалить дублирующиеся roadmap.md и implementation_plan.md из корня

- Priority: **high**
- Cost: low
- Risk: low

**Проблема:** `roadmap.md` и `implementation_plan.md` лежат и в корне, и в `doc/`. Это дублирование, нарушающее roadmap #16.

**Решение:** Удалить root-копии. Каноничные файлы — `doc/roadmap.md` и `doc/implementation_plan.md`.

---

#### ✅ 21. Добавить предупреждение о перезаписи выходного файла

- Priority: **medium**
- Cost: low
- Risk: low

**Файл:** `rusa.py`, `main()`

**Проблема:** `rusa` перезаписывает выходной файл с `-y` ffmpeg без предупреждения.

**Решение:** Перед запуском ffmpeg проверять, существует ли `output`; если да — выводить предупреждение и спрашивать подтверждение (или просто предупреждать, если не `--yes`/`--overwrite`).

---

#### ✅ 22. Расширить `LANG_VOICE_MAP` для неподдерживаемых языков

- Priority: **medium**
- Cost: low
- Risk: low

**Файл:** `rusa_shared.py`

**Проблема:** Алиасы `ukrainian`, `hindi`, `indonesian`, `thai`, `vietnamese`, `greek`, `romanian`, `croatian`, `serbian`, `bulgarian`, `malay`, `slovak` ведут на ISO-коды, отсутствующие в `LANG_VOICE_MAP`, что вызывает ошибку "Язык не поддерживается".

**Решение:** Добавить соответствующие голоса Edge TTS для этих языков. Если голос неизвестен — убрать алиас или выдавать понятное сообщение.

---

#### 23. Рассмотреть полный отказ от `shell=True` в `CustomCmdBackend`

- Priority: **low**
- Cost: medium
- Risk: medium

**Файл:** `rusa_shared.py`, `CustomCmdBackend.generate`

**Проблема:** `shlex.quote` снижает риск shell-инъекций, но не устраняет его полностью. `shell=True` позволяет пайпы и редиректы в шаблоне пользователя, что удобно, но опасно.

**Решение:** 
- Вариант A: оставить `shell=True` + `shlex.quote` (текущий)
- Вариант B: разбирать шаблон на список аргументов, запускать с `shell=False` (безопаснее, но ломает пайпы)
- Вариант C: документировать риски и рекомендовать не использовать шаблоны с пайпами

---

## Remaining Items (из предыдущего аудита)

Эти пункты зафиксированы в `audit_report.md` и остаются актуальными для будущих итераций:

1. Добавить встроенные голоса Edge TTS для языков: uk, hi, id, th, vi, el, ro, hr, sr, bg, ms, sk
2. Добавить `--overwrite` / предупреждение о перезаписи выходного файла
3. Рассмотреть отказ от `shell=True` в `CustomCmdBackend`
4. Кэшировать результат `EdgeTtsBackend.validate_voice` (сейчас вызывает `--list-voices` каждый раз)
5. Унифицировать `cache_bucket_stats` (рекурсивный) и `_evict_oldest` (один уровень)
6. Вынести логику `print_cache_stats`/`clear_cache` отдельно от `sys.exit`



---

## 24. WebUI — Пользовательский интерфейс (Gradio)

- Priority: **medium**
- Статус: **планирование**
- Сложность: 15–19 человеко-дней
- Риск: средний

### Обоснование

Добавление WebUI сделает rusa доступной для пользователей без опыта работы с командной строкой,
а также упростит визуальный мониторинг прогресса обработки видео.

### Выбор фреймворка: Gradio ✅

| Критерий | Gradio | Streamlit | FastAPI+HTMX | NiceGUI |
|---|---|---|---|---|
| Скорость разработки | ★★★★★ | ★★★★ | ★★ | ★★★★ |
| Интеграция с кодом | ★★★★★ | ★★★★ | ★★★ | ★★★★ |
| Прогресс и файлы | ★★★★★ | ★★★★ | ★★★ | ★★★ |
| Простота деплоя | ★★★★★ | ★★★★ | ★★★ | ★★★★ |
| TTS/ML-сообщество | ★★★★★ | ★★★★★ | ★★★★ | ★★★ |

### Архитектура

```
rusa/
├── rusa.py                 # CLI entrypoint
├── webui/
│   ├── __init__.py
│   ├── app.py              # Главный Gradio app
│   ├── components.py       # Переиспользуемые компоненты UI
│   ├── config.py           # Настройки WebUI
│   └── utils.py            # Вспомогательные функции
├── engines.yaml
└── pyproject.toml
```

**Принцип:** WebUI вызывает существующие функции rusa, не дублируя логику.

### Фазы реализации

#### Фаза 1: Подготовка и архитектура (3–4 дня)

- [ ] Создать `webui/` пакет с модулями
- [ ] Добавить `gradio>=4.0` в `pyproject.toml` (опциональная зависимость)
- [ ] Создать `webui/app.py` — точка входа Gradio
- [ ] CLI-флаг `--webui` для запуска интерфейса

#### Фаза 2: Базовый интерфейс (5–6 дней)

- [ ] Загрузка видео и SRT (`gr.File`)
- [ ] Выбор языка и голоса (`gr.Dropdown`)
- [ ] Поле `--tts-cmd` с примерами (`gr.Textbox`)
- [ ] Настройки: громкость, скорость, кодек (`gr.Slider`)
- [ ] Запуск обработки с прогресс-баром (`gr.Button` + `gr.Progress`)

#### Фаза 3: Продвинутые функции (4–5 дней)

- [ ] Логи и этапы обработки в реальном времени
- [ ] Предпросмотр и скачивание результата
- [ ] История обработанных файлов
- [ ] Поддержка batch-обработки

#### Фаза 4: Полировка и интеграция (3–4 дня)

- [ ] Docker-образ с WebUI
- [ ] Документация по запуску
- [ ] Тестирование на Linux/macOS/Windows
- [ ] Обновление README

### MVP-фичи (первая версия)

Обязательно:
- Загрузка видео + SRT
- Выбор языка / голоса
- `--tts-cmd` с примерами
- Прогресс-бар с этапами
- Скачивание результата
- Логи в реальном времени

Опционально (позже):
- Сохранение пресетов
- Batch-режим
- Тёмная тема

### Потенциальные проблемы

| Проблема | Решение |
|----------|---------|
| Выделение памяти при long-running задачах | Использовать очереди / бэкграунд-воркеры |
| Два интерфейса (CLI + WebUI) нужно поддерживать | WebUI только вызывает core-функции, не дублирует |
| Прогресс-бар при многопоточном TTS | Публиковать обновления через `gr.Progress()` с колбэками |
| Зависимость от `gradio` увеличивает размер пакета | Сделать `gradio` extra-dep (`pip install rusa[webui]`) |


## Notes

- После каждого изменения — полный прогон тестов: `PYTHONDONTWRITEBYTECODE=1 pytest -q tests/`
- Офлайн-прогон: `PYTHONDONTWRITEBYTECODE=1 pytest -q -m 'not slow and not live_tts' tests/`
- Фикстуры генерируются автоматически; принудительно: `python3 tests/generate_fixtures.py`
