"""Import-level regression tests for the split module layout."""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rusa
import rusa_audio
import rusa_cli
import rusa_mux
import rusa_shared
import rusa_subtitle
import rusa_tts


def test_split_modules_import_cleanly():
    assert callable(rusa.main)
    assert callable(rusa_audio.step_assemble)
    assert callable(rusa_shared.print_cache_stats)
    assert callable(rusa_cli.build_parser)
    assert callable(rusa_mux.step_mix_output)
    assert callable(rusa_subtitle.step_parse_srt)
    assert callable(rusa_tts.step_generate_tts)
    assert rusa.DEFAULT_VOICE == rusa_shared.DEFAULT_VOICE


def test_engine_module_can_be_imported_first():
    result = subprocess.run(
        [sys.executable, "-c", "import rusa_engines, rusa_shared; "
         "assert 'piper' in rusa_shared.BACKEND_REGISTRY"],
        cwd=Path(__file__).parent.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_thin_entrypoint_reexports_split_callables():
    assert rusa.step_assemble is rusa_audio.step_assemble
    assert rusa.step_mix_output is rusa_mux.step_mix_output
    assert rusa.step_parse_srt is rusa_subtitle.step_parse_srt
    assert rusa.step_generate_tts is rusa_tts.step_generate_tts
