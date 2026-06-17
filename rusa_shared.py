#!/usr/bin/env python3
"""Shared constants, optional deps, utilities, and cache helpers for rusa."""
__all__ = ['HAS_TQDM', 'HAS_LANGDETECT', 'tqdm', 'detect', 'LangDetectException', 'DEFAULT_VOICE', 'DEFAULT_SPEED', 'DEFAULT_ORIG_VOL', 'DEFAULT_TTS_VOL', 'DEFAULT_THREADS', 'MAX_TTS_CHARS', 'WAV_FILTER_VERSION', 'DEFAULT_SUBS_MODE', 'EXIT_RUNTIME_ERROR', 'EXIT_USAGE_ERROR', 'EXIT_DEPENDENCY_ERROR', 'EXIT_SUBTITLE_ERROR', 'EXIT_CODEC_ERROR', 'CODEC_MAP', 'LANG_VOICE_MAP', 'LANG_FFPROBE_MAP', 'FFPROBE_TO_ISO6391', 'RED', 'GREEN', 'YELLOW', 'CYAN', 'NC', 'WAV_CHANNELS', 'WAV_SAMPLEWIDTH', 'WAV_FRAMERATE', 'WAV_BPF', 'WAV_HEADER_SIZE', 'voice_to_lang_code', 'lang_code_to_ffprobe_codes', 'normalize_lang_code', 'info', 'ok', 'warn', 'err', 'die', 'which', 'shell', 'shell_ok', 'cache_enabled', 'cache_root_dir', 'cache_subdir', 'tts_cache_dir', 'tts_cache_path', 'copy_into_cache', 'wav_cache_dir', 'file_sha256', 'wav_cache_path', 'cache_bucket_stats', 'format_bytes', 'print_cache_stats', 'clear_cache', 'print_timing_summary']

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

HAS_TQDM = False
HAS_LANGDETECT = False
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    pass

# langdetect is optional; define fallbacks so downstream imports never crash
try:
    from langdetect import detect, DetectorFactory, LangDetectException
    DetectorFactory.seed = 0
    HAS_LANGDETECT = True
except ImportError:
    detect = None  # type: ignore[assignment]
    LangDetectException = Exception  # type: ignore[misc]

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"
DEFAULT_SPEED = "1.5"
DEFAULT_ORIG_VOL = "0.65"
DEFAULT_TTS_VOL = "0.93"
DEFAULT_THREADS = 6
MAX_TTS_CHARS = 3000
WAV_FILTER_VERSION = "1"
DEFAULT_SUBS_MODE = "auto"
_CACHE_DISABLED = False

# Cache size limit (LRU eviction)
DEFAULT_CACHE_MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GiB


def _cache_max_size() -> int:
    """Return max cache size in bytes from RUSA_CACHE_MAX_SIZE env (default 2 GiB)."""
    raw = os.environ.get("RUSA_CACHE_MAX_SIZE", "")
    if raw:
        try:
            return max(1024 * 1024, int(raw))  # at least 1 MiB
        except ValueError:
            pass
    return DEFAULT_CACHE_MAX_SIZE


def _evict_oldest(cache_dir: str, max_size: int | None = None) -> int:
    """Remove oldest files by mtime until total size <= max_size.

    Returns number of files removed. Only examines files directly in *cache_dir*
    (one level, no recursive walk).
    """
    if max_size is None:
        max_size = _cache_max_size()
    if not os.path.isdir(cache_dir):
        return 0
    entries: list[tuple[float, str, int]] = []  # (mtime, path, size)
    total = 0
    for name in os.listdir(cache_dir):
        child = os.path.join(cache_dir, name)
        try:
            st = os.stat(child)
        except OSError:
            continue
        if not os.path.isfile(child):
            continue
        entries.append((st.st_mtime, child, st.st_size))
        total += st.st_size

    if total <= max_size:
        return 0

    # Sort by mtime ascending (oldest first)
    entries.sort(key=lambda e: e[0])
    removed = 0
    for _mtime, child, size in entries:
        if total <= max_size:
            break
        try:
            os.remove(child)
            total -= size
            removed += 1
        except OSError:
            continue
    return removed


EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_DEPENDENCY_ERROR = 3
EXIT_SUBTITLE_ERROR = 4
EXIT_CODEC_ERROR = 5

