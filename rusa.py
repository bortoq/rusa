#!/usr/bin/env python3
"""rusa — Russian Voiceover for Movies."""

import os
import shutil
import subprocess
import sys
import tempfile
import time

import rusa_audio
import rusa_mux
import rusa_shared
from rusa_audio import step_assemble, step_convert_wav
from rusa_cache import (
    clear_cache,
    print_cache_stats,
    print_timing_summary,
    tts_cache_path as _tts_cache_path,
    wav_cache_path as _wav_cache_path,
)
from rusa_cli import build_parser as _build_parser_impl, list_voices
from rusa_mux import _check_ffmpeg_codec, _get_codec, step_mix_output
from rusa_shared import *
from rusa_subtitle import detect_language_from_srt, step_extract_subtitles, step_parse_srt, step_sync_alass
from rusa_tts import _split_text, step_generate_tts

_PARSER = None


def _get_parser():
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER


def _build_parser():
    return _build_parser_impl()


def _tts_cache_dir():
    return rusa_shared.tts_cache_dir()


def _copy_into_cache(src: str, cache_path: str | None) -> None:
    return rusa_shared.copy_into_cache(src, cache_path)


def _wav_cache_dir():
    return rusa_shared.wav_cache_dir()


def _file_sha256(path: str) -> str:
    return rusa_shared.file_sha256(path)


def main() -> None:
    args = _get_parser().parse_args(sys.argv[1:])
    prev_cache_disabled = rusa_shared._CACHE_DISABLED
    try:
        if args.voice == "__LIST__":
            list_voices()
        if args.cache_stats:
            print_cache_stats()
        if args.cache_clear:
            clear_cache()

        rusa_shared._CACHE_DISABLED = bool(args.no_cache)

        if not args.video:
            _get_parser().print_help()
            sys.exit(0)

        video = os.path.realpath(args.video)
        if not os.path.isfile(video):
            die(f"Файл не найден: {video}")

        which("ffmpeg")
        which("ffprobe")
        which("python3")
        rc = subprocess.run(["python3", "-m", "edge_tts", "--help"], check=False, capture_output=True)
        if rc.returncode != 0:
            die("edge-tts не установлен (pip install edge-tts)", EXIT_DEPENDENCY_ERROR)

        audio_fmt = "opus"
        audio_bitrate = "64"
        normalize = args.normalize
        for candidate in ("aac", "mp3", "opus", "ac3"):
            value = getattr(args, candidate, None)
            if value is not None:
                audio_fmt = candidate
                audio_bitrate = value
                break

        target_lang = None
        if args.lang:
            target_lang = normalize_lang_code(args.lang)
            if target_lang not in LANG_VOICE_MAP and not args.voice:
                die(
                    f"Язык '{args.lang}' не поддерживается для авто-выбора голоса. Укажите --voice явно.",
                    EXIT_USAGE_ERROR,
                )
            info(f"Язык субтитров: {target_lang}")
        elif args.voice:
            target_lang = voice_to_lang_code(args.voice)

        if args.voice:
            voice = args.voice
        elif target_lang and target_lang in LANG_VOICE_MAP:
            voice = LANG_VOICE_MAP[target_lang]
        else:
            voice = DEFAULT_VOICE

        rc_list = subprocess.run(["python3", "-m", "edge_tts", "--list-voices"], check=False, capture_output=True, text=True)
        if rc_list.returncode == 0 and voice not in rc_list.stdout:
            warn(f"Голос '{voice}' отсутствует в списке edge-tts --list-voices")
            warn("Возможно, он удалён Microsoft. Генерация может не работать.")

        if args.output:
            output = os.path.realpath(args.output)
        else:
            base = os.path.splitext(os.path.basename(video))[0]
            ext = CODEC_MAP[audio_fmt][2] if args.audio_only else ".mkv"
            output = os.path.join(os.path.dirname(video), f"{base}_dubbed{ext}")

        sync_str = "вкл" if args.sync else "выкл"
        codec_name, codec_bit, _ext = _get_codec(audio_fmt, audio_bitrate)
        info(
            f"Синхронизация: {sync_str} | Голос: {voice} | Кодек: {codec_name} {codec_bit} | "
            f"Темп: {args.speed}x | Оригинал: {args.orig_vol} | TTS: {args.tts_vol}"
        )
        if normalize:
            info(f"Нормализация: {normalize}")
        if args.no_cache:
            info("Кэш: выкл")
        if args.range_from or args.range_to:
            info(f"Диапазон субтитров: {args.range_from or 1}–{args.range_to or '...'}")
        if args.audio_only:
            info("Режим: только аудио")
        elif args.subs_mode != DEFAULT_SUBS_MODE:
            info(f"Субтитры: {args.subs_mode}")

        timings: list[tuple[str, float]] = []
        tmpdir = tempfile.mkdtemp(prefix="rusa_")
        try:
            started = time.perf_counter()
            subs_path = step_extract_subtitles(video, args.srt, tmpdir, target_lang)
            if args.voice is None and args.lang is None:
                detected = detect_language_from_srt(subs_path)
                if detected:
                    voice = detected
                    info(f"Язык определён: {voice}")
                else:
                    if HAS_LANGDETECT:
                        warn("Не удалось определить язык субтитров, использую голос по умолчанию")
                    else:
                        warn("langdetect не установлен (pip install langdetect), использую голос по умолчанию")
            if args.sync:
                subs_path = step_sync_alass(video, subs_path, tmpdir)
            entries, count = step_parse_srt(subs_path, args.range_from, args.range_to)
            if count == 0:
                die("Не удалось распарсить ни одного субтитра из SRT. Проверьте формат файла.", EXIT_SUBTITLE_ERROR)
            timings.append(("subtitles", time.perf_counter() - started))

            started = time.perf_counter()
            tts_results = step_generate_tts(entries, voice, args.threads, tmpdir)
            timings.append(("tts", time.perf_counter() - started))

            started = time.perf_counter()
            wav_results = step_convert_wav(tts_results, args.speed, tmpdir, args.threads)
            timings.append(("wav", time.perf_counter() - started))

            started = time.perf_counter()
            voiceover_wav = step_assemble(entries, wav_results, tmpdir)
            timings.append(("assemble", time.perf_counter() - started))

            voiceover_lang = lang_code_to_ffprobe_codes(target_lang)[0] if target_lang else "rus"
            started = time.perf_counter()
            step_mix_output(
                video,
                voiceover_wav,
                args.orig_vol,
                args.tts_vol,
                output,
                tmpdir,
                audio_fmt,
                audio_bitrate,
                normalize,
                args.audio_only,
                voiceover_lang,
                args.subs_mode,
            )
            timings.append(("mux", time.perf_counter() - started))
            print_timing_summary(timings)
        finally:
            if not args.keep_temp:
                shutil.rmtree(tmpdir, ignore_errors=True)
            elif os.path.isdir(tmpdir):
                info(f"Временные файлы: {tmpdir}")
    finally:
        rusa_shared._CACHE_DISABLED = prev_cache_disabled


if __name__ == "__main__":
    main()
