import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa
import rusa_audio
import rusa_mux
import rusa_shared
import rusa_cli
import rusa_tts


# ── shell ────────────────────────────────────────────────────────────

class TestShell:
    def test_shell_success(self, monkeypatch):
        """shell should return CompletedProcess on success."""
        monkeypatch.setattr(rusa_shared.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0))
        result = rusa_shared.shell(["true"])
        assert result.returncode == 0

    def test_shell_failure_dies(self, monkeypatch):
        """shell should call die() on non-zero exit."""
        def fake_run(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd)
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        with pytest.raises(SystemExit):
            rusa_shared.shell(["false"])

    def test_shell_file_not_found_dies(self, monkeypatch):
        """shell should call die() when command not found."""
        def fake_run(cmd, **kw):
            raise FileNotFoundError()
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        with pytest.raises(SystemExit):
            rusa_shared.shell(["nonexistent_cmd_xyz"])

    def test_shell_passes_kwargs(self, monkeypatch):
        """shell should forward kwargs to subprocess.run."""
        seen = {}
        def fake_run(cmd, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0)
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        rusa_shared.shell(["echo", "hi"], capture_output=True, timeout=5)
        assert seen.get("capture_output") is True
        assert seen.get("timeout") == 5


# ── which ────────────────────────────────────────────────────────────

