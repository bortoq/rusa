"""Tests for webui shared modules (config, utils, CLI integration).

These tests do NOT require Gradio — they test the configuration
constants, argument building, and CLI flag parsing.
"""
from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from webui.config import (
    AUDIO_CODECS,
    DEFAULT_DESCRIPTION,
    DEFAULT_HOST,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PORT,
    DEFAULT_TITLE,
    NORMALIZE_OPTIONS,
    SPEED_MAX,
    SPEED_MIN,
    SPEED_STEP,
    SUBS_MODES,
    VOLUME_MAX,
    VOLUME_MIN,
    VOLUME_STEP,
)


# ── Config ────────────────────────────────────────────────────────────


class TestConfig:
    """webui/config.py default values."""

    def test_defaults_exist(self):
        assert DEFAULT_HOST == "127.0.0.1"
        assert DEFAULT_PORT == 7860
        assert isinstance(DEFAULT_TITLE, str) and len(DEFAULT_TITLE) > 0
        assert isinstance(DEFAULT_DESCRIPTION, str) and len(DEFAULT_DESCRIPTION) > 0
        assert DEFAULT_OUTPUT_DIR.endswith("Downloads/rusa")

    def test_codec_bitrates(self):
        for codec_key, info in AUDIO_CODECS.items():
            assert "label" in info
            assert "default" in info
            assert "bitrates" in info
            assert info["default"] in info["bitrates"]

    def test_subs_modes(self):
        assert "auto" in SUBS_MODES
        assert "copy" in SUBS_MODES
        assert "convert" in SUBS_MODES
        assert "drop" in SUBS_MODES

    def test_normalize_options(self):
        labels = [label for label, _ in NORMALIZE_OPTIONS]
        assert "Выкл" in labels
        assert "Быстрая" in labels
        assert "Точная" in labels


# ── BuildArgs ─────────────────────────────────────────────────────────


class TestBuildArgs:
    """webui/utils.py build_args() function."""

    def test_minimal_args(self):
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/test.mkv")
        assert isinstance(ns, Namespace)
        assert ns.video == "/tmp/test.mkv"
        assert ns.srt is None
        assert ns.speed == "1.5"
        assert ns.subs_mode == "auto"

    def test_voice_and_lang(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/test.mkv",
            voice="ru-RU-SvetlanaNeural",
            lang="ru",
        )
        assert ns.voice == "ru-RU-SvetlanaNeural"
        assert ns.lang == "ru"

    def test_custom_tts_cmd(self):
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/t.mkv", tts_cmd="espeak {in} {out} {voice}")
        assert ns.tts_cmd == "espeak {in} {out} {voice}"

    def test_audio_codec(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/t.mkv",
            audio_fmt="aac",
            audio_bitrate="128",
        )
        assert ns.aac == "128"
        assert ns.mp3 is None
        assert ns.opus is None

    def test_advanced_flags(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/t.mkv",
            sync=True,
            audio_only=True,
            keep_temp=True,
            no_cache=True,
        )
        assert ns.sync is True
        assert ns.audio_only is True
        assert ns.keep_temp is True
        assert ns.no_cache is True

    def test_preview_and_range(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/t.mkv",
            preview=10,
            range_from=5,
            range_to=30,
        )
        assert ns.preview == 10
        assert ns.range_from == 5
        assert ns.range_to == 30

    def test_webui_flag_in_build_args(self):
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/t.mkv")
        assert ns.webui is False

    def test_rusa_main_accepts_namespace(self):
        """Verify that the output of build_args() can be passed to rusa.main()

        without raising a TypeError about unexpected arguments.
        """
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/test.mkv")
        from rusa import main

        # main() takes a single Namespace arg; verify ours has all required fields
        required = {"video", "srt", "voice", "lang", "speed", "orig_vol",
                     "tts_vol", "threads", "tts_cmd", "engine", "normalize",
                     "subs_mode", "merge_sentences", "keep_temp", "sync",
                     "audio_only", "output", "dry_run", "no_cache",
                     "range_from", "range_to", "preview", "webui",
                     "cache_stats", "cache_clear", "aac", "mp3", "opus", "ac3"}
        ns_keys = set(vars(ns).keys())
        missing = required - ns_keys
        assert not missing, f"build_args() missing keys required by main(): {missing}"
        # Many optional fields can be None — that's fine
        assert ns.video == "/tmp/test.mkv"
        assert ns.speed == "1.5"
        assert ns.subs_mode == "auto"
        assert ns.webui is False

    def test_signal_safe_in_background_thread(self):
        """build_args must work in a thread with modified signal handlers.

        Some GUI frameworks override SIGINT handler, which can break
        signal.SIGINT-based code.  The function must not use signal.
        """
        import signal
        import threading

        errors: list[Exception] = []

        def _run() -> None:
            try:
                from webui.utils import build_args

                build_args(video_path="/tmp/test.mkv")
            except Exception as exc:
                errors.append(exc)

        # Install an alternative SIGINT handler (simulates a GUI thread)
        orig = signal.signal(signal.SIGINT, lambda s, f: None)
        try:
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=5)
        finally:
            signal.signal(signal.SIGINT, orig)

        assert not errors, f"build_args raised in background thread: {errors}"


# ── CLI Integration ───────────────────────────────────────────────────


class TestCLIIntegration:
    """Tests for --webui flag in rusa_cli.py argument parser."""

    def test_webui_flag_accepted(self):
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui", "/tmp/test.mkv"])
        assert ns.webui is True

    def test_webui_flag_false_by_default(self):
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["/tmp/test.mkv"])
        assert ns.webui is False

    def test_webui_flag_with_video(self):
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui", "/tmp/video.mkv"])
        assert ns.webui is True
        assert "/tmp/video.mkv" in str(ns.video)


# ── Output File Picker (tkinter helper) ──────────────────────────────


def _display_available() -> bool:
    """Check if tkinter can create windows (display available)."""
    import tkinter as tk
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@pytest.mark.skipif(not _display_available(), reason="No display available")
class TestOutputFilePicker:
    """webui/utils.py pick_output_file() — tkinter dialog helper."""

    def test_pick_output_file_returns_path(self, monkeypatch):
        from webui.utils import pick_output_file

        def _fake_asksaveasfilename(**kw):
            return "/home/user/Downloads/output.mp4"

        monkeypatch.setattr(
            "tkinter.filedialog.asksaveasfilename",
            _fake_asksaveasfilename,
        )
        result = pick_output_file("output.mp4")
        assert result == "/home/user/Downloads/output.mp4"

    def test_pick_output_file_cancelled(self, monkeypatch):
        from webui.utils import pick_output_file

        def _fake_cancel(**kw):
            return ""

        monkeypatch.setattr(
            "tkinter.filedialog.asksaveasfilename",
            _fake_cancel,
        )
        result = pick_output_file("output.mp4")
        assert result is None

    def test_pick_output_file_tkinter_unavailable(self, monkeypatch):
        from webui.utils import pick_output_file

        def _fake_import(*args, **kw):
            raise ImportError("no tkinter")

        monkeypatch.setattr("builtins.__import__", _fake_import)
        result = pick_output_file("output.mp4")
        assert result is None
