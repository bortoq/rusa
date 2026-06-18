#!/usr/bin/env python3
"""Shared constants, optional deps, utilities, and cache helpers for rusa."""
__all__ = ['HAS_TQDM', 'HAS_LANGDETECT', 'tqdm', 'detect', 'LangDetectException', 'DEFAULT_VOICE', 'DEFAULT_SPEED', 'DEFAULT_ORIG_VOL', 'DEFAULT_TTS_VOL', 'DEFAULT_THREADS', 'MAX_TTS_CHARS', 'WAV_FILTER_VERSION', 'DEFAULT_SUBS_MODE', 'EXIT_RUNTIME_ERROR', 'EXIT_USAGE_ERROR', 'EXIT_DEPENDENCY_ERROR', 'EXIT_SUBTITLE_ERROR', 'EXIT_CODEC_ERROR', 'CODEC_MAP', 'LANG_VOICE_MAP', 'LANG_FFPROBE_MAP', 'FFPROBE_TO_ISO6391', 'RED', 'GREEN', 'YELLOW', 'CYAN', 'NC', 'WAV_CHANNELS', 'WAV_SAMPLEWIDTH', 'WAV_FRAMERATE', 'WAV_BPF', 'WAV_HEADER_SIZE', 'voice_to_lang_code', 'lang_code_to_ffprobe_codes', 'normalize_lang_code', 'info', 'ok', 'warn', 'err', 'die', 'which', 'shell', 'shell_ok', 'cache_enabled', 'cache_root_dir', 'cache_subdir', 'tts_cache_dir', 'tts_cache_path', 'copy_into_cache', 'wav_cache_dir', 'file_sha256', 'wav_cache_path', 'cache_bucket_stats', 'format_bytes', 'print_cache_stats', 'clear_cache', 'print_timing_summary', "_save_terminal", "_restore_terminal"]

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import atexit
import signal
import termios

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

    "bg": "bg-BG-KalinaNeural",
    "el": "el-GR-AthinaNeural",
    "hi": "hi-IN-SwaraNeural",
    "hr": "hr-HR-GabrijelaNeural",
    "id": "id-ID-GadisNeural",
    "ms": "ms-MY-YasminNeural",
    "ro": "ro-RO-AlinaNeural",
    "sk": "sk-SK-ViktoriaNeural",
    "sr": "sr-RS-SophieNeural",
    "th": "th-TH-PremwadeeNeural",
    "uk": "uk-UA-UlianaNeural",
    "vi": "vi-VN-HoaiMyNeural",
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
    "nb": ["nor", "nb", "no", "norwegian"],
    "cs": ["ces", "cze", "cs", "czech"],
    "hu": ["hun", "hu", "hungarian"],

    "bg": ["bul", "bg", "bulgarian"],
    "el": ["ell", "gre", "el", "greek"],
    "hi": ["hin", "hi", "hindi"],
    "hr": ["hrv", "hr", "croatian"],
    "id": ["ind", "id", "indonesian"],
    "ms": ["msa", "may", "ms", "malay"],
    "ro": ["ron", "rum", "ro", "romanian"],
    "sk": ["slk", "slo", "sk", "slovak"],
    "sr": ["srp", "sr", "serbian"],
    "th": ["tha", "th", "thai"],
    "uk": ["ukr", "uk", "ukrainian"],
    "vi": ["vie", "vi", "vietnamese"],
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


