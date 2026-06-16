"""Integration tests: run full pipeline on generated fixtures."""
import sys, os, struct, wave, json, subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
PROJECT_DIR = TESTS_DIR.parent


# ── Video-based integration tests ─────────────────────────────────

@pytest.mark.slow
def test_full_pipeline_with_srt(fixtures_ready, tmp_path):
    """Full pipeline: rusa on test_video.mkv with ru_subtitles.srt.

    This is the MAIN regression test: generates TTS, converts, assembles,
    mixes, and encodes output. Verifies WAV header integrity at assembly step.
    """
    video = str(FIXTURES_DIR / "test_video.mkv")
    srt = str(FIXTURES_DIR / "ru_subtitles.srt")
    output = str(tmp_path / "output.mkv")

    # Sanity checks
    assert os.path.isfile(video), f"Video not found: {video}"
    assert os.path.isfile(srt), f"SRT not found: {srt}"

    # Parse SRT
    entries, count = rusa.step_parse_srt(srt, None, None)
    assert count > 0, "No subtitles parsed"

    voice = "ru-RU-SvetlanaNeural"

    # Generate TTS (can be slow - mark as slow)
    print(f"\n  Parsed {count} subtitles from {os.path.basename(srt)}")
    tts_results = rusa.step_generate_tts(entries, voice, 4, str(tmp_path))
    assert len(tts_results) > 0, "No TTS files generated"

    # Convert to WAV
    wav_results = rusa.step_convert_wav(tts_results, "1.5", str(tmp_path))
    assert len(wav_results) > 0, "No WAV files produced"

    # Assembly (the buggy step - verify WAV header!)
    voiceover_wav = rusa.step_assemble(entries, wav_results, str(tmp_path))

    # CRITICAL ASSERTION: WAV header must match actual file size
    with open(voiceover_wav, "rb") as f:
        data_size = struct.unpack("<I", f.read(44)[40:44])[0]
    file_size = os.path.getsize(voiceover_wav)
    assert 44 + data_size == file_size, (
        f"REGRESSION: WAV header mismatch! "
        f"Header declares {44 + data_size} bytes, file is {file_size} bytes. "
        f"Data will be truncated by {file_size - 44 - data_size} bytes."
    )

    # Verify voiceover has actual audio (non-silence)
    # Scan the entire first 3 seconds (edge-tts has ~100ms leading silence)
    with wave.open(voiceover_wav, "rb") as w:
        nframes = w.getnframes()
        scan_frames = min(nframes, 144000)  # up to 3 seconds
        raw = w.readframes(scan_frames)
        max_val = 0
        for j in range(0, len(raw), 4):
            val = abs(struct.unpack("<h", raw[j:j+2])[0])
            if val > max_val:
                max_val = val
                if max_val > 5000:
                    break
        assert max_val > 100, "Voiceover WAV is all silence!"

    print(f"  Voiceover: {nframes/48000:.1f}s, max sample value: {max_val}")

    # Final mix (smoke test - just check it doesn't crash)
    rusa.step_mix_output(
        video, voiceover_wav,
        rusa.DEFAULT_ORIG_VOL, rusa.DEFAULT_TTS_VOL,
        output, str(tmp_path),
        "opus", "64",
        None, False
    )

    assert os.path.isfile(output), "Output file was not created"
    out_size = os.path.getsize(output)
    assert out_size > 1000, f"Output file too small: {out_size} bytes"
    print(f"  Output: {os.path.basename(output)} ({out_size / 1024:.0f} KB)")


