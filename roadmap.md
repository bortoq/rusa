# rusa Roadmap

## Status

- Подтверждено направление: добавить `--subs-mode`
- Уже сделано:
  - устойчивый mux fallback для несовместимых subtitle codecs
  - параллельная конвертация `MP3 -> WAV`
  - persistent TTS cache

## Priorities

### 1. WAV Cache

- Priority: high
- Cost: low-medium
- Risk: low

Повторные запуски с тем же `--speed` не должны заново прогонять сотни сегментов через `ffmpeg`.

Идея:

- key: `tts_mp3_hash + speed + filter_version`
- cache payload:
  - final `wav`
  - optional sidecar metadata with `duration_ms`

Ожидаемый эффект:

- существенное ускорение повторных прогонов
- особенно полезно при подборе громкости, mux-настроек и контейнера

### 2. `--subs-mode` + Preflight Subtitle/Container Check

- Priority: high
- Cost: medium
- Risk: low

Сейчас логика сохранения субтитров полезная, но неявная. Пользователю нужен явный контракт.

Предлагаемый интерфейс:

- `--subs-mode auto`
- `--subs-mode copy`
- `--subs-mode convert`
- `--subs-mode drop`

Семантика:

- `auto`
  - текущее умное поведение
  - `copy -> convert -> drop`
- `copy`
  - только копировать исходные субтитры как есть
  - при несовместимости контейнера завершать процесс ошибкой
- `convert`
  - всегда перекодировать субтитры в совместимый формат
  - для `.mkv` по умолчанию это обычно `srt`
- `drop`
  - не переносить субтитры в выходной файл

Что еще сделать:

- заранее определять subtitle codec через `ffprobe`
- выбирать стратегию mux до финального `ffmpeg`, а не только по stderr fallback
- документировать поведение для `.mkv`, `.mp4` и `--audio-only`

### 3. Split `rusa.py` Into Modules

- Priority: high
- Cost: medium
- Risk: medium

Текущий файл монолитный. Дальнейшие изменения будут дорожать быстрее, чем добавление функций.

Предлагаемая структура:

- `cli.py`
- `subtitle.py`
- `tts.py`
- `audio.py`
- `mux.py`
- `cache.py`

Цели:

- упростить тестирование
- уменьшить риск регрессий
- изолировать TTS/cache/mux логику

### 4. Cache Management

- Priority: medium
- Cost: medium
- Risk: low

Сейчас кэш только растет. Нужны инструменты управления.

Минимальный набор:

- `rusa cache stats`
- `rusa cache clear`
- `--no-cache`
- size limit
- LRU eviction

### 5. Timing Summary / Profiling

- Priority: medium
- Cost: low
- Risk: low

После каждого прогона полезно печатать время по этапам.

Пример:

```text
subtitles: 2.1s
tts: 401.3s
wav: 60.8s
assemble: 14.0s
mux: 9.5s
```

Цель:

- принимать решения по оптимизации на реальных данных
- видеть эффект от кэша и числа потоков

### 6. Full Integration Tests Without Live `edge-tts`

- Priority: medium
- Cost: medium
- Risk: low

Нужен полностью локальный интеграционный путь без внешнего TTS-сервиса.

Идеи:

- fake TTS backend for tests
- deterministic fixture generation
- explicit separation between offline integration tests and live smoke tests

### 7. Memory / I/O Optimization in Assembly

- Priority: medium-high
- Cost: high
- Risk: medium-high

Длинные фильмы создают очень большой промежуточный `voiceover.wav`.

Возможные направления:

- chunked assembly
- more streaming-oriented write path
- later: ffmpeg-based timeline assembly instead of large intermediate WAV

### 8. Error UX and Exit Codes

- Priority: medium
- Cost: low
- Risk: low

Полезно улучшить:

- сообщения про missing encoder
- сообщения про subtitle/container mismatch
- сообщения про invalid/empty SRT
- более стабильные exit codes для автоматизации

## Suggested Next Order

1. `--subs-mode` + preflight subtitle/container strategy
2. WAV cache
3. split `rusa.py` into modules
4. cache management commands
5. timing summary

## Notes

- `--subs-mode` уже одобрен и может считаться следующим целевым feature track.
- Самая практичная ближайшая оптимизация после TTS cache — именно WAV cache.
