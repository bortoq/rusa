#!/usr/bin/env python3
from __future__ import annotations
"""CLI parser and voice-listing helpers for rusa."""
__all__ = ['build_parser', 'list_voices']

import argparse
import subprocess
import sys
import textwrap

from rusa_shared import (
    CYAN,
    DEFAULT_ORIG_VOL,
    DEFAULT_SPEED,
    DEFAULT_SUBS_MODE,
    DEFAULT_THREADS,
    DEFAULT_TTS_VOL,
    NC,
    EXIT_DEPENDENCY_ERROR,
    die,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rusa",
        description="Создать и добавить голосовой закадровый перевод к фильму",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Примеры:
              rusa movie.mkv
              rusa --voice ru-RU-DmitryNeural movie.mkv
              rusa -s subs.srt --speed 2.0 movie.mkv
              rusa --aac 192 --normalize movie.mkv
              rusa --from 10 --to 50 --audio-only movie.mkv
              rusa --lang he movie.mkv
              rusa --voice he-IL-HilaNeural --lang he movie.mkv
              rusa --engine piper --voice ru_RU-dmitri-medium movie.mkv
        """
        ),
    )
    parser.add_argument("video", nargs="?", help="Видеофайл")
    parser.add_argument("-o", "--output", help="Выходной файл")
    parser.add_argument("-s", "--srt", help="Файл субтитров .srt")
    parser.add_argument(
        "--voice",
        nargs="?",
        const="__LIST__",
        default=None,
        help="Голос TTS. Без аргумента — список доступных голосов. --lang фильтрует по языку. По умолчанию автоопределение по языку субтитров",
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar="LANG",
        help="Язык субтитров (код ISO 639-1: ru, en, he, de, fr, ...). По умолчанию определяется из голоса --voice.",
    )
    parser.add_argument("--speed", default=DEFAULT_SPEED, help=f"Темп речи TTS (по умолч. {DEFAULT_SPEED})")
    parser.add_argument("--orig-vol", default=DEFAULT_ORIG_VOL, help=f"Громкость оригинала 0.0–1.0 (по умолч. {DEFAULT_ORIG_VOL})")
    parser.add_argument("--tts-vol", default=DEFAULT_TTS_VOL, help=f"Громкость TTS 0.0–1.0 (по умолч. {DEFAULT_TTS_VOL})")
    parser.add_argument("--sync", action="store_true", help="Синхронизировать субтитры через alass")
    parser.add_argument("--keep-temp", action="store_true", help="Не удалять временные файлы")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help=f"Количество потоков TTS (по умолч. {DEFAULT_THREADS})")
    parser.add_argument("--cache-stats", action="store_true", help="Показать статистику TTS/WAV кэша и выйти")
    parser.add_argument("--cache-clear", action="store_true", help="Очистить TTS/WAV кэш и выйти")
    parser.add_argument("--no-cache", action="store_true", help="Не читать и не писать TTS/WAV кэш в этом запуске")
    parser.add_argument("--version", action="version", version="rusa 1.0.0", help="Показать версию и выйти")

    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--aac", nargs="?", const="128", metavar="BITRATE", help="Кодек AAC (по умолч. 128k)")
    fmt_group.add_argument("--mp3", nargs="?", const="192", metavar="BITRATE", help="Кодек MP3 (по умолч. 192k)")
    fmt_group.add_argument("--opus", nargs="?", const="64", metavar="BITRATE", help="Кодек Opus (по умолч. 64k)")
    fmt_group.add_argument("--ac3", nargs="?", const="448", metavar="BITRATE", help="Кодек AC3 (по умолч. 448k)")

    parser.add_argument("--from", type=int, default=None, metavar="N", dest="range_from", help="Начальный номер субтитра")
    parser.add_argument("--to", type=int, default=None, metavar="N", dest="range_to", help="Конечный номер субтитра")
    parser.add_argument("--audio-only", action="store_true", help="Только аудио (без видео)")
    parser.add_argument(
        "--subs-mode",
        choices=["auto", "copy", "convert", "drop"],
        default=DEFAULT_SUBS_MODE,
        help="Режим субтитров в выходном видео: auto|copy|convert|drop (по умолч. auto)",
    )
    parser.add_argument(
        "--merge-sentences",
        action="store_true",
        default=True,
        help="Склеивать разорванные реплики (по умолч. вкл)",
    )
    parser.add_argument(
        "--no-merge-sentences",
        action="store_false",
        dest="merge_sentences",
        help="Не склеивать разорванные реплики",
    )
    parser.add_argument(
        "--normalize",
        nargs="?",
        const="fine",
        choices=["fast", "fine"],
        help="Нормализация громкости: fast (быстро) или fine (точно, по умолч.)",
    )
    parser.add_argument(
        "--tts-cmd",
        metavar="ШАБЛОН",
        default="",
        help=(
            "Произвольная TTS-команда. {in} = файл с текстом, {out} = аудиовыход, {voice} = --voice. "
            "Пример: --tts-cmd 'espeak-ng -w {out} -f {in} -v {voice}'"
        ),
    )
    parser.add_argument(
        "--engine",
        metavar="ENGINE",
        default="",
        help="TTS-движок (edge, piper, rhvoice, espeak, gtts, festival или пользовательский из ~/.config/rusa/engines.yaml). По умолчанию edge.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать план генерации (голос, язык, файл, субтитры) без запуска TTS и рендера",
    )
    parser.add_argument(
        "--preview",
        type=int,
        metavar="N",
        default=None,
        help="Сгенерировать только первые N субтитров (preview-режим)",
    )
    parser.add_argument(
        "--webui",
        action="store_true",
        help="Запустить API сервер вместо CLI",
    )
    return parser


def list_voices(lang: str | None = None, engine: str | None = None) -> None:
    """Print available voices for the selected TTS engine."""
    from rusa_shared import BACKEND_REGISTRY, normalize_lang_code

    if lang:
        lang = normalize_lang_code(lang)

    engine = engine or "edge"
    backend_cls = BACKEND_REGISTRY.get(engine)
    if backend_cls is None:
        print(f"Неизвестный TTS-движок: {engine}")
        print(f"Доступные: {', '.join(sorted(BACKEND_REGISTRY))}")
        sys.exit(2)

    display_name = getattr(backend_cls, "_display_name", backend_cls.name)
    if callable(display_name):
        display_name = display_name()
    print(f"{CYAN}{display_name}:{NC}")
    voices = backend_cls.list_voices()
    if voices:
        for voice, voice_lang in voices:
            voice_name = voice.split(":")[-1].strip() if ":" in voice else voice
            if lang and not voice_name.lower().startswith(f"{lang}"):
                continue
            print(f"  {voice_name}")
    else:
        print(f"  (для движка '{engine}' не найдено голосов или бинарий отсутствует в PATH)")

    sys.exit(0)
