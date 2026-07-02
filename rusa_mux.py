#!/usr/bin/env python3
from __future__ import annotations
"""Mixing, normalization, codec checks, and subtitle mux planning for rusa."""
__all__ = ['step_mix_output', '_get_codec', '_check_ffmpeg_codec', '_subtitle_copy_not_supported', '_probe_subtitle_codecs', '_subtitle_copy_codecs_supported', '_subtitle_convert_codec', '_subtitle_mux_plan', '_build_video_mux_cmd', '_run_loudnorm', '_run_dynaudnorm']

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from rusa_shared import (
    CODEC_MAP,
    DEFAULT_SUBS_MODE,
    EXIT_CODEC_ERROR,
    EXIT_SUBTITLE_ERROR,
    WAV_CHANNELS,
    WAV_FRAMERATE,
    _cfg,
    die,
    info,
    ok,
    warn,
)


def _get_codec(codec_name: str, bitrate: str) -> tuple[str, str, str] | None:
    """Return (ffmpeg_codec, bitrate_arg, extension) or None if unknown."""
    entry = CODEC_MAP.get(codec_name)
    if not entry:
        return None
    return (entry[0], f"{bitrate}k", entry[2])


@lru_cache(maxsize=1)
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
                f"Could not reliably verify subtitle compatibility for codec={codec_label} "
                f"with container '{Path(output).suffix or output}' in --subs-mode copy. "
                "Use --subs-mode auto, --subs-mode convert, or --subs-mode drop.",
                EXIT_SUBTITLE_ERROR,
            )
        if not copy_supported:
            codec_label = ", ".join(source_subtitle_codecs) if source_subtitle_codecs else "unknown"
            die(
                f"Cannot copy subtitles with codec={codec_label} into container '{Path(output).suffix or output}' "
                "in --subs-mode copy. Use --subs-mode convert or --subs-mode drop.",
                EXIT_SUBTITLE_ERROR,
            )
        return ["copy"], source_subtitle_codecs

    if subs_mode == "convert":
        if not convert_codec:
            die(
                f"No supported text subtitle format is available for container '{Path(output).suffix or output}' "
                "in --subs-mode convert.",
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
    _ln_I = _cfg("normalization", "loudnorm_I", default=-16)
    _ln_LRA = _cfg("normalization", "loudnorm_LRA", default=11)
    _ln_TP = _cfg("normalization", "loudnorm_TP", default=-1.5)
    r1 = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav, "-af", f"loudnorm=I={_ln_I}:LRA={_ln_LRA}:TP={_ln_TP}:print_format=json", "-f", "null", "-"],
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
        measured_i = measured.get("input_i", str(_ln_I))
        measured_lra = measured.get("input_lra", str(_ln_LRA))
        measured_tp = measured.get("input_tp", str(_ln_TP))
        measured_thresh = measured.get("input_thresh", "-21.0")
        offset = measured.get("target_offset", "0.0")
    except (json.JSONDecodeError, ValueError):
        return False

    filter_expr = (
        f"loudnorm=I={_ln_I}:LRA={_ln_LRA}:TP={_ln_TP}:"
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
    info("Mixing audio...")
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
        die(f"Audio mix failed: {err_text[:500]}")

    norm_applied = False
    if normalize:
        info(f"Normalizing audio ({normalize})...")
        norm_in = mixed
        norm_out = os.path.join(tmpdir, "normalized.wav")
        if normalize == "fine":
            norm_applied = _run_loudnorm(norm_in, norm_out)
            if not norm_applied:
                warn("loudnorm failed, trying dynaudnorm...")
                norm_applied = _run_dynaudnorm(norm_in, norm_out)
        else:
            norm_applied = _run_dynaudnorm(norm_in, norm_out)
        if norm_applied:
            ok("Normalization complete")
        else:
            warn("Normalization failed. Continuing without it.")

    codec_info = _get_codec(audio_fmt, audio_bitrate)
    if codec_info is None:
        known = ", ".join(sorted(CODEC_MAP))
        die(
            f"Unknown audio format: {audio_fmt}. Available formats: {known}",
            EXIT_CODEC_ERROR,
        )
    ffmpeg_codec, bitrate_arg, ext = codec_info

    if not _check_ffmpeg_codec(ffmpeg_codec):
        alt_suggestions = []
        for alt_name in CODEC_MAP:
            if alt_name == audio_fmt:
                continue
            alt_codec_name = CODEC_MAP[alt_name][0]
            alt_bitrate_default = CODEC_MAP[alt_name][3]
            if _check_ffmpeg_codec(alt_codec_name):
                alt_suggestions.append(f"--{alt_name} {alt_bitrate_default}")
        suggestions = ", ".join(alt_suggestions) if alt_suggestions else "no known alternatives"
        die(
            f"Codec {ffmpeg_codec} is not available in your ffmpeg build.\nTry another format: {suggestions}",
            EXIT_CODEC_ERROR,
        )

    info(f"Encoding: {ffmpeg_codec} {bitrate_arg}...")
    source = norm_out if norm_applied else mixed

    if audio_only:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", source, "-ac", str(WAV_CHANNELS), "-ar", str(WAV_FRAMERATE), "-c:a", ffmpeg_codec, "-b:a", bitrate_arg, output],
            check=False,
            capture_output=True,
        )
    else:
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
            remaining_modes = subtitle_modes[index + 1:]
            if subtitle_mode == "copy" and remaining_modes:
                if _subtitle_copy_not_supported(last_err_text, output):
                    warn("Subtitle copy is not supported for this container. Trying subtitle conversion instead.")
                    continue
                if source_subtitle_codec:
                    warn("Could not copy subtitles as-is. Trying a compatible text subtitle format instead.")
                    continue
                if len(subtitle_modes) > 1:
                    warn("Could not copy subtitles as-is. Trying a compatible text subtitle format instead.")
                    continue
            if subtitle_mode != "drop" and remaining_modes == ["drop"]:
                warn("Could not keep subtitles in the output container. Trying again without subtitles.")
                continue
            break
        else:
            rc = subprocess.CompletedProcess([], 1, stderr=last_err_text.encode("utf-8"))

    if rc.returncode != 0:
        err_text = rc.stderr.decode("utf-8", errors="replace") if rc.stderr else ""
        die(f"Encoding failed: {err_text[:500]}")

    if os.path.isfile(output):
        ok(f"Done: {output}")
        print(f"  Size: {os.path.getsize(output) / 1024 / 1024:.0f} MB")
    else:
        die(f"Output file was not created: {output}")