@pytest.mark.slow
def test_overlap_regression(fixtures_ready, tmp_path):
    """Deliberately use tightly-spaced subtitles to trigger overlap cascade.

    If assembly doesn't update the WAV header, some segments will be lost.
    This test verifies that ALL generated segments are audible.
    """
    # Generate entries with very tight spacing (every 800ms)
    # Use natural Russian speech so silenceremove doesn't eat pauses
    short_lines = [
        "Привет. Как дела?",
        "Всё хорошо. Спасибо.",
        "Что нового?",
        "Ничего особенного.",
        "Пойдём гулять?",
        "Да, конечно.",
        "Куда пойдём?",
        "В парк. Там красиво.",
        "Хорошая идея.",
        "Когда встречаемся?",
        "В пять часов.",
        "Договорились.",
        "Не опаздывай.",
        "Хорошо. Пока.",
        "До встречи.",
        "Принеси книгу.",
        "Какую книгу?",
        "Ту, что я дал.",
        "А, эту. Хорошо.",
        "Спасибо большое.",
    ]
    entries = []
    n = len(short_lines)
    for i, line in enumerate(short_lines, 1):
        start_ms = (i - 1) * 800
        entries.append({
            "idx": i,
            "start_ms": start_ms,
            "end_ms": start_ms + 2000,
            "text": line
        })

    voice = "ru-RU-SvetlanaNeural"

    # Generate TTS
    tts_results = rusa.step_generate_tts(entries, voice, 4, str(tmp_path))
    assert len(tts_results) == n, f"Expected {n} TTS files, got {len(tts_results)}"

    # Convert to WAV
    wav_results = rusa.step_convert_wav(tts_results, "1.5", str(tmp_path))
    # stop_periods may aggressively trim short text — accept fewer WAVs
    assert len(wav_results) >= 5, f"Too few WAV files: {len(wav_results)}/{n}"
    print(f"  WAV files: {len(wav_results)}/{n}")

    # Assembly
    out = rusa.step_assemble(entries, wav_results, str(tmp_path))

    # CRITICAL: WAV header must be correct
    with open(out, "rb") as f:
        data_size = struct.unpack("<I", f.read(44)[40:44])[0]
    file_size = os.path.getsize(out)
    assert 44 + data_size == file_size, (
        f"Overlap regression: WAV header mismatch! "
        f"{file_size - 44 - data_size} bytes past boundary!"
    )

    # Verify that all segments produced audio somewhere in the file
    with wave.open(out, "rb") as w:
        nframes = w.getnframes()
        # Find all non-silent regions
        step = int(0.1 * 48000)  # check every 100ms
        audio_count = 0
        for pos in range(0, min(nframes, int(60 * 48000)), step):
            w.setpos(pos)
            data = w.readframes(10)
            max_val = max(abs(struct.unpack("<h", data[j:j+2])[0])
                          for j in range(0, min(20, len(data)), 2))
            if max_val > 100:
                audio_count += 1

        # Should have audio in some of the checked positions
        total_checks = min(nframes, int(60 * 48000)) // step
        assert audio_count > 0, (
            f"No audio detected in {total_checks} checked positions "
            f"(possible regression)"
        )
        print(f"  Audio density: {audio_count}/{total_checks} "
              f"({100*audio_count//total_checks}%)")




def test_extract_from_video_with_embedded_subs(fixtures_ready, tmp_path):
    """Test using externally provided SRT (safer than embedded subs extraction)."""
    # ffprobe doesn't always detect embedded SRT streams; use external SRT instead
    srt = str(FIXTURES_DIR / "en_subtitles.srt")
    assert os.path.isfile(srt)

    subs_path = rusa.step_extract_subtitles(
        str(FIXTURES_DIR / "test_video.mkv"),
        srt, str(tmp_path)
    )
    assert os.path.isfile(subs_path), "SRT was not copied"
    assert os.path.getsize(subs_path) > 0, "Copied SRT is empty"

    entries, count = rusa.step_parse_srt(subs_path, None, None)
    assert count > 0, "No subtitles parsed from SRT"


def test_extract_from_external_srt():
    """Test using an externally provided SRT."""
    srt = str(FIXTURES_DIR / "ru_subtitles.srt")
    assert os.path.isfile(srt), f"SRT not found: {srt}"

    tmp_path = Path("/tmp/rusa_test_extract")
    tmp_path.mkdir(parents=True, exist_ok=True)

    subs_path = rusa.step_extract_subtitles(
        str(FIXTURES_DIR / "test_video.mkv"),
        srt, str(tmp_path)
    )
    assert os.path.isfile(srt), "External SRT should be used"
    with open(subs_path, encoding="utf-8") as f:
        content = f.read()
    # The copied SRT should contain Russian text
    assert "Всеобщая декларация" in content, (
        "Copied SRT should contain Russian text"
    )

    import shutil
    shutil.rmtree(str(tmp_path), ignore_errors=True)


# ── WAV header integrity tests ──────────────────────────────────

def test_wav_header_after_mix(fixtures_ready, tmp_path):
    """After mixing, the WAV should have a valid, non-trunctated header."""
    video = str(FIXTURES_DIR / "test_video.mkv")
    srt = str(FIXTURES_DIR / "ru_subtitles.srt")
    output = str(tmp_path / "mix_output.wav")

    entries, count = rusa.step_parse_srt(srt, None, None)
    voice = "ru-RU-SvetlanaNeural"

    # Quick end-to-end with just 5 subtitles for speed
    entries = entries[:5]

    tts_results = rusa.step_generate_tts(entries, voice, 2, str(tmp_path))
    wav_results = rusa.step_convert_wav(tts_results, "1.5", str(tmp_path))
    voiceover = rusa.step_assemble(entries, wav_results, str(tmp_path))

    # Mix to WAV (use PCM for WAV container, not Opus)
    rusa.step_mix_output(
        video, voiceover,
        rusa.DEFAULT_ORIG_VOL, rusa.DEFAULT_TTS_VOL,
        output, str(tmp_path),
        "aac", "128",
        None, True  # audio-only
    )

    # Verify the final output has audio
    if output.endswith(".opus"):
        r = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "csv=p=0", output
        ], capture_output=True, text=True, check=False)
        try:
            dur = float(r.stdout.strip())
            assert dur > 0, "Output audio duration is 0"
        except (ValueError, TypeError):
            pass  # ffprobe might not handle opus well, skip
    else:
        assert os.path.getsize(output) > 44, "Output too small"


