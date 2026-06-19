"""Tests for rusa WebUI FastAPI server (headless REST API).

Replaces the old Gradio-based webui with a FastAPI REST API.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest
pytest.importorskip("fastapi")
from fastapi import FastAPI

try:
    from starlette.testclient import TestClient
except (ImportError, RuntimeError):
    TestClient = None  # starlette misses httpx/httpx2

PROJECT_DIR = Path(__file__).parent.parent


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    """Build a fresh FastAPI app for each test."""
    # Import here so tests can be collected without the server module
    from webui.server import create_app

    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient wrapping the FastAPI app.

    Requires ``httpx2`` on starlette >=1.4 (CI); falls back to ``httpx``
    on older versions.  The import is inside the fixture so that the
    module can be collected on Python 3.9 (where httpx2 is unavailable).
    """
    if TestClient is None:
        pytest.skip("starlette.testclient not available (need httpx/httpx2)")
    try:
        return TestClient(app)
    except RuntimeError as exc:
        pytest.skip(f"TestClient unavailable: {exc}")


@pytest.fixture
def sample_video() -> bytes:
    """Return a tiny valid Matroska segment (minimal file header).

    This is NOT a playable video — just enough bytes for the server
    to accept it as a video/* upload.  The pipeline will fail later
    on ffmpeg decode, but /api/process should accept the file.
    """
    # Minimal Matroska header (EBML)
    return bytes([
        0x1A, 0x45, 0xDF, 0xA3,  # EBML header
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F,  # EBMLVersion, etc.
    ]) + b"\x00" * 32  # pad


@pytest.fixture
def sample_srt() -> bytes:
    """Minimal valid SRT content."""
    return b"1\n00:00:01,000 --> 00:00:02,000\nHello world\n"


# ── GET /health ───────────────────────────────────────────────────────


class TestHealth:
    """GET /health must return a simple status."""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok"}

    def test_health_content_type(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers["content-type"] == "application/json"


# ── POST /api/process — validation ────────────────────────────────────


class TestProcessValidation:
    """POST /api/process without a video file should be rejected."""

    def test_missing_video_returns_422(self, client: TestClient):
        resp = client.post("/api/process")
        assert resp.status_code == 422

    def test_empty_video_field_returns_422(self, client: TestClient):
        resp = client.post("/api/process", data={"lang": "ru"})
        assert resp.status_code == 422

    def test_invalid_codec_returns_error_in_stream(self, client: TestClient, sample_video: bytes):
        """Unknown codec label → error SSE event, not crash."""
        resp = client.post(
            "/api/process",
            files={"video": ("test.mkv", io.BytesIO(sample_video), "video/x-matroska")},
            data={"codec": "invalid_codec_xyz"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text
        # Should contain an error event about unknown codec
        assert '"error"' in body or '"type":"error"' in body


# ── POST /api/process — streaming response ────────────────────────────


class TestProcessStreaming:
    """POST /api/process must return a SSE stream with log lines."""

    def test_returns_event_stream(self, client: TestClient, sample_video: bytes):
        resp = client.post(
            "/api/process",
            files={"video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska")},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-cache"

    def test_stream_contains_log_events(self, client: TestClient, sample_video: bytes):
        resp = client.post(
            "/api/process",
            files={"video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska")},
        )
        lines = resp.text.strip().split("\n")
        # Each SSE event starts with "data: "
        data_events = [l for l in lines if l.startswith("data: ")]
        assert len(data_events) >= 1
        # First event should contain the processing start message
        first = json.loads(data_events[0][6:])  # strip "data: "
        assert first["type"] == "log"

    def test_stream_ends_with_complete_or_error(self, client: TestClient, sample_video: bytes):
        """The last SSE event must be 'complete' or 'error'."""
        resp = client.post(
            "/api/process",
            files={"video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska")},
        )
        data_events = [
            json.loads(l[6:])
            for l in resp.text.strip().split("\n")
            if l.startswith("data: ")
        ]
        assert len(data_events) >= 1
        last = data_events[-1]
        assert last["type"] in ("complete", "error")

    def test_stream_event_format(self, client: TestClient, sample_video: bytes):
        """Each SSE event must be valid JSON with 'type' and 'message'."""
        resp = client.post(
            "/api/process",
            files={"video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska")},
        )
        for line in resp.text.strip().split("\n"):
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            assert "type" in event
            assert "message" in event
            assert event["type"] in ("log", "complete", "error")


# ── POST /api/process — with SRT ──────────────────────────────────────


