"""Gradio application for rusa WebUI."""
from __future__ import annotations

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
from webui.config import DEFAULT_DESCRIPTION, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SHARE, DEFAULT_TITLE


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
    progress: gr.Progress = gr.Progress(),
) -> tuple[str, str | None]:
    """Run rusa processing (stub for Phase 1, real logic in Phase 2).

    Yields status updates via progress bar.
    Returns (log_text, output_file_path_or_None).
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

    def log(msg: str) -> None:
        log_lines.append(msg)
        yield "\n".join(log_lines), None

    if not video_file:
        yield "Ошибка: не выбран видеофайл", None
        return

    yield from log(f"▶ Начинаю обработку: {os.path.basename(video_file)}")
    progress(0.05, desc="Проверка зависимостей...")

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

    yield from log("")
    yield from log("✅ Проверка пройдена. Запуск core-функций rusa...")
    progress(0.1, desc="Запуск обработки...")

    # Phase 2 will replace this with actual rusa.main() call
    # For Phase 1 — simulate processing steps
    steps = [
        ("Извлечение субтитров", 0.2),
        ("Генерация TTS", 0.5),
        ("Конвертация WAV", 0.7),
        ("Сборка voiceover", 0.85),
        ("Микс + кодирование", 0.95),
    ]
    for step_name, step_progress in steps:
        yield from log(f"  → {step_name}...")
        progress(step_progress, desc=step_name)
        time.sleep(0.3)
        yield from log(f"    ✓ {step_name} завершён")

    yield from log("")
    yield from log(f"📁 Выходной файл: (будет определён в Фазе 2)")
    yield from log("✅ Обработка завершена (заглушка Фазы 1)")
    progress(1.0, desc="Готово")

    return


def create_app() -> gr.Blocks:
    """Build the Gradio Blocks interface."""
    css = """
    footer { display: none !important; }
    .gradio-container { max-width: 960px !important; margin: auto !important; }
    """
    with gr.Blocks(title=DEFAULT_TITLE) as app:
        gr.Markdown(f"# {DEFAULT_TITLE}")
        gr.Markdown(DEFAULT_DESCRIPTION)

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

        output_file = gr.File(label="Готовый файл", visible=False)

        # ── Events ────────────────────────────────────────────────────
        process_btn.click(
            fn=_process_video,
            inputs=[
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
            outputs=[log_output, output_file],
        )

        # Update bitrate dropdown when codec changes
        def _update_bitrates(codec_label: str) -> list[str]:
            from webui.config import AUDIO_CODECS
            codec_map = {v["label"]: k for k, v in AUDIO_CODECS.items()}
            key = codec_map.get(codec_label, "opus")
            return AUDIO_CODECS[key]["bitrates"]

        codec_radio.change(
            fn=_update_bitrates,
            inputs=codec_radio,
            outputs=bitrate_dropdown,
        )

    return app


def main() -> None:
    """Entry point for ``python -m rusa.webui``."""
    import argparse

    parser = argparse.ArgumentParser(description=DEFAULT_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Хост (по умолч. 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт (по умолч. 7860)")
    parser.add_argument("--share", action="store_true", help="Создать публичную ссылку (share=True)")
    args = parser.parse_args()

    app = create_app()
    print(f"🌐 rusa WebUI запущен: http://{args.host}:{args.port}")
    app.launch(server_name=args.host, server_port=args.port, share=args.share, css=css, theme=gr.themes.Soft())


if __name__ == "__main__":
    main()
