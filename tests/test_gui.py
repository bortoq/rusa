"""Tests for rusa_gui.py — native tkinter GUI.

All tests in this file require a display (tkinter window).
They are skipped on headless CI.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def _display_available() -> bool:
    """Return True if tkinter can create a window (display available)."""
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


_HAS_DISPLAY = _display_available()
pytestmark = pytest.mark.skipif(
    not _HAS_DISPLAY,
    reason="No display available (headless CI)",
)


class TestGUICreation:
    """The main window must create without errors."""

    def test_window_created(self):
        from rusa_gui import RusaGUI

        gui = RusaGUI()
        try:
            assert gui.root is not None
            assert gui.root.winfo_exists()
            assert "rusa" in gui.root.title().lower()
        finally:
            if gui.root.winfo_exists():
                gui.root.destroy()

    def test_window_title(self):
        from rusa_gui import RusaGUI

        gui = RusaGUI()
        try:
            assert "Закадровый перевод" in gui.root.title()
        finally:
            if gui.root.winfo_exists():
                gui.root.destroy()


class TestFileSelection:
    """File selection rows: video, srt, output."""

    @pytest.fixture
    def gui(self):
        from rusa_gui import RusaGUI

        g = RusaGUI()
        yield g
        if g.root.winfo_exists():
            g.root.destroy()

    def test_video_browse_button(self, gui):
        btns = self._find_buttons(gui, "Обзор")
        assert len(btns) >= 1

    def test_video_clear_button(self, gui):
        btns = self._find_buttons(gui, "✕")
        assert len(btns) >= 1

    def test_output_save_button(self, gui):
        btns = self._find_buttons(gui, "Сохранить")
        assert len(btns) >= 1

    def test_initial_video_path(self, gui):
        assert gui.video_path == ""
        lbl = getattr(gui, "_lbl_0", None)
        assert lbl is not None
        assert "не выбран" in lbl.cget("text").lower()

    def test_initial_srt_path(self, gui):
        assert gui.srt_path == ""
        lbl = getattr(gui, "_lbl_1", None)
        assert lbl is not None
        assert "не выбран" in lbl.cget("text").lower()

    def test_initial_output_label(self, gui):
        assert gui.output_path == ""
        assert "по умолчанию" in gui.output_lbl.cget("text").lower()

    @staticmethod
    def _find_buttons(gui, text):
        """Find all ttk.Button widgets with matching text."""
        from tkinter import ttk

        found = []
        stack = list(gui.root.winfo_children())
        while stack:
            w = stack.pop()
            if isinstance(w, (ttk.Button, tk.Button)):
                try:
                    if text in w.cget("text"):
                        found.append(w)
                except tk.TclError:
                    pass
            stack.extend(w.winfo_children())
        return found


class TestProcessingButton:
    """The 'Запустить обработку' button."""

    @pytest.fixture
    def gui(self):
        from rusa_gui import RusaGUI

        g = RusaGUI()
        yield g
        if g.root.winfo_exists():
            g.root.destroy()

    def test_button_exists(self, gui):
        assert gui.process_btn is not None
        assert "Запустить" in gui.process_btn.cget("text")

    def test_warning_without_video(self, gui, monkeypatch):
        shown = []
        monkeypatch.setattr(
            "tkinter.messagebox.showwarning",
            lambda *a, **kw: shown.append(True),
        )
        gui._on_process()
        assert len(shown) == 1


class TestLogWidget:
    """Log text widget."""

    @pytest.fixture
    def gui(self):
        from rusa_gui import RusaGUI

        g = RusaGUI()
        yield g
        if g.root.winfo_exists():
            g.root.destroy()

    def test_log_text_exists(self, gui):
        assert isinstance(gui.log_text, tk.Text)

    def test_log_append(self, gui):
        gui._log_append("test message")
        content = gui.log_text.get("1.0", "end")
        assert "test message" in content

    def test_log_clear(self, gui):
        gui._log_append("something")
        gui._log_clear()
        content = gui.log_text.get("1.0", "end").strip()
        assert content == ""


class TestDefaultValues:
    """Default values of controls."""

    @pytest.fixture
    def gui(self):
        from rusa_gui import RusaGUI

        g = RusaGUI()
        yield g
        if g.root.winfo_exists():
            g.root.destroy()

    def test_lang_default(self, gui):
        assert gui.lang_var.get() == "ru"

    def test_voice_default(self, gui):
        assert gui.voice_var.get() == ""

    def test_tts_cmd_default(self, gui):
        assert gui.tts_cmd_var.get() == ""

    def test_speed_default(self, gui):
        assert abs(gui.speed_var.get() - 1.5) < 0.01

    def test_orig_vol_default(self, gui):
        assert abs(gui.orig_vol_var.get() - 0.65) < 0.01

    def test_tts_vol_default(self, gui):
        assert abs(gui.tts_vol_var.get() - 0.93) < 0.01

    def test_subs_mode_default(self, gui):
        assert gui.subs_mode_var.get() == "auto"

    def test_sync_default(self, gui):
        assert gui.sync_var.get() is False

    def test_audio_only_default(self, gui):
        assert gui.audio_only_var.get() is False

    def test_keep_temp_default(self, gui):
        assert gui.keep_temp_var.get() is False

    def test_no_cache_default(self, gui):
        assert gui.no_cache_var.get() is False

    def test_codec_change_updates_bitrate(self, gui):
        gui.codec_var.set("Opus")
        gui._on_codec_change()
        assert gui.bitrate_var.get() == "64"
        gui.codec_var.set("AAC")
        gui._on_codec_change()
        assert gui.bitrate_var.get() == "96"
