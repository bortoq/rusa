#!/usr/bin/env python3
from __future__ import annotations
"""Declarative external TTS engine backend for rusa.

Engines are defined in YAML files (bundled engines.yaml + user override in
~/.config/rusa/engines.yaml). Each engine only needs a binary, a generate
command template, and optionally a voice list command/parser.
"""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rusa_shared import TtsBackend, register_backend

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]
    HAS_YAML = False


__all__ = ["ExternalTtsBackend", "load_engine_configs", "register_external_engines"]


def _guess_lang(voice: str) -> str:
    """Extract a 2-letter ISO code from a voice name like ru_RU-dmitri."""
    if "-" in voice and len(voice) >= 2:
        return voice[:2].lower()
    return "und"


def _format_cmd(template: str, **kwargs: Any) -> str:
    """Format a command template with shell-quoted values."""
    formatted: dict[str, str] = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            formatted[key] = shlex.quote(value)
        else:
            formatted[key] = str(value)
    return template.format(**formatted)


def _one_per_line_parser(stdout: str, cfg: dict) -> list[tuple[str, str]]:
    """Treat each non-empty line as a voice name."""
    voices: list[tuple[str, str]] = []
    for line in stdout.strip().splitlines():
        voice = line.strip()
        if voice:
            voices.append((voice, _guess_lang(voice)))
    return voices


def _static_voice_parser(stdout: str, cfg: dict) -> list[tuple[str, str]]:
    """Use static_voices from the engine config."""
    voices: list[tuple[str, str]] = []
    for voice in cfg.get("static_voices", []) or []:
        voices.append((str(voice), _guess_lang(str(voice))))
    return voices


def _espeak_voice_parser(stdout: str, cfg: dict) -> list[tuple[str, str]]:
    """Parse espeak-ng --voices output.

    Expected format (whitespace-separated columns):
      Pty Language Age/Gender VoiceName File Other Languages
    """
    voices: list[tuple[str, str]] = []
    for line in stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        if not parts[0].isdigit():
            continue
        lang = parts[1]
        voice = parts[3] if len(parts) > 3 else lang
        voices.append((voice, lang[:2].lower() if len(lang) >= 2 else "und"))
    return voices


_VOICE_PARSERS: dict[str, Any] = {
    "static": _static_voice_parser,
    "one_per_line": _one_per_line_parser,
    "espeak": _espeak_voice_parser,
}


