"""Per-bar degradation ladder for measures that fail solving or validation.

For each failing bar, in order: drop harmony notes, drop bass (melody
survives), collapse to the single highest melody note per slice -- re-
solving after every step. A bar that still has no admissible realization
marks the whole arrangement as failed; the CLI then exits non-zero and the
report names the failing bars.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .arrangement import DifficultyProfile
from .fingering import BarSolution, solve_bar
from .models import TabNote
from .timing import Bar, TimeSlice
from .tuning import HIGH_G, Tuning
from .validation import ValidationReport, validate_notes

LADDER: tuple[str, ...] = ("remove_harmony", "remove_bass", "melody_only")


@dataclass(frozen=True)
class FallbackAction:
    bar: int
    step: str
    reason: str = ""


@dataclass(frozen=True)
class ResolutionResult:
    solutions: tuple[BarSolution, ...]
    actions: tuple[FallbackAction, ...]
    report: ValidationReport
    failed_bars: tuple[int, ...]

    @property
    def success(self) -> bool:
        return not self.failed_bars and self.report.passed


def resolve_with_fallback(
    bars: Sequence[Bar],
    profile: DifficultyProfile,
    time_signature: tuple[int, int],
    tuning: Tuning = HIGH_G,
) -> ResolutionResult:
    solutions = {bar.index: solve_bar(bar, profile, tuning) for bar in bars}
    actions: list[FallbackAction] = []
    working = {bar.index: bar for bar in bars}

    for bar in bars:
        if solutions[bar.index].feasible:
            continue
        # Ladder steps accumulate: each applies to the already-degraded bar.
        degraded = working[bar.index]
        applied: list[str] = []
        solution = None
        for step in LADDER:
            degraded = _apply_step(degraded, step)
            if degraded == working[bar.index]:
                continue  # step had nothing to remove; don't log noise
            applied.append(step)
            working[bar.index] = degraded
            solution = solve_bar(degraded, profile, tuning)
            if solution.feasible and _bar_passes(solution, time_signature, profile, tuning):
                break
        if solution is not None and solution.feasible and _bar_passes(
            solution, time_signature, profile, tuning
        ):
            solutions[bar.index] = solution
            actions.extend(
                FallbackAction(bar=bar.index, step=step, reason="求解或校验失败")
                for step in applied
            )

    ordered = tuple(solutions[bar.index] for bar in bars)
    failed = tuple(bar.index for bar in bars if not solutions[bar.index].feasible)
    all_notes: tuple[TabNote, ...] = tuple(n for s in ordered for n in s.notes)
    report = validate_notes(all_notes, time_signature, profile, tuning)
    return ResolutionResult(
        solutions=ordered,
        actions=tuple(actions),
        report=report,
        failed_bars=failed,
    )


def _bar_passes(
    solution: BarSolution,
    time_signature: tuple[int, int],
    profile: DifficultyProfile,
    tuning: Tuning,
) -> bool:
    return validate_notes(solution.notes, time_signature, profile, tuning).passed


def _apply_step(bar: Bar, step: str) -> Bar:
    if step == "remove_harmony":
        return _filter_roles(bar, dropped={"harmony"})
    if step == "remove_bass":
        return _filter_roles(bar, dropped={"bass"})
    if step == "melody_only":
        slices = [
            replace(slice_, notes=(slice_.notes[0],)) if slice_.notes else slice_
            for slice_ in bar.slices
        ]
        return replace(bar, slices=tuple(slices))
    raise ValueError(f"unknown fallback step: {step}")


def _filter_roles(bar: Bar, dropped: set[str]) -> Bar:
    slices = [
        TimeSlice(beat=slice_.beat, notes=tuple(n for n in slice_.notes if n.role not in dropped))
        for slice_ in bar.slices
    ]
    return replace(bar, slices=tuple(s for s in slices if s.notes))
