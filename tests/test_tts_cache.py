"""Tests for persistent TTS cache."""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def _write_fake_mp3(path: str, payload: bytes = b"ID3" + b"x" * 200) -> None:
    Path(path).write_bytes(payload)


def test_step_generate_tts_populates_cache(monkeypatch, tmp_path):
    """Generated TTS should be copied into persistent cache."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))

    calls = {"count": 0}

    def fake_run(cmd, **kwargs):
        calls["count"] += 1
        _write_fake_mp3(cmd[-1])
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    result = rusa.step_generate_tts(
        [{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "cache me"}],
        "ru-RU-SvetlanaNeural",
        1,
        str(tmp_path / "run1"),
    )

    assert calls["count"] == 1
    assert len(result) == 1
    cached_files = list(cache_dir.rglob("*.mp3"))
    assert cached_files, "Expected at least one cached mp3 file"


def test_step_generate_tts_reuses_cache_without_edge_tts(monkeypatch, tmp_path):
    """Second run with same voice/text should reuse cache and skip subprocess."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))
    entry = {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "reuse me"}

    def fake_run(cmd, **kwargs):
        _write_fake_mp3(cmd[-1], payload=b"ID3cached" + b"y" * 200)
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)
    first = rusa.step_generate_tts([entry], "ru-RU-SvetlanaNeural", 1, str(tmp_path / "run1"))
    assert len(first) == 1

    def fail_run(cmd, **kwargs):
        raise AssertionError(f"subprocess.run should not be called when cache exists: {cmd}")

    monkeypatch.setattr(rusa.subprocess, "run", fail_run)
    second = rusa.step_generate_tts([entry], "ru-RU-SvetlanaNeural", 1, str(tmp_path / "run2"))

    assert len(second) == 1
    assert os.path.isfile(second[0][1])
    assert Path(second[0][1]).read_bytes() == Path(first[0][1]).read_bytes()


def test_step_generate_tts_does_not_silently_truncate_multipart_audio(monkeypatch, tmp_path):
    """Long text must fail loudly when multipart concat fails.

    Regression: do not fall back to the first generated chunk, because that
    silently drops the rest of the subtitle text.
    """
    monkeypatch.setenv("RUSA_CACHE_DIR", str(tmp_path / "cache"))
    long_text = ("Sentence. " * 400).strip()  # > MAX_TTS_CHARS → multipart
    entry = {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": long_text}

    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "ffmpeg":
            return rusa.subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"concat failed")
        _write_fake_mp3(cmd[-1], payload=b"ID3part" + b"z" * 200)
        return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        rusa.step_generate_tts([entry], "ru-RU-SvetlanaNeural", 1, str(tmp_path / "run"))
