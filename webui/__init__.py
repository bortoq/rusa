"""WebUI for rusa — Gradio-based graphical interface.

Usage:
    rusa --webui
    python -m rusa.webui
"""
from __future__ import annotations

__all__ = ["run", "create_app"]

import sys


def run(host: str = "127.0.0.1", port: int = 7860, share: bool = False) -> None:
    """Launch the rusa WebUI server."""
    import gradio as gr
    from webui.app import create_app

    css = """
    footer { display: none !important; }
    .gradio-container { max-width: 960px !important; margin: auto !important; }
    """
    app = create_app()
    app.launch(server_name=host, server_port=port, share=share, css=css, theme=gr.themes.Soft())


def create_app():
    """Create the Gradio Blocks app. Imported by run() and tests."""
    from webui.app import create_app as _create

    return _create()


if __name__ == "__main__":
    run()