class TestWhich:
    def test_which_found(self, monkeypatch):
        """which should return path when command exists."""
        monkeypatch.setattr(rusa_shared.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
        path = rusa_shared.which("ffmpeg")
        assert path == "/usr/bin/ffmpeg"

    def test_which_not_found(self, monkeypatch):
        """which should die when command not in PATH."""
        monkeypatch.setattr(rusa_shared.shutil, "which", lambda cmd: None)
        with pytest.raises(SystemExit):
            rusa_shared.which("nonexistent_cmd_xyz")


# ── die ──────────────────────────────────────────────────────────────

class TestDie:
    def test_die_exits_with_default_code(self, monkeypatch):
        """die should sys.exit with EXIT_RUNTIME_ERROR (1) by default."""
        exited = []
        monkeypatch.setattr(rusa_shared.sys, "exit", exited.append)
        rusa_shared.die("test error")
        assert exited == [rusa_shared.EXIT_RUNTIME_ERROR]

    def test_die_exits_with_custom_code(self, monkeypatch):
        """die should sys.exit with the provided code."""
        exited = []
        monkeypatch.setattr(rusa_shared.sys, "exit", exited.append)
        rusa_shared.die("test error", code=42)
        assert exited == [42]

    def test_die_prints_to_stderr(self, monkeypatch, capsys):
        """die should print the message to stderr."""
        exited = []
        monkeypatch.setattr(rusa_shared.sys, "exit", exited.append)
        rusa_shared.die("custom message")
        captured = capsys.readouterr()
        assert "custom message" in captured.err


# ── _check_ffmpeg_codec ──────────────────────────────────────────────

class TestCheckFfmpegCodec:
    def test_codec_found(self, monkeypatch):
        """_check_ffmpeg_codec should return True when codec in ffmpeg output."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, stdout="libopus\naac\nlibmp3lame\n", stderr="")
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        rusa_mux._check_ffmpeg_codec.cache_clear()
        assert rusa_mux._check_ffmpeg_codec("libopus") is True

    def test_codec_not_found(self, monkeypatch):
        """_check_ffmpeg_codec should return False when codec not in ffmpeg output."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, stdout="libopus\naac\n", stderr="")
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        rusa_mux._check_ffmpeg_codec.cache_clear()
        assert rusa_mux._check_ffmpeg_codec("nonexistent_codec") is False

    def test_codec_ffmpeg_fails(self, monkeypatch):
        """_check_ffmpeg_codec should return False when ffmpeg -encoders fails."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        rusa_mux._check_ffmpeg_codec.cache_clear()
        assert rusa_mux._check_ffmpeg_codec("libopus") is False

    def test_codec_cache_hits(self, monkeypatch):
        """_check_ffmpeg_codec should cache the result (lru_cache maxsize=1)."""
        call_count = [0]
        def fake_run(cmd, **kw):
            call_count[0] += 1
            return subprocess.CompletedProcess(cmd, 0, stdout="libopus\naac\n", stderr="")
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        rusa_mux._check_ffmpeg_codec.cache_clear()

        rusa_mux._check_ffmpeg_codec("libopus")
        assert call_count[0] == 1

        rusa_mux._check_ffmpeg_codec("libopus")
        assert call_count[0] == 1, "lru_cache should prevent second subprocess call"

        rusa_mux._check_ffmpeg_codec("aac")
        assert call_count[0] == 2


# ── _run_loudnorm ────────────────────────────────────────────────────

def _fake_completed(cmd, rc, stdout=b"", stderr=b"", text=False):
    """Build CompletedProcess; decode if text=True like real subprocess.run."""
    if text:
        stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
    return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)


class TestRunLoudnorm:
    def test_loudnorm_success(self, monkeypatch, tmp_path):
        """_run_loudnorm should return True when both ffmpeg passes succeed."""
        calls = []
        in_wav = str(tmp_path / "in.wav")
        out_wav = str(tmp_path / "out.wav")
        with open(in_wav, "w") as f:
            f.write("dummy")

        def fake_run(cmd, **kw):
            calls.append(cmd)
            text_mode = kw.get("text", False)
            if "-f" in cmd and "null" in cmd:
                return _fake_completed(
                    cmd, 0,
                    stderr=b'{"input_i":"-16.0","input_lra":"11.0","input_tp":"-1.5","input_thresh":"-21.0","target_offset":"0.0"}',
                    text=text_mode,
                )
            with open(out_wav, "w") as f:
                f.write("x" * 200)
            return _fake_completed(cmd, 0, text=text_mode)

        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        result = rusa_mux._run_loudnorm(in_wav, out_wav)
        assert result is True
        assert len(calls) == 2

    def test_loudnorm_first_pass_fails(self, monkeypatch, tmp_path):
        """_run_loudnorm should return False when first ffmpeg pass fails."""
        def fake_run(cmd, **kw):
            text_mode = kw.get("text", False)
            return _fake_completed(cmd, 1, text=text_mode)
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        result = rusa_mux._run_loudnorm("/tmp/in.wav", "/tmp/out.wav")
        assert result is False

    def test_loudnorm_no_json_in_stderr(self, monkeypatch, tmp_path):
        """_run_loudnorm should return False when no JSON found in stderr."""
        def fake_run(cmd, **kw):
            text_mode = kw.get("text", False)
            return _fake_completed(cmd, 0, stderr=b"no json here", text=text_mode)
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        result = rusa_mux._run_loudnorm("/tmp/in.wav", "/tmp/out.wav")
        assert result is False


# ── _run_dynaudnorm ──────────────────────────────────────────────────

class TestRunDynaudnorm:
    def test_dynaudnorm_success(self, monkeypatch, tmp_path):
        """_run_dynaudnorm should return True when ffmpeg succeeds."""
        in_wav = str(tmp_path / "in.wav")
        out_wav = str(tmp_path / "out.wav")
        with open(in_wav, "w") as f:
            f.write("dummy")

        def fake_run(cmd, **kw):
            # Write a file larger than 100 bytes (code checks os.path.getsize > 100)
            with open(out_wav, "w") as f:
                f.write("x" * 200)
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        result = rusa_mux._run_dynaudnorm(in_wav, out_wav)
        assert result is True

    def test_dynaudnorm_fails(self, monkeypatch, tmp_path):
        """_run_dynaudnorm should return False when ffmpeg fails."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"error")
        monkeypatch.setattr(rusa_mux.subprocess, "run", fake_run)
        result = rusa_mux._run_dynaudnorm("/tmp/in.wav", "/tmp/out.wav")
        assert result is False


# ── list_voices ──────────────────────────────────────────────────────

class TestListVoices:
    def test_list_voices_success(self, monkeypatch, capsys):
        """list_voices should print voice list and exit cleanly."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout="ru-RU-SvetlanaNeural\nen-US-AriaNeural\n",
                stderr="",
            )
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        monkeypatch.setattr(rusa_cli.sys, "exit", lambda code: None)
        # Only test edge-tts (other backends are not relevant here)


        rusa.list_voices()
        captured = capsys.readouterr()
        assert "edge:" in captured.out
        assert "ru-RU-SvetlanaNeural" in captured.out

    def test_list_voices_edge_tts_fails(self, monkeypatch, capsys):
        """list_voices should show note when edge-tts fails."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        monkeypatch.setattr(rusa_cli.sys, "exit", lambda code: None)

        rusa.list_voices()
        captured = capsys.readouterr()
        assert "edge" in captured.out

    def test_list_voices_shows_filters_ru(self, monkeypatch, capsys):
        """list_voices should filter output for Russian voices."""
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout="Name: ru-RU-SvetlanaNeural\nName: en-US-AriaNeural\nName: ru-RU-DmitryNeural\n",
                stderr="",
            )
        monkeypatch.setattr(rusa_shared.subprocess, "run", fake_run)
        monkeypatch.setattr(rusa_cli.sys, "exit", lambda code: None)


        rusa.list_voices()
        captured = capsys.readouterr()
        ru_lines = [l for l in captured.out.split("\n") if "ru-" in l.lower()]
        assert len(ru_lines) >= 2


