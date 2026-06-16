"""Regression tests for CLI flow and ffmpeg fallback behavior."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


class _StopMain(Exception):
    """Sentinel exception to stop main() after the target branch."""


def test_main_without_codec_flag_reaches_subtitle_step(monkeypatch, tmp_path):
    """Default CLI path must not crash before subtitle extraction."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["python3", "-m", "edge_tts"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="ru-RU-SvetlanaNeural\n", stderr="")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(rusa.subprocess, "run", fake_run)
    monkeypatch.setattr(
        rusa,
        "step_extract_subtitles",
        lambda video, srt, tmpdir, target_lang=None: (_ for _ in ()).throw(_StopMain()),
    )
    monkeypatch.setattr(sys, "argv", ["rusa", str(video)])

    with pytest.raises(_StopMain):
        rusa.main()


def test_extract_subtitles_with_target_lang_does_not_fallback_to_plain_srt(tmp_path):
    """--lang must not silently accept an unrelated plain .srt file."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")
    plain_srt = tmp_path / "movie.srt"
    plain_srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nThis is English text\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        rusa.step_extract_subtitles(str(video), None, str(tmp_path), "he")


def test_main_rejects_unsupported_lang_without_explicit_voice(monkeypatch, tmp_path, capsys):
    """Unsupported --lang must fail clearly instead of falling back to Russian."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")

    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        rusa.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    monkeypatch.setattr(sys, "argv", ["rusa", "--lang", "el", str(video)])

    with pytest.raises(SystemExit):
        rusa.main()

    captured = capsys.readouterr()
    assert "--voice" in captured.err
    assert "el" in captured.err


def test_step_mix_output_retries_mov_text_subtitles_as_srt(monkeypatch, tmp_path):
    """mov_text subtitles in source container should be re-encoded for mkv output."""
    video = tmp_path / "input.mp4"
    voiceover = tmp_path / "voiceover.wav"
    output = tmp_path / "output.mkv"
    video.write_bytes(b"video")
    voiceover.write_bytes(b"wav")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "-filter_complex" in cmd:
            (tmp_path / "mixed.wav").write_bytes(b"mixed")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd[:3] == ["ffmpeg", "-hide_banner", "-encoders"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="libopus\naac\n", stderr="")
        if "-metadata:s:a:1" in cmd and "-c:s" in cmd:
            subtitle_codec = cmd[cmd.index("-c:s") + 1]
            if subtitle_codec == "copy":
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout=b"",
                    stderr=(
                        b"[matroska @ 0x1] Subtitle codec mov_text (94213) is not supported.\n"
                        b"Could not write header\n"
                    ),
                )
            if subtitle_codec == "srt":
                output.write_bytes(b"ok")
                return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    rusa.step_mix_output(
        str(video),
        str(voiceover),
        rusa.DEFAULT_ORIG_VOL,
        rusa.DEFAULT_TTS_VOL,
        str(output),
        str(tmp_path),
        "opus",
        "64",
        None,
        False,
    )

    subtitle_codecs = [
        cmd[cmd.index("-c:s") + 1]
        for cmd in calls
        if "-c:s" in cmd and "-metadata:s:a:1" in cmd
    ]
    assert subtitle_codecs == ["copy", "srt"]


def test_step_mix_output_codec_error_lists_alternatives(monkeypatch, tmp_path, capsys):
    """Unavailable audio encoder should produce a clear error, not NameError."""
    video = tmp_path / "input.mkv"
    voiceover = tmp_path / "voiceover.wav"
    video.write_bytes(b"video")
    voiceover.write_bytes(b"wav")

    def fake_run(cmd, **kwargs):
        if "-filter_complex" in cmd:
            (tmp_path / "mixed.wav").write_bytes(b"mixed")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    def fake_check(codec):
        return codec != "libopus"

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)
    monkeypatch.setattr(rusa, "_check_ffmpeg_codec", fake_check)

    with pytest.raises(SystemExit):
        rusa.step_mix_output(
            str(video),
            str(voiceover),
            rusa.DEFAULT_ORIG_VOL,
            rusa.DEFAULT_TTS_VOL,
            str(tmp_path / "out.mkv"),
            str(tmp_path),
            "opus",
            "64",
            None,
            False,
        )

    captured = capsys.readouterr()
    assert "--aac" in captured.err or "--mp3" in captured.err or "--ac3" in captured.err
