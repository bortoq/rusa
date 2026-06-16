#!/usr/bin/env python3
"""Generate deterministic offline fixtures for regression testing."""
import os, subprocess
from pathlib import Path

TESTS_DIR = Path(__file__).parent
PROJECT_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"

# Public domain text: UDHR preamble + article 1
EN_TEXT = """The Universal Declaration of Human Rights is a milestone document in the history of human rights.
Drafted by representatives with different legal and cultural backgrounds from all regions of the world,
the declaration was proclaimed by the United Nations General Assembly in Paris on ten December nineteen forty eight.
It sets out for the first time fundamental human rights to be universally protected.
All human beings are born free and equal in dignity and rights.
They are endowed with reason and conscience and should act towards one another in a spirit of brotherhood.
Everyone has the right to life, liberty and security of person.
No one shall be held in slavery or servitude.
Everyone has the right to freedom of thought, conscience and religion.
Everyone has the right to freedom of opinion and expression."""

RU_TEXT = """Всеобщая декларация прав человека является знаковым документом в истории прав человека.
Разработанная представителями разных правовых и культурных традиций со всего мира,
декларация была провозглашена Генеральной Ассамблеей ООН в Париже десятого декабря тысяча девятьсот сорок восьмого года.
Она впервые устанавливает основные права человека, которые должны быть защищены во всём мире.
Все люди рождаются свободными и равными в своём достоинстве и правах.
Они наделены разумом и совестью и должны поступать по отношению друг к другу в духе братства.
Каждый имеет право на жизнь, свободу и личную неприкосновенность.
Никто не должен содержаться в рабстве или подневольном состоянии.
Каждый имеет право на свободу мысли, совести и религии.
Каждый имеет право на свободу убеждений и на свободное их выражение."""

EN_LINES = [l.strip() for l in EN_TEXT.strip().split("\n") if l.strip()]
RU_LINES = [l.strip() for l in RU_TEXT.strip().split("\n") if l.strip()]

assert len(EN_LINES) == len(RU_LINES), "EN and RU must have same number of lines"

def generate_audio(text: str, output_path: str, freq: int) -> None:
    """Generate deterministic offline audio without network TTS."""
    print(f"  Generating {output_path} (offline tone {freq}Hz)...")
    dur_s = max(len(text) / 55.0, 12.0)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur_s}",
            "-ac", "1", "-ar", "16000",
            "-c:a", "mp3",
            output_path,
        ],
        check=True,
        capture_output=True,
    )

def create_srt(lines: list[str], audio_duration_s: float, output_path: str,
               lang: str = "en") -> None:
    """Create SRT from lines, distributed evenly over audio duration."""
    n = len(lines)
    sec_per_line = audio_duration_s / n
    with open(output_path, "w", encoding="utf-8") as f:
        for i, line in enumerate(lines):
            start_s = i * sec_per_line
            end_s = (i + 1) * sec_per_line
            # SRT format: HH:MM:SS,mmm
            def to_srt(sec):
                h = int(sec // 3600)
                m = int((sec % 3600) // 60)
                s = int(sec % 60)
                ms = int((sec - int(sec)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i+1}\n{to_srt(start_s)} --> {to_srt(end_s)}\n{line}\n\n")

def get_audio_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=False
    )
    try:
        return float(r.stdout.strip())
    except (ValueError, TypeError):
        return 0.0

def main():
    os.makedirs(FIXTURES_DIR, exist_ok=True)

    print("=== Generating test fixtures ===")

    # 1. Generate English audio (original track)
    en_audio = str(FIXTURES_DIR / "en_audio.mp3")
    en_full_text = " ".join(EN_LINES)
    generate_audio(en_full_text, en_audio, 440)
    en_duration = get_audio_duration(en_audio)
    print(f"  English audio duration: {en_duration:.1f}s")

    # 2. Generate Russian audio (voiceover reference)
    ru_audio = str(FIXTURES_DIR / "ru_audio.mp3")
    ru_full_text = " ".join(RU_LINES)
    generate_audio(ru_full_text, ru_audio, 660)
    ru_duration = get_audio_duration(ru_audio)
    print(f"  Russian audio duration: {ru_duration:.1f}s")

    # 3. Create SRT files
    duration_for_srt = max(en_duration, ru_duration)
    en_srt = str(FIXTURES_DIR / "en_subtitles.srt")
    ru_srt = str(FIXTURES_DIR / "ru_subtitles.srt")
    ru_srt_en_name = str(FIXTURES_DIR / "en.ru_subtitles.srt")  # language-tagged
    create_srt(EN_LINES, duration_for_srt, en_srt, "en")
    create_srt(RU_LINES, duration_for_srt, ru_srt, "ru")
    # Also create .ru.srt variant for filename-based detection
    create_srt(RU_LINES, duration_for_srt, ru_srt_en_name, "ru")

    print(f"  SRT created: {os.path.basename(en_srt)}, {os.path.basename(ru_srt)}")

    # 4. Create test video (black screen + English audio)
    # Pad English audio with silence to make a round duration
    target_duration = max(duration_for_srt + 5, 30)
    video_path = str(FIXTURES_DIR / "test_video.mkv")

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s=640x480:r=24:d={target_duration}",
        "-i", en_audio,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "copy",
        "-shortest",
        video_path
    ], check=True, capture_output=True)
    print(f"  Video: {os.path.basename(video_path)} ({target_duration:.0f}s)")

    # Also create a version with embedded English SRT for extraction tests
    video_with_subs = str(FIXTURES_DIR / "test_video_subs.mkv")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-i", en_srt,
        "-c", "copy",
        "-c:s", "srt",
        "-map", "0",
        "-map", "1",
        video_with_subs
    ], check=True, capture_output=True)
    print(f"  Video with subs: {os.path.basename(video_with_subs)}")

    print("\n=== Fixtures generated ===")
    print(f"  Directory: {FIXTURES_DIR}")
    for f in sorted(FIXTURES_DIR.iterdir()):
        print(f"  {f.name} ({f.stat().st_size / 1024:.0f} KB)")

if __name__ == "__main__":
    main()
