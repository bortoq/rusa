#!/usr/bin/env python3
"""Native tkinter GUI for rusa — Закадровый перевод видео."""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from webui.config import (
    AUDIO_CODECS,
    NORMALIZE_OPTIONS,
    SPEED_MAX,
    SPEED_MIN,
    SPEED_STEP,
    SUBS_MODES,
    VOLUME_MAX,
    VOLUME_MIN,
    VOLUME_STEP,
)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Processing — delegated to gui_processing module (tkinter-free)
# ---------------------------------------------------------------------------
from gui_processing import run_processing as _run_processing  # noqa: F401


class RusaGUI:
    """Main application window."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("rusa — Закадровый перевод видео")
        self.root.minsize(680, 520)

        # ── State variables ──────────────────────────────────────────────
        self.video_path: str = ""
        self.srt_path: str = ""
        self.output_path: str = ""

        # ── Build UI ─────────────────────────────────────────────────────
        self._build_widgets()
        self._center_window()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        """Create all UI widgets."""
        f_main = ttk.Frame(self.root, padding=10)
        f_main.pack(fill=tk.BOTH, expand=True)

        # ── File selection ───────────────────────────────────────────────
        row = 0
        self._file_row(f_main, row, "Видеофайл:",
                        self._browse_video, self._clear_video)
        row += 1
        self._file_row(f_main, row, "Субтитры .srt:",
                        self._browse_srt, self._clear_srt, optional=True)
        row += 1
        self._output_row(f_main, row)

        # ── Notebook (tabs) ──────────────────────────────────────────────
        row += 1
        nb = ttk.Notebook(f_main)
        nb.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # Tab 1 — Основные
        tab_main = ttk.Frame(nb, padding=8)
        nb.add(tab_main, text="Основные")
        self._build_main_tab(tab_main)

        # Tab 2 — Аудио
        tab_audio = ttk.Frame(nb, padding=8)
        nb.add(tab_audio, text="Аудио")
        self._build_audio_tab(tab_audio)

        # Tab 3 — Субтитры
        tab_subs = ttk.Frame(nb, padding=8)
        nb.add(tab_subs, text="Субтитры")
        self._build_subs_tab(tab_subs)

        # ── Process button ───────────────────────────────────────────────
        row += 1
        btn_frame = ttk.Frame(f_main)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        self.process_btn = ttk.Button(
            btn_frame, text="🚀 Запустить обработку",
            command=self._on_process,
        )
        self.process_btn.pack(fill=tk.X)

        # ── Log ──────────────────────────────────────────────────────────
        row += 1
        ttk.Label(f_main, text="Лог обработки:").pack(anchor=tk.W, pady=(8, 0))
        self.log_text = tk.Text(f_main, height=10, width=80,
                                 state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Scrollbar for log
        scroll = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------
    # File rows
    # ------------------------------------------------------------------
    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        browse_cmd: Any,
        clear_cmd: Any,
        optional: bool = False,
    ) -> ttk.Label:
        """Helper: label + non-editable entry + Browse + Clear."""
        f = ttk.Frame(parent)
        f.pack(fill=tk.X, pady=2)
        ttk.Label(f, text=label, width=14).pack(side=tk.LEFT)
        lbl = ttk.Label(f, text="(не выбран)", foreground="gray",
                         anchor=tk.W, width=50)
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(f, text="📁 Обзор", command=browse_cmd, width=8).pack(side=tk.RIGHT)
        ttk.Button(f, text="✕", command=clear_cmd, width=3).pack(side=tk.RIGHT, padx=(0, 4))
        # Store reference to label for updates
        setattr(self, f"_lbl_{row}", lbl)
        if optional:
            setattr(self, f"_lbl_{row}_optional", True)
        return lbl

    def _output_row(self, parent: ttk.Frame, row: int) -> None:
        """Row with 'Сохранить как…' button showing chosen path."""
        f = ttk.Frame(parent)
        f.pack(fill=tk.X, pady=2)
        ttk.Label(f, text="Сохранить как:", width=14).pack(side=tk.LEFT)
        self.output_lbl = ttk.Label(f, text="(путь по умолчанию)",
                                     foreground="gray", anchor=tk.W, width=50)
        self.output_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(f, text="📁 Сохранить", command=self._browse_output, width=10).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Tab contents
    # ------------------------------------------------------------------
    def _build_main_tab(self, parent: ttk.Frame) -> None:
        """Основные настройки."""
        # Row 0: Язык + Голос
        f0 = ttk.Frame(parent)
        f0.pack(fill=tk.X, pady=2)
        ttk.Label(f0, text="Язык:").pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="ru")
        lang_combo = ttk.Combobox(f0, textvariable=self.lang_var, state="readonly",
                                   width=20)
        lang_combo["values"] = ["ru", "en", "de", "fr", "es", "it", "pt",
                                 "zh", "ja", "ko", "ar", "tr", "pl", "nl"]
        lang_combo.pack(side=tk.LEFT, padx=4)

        ttk.Label(f0, text="Голос:").pack(side=tk.LEFT, padx=(16, 0))
        self.voice_var = tk.StringVar(value="")
        voice_entry = ttk.Entry(f0, textvariable=self.voice_var, width=24)
        voice_entry.pack(side=tk.LEFT, padx=4)

        # Row 1: TTS command
        f1 = ttk.Frame(parent)
        f1.pack(fill=tk.X, pady=2)
        ttk.Label(f1, text="TTS-команда:").pack(side=tk.LEFT)
        self.tts_cmd_var = tk.StringVar(value="")
        ttk.Entry(f1, textvariable=self.tts_cmd_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

    def _build_audio_tab(self, parent: ttk.Frame) -> None:
        """Аудио настройки."""
        # Speed
        f_speed = ttk.Frame(parent)
        f_speed.pack(fill=tk.X, pady=2)
        ttk.Label(f_speed, text="Темп речи:").pack(side=tk.LEFT)
        self.speed_var = tk.DoubleVar(value=1.5)
        ttk.Scale(f_speed, from_=SPEED_MIN, to=SPEED_MAX,
                   variable=self.speed_var, orient=tk.HORIZONTAL,
                   length=200).pack(side=tk.LEFT, padx=4)
        self.speed_lbl = ttk.Label(f_speed, text="1.5", width=4)
        self.speed_lbl.pack(side=tk.LEFT)
        self.speed_var.trace("w", lambda *_: self.speed_lbl.config(
            text=f"{self.speed_var.get():.1f}"))

        # Orig volume
        f_ov = ttk.Frame(parent)
        f_ov.pack(fill=tk.X, pady=2)
        ttk.Label(f_ov, text="Громкость оригинала:").pack(side=tk.LEFT)
        self.orig_vol_var = tk.DoubleVar(value=0.65)
        ttk.Scale(f_ov, from_=VOLUME_MIN, to=VOLUME_MAX,
                   variable=self.orig_vol_var, orient=tk.HORIZONTAL,
                   length=200).pack(side=tk.LEFT, padx=4)
        self.orig_vol_lbl = ttk.Label(f_ov, text="0.65", width=4)
        self.orig_vol_lbl.pack(side=tk.LEFT)
        self.orig_vol_var.trace("w", lambda *_: self.orig_vol_lbl.config(
            text=f"{self.orig_vol_var.get():.2f}"))

        # TTS volume
        f_tv = ttk.Frame(parent)
        f_tv.pack(fill=tk.X, pady=2)
        ttk.Label(f_tv, text="Громкость TTS:").pack(side=tk.LEFT)
        self.tts_vol_var = tk.DoubleVar(value=0.93)
        ttk.Scale(f_tv, from_=VOLUME_MIN, to=VOLUME_MAX,
                   variable=self.tts_vol_var, orient=tk.HORIZONTAL,
                   length=200).pack(side=tk.LEFT, padx=4)
        self.tts_vol_lbl = ttk.Label(f_tv, text="0.93", width=4)
        self.tts_vol_lbl.pack(side=tk.LEFT)
        self.tts_vol_var.trace("w", lambda *_: self.tts_vol_lbl.config(
            text=f"{self.tts_vol_var.get():.2f}"))

        # Codec
        f_codec = ttk.Frame(parent)
        f_codec.pack(fill=tk.X, pady=2)
        ttk.Label(f_codec, text="Кодек:").pack(side=tk.LEFT)
        self.codec_var = tk.StringVar(value="Opus")
        codec_labels = [v["label"] for v in AUDIO_CODECS.values()]
        for i, lbl in enumerate(codec_labels):
            ttk.Radiobutton(f_codec, text=lbl, variable=self.codec_var,
                             value=lbl,
                             command=self._on_codec_change).pack(side=tk.LEFT, padx=2)

        # Bitrate
        f_bit = ttk.Frame(parent)
        f_bit.pack(fill=tk.X, pady=2)
        ttk.Label(f_bit, text="Битрейт:").pack(side=tk.LEFT)
        self.bitrate_var = tk.StringVar(value="64")
        self.bitrate_combo = ttk.Combobox(f_bit, textvariable=self.bitrate_var,
                                           state="readonly", width=10)
        self._update_bitrates()
        self.bitrate_combo.pack(side=tk.LEFT, padx=4)

        # Normalize
        ttk.Label(f_bit, text="Нормализация:").pack(side=tk.LEFT, padx=(16, 0))
        self.normalize_var = tk.StringVar(value="")
        norm_combo = ttk.Combobox(f_bit, textvariable=self.normalize_var,
                                   state="readonly", width=12)
        norm_combo["values"] = [lbl for lbl, _ in NORMALIZE_OPTIONS]
        norm_combo.pack(side=tk.LEFT, padx=4)

    def _build_subs_tab(self, parent: ttk.Frame) -> None:
        """Субтитры."""
        f_mode = ttk.Frame(parent)
        f_mode.pack(fill=tk.X, pady=2)
        ttk.Label(f_mode, text="Режим субтитров:").pack(side=tk.LEFT)
        self.subs_mode_var = tk.StringVar(value="auto")
        sub_combo = ttk.Combobox(f_mode, textvariable=self.subs_mode_var,
                                  state="readonly", width=12)
        sub_combo["values"] = SUBS_MODES
        sub_combo.pack(side=tk.LEFT, padx=4)

        # Checkboxes
        self.sync_var = tk.BooleanVar(value=False)
        self.audio_only_var = tk.BooleanVar(value=False)
        self.keep_temp_var = tk.BooleanVar(value=False)
        self.no_cache_var = tk.BooleanVar(value=False)

        f_cb = ttk.Frame(parent)
        f_cb.pack(fill=tk.X, pady=8)
        ttk.Checkbutton(f_cb, text="Синхронизировать (alass)",
                         variable=self.sync_var).pack(anchor=tk.W)
        ttk.Checkbutton(f_cb, text="Только аудио",
                         variable=self.audio_only_var).pack(anchor=tk.W)
        ttk.Checkbutton(f_cb, text="Не удалять временные файлы",
                         variable=self.keep_temp_var).pack(anchor=tk.W)
        ttk.Checkbutton(f_cb, text="Отключить кэш",
                         variable=self.no_cache_var).pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите видеофайл",
            filetypes=[
                ("Видео", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.flv"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self.video_path = path
            self._set_lbl(0, os.path.basename(path), "black")

    def _clear_video(self) -> None:
        self.video_path = ""
        self._set_lbl(0, "(не выбран)", "gray")

    def _browse_srt(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл субтитров .srt",
            filetypes=[
                ("Субтитры", "*.srt *.ass *.ssa *.vtt"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self.srt_path = path
            self._set_lbl(1, os.path.basename(path), "black")

    def _clear_srt(self) -> None:
        self.srt_path = ""
        self._set_lbl(1, "(не выбран)", "gray")

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Сохранить результат как…",
            initialfile="output.mp4",
            defaultextension="",
            filetypes=[
                ("Видео", "*.mp4 *.mkv *.avi *.mov *.webm"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self.output_path = path
            self.output_lbl.config(text=path, foreground="black")

    def _on_codec_change(self) -> None:
        self._update_bitrates()

    def _update_bitrates(self) -> None:
        label = self.codec_var.get()
        codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
        key = codec_map.get(label, "opus")
        info = AUDIO_CODECS[key]
        self.bitrate_combo["values"] = info["bitrates"]
        self.bitrate_var.set(info["default"])

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def _on_process(self) -> None:
        if not self.video_path:
            messagebox.showwarning("Нет видео", "Сначала выберите видеофайл.")
            return
        self._log_clear()
        self.process_btn.config(state=tk.DISABLED, text="⏳ Обработка…")

        # Build args
        from webui.utils import build_args

        codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
        audio_fmt = codec_map.get(self.codec_var.get())

        # Map normalize label → value
        norm_map = {lbl: val for lbl, val in NORMALIZE_OPTIONS}
        normalize = norm_map.get(self.normalize_var.get(), "")

        args = build_args(
            video_path=self.video_path,
            srt_path=self.srt_path or None,
            voice=self.voice_var.get() or None,
            lang=self.lang_var.get() or None,
            speed=self.speed_var.get(),
            orig_vol=self.orig_vol_var.get(),
            tts_vol=self.tts_vol_var.get(),
            audio_fmt=audio_fmt,
            audio_bitrate=self.bitrate_var.get(),
            tts_cmd=self.tts_cmd_var.get(),
            normalize=normalize,
            subs_mode=self.subs_mode_var.get(),
            sync=self.sync_var.get(),
            audio_only=self.audio_only_var.get(),
            keep_temp=self.keep_temp_var.get(),
            no_cache=self.no_cache_var.get(),
            output=self.output_path or None,
        )

        # Run in background
        self._processing = True
        t = threading.Thread(
            target=_run_processing,
            args=(args, self._log, self._on_done),
            daemon=True,
        )
        t.start()

    def _on_done(self, success: bool, path: str | None) -> None:
        self.root.after(0, self._on_done_ui, success, path)

    def _on_done_ui(self, success: bool, path: str | None) -> None:
        self.process_btn.config(state=tk.NORMAL, text="🚀 Запустить обработку")
        self._processing = False

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        """Thread-safe: schedule log append on main thread."""
        self.root.after(0, self._log_append, msg)

    def _log_append(self, msg: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _log_clear(self) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set_lbl(self, row: int, text: str, color: str = "black") -> None:
        lbl = getattr(self, f"_lbl_{row}", None)
        if lbl:
            lbl.config(text=text, foreground=color)

    def _center_window(self) -> None:
        self.root.update_idletasks()
        w = max(700, self.root.winfo_reqwidth())
        h = max(580, self.root.winfo_reqheight())
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    gui = RusaGUI()
    gui.run()


if __name__ == "__main__":
    main()
