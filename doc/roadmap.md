# rusa Roadmap

## Current direction

rusa is maintained as a **CLI-first** project.

Current priorities:

1. core pipeline correctness
2. simple English CLI UX
3. tests and regressions
4. documentation and packaging
5. release discipline

## Completed foundations

- CLI pipeline
- subtitle extraction and sync support
- TTS backend abstraction
- WAV cache and TTS cache
- timing summary
- output codec selection
- subtitle handling modes (`auto`, `copy`, `convert`, `drop`)
- Docker support
- GitHub Action support
- subprocess-based CLI smoke tests

## Current technical debt

- continue simplifying user-facing output into plain English
- keep README examples aligned with real CLI behavior
- keep cross-platform behavior stable
- keep fixture-dependent integration tests separate from fast offline checks

## Nice-to-have later

- broader engine examples and tuning guides
- more real-world CLI smoke scenarios
- optional packaging polish for public release

## Out of focus for now

- GUI layers
- REST API layers
- hosted service features
- billing or account features
