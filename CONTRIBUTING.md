# Contributing

rusa is maintained **CLI-first**.

## Priorities

1. core pipeline correctness
2. CLI UX and diagnostics
3. tests and regressions
4. documentation and packaging
5. experimental layers (`--webui`, tkinter GUI)

## Before changing behavior

- update `README.md`
- add or update tests
- keep offline tests runnable with:

```bash
pytest -q -m 'not slow and not live_tts'
pytest -q tests/test_cli_smoke.py
```

## Scope guidance

If a change improves the core CLI flow, it is likely in scope.
If a change mainly expands GUI/WebUI behavior, treat it as lower priority unless it fixes a regression.
