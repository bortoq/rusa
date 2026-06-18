"""Tests for gui_processing.py — processing logic (no tkinter dependency)."""

from __future__ import annotations

import io
import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


class TestFlushCaptured:
    """gui_processing.flush_captured"""

    def test_flush_stdout(self):
        from gui_processing import flush_captured

        stdout = io.StringIO("line1\nline2\n")
        stderr = io.StringIO("")
        logs = []
        flush_captured(stdout, stderr, logs.append)
        assert "line1" in logs
        assert "line2" in logs
        assert stdout.getvalue() == "", "stdout should be cleared"

    def test_flush_stderr(self):
        from gui_processing import flush_captured

        stdout = io.StringIO("")
        stderr = io.StringIO("error\n")
        logs = []
        flush_captured(stdout, stderr, logs.append)
        assert "error" in logs
        assert stderr.getvalue() == "", "stderr should be cleared"

    def test_flush_ansi_escapes(self):
        from gui_processing import flush_captured

        stdout = io.StringIO("\x1b[32mgreen\x1b[0m\n")
        stderr = io.StringIO("")
        logs = []
        flush_captured(stdout, stderr, logs.append)
        assert "green" in logs
        assert "\x1b" not in "".join(logs), "ANSI escapes should be stripped"

    def test_flush_empty_buffers(self):
        from gui_processing import flush_captured

        stdout = io.StringIO("")
        stderr = io.StringIO("")
        logs = []
        # Should not crash
        flush_captured(stdout, stderr, logs.append)
        assert logs == []

    def test_strip_ansi_standalone(self):
        from gui_processing import strip_ansi

        assert strip_ansi("\x1b[1mBold\x1b[0m") == "Bold"
        assert strip_ansi("\x1b[31mRed\x1b[0m") == "Red"
        assert strip_ansi("no escapes") == "no escapes"
        assert strip_ansi("") == ""


class TestRunProcessing:
    """gui_processing.run_processing — core pipeline."""

    def test_missing_ffmpeg_shows_error(self, monkeypatch):
        """When ffmpeg/ffprobe not found, log shows error and done(False)."""
        from gui_processing import run_processing

        def mock_which(name):
            raise SystemExit(1)

        monkeypatch.setattr("rusa_shared.which", mock_which)

        logs = []
        done_calls = []
        args = types.SimpleNamespace(video="/tmp/test.mkv", tts_cmd="")

        run_processing(args, logs.append, lambda *a: done_calls.append(a))

        assert any("ffmpeg" in m.lower() for m in logs), f"Got: {logs}"
        assert done_calls == [(False, None)], f"Got: {done_calls}"

    def test_rusa_main_called_with_args(self, monkeypatch):
        """rusa.main() should be called with the given args."""
        from gui_processing import run_processing

        called_with = []

        def mock_which(name):
            pass

        def mock_rusa_main(args_obj):
            called_with.append(args_obj)
            args_obj.output = "/tmp/test_output.mkv"
            with open(args_obj.output, "w") as f:
                f.write("done")
            raise SystemExit(0)

        monkeypatch.setattr("rusa_shared.which", mock_which)
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=0))
        monkeypatch.setattr("rusa.main", mock_rusa_main)

        args = types.SimpleNamespace(
            video="/tmp/test.mkv", tts_cmd="", output="/tmp/final.mkv"
        )
        logs = []
        done_calls = []

        run_processing(args, logs.append, lambda *a: done_calls.append(a))

        assert len(called_with) == 1
        assert called_with[0].video == "/tmp/test.mkv"

    def test_success_callback_with_path(self, monkeypatch):
        """On success, done_callback(True, path) is called."""
        from gui_processing import run_processing

        def mock_which(name):
            pass

        def mock_rusa_main(args_obj):
            args_obj.output = "/tmp/test_done.mkv"
            with open(args_obj.output, "w") as f:
                f.write("ok")
            raise SystemExit(0)

        monkeypatch.setattr("rusa_shared.which", mock_which)
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=0))
        monkeypatch.setattr("rusa.main", mock_rusa_main)

        args = types.SimpleNamespace(
            video="/tmp/test.mkv", tts_cmd="", output=None
        )
        logs = []
        done_calls = []

        run_processing(args, logs.append, lambda *a: done_calls.append(a))

        assert any("завершен" in m.lower() for m in logs), f"Got: {logs}"
        assert len(done_calls) == 1
        success, path = done_calls[0]
        assert success is True
        assert path is not None and os.path.isfile(path)

    def test_rusa_main_exception_handled(self, monkeypatch):
        """If rusa.main raises, done_callback(False, None) is called."""
        from gui_processing import run_processing

        def mock_which(name):
            pass

        def mock_rusa_main(args_obj):
            raise RuntimeError("something broke")

        monkeypatch.setattr("rusa_shared.which", mock_which)
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=0))
        monkeypatch.setattr("rusa.main", mock_rusa_main)

        args = types.SimpleNamespace(
            video="/tmp/test.mkv", tts_cmd="", output=None
        )
        logs = []
        done_calls = []

        run_processing(args, logs.append, lambda *a: done_calls.append(a))

        assert any("ошибк" in m.lower() for m in logs), f"Got: {logs}"
        assert done_calls == [(False, None)]

    def test_edge_tts_not_available(self, monkeypatch):
        """edge-tts check fails → error in log, done(False)."""
        from gui_processing import run_processing

        def mock_which(name):
            pass

        monkeypatch.setattr("rusa_shared.which", mock_which)
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=1))

        args = types.SimpleNamespace(
            video="/tmp/test.mkv", tts_cmd="", output=None
        )
        logs = []
        done_calls = []

        run_processing(args, logs.append, lambda *a: done_calls.append(a))

        assert any("edge-tts" in m.lower() for m in logs), f"Got: {logs}"
        assert done_calls == [(False, None)]
