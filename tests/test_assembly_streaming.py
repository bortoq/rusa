"""Regression tests for streaming voiceover assembly."""

import builtins
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def test_assemble_uses_single_write_pass(monkeypatch, tmp_path):
    """Assembly should stream into the output file without reopening it in rb+ mode."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "First"},
        {"idx": 2, "start_ms": 4000, "end_ms": 5000, "text": "Second"},
    ]
    from tests.test_assembly import _make_sine_wav

    wav1 = _make_sine_wav(str(tmp_path / "batch_0001.wav"), 700)
    wav2 = _make_sine_wav(str(tmp_path / "batch_0002.wav"), 800)
    wav_results = [(1, wav1, 700.0), (2, wav2, 800.0)]
    out_path = str(tmp_path / "voiceover.wav")

    real_open = builtins.open
    opened_modes = []

    def tracking_open(path, mode="r", *args, **kwargs):
        if os.path.abspath(path) == os.path.abspath(out_path):
            opened_modes.append(mode)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)

    out = rusa.step_assemble(entries, wav_results, str(tmp_path))

    assert out == out_path
    assert opened_modes == ["wb"], f"expected single streaming write pass, got modes {opened_modes}"
