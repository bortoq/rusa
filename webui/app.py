"""Gradio application for rusa WebUI."""
from __future__ import annotations

from typing import Generator

import os
import subprocess
import sys
import tempfile
import time

import gradio as gr

from webui.components import (
    create_advanced_checkboxes,
    create_codec_group,
    create_lang_selector,
    create_normalize_input,
    create_speed_slider,
    create_srt_input,
    create_subs_mode_input,
    create_tts_cmd_input,
    create_video_input,
    create_voice_input,
    create_volume_sliders,
)
from webui.config import DEFAULT_DESCRIPTION, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SHARE, DEFAULT_TITLE, DEFAULT_OUTPUT_DIR

_WEBUI_CSS = """\
    footer { display: none !important; }\
    .gradio-container { max-width: 960px !important; margin: auto !important; }\
    """


def _process_video(
    video_file: str | None,
    srt_file: str | None,
    lang: str | None,
    voice: str | None,
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
    output_path: str | None = None,
) -> Generator[tuple[str, str | None], None, None]:
    """Run rusa processing pipeline.

    Yields (log_text, output_file_path_or_None).
    """
    from webui.config import AUDIO_CODECS

    # Build audio format from the codec label
    codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
    audio_fmt = codec_map.get(codec_label)

    from webui.utils import build_args
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

    log_lines: list[str] = []

    def log(msg: str) -> Generator[tuple[str, str | None], None, None]:
        log_lines.append(msg)
        yield "\n".join(log_lines), None

    if not video_file:
        yield "Ошибка: не выбран видеофайл", None
        return

    yield from log(f"▶ Начинаю обработку: {os.path.basename(video_file)}")

    from rusa_shared import which
    try:
        which("ffmpeg")
        which("ffprobe")
        which("python3")
    except SystemExit as exc:
        yield f"Ошибка: ffmpeg/ffprobe не найдены (exit {exc.code})", None
        return

    yield from log("✓ ffmpeg, ffprobe, python3 — найдены")

    # Check if edge-tts is available (unless --tts-cmd)
    if not args.tts_cmd:
        try:
            rc = subprocess.run(
                ["python3", "-m", "edge_tts", "--help"],
                check=False, capture_output=True, timeout=30,
            )
            if rc.returncode != 0:
                yield "Ошибка: edge-tts не установлен (pip install edge-tts)", None
                return
        except (OSError, subprocess.TimeoutExpired):
            yield "Ошибка: edge-tts не доступен", None
            return
        yield from log("✓ edge-tts — доступен")


    # Phase 2: call real rusa.main()
    import io
    import re
    from contextlib import redirect_stdout, redirect_stderr

    # Strip ANSI escape sequences for clean log display
    _re_ansi = re.compile(r"\x1b\[[0-9;]*m")

    def _strip_ansi(text: str) -> str:
        return _re_ansi.sub("", text)

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    def _emit_captured(
        src: io.StringIO, prefix: str = "",
    ) -> Generator[tuple[str, str | None], None, None]:
        text = src.getvalue()
        if not text.strip():
            return
        cleaned = _strip_ansi(text)
        for line in cleaned.strip().split("\n"):
            if line:
                yield from log(f"{prefix}{line}")

    try:
        from rusa import main as rusa_main
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            rusa_main(args)
    except SystemExit as exc:
        yield from _emit_captured(stdout_capture)
        yield from _emit_captured(stderr_capture, "⚠ ")
        yield from log(f"❌ Ошибка обработки (код {exc.code})")
        return
    except Exception as exc:
        yield from _emit_captured(stdout_capture)
        yield from _emit_captured(stderr_capture, "⚠ ")
        yield from log(f"❌ Непредвиденная ошибка: {exc}")
        return

    # Show rusa's captured output in the log
    yield from _emit_captured(stdout_capture)
    yield from _emit_captured(stderr_capture, "⚠ ")

    # Copy output file to user-accessible directory
    src_path = args.output  # set by rusa.main()
    final_path = None
    if src_path and os.path.isfile(src_path):
        import shutil
        if output_path:
            # Write directly to the user-chosen path
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(src_path, output_path)
            final_path = output_path
        else:
            from webui.config import DEFAULT_OUTPUT_DIR
            dest_dir = os.path.expanduser(DEFAULT_OUTPUT_DIR)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(src_path))
            shutil.copy2(src_path, dest)
            final_path = dest

    if final_path and os.path.isfile(final_path):
        yield from log("")
        yield from log("✅ Обработка завершена")
        yield from log(f"📁 Выходной файл: {final_path}")
        yield "\n".join(log_lines), final_path
    else:
        yield from log("")
        yield from log(f"⚠ Выходной файл не найден (src={src_path})")
        yield "\n".join(log_lines), None
    return


