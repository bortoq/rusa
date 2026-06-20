#!/usr/bin/env python3
from __future__ import annotations
__all__ = ['step_assemble', 'step_convert_wav', 'list_voices', '_check_ffmpeg_codec', '_get_codec', 'step_mix_output', 'CODEC_MAP', 'DEFAULT_ORIG_VOL', 'DEFAULT_SPEED', 'DEFAULT_SUBS_MODE', 'DEFAULT_THREADS', 'DEFAULT_TTS_VOL', 'DEFAULT_VOICE', 'EXIT_CODEC_ERROR', 'EXIT_DEPENDENCY_ERROR', 'EXIT_RUNTIME_ERROR', 'EXIT_SUBTITLE_ERROR', 'EXIT_USAGE_ERROR', 'HAS_LANGDETECT', 'HAS_TQDM', 'LANG_VOICE_MAP', 'WAV_BPF', 'WAV_CHANNELS', 'WAV_FRAMERATE', 'WAV_HEADER_SIZE', 'WAV_SAMPLEWIDTH', 'clear_cache', 'copy_into_cache', 'die', 'err', 'file_sha256', 'info', 'lang_code_to_ffprobe_codes', 'normalize_lang_code', 'ok', 'print_cache_stats', 'print_timing_summary', 'tts_cache_dir', 'voice_to_lang_code', 'wav_cache_dir', 'warn', 'which', 'detect_language_from_srt', 'step_extract_subtitles', 'step_parse_srt', 'step_sync_alass', '_split_text', 'step_generate_tts', 'main']
"""rusa — CLI voiceover for movies and other videos.

Public API: all commonly-used names are re-exported from submodules.
Tests and external code should access everything through ``rusa.*``.
"""

import argparse
import os
import re
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
from rusa_shared import BACKEND_REGISTRY  # noqa: F401 — TTS backends
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
    print_doctor_report,
    print_timing_summary,
    tts_cache_dir,
    tts_cache_path as _tts_cache_path,
    voice_to_lang_code,
    wav_cache_dir,
    wav_cache_path as _wav_cache_path,
    warn,
    which,
    python_executable,
)
from rusa_subtitle import detect_language_from_srt, step_extract_subtitles, step_merge_srt_entries, step_parse_srt, step_sync_alass
from rusa_tts import _split_text, step_generate_tts

# ── Quality presets ───────────────────────────────────────────────────
# Each preset sets flags that can be overridden by explicit CLI args.
# Semantics: if the user explicitly passed a flag, it wins over the preset.
PRESET_MAP = {
    "youtube": {
        "aac": "192",
        "normalize": "fine",
        "speed": "1.5",
        "orig_vol": "0.65",
        "audio_only": False,
    },
    "tiktok": {
        "aac": "128",
        "normalize": "fine",
        "speed": "1.8",
        "orig_vol": "0.70",
        "audio_only": True,
    },
    "podcast": {
        "mp3": "128",
        "normalize": "fine",
        "speed": "1.5",
        "orig_vol": "0.50",
        "audio_only": True,
    },
    "cinema": {
        "opus": "96",
        "normalize": "fine",
        "speed": "1.3",
        "orig_vol": "0.50",
        "audio_only": False,
    },
}


def _explicit_flag(name: str, argv: list[str] | None = None) -> bool:
    """Return True if the user explicitly passed --flag or -f in argv.

    Uses sys.argv if argv is None (production), or a custom list (tests).
    """
    args_to_check = argv if argv is not None else sys.argv[1:]
    for a in args_to_check:
        if a.startswith('--'):
            if a.startswith(f'--{name}') or a.startswith(f'--{name.replace("_","-")}'):
                return True
        elif a.startswith('-') and not a.startswith('--'):
            # short flags: -o, -s
            if a[1:] == name[:1]:
                return True
    return False


def _apply_preset(args: argparse.Namespace, argv: list[str] | None = None) -> None:
    """Apply a quality preset.
    
    A preset sets sensible defaults, but explicitly-passed CLI flags
    always take precedence.

    Args:
        args: Parsed argparse namespace (will be modified in-place).
        argv: Optional custom argv (used by tests). Defaults to sys.argv[1:].
    """
    if not args.preset:
        return

    preset = PRESET_MAP[args.preset]

    # Codec: set only if no other codec flag was given
    codec_explicit = any(_explicit_flag(c, argv) for c in ("aac", "mp3", "opus", "ac3"))
    if not codec_explicit:
        for codec_flag in ("aac", "mp3", "opus", "ac3"):
            if codec_flag in preset:
                setattr(args, codec_flag, preset[codec_flag])
                break

    # Normalize
    if not _explicit_flag("normalize", argv) and "normalize" in preset:
        args.normalize = preset["normalize"]

    # Speed
    if not _explicit_flag("speed", argv) and "speed" in preset:
        args.speed = preset["speed"]

    # orig_vol
    if not _explicit_flag("orig_vol", argv) and "orig_vol" in preset:
        args.orig_vol = preset["orig_vol"]

    # audio-only
    if not _explicit_flag("audio_only", argv) and not _explicit_flag("audio-only", argv) and "audio_only" in preset:
        args.audio_only = preset["audio_only"]


