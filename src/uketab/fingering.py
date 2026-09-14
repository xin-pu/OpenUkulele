"""Fretboard assignment: per-slice chord candidates + per-bar DP.

Each slice's pitches are enumerated onto all (string, fret) combinations
within the difficulty's fret range; conflicting, out-of-span and
finger-impossible combinations are pruned at generation time. A dynamic
program then chooses one candidate per slice per bar, minimizing the
transfer cost defined by the design doc:

    10000 * infeasible
      + 40 * position shifts
      +  8 * average fret movement
      +  5 * current span
      +  3 * non-open strings
      +  2 * barres (hard only)

Weights are fixed code constants; the report does not claim they form an
objective difficulty metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .arrangement import DifficultyProfile
from .models import Fingering, TabNote
from .timing import Bar, TimeSlice
from .tuning import HIGH_G, Tuning, enumerate_candidates

COST_INFEASIBLE = 10_000
COST_SHIFT = 40
COST_FRET_MOVE = 8
COST_SPAN = 5
COST_NON_OPEN = 3
COST_BARRE = 2

#: Right-hand preference for melody/harmony by string (A, E, C, G).
RIGHT_HAND_BY_STRING: dict[int, str] = {1: "a", 2: "m", 3: "i", 4: "i"}


class _InfeasibleFingering(Exception):
    """Raised when no valid left-hand finger assignment exists."""


@dataclass(frozen=True)
class ChordCandidate:
    """One fretboard realization of a time slice."""

    fingerings: tuple[Fingering, ...]  # aligned 1:1 with the slice's notes
    span: int
    barre_count: int
    non_open: int
    position: int | None  # lowest fretted fret; None when fully open
    static_cost: int

    def fret_on(self, string: int) -> int | None:
        for fingering in self.fingerings:
            if fingering.string == string:
                return fingering.fret
        return None


@dataclass(frozen=True)
class BarSolution:
    """DP result for one bar; ``notes`` is empty when infeasible."""

    index: int
    notes: tuple[TabNote, ...]
    slice_candidate_counts: tuple[int, ...]
    cost: int | None
    feasible: bool


def generate_candidates(
    slice_: TimeSlice, profile: DifficultyProfile, tuning: Tuning = HIGH_G
) -> tuple[ChordCandidate, ...]:
    """All admissible chord fingerings for one slice, pruned inline."""
    per_note: list[tuple[tuple[int, int], ...]] = []
    for note in slice_.notes:
        options = enumerate_candidates(note.pitch, tuning, profile.max_fret)
        if not options:
            return ()  # unreachable pitch: slice cannot be realized
        per_note.append(options)

    candidates: list[ChordCandidate] = []
    for combo in _cartesian(per_note):
        strings = [string for string, _ in combo]
        if len(set(strings)) != len(strings):
            continue  # same_string_conflict
        frets = [fret for _, fret in combo if fret > 0]
        if frets:
            span = max(frets) - min(frets)
            if span > profile.max_span:
                continue  # span_exceeded
        try:
            candidates.append(_make_candidate(combo, slice_, profile))
        except _InfeasibleFingering:
            continue  # finger_conflict
    return tuple(candidates)


def solve_bar(bar: Bar, profile: DifficultyProfile, tuning: Tuning = HIGH_G) -> BarSolution:
    """Choose the minimum-cost candidate sequence over one bar."""
    if not bar.slices:
        return BarSolution(
            index=bar.index, notes=(), slice_candidate_counts=(), cost=0, feasible=True
        )

    per_slice = [generate_candidates(s, profile, tuning) for s in bar.slices]
    counts = tuple(len(c) for c in per_slice)
    if any(count == 0 for count in counts):
        return BarSolution(
            index=bar.index, notes=(), slice_candidate_counts=counts, cost=None, feasible=False
        )

    best_costs = [candidate.static_cost for candidate in per_slice[0]]
    predecessors: list[list[int]] = [[]]
    for i in range(1, len(per_slice)):
        previous, current = per_slice[i - 1], per_slice[i]
        new_costs: list[int] = []
        preds: list[int] = []
        for candidate in current:
            cost, pred = min(
                (best_costs[p] + _transfer_cost(previous[p], candidate), p)
                for p in range(len(previous))
            )
            new_costs.append(cost)
            preds.append(pred)
        best_costs = new_costs
        predecessors.append(preds)

    end = min(range(len(per_slice[-1])), key=lambda i: best_costs[i])
    chosen = [0] * len(per_slice)
    chosen[-1] = end
    for i in range(len(per_slice) - 1, 0, -1):
        chosen[i - 1] = predecessors[i][chosen[i]]

    return BarSolution(
        index=bar.index,
        notes=_tab_notes(bar, per_slice, chosen),
        slice_candidate_counts=counts,
        cost=best_costs[end],
        feasible=True,
    )


def solve_bars(
    bars: Sequence[Bar], profile: DifficultyProfile, tuning: Tuning = HIGH_G
) -> tuple[BarSolution, ...]:
    return tuple(solve_bar(bar, profile, tuning) for bar in bars)


def _tab_notes(
    bar: Bar, per_slice: Sequence[Sequence[ChordCandidate]], chosen: Sequence[int]
) -> tuple[TabNote, ...]:
    notes: list[TabNote] = []
    for slice_, candidates, candidate_index in zip(bar.slices, per_slice, chosen):
        candidate = candidates[candidate_index]
        for pitch, fingering in zip(slice_.notes, candidate.fingerings):
            right = "p" if pitch.role == "bass" else RIGHT_HAND_BY_STRING[fingering.string]
            complete = Fingering(
                string=fingering.string,
                fret=fingering.fret,
                finger_left=fingering.finger_left,
                finger_right=right,  # type: ignore[arg-type]
            )
            notes.append(TabNote(note=pitch, fingering=complete))
    return tuple(notes)


def _make_candidate(
    combo: tuple[tuple[int, int], ...], slice_: TimeSlice, profile: DifficultyProfile
) -> ChordCandidate:
    """Build a candidate with left-hand finger assignment.

    Fretted notes become press units: a maximal run of consecutive strings
    at one fret is a barre (one finger) when the difficulty allows it,
    otherwise each string presses on its own. A unit's finger follows its
    distance from the lowest fretted fret; distinct units must not share a
    finger, and fingers stop at 4.
    """
    fretted = [(string, fret) for string, fret in combo if fret > 0]
    span = max(f for _, f in fretted) - min(f for _, f in fretted) if fretted else 0
    position = min(f for _, f in fretted) if fretted else None

    barre_count = 0
    finger_by_string: dict[int, int] = {}
    if fretted:
        by_fret: dict[int, list[int]] = {}
        for string, fret in fretted:
            by_fret.setdefault(fret, []).append(string)
        units: list[tuple[int, tuple[int, ...]]] = []  # (fret, strings)
        for fret, strings in by_fret.items():
            for run in _consecutive_runs(sorted(strings)):
                if profile.allow_barre and len(run) >= 2:
                    units.append((fret, tuple(run)))
                    barre_count += 1
                else:
                    units.extend((fret, (string,)) for string in run)

        base_fret = min(fret for fret, _ in units)
        used_fingers: set[int] = set()
        for fret, strings in units:
            finger = fret - base_fret + 1
            if finger > 4 or finger in used_fingers:
                raise _InfeasibleFingering
            used_fingers.add(finger)
            for string in strings:
                finger_by_string[string] = finger

    fingerings = tuple(
        Fingering(
            string=string,
            fret=fret,
            finger_left=finger_by_string.get(string),
            finger_right=None,
        )
        for (string, fret) in combo
    )
    non_open = len(fretted)
    static_cost = COST_SPAN * span + COST_NON_OPEN * non_open + COST_BARRE * barre_count
    return ChordCandidate(
        fingerings=fingerings,
        span=span,
        barre_count=barre_count,
        non_open=non_open,
        position=position,
        static_cost=static_cost,
    )


def _consecutive_runs(strings: Sequence[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for string in strings:
        if runs and runs[-1][-1] + 1 == string:
            runs[-1].append(string)
        else:
            runs.append([string])
    return runs


def _cartesian(pools: Sequence[Sequence[tuple[int, int]]]):
    if not pools:
        yield ()
        return
    for head in pools[0]:
        for tail in _cartesian(pools[1:]):
            yield (head, *tail)


def _transfer_cost(previous: ChordCandidate, current: ChordCandidate) -> int:
    shift = 0
    if previous.position is not None and current.position is not None:
        shift = 1 if previous.position != current.position else 0

    moves = []
    for fingering in current.fingerings:
        if fingering.fret == 0:
            continue
        previous_fret = previous.fret_on(fingering.string)
        if previous_fret is not None and previous_fret > 0:
            moves.append(abs(fingering.fret - previous_fret))
    average_move = sum(moves) / len(moves) if moves else 0.0

    return COST_SHIFT * shift + COST_FRET_MOVE * average_move + current.static_cost