LANG_ALIAS: dict[str, str] = {
    # English full names → ISO 639-1
    "russian": "ru", "english": "en", "hebrew": "he",
    "german": "de", "french": "fr", "spanish": "es",
    "italian": "it", "portuguese": "pt", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar",
    "turkish": "tr", "dutch": "nl", "polish": "pl",
    "swedish": "sv", "danish": "da", "finnish": "fi",
    "norwegian": "nb", "norsk": "nb", "no": "nb", "czech": "cs", "hungarian": "hu",
    "ukrainian": "uk", "hindi": "hi", "indonesian": "id",
    "thai": "th", "vietnamese": "vi", "greek": "el",
    "romanian": "ro", "croatian": "hr", "serbian": "sr",
    "bulgarian": "bg", "malay": "ms", "slovak": "sk",
    # 3-letter ISO 639-2
    "rus": "ru", "eng": "en", "heb": "he",
    "deu": "de", "ger": "de", "fra": "fr", "fre": "fr",
    "spa": "es", "ita": "it", "por": "pt",
    "jpn": "ja", "kor": "ko", "zho": "zh", "chi": "zh",
    "ara": "ar", "tur": "tr", "nld": "nl", "dut": "nl",
    "pol": "pl", "swe": "sv", "dan": "da", "fin": "fi",
    "nor": "no", "ces": "cs", "cze": "cs", "hun": "hu",
    "ukr": "uk", "hin": "hi", "ind": "id",
    "tha": "th", "vie": "vi", "ell": "el", "gre": "el",
    "ron": "ro", "rum": "ro", "hrv": "hr", "srp": "sr",
    "bul": "bg", "msa": "ms", "may": "ms", "slk": "sk", "slo": "sk",
    # Russian full names
    "русский": "ru", "английский": "en", "иврит": "he",
    "немецкий": "de", "французский": "fr", "испанский": "es",
    "итальянский": "it", "португальский": "pt", "японский": "ja",
    "корейский": "ko", "китайский": "zh", "арабский": "ar",
    "турецкий": "tr", "нидерландский": "nl", "польский": "pl",
    "шведский": "sv", "датский": "da", "финский": "fi",
    "норвежский": "no", "чешский": "cs", "венгерский": "hu",
}


def normalize_lang_code(code: str) -> str:
    code = code.lower().replace("_", "-")
    if code in LANG_ALIAS:
        return LANG_ALIAS[code]
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


def tts_cache_path(voice: str, text: str, backend: str = "edge") -> str | None:
    cache_dir = tts_cache_dir()
    if cache_dir is None:
        return None
    digest = hashlib.sha256(f"{backend}\0{voice}\0{text}".encode("utf-8")).hexdigest()
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


### TTS Backend abstraction ###########################################

import abc
import typing


class TtsBackend(abc.ABC):
    """Base class for TTS backends. Subclasses register themselves in BACKEND_REGISTRY."""
    name: str = ""

    @classmethod
    @abc.abstractmethod
    def is_available(cls) -> bool:
        """Check if this backend's executables are installed."""
        ...

    @classmethod
    def list_voices(cls) -> list[tuple[str, str]]:
        """Return [(voice_name, lang_code), ...] for all available voices."""
        return []

    @classmethod
    def get_default_voice(cls, lang: str) -> str | None:
        """Return default voice name for the given ISO 639-1 language code, or None."""
        return None

    @classmethod
    def lang_from_voice(cls, voice: str) -> str:
        """Extract ISO 639-1 language code from a voice name."""
        return voice[:2].lower()

    @staticmethod
    def generate(text: str, voice: str, out: str) -> int:
        """Generate TTS audio file. Returns 0 on success."""
        return 1

    @classmethod
    def validate_voice(cls, voice: str) -> str | None:
        """Return a warning message if voice is likely invalid, else None."""
        return None


BACKEND_REGISTRY: dict[str, type[TtsBackend]] = {}


def register_backend(backend_cls: type[TtsBackend]) -> None:
    """Register a TTS backend class."""
    BACKEND_REGISTRY[backend_cls.name] = backend_cls


# ---------------------------------------------------------------------------
# Edge TTS backend
# ---------------------------------------------------------------------------

class EdgeTtsBackend(TtsBackend):
    name = "edge"
    _display_name = "edge-tts"

    @classmethod
    def is_available(cls) -> bool:
        try:
            rc = subprocess.run(
                ["python3", "-m", "edge_tts", "--help"],
                check=False, capture_output=True,
            )
            return rc.returncode == 0
        except OSError:
            return False

    @classmethod
    def list_voices(cls) -> list[tuple[str, str]]:
        rc = subprocess.run(
            ["python3", "-m", "edge_tts", "--list-voices"],
            check=False, capture_output=True, text=True,
        )
        if rc.returncode != 0:
            return []
        result: list[tuple[str, str]] = []
        for line in rc.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Format: "Name: ru-RU-SvetlanaNeural" — extract lang from locale
            name_part = line.split(":")[-1].strip()
            lang_code = name_part[:2].lower() if len(name_part) >= 2 else ""
            if lang_code:
                result.append((line, lang_code))
        return result

    @classmethod
    def get_default_voice(cls, lang: str) -> str | None:
        from rusa_shared import LANG_VOICE_MAP
        return LANG_VOICE_MAP.get(lang)

    @classmethod
    def validate_voice(cls, voice: str) -> str | None:
        rc = subprocess.run(
            ["python3", "-m", "edge_tts", "--list-voices"],
            check=False, capture_output=True, text=True,
        )
        if rc.returncode == 0 and voice not in rc.stdout:
            return f"Голос '{voice}' отсутствует в списке edge-tts --list-voices. Возможно, он удалён Microsoft."
        return None

    @staticmethod
    def generate(text: str, voice: str, out: str) -> int:
        return subprocess.run(
            ["edge-tts", "--voice", voice, "--text", text, "--write-media", out],
            capture_output=True, timeout=180, check=False,
        ).returncode


