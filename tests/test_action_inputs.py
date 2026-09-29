"""Composite action must pass user inputs as data, not shell code."""

import json
import os
import re
import subprocess
from pathlib import Path

import yaml


def test_action_preserves_shell_metacharacters_in_inputs(tmp_path):
    action_file = Path(__file__).resolve().parents[1] / ".github/actions/rusa-action/action.yml"
    action = yaml.safe_load(action_file.read_text(encoding="utf-8"))
    run_step = next(step for step in action["runs"]["steps"] if step["name"] == "Run rusa")
    assert "${{ inputs." not in run_step["run"]

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_rusa = fake_bin / "rusa"
    fake_rusa.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['RUSA_ARGS_FILE'], 'w') as handle:\n"
        "    json.dump(sys.argv[1:], handle)\n",
        encoding="utf-8",
    )
    fake_rusa.chmod(0o755)

    marker = tmp_path / "injected"
    video = f"movie$(touch {marker}).mkv"
    srt = f'subs"; touch {marker}; #.srt'
    args_file = tmp_path / "args.json"
    inputs = {
        "video": video,
        "srt": srt,
        "lang": "ru",
        "voice": "voice name",
        "tts_cmd": "",
        "engine": "edge",
        "speed": "1.5",
        "output": "output movie.mkv",
    }
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["RUSA_ARGS_FILE"] = str(args_file)
    for name, expression in run_step["env"].items():
        match = re.fullmatch(r"\$\{\{ inputs\.([a-z_]+) \}\}", expression)
        assert match, expression
        env[name] = inputs[match.group(1)]
    result = subprocess.run(
        ["bash", "-e", "-c", run_step["run"]],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert json.loads(args_file.read_text(encoding="utf-8")) == [
        "-s", srt, "--lang", "ru", "--voice", "voice name", "--speed", "1.5",
        "-o", "output movie.mkv", video,
    ]
