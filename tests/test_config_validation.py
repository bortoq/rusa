"""Configuration errors should point to the user override and setting."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("contents, message", [
    ("[]\n", "must contain a mapping"),
    ("codecs: []\n", "'codecs' must be a mapping"),
    ("presets:\n  cinema: false\n", "'presets.cinema' must be a mapping"),
    ("auto_speed:\n  max: nan\n", "'auto_speed.max' must be a finite number"),
    ("auto_speed:\n  min: 2\n  max: 1\n", "cannot exceed"),
])
def test_invalid_user_config_reports_setting(tmp_path, contents, message):
    config = tmp_path / ".config" / "rusa" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(contents, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", "import rusa_shared"],
        env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert str(config) in result.stderr


def test_empty_user_config_is_valid(tmp_path):
    config = tmp_path / ".config" / "rusa" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", "import rusa_shared; assert rusa_shared.CODEC_MAP"],
        env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