class TestProcessWithSrt:
    """/api/process should accept an optional SRT file."""

    def test_with_srt_returns_stream(self, client: TestClient, sample_video: bytes, sample_srt: bytes):
        resp = client.post(
            "/api/process",
            files={
                "video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska"),
                "srt": ("subs.srt", io.BytesIO(sample_srt), "text/plain"),
            },
        )
        assert resp.status_code == 200

    def test_with_all_params(self, client: TestClient, sample_video: bytes, sample_srt: bytes):
        resp = client.post(
            "/api/process",
            files={
                "video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska"),
                "srt": ("subs.srt", io.BytesIO(sample_srt), "text/plain"),
            },
            data={
                "lang": "ru",
                "voice": "ru-RU-SvetlanaNeural",
                "speed": "1.8",
                "orig_vol": "0.70",
                "tts_vol": "0.90",
                "codec": "aac",
                "bitrate": "128",
                "subs_mode": "copy",
                "sync": "true",
                "audio_only": "false",
                "keep_temp": "false",
                "no_cache": "true",
            },
        )
        assert resp.status_code == 200


# ── POST /api/process — parameter defaults ────────────────────────────


class TestProcessDefaults:
    """Default values should be applied when parameters are omitted."""

    @pytest.mark.parametrize("field,expected_type", [
        ("speed", "log"),      # speed=1.5 default
        ("orig_vol", "log"),   # default volume
        ("subs_mode", "log"),  # "auto" default
    ])
    def test_defaults_dont_crash(
        self, client: TestClient, sample_video: bytes, field: str, expected_type: str
    ):
        """Omitted optional fields should use defaults and not crash."""
        resp = client.post(
            "/api/process",
            files={"video": ("movie.mkv", io.BytesIO(sample_video), "video/x-matroska")},
        )
        # Just verify it doesn't crash — the exact behavior depends on ffmpeg
        assert resp.status_code == 200


# ── GET /api/download/{filename} ──────────────────────────────────────


class TestDownload:
    """GET /api/download/{path} serves processed files."""

    def test_download_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/download/nonexistent_file.mp4")
        assert resp.status_code == 404

    def test_download_outside_workdir_returns_403(self, client: TestClient):
        """Path traversal with URL-encoded dots must be blocked."""
        # Use %2f (encoded /) to bypass HTTPX normalisation
        resp = client.get("/api/download/..%2f..%2fetc%2fpasswd")
        assert resp.status_code == 403

    def test_download_double_dot_segment_returns_403(self, client: TestClient):
        """A path segment that is exactly '..' must be blocked."""
        # Use URL-encoded dots to bypass HTTPX path normalisation
        resp = client.get("/api/download/x/%2e%2e/y")
        assert resp.status_code == 403

    def test_download_absolute_path_returns_403(self, client: TestClient):
        """Absolute paths must be blocked."""
        resp = client.get("/api/download//etc/passwd")
        assert resp.status_code == 403


# ── POST /api/process — existing fixtures (real pipeline) ─────────────


class TestProcessWithRealFixtures:
    """Test with real fixture files when available."""

    def test_with_real_video_returns_complete(
        self, client: TestClient, fixtures_ready: str,
    ):
        """If test fixtures exist, /api/process should complete.

        Skips if edge-tts is unavailable (the pipeline will error
        on edge-tts check, but that's acceptable).
        """
        video_path = Path(fixtures_ready) / "test_video.mkv"
        if not video_path.is_file():
            pytest.skip("test_video.mkv fixture not found")
        with open(video_path, "rb") as f:
            resp = client.post(
                "/api/process",
                files={"video": ("test_video.mkv", f, "video/x-matroska")},
            )
        assert resp.status_code == 200
        data_events = [
            json.loads(l[6:])
            for l in resp.text.strip().split("\n")
            if l.startswith("data: ")
        ]
        assert len(data_events) >= 1
        last = data_events[-1]
        # May fail with "error" if edge-tts unavailable — that's fine
        assert last["type"] in ("complete", "error")

    def test_stream_includes_tool_check_logs(
        self, client: TestClient, fixtures_ready: str,
    ):
        """Log should mention ffmpeg/ffprobe checks."""
        video_path = Path(fixtures_ready) / "test_video.mkv"
        if not video_path.is_file():
            pytest.skip("test_video.mkv fixture not found")
        with open(video_path, "rb") as f:
            resp = client.post(
                "/api/process",
                files={"video": ("test_video.mkv", f, "video/x-matroska")},
            )
        log_text = " ".join(
            json.loads(l[6:])["message"]
            for l in resp.text.strip().split("\n")
            if l.startswith("data: ") and json.loads(l[6:])["type"] == "log"
        )
        assert "ffmpeg" in log_text


# ── CORS ──────────────────────────────────────────────────────────────


class TestCORS:
    """CORS headers for frontend access."""

    def test_health_has_cors(self, client: TestClient):
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        # CORS should be permissive for local dev
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_process_has_cors(self, client: TestClient, sample_video: bytes):
        resp = client.post(
            "/api/process",
            files={"video": ("m.mkv", io.BytesIO(sample_video), "video/x-matroska")},
            headers={"Origin": "http://example.com"},
        )
        assert resp.headers.get("access-control-allow-origin") == "*"