CODEC_MAP = {
    "aac": ("aac", "mkv", ".aac", "128"),
    "mp3": ("libmp3lame", "mkv", ".mp3", "192"),
    "opus": ("libopus", "mkv", ".opus", "64"),
    "ac3": ("ac3", "mkv", ".ac3", "448"),
}

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

FFPROBE_TO_ISO6391: dict[str, str] = {}
for _iso2, _codes in LANG_FFPROBE_MAP.items():
    for _code in _codes:
        FFPROBE_TO_ISO6391[_code] = _iso2

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

WAV_CHANNELS = 2
WAV_SAMPLEWIDTH = 2
WAV_FRAMERATE = 48000
WAV_BPF = WAV_CHANNELS * WAV_SAMPLEWIDTH
WAV_HEADER_SIZE = 44


def voice_to_lang_code(voice: str) -> str:
    return voice[:2].lower()


def lang_code_to_ffprobe_codes(lang: str) -> list[str]:
    return LANG_FFPROBE_MAP.get(lang, [lang])


def normalize_lang_code(code: str) -> str:
    code = code.lower().replace("_", "-")
    if code in LANG_VOICE_MAP:
        return code
    if code in FFPROBE_TO_ISO6391:
        return FFPROBE_TO_ISO6391[code]
    if "-" in code and code[:2] in LANG_VOICE_MAP:
        return code[:2]
    return code


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
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            sys.stderr.write(exc.stderr.decode("utf-8", errors="replace"))
        die(f"Команда {' '.join(cmd)} завершилась с кодом {exc.returncode}")
    except FileNotFoundError:
        die(f"Команда не найдена: {cmd[0]}", EXIT_DEPENDENCY_ERROR)
    except Exception as exc:  # pragma: no cover
        die(f"Ошибка выполнения {' '.join(cmd)}: {exc}")


def shell_ok(cmd: list[str], **kwargs) -> bool:
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, **kwargs)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def cache_enabled() -> bool:
    return not _CACHE_DISABLED


def cache_root_dir(create: bool = True) -> str | None:
    if not cache_enabled():
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


def cache_subdir(name: str, create: bool = True) -> str | None:
    root = cache_root_dir(create=create)
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


def tts_cache_dir() -> str | None:
    return cache_subdir("tts")


def tts_cache_path(voice: str, text: str) -> str | None:
    cache_dir = tts_cache_dir()
    if cache_dir is None:
        return None
    digest = hashlib.sha256(f"{voice}\0{text}".encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{digest}.mp3")


def copy_into_cache(src: str, cache_path: str | None) -> None:
    if not cache_path:
        return
    if not os.path.isfile(src) or os.path.getsize(src) <= 100:
        return
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 100:
        return
    tmp_cache = f"{cache_path}.tmp.{os.getpid()}.{time.time_ns()}"
    shutil.copy2(src, tmp_cache)
    os.replace(tmp_cache, cache_path)
    # LRU eviction: keep cache under limit
    cached_dir = os.path.dirname(cache_path) if cache_path else None
    if cached_dir and os.path.isdir(cached_dir):
        _evict_oldest(cached_dir)


def wav_cache_dir() -> str | None:
    return cache_subdir("wav")


def file_sha256(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def wav_cache_path(mp3_path: str, speed: str) -> str | None:
    cache_dir = wav_cache_dir()
    if cache_dir is None:
        return None
    digest = hashlib.sha256(
        f"{file_sha256(mp3_path)}\0{speed}\0{WAV_FILTER_VERSION}".encode("utf-8")
    ).hexdigest()
    return os.path.join(cache_dir, f"{digest}.wav")


def cache_bucket_stats(name: str) -> tuple[int, int]:
    cache_dir = cache_subdir(name, create=False)
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


def format_bytes(size: int) -> str:
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
    root = cache_root_dir(create=False)
    if root is None:
        print("Cache: empty")
        sys.exit(0)
    tts_files, tts_size = cache_bucket_stats("tts")
    wav_files, wav_size = cache_bucket_stats("wav")
    print(f"Cache root: {root}")
    print(f"TTS: {tts_files} files, {format_bytes(tts_size)}")
    print(f"WAV: {wav_files} files, {format_bytes(wav_size)}")
    print(f"Total: {tts_files + wav_files} files, {format_bytes(tts_size + wav_size)}")
    sys.exit(0)


def clear_cache() -> None:
    root = cache_root_dir(create=False)
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
    if not stage_durations:
        return
    print("Timing:")
    for name, seconds in stage_durations:
        print(f"  {name}: {seconds:.1f}s")
