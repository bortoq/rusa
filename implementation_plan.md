# rusa Roadmap Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved roadmap in phased, testable slices without mixing unrelated high-risk refactors into one opaque change.

**Architecture:** The roadmap spans multiple independent subsystems, so execution should be split into phases that each produce working software and green tests. Phase 1 extends the current monolith with user-facing CLI/cache/test improvements, Phase 2 performs the module split on already-stable behavior, and Phase 3 tackles the higher-risk assembly memory and I/O redesign.

**Tech Stack:** Python 3.8+, `argparse`, `ffmpeg`/`ffprobe`, `edge-tts`, `pytest`

---

## Scope Split

This roadmap should not be implemented as one giant commit. It should be executed as these sub-projects:

1. **Phase 1: User-facing behavior and operational improvements**
   - `--subs-mode`
   - WAV cache
   - cache management
   - timing summary
   - offline/live test split cleanup
   - exit codes and error UX polish
2. **Phase 2: Module split**
   - split `rusa.py` into focused files without changing behavior
3. **Phase 3: Assembly memory/I/O redesign**
   - chunked or streaming assembly path

Phase 1 is the first implementation target. Phase 2 and Phase 3 should be executed only after Phase 1 is stable and committed.

## File Map

### Existing files to extend in Phase 1

- Modify: `rusa.py`
  - add `--subs-mode`
  - add WAV cache helpers
  - add cache management CLI
  - add timing summary
  - add stable exit code mapping
- Modify: `README.md`
  - document new CLI, cache controls, timing summary, and subtitle behavior
- Modify: `tests/test_cli_regressions.py`
  - add CLI regressions for `--subs-mode`, cache commands, and errors
- Modify: `tests/test_regression.py`
  - add timing summary and offline/live expectations where appropriate
- Create: `tests/test_wav_cache.py`
  - regression tests for WAV cache
- Create: `tests/test_cache_cli.py`
  - regression tests for cache stats/clear/no-cache

### Files to create in Phase 2

- Create: `rusa_cli.py`
- Create: `rusa_subtitle.py`
- Create: `rusa_tts.py`
- Create: `rusa_audio.py`
- Create: `rusa_mux.py`
- Create: `rusa_cache.py`
- Modify: `rusa.py`
  - keep thin compatibility entrypoint

### Files to extend in Phase 3

- Modify: `rusa_audio.py` or `rusa.py` depending on Phase 2 outcome
- Create: `tests/test_assembly_streaming.py`

## Phase 1 Tasks

### Task 1: Add `--subs-mode` CLI contract

**Files:**
- Modify: `rusa.py`
- Modify: `tests/test_cli_regressions.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_subs_mode_drop_skips_subtitle_mapping(...):
    ...

def test_subs_mode_copy_fails_on_incompatible_subtitles(...):
    ...

def test_subs_mode_convert_uses_srt_for_mkv(...):
    ...

def test_subs_mode_auto_falls_back_copy_convert_drop(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cli_regressions.py -k subs_mode`
Expected: FAIL because `--subs-mode` is not implemented

- [ ] **Step 3: Write minimal implementation**

```python
parser.add_argument(
    "--subs-mode",
    choices=["auto", "copy", "convert", "drop"],
    default="auto",
)
```

Add a preflight subtitle strategy chooser and pass the chosen mode into final mux logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cli_regressions.py -k subs_mode`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rusa.py README.md tests/test_cli_regressions.py
git commit -m "Add subtitle mode controls"
```

### Task 2: Add WAV cache

**Files:**
- Modify: `rusa.py`
- Create: `tests/test_wav_cache.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_step_convert_wav_populates_cache(...):
    ...

def test_step_convert_wav_reuses_cache_when_speed_matches(...):
    ...

def test_step_convert_wav_misses_cache_when_speed_changes(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_wav_cache.py`
Expected: FAIL because WAV cache does not exist

- [ ] **Step 3: Write minimal implementation**

```python
def _wav_cache_path(...): ...
def _wav_cache_key(...): ...
```

Cache key must include:
- source mp3 content identity
- speed
- current filter version

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_wav_cache.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rusa.py README.md tests/test_wav_cache.py
git commit -m "Add persistent WAV cache"
```

### Task 3: Add cache management CLI

**Files:**
- Modify: `rusa.py`
- Create: `tests/test_cache_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_cache_stats_reports_tts_and_wav_entries(...):
    ...

