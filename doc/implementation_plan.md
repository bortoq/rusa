# rusa Implementation Plan — Historical Note

This file is kept as a short historical note.

The main refactoring phases are complete:

1. **Phase 1** — user-facing CLI behavior (`--subs-mode`, cache, timing, exit codes)
2. **Phase 2** — module split (`rusa.py` into focused modules)
3. **Phase 3** — lower-memory assembly with a single write pass

## Current file map

```text
rusa/
├── rusa.py              # CLI entrypoint
├── rusa_cli.py          # Argument parser + voice listing
├── rusa_subtitle.py     # Subtitle extraction, parsing, sync, merge
├── rusa_tts.py          # TTS generation
├── rusa_audio.py        # MP3->WAV conversion + assembly
├── rusa_mux.py          # Mix, mux, codecs
├── rusa_engines.py      # TTS engine registry
├── rusa_shared.py       # Shared constants, cache, backends, helpers
├── engines.yaml         # Declarative engine definitions
├── README.md            # Main project documentation
└── doc/
    ├── roadmap.md
    ├── implementation_plan.md
    └── LANGUAGE_RECOMMENDATIONS.md
```

For the current project direction, see [roadmap.md](roadmap.md).
