"""Tests for cache management CLI flags."""

import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa

from tests.test_tts_cache import _write_fake_mp3
from tests.test_wav_cache import _write_fake_wav


def test_cache_stats_reports_tts_and_wav_entries(monkeypatch, tmp_path, capsys):
    """--cache-stats should report both cache buckets and totals."""
    cache_dir = tmp_path / "cache"
    tts_dir = cache_dir / "tts"
    wav_dir = cache_dir / "wav"
    tts_dir.mkdir(parents=True)
    wav_dir.mkdir(parents=True)
    (tts_dir / "a.mp3").write_bytes(b"a" * 120)
    (tts_dir / "b.mp3").write_bytes(b"b" * 130)
    (wav_dir / "a.wav").write_bytes(b"c" * 220)

    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(sys, "argv", ["rusa", "--cache-stats"])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "TTS" in out
    assert "WAV" in out
    assert "2 files" in out
    assert "1 files" in out
    assert "Total" in out


def test_cache_clear_removes_cached_files(monkeypatch, tmp_path, capsys):
    """--cache-clear should remove both TTS and WAV cache payloads."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "tts").mkdir(parents=True)
    (cache_dir / "wav").mkdir(parents=True)
    (cache_dir / "tts" / "a.mp3").write_bytes(b"a" * 120)
    (cache_dir / "wav" / "a.wav").write_bytes(b"b" * 220)

    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(sys, "argv", ["rusa", "--cache-clear"])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == 0
    assert not any(cache_dir.rglob("*.*"))
    out = capsys.readouterr().out
    assert "cleared" in out.lower()


def test_cache_stats_ignores_no_cache_and_does_not_create_missing_dirs(monkeypatch, tmp_path, capsys):
    """Management stats should inspect real cache even if --no-cache is also passed."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "tts").mkdir(parents=True)
    (cache_dir / "tts" / "a.mp3").write_bytes(b"a" * 120)

    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(sys, "argv", ["rusa", "--no-cache", "--cache-stats"])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "TTS: 1 files" in out
    assert not (cache_dir / "wav").exists()


def test_cache_clear_ignores_no_cache_and_removes_existing_files(monkeypatch, tmp_path):
    """Management clear should still remove cache even if --no-cache is also passed."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "tts").mkdir(parents=True)
    (cache_dir / "tts" / "a.mp3").write_bytes(b"a" * 120)

    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(sys, "argv", ["rusa", "--no-cache", "--cache-clear"])

    with pytest.raises(SystemExit) as exc:
        rusa.main()

    assert exc.value.code == 0
    assert not any((cache_dir / "tts").iterdir())


def test_no_cache_disables_reads_and_writes(monkeypatch, tmp_path):
    """Disabled cache should neither reuse existing entries nor overwrite them."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("RUSA_CACHE_DIR", str(cache_dir))

    voice = "ru-RU-SvetlanaNeural"
    entry = {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "disable cache"}
    source_mp3 = tmp_path / "source.mp3"
    _write_fake_mp3(source_mp3, payload=b"ID3source" + b"x" * 200)

    tts_cache_path = Path(rusa._tts_cache_path(voice, entry["text"]))
    tts_cache_path.parent.mkdir(parents=True, exist_ok=True)
    tts_cache_path.write_bytes(b"ID3cached-old" + b"c" * 200)

    wav_cache_path = Path(rusa._wav_cache_path(str(source_mp3), "1.5"))
    wav_cache_path.parent.mkdir(parents=True, exist_ok=True)
    _write_fake_wav(str(wav_cache_path), duration_ms=180)
    wav_cache_before = wav_cache_path.read_bytes()

    calls = {"tts": 0, "wav": 0}

    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "edge-tts":
            calls["tts"] += 1
            _write_fake_mp3(cmd[-1], payload=b"ID3fresh" + b"n" * 200)
            return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd and cmd[0] == "ffmpeg":
            calls["wav"] += 1
            _write_fake_wav(cmd[-1], duration_ms=140)
            return rusa.subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(rusa, "_CACHE_DISABLED", True)
    monkeypatch.setattr(rusa.subprocess, "run", fake_run)

    tts_results = rusa.step_generate_tts([entry], voice, 1, str(tmp_path / "tts_run"))
    wav_results = rusa.step_convert_wav(tts_results, "1.5", str(tmp_path / "wav_run"), threads=1)

    assert calls == {"tts": 1, "wav": 1}
    assert len(tts_results) == 1
    assert len(wav_results) == 1
    assert tts_cache_path.read_bytes() == b"ID3cached-old" + b"c" * 200
    assert wav_cache_path.read_bytes() == wav_cache_before
