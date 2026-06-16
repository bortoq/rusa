#!/usr/bin/env python3
"""
rusa — Russian Voiceover for Movies

Создаёт голосовой закадровый перевод (voiceover) для видеофайлов.
Использует Microsoft Edge TTS для генерации речи по субтитрам,
накладывает её поверх оригинала с регулируемой громкостью и темпом.
"""

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Optional deps
HAS_TQDM = False
HAS_LANGDETECT = False
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    pass
try:
    from langdetect import detect, DetectorFactory, LangDetectException
    DetectorFactory.seed = 0
    HAS_LANGDETECT = True
except ImportError:
    pass

# ──────────────────────────────────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────────────────────────────────

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"
DEFAULT_SPEED = "1.5"
DEFAULT_ORIG_VOL = "0.65"
DEFAULT_TTS_VOL = "0.93"
DEFAULT_THREADS = 6
MAX_TTS_CHARS = 3000  # edge-tts limit

# Codec map: short_name -> (ffmpeg_codec, ffmpeg_container, file_ext, default_bitrate)
CODEC_MAP = {
    "aac":  ("aac",         "mkv",  ".aac",  "128"),
    "mp3":  ("libmp3lame",  "mkv",  ".mp3",  "192"),
    "opus": ("libopus",     "mkv",  ".opus", "64"),
    "ac3":  ("ac3",         "mkv",  ".ac3",  "448"),
}

# Language code -> voice (female default)
LANG_VOICE_MAP = {
    "ru": "ru-RU-SvetlanaNeural",
    "en": "en-US-AriaNeural",
    "de": "de-DE-KatjaNeural",
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "tr": "tr-TR-EmelNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-AgnieszkaNeural",
    "sv": "sv-SE-SofieNeural",
    "da": "da-DK-ChristelNeural",
    "fi": "fi-FI-NooraNeural",
    "nb": "nb-NO-PernilleNeural",
    "cs": "cs-CZ-VlastaNeural",
    "hu": "hu-HU-NoemiNeural",
}

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

WAV_CHANNELS = 2
WAV_SAMPLEWIDTH = 2  # s16le
WAV_FRAMERATE = 48000
WAV_BPF = WAV_CHANNELS * WAV_SAMPLEWIDTH
WAV_HEADER_SIZE = 44

# ──────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────

def info(msg: str) -> None:
    print(f"{CYAN}\u25b6{NC} {msg}")

def ok(msg: str) -> None:
    print(f"{GREEN}\u2713{NC} {msg}")

def warn(msg: str) -> None:
    print(f"{YELLOW}\u26a0{NC} {msg}")

def err(msg: str) -> None:
    print(f"{RED}\u2717{NC} {msg}", file=sys.stderr)

def die(msg: str) -> None:
    err(msg)
    sys.exit(1)