def create_app() -> gr.Blocks:
    """Build the Gradio Blocks interface."""
    with gr.Blocks(title=DEFAULT_TITLE) as app:
        gr.Markdown(f"# {DEFAULT_TITLE}")
        gr.Markdown(DEFAULT_DESCRIPTION)

        # ── Output file path picker ───────────────────────────
        output_file_state = gr.State(value=None)
        with gr.Row():
            output_picker_btn = gr.Button("📁 Выходной файл", variant="secondary", scale=1)
            output_path_display = gr.Textbox(
                label="Путь сохранения",
                value="",
                placeholder="Не выбран (будет использован путь по умолчанию)",
                interactive=False,
                scale=4,
            )
        with gr.Row():
            with gr.Column(scale=1):
                video_input = create_video_input()
                srt_input = create_srt_input()

        with gr.Accordion("Основные настройки", open=True):
            with gr.Row():
                lang_input = create_lang_selector()
                voice_input = create_voice_input()
            tts_cmd_input = create_tts_cmd_input()

        with gr.Accordion("Аудио", open=True):
            with gr.Row():
                speed_slider = create_speed_slider()
            with gr.Row():
                orig_vol_slider, tts_vol_slider = create_volume_sliders()
            with gr.Row():
                codec_radio, bitrate_dropdown = create_codec_group()
            normalize_input = create_normalize_input()

        with gr.Accordion("Субтитры", open=False):
            subs_mode_input = create_subs_mode_input()
            sync_check, audio_only_check, keep_temp_check, no_cache_check = create_advanced_checkboxes()



        process_btn = gr.Button("🚀 Запустить обработку", variant="primary", scale=2)

        log_output = gr.Textbox(
            label="Лог обработки",
            lines=15,
            max_lines=30,
            interactive=False,
        )

        # ── Events ────────────────────────────────────────────────────
        process_btn.click(
            fn=_process_video,
            inputs=[
                output_file_state,
                video_input,
                srt_input,
                lang_input,
                voice_input,
                tts_cmd_input,
                speed_slider,
                orig_vol_slider,
                tts_vol_slider,
                codec_radio,
                bitrate_dropdown,
                normalize_input,
                subs_mode_input,
                sync_check,
                audio_only_check,
                keep_temp_check,
                no_cache_check,
            ],
            outputs=[log_output, output_path_display],
        )

        # Update bitrate choices AND value when codec changes
        def _update_bitrates(codec_label: str) -> dict:
            from webui.config import AUDIO_CODECS
            codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
            key = codec_map.get(codec_label, "opus")
            info = AUDIO_CODECS[key]
            return gr.update(choices=info["bitrates"], value=info["default"])

        codec_radio.change(
            fn=_update_bitrates,
            inputs=codec_radio,
            outputs=bitrate_dropdown,
        )

    return app


def _check_port_available(host: str, port: int) -> None:
    """Exit with a friendly message if the port is already in use."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:
        print(f"❌ Порт {port} уже занят (возможно, уже запущен другой экземпляр rusa WebUI).")
        print(f"   Используйте --port для указания другого порта, например: --port {port + 1}")
        sys.exit(1)
    finally:
        sock.close()


def main() -> None:
    """Entry point for ``python -m rusa.webui``."""
    import warnings
    warnings.filterwarnings("ignore", message=".*HTTP_422_UNPROCESSABLE_ENTITY.*")
    import argparse
    from webui.config import DEFAULT_OUTPUT_DIR

    parser = argparse.ArgumentParser(description=DEFAULT_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Хост (по умолч. 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт (по умолч. 7860)")
    parser.add_argument("--share", action="store_true", help="Создать публичную ссылку (share=True)")
    args = parser.parse_args()
    _check_port_available(args.host, args.port)

    app = create_app()
    print(f"🌐 rusa WebUI запущен: http://{args.host}:{args.port}")
    print("Нажмите Ctrl+C для остановки")
    try:
        app.launch(server_name=args.host, server_port=args.port, share=args.share, css=_WEBUI_CSS, theme=gr.themes.Soft(), allowed_paths=[os.path.expanduser(DEFAULT_OUTPUT_DIR)])
    except OSError as exc:
        msg = str(exc)
        if "Cannot find empty port" in msg:
            print(f"❌ Порт {args.port} занят. Используйте --port для указания другого порта, например: --port {args.port + 1}")
        else:
            print(f"❌ Ошибка запуска сервера: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен.")
        # Gradio handles actual cleanup; just notify the user.


if __name__ == "__main__":
    main()
