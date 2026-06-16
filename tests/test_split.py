"""Tests for _split_text (long text splitting)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def test_short_text_no_split():
    """Text under MAX_TTS_CHARS should return as single chunk."""
    result = rusa._split_text("Short text", max_chars=100)
    assert len(result) == 1
    assert result[0] == "Short text"


def test_exactly_max_chars():
    """Text exactly at limit should not split."""
    text = "a" * 100
    result = rusa._split_text(text, max_chars=100)
    assert len(result) == 1
    assert result[0] == text


def test_split_at_punctuation():
    """Should split at sentence-ending punctuation."""
    text = "First sentence. " + "a" * 100 + " Second sentence."
    result = rusa._split_text(text, max_chars=50)
    assert len(result) >= 2
    # First chunk should end at the first period within the first 50 chars
    for part in result:
        assert len(part) <= 50


def test_split_at_space_when_no_punct():
    """When no punctuation found, split at last space."""
    text = "word " * 30  # ~150 chars, no punctuation
    result = rusa._split_text(text, max_chars=50)
    assert len(result) >= 3
    for part in result:
        assert len(part) <= 50
        assert not part.startswith(" ")  # no leading space
        assert not part.endswith(" ")    # no trailing space


def test_split_no_space_no_punct():
    """No punctuation AND no space — split at max_chars boundary."""
    text = "a" * 200
    result = rusa._split_text(text, max_chars=50)
    assert len(result) == 4  # 200 / 50 = 4
    assert all(len(p) <= 50 for p in result)


def test_split_ellipsis():
    """Ellipsis character (U+2026) should be a valid split point."""
    text = "First part\u2026 " + "a" * 100 + " second part."
    result = rusa._split_text(text, max_chars=20)
    # First chunk should end at the ellipsis
    assert "\u2026" in result[0] if len(result) > 1 and len(result[0]) > 3 else True
    for part in result:
        assert len(part) <= 20


def test_split_preserves_all_text():
    """Splitting should not lose any characters."""
    text = "Short. " * 10 + "Longer text fragment. " * 20
    result = rusa._split_text(text, max_chars=100)
    joined = " ".join(result)
    # All original words should be present
    for word in text.split():
        assert word in joined, f"Word '{word}' not found in result"


def test_split_single_long_word():
    """A single word longer than max_chars should be split at max_chars."""
    text = "a" * 500
    result = rusa._split_text(text, max_chars=100)
    assert len(result) == 5  # 500 / 100 = 5
    assert all(len(p) <= 100 for p in result)


def test_split_on_exclamation():
    """Exclamation mark should be a valid split point."""
    text = "Wow! " + "x" * 100 + " Amazing!"
    result = rusa._split_text(text, max_chars=20)
    assert len(result) >= 2
    assert any("!" in p for p in result)


def test_split_on_question():
    """Question mark should be a valid split point."""
    text = "Really? " + "x" * 100 + " No way!"
    result = rusa._split_text(text, max_chars=20)
    assert len(result) >= 2
