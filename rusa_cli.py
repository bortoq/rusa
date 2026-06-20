#!/usr/bin/env python3
from __future__ import annotations
"""CLI parser and voice-listing helpers for rusa."""
__all__ = ["build_parser", "list_voices"]

import argparse
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
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rusa",
        description="Create an AI voiceover track from subtitles and mix it into a video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
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
    parser.add_argument("video", nargs="?", help="Input video file")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("-s", "--srt", help="External subtitle file (.srt)")
    parser.add_argument(
        "--voice",
        nargs="?",
        const="__LIST__",
        default=None,
        help="TTS voice name. Without an argument, list voices. Use --lang to filter the list.",
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar="LANG",
        help="Subtitle language (ISO 639-1 code such as ru, en, he, de, fr). By default it is inferred from --voice.",
    )
    parser.add_argument("--speed", default=DEFAULT_SPEED, help=f"TTS speech speed (default: {DEFAULT_SPEED})")
    parser.add_argument("--orig-vol", default=DEFAULT_ORIG_VOL, help=f"Original audio volume 0.0-1.0 (default: {DEFAULT_ORIG_VOL})")
    parser.add_argument("--tts-vol", default=DEFAULT_TTS_VOL, help=f"Voiceover volume 0.0-1.0 (default: {DEFAULT_TTS_VOL})")
    parser.add_argument("--sync", action="store_true", help="Synchronize subtitles with alass")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help=f"Number of TTS worker threads (default: {DEFAULT_THREADS})")
    parser.add_argument("--cache-stats", action="store_true", help="Show TTS/WAV cache statistics and exit")
    parser.add_argument("--cache-clear", action="store_true", help="Clear TTS/WAV cache and exit")
    parser.add_argument("--no-cache", action="store_true", help="Disable TTS/WAV cache reads and writes for this run")
    parser.add_argument("--doctor", action="store_true", help="Check local runtime dependencies and environment, then exit")
    parser.add_argument("--version", action="version", version="rusa 0.1.0", help="Show version and exit")

    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--aac", nargs="?", const="128", metavar="BITRATE", help="Encode output audio as AAC (default bitrate: 128k)")
    fmt_group.add_argument("--mp3", nargs="?", const="192", metavar="BITRATE", help="Encode output audio as MP3 (default bitrate: 192k)")
    fmt_group.add_argument("--opus", nargs="?", const="64", metavar="BITRATE", help="Encode output audio as Opus (default bitrate: 64k)")
    fmt_group.add_argument("--ac3", nargs="?", const="448", metavar="BITRATE", help="Encode output audio as AC3 (default bitrate: 448k)")

    parser.add_argument("--from", type=int, default=None, metavar="N", dest="range_from", help="First subtitle index to process")
    parser.add_argument("--to", type=int, default=None, metavar="N", dest="range_to", help="Last subtitle index to process")
    parser.add_argument("--audio-only", action="store_true", help="Write audio output only (no video)")
    parser.add_argument(
        "--subs-mode",
        choices=["auto", "copy", "convert", "drop"],
        default=DEFAULT_SUBS_MODE,
        help="Subtitle handling in the output video: auto, copy, convert, or drop (default: auto)",
    )
    parser.add_argument(
        "--merge-sentences",
        action="store_true",
        default=True,
        help="Merge subtitle lines that look like one split sentence (default: on)",
    )
    parser.add_argument(
        "--no-merge-sentences",
        action="store_false",
        dest="merge_sentences",
        help="Do not merge split subtitle lines",
    )
    parser.add_argument(
        "--normalize",
        nargs="?",
        const="fine",
        choices=["fast", "fine"],
        help="Normalize output volume: fast or fine (default when flag is present: fine)",
    )
    parser.add_argument(
        "--tts-cmd",
        metavar="TEMPLATE",
        default="",
        help=(
            "Custom TTS command. {in} = input text file, {out} = output audio file, {voice} = --voice. "
            "Example: --tts-cmd 'espeak-ng -w {out} -f {in} -v {voice}'"
        ),
    )
    parser.add_argument(
        "--engine",
        metavar="ENGINE",
        default="",
        help="TTS engine (edge, piper, rhvoice, espeak, gtts, festival, or a custom engine from ~/.config/rusa/engines.yaml). Default: edge.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the generation plan without running TTS, conversion, or muxing",
    )
    parser.add_argument(
        "--preview",
        type=int,
        metavar="N",
        default=None,
        help="Process only the first N subtitle entries",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    parser.add_argument(
        "--preset",
        choices=["youtube", "tiktok", "podcast", "cinema"],
        default=None,
        help="Quality preset: youtube, tiktok, podcast, or cinema. Explicit flags still win.",
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
        print(f"Unknown TTS engine: {engine}")
        print(f"Available engines: {', '.join(sorted(BACKEND_REGISTRY))}")
        sys.exit(2)

    display_name = getattr(backend_cls, "_display_name", backend_cls.name)
    if callable(display_name):
        display_name = display_name()
    print(f"{CYAN}{display_name}:{NC}")
    voices = backend_cls.list_voices()
    if voices:
        for voice, _voice_lang in voices:
            voice_name = voice.split(":")[-1].strip() if ":" in voice else voice
            if lang and not voice_name.lower().startswith(f"{lang}"):
                continue
            print(f"  {voice_name}")
    else:
        print(f"  (no voices found for engine '{engine}', or its binary is missing from PATH)")

    sys.exit(0)
