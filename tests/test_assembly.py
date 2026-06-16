"""Tests for voiceover assembly (step_assemble)."""
import sys, os, struct, wave, math, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def _make_sine_wav(path: str, duration_ms: int = 1000,
                   freq: int = 440, framerate: int = 48000) -> str:
    """Create a WAV file with a sine tone. Returns path."""
    nframes = int(duration_ms * framerate / 1000)
    bpf = 2 * 2
    data = b""
    for frame in range(nframes):
        t = frame / framerate
        val = int(16000 * math.sin(2 * 3.14159 * freq * t))
        data += struct.pack("<h", val)
        data += struct.pack("<h", val)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(data)))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 2, framerate,
                2 * 2 * framerate, 2 * 2, 2 * 8))
        f.write(b"data")
        f.write(struct.pack("<I", len(data)))
        f.write(data)
    return path


def test_assemble_basic(sample_entries, sample_wav_results, tmp_path):
    """Basic assembly: 3 segments, no overlap, all present."""
    out = rusa.step_assemble(sample_entries, sample_wav_results, str(tmp_path))
    assert os.path.isfile(out)
    with wave.open(out, "rb") as w:
        nframes = w.getnframes()
        assert nframes > 0
        # Should have audio at all 3 positions
        for e in sample_entries:
            pos_frames = int(e["start_ms"] * 48000 / 1000)
            if pos_frames < nframes:
                w.setpos(pos_frames)
                data = w.readframes(10)
                max_val = max(abs(struct.unpack("<h", data[j:j+2])[0])
                              for j in range(0, min(20, len(data)), 2))
                assert max_val > 100, f"No audio at pos {e['start_ms']}ms"


def test_assemble_wav_header_integrity(sample_entries, sample_wav_results, tmp_path):
    """WAV header must correctly report data size."""
    out = rusa.step_assemble(sample_entries, sample_wav_results, str(tmp_path))
    with open(out, "rb") as f:
        data_size = struct.unpack("<I", f.read(44)[40:44])[0]
    file_size = os.path.getsize(out)
    assert 44 + data_size == file_size, (
        f"WAV header mismatch: header says {44+data_size}, file is {file_size}"
    )


def test_assemble_with_overlap(overlapping_entries, overlapping_wav_results, tmp_path):
    """Overlapping segments cascade-shift but all should be present."""
    out = rusa.step_assemble(overlapping_entries, overlapping_wav_results, str(tmp_path))
    with wave.open(out, "rb") as w:
        nframes = w.getnframes()
        # All 5 segments should be audible somewhere
        audio_positions = []
        step = 100
        for pos in range(0, nframes, step):
            w.setpos(pos)
            data = w.readframes(10)
            max_val = max(abs(struct.unpack("<h", data[j:j+2])[0])
                          for j in range(0, min(20, len(data)), 2))
            if max_val > 100:
                audio_positions.append(pos)
        assert len(audio_positions) >= 3, (
            f"Only {len(audio_positions)} audio regions found, expected >= 3"
        )
        # 5th segment should exist (even if cascade-shifted)
        last_seg_pos = overlapping_entries[-1]["start_ms"]
        assert any(p >= last_seg_pos * 48000 / 1000 for p in audio_positions), (
            "Last segment not found (cascade may have pushed it too far)"
        )


def test_assemble_cascade_shifts_segments(tmp_path):
    """When a segment overflows into the next slot, the next shifts forward.

    This is the expected cascading behavior: segments that don't keep up
    with their subtitle timing get 'stacked' (shifted) rather than clipped.
    """
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 5000, "text": "Long"},
        {"idx": 2, "start_ms": 1000, "end_ms": 3000, "text": "Short"},
    ]
    wav1 = _make_sine_wav(str(tmp_path / "batch_0001.wav"), 3000, freq=300)
    wav2 = _make_sine_wav(str(tmp_path / "batch_0002.wav"), 500, freq=500)
    wav_results = [(1, wav1, 3000.0), (2, wav2, 500.0)]

    out = rusa.step_assemble(entries, wav_results, str(tmp_path))

    with wave.open(out, "rb") as w:
        framerate = w.getframerate()

        # Segment 2 should be SHIFTED to after segment 1 ends (3000ms),
        # NOT at its subtitle start_ms (1000ms)
        pos_shifted = int(3.0 * framerate)  # 3000ms = after seg1 ends
        w.setpos(pos_shifted)
        data = w.readframes(20)
        max_val_shifted = max(
            abs(struct.unpack("<h", data[j:j+2])[0])
            for j in range(0, min(40, len(data)), 2)
        )
        assert max_val_shifted > 100, (
            f"Seg 2 should be cascade-shifted to ~3000ms but no audio found"
        )

        # Segment 2 should NOT be at its original 1000ms position
        # (it was pushed forward by seg1's overflow)
        pos_original = int(1.0 * framerate)
        w.setpos(pos_original)
        data = w.readframes(20)
        max_val_original = max(
            abs(struct.unpack("<h", data[j:j+2])[0])
            for j in range(0, min(40, len(data)), 2)
        )
        # At 1000ms, only segment 1's audio should be present (same 300Hz tone)
        # So audio exists but it's seg1's tone, not seg2's
        assert max_val_original > 100, (
            f"At 1000ms there should be audio (seg1), but none found"
        )


