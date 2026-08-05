#!/usr/bin/env python3
from __future__ import annotations
"""Subtitle extraction, language detection, sync, and parsing for rusa."""
__all__ = ['Entry', 'detect_language_from_srt', 'step_extract_subtitles', 'step_sync_alass', 'step_parse_srt', "step_merge_srt_entries"]

import html
import os
import re
import shutil
import subprocess
from typing import TypedDict

from rusa_shared import (
    EXIT_SUBTITLE_ERROR,
    HAS_LANGDETECT,
    LANG_VOICE_MAP,
    LangDetectException,
    detect,
    die,
    info,
    lang_code_to_ffprobe_codes,
    ok,
    warn,
)


class Entry(TypedDict):
    idx: int
    start_ms: int
    end_ms: int
    text: str

_SUBTITLE_FALLBACK_ENCODINGS = ("cp1251", "cp866", "koi8-r", "latin-1")

try:
    from chardet import detect as _chardet_detect
    _HAS_CHARDET = True
except ImportError:
    _chardet_detect = None  # type: ignore[assignment]
    _HAS_CHARDET = False

try:
    from charset_normalizer import from_bytes as _cn_from_bytes
    _HAS_CN = True
except ImportError:
    _cn_from_bytes = None  # type: ignore[assignment]
    _HAS_CN = False


def _heuristic_decode(raw: bytes) -> str:
    """Best-effort decode for legacy single-byte subtitle encodings.

    Prefer the encoding that yields the most Cyrillic letters, then the fewest
    mojibake artefacts (C1 controls / box-drawing).  Latin-1 never fails, so it
    is the ultimate fallback.
    """
    def _cyrillic(text: str) -> int:
        return sum(1 for c in text if 0x0410 <= ord(c) <= 0x045F)

    def _suspicious(text: str) -> int:
        return sum(
            1
            for c in text
            if 0x80 <= ord(c) <= 0x9F
            or 0x2500 <= ord(c) <= 0x257F
            or c == "\ufffd"
        )

    best_enc, best_key = "latin-1", None
    for enc in _SUBTITLE_FALLBACK_ENCODINGS:
        try:
            text = raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
        key = (-_cyrillic(text), _suspicious(text))
        if best_key is None or key < best_key:
            best_key, best_enc = key, enc
    return raw.decode(best_enc)


def _decode_subtitle_bytes(raw: bytes) -> str:
    """Decode SRT bytes regardless of legacy file encoding.

    Order: strict UTF-8 (with BOM) -> chardet -> charset_normalizer -> heuristic.
    Russian subtitles are commonly Windows-1251/cp866; forcing utf-8 used to
    crash rusa with UnicodeDecodeError.
    """
    if not raw:
        return ""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if _HAS_CHARDET:
        guess = _chardet_detect(raw) if _chardet_detect else None
        enc = guess.get("encoding") if guess else None
        if enc:
            try:
                return raw.decode(enc)
            except (LookupError, UnicodeDecodeError):
                pass
    if _HAS_CN and _cn_from_bytes is not None:
        try:
            match = _cn_from_bytes(raw).best()
            if match is not None:
                return str(match)
        except Exception:
            pass
    return _heuristic_decode(raw)


def _read_subtitle_text(path: str) -> str:
    """Read a subtitle file, detecting legacy encodings instead of crashing."""
    with open(path, "rb") as handle:
        return _decode_subtitle_bytes(handle.read())


def _normalize_utf8(path: str) -> None:
    """Rewrite *path* in place as plain UTF-8 (no BOM)."""
    text = _read_subtitle_text(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _subtitle_line_count(path: str) -> int:
    return len(_read_subtitle_text(path).splitlines())


def _extract_subtitle_stream(video: str, idx: str, dest: str) -> tuple[bool, str]:
    """Extract one embedded subtitle stream to *dest* (.srt).

    ffmpeg's text-subtitle decoder assumes UTF-8, so Windows-1251/cp866/koi8-r
    tracks fail with "Invalid UTF-8 in decoded subtitles text".  Retry with
    -sub_charenc until one attempt succeeds.  Returns (ok, last_stderr).
    """
    attempts = (
        [],
        ["-sub_charenc", "cp1251"],
        ["-sub_charenc", "cp866"],
        ["-sub_charenc", "koi8-r"],
    )
    last_err = ""
    for extra in attempts:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *extra, "-i", video, "-map", f"0:{idx}", dest],
            check=False,
            capture_output=True,
        )
        if rc.stderr:
            last_err = rc.stderr.decode("utf-8", errors="replace").strip()
        if rc.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return True, last_err
    return False, last_err


