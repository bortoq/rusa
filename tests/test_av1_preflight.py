"""AV1 stream-copy checks run before expensive TTS generation."""

import shutil
import subprocess

import pytest

import rusa_mux


def test_large_av1_source_is_judged_by_packets_not_file_size(monkeypatch, tmp_path):
    source = tmp_path / "large.mkv"
    with source.open("wb") as handle:
        handle.truncate(60 * 1024 * 1024)
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        if cmd[0] == "ffmpeg":
            (tmp_path / "av1_copy_preflight.mkv").write_bytes(b"preview")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if "stream=codec_name" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="av1\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="0\n0.5\n1\n1.5\n2\n", stderr="")

    monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
    rusa_mux.preflight_av1_copy(str(source), str(tmp_path))
    assert any(cmd[0] == "ffmpeg" and "-c:v" in cmd for cmd in seen)
    assert not (tmp_path / "av1_copy_preflight.mkv").exists()


def test_av1_preflight_rejects_missing_video_packets(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if "stream=codec_name" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="av1\n", stderr="")
        output = "0\n1\n2\n" if str(source) == cmd[-1] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")

    monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        rusa_mux.preflight_av1_copy(str(source), str(tmp_path))


@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg required")
def test_large_real_av1_input_copy(tmp_path):
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libsvtav1" not in encoders.stdout:
        pytest.skip("libsvtav1 encoder is unavailable")
    attachment = tmp_path / "padding.bin"
    attachment.write_bytes(b"x" * (51 * 1024 * 1024))
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=3",
        "-c:v", "libsvtav1", "-preset", "12", "-crf", "50", "-attach", str(attachment),
        "-metadata:s:t:0", "mimetype=application/octet-stream", str(source),
    ], check=True, capture_output=True)
    assert source.stat().st_size > 50 * 1024 * 1024
    rusa_mux.preflight_av1_copy(str(source), str(tmp_path))
