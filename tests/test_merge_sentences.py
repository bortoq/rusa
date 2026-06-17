"""Tests for step_merge_srt_entries — merging split sentences."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa_subtitle


def test_merge_split_sentence():
    """Two entries that form one sentence should be merged."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "Ну, Каретка, ты как и я рада пойти"},
        {"idx": 2, "start_ms": 2001, "end_ms": 4000, "text": "на конвенцию Скакунавтов?"},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 1
    assert result[0]["text"] == "Ну, Каретка, ты как и я рада пойти на конвенцию Скакунавтов?"
    assert result[0]["start_ms"] == 0
    assert result[0]["end_ms"] == 4000
    assert result[0]["idx"] == 1


def test_merge_three_parts():
    """Three consecutive entries forming one sentence should merge into one."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Когда я"},
        {"idx": 2, "start_ms": 1001, "end_ms": 2000, "text": "пошёл в магазин"},
        {"idx": 3, "start_ms": 2001, "end_ms": 3000, "text": "я встретил друга."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 1
    assert result[0]["text"] == "Когда я пошёл в магазин я встретил друга."
    assert result[0]["start_ms"] == 0
    assert result[0]["end_ms"] == 3000


def test_no_merge_complete_sentences():
    """Separate complete sentences should NOT be merged."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 2000, "text": "Это первое предложение."},
        {"idx": 2, "start_ms": 2500, "end_ms": 4000, "text": "А это второе."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 2
    assert result[0]["text"] == "Это первое предложение."
    assert result[1]["text"] == "А это второе."


def test_no_merge_large_gap():
    """Large gap between entries should prevent merging even if no punctuation."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Первая часть"},
        {"idx": 2, "start_ms": 5000, "end_ms": 6000, "text": "Далеко во времени"},  # uppercase D
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries, max_gap_ms=200)
    assert len(result) == 2


def test_merge_lowercase_continuation():
    """Next entry starting lowercase triggers merge even with moderate gap."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Он сказал,"},
        {"idx": 2, "start_ms": 1100, "end_ms": 2000, "text": "что придёт завтра."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 1
    assert "что придёт завтра" in result[0]["text"]


def test_merge_preserves_other_entries():
    """Merge should not affect entries before or after the merged pair."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Привет."},
        {"idx": 2, "start_ms": 1500, "end_ms": 2500, "text": "Как дела?"},
        {"idx": 3, "start_ms": 2600, "end_ms": 3500, "text": "Всё"},
        {"idx": 4, "start_ms": 3600, "end_ms": 4000, "text": "хорошо."},
        {"idx": 5, "start_ms": 4500, "end_ms": 5000, "text": "Пока!"},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 4  # entries 3+4 merged, others stay
    assert result[0]["text"] == "Привет."
    assert result[1]["text"] == "Как дела?"
    assert result[2]["text"] == "Всё хорошо."
    assert result[3]["text"] == "Пока!"
    # Indices are sequential
    assert [e["idx"] for e in result] == [1, 2, 3, 4]


def test_merge_empty_input():
    """Empty input should return empty list."""
    assert rusa_subtitle.step_merge_srt_entries([]) == []


def test_merge_single_entry():
    """Single entry should remain unchanged."""
    entries = [{"idx": 5, "start_ms": 1000, "end_ms": 2000, "text": "Одинокая реплика."}]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 1
    assert result[0]["text"] == "Одинокая реплика."
    assert result[0]["idx"] == 1  # re-indexed


def test_merge_question_mark_ends():
    """Sentence ending with ? should NOT merge with next."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Ты придёшь?"},
        {"idx": 2, "start_ms": 1500, "end_ms": 2500, "text": "Да, конечно."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 2


def test_merge_exclamation_ends():
    """Sentence ending with ! should NOT merge with next."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Вперёд!"},
        {"idx": 2, "start_ms": 1500, "end_ms": 2500, "text": "Мы победим."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 2


def test_merge_ellipsis_ends():
    """Sentence ending with … should NOT merge (it's a pause, not continuation)."""
    entries = [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "Ну…"},
        {"idx": 2, "start_ms": 1500, "end_ms": 2500, "text": "не знаю."},
    ]
    result = rusa_subtitle.step_merge_srt_entries(entries)
    assert len(result) == 2
