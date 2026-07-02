#!/usr/bin/env python3
from __future__ import annotations
"""Audio conversion and assembly for rusa."""
__all__ = ['step_convert_wav', 'step_assemble', 'compute_auto_speed', '_mp3_duration']

import os
import shutil
import struct
import subprocess
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from rusa_shared import (
    HAS_TQDM,
    WAV_BPF,
    WAV_CHANNELS,
    WAV_FRAMERATE,
    WAV_HEADER_SIZE,
    WAV_SAMPLEWIDTH,
    copy_into_cache,
    die,
    info,
    ok,
    tqdm,
    warn,
    wav_cache_path,
)


def _mp3_duration(path: str) -> float:
    """Return duration in ms of an audio file using ffprobe.  Returns 0 on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip()) * 1000  # seconds → ms
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return 0.0


def compute_auto_speed(
    tts_results: list[tuple[int, str]],
    entries: list[dict],
    max_speed: float,
    min_speed: float = 0.8,
) -> dict[int, float]:
    """Build per-entry speed map so each TTS segment fits its subtitle timeslot.

    For each (idx, mp3_path) in *tts_results*:
      1. measure actual mp3 duration via ffprobe
      2. available time = entry.end_ms - entry.start_ms
      3. required = mp3_dur / available, clamped to [min_speed, max_speed]

    Returns *{idx: tempo, ...}*.
    """
    entry_map: dict[int, dict] = {e["idx"]: e for e in entries}
    speed_map: dict[int, float] = {}
    for idx, mp3_path in tts_results:
        entry = entry_map.get(idx)
        if entry is None:
            speed_map[idx] = max_speed
            continue
        avail_ms = entry["end_ms"] - entry["start_ms"]
        if avail_ms <= 0:
            speed_map[idx] = max_speed
            continue
        mp3_dur_ms = _mp3_duration(mp3_path)
        if mp3_dur_ms <= 0:
            speed_map[idx] = max_speed
            continue
        required = mp3_dur_ms / avail_ms
        speed_map[idx] = max(min_speed, min(required, max_speed))
    return speed_map


def step_convert_wav(
    tts_results: list[tuple[int, str]],
    speed: str | dict[int, float],
    tmpdir: str,
    threads: int = 1,
) -> list[tuple[int, str, float]]:
    if isinstance(speed, dict):
        info("Converting MP3 -> WAV (auto-tempo)...")
    else:
        info(f"Converting MP3 -> WAV + atempo={speed}x...")
    wav_dir = os.path.join(tmpdir, "wav")
    os.makedirs(wav_dir, exist_ok=True)
    results: list[tuple[int, str, float]] = []

    def _tempo_filter(speed_val: float) -> str:
        if speed_val > 2.0:
            chain = []
            remaining = speed_val
            while remaining > 2.0:
                chain.append("atempo=2.0")
                remaining /= 2.0
            chain.append(f"atempo={remaining:.6f}")
            return ",".join(chain)
        return f"atempo={speed_val:.6f}"

    def convert_one(item: tuple[int, str]) -> tuple[int, str, float] | None:
        idx, mp3_path = item
        wav_path = os.path.join(wav_dir, f"batch_{idx:04d}.wav")
        cache_path = wav_cache_path(mp3_path, speed)
        if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 44:
            shutil.copy2(cache_path, wav_path)
            try:
                with wave.open(wav_path, "rb") as handle:
                    frames = handle.getnframes()
                    duration_ms = frames / WAV_FRAMERATE * 1000
                if duration_ms >= 50:
                    return (idx, wav_path, duration_ms)
                warn(f"  #{idx} cached wav too short ({duration_ms:.0f}ms), regenerating")
            except Exception:
                warn(f"  #{idx} cached wav damaged, regenerating")

        spd = speed.get(idx, 1.0) if isinstance(speed, dict) else float(speed)
        filter_str = (
            f"{_tempo_filter(spd)},"
            "silenceremove=start_periods=1:start_threshold=0.0001:start_silence=0.01,"
            "areverse,"
            "silenceremove=start_periods=1:start_threshold=0.0001:start_silence=0.01,"
            "areverse"
        )
        rc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                mp3_path,
                "-af",
                filter_str,
                "-ac",
                str(WAV_CHANNELS),
                "-ar",
                str(WAV_FRAMERATE),
                "-sample_fmt",
                "s16",
                wav_path,
            ],
            check=False,
            capture_output=True,
        )
        if rc.returncode == 0 and os.path.isfile(wav_path) and os.path.getsize(wav_path) > 44:
            try:
                with wave.open(wav_path, "rb") as handle:
                    frames = handle.getnframes()
                    duration_ms = frames / WAV_FRAMERATE * 1000
                if duration_ms >= 50:
                    copy_into_cache(wav_path, cache_path)
                    return (idx, wav_path, duration_ms)
                warn(f"  #{idx} too short ({duration_ms:.0f}ms), skipped")
            except Exception as exc:
                warn(f"  #{idx} WAV damaged: {exc}")
                return None
        else:
            warn(f"  #{idx} could not be converted")
        return None

    total = len(tts_results)
    done = 0
    pbar = tqdm(total=total, desc="  WAV", unit="sub") if HAS_TQDM else None
    with ThreadPoolExecutor(max_workers=max(1, threads)) as executor:
        futures = {executor.submit(convert_one, item): item[0] for item in tts_results}
        for future in as_completed(futures):
            done += 1
            converted = future.result()
            if converted is not None:
                results.append(converted)
            if pbar:
                pbar.update(1)
            elif done % 30 == 0 or done == total:
                print(f"  [{done}/{total}]")
    if pbar:
        pbar.close()
    results.sort(key=lambda item: item[0])
    speed_label = "auto" if isinstance(speed, dict) else speed
    ok(f"WAV (sped {speed_label}x): {len(results)}")
    return results


def step_assemble(entries: list[dict], wav_results: list[tuple[int, str, float]], tmpdir: str) -> str:
    out_path = os.path.join(tmpdir, "voiceover.wav")
    info("Assembling voiceover...")
    wav_map: dict[int, tuple[str, float]] = {}
    for idx, path, dur in wav_results:
        wav_map[idx] = (path, dur)
    segments: list[dict] = []
    for entry in entries:
        idx = entry["idx"]
        if idx in wav_map:
            path, dur = wav_map[idx]
            if dur <= 0:
                warn(f"  #{idx} zero-duration segment skipped")
                continue
            segments.append({"start_ms": entry["start_ms"], "duration_ms": dur, "path": path})
    if not segments:
        die("No audio segments are available for assembly")
    segments.sort(key=lambda seg: seg["start_ms"])
    max_end_ms = max(seg["start_ms"] + seg["duration_ms"] for seg in segments)
    print(f"  Segments: {len(segments)}, max duration: {max_end_ms / 1000:.0f}s")
    cur_frame = 0
    overlaps = 0
    chunk = 10 * 1024 * 1024
    zero_chunk = b"\x00" * chunk
    with open(out_path, "wb") as handle:
        handle.write(b"RIFF")
        handle.write(struct.pack("<I", 36))
        handle.write(b"WAVE")
        handle.write(b"fmt ")
        handle.write(
            struct.pack(
                "<IHHIIHH",
                16,
                1,
                WAV_CHANNELS,
                WAV_FRAMERATE,
                WAV_BPF * WAV_FRAMERATE,
                WAV_BPF,
                WAV_SAMPLEWIDTH * 8,
            )
        )
        handle.write(b"data")
        handle.write(struct.pack("<I", 0))

        for index, seg in enumerate(segments, 1):
            start_frame = int(seg["start_ms"] * WAV_FRAMERATE / 1000)
            target = max(cur_frame, start_frame)
            if target > start_frame:
                overlaps += 1
            gap_bytes = (target - cur_frame) * WAV_BPF
            while gap_bytes > 0:
                count = min(gap_bytes, chunk)
                if count == chunk:
                    handle.write(zero_chunk)
                else:
                    handle.write(b"\x00" * count)
                gap_bytes -= count
            with wave.open(seg["path"], "rb") as wav_handle:
                frame_data = wav_handle.readframes(wav_handle.getnframes())
            handle.write(frame_data)
            cur_frame = target + (len(frame_data) // WAV_BPF)
            if not HAS_TQDM and (index % 100 == 0 or index == len(segments)):
                print(f"    ... {index}/{len(segments)}")

        actual_data_bytes = cur_frame * WAV_BPF
        handle.seek(4)
        handle.write(struct.pack("<I", 36 + actual_data_bytes))
        handle.seek(40)
        handle.write(struct.pack("<I", actual_data_bytes))

    if overlaps:
        pct = overlaps * 100 // len(segments)
        print(f"  Overlaps: {overlaps} ({pct}%)")
        if pct > 20:
            warn("Many overlaps were detected. Try a higher --speed or a faster voice.")
    print(f"  Voiceover: {os.path.getsize(out_path) / 1024 / 1024:.0f} MB")
    ok("Voiceover assembled")
    return out_path
