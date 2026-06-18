"""Tests for SRT parsing (step_parse_srt)."""
import sys, os, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa


def test_parse_basic():
    """Parse a simple 3-entry SRT."""
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:04,000
        Hello world

        2
        00:00:05,500 --> 00:00:08,000
        This is a test subtitle

        3
        00:00:10,000 --> 00:00:15,500
        Third and final line
    """)
    p = Path("/tmp/test_basic.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 3, f"Expected 3, got {count}"
    assert entries[0]["idx"] == 1
    assert entries[0]["start_ms"] == 1000
    assert entries[0]["end_ms"] == 4000
    assert entries[0]["text"] == "Hello world"
    assert entries[1]["text"] == "This is a test subtitle"
    assert entries[2]["text"] == "Third and final line"
    p.unlink()


def test_parse_with_bom():
    """SRT with BOM should parse correctly."""
    content = "\ufeff1\n00:00:01,000 --> 00:00:04,000\nBOM test\n"
    p = Path("/tmp/test_bom.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 1
    assert entries[0]["text"] == "BOM test"
    p.unlink()


def test_parse_with_range():
    """--from and --to should filter entries."""
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:04,000
        First

        2
        00:00:05,000 --> 00:00:08,000
        Second

        3
        00:00:09,000 --> 00:00:12,000
        Third
    """)
    p = Path("/tmp/test_range.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), 2, 3)
    assert count == 2
    assert entries[0]["idx"] == 1  # reindexed
    assert entries[0]["text"] == "Second"
    assert entries[1]["text"] == "Third"
    p.unlink()


def test_parse_multi_line_text():
    """SRT entries with multi-line text should join properly."""
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:05,000
        Line one
        Line two
        Line three
    """)
    p = Path("/tmp/test_multiline.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 1
    assert entries[0]["text"] == "Line one Line two Line three"  # joined with spaces
    p.unlink()


def test_parse_with_formatting():
    """HTML tags in SRT should be stripped during parsing so TTS engines get clean text."""
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:04,000
        <i>Italic text</i> and <b>bold</b>
    """)
    p = Path("/tmp/test_format.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 1
    assert entries[0]["text"] == "Italic text and bold"
    assert "<i>" not in entries[0]["text"]
    assert "<b>" not in entries[0]["text"]
    p.unlink()


def test_parse_with_html_escaped_tags():
    """HTML-escaped tags like &lt;i&gt; should be decoded and stripped."""
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:04,000
        &lt;i&gt;Italic text&lt;/i&gt; and &lt;b&gt;bold&lt;/b&gt;
    """)
    p = Path("/tmp/test_escaped_format.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 1
    assert entries[0]["text"] == "Italic text and bold"
    assert "<i>" not in entries[0]["text"]
    assert "<b>" not in entries[0]["text"]
    assert "&lt;" not in entries[0]["text"]
    p.unlink()


def test_parse_dot_as_decimal_separator():
    """Some SRTs use dot instead of comma in timestamps."""
    content = textwrap.dedent("""\
        1
        00:00:01.000 --> 00:00:04.000
        Using dots
    """)
    p = Path("/tmp/test_dot.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 1
    assert entries[0]["start_ms"] == 1000
    p.unlink()


def test_parse_empty_file():
    """Empty SRT should return empty list (zero count)."""
    p = Path("/tmp/test_empty.srt")
    p.write_text("", encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 0
    assert len(entries) == 0
    p.unlink()


def test_parse_malformed_index():
    """Non-integer index should skip the block."""
    content = textwrap.dedent("""\
        abc
        00:00:01,000 --> 00:00:04,000
        Invalid index
    """)
    p = Path("/tmp/test_bad_idx.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 0
    p.unlink()


def test_parse_malformed_timing():
    """Invalid timing line should skip the block."""
    content = textwrap.dedent("""\
        1
        not a timestamp
        Some text
    """)
    p = Path("/tmp/test_bad_time.srt")
    p.write_text(content, encoding="utf-8")
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 0
    p.unlink()


def test_parse_normalizes_indices_with_range():
    """After range filtering, indices should be normalized (1-based)."""
    content = textwrap.dedent("""\
        10
        00:00:01,000 --> 00:00:04,000
        Tenth

        20
        00:00:05,000 --> 00:00:08,000
        Twentieth
    """)
    p = Path("/tmp/test_normalize_idx.srt")
    p.write_text(content, encoding="utf-8")
    # Without range: original indices preserved
    entries, count = rusa.step_parse_srt(str(p), None, None)
    assert count == 2
    assert entries[0]["idx"] == 10  # original idx
    assert entries[1]["idx"] == 20
    # With range: indices are reindexed
    entries2, count2 = rusa.step_parse_srt(str(p), 10, 20)
    assert count2 == 2
    assert entries2[0]["idx"] == 1  # reindexed
    assert entries2[1]["idx"] == 2
    p.unlink()
