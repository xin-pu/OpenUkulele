"""NDJSON progress protocol tests (in-process and real subprocess)."""

import json
import pathlib
import subprocess
import sys

import pytest

from uketab.cli import main
from uketab.progress import ProgressReporter

from conftest import write_midi

TWINKLE = [
    (60, 0, 1), (60, 1, 1), (67, 2, 1), (67, 3, 1),
    (69, 4, 1), (69, 5, 1), (67, 6, 2),
]


def parse_lines(stdout_text: str) -> list[dict]:
    events = []
    for line in stdout_text.splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))  # raises on any non-JSON stdout line
    return events


def test_progress_mode_stdout_is_pure_ndjson_with_terminal(tmp_path, capsys):
    midi = tmp_path / "t.mid"
    write_midi(midi, TWINKLE)
    out = tmp_path / "out"
    code = main([
        "arrange", str(midi), "--output-dir", str(out),
        "--progress-json", "--operation-id", "op-123",
    ])
    assert code == 0
    events = parse_lines(capsys.readouterr().out)
    assert events[0] == {"event": "started", "operationId": "op-123", "inputPath": str(midi)}
    terminal = events[-1]
    assert terminal["event"] == "completed"
    assert terminal["operationId"] == "op-123"
    assert terminal["exitCode"] == 0
    assert terminal["outputDirectory"] == str(out)
    assert json.loads((out / "t-report.json").read_text(encoding="utf-8"))["input"]["events"] == 7


def test_progress_percents_are_stage_vocabulary_and_monotonic(tmp_path, capsys):
    midi = tmp_path / "t.mid"
    write_midi(midi, TWINKLE)
    main([
        "arrange", str(midi), "--output-dir", str(tmp_path / "out"),
        "--progress-json", "--operation-id", "op-1",
    ])
    events = parse_lines(capsys.readouterr().out)
    stages = [e["stage"] for e in events if e["event"] == "progress"]
    assert set(stages) <= {"input", "transcribe", "normalize", "arrange", "lyrics", "export"}
    percents = [e["percent"] for e in events if e["event"] == "progress"]
    assert percents == sorted(percents)
    assert 0 <= percents[0] and percents[-1] <= 100


def test_progress_mode_input_failure_emits_failed_event(tmp_path, capsys):
    code = main([
        "arrange", str(tmp_path / "ghost.mid"), "--output-dir", str(tmp_path / "out"),
        "--progress-json", "--operation-id", "op-2",
    ])
    assert code == 3
    captured = capsys.readouterr()
    events = parse_lines(captured.out)
    terminal = events[-1]
    assert terminal["event"] == "failed"
    assert terminal["code"] == "input_error"
    assert terminal["exitCode"] == 3
    assert terminal["operationId"] == "op-2"
    assert terminal["suggestion"]
    assert "错误" in captured.err  # human diagnostics stay on stderr


def test_progress_mode_partial_result_emits_arrangement_partial(tmp_path, capsys):
    # High-register melody exceeds the easy 0-5 window -> exit 4.
    midi = tmp_path / "high.mid"
    write_midi(midi, [(72, 0, 0.5), (76, 0.5, 0.5), (79, 1, 0.5), (76, 1.5, 0.5)])
    out = tmp_path / "out"
    code = main([
        "arrange", str(midi), "--output-dir", str(out), "--progress-json",
    ])
    assert code == 4
    events = parse_lines(capsys.readouterr().out)
    terminal = events[-1]
    assert terminal["event"] == "failed"
    assert terminal["code"] == "arrangement_partial"
    assert terminal["exitCode"] == 4
    assert (out / "high-report.json").exists()


def test_default_mode_unchanged_text_not_json(tmp_path, capsys):
    midi = tmp_path / "t.mid"
    write_midi(midi, TWINKLE)
    code = main(["arrange", str(midi), "--output-dir", str(tmp_path / "out")])
    assert code == 0
    out = capsys.readouterr().out
    assert "完成" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.splitlines()[0])


def test_reporter_rejects_unknown_stage():
    reporter = ProgressReporter(True, "op", stream=sys.stdout)
    with pytest.raises(ValueError, match="unknown progress stage"):
        reporter.progress("bogus", 50, "x")


def test_real_subprocess_line_discipline(tmp_path):
    """End-to-end: the actual interpreter prints exactly one JSON per line."""
    import os

    src_root = pathlib.Path(__file__).resolve().parent.parent / "src"
    midi = tmp_path / "t.mid"
    write_midi(midi, TWINKLE)
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    result = subprocess.run(
        [sys.executable, "-m", "uketab", "arrange", str(midi),
         "--output-dir", str(tmp_path / "out"), "--progress-json", "--operation-id", "op-sub"],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
        cwd=str(src_root.parent), env=env,
    )
    assert result.returncode == 0, result.stderr
    events = parse_lines(result.stdout)
    assert [e["event"] for e in (events[0], events[-1])] == ["started", "completed"]
    assert events[-1]["operationId"] == "op-sub"
