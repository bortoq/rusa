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
    monkeypatch.setattr(sys, "argv", ["rusa", "--lang", "xh", str(video)])

    with pytest.raises(SystemExit):
        rusa.main()

    captured = capsys.readouterr()
    assert "--voice" in captured.err
    assert "xh" in captured.err


def test_step_mix_output_preflights_mov_text_subtitles_to_srt_for_mkv(monkeypatch, tmp_path):
    """Known-incompatible mov_text subtitles should convert directly for mkv output."""
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="mov_text\n", stderr="")
        if "-metadata:s:a:1" in cmd and "-c:s" in cmd:
            subtitle_codec = cmd[cmd.index("-c:s") + 1]
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
    assert subtitle_codecs == ["srt"]


def test_parser_subs_mode_defaults_to_auto():
    args = rusa._get_parser().parse_args(["movie.mkv"])
    assert args.subs_mode == "auto"


def test_custom_cmd_display_name_uses_basename_only(monkeypatch, tmp_path):
    """Regression for 0185b91: absolute path in --tts-cmd must not create slashes in output filename."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")
    custom_script = tmp_path / "bin" / "tts_silero.py"
    custom_script.parent.mkdir(parents=True)
    custom_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    custom_script.chmod(0o755)

    received_output: list[str] = []

    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        rusa.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="ru-RU-SvetlanaNeural\n", stderr=""),
    )
    monkeypatch.setattr(sys, "argv", [
        "rusa",
        "--tts-cmd", f"{custom_script} {{in}} {{out}} {{voice}}",
        "--voice", "baya",
        "--lang", "ru",
        str(video),
    ])
    monkeypatch.setattr(
        rusa, "step_extract_subtitles",
        lambda video, srt, tmpdir, target_lang=None: str(tmp_path / "subs.srt"),
    )
    monkeypatch.setattr(rusa, "detect_language_from_srt", lambda srt: None)
    monkeypatch.setattr(rusa, "step_parse_srt", lambda *args, **kwargs: ([{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "test"}], 1))
    monkeypatch.setattr(rusa, "step_generate_tts", lambda *args, **kwargs: [(1, str(tmp_path / "line.mp3"))])
    monkeypatch.setattr(rusa, "step_convert_wav", lambda *args, **kwargs: [(1, str(tmp_path / "line.wav"), 100.0)])
    monkeypatch.setattr(rusa, "step_assemble", lambda *args, **kwargs: str(tmp_path / "voiceover.wav"))
    monkeypatch.setattr(rusa, "step_mix_output", lambda *args, **kwargs: received_output.append(args[4]))

    rusa.main()

    assert len(received_output) == 1
    output = received_output[0]
    assert os.path.basename(output) == "movie_tts_silero_ru.mkv"
    assert "/" not in os.path.basename(output)
    assert str(custom_script) not in output


def test_dry_run_prints_plan_and_exits(monkeypatch, tmp_path, capsys):
    """--dry-run should print plan and exit without generating TTS."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")
    srt = tmp_path / "movie.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nSecond line\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["rusa", "--dry-run", "-s", str(srt), str(video)])
    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        rusa.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="ru-RU-SvetlanaNeural\n", stderr=""),
    )

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Dry run plan" in out
    assert "Hello world" in out
    assert "Second line" in out
    assert "Subtitles: 2" in out