# ── Cache eviction ───────────────────────────────────────────────────

class TestCacheEviction:
    def test_evict_oldest_removes_oldest_files(self, tmp_path):
        """_evict_oldest should remove oldest files first when total exceeds max_size."""
        # Create 3 files: 100 + 100 + 100 = 300 bytes
        for i in range(3):
            f = tmp_path / f"file{i}.mp3"
            f.write_bytes(b"x" * 100)
            os.utime(f, (0, 100 - i * 10))  # file0(100)=oldest, file1(90), file2(80)

        # max_size=150 means we need to remove until <= 150
        removed = rusa_shared._evict_oldest(str(tmp_path), max_size=150)
        # After removing file2(100): 200 > 150, after removing file1(100): 100 <= 150
        assert removed == 2
        remaining = sorted(os.listdir(tmp_path))
        assert remaining == ["file0.mp3"]  # file0 (mtime=100) is newest, survives

    def test_evict_oldest_no_removal_when_under_limit(self, tmp_path):
        """_evict_oldest should remove nothing when total <= max_size."""
        (tmp_path / "a.mp3").write_bytes(b"x" * 50)
        (tmp_path / "b.mp3").write_bytes(b"x" * 50)

        removed = rusa_shared._evict_oldest(str(tmp_path), max_size=200)
        assert removed == 0
        assert len(os.listdir(tmp_path)) == 2

    def test_evict_oldest_non_existent_dir(self, tmp_path):
        """_evict_oldest should return 0 for non-existent directories."""
        removed = rusa_shared._evict_oldest(str(tmp_path / "nonexistent"), max_size=100)
        assert removed == 0

    def test_cache_max_size_reads_env(self, monkeypatch):
        """_cache_max_size should read RUSA_CACHE_MAX_SIZE from env, with 1 MiB floor."""
        monkeypatch.setenv("RUSA_CACHE_MAX_SIZE", "2097152")  # 2 MiB
        assert rusa_shared._cache_max_size() == 2097152

    def test_cache_max_size_minimum_floor(self, monkeypatch):
        """_cache_max_size should enforce a 1 MiB minimum."""
        monkeypatch.setenv("RUSA_CACHE_MAX_SIZE", "100")  # below 1 MiB
        assert rusa_shared._cache_max_size() == 1024 * 1024

    def test_cache_max_size_default(self, monkeypatch):
        """_cache_max_size should return DEFAULT_CACHE_MAX_SIZE when env is unset."""
        monkeypatch.delenv("RUSA_CACHE_MAX_SIZE", raising=False)
        assert rusa_shared._cache_max_size() == rusa_shared.DEFAULT_CACHE_MAX_SIZE

    def test_cache_max_size_fallback_on_invalid_env(self, monkeypatch):
        """_cache_max_size should return default when env is not a valid integer."""
        monkeypatch.setenv("RUSA_CACHE_MAX_SIZE", "not_a_number")
        assert rusa_shared._cache_max_size() == rusa_shared.DEFAULT_CACHE_MAX_SIZE


