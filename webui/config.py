"""WebUI configuration for rusa."""
from __future__ import annotations

# ── Server ────────────────────────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
DEFAULT_SHARE = False

# ── UI defaults ───────────────────────────────────────────────────────
DEFAULT_TITLE = "rusa — Закадровый перевод видео"
DEFAULT_DESCRIPTION = (
    "Загрузите видео и субтитры, выберите голос — rusa создаст "
    "закадровый перевод автоматически."
)

# ── Available audio codecs ────────────────────────────────────────────
AUDIO_CODECS = {
    "aac": {"label": "AAC", "default": "128", "bitrates": ["96", "128", "192", "256", "320"]},
    "mp3": {"label": "MP3", "default": "192", "bitrates": ["128", "192", "256", "320"]},
    "opus": {"label": "Opus", "default": "64", "bitrates": ["64", "96", "128", "160"]},
    "ac3": {"label": "AC3", "default": "448", "bitrates": ["384", "448", "640"]},
}

# ── Volume range ──────────────────────────────────────────────────────
VOLUME_MIN = 0.0
VOLUME_MAX = 2.0
VOLUME_STEP = 0.05

# ── Speed range ───────────────────────────────────────────────────────
SPEED_MIN = 0.5
SPEED_MAX = 3.0
SPEED_STEP = 0.1

# ── Subs mode ─────────────────────────────────────────────────────────
SUBS_MODES = ["auto", "copy", "convert", "drop"]

# ── Normalize ─────────────────────────────────────────────────────────
NORMALIZE_OPTIONS = [("Выкл", ""), ("Быстрая", "fast"), ("Точная", "fine")]