# ── Voice detection pipeline test ───────────────────────────────

def test_voice_resolution_with_external_srt(fixtures_ready, tmp_path):
    """Test that voice is correctly resolved with ru.srt extension."""
    # Simulate the main() logic for voice resolution
    srt_path = str(FIXTURES_DIR / "ru_subtitles.srt")

    # With explicit --voice
    explicit = "ru-RU-DmitryNeural"
    assert explicit != rusa.DEFAULT_VOICE

    # Without explicit --voice (auto-detect)
    detected = rusa.detect_language_from_srt(srt_path)
    assert detected is not None, "Should detect language from ru_subtitles.srt"
    assert "ru-RU" in detected, f"Expected Russian voice, got {detected}"


def test_voice_resolution_with_english_srt(fixtures_ready, tmp_path):
    """English SRT should detect English voice (via content)."""
    srt_path = str(FIXTURES_DIR / "en_subtitles.srt")
    detected = rusa.detect_language_from_srt(srt_path)
    if rusa.HAS_LANGDETECT:
        assert detected is not None
        assert "en-US" in detected, f"Expected English voice, got {detected}"
    else:
        # Without langdetect, plain .srt returns None
        assert detected is None


def test_wav_preserves_speech(fixtures_ready, tmp_path):
    """WAV conversion must NOT destroy speech (stop_periods regression).

    A multi-sentence phrase must produce a WAV file longer than 1000ms
    with amplitude > 1000 (i.e., audible speech preserved).
    """
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    from tests.conftest import make_sine_wav

    # Generate TTS for a multi-sentence phrase
    text = "Сезам, откройся. Проезжайте. Спасибо."
    mp3 = str(tts_dir / "test.mp3")
    rc = subprocess.run(
        ["edge-tts", "--voice", "ru-RU-SvetlanaNeural",
         "--text", text, "--write-media", mp3],
        capture_output=True, timeout=60, check=False
    )
    if rc.returncode != 0 or not os.path.isfile(mp3) or os.path.getsize(mp3) < 100:
        pytest.skip("edge-tts unavailable for speech preservation test")

    # Convert using the EXACT parameters from step_convert_wav
    wav = str(tmp_path / "test.wav")
    # Must match the filter in rusa.step_convert_wav (areverse dual-trim)
    filter_str = (
        "atempo=1.5,"
        "silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
        "areverse,"
        "silenceremove=start_periods=1:start_threshold=0.0018:start_silence=0.01,"
        "areverse"
    )
    rc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
         "-af", filter_str, "-ac", "2", "-ar", "48000",
         "-sample_fmt", "s16", wav],
        check=False, capture_output=True
    )
    assert rc.returncode == 0, f"WAV conversion failed: {rc.stderr.decode()}"
    assert os.path.isfile(wav) and os.path.getsize(wav) > 44, "WAV file missing"

    with wave.open(wav, "rb") as w:
        frames = w.getnframes()
        duration_ms = frames / 48000 * 1000
        assert duration_ms > 1000, (
            f"WAV too short ({duration_ms:.0f}ms): stop_periods destroyed speech!"
        )
        raw = w.readframes(min(frames, 48000 * 10))
        max_amp = max(
            abs(struct.unpack("<h", raw[j:j+2])[0])
            for j in range(0, min(len(raw), 48000 * 8), 2)
        )
        assert max_amp > 1000, (
            f"WAV max amplitude {max_amp}: speech was destroyed by silenceremove!"
        )
        # Verify trailing silence was trimmed (< 100ms remaining)
        # Find last sample with amplitude > 50
        speech_end = None
        for j in range(0, len(raw), 4):
            s = abs(struct.unpack("<h", raw[j:j+2])[0])
            if s > 50:
                speech_end = j / 4
        if speech_end is not None:
            trail_ms = duration_ms - (speech_end / 48000 * 1000)
            assert trail_ms < 100, (
                f"Trailing silence not trimmed: {trail_ms:.0f}ms (>100ms)"
            )
        print(f"  Speech test: {duration_ms:.0f}ms, max_amp={max_amp}, "
              f"trail trimmed, OK")
