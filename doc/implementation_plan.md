# rusa Implementation Plan — ALL PHASES COMPLETE ✅

> **This document is historical.** All Phase 1, 2, and 3 tasks have been completed.
> The Gradio→FastAPI migration is also complete.
> See [doc/roadmap.md](roadmap.md) for remaining items.

The original plan covered three phases:

1. **Phase 1: User-facing behaviour** — `--subs-mode`, WAV cache, cache management CLI, timing summary, exit codes, test split
2. **Phase 2: Module split** — monolithic `rusa.py` → 8 focused modules
3. **Phase 3: Assembly memory/I/O redesign** — streaming assembly, single write pass

All phases are fully implemented and tested (205 tests passing on CI, Python 3.9–3.13).

## File Map (current)

```
rusa/
├── rusa.py              # CLI entrypoint
├── rusa_cli.py          # Argument parser + list_voices
├── rusa_subtitle.py     # SRT: extract, detect, parse, sync, merge
├── rusa_tts.py          # TTS generation
├── rusa_audio.py        # MP3→WAV + assembly
├── rusa_mux.py          # Mix, mux, codecs
├── rusa_engines.py      # TTS backend registry
├── rusa_shared.py       # Constants, cache, backends, terminal
├── rusa_gui.py          # Native tkinter GUI
├── webui/
│   ├── server.py        # FastAPI REST API
│   ├── config.py        # Shared config
│   └── utils.py         # build_args(), pick_output_file()
├── engines.yaml          # Declarative engine definitions
├── README.md             # Project documentation
└── doc/
    ├── roadmap.md        # Current roadmap & remaining items
    ├── implementation_plan.md  # This file (historical)
    └── LANGUAGE_RECOMMENDATIONS.md  # TTS recommendations
```
