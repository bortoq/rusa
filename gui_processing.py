"""Processing pipeline for native GUI — no tkinter dependency.

This module is separate from rusa_gui.py so it can be tested without tkinter.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Callable

# ---------------------------------------------------------------------------
# ANSI stripping
# ---------------------------------------------------------------------------
_RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _RE_ANSI.sub("", text)


def flush_captured(
    stdout: io.StringIO,
    stderr: io.StringIO,
    log_callback: Callable[[str], None],
) -> None:
    """Read and clear StringIO buffers, calling *log_callback* per line."""
    for text in (stdout.getvalue(), stderr.getvalue()):
        if text.strip():
            cleaned = strip_ansi(text)
            for line in cleaned.strip().split("\n"):
                if line:
                    log_callback(line)
    stdout.truncate(0)
    stdout.seek(0)
    stderr.truncate(0)
    stderr.seek(0)


def run_processing(
    args: Any,
    log_callback: Callable[[str], None],
    done_callback: Callable[[bool, str | None], None],
) -> None:
    """Run rusa.main(args) in a background thread.

    *log_callback(text)* is called for each line of output.
    *done_callback(success, output_path)* is called when finished.
    """
    from rusa_shared import python_executable, python_module_cmd, which

    log_callback(f"▶ Начинаю обработку: {os.path.basename(args.video)}")

    # Check ffmpeg/ffprobe
    try:
        which("ffmpeg")
        which("ffprobe")
        python_executable()
    except SystemExit:
        log_callback("❌ ffmpeg/ffprobe/python не найдены. Установите зависимости.")
        done_callback(False, None)
        return

    log_callback("✓ ffmpeg, ffprobe, python — найдены")

    # Check edge-tts
    if not args.tts_cmd:
        try:
            rc = subprocess.run(
                python_module_cmd("edge_tts", "--help"),
                check=False, capture_output=True, timeout=30,
            )
            if rc.returncode != 0:
                log_callback("❌ edge-tts не установлен. pip install edge-tts")
                done_callback(False, None)
                return
        except (OSError, subprocess.TimeoutExpired):
            log_callback("❌ edge-tts не доступен")
            done_callback(False, None)
            return
        log_callback("✓ edge-tts — доступен")

    # Run rusa.main
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Save user-chosen output path (if any) before rusa.main() overwrites args.output
    user_output = getattr(args, "output", None)

    try:
        from rusa import main as rusa_main
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            rusa_main(args)
    except SystemExit as exc:
        # rusa.main() calls sys.exit(0) on success; src is in args.output.
        src = getattr(args, "output", None)
        if exc.code == 0 and src and os.path.isfile(src):
            flush_captured(stdout_capture, stderr_capture, log_callback)
            import shutil
            if user_output:
                os.makedirs(os.path.dirname(user_output) or ".", exist_ok=True)
                shutil.copy2(src, user_output)
                final = user_output
            else:
                final = src
            if os.path.isfile(final):
                log_callback("")
                log_callback("✅ Обработка завершена")
                log_callback(f"📁 Выходной файл: {final}")
                done_callback(True, final)
                return
        flush_captured(stdout_capture, stderr_capture, log_callback)
        log_callback(f"❌ Ошибка обработки (код {exc.code})")
        done_callback(False, None)
        return
    except Exception as exc:
        flush_captured(stdout_capture, stderr_capture, log_callback)
        log_callback(f"❌ Непредвиденная ошибка: {exc}")
        done_callback(False, None)
        return

    flush_captured(stdout_capture, stderr_capture, log_callback)

    # Determine final output path
    src = args.output  # set by rusa.main()
    if src and os.path.isfile(src):
        import shutil
        if user_output:
            # User chose a specific path — copy result there
            os.makedirs(os.path.dirname(user_output) or ".", exist_ok=True)
            shutil.copy2(src, user_output)
            final = user_output
        else:
            final = src
        if os.path.isfile(final):
            log_callback("")
            log_callback("✅ Обработка завершена")
            log_callback(f"📁 Выходной файл: {final}")
            done_callback(True, final)
            return

    log_callback("⚠ Выходной файл не найден")
    done_callback(False, None)
