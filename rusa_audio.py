#!/usr/bin/env python3
from __future__ import annotations
"""Audio conversion and assembly for rusa."""
__all__ = ['step_convert_wav', 'step_assemble']

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


def step_convert_wav(tts_results: list[tuple[int, str]], speed: str, tmpdir: str, threads: int = 1) -> list[tuple[int, str, float]]:
    info(f"Converting MP3 -> WAV + atempo={speed}x...")
    wav_dir = os.path.join(tmpdir, "wav")
    os.makedirs(wav_dir, exist_ok=True)
    results: list[tuple[int, str, float]] = []

    speed_val = float(speed)
    if speed_val > 2.0:
        chain = []
        remaining = speed_val
        while remaining > 2.0:
            chain.append("atempo=2.0")
            remaining /= 2.0
        chain.append(f"atempo={remaining:.6f}")
        tempo_filter = ",".join(chain)
    else:
        tempo_filter = f"atempo={speed_val:.6f}"

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

        filter_str = (
            f"{tempo_filter},"
            "silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
            "areverse,"
            "silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
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
            except Exception:
                copy_into_cache(wav_path, cache_path)
                return (idx, wav_path, 0)
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
    ok(f"WAV (sped {speed}x): {len(results)}")
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
