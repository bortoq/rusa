"""Tests for rusa WebUI."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is in path
PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


class TestConfig:
    """webui/config.py"""

    def test_defaults_exist(self):
        from webui.config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TITLE, AUDIO_CODECS

        assert DEFAULT_HOST == "127.0.0.1"
        assert isinstance(DEFAULT_PORT, int)
        assert DEFAULT_TITLE
        assert "aac" in AUDIO_CODECS
        assert "mp3" in AUDIO_CODECS
        assert "opus" in AUDIO_CODECS
        assert "ac3" in AUDIO_CODECS

    def test_codec_bitrates(self):
        from webui.config import AUDIO_CODECS

        for codec in ("aac", "mp3", "opus", "ac3"):
            assert "bitrates" in AUDIO_CODECS[codec]
            assert codec != "opus" or "64" in AUDIO_CODECS[codec]["bitrates"]

    def test_subs_modes(self):
        from webui.config import SUBS_MODES

        assert "auto" in SUBS_MODES
        assert "copy" in SUBS_MODES
        assert "convert" in SUBS_MODES
        assert "drop" in SUBS_MODES

    def test_normalize_options(self):
        from webui.config import NORMALIZE_OPTIONS

        options = {v: k for k, v in NORMALIZE_OPTIONS}
        assert "" in options  # disabled
        assert "fast" in options
        assert "fine" in options


class TestBuildArgs:
    """webui/utils.py — build_args()"""

    def test_minimal_args(self):
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/movie.mkv")
        assert ns.video == "/tmp/movie.mkv"
        assert ns.speed == "1.5"
        assert ns.orig_vol == "0.65"
        assert ns.tts_vol == "0.93"
        assert ns.threads == 6
        assert ns.subs_mode == "auto"
        assert ns.cache_stats is False

    def test_voice_and_lang(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            voice="ru-RU-DmitryNeural",
            lang="ru",
            speed=1.8,
        )
        assert ns.voice == "ru-RU-DmitryNeural"
        assert ns.lang == "ru"
        assert ns.speed == "1.8"

    def test_custom_tts_cmd(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            tts_cmd="espeak-ng -w {out} -f {in} -v {voice}",
            voice="ru",
        )
        assert ns.tts_cmd == "espeak-ng -w {out} -f {in} -v {voice}"

    def test_audio_codec(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            audio_fmt="aac",
            audio_bitrate="192",
        )
        assert ns.aac == "192"
        assert ns.mp3 is None
        assert ns.opus is None
        assert ns.ac3 is None

    def test_advanced_flags(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
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
            video_path="/tmp/movie.mkv",
            preview=10,
            range_from=5,
            range_to=50,
        )
        assert ns.preview == 10
        assert ns.range_from == 5
        assert ns.range_to == 50


class TestApp:
    """webui/app.py — create_app()"""

    def test_create_app(self):
        from webui.app import create_app

        app = create_app()
        assert app is not None
        assert app.title == "rusa — Закадровый перевод видео"

    def test_app_components(self):
        from webui.app import create_app

        app = create_app()
        # Check key blocks/components exist
        assert len(app.blocks) > 0  # has UI components

    def test_process_video_no_file(self):
        """_process_video should handle missing file gracefully."""
        from webui.app import _process_video

        gen = _process_video(
            video_file=None,
            srt_file=None,
            lang=None,
            voice=None,
            tts_cmd="",
            speed=1.5,
            orig_vol=0.65,
            tts_vol=0.93,
            codec_label="Opus",
            bitrate="64",
            normalize="",
            subs_mode="auto",
            sync=False,
            audio_only=False,
            keep_temp=False,
            no_cache=False,
        )
        logs = list(gen)
        # Should return with error about no video
        assert any("ffmpeg" in str(log) for log in logs) or any(
            "Ошибка" in str(log) for log in logs
        )


class TestComponents:
    """webui/components.py"""

    def test_lang_selector_choices(self):
        from webui.components import create_lang_selector

        dd = create_lang_selector()
        assert dd is not None


class TestCLIIntegration:
    """--webui flag in CLI"""

    def test_webui_flag_accepted(self):
        """The --webui flag should be parseable."""
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui"])
        assert ns.webui is True

    def test_webui_flag_false_by_default(self):
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["movie.mkv"])
        assert ns.webui is False

    def test_webui_flag_with_video(self):
        """--webui with a video argument should ignore the video."""
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui", "movie.mkv"])
        assert ns.webui is True
        assert ns.video == "movie.mkv"
