# Lyrics Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make timestamped lyrics align without boundary loss, keep exports private by default, and correct stale testing documentation.

**Architecture:** LRC parsing and melody alignment remain in `uketab.lyrics`; CLI and renderers retain the `dict[Fraction, str]` mapping. Timestamped lines use non-overlapping half-open windows: `[line_start, next_line_start)`; the existing final-line window already includes every available melody onset and requires no behavior change.

**Tech Stack:** Python 3.11+, pytest, argparse, matplotlib.

**Spec:** `docs/issue-ledger.md`, `docs/superpowers/specs/2026-09-13-ukulele-tab-cli-design.md`

## Global Constraints

- Preserve high-G tab generation and no-lyrics output behavior.
- Do not commit user media, LRC files, or generated outputs.
- Attach lyrics only to melody onsets, with at most one token per onset.
- No personal watermark unless the user explicitly requests one.

---

### Task 1: Correct timestamped lyric windows

**Files:**
- Modify: `src/uketab/lyrics.py`, `src/uketab/cli.py`
- Modify: `tests/test_lyrics.py`, `tests/test_cli.py`

**Interfaces:** `align(lines, melody_beats, tempo_bpm, window_tolerance_beats=Fraction(0)) -> dict[Fraction, str]`; `attach(path, notes, tempo_bpm)`.

- [x] Write a failing test where adjacent timestamped lines map to distinct onsets and an earlier line has enough tokens to steal the second line's onset under the previous tolerance.
- [x] Run `.venv\\Scripts\\python -m pytest tests/test_lyrics.py -q`; verify it fails because the default tolerance overlaps windows.
- [x] Change the default tolerance to zero and preserve `start <= beat < end` matching; keep nonzero tolerance only as an explicit caller option.
- [x] Run `.venv\\Scripts\\python -m pytest tests/test_lyrics.py tests/test_cli.py -q` and then `.venv\\Scripts\\python -m pytest -q`; all tests pass.

### Task 2: Remove default personal watermark

**Files:**
- Modify: `src/uketab/render/image.py`, `src/uketab/cli.py`, `README.md`
- Modify: `tests/test_cli.py`

**Interfaces:** `render_png(..., watermark="")`; `--watermark` remains an explicit opt-in string.

- [x] Write a failing CLI test that mocks `uketab.cli.render_png`, calls `main([... "--png"])` without `--watermark`, and expects captured `watermark == ""`.
- [x] Run `.venv\\Scripts\\python -m pytest tests/test_cli.py::test_png_default_has_no_watermark -q`; verify it fails because the default is the personal email.
- [x] Set the image renderer and CLI defaults to `""`, retain explicit custom watermark behavior, and change README copy to say watermarks are disabled by default.
- [x] Run `.venv\\Scripts\\python -m pytest tests/test_cli.py tests/test_render_image.py -q` and then `.venv\\Scripts\\python -m pytest -q`; all tests pass.

### Task 3: Correct documentation and ledger state

**Files:**
- Modify: `README.md`, `docs/issue-ledger.md`

- [x] Replace the hard-coded README test count with “运行全部单元、集成与 CLI 测试”.
- [x] Run the documented `.venv\\Scripts\\python -m pytest -q` command and verify exit code 0.
- [x] Mark `DOC-001` resolved in the ledger with date 2026-09-14 and update resolved lyrics/privacy entries only after their tests pass.
- [ ] Commit only the focused files using `git commit -m "fix: harden lyric alignment and export defaults"`.