class ExternalTtsBackend(TtsBackend):
    """TTS backend loaded from a declarative YAML engine definition."""

    name: str = ""
    _config: dict = {}

    @classmethod
    def _display_name(cls) -> str:
        return cls._config.get("display_name") or cls.name

    @classmethod
    def is_available(cls) -> bool:
        return bool(cls._config) and shutil.which(cls._config.get("binary", "")) is not None

    @classmethod
    def list_voices(cls) -> list[tuple[str, str]]:
        parser_name = cls._config.get("voice_parser", "static")
        parser = _VOICE_PARSERS.get(parser_name, _static_voice_parser)
        list_cmd = cls._config.get("list_voices_cmd")
        if list_cmd:
            try:
                rc = subprocess.run(
                    list_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if rc.returncode == 0:
                    return parser(rc.stdout, cls._config)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return parser("", cls._config)

    @classmethod
    def get_default_voice(cls, lang: str) -> str | None:
        return cls._config.get("default_voice")

    @classmethod
    def lang_from_voice(cls, voice: str) -> str:
        return _guess_lang(voice)

    @classmethod
    def validate_voice(cls, voice: str) -> str | None:
        if not voice:
            return "Голос не указан"
        available = {v for v, _ in cls.list_voices()}
        if available and voice not in available:
            return (
                f"Голос '{voice}' отсутствует в списке доступных для движка '{cls.name}'. "
                f"Доступные: {', '.join(sorted(available))}"
            )
        return None

    @classmethod
    def generate(cls, text: str, voice: str, out: str) -> int:
        if not cls._config or "generate_cmd" not in cls._config:
            return 1
        in_file = out + ".external_in.txt"
        try:
            with open(in_file, "w", encoding="utf-8") as fh:
                fh.write(text)
            cmd = _format_cmd(
                cls._config["generate_cmd"],
                **{"in": in_file, "out": out, "voice": voice},
            )
            rc = subprocess.run(cmd, shell=True, capture_output=True, timeout=180, check=False)
            if rc.returncode != 0:
                err_msg = rc.stderr.decode("utf-8", errors="replace").strip()
                if err_msg:
                    print(f"  stderr: {err_msg}", file=sys.stderr)
            return rc.returncode
        except subprocess.TimeoutExpired:
            return 1
        except Exception as exc:  # pragma: no cover
            print(f"  --engine {cls.name} error: {exc}", file=sys.stderr)
            return 1
        finally:
            try:
                os.remove(in_file)
            except OSError:
                pass


def _load_yaml(path: str) -> dict:
    if not HAS_YAML:
        raise ImportError("PyYAML не установлен (pip install pyyaml)")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _user_engines_path() -> Path:
    return Path.home() / ".config" / "rusa" / "engines.yaml"


_BUNDLED_ENGINES: dict[str, dict] = {
    "piper": {
        "display_name": "piper",
        "binary": "piper",
        "output_format": "wav",
        "default_voice": "ru_RU-dmitri-medium",
        "static_voices": [
            "ru_RU-dmitri-medium",
            "ru_RU-irina-medium",
            "en_US-lessac-medium",
            "en_US-ryan-medium",
            "de_DE-thorsten-medium",
            "fr_FR-siwis-medium",
        ],
        "generate_cmd": "piper --model {voice} --output_file {out} --json-input < {in}",
        "voice_parser": "static",
    },
    "rhvoice": {
        "display_name": "rhvoice",
        "binary": "RHVoice-test",
        "output_format": "wav",
        "default_voice": "elena",
        "static_voices": ["elena", "anna", "aleksandr"],
        "generate_cmd": "RHVoice-test -p {voice} -i {in} -o {out}",
        "voice_parser": "static",
    },
    "espeak": {
        "display_name": "espeak",
        "binary": "espeak-ng",
        "output_format": "wav",
        "default_voice": "ru",
        "list_voices_cmd": "espeak-ng --voices",
        "generate_cmd": "espeak-ng -v {voice} -f {in} -w {out}",
        "voice_parser": "espeak",
    },
    "gtts": {
        "display_name": "gtts",
        "binary": "gtts-cli",
        "output_format": "mp3",
        "default_voice": "ru",
        "static_voices": ["ru", "en", "de", "fr", "es", "it"],
        "generate_cmd": "gtts-cli --lang {voice} -f {in} -o {out}",
        "voice_parser": "static",
    },
    "festival": {
        "display_name": "festival",
        "binary": "text2wave",
        "output_format": "wav",
        "default_voice": "default",
        "static_voices": ["default"],
        "generate_cmd": "text2wave -o {out} {in}",
        "voice_parser": "static",
    },
}


def load_engine_configs() -> dict[str, dict]:
    """Load bundled and user-defined engine configs.

    User config overrides bundled engines by name. If the bundled engines.yaml
    is missing or PyYAML is unavailable, the built-in _BUNDLED_ENGINES are used.
    """
    configs: dict[str, dict] = dict(_BUNDLED_ENGINES)

    # Bundled engines file (optional override of the built-in defaults)
    bundled = Path(__file__).parent / "engines.yaml"
    if bundled.exists() and HAS_YAML:
        try:
            data = _load_yaml(str(bundled))
            configs.update(data.get("engines", {}))
        except Exception as exc:
            print(f"Warning: failed to load bundled engines: {exc}", file=sys.stderr)

    # User override
    user_path = _user_engines_path()
    if user_path.exists() and HAS_YAML:
        try:
            data = _load_yaml(str(user_path))
            configs.update(data.get("engines", {}))
        except Exception as exc:
            print(f"Warning: failed to load user engines from {user_path}: {exc}", file=sys.stderr)

    return configs


def register_external_engines(configs: dict[str, dict] | None = None) -> None:
    """Create and register ExternalTtsBackend subclasses for each engine config."""
    if configs is None:
        configs = load_engine_configs()
    for engine_id, cfg in configs.items():
        if not cfg:
            continue
        cls_name = "".join(part.capitalize() for part in engine_id.replace("-", "_").split("_")) + "Backend"
        cls = type(
            cls_name,
            (ExternalTtsBackend,),
            {"name": engine_id, "_config": cfg},
        )
        register_backend(cls)
