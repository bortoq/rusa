#!/usr/bin/env python3
"""Mixing, normalization, codec checks, and subtitle mux planning for rusa."""

import json
import os
import subprocess
from pathlib import Path

from rusa_shared import (
    CODEC_MAP,
    DEFAULT_SUBS_MODE,
    EXIT_CODEC_ERROR,
    EXIT_SUBTITLE_ERROR,
    WAV_CHANNELS,
    WAV_FRAMERATE,
    die,
    info,
    ok,
    warn,
)


def _get_codec(codec_name: str, bitrate: str) -> tuple[str, str, str]:
    entry = CODEC_MAP.get(codec_name)
    if not entry:
        return ("libopus", "64k", ".opus")
    return (entry[0], f"{bitrate}k", entry[2])


def _check_ffmpeg_codec(codec: str) -> bool:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    return codec in result.stdout


def _subtitle_copy_not_supported(err_text: str, output: str) -> bool:
    lower = err_text.lower()
    return output.lower().endswith(".mkv") and "subtitle codec" in lower and "not supported" in lower


def _probe_subtitle_codecs(video: str) -> list[str] | None:
    rc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if rc.returncode != 0:
        return None
    codecs = []
    for line in rc.stdout.strip().splitlines():
        value = line.strip().lower()
        if value:
            codecs.append(value)
    return codecs


def _subtitle_copy_codecs_supported(output: str, source_subtitle_codecs: list[str] | None) -> bool | None:
    if source_subtitle_codecs is None:
        return None
    if not source_subtitle_codecs:
        return True
    ext = Path(output).suffix.lower()
    incompatible = {
        ".mkv": {"mov_text"},
        ".mp4": {"subrip", "srt", "ass", "ssa", "webvtt", "vtt", "hdmv_pgs_subtitle", "dvd_subtitle", "xsub"},
        ".m4v": {"subrip", "srt", "ass", "ssa", "webvtt", "vtt", "hdmv_pgs_subtitle", "dvd_subtitle", "xsub"},
    }
    if ext in {".mp4", ".m4v"}:
        return all(codec == "mov_text" for codec in source_subtitle_codecs)
    blocked = incompatible.get(ext)
    if blocked is None:
        return None
    return all(codec not in blocked for codec in source_subtitle_codecs)


def _subtitle_convert_codec(output: str) -> str | None:
    ext = Path(output).suffix.lower()
    if ext == ".mkv":
        return "srt"
    if ext in {".mp4", ".m4v"}:
        return "mov_text"
    return None


def _subtitle_mux_plan(video: str, output: str, subs_mode: str) -> tuple[list[str], list[str]]:
    if subs_mode == "drop":
        return ["drop"], []

    source_subtitle_codecs = _probe_subtitle_codecs(video)
    convert_codec = _subtitle_convert_codec(output)
    copy_supported = _subtitle_copy_codecs_supported(output, source_subtitle_codecs)

    if subs_mode == "copy":
        if copy_supported is None:
            codec_label = ", ".join(source_subtitle_codecs) if source_subtitle_codecs else "unknown"
            die(
                f"Не удалось надёжно проверить совместимость субтитров codec={codec_label} "
                f"для контейнера '{Path(output).suffix or output}' при --subs-mode copy. "
                "Используйте --subs-mode auto, --subs-mode convert или --subs-mode drop.",
                EXIT_SUBTITLE_ERROR,
            )
        if not copy_supported:
            codec_label = ", ".join(source_subtitle_codecs) if source_subtitle_codecs else "unknown"
            die(
                f"Нельзя скопировать субтитры codec={codec_label} в контейнер '{Path(output).suffix or output}' "
                f"при --subs-mode copy. Используйте --subs-mode convert или --subs-mode drop.",
                EXIT_SUBTITLE_ERROR,
            )
        return ["copy"], source_subtitle_codecs

    if subs_mode == "convert":
        if not convert_codec:
            die(
                f"Для контейнера '{Path(output).suffix or output}' нет поддерживаемого текстового формата "
                "для --subs-mode convert.",
                EXIT_SUBTITLE_ERROR,
            )
        return [convert_codec], source_subtitle_codecs

    plan = []
    if copy_supported is True or copy_supported is None:
        plan.append("copy")
    if convert_codec:
        plan.append(convert_codec)
    plan.append("drop")
    return plan, source_subtitle_codecs