_PARSER = None


def _get_parser():
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER


def _build_parser():
    return _build_parser_impl()


def _sanitize_filename_part(value: str) -> str:
    """Strip characters that are unsafe or path-like from a filename segment."""
    return re.sub(r"[^a-zA-Z0-9_-]", "", value).strip("_-")[:20] or "custom"


def _print_dry_run(args, backend_cls, voice, target_lang, output, entries):
    """Print a summary of what would be generated and exit."""
    print("Dry run plan:")
    print(f"  Engine: {backend_cls.name}")
    print(f"  Voice: {voice}")
    print(f"  Language: {target_lang or 'auto'}")
    print(f"  Output: {output}")
    print(f"  Subtitles: {len(entries)}")
    print(f"  Total text: {sum(len(e['text']) for e in entries)} chars")
    if args.audio_only:
        print("  Mode: audio only")
    if args.speed != DEFAULT_SPEED:
        print(f"  Speed: {args.speed}x")
    if args.normalize:
        print(f"  Normalize: {args.normalize}")
    print("Sample subtitles:")
    for entry in entries[:5]:
        text = entry['text'][:80]
        if len(entry['text']) > 80:
            text += "..."
        print(f"  #{entry['idx']} [{entry['start_ms']}ms]: {text}")
    sys.exit(0)