def detect_language_from_srt(srt_path: str) -> str | None:
    name = os.path.basename(srt_path)
    match = re.match(r".*\.([a-z]{2,7})\.srt$", name)
    if match:
        code = match.group(1).lower()
        # Map 3+ letter codes → ISO 639-1
        lang_map = {
            "rus": "ru", "russian": "ru",
            "eng": "en", "english": "en",
            "heb": "he", "hebrew": "he",
            "deu": "de", "ger": "de", "german": "de",
            "fra": "fr", "fre": "fr", "french": "fr",
            "spa": "es", "spanish": "es",
            "ita": "it", "italian": "it",
            "por": "pt", "portuguese": "pt",
            "jpn": "ja", "japanese": "ja",
            "kor": "ko", "korean": "ko",
            "zho": "zh", "chi": "zh", "chinese": "zh",
            "ara": "ar", "arabic": "ar",
            "tur": "tr", "turkish": "tr",
            "nld": "nl", "dut": "nl", "dutch": "nl",
            "pol": "pl", "polish": "pl",
            "swe": "sv", "swedish": "sv",
            "dan": "da", "danish": "da",
            "fin": "fi", "finnish": "fi",
            "nor": "nb", "norsk": "nb",
            "ces": "cs", "cze": "cs", "czech": "cs",
            "hun": "hu", "hungarian": "hu",
            "bul": "bg", "bulgarian": "bg",
            "ell": "el", "gre": "el", "greek": "el",
            "hin": "hi", "hindi": "hi",
            "hrv": "hr", "croatian": "hr",
            "ind": "id", "indonesian": "id",
            "msa": "ms", "may": "ms", "malay": "ms",
            "ron": "ro", "rum": "ro", "romanian": "ro",
            "slk": "sk", "slo": "sk", "slovak": "sk",
            "srp": "sr", "serbian": "sr",
            "tha": "th", "thai": "th",
            "ukr": "uk", "ukrainian": "uk",
            "vie": "vi", "vietnamese": "vi",
        }
        iso = lang_map.get(code, code)
        if iso in LANG_VOICE_MAP:
            return LANG_VOICE_MAP[iso]

    if not HAS_LANGDETECT:
        return None

    try:
        raw = _read_subtitle_text(srt_path)
        text = re.sub(r"\d+\s+[\d:,.\s\->]+\s+", "", raw)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()[:5000]
        if len(text) < 20:
            return None
        lang = detect(text)
        if lang in LANG_VOICE_MAP:
            return LANG_VOICE_MAP[lang]
    except (LangDetectException, UnicodeDecodeError, OSError):
        pass
    return None


def step_extract_subtitles(video: str, srt_file: str | None, tmpdir: str, target_lang: str | None = None) -> str:
    dest = os.path.join(tmpdir, "subtitles.srt")
    if srt_file:
        if not os.path.isfile(srt_file):
            die(f"Subtitle file not found: {srt_file}", EXIT_SUBTITLE_ERROR)
        info(f"Using subtitles: {srt_file}")
        shutil.copy2(srt_file, dest)
        _normalize_utf8(dest)
        ok(f"Subtitles: {_subtitle_line_count(dest)} lines")
        return dest

    target_codes = lang_code_to_ffprobe_codes(target_lang) if target_lang else ["rus", "ru", "russian"]
    info("Extracting subtitles from the video...")
    found = 0
    available = []
    last_ffmpeg_err = ""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "s",
                "-show_entries",
                "stream=index:stream_tags=language",
                "-of",
                "csv=p=0",
                video,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        result = None
        warn("ffprobe is unavailable. Skipping embedded subtitle lookup and checking nearby .srt files instead.")
    if result and result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) != 2:
                continue
            idx = parts[0].strip()
            lang = parts[1].strip().lower()
            available.append((idx, lang))
            if lang in target_codes:
                info(f"  Found subtitle stream #{idx} ({lang}), extracting...")
                try:
                    extracted_ok, ffmpeg_err = _extract_subtitle_stream(video, idx, dest)
                except OSError:
                    warn("ffmpeg is unavailable, so embedded subtitles could not be extracted")
                    break
                if ffmpeg_err:
                    last_ffmpeg_err = ffmpeg_err
                if extracted_ok:
                    _normalize_utf8(dest)
                    found = 1
                    break

    if not found:
        base = os.path.splitext(video)[0]
        if target_lang:
            for ext in [f".{target_lang}.srt", f".{target_lang[:2]}.srt"]:
                candidate = base + ext
                if os.path.isfile(candidate):
                    shutil.copy2(candidate, dest)
                    found = 1
                    break
        else:
            for ext in [".rus.srt", ".ru.srt", ".russian.srt", ".srt"]:
                candidate = base + ext
                if os.path.isfile(candidate):
                    shutil.copy2(candidate, dest)
                    found = 1
                    break

    if not found:
        avail_str = ", ".join(f"#{idx} ({lang})" for idx, lang in available) if available else "no subtitle streams"
        reason = ""
        if last_ffmpeg_err:
            reason = f"\nffmpeg said: {' '.join(last_ffmpeg_err.split())}"
        if target_lang:
            die(
                f"Could not find subtitles for language '{target_lang}'. Available streams: {avail_str}. "
                f"Pass -s <file.srt> or choose another --lang value.{reason}",
                EXIT_SUBTITLE_ERROR,
            )
        die(
            f"Could not find Russian subtitles. Available streams: {avail_str}. "
            f"Pass -s <file.srt>.{reason}",
            EXIT_SUBTITLE_ERROR,
        )
    ok(f"Subtitles: {_subtitle_line_count(dest)} lines")
    return dest


