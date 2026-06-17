#!/usr/bin/env python3
__all__ = ['step_assemble', 'step_convert_wav', 'list_voices', '_check_ffmpeg_codec', '_get_codec', 'step_mix_output', 'CODEC_MAP', 'DEFAULT_ORIG_VOL', 'DEFAULT_SPEED', 'DEFAULT_SUBS_MODE', 'DEFAULT_THREADS', 'DEFAULT_TTS_VOL', 'DEFAULT_VOICE', 'EXIT_CODEC_ERROR', 'EXIT_DEPENDENCY_ERROR', 'EXIT_RUNTIME_ERROR', 'EXIT_SUBTITLE_ERROR', 'EXIT_USAGE_ERROR', 'HAS_LANGDETECT', 'HAS_TQDM', 'LANG_VOICE_MAP', 'WAV_BPF', 'WAV_CHANNELS', 'WAV_FRAMERATE', 'WAV_HEADER_SIZE', 'WAV_SAMPLEWIDTH', 'clear_cache', 'copy_into_cache', 'die', 'err', 'file_sha256', 'info', 'lang_code_to_ffprobe_codes', 'normalize_lang_code', 'ok', 'print_cache_stats', 'print_timing_summary', 'tts_cache_dir', 'voice_to_lang_code', 'wav_cache_dir', 'warn', 'which', 'detect_language_from_srt', 'step_extract_subtitles', 'step_parse_srt', 'step_sync_alass', '_split_text', 'step_generate_tts', 'main']
"""rusa — Russian Voiceover for Movies.

Public API: all commonly-used names are re-exported from submodules.
Tests and external code should access everything through ``rusa.*``.
"""

import os
import shutil
import subprocess
import sys
import atexit
import signal
import tempfile
import time

import rusa_audio
import rusa_mux
import rusa_shared
from rusa_audio import step_assemble, step_convert_wav
from rusa_cli import build_parser as _build_parser_impl, list_voices
from rusa_mux import _check_ffmpeg_codec, _get_codec, step_mix_output
from rusa_shared import _restore_terminal, _save_terminal  # noqa: F401 — terminal guard
from rusa_shared import RHVOICE_AVAILABLE, RHVOICE_VOICES, list_rhvoices  # noqa: F401 — rhvoice
from rusa_shared import (          # noqa: F401 — re-exported as public API
    CODEC_MAP,
    DEFAULT_ORIG_VOL,
    DEFAULT_SPEED,
    DEFAULT_SUBS_MODE,
    DEFAULT_THREADS,
    DEFAULT_TTS_VOL,
    DEFAULT_VOICE,
    EXIT_CODEC_ERROR,
    EXIT_DEPENDENCY_ERROR,
    EXIT_RUNTIME_ERROR,
    EXIT_SUBTITLE_ERROR,
    EXIT_USAGE_ERROR,
    HAS_LANGDETECT,
    HAS_TQDM,
    LANG_VOICE_MAP,
    WAV_BPF,
    WAV_CHANNELS,
    WAV_FRAMERATE,
    WAV_HEADER_SIZE,
    WAV_SAMPLEWIDTH,
    _CACHE_DISABLED,
    clear_cache,
    copy_into_cache,
    die,
    err,
    file_sha256,
    info,
    lang_code_to_ffprobe_codes,
    normalize_lang_code,
    ok,
    print_cache_stats,
    print_timing_summary,
    tts_cache_dir,
    tts_cache_path as _tts_cache_path,
    voice_to_lang_code,
    wav_cache_dir,
    wav_cache_path as _wav_cache_path,
    warn,
    which,
)
from rusa_subtitle import detect_language_from_srt, step_extract_subtitles, step_merge_srt_entries, step_parse_srt, step_sync_alass
from rusa_tts import _split_text, step_generate_tts

_PARSER = None


def _get_parser():
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER


def _build_parser():
    return _build_parser_impl()


def main() -> None:
    args = _get_parser().parse_args(sys.argv[1:])
    prev_cache_disabled = _CACHE_DISABLED
    rusa_shared._probe_rhvoice()
    _save_terminal()
    atexit.register(_restore_terminal)
    signal.signal(signal.SIGINT, rusa_shared._term_handler)
    signal.signal(signal.SIGTERM, rusa_shared._term_handler)
    try:
        if args.voice == "__LIST__":
            list_voices(args.lang)
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
        if args.tts_backend != "rhvoice":
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

        if args.tts_backend != "rhvoice":
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
        codec_info = _get_codec(audio_fmt, audio_bitrate)
        if codec_info is None:
            codec_name, codec_bit = audio_fmt, f"{audio_bitrate}k"
        else:
            codec_name, codec_bit = codec_info[0], codec_info[1]
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
            if args.merge_sentences:
                merged_count = len(entries)
                entries = step_merge_srt_entries(entries)
                if len(entries) < merged_count:
                    info(f"Склеено {merged_count - len(entries)} разорванных реплик")
            timings.append(("subtitles", time.perf_counter() - started))

            started = time.perf_counter()
            tts_results = step_generate_tts(entries, voice, args.threads, tmpdir, args.tts_backend)
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
