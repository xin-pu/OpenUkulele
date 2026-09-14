"""JSON playability report.

Always written for a run -- even when a difficulty failed validation --
so the user can inspect quantization parameters, statistics, warnings and
validation issues after the fact.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .errors import ExportError
from .fallback import ResolutionResult
from .models import Arrangement, ValidationReport


def build_report(
    *,
    input_path: str,
    source: str,
    event_count: int,
    tempo_bpm: float,
    tempo_provided: bool,
    time_signature: tuple[int, int],
    grid_easy: Fraction,
    grid_hard: Fraction,
    easy: tuple[Arrangement, ResolutionResult] | None,
    hard: tuple[Arrangement, ResolutionResult] | None,
    warnings: Sequence[str],
) -> dict[str, Any]:
    return {
        "version": __version__,
        "input": {
            "path": input_path,
            "source": source,
            "events": event_count,
            "tempo_bpm": round(tempo_bpm, 2),
            "tempo_provided": tempo_provided,
            "time_signature": list(time_signature),
        },
        "quantization": {
            "grid_easy": _fraction_str(grid_easy),
            "grid_hard": _fraction_str(grid_hard),
            "note": "onsets snapped to the nearest grid position; durations are whole grid multiples (min 1)",
        },
        "arrangements": {
            name: _arrangement_entry(entry)
            for name, entry in (("easy", easy), ("hard", hard))
            if entry is not None
        },
        "warnings": list(warnings),
    }


def _arrangement_entry(entry: tuple[Arrangement, ResolutionResult]) -> dict[str, Any]:
    arrangement, resolution = entry
    notes = arrangement.notes
    roles: dict[str, int] = {}
    for note in notes:
        roles[note.note.role] = roles.get(note.note.role, 0) + 1
    bar_count = max(
        (int(n.note.beat / _bar_beats(arrangement)) + 1 for n in notes), default=0
    )
    return {
        "notes": len(notes),
        "roles": roles,
        "bars": bar_count,
        "passed": resolution.report.passed,
        "failed_bars": list(resolution.failed_bars),
        "validation": _validation_summary(resolution.report),
        "fallback": [
            {"bar": action.bar, "step": action.step, "reason": action.reason}
            for action in resolution.actions
        ],
    }


def _bar_beats(arrangement: Arrangement) -> Fraction:
    numerator, denominator = arrangement.time_signature
    return Fraction(numerator * 4, denominator)


def _validation_summary(report: ValidationReport) -> dict[str, Any]:
    return {
        "passed": report.passed,
        "shift_count": report.shift_count,
        "max_span": report.max_span,
        "barre_count": report.barre_count,
        "difficulty_score": report.difficulty_score,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "bar": issue.bar,
                "beat": _fraction_str(issue.beat) if issue.beat is not None else None,
            }
            for issue in report.errors
        ],
    }


def _fraction_str(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def write_report(report: dict[str, Any], path: str | Path) -> None:
    try:
        Path(path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise ExportError(f"报告写入失败: {path} ({exc})", "检查输出目录权限") from exc