def step_sync_alass(video: str, subs_path: str, tmpdir: str) -> str:
    if not shutil.which("alass"):
        warn("alass was not found. Subtitle sync is skipped.")
        return subs_path
    info("Synchronizing subtitles with alass...")
    synced = os.path.join(tmpdir, "synced.srt")
    rc = subprocess.run(["alass", video, subs_path, synced], check=False, capture_output=True)
    if rc.returncode == 0 and os.path.isfile(synced) and os.path.getsize(synced) > 0:
        shutil.copy2(synced, subs_path)
        ok("Subtitles synchronized")
    else:
        warn("alass failed. Using the original subtitles.")
    return subs_path


def step_parse_srt(subs_path: str, range_from: int | None, range_to: int | None) -> tuple[list[Entry], int]:
    info("Parsing subtitles...")
    subs = _read_subtitle_text(subs_path).lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", subs.strip())
    entries: list[Entry] = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        match = re.match(
            r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
            lines[1],
        )
        if not match:
            continue
        groups = [int(value) for value in match.groups()]

        def to_ms(h, mm, s, ms):
            return h * 3600000 + mm * 60000 + s * 1000 + ms

        start_ms = to_ms(*groups[:4])
        end_ms = to_ms(*groups[4:])
        text = " ".join(lines[2:])
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        entries.append({"idx": idx, "start_ms": start_ms, "end_ms": end_ms, "text": text})

    if range_from is not None or range_to is not None:
        lo = range_from or 1
        hi = range_to or len(entries)
        entries = [entry for entry in entries if lo <= entry["idx"] <= hi]
        if not entries:
            die(f"No subtitles were found in range {lo}-{hi}", EXIT_SUBTITLE_ERROR)
        for i, entry in enumerate(entries, 1):
            entry["idx"] = i

    count = len(entries)
    ok(f"{count} subtitles" + (f" (range {lo}-{hi})" if range_from or range_to else ""))
    return entries, count


def step_merge_srt_entries(entries: list[Entry], max_gap_ms: int = 200) -> list[Entry]:
    """Merge consecutive subtitle entries that form a single sentence.

    Heuristic: entry N and N+1 are merged when:
      - entry N's text does NOT end with sentence-ending punctuation (.!?…—)
      - AND the gap (N.end → N+1.start) is <= *max_gap_ms* ms
        OR entry N+1's text starts with a lowercase letter

    The merged entry inherits idx=N.idx, start_ms=N.start_ms, end_ms=N+1.end_ms,
    and text = N.text + ' ' + N+1.text.  All entries are re-indexed 1..N.
    """
    if not entries:
        return []

    merged: list[Entry] = []
    _sentence_end = re.compile(r"[.!?…—]$")
    i = 0
    while i < len(entries):
        cur = dict(entries[i])  # shallow copy so we don't mutate caller's dict
        j = i + 1
        while j < len(entries):
            nxt = entries[j]
            gap = nxt["start_ms"] - cur["end_ms"]
            cur_text: str = cur["text"]
            nxt_text: str = nxt["text"]

            # Does cur look like an unfinished sentence?
            if _sentence_end.search(cur_text.rstrip('"»)')):
                break  # sentence complete, stop merging

            # Gap must be small, OR next line starts lowercase
            if not (gap <= max_gap_ms or (nxt_text and nxt_text[0].islower())):
                break  # not a continuation

            # Merge
            cur["text"] = cur_text + " " + nxt_text
            cur["end_ms"] = nxt["end_ms"]
            j += 1

        merged.append(cur)
        i = j

    # Re-index
    for idx, entry in enumerate(merged, 1):
        entry["idx"] = idx

    return merged
