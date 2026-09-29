"""Offline regression checks for audible voiceover and source-track preservation."""

import json
import shutil
import subprocess

import pytest

import rusa
import rusa_mux


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg required")
def test_mux_keeps_both_source_audio_tracks_and_audible_voiceover(tmp_path):
    source = tmp_path / "source.mkv"
    voiceover = tmp_path / "voiceover.wav"
    output = tmp_path / "output.mkv"

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=3",
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
        "-c:v", "mpeg4", "-c:a", "aac",
        "-metadata:s:a:0", "language=eng",
        "-metadata:s:a:1", "language=jpn",
        "-disposition:a:0", "default", "-disposition:a:1", "none",
        str(source),
    ], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "sine=frequency=880:duration=3", "-ac", "2", "-ar", "48000",
        str(voiceover),
    ], check=True, capture_output=True)

    rusa.step_mix_output(str(source), str(voiceover), "0", "1", str(output),
                         str(tmp_path), "opus", "64", None, False, subs_mode="drop")

    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
        "stream=codec_name:stream_tags=language,title:stream_disposition=default",
        "-of", "json", str(output),
    ], check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    assert len(streams) == 3
    assert [stream["codec_name"] for stream in streams] == ["aac", "aac", "opus"]
    assert [stream["tags"]["language"] for stream in streams] == ["eng", "jpn", "rus"]
    assert [stream["disposition"]["default"] for stream in streams] == [0, 0, 1]
    assert rusa_mux._has_interleaved_voiceover(str(output), 2)

    # The first original audio ends after one second. Speech must remain audible
    # on the new track two seconds into the film.
    decoded = subprocess.run([
        "ffmpeg", "-v", "error", "-ss", "2", "-i", str(output),
        "-map", "0:a:2", "-t", "0.5", "-f", "s16le", "-acodec", "pcm_s16le", "-",
    ], check=True, capture_output=True)
    assert any(decoded.stdout), "Voiceover track is silent after original audio ends"


def test_interleaving_check_rejects_voiceover_at_end_of_large_movie(monkeypatch, tmp_path):
    output = tmp_path / "movie.mkv"
    with output.open("wb") as handle:
        handle.truncate(2_000_000_000)

    def fake_probe(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="6000\n", stderr="")

    monkeypatch.setattr(rusa_mux.subprocess, "run", fake_probe)
    positions = {"v:0": 28_000_000, "a:2": 1_950_000_000}
    monkeypatch.setattr(rusa_mux, "_packet_position", lambda _path, stream, _time: positions[stream])
    assert not rusa_mux._has_interleaved_voiceover(str(output), 2)

    positions["a:2"] = 29_000_000
    assert rusa_mux._has_interleaved_voiceover(str(output), 2)
