"""CLI smoke tests that exercise the real entry script in a subprocess."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
RUSA_SCRIPT = PROJECT_DIR / "rusa.py"


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(RUSA_SCRIPT), *args],
        cwd=str(PROJECT_DIR),
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_fake_command(bin_dir: Path, name: str) -> None:
    """Create a fake executable command in *bin_dir*.

    Uses POSIX shell scripts on Unix and `.cmd` wrappers on Windows so that
    both `subprocess.run([name, ...])` and `shutil.which(name)` behave as
    expected on CI.
    """
    if os.name == "nt":
        path = bin_dir / f"{name}.cmd"
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path = bin_dir / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)



def _make_fake_runtime(tmp_path: Path) -> dict[str, str]:
    """Create fake toolchain for subprocess-based CLI smoke tests."""
    bin_dir = tmp_path / "bin"
    py_dir = tmp_path / "py"
    bin_dir.mkdir()
    py_dir.mkdir()

    for name in ("ffmpeg", "ffprobe", "piper", "espeak-ng", "gtts-cli", "text2wave", "RHVoice-test"):
        _write_fake_command(bin_dir, name)

    edge_tts = py_dir / "edge_tts.py"
    edge_tts.write_text(
        textwrap.dedent(
            """\
            import sys

            if "--list-voices" in sys.argv:
                print("Name: ru-RU-SvetlanaNeural")
                print("Name: en-US-AriaNeural")
                print("Name: he-IL-HilaNeural")
                raise SystemExit(0)
            if "--help" in sys.argv:
                print("edge_tts help")
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
    )

    env = {
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "PYTHONPATH": str(py_dir) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    return env


def test_cli_help_smoke() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "usage: rusa" in result.stdout.lower()
    assert "--voice" in result.stdout


def test_cli_version_smoke() -> None:
    result = _run_cli("--version")
    assert result.returncode == 0
    assert "rusa 0.1.0" in result.stdout


def test_cli_voice_list_default_engine_smoke(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    result = _run_cli("--voice", env=env)
    assert result.returncode == 0
    assert "edge-tts:" in result.stdout.lower()
    assert "ru-RU-SvetlanaNeural" in result.stdout



def test_cli_without_args_prints_help() -> None:
    result = _run_cli()
    assert result.returncode == 0
    assert "usage: rusa" in result.stdout.lower()


def test_cli_missing_video_fails_cleanly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mkv"
    result = _run_cli(str(missing))
    assert result.returncode == 1
    assert "File not found" in result.stderr


def test_cli_cache_stats_smoke(tmp_path: Path) -> None:
    result = _run_cli("--cache-stats", env={"RUSA_CACHE_DIR": str(tmp_path / "cache")})
    assert result.returncode == 0
    assert "Cache" in result.stdout


def test_cli_cache_clear_smoke(tmp_path: Path) -> None:
    result = _run_cli("--cache-clear", env={"RUSA_CACHE_DIR": str(tmp_path / "cache")})
    assert result.returncode == 0
    assert "Cache" in result.stdout


def test_cli_dry_run_with_external_srt_smoke(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nSecond line\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "--dry-run",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Dry run plan" in result.stdout
    assert "Subtitles: 2" in result.stdout
    assert "Hello world" in result.stdout



def test_cli_dry_run_with_sidecar_lang_srt_smoke(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    sidecar = tmp_path / "movie.he.srt"
    video.write_bytes(b"fake video")
    sidecar.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nשלום\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "--dry-run",
        "--lang", "he",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Language: he" in result.stdout
    assert "he-IL-HilaNeural" in result.stdout
    assert "Subtitles: 1" in result.stdout



def test_cli_preview_affects_dry_run_plan(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nOne\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nTwo\n\n"
        "3\n00:00:05,000 --> 00:00:06,000\nThree\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "--preview", "2",
        "--dry-run",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Subtitles: 2" in result.stdout
    assert "One" in result.stdout
    assert "Two" in result.stdout
    assert "Three" not in result.stdout



def test_cli_overwrite_flag_changes_existing_output_behavior(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    output = tmp_path / "out.mkv"
    video.write_bytes(b"fake video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    output.write_bytes(b"existing")

    fail_result = _run_cli(
        "--dry-run",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        "-o", str(output),
        str(video),
        env=env,
    )
    assert fail_result.returncode == 2
    assert "--overwrite" in fail_result.stderr

    ok_result = _run_cli(
        "--overwrite",
        "--dry-run",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        "-o", str(output),
        str(video),
        env=env,
    )
    assert ok_result.returncode == 0
    assert "Dry run plan" in ok_result.stdout



def test_cli_voice_list_for_piper_engine_smoke(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    result = _run_cli("--engine", "piper", "--voice", env=env)
    assert result.returncode == 0
    assert "piper:" in result.stdout.lower()
    assert "ru_RU-dmitri-medium" in result.stdout



def test_cli_invalid_engine_fails_cleanly(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake video")
    result = _run_cli("--engine", "nope", str(video), env=env)
    assert result.returncode == 2
    assert "Unknown TTS engine" in result.stderr



def test_cli_lang_alias_hebrew_selects_hebrew_voice_in_dry_run(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    result = _run_cli(
        "--dry-run",
        "-s", str(srt),
        "--lang", "hebrew",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Language: he" in result.stdout
    assert "he-IL-HilaNeural" in result.stdout



def test_cli_subs_mode_drop_is_visible_in_output(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    result = _run_cli(
        "--dry-run",
        "--subs-mode", "drop",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Subtitles: drop" in result.stdout



def test_cli_engine_piper_dry_run_smoke(tmp_path: Path) -> None:
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    result = _run_cli(
        "--dry-run",
        "--engine", "piper",
        "--voice", "ru_RU-dmitri-medium",
        "-s", str(srt),
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Engine: piper" in result.stdout
    assert "ru_RU-dmitri-medium" in result.stdout



def test_cli_missing_ffmpeg_fails_with_dependency_exit_code(tmp_path: Path) -> None:
    py_dir = tmp_path / "py"
    py_dir.mkdir()
    (py_dir / "edge_tts.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    env = {
        "PATH": "",
        "PYTHONPATH": str(py_dir),
    }
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "movie.srt"
    video.write_bytes(b"fake video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

    result = _run_cli(
        "--dry-run",
        "-s", str(srt),
        "--voice", "ru-RU-SvetlanaNeural",
        str(video),
        env=env,
    )
    assert result.returncode == 3
    assert "ffmpeg" in result.stderr.lower()





def test_cli_dry_run_non_ascii_sidecar_no_crash(tmp_path: Path) -> None:
    """Non-ASCII subtitle text must not crash on any platform.

    Regression test for Windows ``UnicodeEncodeError`` with limited console
    encodings (cp1252/cp866).  Characters outside the Latin-1 range (CJK,
    emoji, etc.) must be silently replaced rather than raising an error.
    """
    env = _make_fake_runtime(tmp_path)
    video = tmp_path / "movie.mkv"
    sidecar = tmp_path / "movie.ja.srt"
    video.write_bytes(b"fake video")
    sidecar.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこんにちは世界\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n\u2603\u2601\ufe0f\n",  # snowman + cloud + emoji
        encoding="utf-8",
    )

    result = _run_cli(
        "--dry-run",
        "--lang", "ja",
        str(video),
        env=env,
    )
    assert result.returncode == 0
    assert "Language: ja" in result.stdout
    assert "Subtitles: 2" in result.stdout
