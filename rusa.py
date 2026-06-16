#!/usr/bin/env python3
"""
rusa — Russian Voiceover for Movies

Создаёт голосовой закадровый перевод (voiceover) для видеофайлов.
Использует Microsoft Edge TTS для генерации речи по субтитрам,
накладывает её поверх оригинала с регулируемой громкостью и темпом.
"""

import argparse
import hashlib
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
WAV_FILTER_VERSION = "1"
DEFAULT_SUBS_MODE = "auto"
_CACHE_DISABLED = False
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_DEPENDENCY_ERROR = 3
EXIT_SUBTITLE_ERROR = 4
EXIT_CODEC_ERROR = 5

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
    "he": "he-IL-HilaNeural",
}

# Map ISO 639-1 → possible ffprobe language codes (ISO 639-2/B and 639-1)
LANG_FFPROBE_MAP: dict[str, list[str]] = {
    "ru": ["rus", "ru", "russian"],
    "en": ["eng", "en", "english"],
    "he": ["heb", "he", "hebrew"],
    "de": ["deu", "ger", "de", "german"],
    "fr": ["fra", "fre", "fr", "french"],
    "es": ["spa", "es", "spanish"],
    "it": ["ita", "it", "italian"],
    "pt": ["por", "pt", "portuguese"],
    "ja": ["jpn", "ja", "japanese"],
    "ko": ["kor", "ko", "korean"],
    "zh": ["zho", "chi", "zh", "chinese"],
    "ar": ["ara", "ar", "arabic"],
    "tr": ["tur", "tr", "turkish"],
    "nl": ["nld", "dut", "nl", "dutch"],
    "pl": ["pol", "pl", "polish"],
    "sv": ["swe", "sv", "swedish"],
    "da": ["dan", "da", "danish"],
    "fi": ["fin", "fi", "finnish"],
    "nb": ["nor", "nb", "norwegian"],
    "cs": ["ces", "cze", "cs", "czech"],
    "hu": ["hun", "hu", "hungarian"],
}


def voice_to_lang_code(voice: str) -> str:
    """Extract ISO 639-1 language code from an edge-tts voice name.
    
    'he-IL-HilaNeural' → 'he'
    'ru-RU-SvetlanaNeural' → 'ru'
    """
    return voice[:2].lower()


def lang_code_to_ffprobe_codes(lang: str) -> list[str]:
    """Return possible ffprobe language codes for a given ISO 639-1 code."""
    return LANG_FFPROBE_MAP.get(lang, [lang])


# Reverse map: any ffprobe code -> ISO 639-1
FFPROBE_TO_ISO6391: dict[str, str] = {}
for _iso2, _codes in LANG_FFPROBE_MAP.items():
    for _c in _codes:
        FFPROBE_TO_ISO6391[_c] = _iso2


def normalize_lang_code(code: str) -> str:
    """Normalize language code to ISO 639-1.
    'heb' -> 'he', 'rus' -> 'ru', 'eng' -> 'en', 'he-IL' -> 'he', etc."""
    code = code.lower().replace('_', '-')
    # Already ISO 639-1?
    if code in LANG_VOICE_MAP:
        return code
    # Try ffprobe code -> ISO 639-1
    if code in FFPROBE_TO_ISO6391:
        return FFPROBE_TO_ISO6391[code]
    # Try voice/locale prefix: he-IL -> he
    if '-' in code and code[:2] in LANG_VOICE_MAP:
        return code[:2]
    return code


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

def die(msg: str, code: int = EXIT_RUNTIME_ERROR) -> None:
    err(msg)
    sys.exit(code)