def _build_video_mux_cmd(
    video: str,
    source_audio: str,
    output: str,
    ffmpeg_codec: str,
    bitrate_arg: str,
    voiceover_lang: str,
    subtitle_mode: str,
) -> list[str]:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", source_audio, "-map", "0:v", "-map", "0:a:0", "-map", "1:a"]
    if subtitle_mode != "drop":
        cmd.extend(["-map", "0:s?"])
    cmd.extend(["-c:v", "copy", "-c:a:0", "copy", "-c:a:1", ffmpeg_codec, "-b:a:1", bitrate_arg])
    if subtitle_mode != "drop":
        cmd.extend(["-c:s", subtitle_mode])
    cmd.extend(
        [
            "-disposition:a:0",
            "none",
            "-disposition:a:1",
            "default",
            "-metadata:s:a:1",
            f"language={voiceover_lang}",
            "-metadata:s:a:1",
            "title=Voiceover",
            output,
        ]
    )
    return cmd


def _run_loudnorm(in_wav: str, out_wav: str) -> bool:
    r1 = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav, "-af", "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json", "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if r1.returncode != 0:
        return False
    try:
        stderr = r1.stderr
        json_start = stderr.find("{")
        json_end = stderr.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return False
        measured = json.loads(stderr[json_start:json_end])
        measured_i = measured.get("input_i", "-16.0")
        measured_lra = measured.get("input_lra", "11.0")
        measured_tp = measured.get("input_tp", "-1.5")
        measured_thresh = measured.get("input_thresh", "-21.0")
        offset = measured.get("target_offset", "0.0")
    except (json.JSONDecodeError, ValueError):
        return False

    filter_expr = (
        f"loudnorm=I=-16:LRA=11:TP=-1.5:"
        f"measured_I={measured_i}:measured_LRA={measured_lra}:"
        f"measured_TP={measured_tp}:measured_thresh={measured_thresh}:"
        f"offset={offset}:print_format=summary"
    )
    r2 = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav, "-af", filter_expr, "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE), "-sample_fmt", "s16", out_wav],
        check=False,
        capture_output=True,
    )
    return r2.returncode == 0 and os.path.isfile(out_wav) and os.path.getsize(out_wav) > 100


