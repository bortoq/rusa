"""Utility functions for rusa WebUI."""
from __future__ import annotations

import os
import sys
import tempfile
from argparse import Namespace
from typing import Any


def build_args(
    video_path: str,
    srt_path: str | None = None,
    voice: str | None = None,
    lang: str | None = None,
    speed: float = 1.5,
    orig_vol: float = 0.65,
    tts_vol: float = 0.93,
    audio_fmt: str | None = None,
    audio_bitrate: str | None = None,
    threads: int = 6,
    tts_cmd: str = "",
    engine: str = "",
    normalize: str = "",
    subs_mode: str = "auto",
    merge_sentences: bool = True,
    keep_temp: bool = False,
    sync: bool = False,
    audio_only: bool = False,
    output: str | None = None,
    dry_run: bool = False,
    no_cache: bool = False,
    range_from: int | None = None,
    range_to: int | None = None,
    preview: int | None = None,
) -> Namespace:
    """Convert WebUI form values to argparse Namespace compatible with main()."""
    args_dict: dict[str, Any] = {
        "video": video_path,
        "srt": srt_path or None,
        "voice": voice,
        "lang": lang,
        "speed": str(speed),
        "orig_vol": str(orig_vol),
        "tts_vol": str(tts_vol),
        "threads": threads,
        "tts_cmd": tts_cmd,
        "engine": engine,
        "normalize": normalize or None,
        "subs_mode": subs_mode,
        "merge_sentences": merge_sentences,
        "keep_temp": keep_temp,
        "sync": sync,
        "audio_only": audio_only,
        "output": output or None,
        "dry_run": dry_run,
        "no_cache": no_cache,
        "range_from": range_from,
        "range_to": range_to,
        "preview": preview,
        # Flags not exposed via WebUI — keep Namespace compatible with main()
        "webui": False,
        "cache_stats": False,
        "cache_clear": False,
        "preset": None,
        "overwrite": False,
    }

    # Set audio codec flags (mutually exclusive in CLI)
    for codec in ("aac", "mp3", "opus", "ac3"):
        args_dict[codec] = None
    if audio_fmt and audio_bitrate:
        args_dict[audio_fmt] = audio_bitrate

    return Namespace(**args_dict)


def pick_output_file(default_name: str = "output.mp4") -> str | None:
    """Open native Save-As dialog via tkinter.

    Returns the chosen absolute path, or *None* if the user cancels
    or tkinter is not available (headless environment).
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    path: str = filedialog.asksaveasfilename(
        initialfile=default_name,
        defaultextension="",
        filetypes=[
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()

    if not path:
        return None
    return path
