"""WebUI for rusa — FastAPI REST API server.

Usage:
    rusa --webui
    python -m webui
"""
from __future__ import annotations

__all__ = ["run", "create_app"]

import os
import sys


def run(host: str = "127.0.0.1", port: int = 7860) -> None:
    """Launch the rusa API server."""
    from webui.server import run as _server_run

    _server_run(host=host, port=port)


def create_app():
    """Create the FastAPI app. Imported by tests."""
    from webui.server import create_app as _create

    return _create()


if __name__ == "__main__":
    run()