def which(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        die(f"{cmd} не найден в PATH")
    return exe

def shell(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    check = kwargs.pop("check", True)
    capture = kwargs.pop("capture_output", False)
    try:
        return subprocess.run(cmd, check=check, capture_output=capture, **kwargs)
    except subprocess.CalledProcessError as e:
        if e.stderr:
            sys.stderr.write(e.stderr.decode("utf-8", errors="replace"))
        die(f"\u041a\u043e\u043c\u0430\u043d\u0434\u0430 {' '.join(cmd)} \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c \u0441 \u043a\u043e\u0434\u043e\u043c {e.returncode}")
    except FileNotFoundError:
        die(f"\u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430: {cmd[0]}")
    except Exception as e:
        die(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044f {' '.join(cmd)}: {e}")

def shell_ok(cmd: list[str], **kwargs) -> bool:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, **kwargs)
        return r.returncode == 0
    except FileNotFoundError:
        return False

# ──────────────────────────────────────────────────────────────────────────
# Определение языка субтитров
# ──────────────────────────────────────────────────────────────────────────

def detect_language_from_srt(srt_path: str) -> str | None:
    """Определить голос по субтитрам. Возвращает voice или None."""
    # 1. По расширению файла: .ru.srt, .en.srt, .de.srt, …
    name = os.path.basename(srt_path)
    m = re.match(r'.*\.([a-z]{2})\.srt$', name)
    if m:
        code = m.group(1).lower()
        if code in LANG_VOICE_MAP:
            return LANG_VOICE_MAP[code]

    # 2. По содержимому через langdetect
    if not HAS_LANGDETECT:
        return None

    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            raw = f.read()
        # Remove timings and numbers, keep only text
        text = re.sub(r'\d+\s+[\d:,.\s\->]+\s+', '', raw)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Take first 5000 chars for detection
        text = text[:5000]
        if len(text) < 20:
            return None
        lang = detect(text)
        if lang in LANG_VOICE_MAP:
            return LANG_VOICE_MAP[lang]
    except (LangDetectException, UnicodeDecodeError, OSError):
        pass

    return None

# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

_PARSER = None

def _get_parser() -> argparse.ArgumentParser:
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rusa",
        description="\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0438 \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0439 \u0437\u0430\u043a\u0430\u0434\u0440\u043e\u0432\u044b\u0439 \u043f\u0435\u0440\u0435\u0432\u043e\u0434 \u043a \u0444\u0438\u043b\u044c\u043c\u0443",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            \u041f\u0440\u0438\u043c\u0435\u0440\u044b:
              rusa movie.mkv
              rusa --voice ru-RU-DmitryNeural movie.mkv
              rusa -s subs.srt --speed 2.0 movie.mkv
              rusa --aac 192 --normalize movie.mkv
              rusa --from 10 --to 50 --audio-only movie.mkv
        """),
    )
    parser.add_argument("video", nargs="?", help="\u0412\u0438\u0434\u0435\u043e\u0444\u0430\u0439\u043b")
    parser.add_argument("-o", "--output", help="\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439 \u0444\u0430\u0439\u043b")
    parser.add_argument("-s", "--srt", help="\u0424\u0430\u0439\u043b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 .srt")

    # Voice: --voice without arg -> list, --voice VOICE -> use it, default -> auto-detect then DEFAULT_VOICE
    parser.add_argument("--voice", nargs="?", const="__LIST__", default=None,
                        help="\u0413\u043e\u043b\u043e\u0441 edge-tts. \u0411\u0435\u0437 \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442\u0430 \u2014 \u0441\u043f\u0438\u0441\u043e\u043a \u0433\u043e\u043b\u043e\u0441\u043e\u0432. "
                             "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u0430\u0432\u0442\u043e\u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u0435 \u043f\u043e \u044f\u0437\u044b\u043a\u0443 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432")

    parser.add_argument("--speed", default=DEFAULT_SPEED,
                        help=f"\u0422\u0435\u043c\u043f \u0440\u0435\u0447\u0438 TTS (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. {DEFAULT_SPEED})")
    parser.add_argument("--orig-vol", default=DEFAULT_ORIG_VOL,
                        help=f"\u0413\u0440\u043e\u043c\u043a\u043e\u0441\u0442\u044c \u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u0430 0.0\u20131.0 (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. {DEFAULT_ORIG_VOL})")
    parser.add_argument("--tts-vol", default=DEFAULT_TTS_VOL,
                        help=f"\u0413\u0440\u043e\u043c\u043a\u043e\u0441\u0442\u044c TTS 0.0\u20131.0 (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. {DEFAULT_TTS_VOL})")
    parser.add_argument("--sync", action="store_true",
                        help="\u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b \u0447\u0435\u0440\u0435\u0437 alass")
    parser.add_argument("--keep-temp", action="store_true",
                        help="\u041d\u0435 \u0443\u0434\u0430\u043b\u044f\u0442\u044c \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0444\u0430\u0439\u043b\u044b")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS,
                        help=f"\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u043f\u043e\u0442\u043e\u043a\u043e\u0432 TTS (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. {DEFAULT_THREADS})")

    # Audio format (mutually exclusive)
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--aac", nargs="?", const="128", metavar="BITRATE",
                           help="\u041a\u043e\u0434\u0435\u043a AAC (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. 128k)")
    fmt_group.add_argument("--mp3", nargs="?", const="192", metavar="BITRATE",
                           help="\u041a\u043e\u0434\u0435\u043a MP3 (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. 192k)")
    fmt_group.add_argument("--opus", nargs="?", const="64", metavar="BITRATE",
                           help="\u041a\u043e\u0434\u0435\u043a Opus (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. 64k)")
    fmt_group.add_argument("--ac3", nargs="?", const="448", metavar="BITRATE",
                           help="\u041a\u043e\u0434\u0435\u043a AC3 (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. 448k)")

    # Range
    parser.add_argument("--from", type=int, default=None, metavar="N",
                        dest="range_from",
                        help="\u041d\u0430\u0447\u0430\u043b\u044c\u043d\u044b\u0439 \u043d\u043e\u043c\u0435\u0440 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u0430")
    parser.add_argument("--to", type=int, default=None, metavar="N",
                        dest="range_to",
                        help="\u041a\u043e\u043d\u0435\u0447\u043d\u044b\u0439 \u043d\u043e\u043c\u0435\u0440 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u0430")

    # Audio-only
    parser.add_argument("--audio-only", action="store_true",
                        help="\u0422\u043e\u043b\u044c\u043a\u043e \u0430\u0443\u0434\u0438\u043e (\u0431\u0435\u0437 \u0432\u0438\u0434\u0435\u043e)")

    # Normalize
    parser.add_argument("--normalize", nargs="?", const="fine",
                        choices=["fast", "fine"],
                        help="\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0433\u0440\u043e\u043c\u043a\u043e\u0441\u0442\u0438: "
                             "fast (\u0431\u044b\u0441\u0442\u0440\u043e) \u0438\u043b\u0438 fine (\u0442\u043e\u0447\u043d\u043e, \u043f\u043e \u0443\u043c\u043e\u043b\u0447.)")

    return parser

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 1: \u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b
# ──────────────────────────────────────────────────────────────────────────

def step_extract_subtitles(video: str, srt_file: str | None, tmpdir: str) -> str:
    dest = os.path.join(tmpdir, "subtitles.srt")
    if srt_file:
        if not os.path.isfile(srt_file):
            die(f"\u0424\u0430\u0439\u043b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d: {srt_file}")
        info(f"\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b: {srt_file}")
        shutil.copy2(srt_file, dest)
        ok(f"\u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b: {sum(1 for _ in open(dest, encoding='utf-8'))} \u0441\u0442\u0440\u043e\u043a")
        return dest

    info("\u0418\u0437\u0432\u043b\u0435\u0447\u0435\u043d\u0438\u0435 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0438\u0437 \u0432\u0438\u0434\u0435\u043e...")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream=index:stream_tags=language",
         "-of", "csv=p=0", video],
        capture_output=True, text=True, check=False
    )
    found = 0
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) != 2:
                continue
            idx = parts[0].strip()
            lang = parts[1].strip().lower()
            if lang in ("rus", "ru", "russian"):
                info(f"  \u041d\u0430\u0439\u0434\u0435\u043d \u043f\u043e\u0442\u043e\u043a \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 #{idx} ({lang}), \u0438\u0437\u0432\u043b\u0435\u043a\u0430\u044e...")
                rc = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", video,
                     "-map", f"0:{idx}", dest],
                    check=False, capture_output=True
                )
                if rc.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0:
                    found = 1
                    break

    if not found:
        base = os.path.splitext(video)[0]
        for ext in [".rus.srt", ".ru.srt", ".russian.srt", ".srt"]:
            cand = base + ext
            if os.path.isfile(cand):
                shutil.copy2(cand, dest)
                found = 1
                break

    if not found:
        die("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b. \u0423\u043a\u0430\u0436\u0438\u0442\u0435 -s <file.srt>")
    ok(f"\u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b: {sum(1 for _ in open(dest, encoding='utf-8'))} \u0441\u0442\u0440\u043e\u043a")
    return dest

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 2: \u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f alass
# ──────────────────────────────────────────────────────────────────────────

def step_sync_alass(video: str, subs_path: str, tmpdir: str) -> str:
    if not shutil.which("alass"):
        warn("alass \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d, \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u0430")
        return subs_path
    info("\u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0447\u0435\u0440\u0435\u0437 alass...")
    synced = os.path.join(tmpdir, "synced.srt")
    rc = subprocess.run(["alass", video, subs_path, synced], check=False, capture_output=True)
    if rc.returncode == 0 and os.path.isfile(synced) and os.path.getsize(synced) > 0:
        shutil.copy2(synced, subs_path)
        ok("\u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u044b")
    else:
        warn("alass \u043d\u0435 \u0443\u0434\u0430\u043b\u0441\u044f, \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0438\u0441\u0445\u043e\u0434\u043d\u044b\u0435 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b")
    return subs_path

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 3: \u041f\u0430\u0440\u0441\u0438\u043d\u0433 SRT
# ──────────────────────────────────────────────────────────────────────────

Entry = dict  # {"idx": int, "start_ms": int, "end_ms": int, "text": str}

def step_parse_srt(subs_path: str, range_from: int | None, range_to: int | None) -> tuple[list[Entry], int]:
    info("\u041f\u0430\u0440\u0441\u0438\u043d\u0433 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432...")
    with open(subs_path, "r", encoding="utf-8") as f:
        subs = f.read().lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", subs.strip())
    entries: list[Entry] = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        m = re.match(
            r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
            lines[1],
        )
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        def to_ms(h, mm, s, ms):
            return h * 3600000 + mm * 60000 + s * 1000 + ms
        start_ms = to_ms(*g[:4])
        end_ms = to_ms(*g[4:])
        text = " ".join(lines[2:])
        text = re.sub(r"\s+", " ", text).strip()
        entries.append({"idx": idx, "start_ms": start_ms, "end_ms": end_ms, "text": text})

    # Apply range filter
    if range_from is not None or range_to is not None:
        lo = range_from or 1
        hi = range_to or len(entries)
        entries = [e for e in entries if lo <= e["idx"] <= hi]
        if not entries:
            die(f"\u041d\u0435\u0442 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0432 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u0435 {lo}\u2013{hi}")
        # Normalize indices so file naming stays clean
        for i, e in enumerate(entries, 1):
            e["idx"] = i

    count = len(entries)
    ok(f"{count} \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432" + (f" (\u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d {lo}\u2013{hi})" if range_from or range_to else ""))
    return entries, count

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 4: \u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f TTS
# ──────────────────────────────────────────────────────────────────────────

def _split_text(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
    """Split long text into chunks at punctuation boundaries."""
    if len(text) <= max_chars:
        return [text]
    parts = []
    while len(text) > max_chars:
        chunk = text[:max_chars]
        # Find last sentence-ending punctuation in chunk
        split_at = -1
        for m in re.finditer(r'[.!?\u2026]', chunk):
            split_at = m.end()
        if split_at == -1:
            # No punctuation, split at last space
            split_at = chunk.rfind(' ')
            if split_at == -1:
                split_at = max_chars
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts

def step_generate_tts(entries: list[Entry], voice: str, threads: int,
                      tmpdir: str) -> list[tuple[int, str]]:
    info(f"\u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f TTS ({len(entries)} \u0444\u0430\u0439\u043b\u043e\u0432, {threads} \u043f\u043e\u0442\u043e\u043a\u043e\u0432)...")
    tts_dir = os.path.join(tmpdir, "tts")
    os.makedirs(tts_dir, exist_ok=True)
    MAX_RETRIES = 3

    def gen_one(entry: Entry) -> tuple[int, str | None]:
        idx = entry["idx"]
        text = entry["text"]
        if not text or not text.strip():
            return idx, None

        parts = _split_text(text)
        out = os.path.join(tts_dir, f"batch_{idx:04d}.mp3")

        # Single part — generate directly
        if len(parts) == 1:
            for attempt in range(1, MAX_RETRIES + 1):
                if os.path.isfile(out) and os.path.getsize(out) > 100:
                    return idx, out
                try:
                    rc = subprocess.run(
                        ["edge-tts", "--voice", voice, "--text", parts[0], "--write-media", out],
                        capture_output=True, timeout=180, check=False,
                    ).returncode
                    if rc == 0 and os.path.isfile(out) and os.path.getsize(out) > 100:
                        return idx, out
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                if attempt < MAX_RETRIES:
                    time.sleep(1.5 * attempt)
            return idx, None

        # Multiple parts — generate + concat
        part_files: list[str] = []
        for pi, part in enumerate(parts):
            p_out = os.path.join(tts_dir, f"batch_{idx:04d}_p{pi}.mp3")
            generated = False
            for attempt in range(1, MAX_RETRIES + 1):
                if os.path.isfile(p_out) and os.path.getsize(p_out) > 100:
                    generated = True
                    break
                try:
                    rc = subprocess.run(
                        ["edge-tts", "--voice", voice, "--text", part, "--write-media", p_out],
                        capture_output=True, timeout=180, check=False,
                    ).returncode
                    if rc == 0 and os.path.isfile(p_out) and os.path.getsize(p_out) > 100:
                        generated = True
                        break
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                if attempt < MAX_RETRIES:
                    time.sleep(1.5 * attempt)
            if generated:
                part_files.append(p_out)

        if not part_files:
            return idx, None

        # Concat parts with ffmpeg
        concat_list = os.path.join(tts_dir, f"batch_{idx:04d}_list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for pf in part_files:
                f.write(f"file '{pf}'\n")
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", out],
            check=False, capture_output=True,
        )
        if rc.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 100:
            return idx, out
        # Fallback: use first part only
        if part_files:
            shutil.copy2(part_files[0], out)
            if os.path.getsize(out) > 100:
                return idx, out
        return idx, None

    total = len(entries)
    results: list[tuple[int, str]] = []
    done = 0

    pbar = tqdm(total=total, desc="  TTS", unit="sub") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = {ex.submit(gen_one, e): e for e in entries}
        for f in as_completed(futures):
            done += 1
            idx, path = f.result()
            if path:
                results.append((idx, path))
            if pbar:
                pbar.update(1)
            elif done % 30 == 0 or done == total:
                print(f"  [{done}/{total}]")

    if pbar:
        pbar.close()

    ok(f"TTS: {len(results)}/{total}")
    if not results:
        die("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043d\u0438 \u043e\u0434\u043d\u043e\u0433\u043e TTS-\u0444\u0430\u0439\u043b\u0430")
    return results

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 5: MP3 \u2192 WAV + atempo + \u043e\u0431\u0440\u0435\u0437\u043a\u0430 \u0442\u0438\u0448\u0438\u043d\u044b
# ──────────────────────────────────────────────────────────────────────────

def step_convert_wav(tts_results: list[tuple[int, str]], speed: str,
                     tmpdir: str) -> list[tuple[int, str, float]]:
    info(f"\u041a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u044f MP3 \u2192 WAV + atempo={speed}x...")
    wav_dir = os.path.join(tmpdir, "wav")
    os.makedirs(wav_dir, exist_ok=True)
    results: list[tuple[int, str, float]] = []
    speed_val = float(speed)

    # Build atempo filter chain
    if speed_val > 2.0:
        chain = []
        remaining = speed_val
        while remaining > 2.0:
            chain.append("atempo=2.0")
            remaining /= 2.0
        chain.append(f"atempo={remaining:.6f}")
        tempo_filter = ",".join(chain)
    else:
        tempo_filter = f"atempo={speed_val:.6f}"

    iterator = tqdm(tts_results, desc="  WAV", unit="sub") if HAS_TQDM else tts_results
    for idx, mp3_path in iterator:
        wav_path = os.path.join(wav_dir, f"batch_{idx:04d}.wav")
        # atempo + trim silence from both ends (start + stop)
        filter_str = (
            f"{tempo_filter},"
            f"silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01:"
            f"stop_periods=1:stop_threshold=0.0018:stop_silence=0.01"
        )
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", mp3_path,
             "-af", filter_str,
             "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE),
             "-sample_fmt", "s16", wav_path],
            check=False, capture_output=True,
        )
        if rc.returncode == 0 and os.path.isfile(wav_path) and os.path.getsize(wav_path) > 44:
            try:
                with wave.open(wav_path, "rb") as w:
                    frames = w.getnframes()
                    duration_ms = frames / WAV_FRAMERATE * 1000
                # Sanity check: reject near-silent files (duration < 50ms)
                if duration_ms >= 50:
                    results.append((idx, wav_path, duration_ms))
                else:
                    warn(f"  #{idx} too short ({duration_ms:.0f}ms), skipped")
            except Exception:
                results.append((idx, wav_path, 0))
        else:
            warn(f"  #{idx} \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c")
    ok(f"WAV (sped {speed}x): {len(results)}")
    return results

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 6: \u0421\u0431\u043e\u0440\u043a\u0430 voiceover
# ──────────────────────────────────────────────────────────────────────────

def step_assemble(entries: list[Entry], wav_results: list[tuple[int, str, float]],
                  tmpdir: str) -> str:
    out_path = os.path.join(tmpdir, "voiceover.wav")
    info("\u0421\u0431\u043e\u0440\u043a\u0430 voiceover...")
    wav_map: dict[int, tuple[str, float]] = {}
    for idx, path, dur in wav_results:
        wav_map[idx] = (path, dur)
    segments: list[dict] = []
    for e in entries:
        idx = e["idx"]
        if idx in wav_map:
            path, dur = wav_map[idx]
            if dur <= 0:
                continue  # \u043f\u0440\u043e\u043f\u0443\u0441\u043a\u0430\u0435\u043c \u043f\u0443\u0441\u0442\u044b\u0435 \u0441\u0435\u0433\u043c\u0435\u043d\u0442\u044b
            segments.append({"start_ms": e["start_ms"], "duration_ms": dur, "path": path})
    if not segments:
        die("\u041d\u0435\u0442 \u0441\u0435\u0433\u043c\u0435\u043d\u0442\u043e\u0432 \u0434\u043b\u044f \u0441\u0431\u043e\u0440\u043a\u0438")
    segments.sort(key=lambda s: s["start_ms"])
    max_end_ms = max(s["start_ms"] + s["duration_ms"] for s in segments)
    total_frames = int(max_end_ms * WAV_FRAMERATE / 1000)
    total_data_bytes = total_frames * WAV_BPF
    print(f"  \u0421\u0435\u0433\u043c\u0435\u043d\u0442\u043e\u0432: {len(segments)}, \u043c\u0430\u043a\u0441. \u0434\u043b\u0438\u0442.: {max_end_ms / 1000:.0f}s")

    # Pre-allocate WAV with silence
    with open(out_path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + total_data_bytes))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, WAV_CHANNELS, WAV_FRAMERATE,
                WAV_BPF * WAV_FRAMERATE, WAV_BPF, WAV_SAMPLEWIDTH * 8))
        f.write(b"data")
        f.write(struct.pack("<I", total_data_bytes))
        CHUNK = 10 * 1024 * 1024
        remaining = total_data_bytes
        while remaining > 0:
            n = min(remaining, CHUNK)
            f.write(b"\x00" * n)
            remaining -= n

    cur_frame = 0
    overlaps = 0
    actual_max_frame = 0
    with open(out_path, "rb+") as f:
        for i, seg in enumerate(segments, 1):
            sf = int(seg["start_ms"] * WAV_FRAMERATE / 1000)
            target = max(cur_frame, sf)
            if target > sf:
                overlaps += 1
            offset = WAV_HEADER_SIZE + target * WAV_BPF
            with wave.open(seg["path"], "rb") as w:
                frame_data = w.readframes(w.getnframes())
            f.seek(offset)
            f.write(frame_data)
            seg_end_frame = target + (len(frame_data) // WAV_BPF)
            if seg_end_frame > actual_max_frame:
                actual_max_frame = seg_end_frame
            cur_frame = seg_end_frame
            if not HAS_TQDM and (i % 100 == 0 or i == len(segments)):
                print(f"    ... {i}/{len(segments)}")

    # \u041e\u0431\u043d\u043e\u0432\u043b\u044f\u0435\u043c WAV-\u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a,
    # \u0435\u0441\u043b\u0438 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0439 \u043e\u0431\u044a\u0451\u043c \u0434\u0430\u043d\u043d\u044b\u0445
    # \u043f\u0440\u0435\u0432\u044b\u0441\u0438\u043b \u043f\u0440\u0435\u0434\u0432\u044b\u0434\u0435\u043b\u0435\u043d\u043d\u044b\u0439
    actual_data_bytes = actual_max_frame * WAV_BPF
    if actual_data_bytes > total_data_bytes:
        # \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u0438\u0448\u0438\u043d\u0443 \u0432 \u043a\u043e\u043d\u0435\u0446, \u0435\u0441\u043b\u0438 \u043d\u0443\u0436\u043d\u043e
        needed = WAV_HEADER_SIZE + actual_data_bytes
        cur_size = os.path.getsize(out_path)
        if needed > cur_size:
            with open(out_path, "ab") as f:
                f.write(b"\x00" * (needed - cur_size))
        with open(out_path, "rb+") as f:
            f.seek(4)
            f.write(struct.pack("<I", 36 + actual_data_bytes))
            f.seek(40)
            f.write(struct.pack("<I", actual_data_bytes))

    if overlaps:
        pct = overlaps * 100 // len(segments)
        print(f"  Перекрытий: {overlaps} ({pct}%)")
        if pct > 20:
            warn("Много перекрытий. "
                 "Попробуйте --speed больше "
                 "или --voice с более быстрым произношением")

    print(f"  Voiceover: {os.path.getsize(out_path) / 1024 / 1024:.0f} MB")
    ok("Voiceover собрано")
    return out_path
# \u0428\u0430\u0433 7: \u041c\u0438\u043a\u0441 + \u0432\u044b\u0432\u043e\u0434
# ──────────────────────────────────────────────────────────────────────────

# Map of codec short name -> (ffmpeg_codec, container, ext, default_bitrate)
# Re-using CODEC_MAP from top, but we need a lookup function
def _get_codec(codec_name: str, bitrate: str) -> tuple[str, str, str]:
    """Return (ffmpeg_codec_name, bitrate_arg, file_extension)."""
    entry = CODEC_MAP.get(codec_name)
    if not entry:
        return ("libopus", "64k", ".opus")
    return (entry[0], f"{bitrate}k", entry[2])

def _check_ffmpeg_codec(codec: str) -> bool:
    """Check if ffmpeg supports a given encoder."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        check=False, capture_output=True, text=True
    )
    if r.returncode != 0:
        return False
    return codec in r.stdout

def _run_loudnorm(in_wav: str, out_wav: str) -> bool:
    """Two-pass EBU R128 loudnorm."""
    # Pass 1: measure
    r1 = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav,
         "-af", "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
         "-f", "null", "-"],
        check=False, capture_output=True, text=True
    )
    if r1.returncode != 0:
        return False
    # Parse JSON from stderr (loudnorm prints to stderr)
    try:
        # Find JSON block in stderr
        stderr = r1.stderr
        json_start = stderr.find("{")
        json_end = stderr.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return False
        measured = json.loads(stderr[json_start:json_end])
        measured_i = measured.get("input_i", "-16.0")
        measured_lra = measured.get("input_lra", "11.0")
        measured_tp = measured.get("input_tp", "-1.5")
        measured_thresh = measured.get("input_thresh", "-21.0")
        offset = measured.get("target_offset", "0.0")
    except (json.JSONDecodeError, ValueError):
        return False

    # Pass 2: apply
    filter_expr = (
        f"loudnorm=I=-16:LRA=11:TP=-1.5:"
        f"measured_I={measured_i}:measured_LRA={measured_lra}:"
        f"measured_TP={measured_tp}:measured_thresh={measured_thresh}:"
        f"offset={offset}:print_format=summary"
    )
    r2 = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav,
         "-af", filter_expr,
         "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE),
         "-sample_fmt", "s16", out_wav],
        check=False, capture_output=True
    )
    return r2.returncode == 0 and os.path.isfile(out_wav) and os.path.getsize(out_wav) > 100

