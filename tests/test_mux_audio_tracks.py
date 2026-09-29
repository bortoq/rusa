"""Offline regression checks for audible voiceover and source-track preservation."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import rusa
import rusa_mux


def test_mux_command_maps_every_source_stream_type():
    cmd = rusa_mux._build_video_mux_cmd(
        "source.mkv", "mixed.wav", "out.mkv", "aac", "128k", "rus", "copy", n_source_audio=2,
    )
    maps = [cmd[index + 1] for index, arg in enumerate(cmd[:-1]) if arg == "-map"]
    assert maps == ["0:v", "0:a", "1:a:0", "0:s?", "0:t?", "0:d?"]
    assert cmd[cmd.index("-c:d") + 1] == "copy"
    assert cmd[cmd.index("-c:t") + 1] == "copy"


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


def test_interleaving_check_rejects_late_packet_gap(monkeypatch, tmp_path):
    output = tmp_path / "movie.mkv"
    with output.open("wb") as handle:
        handle.truncate(1_000_000_000)
    monkeypatch.setattr(rusa_mux.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="6000\n"))

    def packet_pos(_path, stream, seconds):
        if seconds > 5000 and stream == "a:2":
            return 900_000_000
        return 10_000_000

    monkeypatch.setattr(rusa_mux, "_packet_position", packet_pos)
    assert not rusa_mux._has_interleaved_voiceover(str(output), 2)


def test_packet_position_uses_packet_near_requested_time_after_keyframe_seek(monkeypatch):
    def fake_probe(cmd, **kwargs):
        assert cmd[cmd.index("-read_intervals") + 1] == "6414.000%+40"
        return subprocess.CompletedProcess(
            cmd, 0,
            stdout="6413.994,100\n6423.994,200\n6424.014,300\n6430.000,400\n",
            stderr="",
        )

    monkeypatch.setattr(rusa_mux.subprocess, "run", fake_probe)
    assert rusa_mux._packet_position("movie.mkv", "a:1", 6424) == 200


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg required")
def test_mux_preserves_extra_video_subtitle_and_attachment(tmp_path):
    source = tmp_path / "source.mkv"
    voiceover = tmp_path / "voice.wav"
    output = tmp_path / "output.mkv"
    subtitles = tmp_path / "original.srt"
    attachment = tmp_path / "font.txt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    attachment.write_text("font placeholder", encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=3",
        "-f", "lavfi", "-i", "color=c=red:s=32x32:r=10:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-i", str(subtitles), "-map", "0:v", "-map", "1:v", "-map", "2:a", "-map", "3:s",
        "-c:v", "mpeg4", "-c:a", "aac", "-c:s", "srt",
        "-attach", str(attachment), "-metadata:s:t:0", "mimetype=text/plain", str(source),
    ], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
        "-ac", "2", "-ar", "48000", str(voiceover),
    ], check=True, capture_output=True)

    rusa.step_mix_output(str(source), str(voiceover), "0.5", "1", str(output), str(tmp_path),
                         "aac", "128", None, False)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(output),
    ], check=True, capture_output=True, text=True)
    types = [s["codec_type"] for s in json.loads(probe.stdout)["streams"]]
    assert types.count("video") == 2
    assert types.count("audio") == 2
    assert types.count("subtitle") == 1
    assert types.count("attachment") == 1


@pytest.mark.slow
@pytest.mark.skipif(not Path("/usr/bin/time").exists() or not shutil.which("ffmpeg"), reason="GNU time and ffmpeg required")
def test_long_video_with_sparse_subtitles_uses_bounded_mux_memory(tmp_path):
    source = tmp_path / "source.mkv"
    voiceover = tmp_path / "voice.wav"
    output = tmp_path / "output.mkv"
    subtitles = tmp_path / "sparse.srt"
    subtitles.write_text("1\n00:01:50,000 --> 00:01:51,000\nLate caption\n", encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=2:d=120",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=120", "-i", str(subtitles),
        "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "mpeg4", "-g", "60", "-c:a", "aac", "-c:s", "srt",
        str(source),
    ], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=120",
        "-ac", "2", "-ar", "48000", str(voiceover),
    ], check=True, capture_output=True)
    memory_file = tmp_path / "maxrss-kib"
    script = (
        "from rusa_mux import step_mix_output; "
        "import sys; "
        "step_mix_output(sys.argv[1], sys.argv[2], '1', '1', sys.argv[3], sys.argv[4], 'aac', '128', None, False)"
    )
    # This test uses a separate process so GNU time measures only the mux pipeline.
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)}
    subprocess.run([
        "/usr/bin/time", "-f", "%M", "-o", str(memory_file), sys.executable, "-c", script,
        str(source), str(voiceover), str(output), str(tmp_path),
    ], check=True, capture_output=True, env=env)
    peak_kib = int(memory_file.read_text().strip())
    print(f"Mux peak RSS: {peak_kib} KiB")
    assert peak_kib < 500_000
    assert rusa_mux._has_interleaved_voiceover(str(output), 1)
