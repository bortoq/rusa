"""pytest fixtures for rusa tests."""
import os, sys, tempfile, struct, wave, json
from pathlib import Path
import pytest

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import rusa

# Paths
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
PROJECT_DIR = TESTS_DIR.parent


# ── Fixture generation ──────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")


def pytest_addoption(parser):
    parser.addoption("--generate-fixtures", action="store_true",
                     default=False, help="Generate test fixtures before running tests")


def pytest_sessionstart(session):
    """Auto-generate fixtures if missing or --generate-fixtures given."""
    generate = session.config.getoption("--generate-fixtures", default=False)
    if generate or not (FIXTURES_DIR / "test_video.mkv").exists():
        print("\nGenerating test fixtures (this may take a moment)...")
        from tests.generate_fixtures import main
        main()


# ── Helpers ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fixtures_ready():
    """Ensure fixtures exist."""
    assert (FIXTURES_DIR / "test_video.mkv").exists(), (
        "Run `python -m tests.generate_fixtures` first"
    )
    return FIXTURES_DIR


@pytest.fixture
def tmp_wav():
    """Create a temporary WAV with known duration."""
    path = tempfile.mktemp(suffix=".wav")
    yield path
    if os.path.isfile(path):
        os.unlink(path)


def make_sine_wav(path: str, duration_ms: int = 1000,
                  freq: int = 440, framerate: int = 48000) -> str:
    """Create a WAV file with a sine tone. Returns path."""
    nframes = int(duration_ms * framerate / 1000)
    bpf = 2 * 2  # 2 channels * 2 bytes
    data = b""
    import math
    for frame in range(nframes):
        t = frame / framerate
        val = int(16000 * math.sin(2 * 3.14159 * freq * t))
        data += struct.pack("<h", val)
        data += struct.pack("<h", val)  # right channel
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(data)))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 2, framerate,
                2 * 2 * framerate, 2 * 2, 2 * 8))
        f.write(b"data")
        f.write(struct.pack("<I", len(data)))
        f.write(data)
    return path


@pytest.fixture
def sample_entries():
    """Return a list of sample subtitle entries."""
    return [
        {"idx": 1, "start_ms": 0, "end_ms": 3000, "text": "First subtitle"},
        {"idx": 2, "start_ms": 4000, "end_ms": 7000, "text": "Second subtitle"},
        {"idx": 3, "start_ms": 8000, "end_ms": 12000, "text": "Third subtitle with more text"},
    ]


@pytest.fixture
def sample_wav_results(tmp_path, sample_entries):
    """Create WAV files for sample entries. Returns list of (idx, path, dur_ms)."""
    results = []
    for e in sample_entries:
        dur_ms = 1000  # 1 second each
        path = str(tmp_path / f"batch_{e['idx']:04d}.wav")
        make_sine_wav(path, dur_ms, freq=e["idx"] * 100)
        results.append((e["idx"], path, float(dur_ms)))
    return results


@pytest.fixture
def overlapping_entries():
    """Entries where TTS duration exceeds subtitle gaps (triggers overlap)."""
    return [
        {"idx": 1, "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"idx": 2, "start_ms": 500, "end_ms": 1500, "text": "B"},
        {"idx": 3, "start_ms": 1000, "end_ms": 2000, "text": "C"},
        {"idx": 4, "start_ms": 1500, "end_ms": 2500, "text": "D"},
        {"idx": 5, "start_ms": 2000, "end_ms": 3000, "text": "E"},
    ]


@pytest.fixture
def overlapping_wav_results(tmp_path, overlapping_entries):
    """Create WAV files for overlapping entries, each ~800ms (longer than 500ms gap)."""
    results = []
    for e in overlapping_entries:
        dur_ms = 800
        path = str(tmp_path / f"batch_{e['idx']:04d}.wav")
        make_sine_wav(path, dur_ms, freq=e["idx"] * 150)
        results.append((e["idx"], path, float(dur_ms)))
    return results


@pytest.fixture
def srt_content_en():
    """English SRT content for parsing tests."""
    return textwrap.dedent("""\
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


@pytest.fixture
def srt_path(tmp_path, srt_content_en):
    """Write SRT content to a temp file."""
    path = str(tmp_path / "test.srt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(srt_content_en)
    return path


import textwrap
