# Release Checklist

Use this checklist before cutting a new release.

## Core quality

- [ ] `python -m compileall -q .`
- [ ] `pytest -q -m 'not slow and not live_tts'`
- [ ] `pytest -q tests/test_cli_smoke.py`
- [ ] README examples still match actual CLI behavior
- [ ] no known critical regressions in subtitle extraction, TTS, WAV conversion, muxing, or cache logic

## Docs

- [ ] `README.md` reflects current behavior
- [ ] `CHANGELOG.md` updated
- [ ] experimental status of GUI/WebUI is still accurate
- [ ] install instructions still work on the supported CLI path

## Packaging

- [ ] version updated in `pyproject.toml` if needed
- [ ] `LICENSE` present
- [ ] project URLs in `pyproject.toml` still valid
- [ ] optional extras (`[webui]`) still install cleanly

## Release

- [ ] create git tag
- [ ] create GitHub Release notes from `CHANGELOG.md`
- [ ] publish package / image only after tests pass
