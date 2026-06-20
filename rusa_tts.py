#!/usr/bin/env python3
from __future__ import annotations
"""TTS generation helpers for rusa."""
__all__ = ['_split_text', 'step_generate_tts']

import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from rusa_shared import (
    BACKEND_REGISTRY,
    HAS_TQDM,
    MAX_TTS_CHARS,
    copy_into_cache,
    die,
    info,
    ok,
    tqdm,
    tts_cache_path,
    warn,
)


def _split_text(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts = []
    while len(text) > max_chars:
        chunk = text[:max_chars]
        split_at = -1
        # Prefer splitting after sentence-ending punctuation followed by space/end
        for match in re.finditer(r"[.!?\u2026](\s|$)", chunk):
            split_at = match.end()
        if split_at <= 0:
            split_at = chunk.rfind(" ")
            if split_at == -1:
                split_at = max_chars
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts



def _tts_generate(text: str, voice: str, out: str, backend: str) -> int:
    """Generate TTS audio using the specified backend. Returns 0 on success."""
    backend_cls = BACKEND_REGISTRY.get(backend)
    if backend_cls is None:
        die(f"Неизвестный TTS бэкенд: {backend}")
    return backend_cls.generate(text, voice, out)


def step_generate_tts(entries: list[dict], voice: str, threads: int, tmpdir: str, backend: str = "edge") -> list[tuple[int, str]]:
    info(f"Генерация TTS ({len(entries)} файлов, {threads} потоков)...")
    tts_dir = os.path.join(tmpdir, "tts")
    os.makedirs(tts_dir, exist_ok=True)
    max_retries = 3

    def gen_one(entry: dict) -> tuple[int, str | None]:
        idx = entry["idx"]
        text = entry["text"]
        if not text or not text.strip():
            return idx, None

        parts = _split_text(text)
        out = os.path.join(tts_dir, f"batch_{idx:04d}.mp3")
        cache_path = tts_cache_path(voice, text, backend)

        if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 100:
            shutil.copy2(cache_path, out)
            return idx, out

        if len(parts) == 1:
            for attempt in range(1, max_retries + 1):
                if os.path.isfile(out) and os.path.getsize(out) > 100:
                    copy_into_cache(out, cache_path)
                    return idx, out
                try:
                    rc = _tts_generate(parts[0], voice, out, backend)
                    if rc == 0 and os.path.isfile(out) and os.path.getsize(out) > 100:
                        copy_into_cache(out, cache_path)
                        return idx, out
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
            return idx, None

        part_files: list[str] = []
        for part_index, part in enumerate(parts):
            part_out = os.path.join(tts_dir, f"batch_{idx:04d}_p{part_index}.mp3")
            generated = False
            for attempt in range(1, max_retries + 1):
                if os.path.isfile(part_out) and os.path.getsize(part_out) > 100:
                    generated = True
                    break
                try:
                    rc = _tts_generate(part, voice, part_out, backend)
                    if rc == 0 and os.path.isfile(part_out) and os.path.getsize(part_out) > 100:
                        generated = True
                        break
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
            if generated:
                part_files.append(part_out)

        if len(part_files) != len(parts):
            warn(f"  #{idx} не удалось сгенерировать все части TTS ({len(part_files)}/{len(parts)})")
            return idx, None

        concat_list = os.path.join(tts_dir, f"batch_{idx:04d}_list.txt")
        with open(concat_list, "w", encoding="utf-8") as handle:
            for part_file in part_files:
                handle.write(f"file '{part_file}'\n")
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out],
            check=False,
            capture_output=True,
        )
        if rc.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 100:
            copy_into_cache(out, cache_path)
            return idx, out
        warn(f"  #{idx} не удалось склеить TTS-части без потери текста")
        return idx, None

    results: list[tuple[int, str]] = []
    total = len(entries)
    done = 0
    pbar = tqdm(total=total, desc="  TTS", unit="sub") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(gen_one, entry): entry for entry in entries}
        for future in as_completed(futures):
            done += 1
            idx, out = future.result()
            if out:
                results.append((idx, out))
            if pbar:
                pbar.update(1)
            elif done % 30 == 0 or done == total:
                print(f"  [{done}/{total}]")

    if pbar:
        pbar.close()

    results.sort(key=lambda item: item[0])
    ok(f"TTS: {len(results)}/{len(entries)}")
    if not results:
        die("Не удалось сгенерировать ни одного TTS-файла")
    return results
