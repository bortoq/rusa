"""Tests for WAV conversion stage."""

import os
import struct
import subprocess
import threading
import time
from pathlib import Path
import wave

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa
import rusa_audio
import rusa_shared


def _write_test_wav(path: str, duration_ms: int = 120) -> None:
    """Create a tiny valid stereo WAV file."""
    framerate = rusa.WAV_FRAMERATE
    frames = int(duration_ms * framerate / 1000)
    with wave.open(path, "wb") as w:
        w.setnchannels(rusa.WAV_CHANNELS)
        w.setsampwidth(rusa.WAV_SAMPLEWIDTH)
        w.setframerate(framerate)
        raw = bytearray()
        for _ in range(frames):
            raw.extend(struct.pack("<h", 500))
            raw.extend(struct.pack("<h", 500))
        w.writeframes(bytes(raw))


def test_step_convert_wav_runs_ffmpeg_in_parallel_and_returns_sorted_results(
    monkeypatch, tmp_path
):
    """Conversion should use multiple workers but return results sorted by idx."""
    tts_results = []
    for idx in range(1, 5):
        mp3_path = tmp_path / f"batch_{idx:04d}.mp3"
        mp3_path.write_bytes(b"fake-mp3")
        tts_results.append((idx, str(mp3_path)))

    state = {"active": 0, "max_active": 0}
    lock = threading.Lock()

    def fake_run(cmd, **kwargs):
        wav_path = cmd[-1]
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            time.sleep(0.05)
            _write_test_wav(wav_path)
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        finally:
            with lock:
                state["active"] -= 1

    # Isolate cache to a temp directory so we never hit stale entries
    monkeypatch.setenv("RUSA_CACHE_DIR", str(tmp_path / "cache"))
    # Patch subprocess.run in the module where convert_one actually calls it
    monkeypatch.setattr(rusa_audio.subprocess, "run", fake_run)

    results = rusa_audio.step_convert_wav(tts_results, "1.5", str(tmp_path), threads=4)

    assert [idx for idx, _, _ in results] == [1, 2, 3, 4]
    assert all(os.path.isfile(path) for _, path, _ in results)
    assert state["max_active"] >= 2, "Expected concurrent ffmpeg conversions"
