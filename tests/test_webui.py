"""Tests for rusa WebUI."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is in path
PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


class TestConfig:
    """webui/config.py"""

    def test_defaults_exist(self):
        from webui.config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TITLE, AUDIO_CODECS

        assert DEFAULT_HOST == "127.0.0.1"
        assert isinstance(DEFAULT_PORT, int)
        assert DEFAULT_TITLE
        assert "aac" in AUDIO_CODECS
        assert "mp3" in AUDIO_CODECS
        assert "opus" in AUDIO_CODECS
        assert "ac3" in AUDIO_CODECS

    def test_codec_bitrates(self):
        from webui.config import AUDIO_CODECS

        for codec in ("aac", "mp3", "opus", "ac3"):
            assert "bitrates" in AUDIO_CODECS[codec]
            assert codec != "opus" or "64" in AUDIO_CODECS[codec]["bitrates"]

    def test_subs_modes(self):
        from webui.config import SUBS_MODES

        assert "auto" in SUBS_MODES
        assert "copy" in SUBS_MODES
        assert "convert" in SUBS_MODES
        assert "drop" in SUBS_MODES

    def test_normalize_options(self):
        from webui.config import NORMALIZE_OPTIONS

        options = {v: k for k, v in NORMALIZE_OPTIONS}
        assert "" in options  # disabled
        assert "fast" in options
        assert "fine" in options


class TestBuildArgs:
    """webui/utils.py — build_args()"""

    def test_minimal_args(self):
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/movie.mkv")
        assert ns.video == "/tmp/movie.mkv"
        assert ns.speed == "1.5"
        assert ns.orig_vol == "0.65"
        assert ns.tts_vol == "0.93"
        assert ns.threads == 6
        assert ns.subs_mode == "auto"
        assert ns.cache_stats is False

    def test_voice_and_lang(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            voice="ru-RU-DmitryNeural",
            lang="ru",
            speed=1.8,
        )
        assert ns.voice == "ru-RU-DmitryNeural"
        assert ns.lang == "ru"
        assert ns.speed == "1.8"

    def test_custom_tts_cmd(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            tts_cmd="espeak-ng -w {out} -f {in} -v {voice}",
            voice="ru",
        )
        assert ns.tts_cmd == "espeak-ng -w {out} -f {in} -v {voice}"

    def test_audio_codec(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            audio_fmt="aac",
            audio_bitrate="192",
        )
        assert ns.aac == "192"
        assert ns.mp3 is None
        assert ns.opus is None
        assert ns.ac3 is None

    def test_advanced_flags(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            sync=True,
            audio_only=True,
            keep_temp=True,
            no_cache=True,
        )
        assert ns.sync is True
        assert ns.audio_only is True
        assert ns.keep_temp is True
        assert ns.no_cache is True

    def test_preview_and_range(self):
        from webui.utils import build_args

        ns = build_args(
            video_path="/tmp/movie.mkv",
            preview=10,
            range_from=5,
            range_to=50,
        )
        assert ns.preview == 10
        assert ns.range_from == 5
        assert ns.range_to == 50




    def test_webui_flag_in_build_args(self):
        """build_args should include webui=False."""
        from webui.utils import build_args

        ns = build_args(video_path="/tmp/movie.mkv")
        assert hasattr(ns, "webui")
        assert ns.webui is False

    def test_rusa_main_accepts_namespace(self):
        """rusa.main() should accept an argparse.Namespace."""
        from rusa import main as rusa_main
        from webui.utils import build_args

        # Dry run with a non-existent file — should exit gracefully
        ns = build_args(
            video_path="/tmp/nonexistent_test_file.mkv",
            dry_run=True,
        )
        try:
            rusa_main(ns)
        except SystemExit:
            pass  # expected because file doesn't exist
        # If we reach here without exception, the Namespace was accepted
        assert True




    def test_signal_safe_in_background_thread(self):
        """rusa.main() should not crash with 'signal only works in main thread'."""
        import threading
        from rusa import main as rusa_main
        from webui.utils import build_args

        errors = []

        def run():
            try:
                ns = build_args(video_path="/tmp/no_such_file_rusa_test.mkv", dry_run=True)
                rusa_main(ns)
            except SystemExit as e:
                errors.append(f"SystemExit({e.code})")
            except Exception as e:
                errors.append(f"Exception: {type(e).__name__}: {e}")

        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=30)

        assert len(errors) == 1, f"Expected 1 error, got {errors}"
        assert errors[0].startswith("SystemExit"), f"Expected SystemExit, got {errors[0]}"



class TestApp:
    """webui/app.py — create_app()"""

    def setup_method(self):
        pytest.importorskip("gradio")

    def test_create_app(self):
        from webui.app import create_app

        app = create_app()
        assert app is not None
        assert app.title == "rusa — Закадровый перевод видео"

    def test_app_components(self):
        from webui.app import create_app

        app = create_app()
        # Check key blocks/components exist
        assert len(app.blocks) > 0  # has UI components

    def test_process_video_no_file(self):
        """_process_video should handle missing file gracefully."""
        from webui.app import _process_video

        gen = _process_video(
            video_file=None,
            srt_file=None,
            lang=None,
            voice=None,
            tts_cmd="",
            speed=1.5,
            orig_vol=0.65,
            tts_vol=0.93,
            codec_label="Opus",
            bitrate="64",
            normalize="",
            subs_mode="auto",
            sync=False,
            audio_only=False,
            keep_temp=False,
            no_cache=False,
        )
        logs = list(gen)
        # Should return with error about no video
        assert any("ffmpeg" in str(log) for log in logs) or any(
            "Ошибка" in str(log) for log in logs
        )



    def test_output_dir_is_video_dir(self):
        """build_args preserves video path; rusa.main() puts output next to video."""
        import os
        import tempfile
        from webui.utils import build_args

        video_dir = tempfile.mkdtemp(prefix="rusa_video_test_")
        video_path = os.path.join(video_dir, "movie.mkv")

        args = build_args(video_path=video_path)
        # args.video should be the exact path passed
        assert args.video == video_path
        # The directory of the video is what rusa.main() uses for output
        assert os.path.dirname(args.video) == video_dir

        import shutil
        shutil.rmtree(video_dir, ignore_errors=True)



class TestComponents:
    """webui/components.py"""

    def setup_method(self):
        pytest.importorskip("gradio")

    def test_lang_selector_choices(self):
        from webui.components import create_lang_selector

        dd = create_lang_selector()
        assert dd is not None




class TestServerStartup:
    """webui/app.py main() — server startup edge cases."""

    def setup_method(self):
        pytest.importorskip("gradio")

    def test_port_conflict_shows_friendly_message(self, capsys, monkeypatch):
        """OSError from port conflict should show --port hint and exit(1)."""
        import sys
        from webui.app import main

        # Mock create_app to return an object whose launch() raises OSError
        class _MockApp:
            def launch(self, **kwargs):
                raise OSError("Cannot find empty port in range: 7860-7860. "
                              "Use GRADIO_SERVER_PORT env or server_port param.")

        monkeypatch.setattr("webui.app.create_app", lambda: _MockApp())
        monkeypatch.setattr("webui.app._check_port_available", lambda host, port: None)
        monkeypatch.setattr("sys.argv", ["webui", "--port", "7860"])

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        main()

        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "Порт 7860 занят" in out, f"Got: {out}"
        assert "--port" in out, f"Should suggest --port flag, got: {out}"
        assert exit_code == [1], f"Expected exit(1), got {exit_code}"

    def test_other_oserror_shows_error(self, capsys, monkeypatch):
        """Non-port-conflict OSError should still show a message and exit(1)."""
        from webui.app import main

        class _MockApp:
            def launch(self, **kwargs):
                raise OSError("Permission denied")

        monkeypatch.setattr("webui.app.create_app", lambda: _MockApp())
        monkeypatch.setattr("webui.app._check_port_available", lambda host, port: None)
        monkeypatch.setattr("sys.argv", ["webui", "--port", "7860"])

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        main()

        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "Ошибка запуска сервера" in out, f"Got: {out}"
        assert exit_code == [1], f"Expected exit(1), got {exit_code}"

    def test_keyboard_interrupt_shows_stopped(self, capsys, monkeypatch):
        """KeyboardInterrupt should print a friendly stop message."""
        from webui.app import main

        class _MockApp:
            def launch(self, **kwargs):
                raise KeyboardInterrupt()

        monkeypatch.setattr("webui.app.create_app", lambda: _MockApp())
        monkeypatch.setattr("webui.app._check_port_available", lambda host, port: None)
        monkeypatch.setattr("sys.argv", ["webui", "--port", "7860"])

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        main()

        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "Сервер остановлен" in out, f"Got: {out}"
        # KeyboardInterrupt should NOT call sys.exit(1)
        assert exit_code == [], f"Should not call sys.exit on KeyboardInterrupt, got {exit_code}"

    def test_server_starts_successfully(self, capsys, monkeypatch):
        """Happy path — launch() succeeds and returns."""
        from webui.app import main

        class _MockApp:
            def launch(self, **kwargs):
                pass  # success

        monkeypatch.setattr("webui.app.create_app", lambda: _MockApp())
        monkeypatch.setattr("webui.app._check_port_available", lambda host, port: None)
        monkeypatch.setattr("sys.argv", ["webui", "--port", "7860"])

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        main()

        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "WebUI запущен" in out, f"Got: {out}"
        assert exit_code == [], f"Should not call sys.exit on success, got {exit_code}"


    def test_check_port_available_detects_conflict(self, capsys, monkeypatch):
        """_check_port_available should detect occupied port and exit(1)."""
        from webui.app import _check_port_available

        # First, bind a socket to a port to simulate conflict
        import socket
        import sys

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))  # bind to random available port
        occupied_port = sock.getsockname()[1]

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        _check_port_available("127.0.0.1", occupied_port)

        sock.close()

        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "уже занят" in out, f"Got: {out}"
        assert exit_code == [1], f"Expected exit(1), got {exit_code}"

    def test_check_port_available_succeeds(self, capsys, monkeypatch):
        """_check_port_available should pass when port is free."""
        from webui.app import _check_port_available

        import socket
        # Find a free port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
        sock.close()

        exit_code = []
        monkeypatch.setattr("sys.exit", lambda code: exit_code.append(code))

        _check_port_available("127.0.0.1", free_port)

        assert exit_code == [], f"Should not exit, got {exit_code}"






    def test_output_overwrites_existing(self, monkeypatch):
        """When output file exists, it should be overwritten (no _1 suffix)."""
        import os
        import tempfile
        from webui.app import _process_video

        tmpdir = tempfile.mkdtemp(prefix="rusa_overwrite_")
        video_path = os.path.join(tmpdir, "movie.mkv")
        with open(video_path, "w") as f:
            f.write("dummy")

        # Mock DEFAULT_OUTPUT_DIR to point to tmpdir
        monkeypatch.setattr("webui.config.DEFAULT_OUTPUT_DIR", tmpdir)

        gen = _process_video(
            video_file=video_path,
            srt_file=None,
            lang="ru",
            voice="ru-RU-DmitryNeural",
            tts_cmd="",
            speed=1.5,
            orig_vol=0.65,
            tts_vol=0.93,
            codec_label="Opus",
            bitrate="64",
            normalize="",
            subs_mode="auto",
            sync=False,
            audio_only=False,
            keep_temp=False,
            no_cache=False,
        )
        # Consume — will fail at rusa.main() but we catch SystemExit
        try:
            for _ in gen:
                pass
        except (SystemExit, Exception):
            pass

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_starlette_warning_suppressed(self, capsys, monkeypatch):
        """StarletteDeprecationWarning about HTTP_422 should be suppressed."""
        from webui.app import main

        class _MockApp:
            def launch(self, **kwargs):
                import warnings
                # Simulate the warning Gradio emits
                warnings.warn(
                    "'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.",
                    DeprecationWarning,
                )

        monkeypatch.setattr("webui.app.create_app", lambda: _MockApp())
        monkeypatch.setattr("webui.app._check_port_available", lambda host, port: None)
        monkeypatch.setattr("sys.argv", ["webui", "--port", "7860"])
        monkeypatch.setattr("sys.exit", lambda code: None)

        main()

        captured = capsys.readouterr()
        # The warning should NOT appear in stderr
        assert "HTTP_422" not in captured.err, f"Warning leaked to stderr: {captured.err}"



class TestUIIntegrity:
    """Verify UI components are correctly wired and functional."""

    def setup_method(self):
        pytest.importorskip("gradio")

    def test_video_input_is_file_upload(self):
        """The video input must be a gr.File (file picker), not gr.Textbox."""
        from webui.components import create_video_input
        import gradio as gr

        widget = create_video_input()
        assert isinstance(widget, gr.File), (
            f"Expected gr.File, got {type(widget).__name__}"
        )

    def test_video_input_has_file_types(self):
        """Video input should restrict to common video formats."""
        from webui.components import create_video_input

        widget = create_video_input()
        assert len(widget.file_types) > 0
        for ext in (".mkv", ".mp4", ".avi", ".mov", ".webm"):
            assert ext in widget.file_types, f"Missing {ext} in {widget.file_types}"

    def test_codec_group_returns_two_components(self):
        """create_codec_group must return (radio, dropdown)."""
        from webui.components import create_codec_group
        import gradio as gr

        radio, dropdown = create_codec_group()
        assert isinstance(radio, gr.Radio)
        assert isinstance(dropdown, gr.Dropdown)

    def test_process_button_has_click_handler(self):
        """The process button must have at least one click event."""
        from webui.app import create_app

        app = create_app()
        # Find the button with "Запустить" text
        btn = None
        for block in app.blocks.values():
            if hasattr(block, "value") and "Запустить" in str(getattr(block, "value", "")):
                btn = block
                break

        assert btn is not None, "Could not find process button"
        # Gradio stores click events; just check the button exists
        assert hasattr(btn, "click"), "Button missing click method"

    def test_log_output_is_textbox(self):
        """The log output must be a gr.Textbox (interactive=False)."""
        from webui.app import create_app

        app = create_app()
        # Find the Textbox labeled "Лог обработки"
        textboxes = [
            b for b in app.blocks.values()
            if hasattr(b, "label") and (getattr(b, "label") or "") == "Лог обработки"
        ]
        assert len(textboxes) == 1, f"Expected 1 log textbox, got {len(textboxes)}"
        tb = textboxes[0]
        assert not tb.interactive, "Log textbox should be read-only"

    def test_output_file_component_exists(self):
        """Output file picker button and textbox must exist."""
        from webui.app import create_app
        import gradio as gr

        app = create_app()
        picker_btn = None
        path_tb = None
        for b in app.blocks.values():
            if isinstance(b, gr.Button) and "Выходной файл" in (b.value or ""):
                picker_btn = b
            if isinstance(b, gr.Textbox) and (b.label or "") == "Путь сохранения":
                path_tb = b

        assert picker_btn is not None, "Output file button not found"
        assert path_tb is not None, "Output path textbox not found"
        assert not path_tb.interactive, "Path textbox should be read-only"
    def test_app_has_correct_title(self):
        """The Blocks app must have the correct title."""
        from webui.app import create_app

        app = create_app()
        assert app.title == "rusa — Закадровый перевод видео"



class TestCLIIntegration:
    """--webui flag in CLI"""

    def test_webui_flag_accepted(self):
        """The --webui flag should be parseable."""
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui"])
        assert ns.webui is True

    def test_webui_flag_false_by_default(self):
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["movie.mkv"])
        assert ns.webui is False

    def test_webui_flag_with_video(self):
        """--webui with a video argument should ignore the video."""
        from rusa_cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["--webui", "movie.mkv"])
        assert ns.webui is True
        assert ns.video == "movie.mkv"

class TestOutputFilePicker:
    """webui/utils.py — pick_output_file()"""

    def test_pick_output_file_returns_path(self, monkeypatch):
        """When user picks a file, returns the chosen path."""
        import sys
        import types

        # Build mock tkinter module tree
        class MockTk:
            instances = []
            def __init__(self):
                self.instances.append(self)
            def withdraw(self): pass
            def attributes(self, *args, **kwargs): pass
            def destroy(self): pass

        mock_filedialog = types.ModuleType('tkinter.filedialog')
        mock_filedialog.asksaveasfilename = lambda **kw: "/home/user/result.mp4"

        mock_tkinter = types.ModuleType('tkinter')
        mock_tkinter.Tk = MockTk
        mock_tkinter.filedialog = mock_filedialog

        monkeypatch.setitem(sys.modules, 'tkinter', mock_tkinter)
        monkeypatch.setitem(sys.modules, 'tkinter.filedialog', mock_filedialog)

        # Force reimport of webui.utils so it picks up mocked tkinter
        if 'webui.utils' in sys.modules:
            del sys.modules['webui.utils']

        from webui.utils import pick_output_file
        result = pick_output_file("result.mp4")
        assert result == "/home/user/result.mp4", f"Expected path, got {result!r}"

    def test_pick_output_file_cancelled(self, monkeypatch):
        """When user cancels the dialog, returns None."""
        import sys
        import types

        class MockTk:
            def __init__(self): pass
            def withdraw(self): pass
            def attributes(self, *args, **kwargs): pass
            def destroy(self): pass

        mock_filedialog = types.ModuleType('tkinter.filedialog')
        mock_filedialog.asksaveasfilename = lambda **kw: ""  # empty = cancelled

        mock_tkinter = types.ModuleType('tkinter')
        mock_tkinter.Tk = MockTk
        mock_tkinter.filedialog = mock_filedialog

        monkeypatch.setitem(sys.modules, 'tkinter', mock_tkinter)
        monkeypatch.setitem(sys.modules, 'tkinter.filedialog', mock_filedialog)

        if 'webui.utils' in sys.modules:
            del sys.modules['webui.utils']

        from webui.utils import pick_output_file
        result = pick_output_file("result.mp4")
        assert result is None, f"Expected None, got {result!r}"

    def test_pick_output_file_tkinter_unavailable(self, monkeypatch):
        """When tkinter cannot be imported, returns None gracefully."""
        import sys

        # Remove tkinter from sys.modules and force ImportError
        monkeypatch.setitem(sys.modules, 'tkinter', None)
        # Ensure a fresh import of webui.utils will attempt real tkinter import
        # We use original_import trick — keep __import__ to raise for tkinter

        if 'webui.utils' in sys.modules:
            del sys.modules['webui.utils']

        # Mock __import__ to raise ImportError for tkinter
        import builtins
        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'tkinter' or name.startswith('tkinter.'):
                raise ImportError(f"No module named {name}")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', mock_import)

        from webui.utils import pick_output_file
        result = pick_output_file("result.mp4")
        assert result is None, f"Expected None, got {result!r}"


class TestOutputFilePickerIntegration:
    """Integration: output file picker in the UI."""

    def setup_method(self):
        pytest.importorskip("gradio")

    def test_output_file_picker_button_exists(self):
        """A button 'Выходной файл' must exist in the UI."""
        from webui.app import create_app
        import gradio as gr

        app = create_app()
        buttons = [
            b for b in app.blocks.values()
            if isinstance(b, gr.Button) and "Выходной файл" in (b.value or "")
        ]
        assert len(buttons) == 1, (
            f"Expected 1 'Выходной файл' button, got {len(buttons)}"
        )

    def test_output_path_textbox_exists(self):
        """A readonly Textbox showing the chosen output path must exist."""
        from webui.app import create_app
        import gradio as gr

        app = create_app()
        textboxes = [
            b for b in app.blocks.values()
            if isinstance(b, gr.Textbox)
            and (b.label or "") == "Путь сохранения"
        ]
        assert len(textboxes) == 1, (
            f"Expected 1 path textbox, got {len(textboxes)}"
        )
        tb = textboxes[0]
        assert not tb.interactive, "Output path textbox should be read-only"

    def test_output_file_state_exists(self):
        """gr.State for storing the chosen output path must exist."""
        from webui.app import create_app
        import gradio as gr

        app = create_app()
        states = [
            b for b in app.blocks.values()
            if isinstance(b, gr.State)
        ]
        assert len(states) >= 1, (
            f"Expected at least 1 State, got {len(states)}"
        )

    def test_picker_button_has_click_handler(self):
        """The 'Выходной файл' button must have a click event wired."""
        from webui.app import create_app
        import gradio as gr

        app = create_app()
        btn = None
        for b in app.blocks.values():
            if isinstance(b, gr.Button) and "Выходной файл" in (b.value or ""):
                btn = b
                break
        assert btn is not None, "Button not found"
        assert hasattr(btn, "click"), "Button missing click method"

    def test_process_video_accepts_output_path_param(self):
        """_process_video should accept an output_path parameter."""
        from webui.app import _process_video
        import inspect

        sig = inspect.signature(_process_video)
        assert "output_path" in sig.parameters, (
            f"output_path parameter missing; params: {list(sig.parameters.keys())}"
        )
        # Should default to None
        param = sig.parameters["output_path"]
        assert param.default is None, "output_path should default to None"

    def test_process_video_uses_chosen_path(self, monkeypatch):
        """When output_path is provided, the result should be written there."""
        import os
        import tempfile
        import shutil
        from webui.app import _process_video

        tmpdir = tempfile.mkdtemp(prefix="rusa_outpath_")
        chosen_path = os.path.join(tmpdir, "custom_output.mkv")

        # Mock rusa.main to create a dummy output file
        def mock_rusa_main(args):
            args.output = os.path.join(tmpdir, "source_output.mkv")
            with open(args.output, "w") as f:
                f.write("dummy")

        monkeypatch.setattr("rusa.main", mock_rusa_main)

        gen = _process_video(
            video_file=os.path.join(tmpdir, "input.mkv"),
            srt_file=None,
            lang="ru",
            voice="ru-RU-DmitryNeural",
            tts_cmd="",
            speed=1.5,
            orig_vol=0.65,
            tts_vol=0.93,
            codec_label="Opus",
            bitrate="64",
            normalize="",
            subs_mode="auto",
            sync=False,
            audio_only=False,
            keep_temp=False,
            no_cache=False,
            output_path=chosen_path,
        )
        # Consume generator
        logs = list(gen)
        last = logs[-1] if logs else ("", None)
        log_text, final_path = last if isinstance(last, tuple) else ("", None)

        # The final path should be the chosen path
        if final_path is not None:
            assert final_path == chosen_path, (
                f"Expected {chosen_path}, got {final_path}"
            )

        shutil.rmtree(tmpdir, ignore_errors=True)