# ---------------------------------------------------------------------------
register_backend(EdgeTtsBackend)

### Custom TTS backend (--tts-cmd) ##################################


class CustomCmdBackend(TtsBackend):
    """User-defined TTS backend via --tts-cmd."""
    name = "custom"
    _cmd_template: str = ""

    @classmethod
    def set_template(cls, template: str) -> None:
        cls._cmd_template = template
        # Derive a display name from the first word of the command (for filenames etc.)
        if template and template.split():
            exe = template.split()[0]
            base = os.path.basename(exe).rsplit(".exe", 1)[0]
            for suffix in ("-test", "-cli", ".exe", ".py", ".sh", ".pl", ".rb"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
            cls._display_name = base or "custom"
        else:
            cls._display_name = "custom"
        # .name stays "custom" so BACKEND_REGISTRY lookup always works
        cls.name = "custom"

    @classmethod
    def is_available(cls) -> bool:
        if not cls._cmd_template:
            return False
        exe = cls._cmd_template.split()[0]
        return shutil.which(exe) is not None

    @classmethod
    def list_voices(cls) -> list[tuple[str, str]]:
        return []

    @classmethod
    def get_default_voice(cls, lang: str) -> str | None:
        return None

    @classmethod
    def lang_from_voice(cls, voice: str) -> str:
        return voice  # full voice name, we can't know the language

    @classmethod
    def validate_voice(cls, voice: str) -> str | None:
        return None

    @classmethod
    def generate(cls, text: str, voice: str, out: str) -> int:
        if not cls._cmd_template:
            return 1
        in_file = out + ".custom_in.txt"
        try:
            with open(in_file, "w", encoding="utf-8") as fh:
                fh.write(text)
            cmd = (cls._cmd_template
                   .replace("{in}", shlex.quote(in_file))
                   .replace("{out}", shlex.quote(out))
                   .replace("{voice}", shlex.quote(voice)))
            rc = subprocess.run(cmd, shell=True, capture_output=True, timeout=180)
            if rc.returncode != 0:
                err_msg = rc.stderr.decode("utf-8", errors="replace").strip()
                if err_msg:
                    print(f"  stderr: {err_msg}", file=sys.stderr)
            return rc.returncode
        except subprocess.TimeoutExpired:
            return 1
        except Exception as exc:
            print(f"  --tts-cmd error: {exc}", file=sys.stderr)
            return 1
        finally:
            try:
                os.remove(in_file)
            except OSError:
                pass


register_backend(CustomCmdBackend)

### End TTS Backend abstraction ########################################

# Register declarative external engines defined in engines.yaml / user config.
try:
    import rusa_engines
    rusa_engines.register_external_engines()
except ImportError:
    pass

### Terminal state guard ############################################
_TERM_SAVED = False
_TERM_FD = -1
_TERM_ATTRS = None


def _save_terminal() -> None:
    """Save current terminal attributes for restoration on exit."""
    global _TERM_SAVED, _TERM_FD, _TERM_ATTRS
    if _TERM_SAVED:
        return
    try:
        fd = sys.stdin.fileno()
        if os.isatty(fd):
            _TERM_FD = fd
            _TERM_ATTRS = termios.tcgetattr(fd)
            _TERM_SAVED = True
    except (termios.error, OSError, AttributeError):
        pass


def _restore_terminal() -> None:
    """Restore terminal attributes to saved state."""
    global _TERM_SAVED, _TERM_FD, _TERM_ATTRS
    if not _TERM_SAVED or _TERM_FD < 0 or _TERM_ATTRS is None:
        return
    try:
        termios.tcsetattr(_TERM_FD, termios.TCSANOW, _TERM_ATTRS)
    except (termios.error, OSError):
        pass
    finally:
        _TERM_SAVED = False
        _TERM_FD = -1
        _TERM_ATTRS = None


def _term_handler(signum: int, frame: object) -> None:
    """Signal handler: restore terminal and exit cleanly."""
    _restore_terminal()
    sys.exit(128 + signum)


### End terminal guard ##############################################