def which(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        die(f"{cmd} не найден в PATH", EXIT_DEPENDENCY_ERROR)
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
        die(f"\u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430: {cmd[0]}", EXIT_DEPENDENCY_ERROR)
    except Exception as e:
        die(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044f {' '.join(cmd)}: {e}")

def shell_ok(cmd: list[str], **kwargs) -> bool:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, **kwargs)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _cache_enabled() -> bool:
    return not _CACHE_DISABLED


def _cache_root_dir(create: bool = True) -> str | None:
    """Return persistent cache root directory, or None if cache is unavailable."""
    if not _cache_enabled():
        return None
    if os.environ.get("RUSA_CACHE_DIR"):
        base = os.environ["RUSA_CACHE_DIR"]
    elif os.environ.get("XDG_CACHE_HOME"):
        base = os.path.join(os.environ["XDG_CACHE_HOME"], "rusa")
    else:
        base = os.path.join(os.path.expanduser("~/.cache"), "rusa")
    if create:
        try:
            os.makedirs(base, exist_ok=True)
        except OSError:
            return None
    elif not os.path.isdir(base):
        return None
    return base


def _cache_subdir(name: str, create: bool = True) -> str | None:
    """Return a cache subdirectory path, or None if cache is unavailable."""
    root = _cache_root_dir(create=create)
    if root is None:
        return None
    cache_dir = os.path.join(root, name)
    if create:
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            return None
    elif not os.path.isdir(cache_dir):
        return None
    return cache_dir


def _tts_cache_dir() -> str | None:
    """Return persistent cache directory for generated TTS assets."""
    return _cache_subdir("tts")


def _tts_cache_path(voice: str, text: str) -> str | None:
    """Stable cache key for final MP3 generated from voice+text."""
    cache_dir = _tts_cache_dir()
    if cache_dir is None:
        return None
    digest = hashlib.sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{digest}.mp3")


def _copy_into_cache(src: str, cache_path: str | None) -> None:
    """Atomically populate cache entry if it does not exist yet."""
    if not cache_path:
        return
    if not os.path.isfile(src) or os.path.getsize(src) <= 100:
        return
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 100:
        return
    tmp_cache = f"{cache_path}.tmp.{os.getpid()}.{time.time_ns()}"
    shutil.copy2(src, tmp_cache)
    os.replace(tmp_cache, cache_path)


def _wav_cache_dir() -> str | None:
    """Return persistent cache directory for converted WAV assets."""
    return _cache_subdir("wav")


def _file_sha256(path: str) -> str:
    """Hash file contents for cache identity."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _wav_cache_path(mp3_path: str, speed: str) -> str | None:
    """Stable cache key for final WAV generated from mp3 content and speed."""
    cache_dir = _wav_cache_dir()
    if cache_dir is None:
        return None
    digest = hashlib.sha256(
        f"{_file_sha256(mp3_path)}\0{speed}\0{WAV_FILTER_VERSION}".encode("utf-8")
    ).hexdigest()
    return os.path.join(cache_dir, f"{digest}.wav")


def _cache_bucket_stats(name: str) -> tuple[int, int]:
    """Return file count and total size for a cache bucket."""
    cache_dir = _cache_subdir(name, create=False)
    if cache_dir is None or not os.path.isdir(cache_dir):
        return 0, 0
    files = 0
    size = 0
    for root, _dirs, filenames in os.walk(cache_dir):
        for filename in filenames:
            path = os.path.join(root, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            files += 1
            size += stat.st_size
    return files, size


def _format_bytes(size: int) -> str:
    """Render bytes in a compact human-readable form."""
    value = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for candidate in units:
        unit = candidate
        if value < 1024.0 or candidate == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def print_cache_stats() -> None:
    """Print current cache usage and exit."""
    root = _cache_root_dir(create=False)
    if root is None:
        print("Cache: empty")
        sys.exit(0)

    tts_files, tts_size = _cache_bucket_stats("tts")
    wav_files, wav_size = _cache_bucket_stats("wav")
    total_files = tts_files + wav_files
    total_size = tts_size + wav_size
    print(f"Cache root: {root}")
    print(f"TTS: {tts_files} files, {_format_bytes(tts_size)}")
    print(f"WAV: {wav_files} files, {_format_bytes(wav_size)}")
    print(f"Total: {total_files} files, {_format_bytes(total_size)}")
    sys.exit(0)


def clear_cache() -> None:
    """Remove all cache payloads and exit."""
    root = _cache_root_dir(create=False)
    if root is None or not os.path.isdir(root):
        print("Cache already empty")
        sys.exit(0)

    removed = 0
    for name in ("tts", "wav"):
        cache_dir = os.path.join(root, name)
        if not os.path.isdir(cache_dir):
            continue
        for entry in os.scandir(cache_dir):
            removed += 1
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                try:
                    os.remove(entry.path)
                except OSError:
                    pass
    print(f"Cache cleared: removed {removed} entries from {root}")
    sys.exit(0)


def print_timing_summary(stage_durations: list[tuple[str, float]]) -> None:
    """Print a compact timing summary for the completed pipeline."""
    if not stage_durations:
        return
    print("Timing:")
    for name, seconds in stage_durations:
        print(f"  {name}: {seconds:.1f}s")

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
               rusa --lang he movie.mkv
               rusa --voice he-IL-HilaNeural --lang he movie.mkv
        """),
    )
    parser.add_argument("video", nargs="?", help="\u0412\u0438\u0434\u0435\u043e\u0444\u0430\u0439\u043b")
    parser.add_argument("-o", "--output", help="\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439 \u0444\u0430\u0439\u043b")
    parser.add_argument("-s", "--srt", help="\u0424\u0430\u0439\u043b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 .srt")

    # Voice: --voice without arg -> list, --voice VOICE -> use it, default -> auto-detect then DEFAULT_VOICE
    parser.add_argument("--voice", nargs="?", const="__LIST__", default=None,
                        help="\u0413\u043e\u043b\u043e\u0441 edge-tts. \u0411\u0435\u0437 \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442\u0430 \u2014 \u0441\u043f\u0438\u0441\u043e\u043a \u0433\u043e\u043b\u043e\u0441\u043e\u0432. "
                             "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u0430\u0432\u0442\u043e\u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u0435 \u043f\u043e \u044f\u0437\u044b\u043a\u0443 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432")

    parser.add_argument("--lang", default=None, metavar="LANG",
                        help="\u042f\u0437\u044b\u043a \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 (\u043a\u043e\u0434 ISO 639-1: ru, en, he, de, fr, ...). "
                             "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u044f\u0435\u0442\u0441\u044f \u0438\u0437 \u0433\u043e\u043b\u043e\u0441\u0430 --voice.")

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
    parser.add_argument("--cache-stats", action="store_true",
                        help="\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0443 TTS/WAV \u043a\u044d\u0448\u0430 \u0438 \u0432\u044b\u0439\u0442\u0438")
    parser.add_argument("--cache-clear", action="store_true",
                        help="\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c TTS/WAV \u043a\u044d\u0448 \u0438 \u0432\u044b\u0439\u0442\u0438")
    parser.add_argument("--no-cache", action="store_true",
                        help="\u041d\u0435 \u0447\u0438\u0442\u0430\u0442\u044c \u0438 \u043d\u0435 \u043f\u0438\u0441\u0430\u0442\u044c TTS/WAV \u043a\u044d\u0448 \u0432 \u044d\u0442\u043e\u043c \u0437\u0430\u043f\u0443\u0441\u043a\u0435")

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
    parser.add_argument(
        "--subs-mode",
        choices=["auto", "copy", "convert", "drop"],
        default=DEFAULT_SUBS_MODE,
        help="\u0420\u0435\u0436\u0438\u043c \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0432 \u0432\u044b\u0445\u043e\u0434\u043d\u043e\u043c \u0432\u0438\u0434\u0435\u043e: "
             "auto|copy|convert|drop (\u043f\u043e \u0443\u043c\u043e\u043b\u0447. auto)",
    )

    # Normalize
    parser.add_argument("--normalize", nargs="?", const="fine",
                        choices=["fast", "fine"],
                        help="\u041d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0433\u0440\u043e\u043c\u043a\u043e\u0441\u0442\u0438: "
                             "fast (\u0431\u044b\u0441\u0442\u0440\u043e) \u0438\u043b\u0438 fine (\u0442\u043e\u0447\u043d\u043e, \u043f\u043e \u0443\u043c\u043e\u043b\u0447.)")

    return parser

