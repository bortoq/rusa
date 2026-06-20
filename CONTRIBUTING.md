# Contributing

rusa is maintained as a **CLI-first** project.

## Priorities

1. core pipeline correctness
2. simple English CLI UX and diagnostics
3. tests and regressions
4. documentation and packaging
5. release discipline

## Before changing behavior

- update `README.md`
- add or update tests
- keep fast checks runnable:

```bash
pytest -q -m 'not slow and not live_tts'
pytest -q tests/test_cli_smoke.py
```

## Scope guidance

Changes that improve the core CLI flow are in scope.
Changes that add a new UI layer are out of scope for now.