def _run_dynaudnorm(in_wav: str, out_wav: str) -> bool:
    """Fast single-pass dynamic normalization."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav,
         "-af", "dynaudnorm",
         "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE),
         "-sample_fmt", "s16", out_wav],
        check=False, capture_output=True
    )
    return r.returncode == 0 and os.path.isfile(out_wav) and os.path.getsize(out_wav) > 100

def step_mix_output(video: str, voiceover_wav: str, orig_vol: str, tts_vol: str,
                    output: str, tmpdir: str,
                    audio_fmt: str, audio_bitrate: str,
                    normalize: str | None, audio_only: bool) -> None:
    info("\u041c\u0438\u043a\u0441...")
    mixed = os.path.join(tmpdir, "mixed.wav")
    filter_expr = (
        f"[1:a]volume={orig_vol}[orig];"
        f"[2:a]volume={tts_vol}[tts];"
        f"[orig][tts]amix=inputs=2:duration=first:normalize=0[mixed]"
    )

    # Always mix to WAV first (3 inputs: video, video(orig audio), voiceover)
    rc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", video,
         "-i", video,
         "-i", voiceover_wav,
         "-filter_complex", filter_expr,
         "-map", "[mixed]",
         "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE),
         "-sample_fmt", "s16", mixed],
        check=False, capture_output=True
    )

    if rc.returncode != 0:
        err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
        die(f"\u041c\u0438\u043a\u0441 \u043d\u0435 \u0443\u0434\u0430\u043b\u0441\u044f: {err_text[:500]}")

    # Apply normalization if requested
    norm_applied = False
    if normalize:
        info(f"\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f ({normalize})...")
        if audio_only:
            norm_in = mixed
            norm_out = os.path.join(tmpdir, "normalized.wav")
        else:
            # mixed is already WAV, normalize directly
            norm_in = mixed
            norm_out = os.path.join(tmpdir, "normalized.wav")

        if normalize == "fine":
            norm_applied = _run_loudnorm(norm_in, norm_out)
            if not norm_applied:
                warn("loudnorm \u043d\u0435 \u0443\u0434\u0430\u043b\u0441\u044f, \u043f\u0440\u043e\u0431\u0443\u044e dynaudnorm...")
                norm_applied = _run_dynaudnorm(norm_in, norm_out)
        else:
            norm_applied = _run_dynaudnorm(norm_in, norm_out)

        if norm_applied:
            ok(f"\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430")
        else:
            warn("\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u043d\u0435 \u0443\u0434\u0430\u043b\u0430\u0441\u044c, \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u044e \u0431\u0435\u0437 \u043d\u0435\u0451")

    # Encode to final format
    ffmpeg_codec, bitrate_arg, ext = _get_codec(audio_fmt, audio_bitrate)

    # Check codec availability
    if not _check_ffmpeg_codec(ffmpeg_codec):
        # Build a helpful error message suggesting alternatives
        alt_suggestions = []
        for alt_name in CODEC_MAP:
            if alt_name == audio_fmt:
                continue
            alt_codec, alt_bitrate_default, _ = CODEC_MAP[alt_name]
            alt_codec_name = CODEC_MAP[alt_name][0]
            if _check_ffmpeg_codec(alt_codec_name):
                alt_suggestions.append(f"--{alt_name} {alt_bitrate_default}")
        msg = (
            f"\u041a\u043e\u0434\u0435\u043a {ffmpeg_codec} \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0432 \u0432\u0430\u0448\u0435\u0439 \u0441\u0431\u043e\u0440\u043a\u0435 ffmpeg.\n"
            f"\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u043e\u0440\u043c\u0430\u0442: {suggestions}"
        )
        die(msg)

    info(f"\u041a\u043e\u0434\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435: {ffmpeg_codec} {bitrate_arg}...")

    source = norm_out if norm_applied else mixed

    if audio_only:
        # Output standalone audio file
        if not output:
            base = os.path.splitext(os.path.basename(video))[0]
            output = os.path.join(os.path.dirname(video), f"{base}_voiceover{ext}")
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", source,
             "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE),
             "-c:a", ffmpeg_codec, "-b:a", bitrate_arg,
             output],
            check=False, capture_output=True
        )
    else:
        if not output:
            base = os.path.splitext(os.path.basename(video))[0]
            output = os.path.join(os.path.dirname(video), f"{base}_dubbed.mkv")
        # If normalized, inject back into container
        if norm_applied:
            # Replace the voiceover track with normalized version
            rc = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", video,
                 "-i", norm_out,
                 "-map", "0:v",
                 "-map", "0:a:0",
                 "-map", "1:a",
                 "-map", "0:s?",
                 "-c:v", "copy",
                 "-c:a:0", "copy",
                 "-c:a:1", ffmpeg_codec, "-b:a:1", bitrate_arg,
                 "-c:s", "copy",
                 "-disposition:a:0", "none",
                 "-disposition:a:1", "default",
                 "-metadata:s:a:1", "language=rus",
                 "-metadata:s:a:1", "title=Voiceover",
                 output],
                check=False, capture_output=True
            )
        else:
            rc = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", video,
                 "-i", source,
                 "-map", "0:v",
                 "-map", "0:a:0",
                 "-map", "1:a",
                 "-map", "0:s?",
                 "-c:v", "copy",
                 "-c:a:0", "copy",
                 "-c:a:1", ffmpeg_codec, "-b:a:1", bitrate_arg,
                 "-c:s", "copy",
                 "-disposition:a:0", "none",
                 "-disposition:a:1", "default",
                 "-metadata:s:a:1", "language=rus",
                 "-metadata:s:a:1", "title=Voiceover",
                 output],
                check=False, capture_output=True
            )

    if rc.returncode != 0:
        err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
        die(f"\u041a\u043e\u0434\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c: {err_text[:500]}")

    if os.path.isfile(output):
        ok(f"\u0413\u043e\u0442\u043e\u0432\u043e: {output}")
        print(f"  \u0420\u0430\u0437\u043c\u0435\u0440: {os.path.getsize(output) / 1024 / 1024:.0f} MB")
    else:
        die(f"\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439 \u0444\u0430\u0439\u043b \u043d\u0435 \u0441\u043e\u0437\u0434\u0430\u043d: {output}")

# ──────────────────────────────────────────────────────────────────────────
# \u0421\u043f\u0438\u0441\u043e\u043a \u0433\u043e\u043b\u043e\u0441\u043e\u0432
# ──────────────────────────────────────────────────────────────────────────

def list_voices() -> None:
    print(f"{CYAN}\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u0433\u043e\u043b\u043e\u0441\u0430 edge-tts:{NC}")
    rc = subprocess.run(
        ["python3", "-m", "edge_tts", "--list-voices"],
        check=False, capture_output=True, text=True
    )
    if rc.returncode != 0:
        die("edge-tts \u043d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442")
    print(rc.stdout)
    print("\u0424\u0438\u043b\u044c\u0442\u0440 \u043f\u043e \u0440\u0443\u0441\u0441\u043a\u0438\u043c:")
    for line in rc.stdout.split("\n"):
        if "ru-" in line.lower():
            print(f"  {line.strip()}")
    sys.exit(0)

# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _get_parser().parse_args(sys.argv[1:])

    # --voice without argument → list voices
    if args.voice == "__LIST__":
        list_voices()

    if not args.video:
        _get_parser().print_help()
        sys.exit(0)

    video = os.path.realpath(args.video)
    if not os.path.isfile(video):
        die(f"\u0424\u0430\u0439\u043b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d: {video}")

    # \u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0437\u0430\u0432\u0438\u0441\u0438\u043c\u043e\u0441\u0442\u0435\u0439
    which("ffmpeg")
    which("ffprobe")
    which("python3")
    rc = subprocess.run(
        ["python3", "-m", "edge_tts", "--help"],
        check=False, capture_output=True
    )
    if rc.returncode != 0:
        die("edge-tts \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d (pip install edge-tts)")

    # \u0410\u0443\u0434\u0438\u043e\u0444\u043e\u0440\u043c\u0430\u0442
    audio_fmt = "opus"
    audio_bitrate = "64"
    for candidate in ("aac", "mp3", "opus", "ac3"):
        val = getattr(args, candidate, None)
        if val is not None:
            audio_fmt = candidate
            audio_bitrate = val
            break

    # Голос: пока DEFAULT, уточним после получения субтитров
    voice = args.voice if args.voice else DEFAULT_VOICE
    normalize = args.normalize
    # Warn if voice is not in the live list
    rc_list = subprocess.run(
        ["python3", "-m", "edge_tts", "--list-voices"],
        check=False, capture_output=True, text=True
    )
    if rc_list.returncode == 0 and voice not in rc_list.stdout:
        warn(f"\u0413\u043e\u043b\u043e\u0441 '{voice}' \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0432 \u0441\u043f\u0438\u0441\u043a\u0435 edge-tts --list-voices")
        warn("\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u043e, \u043e\u043d \u0443\u0434\u0430\u043b\u0451\u043d Microsoft. \u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u043c\u043e\u0436\u0435\u0442 \u043d\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c.")

    # Output file
    if args.output:
        output = os.path.realpath(args.output)
    else:
        base = os.path.splitext(os.path.basename(video))[0]
        ext = CODEC_MAP[audio_fmt][2] if args.audio_only else ".mkv"
        output = os.path.join(os.path.dirname(video), f"{base}_dubbed{ext}")

    # Info
    sync_str = "\u0432\u043a\u043b" if args.sync else "\u0432\u044b\u043a\u043b"
    codec_name, codec_bit, _ = _get_codec(audio_fmt, audio_bitrate)
    info(f"\u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f: {sync_str} | "
         f"\u0413\u043e\u043b\u043e\u0441: {voice} | "
         f"\u041a\u043e\u0434\u0435\u043a: {codec_name} {codec_bit} | "
         f"\u0422\u0435\u043c\u043f: {args.speed}x | "
         f"\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b: {args.orig_vol} | TTS: {args.tts_vol}")
    if normalize:
        info(f"\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f: {normalize}")
    if args.range_from or args.range_to:
        info(f"\u0414\u0438\u0430\u043f\u0430\u0437\u043e\u043d \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432: {args.range_from or 1}\u2013{args.range_to or '...'}")
    if args.audio_only:
        info("\u0420\u0435\u0436\u0438\u043c: \u0442\u043e\u043b\u044c\u043a\u043e \u0430\u0443\u0434\u0438\u043e")

    # Temp dir
    tmpdir = tempfile.mkdtemp(prefix="rusa_")
    try:
        subs_path = step_extract_subtitles(video, args.srt, tmpdir)

        # Уточняем голос после получения субтитров
        if args.voice is None:
            detected = detect_language_from_srt(subs_path)
            if detected:
                voice = detected
                info(f"\u042f\u0437\u044b\u043a \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0451\u043d: {voice}")
            else:
                if HAS_LANGDETECT:
                    warn("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u044f\u0437\u044b\u043a \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432, \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e \u0433\u043e\u043b\u043e\u0441 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e")
                else:
                    warn("langdetect \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d (pip install langdetect), \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e \u0433\u043e\u043b\u043e\u0441 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e")

        if args.sync:
            subs_path = step_sync_alass(video, subs_path, tmpdir)
        entries, count = step_parse_srt(subs_path, args.range_from, args.range_to)
        tts_results = step_generate_tts(entries, voice, args.threads, tmpdir)
        wav_results = step_convert_wav(tts_results, args.speed, tmpdir)
        voiceover_wav = step_assemble(entries, wav_results, tmpdir)
        step_mix_output(video, voiceover_wav, args.orig_vol, args.tts_vol,
                        output, tmpdir,
                        audio_fmt, audio_bitrate,
                        args.normalize, args.audio_only)
    finally:
        if not args.keep_temp:
            shutil.rmtree(tmpdir, ignore_errors=True)
        elif os.path.isdir(tmpdir):
            info(f"\u0412\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0444\u0430\u0439\u043b\u044b: {tmpdir}")

if __name__ == "__main__":
    main()