def _run_dynaudnorm(in_wav: str, out_wav: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav, "-af", "dynaudnorm", "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE), "-sample_fmt", "s16", out_wav],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0 and os.path.isfile(out_wav) and os.path.getsize(out_wav) > 100


def step_mix_output(
    video: str,
    voiceover_wav: str,
    orig_vol: str,
    tts_vol: str,
    output: str,
    tmpdir: str,
    audio_fmt: str,
    audio_bitrate: str,
    normalize: str | None,
    audio_only: bool,
    voiceover_lang: str = "rus",
    subs_mode: str = DEFAULT_SUBS_MODE,
) -> None:
    info("Микс...")
    mixed = os.path.join(tmpdir, "mixed.wav")
    filter_expr = (
        f"[1:a]volume={orig_vol}[orig];"
        f"[2:a]volume={tts_vol}[tts];"
        "[orig][tts]amix=inputs=2:duration=first:normalize=0[mixed]"
    )
    rc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", video, "-i", voiceover_wav, "-filter_complex", filter_expr, "-map", "[mixed]", "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE), "-sample_fmt", "s16", mixed],
        check=False,
        capture_output=True,
    )

    if rc.returncode != 0:
        err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
        die(f"Микс не удался: {err_text[:500]}")

    norm_applied = False
    if normalize:
        info(f"Нормализация ({normalize})...")
        norm_in = mixed
        norm_out = os.path.join(tmpdir, "normalized.wav")
        if normalize == "fine":
            norm_applied = _run_loudnorm(norm_in, norm_out)
            if not norm_applied:
                warn("loudnorm не удался, пробую dynaudnorm...")
                norm_applied = _run_dynaudnorm(norm_in, norm_out)
        else:
            norm_applied = _run_dynaudnorm(norm_in, norm_out)
        if norm_applied:
            ok("Нормализация выполнена")
        else:
            warn("Нормализация не удалась, продолжаю без неё")

    ffmpeg_codec, bitrate_arg, ext = _get_codec(audio_fmt, audio_bitrate)
    if not _check_ffmpeg_codec(ffmpeg_codec):
        alt_suggestions = []
        for alt_name in CODEC_MAP:
            if alt_name == audio_fmt:
                continue
            alt_codec_name = CODEC_MAP[alt_name][0]
            alt_bitrate_default = CODEC_MAP[alt_name][3]
            if _check_ffmpeg_codec(alt_codec_name):
                alt_suggestions.append(f"--{alt_name} {alt_bitrate_default}")
        suggestions = ", ".join(alt_suggestions) if alt_suggestions else "нет известных альтернатив"
        die(
            f"Кодек {ffmpeg_codec} недоступен в вашей сборке ffmpeg.\nПопробуйте другой формат: {suggestions}",
            EXIT_CODEC_ERROR,
        )

    info(f"Кодирование: {ffmpeg_codec} {bitrate_arg}...")
    source = norm_out if norm_applied else mixed

    if audio_only:
        if not output:
            base = os.path.splitext(os.path.basename(video))[0]
            output = os.path.join(os.path.dirname(video), f"{base}_voiceover{ext}")
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", source, "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE), "-c:a", ffmpeg_codec, "-b:a", bitrate_arg, output],
            check=False,
            capture_output=True,
        )
    else:
        if not output:
            base = os.path.splitext(os.path.basename(video))[0]
            output = os.path.join(os.path.dirname(video), f"{base}_dubbed.mkv")
        subtitle_modes, source_subtitle_codec = _subtitle_mux_plan(video, output, subs_mode)
        last_err_text = ""
        for index, subtitle_mode in enumerate(subtitle_modes):
            rc = subprocess.run(
                _build_video_mux_cmd(video, source, output, ffmpeg_codec, bitrate_arg, voiceover_lang, subtitle_mode),
                check=False,
                capture_output=True,
            )
            if rc.returncode == 0:
                break
            last_err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
            remaining_modes = subtitle_modes[index + 1 :]
            if subtitle_mode == "copy" and remaining_modes:
                if _subtitle_copy_not_supported(last_err_text, output):
                    warn("Копирование субтитров в этот контейнер не поддерживается, пробую перекодировать их в SRT")
                    continue
                if source_subtitle_codec:
                    warn("Не удалось скопировать субтитры как есть, пробую совместимый текстовый формат")
                    continue
                if len(subtitle_modes) > 1:
                    warn("Не удалось скопировать субтитры как есть, пробую совместимый текстовый формат")
                    continue
            if subtitle_mode != "drop" and remaining_modes == ["drop"]:
                warn("Не удалось сохранить субтитры в выходном контейнере, пробую сохранить файл без них")
                continue
            break
        else:
            rc = subprocess.CompletedProcess([], 1, stderr=last_err_text.encode("utf-8"))

    if rc.returncode != 0:
        err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
        die(f"Кодирование не удалось: {err_text[:500]}")

    if os.path.isfile(output):
        ok(f"Готово: {output}")
        print(f"  Размер: {os.path.getsize(output) / 1024 / 1024:.0f} MB")
    else:
        die(f"Выходной файл не создан: {output}")