def test_cache_clear_removes_cached_files(...):
    ...

def test_no_cache_disables_reads_and_writes(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cache_cli.py`
Expected: FAIL because cache management commands do not exist

- [ ] **Step 3: Write minimal implementation**

Implement CLI shapes:

```text
rusa --cache-stats
rusa --cache-clear
rusa --no-cache
```

Keep them as top-level flags instead of adding subcommands to avoid a larger CLI refactor in Phase 1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cache_cli.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rusa.py README.md tests/test_cache_cli.py
git commit -m "Add cache management flags"
```

### Task 4: Add timing summary

**Files:**
- Modify: `rusa.py`
- Modify: `tests/test_regression.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

```python
def test_main_prints_timing_summary(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_regression.py -k timing_summary`
Expected: FAIL because timing summary is absent

- [ ] **Step 3: Write minimal implementation**

Track start/stop times for:
- subtitles
- tts
- wav
- assemble
- mux

Print a compact summary at the end of successful execution.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_regression.py -k timing_summary`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rusa.py README.md tests/test_regression.py
git commit -m "Add timing summary output"
```

### Task 5: Improve test split and live smoke semantics

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_regression.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

```python
def test_live_tts_tests_are_explicitly_marked(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_regression.py -k live_tts`
Expected: FAIL because live smoke semantics are inconsistent

- [ ] **Step 3: Write minimal implementation**

Introduce explicit marker separation:
- `slow`
- `live_tts`

Document how to run:
- offline suite
- live smoke suite

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_regression.py -k live_tts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_regression.py README.md
git commit -m "Clarify offline and live test modes"
```

### Task 6: Error UX and exit codes

**Files:**
- Modify: `rusa.py`
- Modify: `tests/test_cli_regressions.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_encoder_returns_stable_exit_code(...):
    ...

def test_invalid_srt_returns_stable_exit_code(...):
    ...

def test_subtitle_container_mismatch_message_is_actionable(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cli_regressions.py -k exit_code`
Expected: FAIL because exit codes/messages are not stable enough

- [ ] **Step 3: Write minimal implementation**

Add named exit code constants and route common failures through them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q tests/test_cli_regressions.py -k exit_code`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rusa.py README.md tests/test_cli_regressions.py
git commit -m "Stabilize CLI exit codes and errors"
```

## Phase 2 Tasks

### Task 7: Split monolith into focused modules without behavior changes

**Files:**
- Create: `rusa_cli.py`
- Create: `rusa_subtitle.py`
- Create: `rusa_tts.py`
- Create: `rusa_audio.py`
- Create: `rusa_mux.py`
- Create: `rusa_cache.py`
- Modify: `rusa.py`
- Re-run: full test suite

- [ ] **Step 1: Write focused import-level regression tests**
- [ ] **Step 2: Move pure helpers first**
- [ ] **Step 3: Move subtitle logic**
- [ ] **Step 4: Move TTS/cache logic**
- [ ] **Step 5: Move audio/mux logic**
- [ ] **Step 6: Leave `rusa.py` as compatibility entrypoint**
- [ ] **Step 7: Run full suite**
- [ ] **Step 8: Commit**

Commit message:

```bash
git commit -m "Split rusa monolith into focused modules"
```

## Phase 3 Tasks

### Task 8: Reduce assembly memory and I/O pressure

**Files:**
- Modify: assembly implementation after Phase 2 split
- Create: `tests/test_assembly_streaming.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing regression tests for large-file assembly behavior**
- [ ] **Step 2: Implement chunked or streaming assembly path**
- [ ] **Step 3: Verify WAV header integrity and timing behavior remain unchanged**
- [ ] **Step 4: Run full suite**
- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "Reduce assembly memory and I/O footprint"
```

## Verification Commands

After each completed task:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q
```

For offline-only verification:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' pytest -q -m 'not slow and not live_tts'
```

## Self-Review

- Coverage: the roadmap items are all covered, but only by phased execution; they should not be collapsed into one commit.
- Placeholder scan: high-risk phases 2 and 3 are intentionally expressed as scoped work packages, not immediate coding steps, because they depend on Phase 1 stabilization.
- Type consistency: current plan keeps CLI flags in `rusa.py` for Phase 1 and reserves module split for Phase 2 to avoid mixed concerns.