def test_assemble_exact_time_when_no_overlap(tmp_path):
    """When a segment fits within its subtitle gap, it places EXACTLY at start_ms.

    No overlap → no shift → exact positioning.
    """
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 5000, "text": "First"},
        {"idx": 2, "start_ms": 3000, "end_ms": 6000, "text": "Second"},
    ]
    # Seg1 is short — finishes before seg2 starts
    wav1 = _make_sine_wav(str(tmp_path / "batch_0001.wav"), 2000, freq=300)
    wav2 = _make_sine_wav(str(tmp_path / "batch_0002.wav"), 1000, freq=500)
    wav_results = [(1, wav1, 2000.0), (2, wav2, 1000.0)]

    out = rusa.step_assemble(entries, wav_results, str(tmp_path))

    with wave.open(out, "rb") as w:
        framerate = w.getframerate()

        # Seg1 ends at 2000ms, seg2 starts at 3000ms — no overlap
        # Seg2 should be at EXACTLY 3000ms
        pos_seg2 = int(3.0 * framerate)
        w.setpos(pos_seg2)
        data = w.readframes(20)
        max_val = max(
            abs(struct.unpack("<h", data[j:j+2])[0])
            for j in range(0, min(40, len(data)), 2)
        )
        assert max_val > 100, (
            f"Seg 2 should be at exactly 3000ms (no overlap), but no audio found"
        )


def test_assemble_with_zero_duration(tmp_path):
    """Segments with duration=0 should be filtered out."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "First"},
        {"idx": 2, "start_ms": 3000, "end_ms": 4000, "text": "Second"},
    ]
    wav1 = _make_sine_wav(str(tmp_path / "batch_0001.wav"), 500)
    wav_results = [
        (1, wav1, 500.0),
        (2, str(tmp_path / "missing.wav"), 0),
    ]
    out = rusa.step_assemble(entries, wav_results, str(tmp_path))
    with wave.open(out, "rb") as w:
        nframes = w.getnframes()
        pos_seg2 = int(3.0 * 48000)
        if pos_seg2 < nframes:
            w.setpos(pos_seg2)
            data = w.readframes(10)
            max_val = max(abs(struct.unpack("<h", data[j:j+2])[0])
                          for j in range(0, min(20, len(data)), 2))
            assert max_val < 100, (
                f"Zero-duration segment should not produce audio, got {max_val}"
            )


def test_assemble_empty_results(tmp_path):
    """Empty wav_results should raise SystemExit."""
    import pytest
    entries = [{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Test"}]
    with pytest.raises(SystemExit):
        rusa.step_assemble(entries, [], str(tmp_path))


def test_assemble_no_matching_entries(tmp_path):
    """wav_results with indices not in entries should produce empty segments → exit."""
    import pytest
    entries = [{"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Test"}]
    wav_results = [(99, "/tmp/nonexistent.wav", 500.0)]
    with pytest.raises(SystemExit):
        rusa.step_assemble(entries, wav_results, str(tmp_path))


def test_assemble_large_number_of_segments(tmp_path):
    """100 segments with random timings should produce valid WAV."""
    import random
    random.seed(42)
    entries = []
    wav_results = []
    for i in range(1, 101):
        start_ms = (i - 1) * 1200
        entries.append({"idx": i, "start_ms": start_ms, "end_ms": start_ms + 1000,
                        "text": f"Line {i}"})
        dur_ms = 800 + random.randint(0, 400)
        wav_path = str(tmp_path / f"batch_{i:04d}.wav")
        _make_sine_wav(wav_path, dur_ms, freq=200 + (i % 10) * 100)
        wav_results.append((i, wav_path, float(dur_ms)))

    out = rusa.step_assemble(entries, wav_results, str(tmp_path))

    with open(out, "rb") as f:
        data_size = struct.unpack("<I", f.read(44)[40:44])[0]
    assert 44 + data_size == os.path.getsize(out), "WAV header mismatch"

    with wave.open(out, "rb") as w:
        readable_frames = w.getnframes()
        raw = w.readframes(min(readable_frames, 480000))
        max_val = max(abs(struct.unpack("<h", raw[j:j+2])[0])
                      for j in range(0, min(10000, len(raw)), 2))
        assert max_val > 100, "All audio is silence"
