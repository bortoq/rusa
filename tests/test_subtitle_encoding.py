"""Tests for robust subtitle encoding handling and embedded-stream extraction.

Covers two reported regressions:
  1. Russian subtitles embedded in a video (Windows-1251/cp866/koi8-r SRT streams)
     made ffmpeg extraction fail with "Invalid UTF-8 in decoded subtitles text",
     so rusa reported "Could not find Russian subtitles".
  2. Legacy-encoded external .srt files (e.g. cp1251) crashed rusa with
     UnicodeDecodeError.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa_shared
import rusa_subtitle

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"

RU_TEXT = (
    "1\n00:00:01,000 --> 00:00:04,000\nПривет, это русские субтитры!\n\n"
    "2\n00:00:05,000 --> 00:00:08,000\nВторая строка, проверка Ёлка ёлка\n"
)


# ── _decode_subtitle_bytes unit tests ─────────────────────────────────

def test_decode_utf8():
    assert rusa_subtitle._decode_subtitle_bytes(RU_TEXT.encode("utf-8")) == RU_TEXT


def test_decode_utf8_with_bom():
    raw = b"\xef\xbb\xbf" + RU_TEXT.encode("utf-8")
    assert rusa_subtitle._decode_subtitle_bytes(raw) == RU_TEXT


def test_decode_cp1251():
    assert rusa_subtitle._decode_subtitle_bytes(RU_TEXT.encode("cp1251")) == RU_TEXT


def test_decode_cp866():
    assert rusa_subtitle._decode_subtitle_bytes(RU_TEXT.encode("cp866")) == RU_TEXT


def test_decode_koi8_r():
    assert rusa_subtitle._decode_subtitle_bytes(RU_TEXT.encode("koi8-r")) == RU_TEXT


@pytest.mark.parametrize("encoding", ["cp1251", "cp866", "koi8-r"])
def test_decode_legacy_russian_without_optional_detectors(monkeypatch, encoding):
    monkeypatch.setattr(rusa_subtitle, "_HAS_CHARDET", False)
    monkeypatch.setattr(rusa_subtitle, "_HAS_CN", False)
    for text in (RU_TEXT, RU_TEXT.upper()):
        assert rusa_subtitle._decode_subtitle_bytes(text.encode(encoding)) == text


def test_decode_empty_bytes():
    assert rusa_subtitle._decode_subtitle_bytes(b"") == ""


def test_decode_byte_0xcf_from_user_report():
    """Exact byte (0xcf = 'П' in cp1251) from the reported crash."""
    raw = b"1\n00:00:00,000 --> 00:00:02,000\n\xcf\xf0\xe8\xe2\xe5\xf2\n"
    out = rusa_subtitle._decode_subtitle_bytes(raw)
    assert "Привет" in out


def test_decode_garbage_never_raises():
    garbage = bytes(range(0x80, 0x100)) * 3
    out = rusa_subtitle._decode_subtitle_bytes(garbage)
    assert isinstance(out, str)


# ── step_parse_srt with legacy encodings ──────────────────────────────

def test_parse_srt_cp1251(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_bytes(RU_TEXT.encode("cp1251"))
    entries, count = rusa_subtitle.step_parse_srt(str(p), None, None)
    assert count == 2
    assert entries[0]["text"] == "Привет, это русские субтитры!"
    assert entries[1]["text"] == "Вторая строка, проверка Ёлка ёлка"


def test_parse_srt_cp866(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_bytes(RU_TEXT.encode("cp866"))
    entries, count = rusa_subtitle.step_parse_srt(str(p), None, None)
    assert count == 2
    assert entries[0]["text"] == "Привет, это русские субтитры!"


# ── detect_language_from_srt with legacy encodings ────────────────────

def test_detect_cp1251_by_extension(tmp_path):
    p = tmp_path / "movie.ru.srt"
    p.write_bytes(RU_TEXT.encode("cp1251"))
    assert rusa_subtitle.detect_language_from_srt(str(p)) == "ru-RU-SvetlanaNeural"


def test_detect_cp1251_by_content(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_bytes(RU_TEXT.encode("cp1251"))
    result = rusa_subtitle.detect_language_from_srt(str(p))
    if rusa_shared.HAS_LANGDETECT:
        assert result == "ru-RU-SvetlanaNeural"
    else:
        assert result is None


# ── step_extract_subtitles: external cp1251 sidecar ───────────────────

def test_extract_external_cp1251_normalizes_to_utf8(tmp_path):
    srt = tmp_path / "subs.srt"
    srt.write_bytes(RU_TEXT.encode("cp1251"))
    work = tmp_path / "work"
    work.mkdir()
    out = rusa_subtitle.step_extract_subtitles("video.mkv", str(srt), str(work))
    assert Path(out).read_bytes().decode("utf-8") == RU_TEXT
    entries, count = rusa_subtitle.step_parse_srt(out, None, None)
    assert count == 2
    assert entries[0]["text"] == "Привет, это русские субтитры!"


# ── step_extract_subtitles: embedded streams (mocked) ─────────────────

def test_extract_embedded_retries_with_sub_charenc(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout="2,rus\n", stderr="")
        if "-sub_charenc" in cmd:  # ffmpeg with legacy charset succeeds
            Path(cmd[-1]).write_text("1\n00:00:01,000 --> 00:00:02,000\nПривет\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        # plain ffmpeg attempt fails exactly like the reported bug
        return subprocess.CompletedProcess(
            cmd, 69, stdout=b"",
            stderr=b"Invalid UTF-8 in decoded subtitles text; maybe missing -sub_charenc option",
        )

    monkeypatch.setattr(rusa_subtitle.subprocess, "run", fake_run)
    work = tmp_path / "work"
    work.mkdir()
    out = rusa_subtitle.step_extract_subtitles("video.mkv", None, str(work))
    assert Path(out).read_text(encoding="utf-8").startswith("1\n00:00:01,000")
    ffmpeg_calls = [c for c in calls if c[0] == "ffmpeg"]
    assert len(ffmpeg_calls) >= 2  # plain attempt failed, charenc retry succeeded


def test_extract_embedded_total_failure_reports_ffmpeg_error(monkeypatch, tmp_path, capsys):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout="2,rus\n", stderr="")
        return subprocess.CompletedProcess(
            cmd, 69, stdout=b"",
            stderr=b"Subtitle encoding currently only possible from text to text or bitmap to bitmap",
        )

    monkeypatch.setattr(rusa_subtitle.subprocess, "run", fake_run)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(SystemExit) as exc:
        rusa_subtitle.step_extract_subtitles("video.mkv", None, str(work))
    assert exc.value.code == rusa_shared.EXIT_SUBTITLE_ERROR
    assert "text to text" in capsys.readouterr().err


def test_extract_embedded_ffprobe_unavailable_falls_back(monkeypatch, tmp_path):
    """ffprobe missing -> warn and fall through to nearby .srt search."""
    monkeypatch.setattr(
        rusa_subtitle.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no ffprobe")),
    )
    video = str(tmp_path / "movie.mkv")
    nearby = tmp_path / "movie.rus.srt"
    nearby.write_text(RU_TEXT, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    out = rusa_subtitle.step_extract_subtitles(video, None, str(work))
    assert Path(out).read_text(encoding="utf-8") == RU_TEXT


# ── step_extract_subtitles: embedded streams (real ffmpeg fixtures) ───

def _build_mkv_with_srt(video: str, srt: Path, out: Path) -> Path:
    if shutil.which("ffmpeg") is None or not Path(video).is_file():
        return None  # caller skips
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video, "-i", str(srt),
        "-map", "0:v", "-map", "0:a?", "-map", "1:0",
        "-c", "copy", "-metadata:s:s:0", "language=rus",
        str(out),
    ]
    rc = subprocess.run(cmd, capture_output=True)
    if rc.returncode != 0 or not out.is_file():
        return None
    return out


@pytest.mark.skipif(
    not (FIXTURES_DIR / "test_video.mkv").is_file() or shutil.which("ffmpeg") is None,
    reason="requires video fixture and ffmpeg",
)
def test_extract_embedded_cp1251_real(tmp_path):
    srt = tmp_path / "rus_cp1251.srt"
    srt.write_bytes(RU_TEXT.encode("cp1251"))
    mkv = _build_mkv_with_srt(str(FIXTURES_DIR / "test_video.mkv"), srt, tmp_path / "emb.mkv")
    if mkv is None:
        pytest.skip("ffmpeg could not build the embedded-subtitle fixture")
    work = tmp_path / "work"
    work.mkdir()
    out = rusa_subtitle.step_extract_subtitles(str(mkv), None, str(work))
    entries, count = rusa_subtitle.step_parse_srt(out, None, None)
    assert count == 2
    assert entries[0]["text"] == "Привет, это русские субтитры!"


@pytest.mark.skipif(
    not (FIXTURES_DIR / "test_video.mkv").is_file() or shutil.which("ffmpeg") is None,
    reason="requires video fixture and ffmpeg",
)
def test_extract_embedded_utf8_stays_utf8_real(tmp_path):
    """UTF-8 embedded streams must not be mojibaked by -sub_charenc retries."""
    srt = tmp_path / "rus_utf8.srt"
    srt.write_text(RU_TEXT, encoding="utf-8")
    mkv = _build_mkv_with_srt(str(FIXTURES_DIR / "test_video.mkv"), srt, tmp_path / "emb2.mkv")
    if mkv is None:
        pytest.skip("ffmpeg could not build the embedded-subtitle fixture")
    work = tmp_path / "work2"
    work.mkdir()
    out = rusa_subtitle.step_extract_subtitles(str(mkv), None, str(work))
    entries, count = rusa_subtitle.step_parse_srt(out, None, None)
    assert count == 2
    assert entries[0]["text"] == "Привет, это русские субтитры!"
