"""Tests for language detection (detect_language_from_srt)."""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def test_detect_by_extension_ru():
    """File named .ru.srt should detect Russian."""
    p = Path("/tmp/test_detect.ru.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\nПривет\n", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result == "ru-RU-SvetlanaNeural", f"Expected ru-RU-SvetlanaNeural, got {result}"
    p.unlink()


def test_detect_by_extension_en():
    """File named .en.srt should detect English."""
    p = Path("/tmp/test_detect.en.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result == "en-US-AriaNeural", f"Expected en-US-AriaNeural, got {result}"
    p.unlink()


def test_detect_by_extension_de():
    """File named .de.srt should detect German."""
    p = Path("/tmp/test_detect.de.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result == "de-DE-KatjaNeural", f"Expected de-DE-KatjaNeural, got {result}"
    p.unlink()


def test_detect_by_extension_fr():
    """File named .fr.srt should detect French."""
    p = Path("/tmp/test_detect.fr.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\nBonjour\n", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result == "fr-FR-DeniseNeural"
    p.unlink()


def test_detect_plain_srt_russian_text():
    """Plain .srt with Russian text should detect Russian via langdetect."""
    p = Path("/tmp/test_detect_ru.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\n"
                 "Это русский текст для проверки определения языка\n",
                 encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    if rusa.HAS_LANGDETECT:
        assert result == "ru-RU-SvetlanaNeural", f"Expected ru, got {result}"
    else:
        assert result is None  # no langdetect, returns None
    p.unlink()


def test_detect_plain_srt_english_text():
    """Plain .srt with English text should detect English via langdetect."""
    p = Path("/tmp/test_detect_en.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\n"
                 "This is English text for language detection testing\n",
                 encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    if rusa.HAS_LANGDETECT:
        assert result == "en-US-AriaNeural", f"Expected en, got {result}"
    else:
        assert result is None
    p.unlink()


def test_detect_plain_srt_german_text():
    """Plain .srt with German text should detect German via langdetect."""
    p = Path("/tmp/test_detect_de.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\n"
                 "Dies ist ein deutscher Text zur Sprachprüfung\n",
                 encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    if rusa.HAS_LANGDETECT:
        assert result == "de-DE-KatjaNeural", f"Expected de, got {result}"
    else:
        assert result is None
    p.unlink()


def test_detect_empty_file():
    """Empty SRT should return None."""
    p = Path("/tmp/test_detect_empty.srt")
    p.write_text("", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result is None
    p.unlink()


def test_detect_too_short_text():
    """Very short text (< 20 chars) should return None."""
    p = Path("/tmp/test_detect_short.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    if rusa.HAS_LANGDETECT:
        assert result is None  # too short for langdetect
    p.unlink()


def test_detect_ru_dot_srt_overrides_content():
    """Extension should take priority over content detection."""
    # File is .ru.srt but contains English text -> should detect Russian
    p = Path("/tmp/test_override.ru.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\n"
                 "This is English but extension says Russian\n",
                 encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    assert result == "ru-RU-SvetlanaNeural"  # extension wins
    p.unlink()


def test_detect_unknown_extension():
    """Unknown language extension should fall back to content (needs 20+ chars)."""
    p = Path("/tmp/test_detect.xx.srt")
    p.write_text("1\n00:00:01,000 --> 00:00:02,000\n"
                 "This is a longer English text for language detection testing sufficient length\n",
                 encoding="utf-8")
    result = rusa.detect_language_from_srt(str(p))
    if rusa.HAS_LANGDETECT:
        assert result == "en-US-AriaNeural", f"Expected en, got {result}"
    else:
        assert result is None
    p.unlink()
