"""FastAPI REST API for rusa — headless processing server.

Replaces the old Gradio-based WebUI with a lightweight REST API.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Generator
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from webui.config import (
    AUDIO_CODECS,
    DEFAULT_HOST,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PORT,
    DEFAULT_TITLE,
)
from webui.utils import build_args

# ── Helpers ───────────────────────────────────────────────────────────

_re_ansi = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _re_ansi.sub("", text)


def _sse_event(event_type: str, message: str, **extra: Any) -> str:
    """Build a Server-Sent Event data line."""
    payload = {"type": event_type, "message": message, **extra}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _process_video(
    video_file: Optional[str],
    srt_file: Optional[str],
    lang: Optional[str],
    voice: Optional[str],
    tts_cmd: str,
    speed: float,
    orig_vol: float,
    tts_vol: float,
    codec_label: str,
    bitrate: str,
    normalize: str,
    subs_mode: str,
    sync: bool,
    audio_only: bool,
    keep_temp: bool,
    no_cache: bool,
) -> Generator[str, None, None]:
    """Run rusa processing pipeline, yielding SSE events.

    Yields ``text/event-stream`` formatted strings for the API endpoint.
    """
    # Resolve codec label → key
    codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
    audio_fmt = codec_map.get(codec_label)
    if audio_fmt is None:
        yield _sse_event(
            "error",
            f"Неизвестный кодек: {codec_label}. "
            f"Допустимые: {', '.join(codec_map)}",
        )
        return

    args = build_args(
        video_path=video_file,
        srt_path=srt_file,
        voice=voice or None,
        lang=lang or None,
        speed=speed,
        orig_vol=orig_vol,
        tts_vol=tts_vol,
        audio_fmt=audio_fmt,
        audio_bitrate=bitrate,
        tts_cmd=tts_cmd,
        normalize=normalize,
        subs_mode=subs_mode,
        sync=sync,
        audio_only=audio_only,
        keep_temp=keep_temp,
        no_cache=no_cache,
    )

    if not video_file:
        yield _sse_event("error", "Ошибка: не выбран видеофайл")
        return

    yield _sse_event("log", f"▶ Начинаю обработку: {os.path.basename(video_file)}")

    from rusa_shared import which

    try:
        which("ffmpeg")
        which("ffprobe")
        which("python3")
    except SystemExit as exc:
        yield _sse_event(
            "error",
            f"Ошибка: ffmpeg/ffprobe не найдены (exit {exc.code})",
        )
        return

    yield _sse_event("log", "✓ ffmpeg, ffprobe, python3 — найдены")

    if not args.tts_cmd:
        try:
            rc = subprocess.run(
                ["python3", "-m", "edge_tts", "--help"],
                check=False, capture_output=True, timeout=30,
            )
            if rc.returncode != 0:
                yield _sse_event(
                    "error",
                    "Ошибка: edge-tts не установлен (pip install edge-tts)",
                )
                return
        except (OSError, subprocess.TimeoutExpired):
            yield _sse_event("error", "Ошибка: edge-tts не доступен")
            return
        yield _sse_event("log", "✓ edge-tts — доступен")

    # Call rusa.main() with captured output
    stdout_capture = StringIO()
    stderr_capture = StringIO()

    def _emit_captured(src: StringIO, prefix: str = "") -> None:
        text = src.getvalue()
        if not text.strip():
            return
        cleaned = _strip_ansi(text)
        for line in cleaned.strip().split("\n"):
            if line:
                yield _sse_event("log", f"{prefix}{line}")

    try:
        from rusa import main as rusa_main

        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            rusa_main(args)
    except SystemExit as exc:
        yield from _emit_captured(stdout_capture)
        yield from _emit_captured(stderr_capture, "⚠ ")
        yield _sse_event("error", f"❌ Ошибка обработки (код {exc.code})")
        return
    except Exception as exc:
        yield from _emit_captured(stdout_capture)
        yield from _emit_captured(stderr_capture, "⚠ ")
        yield _sse_event("error", f"❌ Непредвиденная ошибка: {exc}")
        return

    yield from _emit_captured(stdout_capture)
    yield from _emit_captured(stderr_capture, "⚠ ")

    # Copy output file to user-accessible directory
    src_path = getattr(args, "output", None)
    final_path: Optional[str] = None
    if src_path and os.path.isfile(src_path):
        dest_dir = os.path.expanduser(DEFAULT_OUTPUT_DIR)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src_path))
        shutil.copy2(src_path, dest)
        final_path = dest

    if final_path and os.path.isfile(final_path):
        yield _sse_event("log", "")
        yield _sse_event("log", "✅ Обработка завершена")
        yield _sse_event("log", f"📁 Выходной файл: {final_path}")
        rel_path = os.path.relpath(final_path, os.path.expanduser(DEFAULT_OUTPUT_DIR))
        yield _sse_event("complete", f"Файл сохранён: {final_path}", path=rel_path)
    else:
        yield _sse_event("log", "")
        yield _sse_event(
            "error",
            f"⚠ Выходной файл не найден (src={src_path})",
        )


# ── App factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title=DEFAULT_TITLE,
        version="1.0.0",
        docs_url="/docs",
    )

    # ── CORS — permissive for local dev (no credentials needed) ──────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health ────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ── Process ───────────────────────────────────────────────────────
    @app.post("/api/process")
    async def process_video(
        video: UploadFile = File(...),
        srt: Optional[UploadFile] = File(None),
        lang: Optional[str] = Form(None),
        voice: Optional[str] = Form(None),
        tts_cmd: str = Form(""),
        speed: float = Form(1.5),
        orig_vol: float = Form(0.65),
        tts_vol: float = Form(0.93),
        codec: str = Form("Opus"),
        bitrate: str = Form("64"),
        normalize: Optional[str] = Form(None),
        subs_mode: str = Form("auto"),
        sync: bool = Form(False),
        audio_only: bool = Form(False),
        keep_temp: bool = Form(False),
        no_cache: bool = Form(False),
    ):
        """Upload a video and start processing.

        Returns a ``text/event-stream`` stream with ``log``, ``error``,
        and ``complete`` events.
        """
        tmpdir = tempfile.mkdtemp(prefix="rusa_upload_")
        video_path = os.path.join(tmpdir, video.filename or "input_video")
        content = await video.read()
        with open(video_path, "wb") as f:
            f.write(content)

        srt_path: Optional[str] = None
        if srt and srt.filename:
            srt_path = os.path.join(tmpdir, srt.filename or "subtitles.srt")
            srt_content = await srt.read()
            with open(srt_path, "wb") as f:
                f.write(srt_content)

        def _stream() -> Generator[str, None, None]:
            try:
                yield from _process_video(
                    video_file=video_path,
                    srt_file=srt_path,
                    lang=lang,
                    voice=voice,
                    tts_cmd=tts_cmd,
                    speed=speed,
                    orig_vol=orig_vol,
                    tts_vol=tts_vol,
                    codec_label=codec,
                    bitrate=bitrate,
                    normalize=normalize or "",
                    subs_mode=subs_mode,
                    sync=sync,
                    audio_only=audio_only,
                    keep_temp=keep_temp,
                    no_cache=no_cache,
                )
            finally:
                if os.path.isdir(tmpdir):
                    shutil.rmtree(tmpdir, ignore_errors=True)

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # ── Download ──────────────────────────────────────────────────────
    @app.get("/api/download/{path:path}")
    def download_file(path: str):
        """Serve a processed file from the output directory.

        Path traversal protection: only files under ``DEFAULT_OUTPUT_DIR``
        are accessible.  The path is URL-decoded by FastAPI automatically;
        we block any component containing ``..``.
        """
        # Split on both / and \ (Windows) to catch traversal
        parts = path.replace("\\", "/").split("/")
        if ".." in parts:
            raise HTTPException(status_code=403, detail="Forbidden: path traversal")

        full_path = os.path.normpath(
            os.path.join(os.path.expanduser(DEFAULT_OUTPUT_DIR), path)
        )
        output_dir = os.path.normpath(os.path.expanduser(DEFAULT_OUTPUT_DIR))

        if not full_path.startswith(output_dir + os.sep) and full_path != output_dir:
            raise HTTPException(status_code=403, detail="Forbidden: outside output dir")

        if not os.path.isfile(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(full_path, filename=os.path.basename(path))

    return app


# ── Direct execution ──────────────────────────────────────────────────


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Launch the rusa API server via uvicorn."""
    import uvicorn

    app = create_app()
    print(f"🌐 rusa API server: http://{host}:{port}")
    print(f"📚 API docs:       http://{host}:{port}/docs")
    print("Нажмите Ctrl+C для остановки")
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Entry point for ``python -m webui``."""
    import argparse

    parser = argparse.ArgumentParser(description=DEFAULT_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Хост (по умолч. {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Порт (по умолч. {DEFAULT_PORT})")
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
