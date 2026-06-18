"""Reusable Gradio UI components for rusa WebUI."""
from __future__ import annotations

import gradio as gr

from webui.config import (
    AUDIO_CODECS,
    NORMALIZE_OPTIONS,
    SPEED_MAX,
    SPEED_MIN,
    SPEED_STEP,
    SUBS_MODES,
    VOLUME_MAX,
    VOLUME_MIN,
    VOLUME_STEP,
)


def create_video_input() -> gr.File:
    """File upload for input video."""
    return gr.File(
        label="Выберите видеофайл",
        file_types=[".mkv", ".mp4", ".avi", ".mov", ".webm"],
        file_count="single",
    )



def create_srt_input() -> gr.File:
    """Optional SRT subtitle file upload."""
    return gr.File(
        label="Файл субтитров .srt (опционально)",
        file_types=[".srt"],
        file_count="single",
    )


def create_lang_selector() -> gr.Dropdown:
    """Language dropdown for auto-voice selection."""
    return gr.Dropdown(
        label="Язык субтитров",
        info="Оставьте пустым для автоопределения",
        choices=[
            ("Русский", "ru"),
            ("English", "en"),
            ("Deutsch", "de"),
            ("Français", "fr"),
            ("Español", "es"),
            ("Italiano", "it"),
            ("Português", "pt"),
            ("日本語", "ja"),
            ("한국어", "ko"),
            ("中文", "zh"),
            ("العربية", "ar"),
            ("Türkçe", "tr"),
            ("Nederlands", "nl"),
            ("Polski", "pl"),
            ("Svenska", "sv"),
            ("Dansk", "da"),
            ("Suomi", "fi"),
            ("Norsk", "nb"),
            ("Čeština", "cs"),
            ("Magyar", "hu"),
            ("עברית", "he"),
            ("English (auto)", None),
        ],
        value=None,
    )


def create_voice_input() -> gr.Textbox:
    """Voice override (edge-tts voice name)."""
    return gr.Textbox(
        label="Голос (опционально)",
        info="Например: ru-RU-SvetlanaNeural. Оставьте пустым для автоопределения",
        placeholder="ru-RU-SvetlanaNeural",
    )


def create_tts_cmd_input() -> gr.Textbox:
    """Custom TTS command template."""
    return gr.Textbox(
        label="Произвольная TTS-команда (--tts-cmd)",
        info="{in} {out} {voice} — плейсхолдеры имени файла и голоса",
        placeholder="espeak-ng -w {out} -f {in} -v {voice}",
        lines=2,
    )


def create_codec_group() -> tuple:
    """Radio + dropdown for audio codec selection."""
    codec_names = {v["label"]: k for k, v in AUDIO_CODECS.items()}
    codec_radio = gr.Radio(
        choices=list(codec_names.keys()),
        label="Аудиокодек",
        value="Opus",
    )
    bitrate_dropdown = gr.Dropdown(
        label="Битрейт",
        choices=AUDIO_CODECS["opus"]["bitrates"],
        value=AUDIO_CODECS["opus"]["default"],
        allow_custom_value=True,
    )
    return codec_radio, bitrate_dropdown


def create_speed_slider() -> gr.Slider:
    return gr.Slider(
        minimum=SPEED_MIN,
        maximum=SPEED_MAX,
        step=SPEED_STEP,
        value=1.5,
        label="Темп речи TTS",
    )


def create_volume_sliders() -> tuple:
    orig = gr.Slider(
        minimum=VOLUME_MIN, maximum=VOLUME_MAX, step=VOLUME_STEP,
        value=0.65, label="Громкость оригинала",
    )
    tts = gr.Slider(
        minimum=VOLUME_MIN, maximum=VOLUME_MAX, step=VOLUME_STEP,
        value=0.93, label="Громкость TTS",
    )
    return orig, tts


def create_normalize_input() -> gr.Dropdown:
    return gr.Dropdown(
        label="Нормализация",
        choices=NORMALIZE_OPTIONS,
        value="",
    )


def create_subs_mode_input() -> gr.Dropdown:
    return gr.Dropdown(
        label="Режим субтитров",
        choices=[(m.capitalize(), m) for m in SUBS_MODES],
        value="auto",
    )


def create_advanced_checkboxes() -> tuple:
    sync = gr.Checkbox(label="Синхронизировать субтитры (alass)", value=False)
    audio_only = gr.Checkbox(label="Только аудио", value=False)
    keep_temp = gr.Checkbox(label="Не удалять временные файлы", value=False)
    no_cache = gr.Checkbox(label="Отключить кэш", value=False)
    return sync, audio_only, keep_temp, no_cache
