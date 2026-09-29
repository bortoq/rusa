"""Long media should fail before TTS when the temp disk cannot hold PCM files."""

import subprocess
from collections import namedtuple

import pytest

import rusa


def test_long_video_rejected_when_temp_disk_is_too_small(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        rusa.subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="7200\n", stderr=""),
    )
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(rusa.shutil, "disk_usage", lambda path: usage(10**12, 0, 100_000_000))
    entries = [{"end_ms": 1000}]
    with pytest.raises(SystemExit) as exc:
        rusa._preflight_temp_space("movie.mkv", str(tmp_path), entries, "fine")
    assert exc.value.code == rusa.EXIT_RUNTIME_ERROR
    assert "TMPDIR" in capsys.readouterr().err


def test_short_video_passes_temp_disk_preflight(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rusa.subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="3\n", stderr=""),
    )
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(rusa.shutil, "disk_usage", lambda path: usage(10**12, 0, 1_000_000_000))
    rusa._preflight_temp_space("movie.mkv", str(tmp_path), [{"end_ms": 2000}], None)