def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        args = _get_parser().parse_args(sys.argv[1:])
    _apply_preset(args, sys.argv[1:])
    prev_cache_disabled = _CACHE_DISABLED

    _save_terminal()
    rusa_shared._configure_stdio()
    atexit.register(_restore_terminal)
    import threading
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, rusa_shared._term_handler)
            signal.signal(signal.SIGTERM, rusa_shared._term_handler)
        except (RuntimeError, ValueError):
            pass
    try:
        if args.voice == "__LIST__":
            list_voices(args.lang, args.engine)
        if args.cache_stats:
            print_cache_stats()
        if args.cache_clear:
            clear_cache()

        if args.doctor:
            print_doctor_report()
        rusa_shared._CACHE_DISABLED = bool(args.no_cache)

        if not args.video:
            _get_parser().print_help()
            sys.exit(0)

        video = os.path.realpath(args.video)
        if not os.path.isfile(video):
            die(f"File not found: {video}")

        which("ffmpeg")
        which("ffprobe")
        python_executable()

        # Resolve TTS backend
        if args.tts_cmd:
            rusa_shared.CustomCmdBackend.set_template(args.tts_cmd)
            backend_cls = rusa_shared.CustomCmdBackend
        elif args.engine:
            engine_name = args.engine
            backend_cls = BACKEND_REGISTRY.get(engine_name)
            if backend_cls is None:
                die(f"Unknown TTS engine: {engine_name}", EXIT_USAGE_ERROR)
            if not backend_cls.is_available():
                die(f"TTS engine '{engine_name}' was not found in PATH", EXIT_DEPENDENCY_ERROR)
        else:
            backend_cls = rusa_shared.EdgeTtsBackend
            if not backend_cls.is_available():
                die("edge-tts is not installed (pip install edge-tts)", EXIT_DEPENDENCY_ERROR)

        audio_fmt = "opus"
        audio_bitrate = "64"
        normalize = args.normalize
        for candidate in ("aac", "mp3", "opus", "ac3"):
            value = getattr(args, candidate, None)
            if value is not None:
                audio_fmt = candidate
                audio_bitrate = value
                break

        if backend_cls.name == "custom" and not args.voice:
            die(
                "--tts-cmd requires an explicit --voice value.",
                EXIT_USAGE_ERROR,
            )

        target_lang = None
        if args.lang:
            target_lang = normalize_lang_code(args.lang)
            info(f"Subtitle language: {target_lang}")
        elif args.voice and backend_cls.name != "custom":
            target_lang = backend_cls.lang_from_voice(args.voice)

        if args.voice:
            voice = args.voice
        elif target_lang:
            default_voice = backend_cls.get_default_voice(target_lang)
            if default_voice is None:
                die(
                    f"Language '{target_lang}' is not supported by backend '{backend_cls.name}'. "
                    "Please pass --voice explicitly.",
                    EXIT_USAGE_ERROR,
                )
            voice = default_voice
        else:
            # Fallback: use backend's default for 'ru' if available
            voice = backend_cls.get_default_voice("ru") or DEFAULT_VOICE

        # Validate voice
        warning = backend_cls.validate_voice(voice)
        if warning:
            warn(warning)

        if args.output:
            output = os.path.realpath(args.output)
        else:
            base = os.path.splitext(os.path.basename(video))[0]
            ext = CODEC_MAP[audio_fmt][2] if args.audio_only else ".mkv"
            if target_lang:
                lang_suffix = target_lang
            elif backend_cls.name == "custom":
                lang_suffix = _sanitize_filename_part(voice)
            else:
                lang_suffix = backend_cls.lang_from_voice(voice)
            display_name = getattr(backend_cls, "_display_name", backend_cls.name)
            if callable(display_name):
                display_name = display_name()
            output = os.path.join(
                os.path.dirname(video),
                f"{base}_{display_name}_{lang_suffix}{ext}",
            )
        args.output = output

        if os.path.isfile(output):
            if args.overwrite:
                warn(f"Output file already exists: {output} (will overwrite)")
            else:
                die(
                    f"Output file already exists: {output}. "
                    "Use --overwrite to replace it, or -o to choose another name.",
                    EXIT_USAGE_ERROR,
                )

        sync_str = "on" if args.sync else "off"
        codec_info = _get_codec(audio_fmt, audio_bitrate)
        if codec_info is None:
            codec_name, codec_bit = audio_fmt, f"{audio_bitrate}k"
        else:
            codec_name, codec_bit = codec_info[0], codec_info[1]
        info(
            f"Sync: {sync_str} | Voice: {voice} | Codec: {codec_name} {codec_bit} | "
            f"Speed: {args.speed}x | Original: {args.orig_vol} | TTS: {args.tts_vol}"
        )
        if normalize:
            info(f"Normalization: {normalize}")
        if args.no_cache:
            info("Cache: off")
        if args.range_from or args.range_to:
            info(f"Subtitle range: {args.range_from or 1}-{args.range_to or '...'}")
        if args.audio_only:
            info("Mode: audio only")
        elif args.subs_mode != DEFAULT_SUBS_MODE:
            info(f"Subtitles: {args.subs_mode}")

        timings: list[tuple[str, float]] = []
        tmpdir = tempfile.mkdtemp(prefix="rusa_")
        try:
            started = time.perf_counter()
            subs_path = step_extract_subtitles(video, args.srt, tmpdir, target_lang)
            if args.voice is None and args.lang is None:
                if backend_cls.name == "custom":
                    die(
                        "For --tts-cmd, pass either --voice or --lang so rusa can resolve the subtitle language.",
                        EXIT_USAGE_ERROR,
                    )
                detected = detect_language_from_srt(subs_path)
                if detected:
                    # detected is an edge-tts voice name; extract lang, find voice for this backend
                    lang_code = voice_to_lang_code(detected)
                    voice = backend_cls.get_default_voice(lang_code) or detected
                    info(f"Detected subtitle language: {lang_code} -> voice: {voice}")
                else:
                    if HAS_LANGDETECT:
                        warn("Could not detect subtitle language. Using the default voice.")
                    else:
                        warn("langdetect is not installed (pip install langdetect). Using the default voice.")
            if args.sync:
                subs_path = step_sync_alass(video, subs_path, tmpdir)
            entries, count = step_parse_srt(subs_path, args.range_from, args.range_to)
            if args.preview is not None:
                preview_count = max(1, args.preview)
                entries = entries[:preview_count]
                count = len(entries)
                info(f"Preview mode: first {count} subtitles")
            if count == 0:
                die("Could not parse any subtitle entries from the SRT file. Please check the file format.", EXIT_SUBTITLE_ERROR)
            if args.dry_run:
                _print_dry_run(args, backend_cls, voice, target_lang, output, entries)
                return
            if args.merge_sentences:
                merged_count = len(entries)
                entries = step_merge_srt_entries(entries)
                if len(entries) < merged_count:
                    info(f"Merged {merged_count - len(entries)} split subtitle lines")
            timings.append(("subtitles", time.perf_counter() - started))

            started = time.perf_counter()
            tts_results = step_generate_tts(entries, voice, args.threads, tmpdir, backend_cls.name)
            timings.append(("tts", time.perf_counter() - started))

            started = time.perf_counter()
            wav_results = step_convert_wav(tts_results, args.speed, tmpdir, args.threads)
            timings.append(("wav", time.perf_counter() - started))

            started = time.perf_counter()
            voiceover_wav = step_assemble(entries, wav_results, tmpdir)
            timings.append(("assemble", time.perf_counter() - started))

            if target_lang:
                voiceover_lang = lang_code_to_ffprobe_codes(target_lang)[0]
            elif backend_cls.name == "custom":
                voiceover_lang = "und"
            else:
                voiceover_lang = "rus"
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
                info(f"Temporary files kept at: {tmpdir}")
    finally:
        rusa_shared._CACHE_DISABLED = prev_cache_disabled


if __name__ == "__main__":
    main()