# ──────────────────────────────────────────────────────────────────────────
# \u0428\u0430\u0433 1: \u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b
# ──────────────────────────────────────────────────────────────────────────

def step_extract_subtitles(video: str, srt_file: str | None, tmpdir: str, target_lang: str | None = None) -> str:
    dest = os.path.join(tmpdir, "subtitles.srt")
    if srt_file:
        if not os.path.isfile(srt_file):
            die(f"\u0424\u0430\u0439\u043b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d: {srt_file}", EXIT_SUBTITLE_ERROR)
        info(f"\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b: {srt_file}")
        shutil.copy2(srt_file, dest)
        ok(f"\u0421\u0443\u0431\u0442\u0438\u0442\u0440\u044b: {sum(1 for _ in open(dest, encoding='utf-8'))} \u0441\u0442\u0440\u043e\u043a")
        return dest

    # Determine target language codes to look for
    if target_lang:
        target_codes = lang_code_to_ffprobe_codes(target_lang)
    else:
        target_codes = ["rus", "ru", "russian"]

    info("\u0418\u0437\u0432\u043b\u0435\u0447\u0435\u043d\u0438\u0435 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0438\u0437 \u0432\u0438\u0434\u0435\u043e...")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream=index:stream_tags=language",
         "-of", "csv=p=0", video],
        capture_output=True, text=True, check=False
    )
    found = 0
    available = []
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) != 2:
                continue
            idx = parts[0].strip()
            lang = parts[1].strip().lower()
            available.append((idx, lang))
            if lang in target_codes:
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
        # Try external .srt files matching the target language
        if target_lang:
            for ext in [f".{target_lang}.srt", f".{target_lang[:2]}.srt"]:
                cand = base + ext
                if os.path.isfile(cand):
                    shutil.copy2(cand, dest)
                    found = 1
                    break
        else:
            for ext in [".rus.srt", ".ru.srt", ".russian.srt", ".srt"]:
                cand = base + ext
                if os.path.isfile(cand):
                    shutil.copy2(cand, dest)
                    found = 1
                    break

    if not found:
        avail_str = ", ".join(f"#{idx} ({lang})" for idx, lang in available) if available else "\u043d\u0435\u0442 \u043f\u043e\u0442\u043e\u043a\u043e\u0432"
        if target_lang:
            die(f"\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b \u043d\u0430 \u044f\u0437\u044b\u043a\u0435 '{target_lang}'. \u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u043f\u043e\u0442\u043e\u043a\u0438: {avail_str}. \u0423\u043a\u0430\u0436\u0438\u0442\u0435 -s <file.srt> \u0438\u043b\u0438 --lang \u0434\u0440\u0443\u0433\u043e\u0439 \u044f\u0437\u044b\u043a.", EXIT_SUBTITLE_ERROR)
        else:
            die(f"\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b \u0440\u0443\u0441\u0441\u043a\u0438\u0435 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u044b. \u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u043f\u043e\u0442\u043e\u043a\u0438: {avail_str}. \u0423\u043a\u0430\u0436\u0438\u0442\u0435 -s <file.srt>", EXIT_SUBTITLE_ERROR)
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
            die(f"\u041d\u0435\u0442 \u0441\u0443\u0431\u0442\u0438\u0442\u0440\u043e\u0432 \u0432 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u0435 {lo}\u2013{hi}", EXIT_SUBTITLE_ERROR)
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
        cache_path = _tts_cache_path(voice, text)

        if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 100:
            shutil.copy2(cache_path, out)
            return idx, out

        # Single part — generate directly
        if len(parts) == 1:
            for attempt in range(1, MAX_RETRIES + 1):
                if os.path.isfile(out) and os.path.getsize(out) > 100:
                    _copy_into_cache(out, cache_path)
                    return idx, out
                try:
                    rc = subprocess.run(
                        ["edge-tts", "--voice", voice, "--text", parts[0], "--write-media", out],
                        capture_output=True, timeout=180, check=False,
                    ).returncode
                    if rc == 0 and os.path.isfile(out) and os.path.getsize(out) > 100:
                        _copy_into_cache(out, cache_path)
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
            _copy_into_cache(out, cache_path)
            return idx, out
        # Fallback: use first part only
        if part_files:
            shutil.copy2(part_files[0], out)
            if os.path.getsize(out) > 100:
                _copy_into_cache(out, cache_path)
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
                     tmpdir: str, threads: int = DEFAULT_THREADS) -> list[tuple[int, str, float]]:
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

    def convert_one(item: tuple[int, str]) -> tuple[int, str, float] | None:
        idx, mp3_path = item
        wav_path = os.path.join(wav_dir, f"batch_{idx:04d}.wav")
        cache_path = _wav_cache_path(mp3_path, speed)
        if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 44:
            shutil.copy2(cache_path, wav_path)
            try:
                with wave.open(wav_path, "rb") as w:
                    frames = w.getnframes()
                    duration_ms = frames / WAV_FRAMERATE * 1000
                if duration_ms >= 50:
                    return (idx, wav_path, duration_ms)
                warn(f"  #{idx} cached wav too short ({duration_ms:.0f}ms), regenerating")
            except Exception:
                warn(f"  #{idx} cached wav damaged, regenerating")
        # atempo + trim leading AND trailing silence via areverse trick
        # (areverse + start_periods reliably trims trailing silence without destroying speech)
        filter_str = (
            f"{tempo_filter},"
            f"silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
            f"areverse,"
            f"silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
            f"areverse"
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
                    _copy_into_cache(wav_path, cache_path)
                    return (idx, wav_path, duration_ms)
                else:
                    warn(f"  #{idx} too short ({duration_ms:.0f}ms), skipped")
            except Exception:
                _copy_into_cache(wav_path, cache_path)
                return (idx, wav_path, 0)
        else:
            warn(f"  #{idx} \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c")
        return None

    total = len(tts_results)
    done = 0
    pbar = tqdm(total=total, desc="  WAV", unit="sub") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        futures = {ex.submit(convert_one, item): item[0] for item in tts_results}
        for f in as_completed(futures):
            done += 1
            converted = f.result()
            if converted is not None:
                results.append(converted)
            if pbar:
                pbar.update(1)
            elif done % 30 == 0 or done == total:
                print(f"  [{done}/{total}]")

    if pbar:
        pbar.close()

    results.sort(key=lambda item: item[0])
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


def _subtitle_copy_not_supported(err_text: str, output: str) -> bool:
    """Detect subtitle/container mismatch worth retrying with text subtitles."""
    lower = err_text.lower()
    return output.lower().endswith(".mkv") and "subtitle codec" in lower and "not supported" in lower


def _probe_subtitle_codecs(video: str) -> list[str] | None:
    """Return codec_name values for all subtitle streams that 0:s? would map."""
    rc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if rc.returncode != 0:
        return None
    codecs = []
    for line in rc.stdout.strip().splitlines():
        value = line.strip().lower()
        if value:
            codecs.append(value)
    return codecs


def _subtitle_copy_codecs_supported(output: str, source_subtitle_codecs: list[str] | None) -> bool | None:
    """Return whether all mapped subtitles can be copied into the target container as-is."""
    if source_subtitle_codecs is None:
        return None
    if not source_subtitle_codecs:
        return True
    ext = Path(output).suffix.lower()
    incompatible = {
        # Keep mkv permissive: only reject codecs we know ffmpeg cannot copy there.
        ".mkv": {"mov_text"},
        ".mp4": {
            "subrip", "srt", "ass", "ssa", "webvtt", "vtt",
            "hdmv_pgs_subtitle", "dvd_subtitle", "xsub",
        },
        ".m4v": {
            "subrip", "srt", "ass", "ssa", "webvtt", "vtt",
            "hdmv_pgs_subtitle", "dvd_subtitle", "xsub",
        },
    }
    if ext in {".mp4", ".m4v"}:
        return all(codec == "mov_text" for codec in source_subtitle_codecs)
    blocked = incompatible.get(ext)
    if blocked is None:
        return None
    return all(codec not in blocked for codec in source_subtitle_codecs)


def _subtitle_convert_codec(output: str) -> str | None:
    """Return a compatible text subtitle codec for the output container."""
    ext = Path(output).suffix.lower()
    if ext == ".mkv":
        return "srt"
    if ext in {".mp4", ".m4v"}:
        return "mov_text"
    return None


def _subtitle_mux_plan(video: str, output: str, subs_mode: str) -> tuple[list[str], list[str]]:
    """Choose explicit subtitle mux strategy for the requested mode."""
    if subs_mode == "drop":
        return ["drop"], []

    source_subtitle_codecs = _probe_subtitle_codecs(video)
    convert_codec = _subtitle_convert_codec(output)
    copy_supported = _subtitle_copy_codecs_supported(output, source_subtitle_codecs)

    if subs_mode == "copy":
        if copy_supported is None:
            codec_label = ", ".join(source_subtitle_codecs) if source_subtitle_codecs else "unknown"
            die(
                f"Не удалось надёжно проверить совместимость субтитров codec={codec_label} "
                f"для контейнера '{Path(output).suffix or output}' при --subs-mode copy. "
                "Используйте --subs-mode auto, --subs-mode convert или --subs-mode drop."
            , EXIT_SUBTITLE_ERROR)
        if not copy_supported:
            codec_label = ", ".join(source_subtitle_codecs) if source_subtitle_codecs else "unknown"
            die(
                f"Нельзя скопировать субтитры codec={codec_label} в контейнер '{Path(output).suffix or output}' "
                f"при --subs-mode copy. Используйте --subs-mode convert или --subs-mode drop."
            , EXIT_SUBTITLE_ERROR)
        return ["copy"], source_subtitle_codecs

    if subs_mode == "convert":
        if not convert_codec:
            die(
                f"Для контейнера '{Path(output).suffix or output}' нет поддерживаемого текстового формата "
                "для --subs-mode convert."
            , EXIT_SUBTITLE_ERROR)
        return [convert_codec], source_subtitle_codecs

    plan = []
    if copy_supported is True or copy_supported is None:
        plan.append("copy")
    if convert_codec:
        plan.append(convert_codec)
    plan.append("drop")
    return plan, source_subtitle_codecs


def _build_video_mux_cmd(
    video: str,
    source_audio: str,
    output: str,
    ffmpeg_codec: str,
    bitrate_arg: str,
    voiceover_lang: str,
    subtitle_mode: str,
) -> list[str]:
    """Build ffmpeg command for final video mux."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video,
        "-i", source_audio,
        "-map", "0:v",
        "-map", "0:a:0",
        "-map", "1:a",
    ]
    if subtitle_mode != "drop":
        cmd.extend(["-map", "0:s?"])
    cmd.extend([
        "-c:v", "copy",
        "-c:a:0", "copy",
        "-c:a:1", ffmpeg_codec, "-b:a:1", bitrate_arg,
    ])
    if subtitle_mode != "drop":
        cmd.extend(["-c:s", subtitle_mode])
    cmd.extend([
        "-disposition:a:0", "none",
        "-disposition:a:1", "default",
        "-metadata:s:a:1", f"language={voiceover_lang}",
        "-metadata:s:a:1", "title=Voiceover",
        output,
    ])
    return cmd

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
                    normalize: str | None, audio_only: bool,
                    voiceover_lang: str = "rus",
                    subs_mode: str = DEFAULT_SUBS_MODE) -> None:
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
            alt_codec_name = CODEC_MAP[alt_name][0]
            alt_bitrate_default = CODEC_MAP[alt_name][3]
            if _check_ffmpeg_codec(alt_codec_name):
                alt_suggestions.append(f"--{alt_name} {alt_bitrate_default}")
        suggestions = ", ".join(alt_suggestions) if alt_suggestions else "нет известных альтернатив"
        msg = (
            f"\u041a\u043e\u0434\u0435\u043a {ffmpeg_codec} \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0432 \u0432\u0430\u0448\u0435\u0439 \u0441\u0431\u043e\u0440\u043a\u0435 ffmpeg.\n"
            f"\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u043e\u0440\u043c\u0430\u0442: {suggestions}"
        )
        die(msg, EXIT_CODEC_ERROR)

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
        subtitle_modes, _source_subtitle_codec = _subtitle_mux_plan(video, output, subs_mode)
        last_err_text = ""
        for index, subtitle_mode in enumerate(subtitle_modes):
            rc = subprocess.run(
                _build_video_mux_cmd(
                    video,
                    source,
                    output,
                    ffmpeg_codec,
                    bitrate_arg,
                    voiceover_lang,
                    subtitle_mode,
                ),
                check=False,
                capture_output=True,
            )
            if rc.returncode == 0:
                break
            last_err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
            remaining_modes = subtitle_modes[index + 1:]
            if subtitle_mode == "copy" and remaining_modes:
                if _subtitle_copy_not_supported(last_err_text, output):
                    warn("Копирование субтитров в этот контейнер не поддерживается, пробую перекодировать их в SRT")
                    continue
                if _source_subtitle_codec:
                    warn("Не удалось скопировать субтитры как есть, пробую совместимый текстовый формат")
                    continue
                if len(subtitle_modes) > 1:
                    warn("Не удалось скопировать субтитры как есть, пробую совместимый текстовый формат")
                    continue
            if subtitle_mode != "drop" and remaining_modes == ["drop"]:
                warn("Не удалось сохранить субтитры в выходном контейнере, пробую сохранить файл без них")
                continue
            break
        else:
            rc = subprocess.CompletedProcess([], 1, stderr=last_err_text.encode("utf-8"))

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
        die("edge-tts \u043d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442", EXIT_DEPENDENCY_ERROR)
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
    global _CACHE_DISABLED
    args = _get_parser().parse_args(sys.argv[1:])
    prev_cache_disabled = _CACHE_DISABLED
    try:
        # --voice without argument → list voices
        if args.voice == "__LIST__":
            list_voices()

        if args.cache_stats:
            print_cache_stats()

        if args.cache_clear:
            clear_cache()

        _CACHE_DISABLED = bool(args.no_cache)

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
            die("edge-tts \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d (pip install edge-tts)", EXIT_DEPENDENCY_ERROR)

        # \u0410\u0443\u0434\u0438\u043e\u0444\u043e\u0440\u043c\u0430\u0442
        audio_fmt = "opus"
        audio_bitrate = "64"
        normalize = args.normalize
        for candidate in ("aac", "mp3", "opus", "ac3"):
            val = getattr(args, candidate, None)
            if val is not None:
                audio_fmt = candidate
                audio_bitrate = val
                break

        # Determine target subtitle language and voice BEFORE info line
        target_lang = None
        if args.lang:
            target_lang = normalize_lang_code(args.lang)
            if target_lang not in LANG_VOICE_MAP and not args.voice:
                die(
                    f"Язык '{args.lang}' не поддерживается для авто-выбора голоса. "
                    "Укажите --voice явно."
                )
            info(f"Язык субтитров: {target_lang}")
        elif args.voice:
            target_lang = voice_to_lang_code(args.voice)

        # Voice: explicit --voice, or look up from --lang, or default
        if args.voice:
            voice = args.voice
        elif target_lang and target_lang in LANG_VOICE_MAP:
            voice = LANG_VOICE_MAP[target_lang]
        else:
            voice = DEFAULT_VOICE

        # Warn if voice is not in the live list
        rc_list = subprocess.run(
            ["python3", "-m", "edge_tts", "--list-voices"],
            check=False, capture_output=True, text=True
        )
        if rc_list.returncode == 0 and voice not in rc_list.stdout:
            warn(f"Голос '{voice}' отсутствует в списке edge-tts --list-voices")
            warn("Возможно, он удалён Microsoft. Генерация может не работать.")

        # Output file
        if args.output:
            output = os.path.realpath(args.output)
        else:
            base = os.path.splitext(os.path.basename(video))[0]
            ext = CODEC_MAP[audio_fmt][2] if args.audio_only else ".mkv"
            output = os.path.join(os.path.dirname(video), f"{base}_dubbed{ext}")

        # Info
        sync_str = "вкл" if args.sync else "выкл"
        codec_name, codec_bit, _ = _get_codec(audio_fmt, audio_bitrate)
        info(f"Синхронизация: {sync_str} | "
             f"Голос: {voice} | "
             f"Кодек: {codec_name} {codec_bit} | "
             f"Темп: {args.speed}x | "
             f"Оригинал: {args.orig_vol} | TTS: {args.tts_vol}")
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

        # Temp dir
        tmpdir = tempfile.mkdtemp(prefix="rusa_")
        try:
            started = time.perf_counter()
            subs_path = step_extract_subtitles(video, args.srt, tmpdir, target_lang)

            # Уточняем голос только если не было --voice и не было --lang
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
            step_mix_output(video, voiceover_wav, args.orig_vol, args.tts_vol,
                            output, tmpdir,
                            audio_fmt, audio_bitrate,
                            normalize, args.audio_only,
                            voiceover_lang, args.subs_mode)
            timings.append(("mux", time.perf_counter() - started))
            print_timing_summary(timings)
        finally:
            if not args.keep_temp:
                shutil.rmtree(tmpdir, ignore_errors=True)
            elif os.path.isdir(tmpdir):
                info(f"\u0412\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0444\u0430\u0439\u043b\u044b: {tmpdir}")
    finally:
        _CACHE_DISABLED = prev_cache_disabled

if __name__ == "__main__":
    main()
