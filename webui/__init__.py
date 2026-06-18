"""WebUI for rusa — Gradio-based graphical interface.

Usage:
    rusa --webui
    python -m webui
"""
from __future__ import annotations

__all__ = ["run", "create_app"]

import os
import sys


def run(host: str = "127.0.0.1", port: int = 7860, share: bool = False) -> None:
    """Launch the rusa WebUI server."""
    import warnings
    warnings.filterwarnings("ignore", message=".*HTTP_422_UNPROCESSABLE_ENTITY.*")
    import gradio as gr
    from webui.app import create_app, _WEBUI_CSS

    app = create_app()
    from webui.config import DEFAULT_OUTPUT_DIR
    app.launch(server_name=host, server_port=port, share=share, css=_WEBUI_CSS, theme=gr.themes.Soft(),
               allowed_paths=[os.path.expanduser(DEFAULT_OUTPUT_DIR)])


def create_app():
    """Create the Gradio Blocks app. Imported by run() and tests."""
    from webui.app import create_app as _create

    return _create()


if __name__ == "__main__":
    run()