def test_preview_limits_subtitles(monkeypatch, tmp_path, capsys):
    """--preview N should generate only first N subtitles."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")
    srt = tmp_path / "movie.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nSecond line\n\n"
        "3\n00:00:09,000 --> 00:00:12,000\nThird line\n",
        encoding="utf-8",
    )

    tts_calls: list[tuple] = []

    def fake_generate_tts(entries, voice, threads, tmpdir, backend="edge"):
        tts_calls.append((len(entries), [e["text"] for e in entries]))
        return []

    monkeypatch.setattr(sys, "argv", ["rusa", "--preview", "2", "-s", str(srt), str(video)])
    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        rusa.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="ru-RU-SvetlanaNeural\n", stderr=""),
    )
    monkeypatch.setattr(rusa, "step_generate_tts", fake_generate_tts)
    monkeypatch.setattr(rusa, "step_convert_wav", lambda *args, **kwargs: [])

    with pytest.raises(SystemExit):
        rusa.main()

    assert len(tts_calls) == 1
    assert tts_calls[0][0] == 2
    assert tts_calls[0][1] == ["Hello world", "Second line"]


def test_custom_cmd_requires_explicit_voice(monkeypatch, tmp_path, capsys):
    """--tts-cmd without --voice must fail early with a clear message."""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")
    custom_script = tmp_path / "bin" / "tts_silero.py"
    custom_script.parent.mkdir(parents=True)
    custom_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    custom_script.chmod(0o755)

    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(sys, "argv", [
        "rusa",
        "--tts-cmd", f"{custom_script} {{in}} {{out}} {{voice}}",
        str(video),
    ])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == rusa.EXIT_USAGE_ERROR
    assert "--voice" in capsys.readouterr().err


def test_step_mix_output_subs_mode_drop_skips_subtitle_mapping(monkeypatch, tmp_path):
    """drop mode must write video without subtitle maps or subtitle codec settings."""
    video = tmp_path / "input.mkv"
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
        if "-metadata:s:a:1" in cmd:
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
        subs_mode="drop",
    )

    mux_cmd = next(cmd for cmd in calls if "-metadata:s:a:1" in cmd)
    assert "-map" in mux_cmd
    assert "0:s?" not in mux_cmd
    assert "-c:s" not in mux_cmd


def test_step_mix_output_subs_mode_copy_fails_on_incompatible_subtitles(monkeypatch, tmp_path, capsys):
    """copy mode must fail clearly before mux fallback when subtitles cannot be copied."""
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="mov_text\n", stderr="")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
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
            subs_mode="copy",
        )

    captured = capsys.readouterr()
    assert "--subs-mode convert" in captured.err
    assert "mov_text" in captured.err
    mux_cmds = [cmd for cmd in calls if "-metadata:s:a:1" in cmd]
    assert mux_cmds == []


def test_step_mix_output_subs_mode_copy_fails_when_any_mapped_subtitle_stream_is_incompatible(
    monkeypatch, tmp_path, capsys
):
    """copy mode must preflight all mapped subtitle streams, not only the first one."""
    video = tmp_path / "input.mkv"
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="subrip\nmov_text\n", stderr="")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
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
            subs_mode="copy",
        )

    captured = capsys.readouterr()
    assert "mov_text" in captured.err
    mux_cmds = [cmd for cmd in calls if "-metadata:s:a:1" in cmd]
    assert mux_cmds == []


def test_step_mix_output_subs_mode_copy_fails_explicitly_when_ffprobe_cannot_verify(
    monkeypatch, tmp_path, capsys
):
    """copy mode should fail clearly when subtitle codec preflight is unavailable."""
    video = tmp_path / "input.mkv"
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="probe failed")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
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
            subs_mode="copy",
        )

    captured = capsys.readouterr()
    assert "Не удалось надёжно проверить совместимость" in captured.err
    mux_cmds = [cmd for cmd in calls if "-metadata:s:a:1" in cmd]
    assert mux_cmds == []


def test_step_mix_output_subs_mode_copy_allows_mkv_compatible_non_text_subtitles(monkeypatch, tmp_path):
    """copy mode should allow mkv-compatible subtitle codecs beyond the old text-only allowlist."""
    video = tmp_path / "input.mkv"
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="hdmv_pgs_subtitle\n", stderr="")
        if "-metadata:s:a:1" in cmd and "-c:s" in cmd:
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
        subs_mode="copy",
    )

    subtitle_codecs = [
        cmd[cmd.index("-c:s") + 1]
        for cmd in calls
        if "-c:s" in cmd and "-metadata:s:a:1" in cmd
    ]
    assert subtitle_codecs == ["copy"]


def test_step_mix_output_subs_mode_convert_uses_srt_for_mkv(monkeypatch, tmp_path):
    """convert mode should go straight to SRT for mkv output."""
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="mov_text\n", stderr="")
        if "-metadata:s:a:1" in cmd and "-c:s" in cmd:
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
        subs_mode="convert",
    )

    subtitle_codecs = [
        cmd[cmd.index("-c:s") + 1]
        for cmd in calls
        if "-c:s" in cmd and "-metadata:s:a:1" in cmd
    ]
    assert subtitle_codecs == ["srt"]


def test_step_mix_output_subs_mode_auto_falls_back_copy_convert_drop(monkeypatch, tmp_path):
    """auto mode should retain convert -> drop fallback when preflight rules out copy."""
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="mov_text\n", stderr="")
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
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout=b"",
                    stderr=b"Subtitle encoder failed\n",
                )
        if "-metadata:s:a:1" in cmd and "-c:s" not in cmd:
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
        subs_mode="auto",
    )

    subtitle_steps = []
    for cmd in calls:
        if "-metadata:s:a:1" not in cmd:
            continue
        if "-c:s" in cmd:
            subtitle_steps.append(cmd[cmd.index("-c:s") + 1])
        else:
            subtitle_steps.append("drop")
    assert subtitle_steps == ["srt", "drop"]


def test_step_mix_output_subs_mode_auto_skips_copy_when_later_stream_is_incompatible(monkeypatch, tmp_path):
    """auto mode should plan around incompatible mapped subtitle streams before mux retry."""
    video = tmp_path / "input.mkv"
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
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="subrip\nmov_text\n", stderr="")
        if "-metadata:s:a:1" in cmd and "-c:s" in cmd:
            subtitle_codec = cmd[cmd.index("-c:s") + 1]
            if subtitle_codec == "srt":
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout=b"",
                    stderr=b"Subtitle encoder failed\n",
                )
        if "-metadata:s:a:1" in cmd and "-c:s" not in cmd:
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
        subs_mode="auto",
    )

    subtitle_steps = []
    for cmd in calls:
        if "-metadata:s:a:1" not in cmd:
            continue
        if "-c:s" in cmd:
            subtitle_steps.append(cmd[cmd.index("-c:s") + 1])
        else:
            subtitle_steps.append("drop")
    assert subtitle_steps == ["srt", "drop"]


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
    monkeypatch.setattr(rusa.rusa_mux, "_check_ffmpeg_codec", fake_check)

    with pytest.raises(SystemExit) as exc:
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

    assert exc.value.code == rusa.EXIT_CODEC_ERROR
    captured = capsys.readouterr()
    assert "--aac" in captured.err or "--mp3" in captured.err or "--ac3" in captured.err


def test_main_invalid_srt_returns_stable_exit_code(monkeypatch, tmp_path):
    """Invalid or empty subtitle files should fail with subtitle-specific exit code in CLI flow."""
    video = tmp_path / "movie.mkv"
    srt = tmp_path / "broken.srt"
    video.write_bytes(b"video")
    srt.write_text("this is not an srt file", encoding="utf-8")

    monkeypatch.setattr(rusa, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(
        rusa.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="ru-RU-SvetlanaNeural\n", stderr=""),
    )
    monkeypatch.setattr(sys, "argv", ["rusa", "-s", str(srt), str(video)])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == rusa.EXIT_SUBTITLE_ERROR


def test_subtitle_container_mismatch_message_is_actionable(monkeypatch, tmp_path, capsys):
    """Subtitle/container mismatch errors should tell the user what to do next."""
    video = tmp_path / "input.mp4"
    voiceover = tmp_path / "voiceover.wav"
    output = tmp_path / "output.mkv"
    video.write_bytes(b"video")
    voiceover.write_bytes(b"wav")

    def fake_run(cmd, **kwargs):
        if "-filter_complex" in cmd:
            (tmp_path / "mixed.wav").write_bytes(b"mixed")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd[:3] == ["ffmpeg", "-hide_banner", "-encoders"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="libopus\naac\n", stderr="")
        if cmd[:2] == ["ffprobe", "-v"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="mov_text\n", stderr="")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
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
            subs_mode="copy",
        )

    assert exc.value.code == rusa.EXIT_SUBTITLE_ERROR
    captured = capsys.readouterr()
    assert "--subs-mode convert" in captured.err
    assert "--subs-mode drop" in captured.err
