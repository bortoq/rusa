"""Tests for persistent WAV cache."""

import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def _write_fake_mp3(path: str, payload: bytes = b"ID3" + b"m" * 200) -> None:
    Path(path).write_bytes(payload)


def _write_fake_wav(path: str, duration_ms: int = 120) -> None:
    from tests.test_convert_wav import _write_test_wav

    _write_test_wav(path, duration_ms=duration_ms)


def test_step_convert_wav_populates_cache(monkeypatch, tmp_path):
    """First conversion should persist a WAV artifact in cache."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))

    mp3 = tmp_path / "line.mp3"
    _write_fake_mp3(mp3)

    calls = {"count": 0}

    def fake_run(cmd, **kwargs):
        calls["count"] += 1
        _write_fake_wav(cmd[-1])
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    result = rusa.step_convert_wav([(1, str(mp3))], "1.5", str(tmp_path / "run1"), threads=1)

    assert calls["count"] == 1
    assert len(result) == 1
    cached_files = list((cache_dir / "wav").rglob("*.wav"))
    assert cached_files, "Expected cached WAV file"


def test_step_convert_wav_reuses_cache_when_speed_matches(monkeypatch, tmp_path):
    """Second run with same source and speed should skip ffmpeg."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))

    mp3 = tmp_path / "line.mp3"
    _write_fake_mp3(mp3, payload=b"ID3cached" + b"x" * 200)
    item = (1, str(mp3))

    def fake_run(cmd, **kwargs):
        _write_fake_wav(cmd[-1], duration_ms=150)
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)
    first = rusa.step_convert_wav([item], "1.5", str(tmp_path / "run1"), threads=1)
    assert len(first) == 1

    def fail_run(cmd, **kwargs):
        raise AssertionError(f"subprocess.run should not be called when WAV cache exists: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fail_run)
    second = rusa.step_convert_wav([item], "1.5", str(tmp_path / "run2"), threads=1)

    assert len(second) == 1
    assert os.path.isfile(second[0][1])
    assert Path(second[0][1]).read_bytes() == Path(first[0][1]).read_bytes()


def test_step_convert_wav_misses_cache_when_speed_changes(monkeypatch, tmp_path):
    """Changing speed must bypass WAV cache and invoke ffmpeg again."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))

    mp3 = tmp_path / "line.mp3"
    _write_fake_mp3(mp3)
    item = (1, str(mp3))
    calls = {"count": 0}

    def fake_run(cmd, **kwargs):
        calls["count"] += 1
        _write_fake_wav(cmd[-1], duration_ms=140 + calls["count"])
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    first = rusa.step_convert_wav([item], "1.5", str(tmp_path / "run1"), threads=1)
    second = rusa.step_convert_wav([item], "2.0", str(tmp_path / "run2"), threads=1)

    assert calls["count"] == 2
    assert len(first) == 1
    assert len(second) == 1


def test_step_convert_wav_disables_cache_when_cache_dir_unavailable(monkeypatch, tmp_path):
    """Read-only or unavailable cache roots must not break conversion."""
    mp3 = tmp_path / "line.mp3"
    _write_fake_mp3(mp3)

    calls = {"count": 0}
    original_makedirs = rusa.os.makedirs

    def fake_makedirs(path, exist_ok=False):
        if str(path).endswith("/rusa") or str(path).endswith("/rusa/wav") or str(path).endswith("\\rusa") or str(path).endswith("\\rusa\\wav"):
            raise OSError("read-only")
        return original_makedirs(path, exist_ok=exist_ok)

    def fake_run(cmd, **kwargs):
        calls["count"] += 1
        _write_fake_wav(cmd[-1], duration_ms=130)
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.delenv("RUSA_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(rusa.os, "makedirs", fake_makedirs)
    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    result = rusa.step_convert_wav([(1, str(mp3))], "1.5", str(tmp_path / "run1"), threads=1)

    assert calls["count"] == 1
    assert len(result) == 1
