"""Independent playability validation of a final arrangement.

The validator re-derives every structural constraint from the finished
``TabNote`` sequence alone -- it never trusts the solver's internal state.
Issue codes (with bar and beat positions):

- ``same_string_conflict``  two notes on one string in one group
- ``out_of_range``          fret outside the difficulty's fret window
- ``too_many_notes``        simultaneous or per-beat note count exceeded
- ``span_exceeded``         fret span beyond the difficulty limit
- ``finger_conflict``       one finger pressing two frets / non-monotonic
- ``barre_not_allowed``     shared finger used where barre is forbidden
- ``unplayable_pitch``      pitch unreachable on the instrument at all
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from typing import Sequence

from .arrangement import DifficultyProfile
from .models import Arrangement, TabNote, ValidationIssue, ValidationReport
from .timing import QUARTER, bar_length
from .tuning import HIGH_G, Tuning, enumerate_candidates

ISSUE_CODES = (
    "same_string_conflict",
    "out_of_range",
    "too_many_notes",
    "span_exceeded",
    "finger_conflict",
    "barre_not_allowed",
    "unplayable_pitch",
)


def validate_arrangement(
    arrangement: Arrangement,
    profile: DifficultyProfile,
    tuning: Tuning = HIGH_G,
) -> ValidationReport:
    return validate_notes(arrangement.notes, arrangement.time_signature, profile, tuning)


def validate_notes(
    notes: Sequence[TabNote],
    time_signature: tuple[int, int],
    profile: DifficultyProfile,
    tuning: Tuning = HIGH_G,
) -> ValidationReport:
    errors: list[ValidationIssue] = []
    groups = _group_by_beat(notes)
    length = bar_length(time_signature)

    shifts = 0
    max_span = 0
    barres = 0
    non_open_total = 0
    previous_position: int | None = None

    for beat, group in groups:
        bar = int(beat / length) + 1
        errors.extend(_check_group(group, beat, bar, profile, tuning))
        frets = [n.fingering.fret for n in group if n.fingering.fret > 0]
        non_open_total += len(frets)
        if frets:
            span = max(frets) - min(frets)
            max_span = max(max_span, span)
            position = min(frets)
            if previous_position is not None and position != previous_position:
                shifts += 1
            previous_position = position
        else:
            previous_position = None
        barres += _barres_in_group(group)

    errors.extend(_check_per_beat(groups, profile, time_signature, length))

    note_count = len(notes)
    score_base = (
        shifts * 0.5
        + max_span * 0.6
        + barres * 0.4
        + (non_open_total / note_count if note_count else 0.0) * 3.0
    )
    difficulty_score = round(min(1.0, score_base / 10.0), 4)

    return ValidationReport(
        passed=not errors,
        errors=tuple(errors),
        shift_count=shifts,
        max_span=max_span,
        barre_count=barres,
        difficulty_score=difficulty_score,
    )


def _group_by_beat(notes: Sequence[TabNote]) -> list[tuple[Fraction, tuple[TabNote, ...]]]:
    grouped: dict[Fraction, list[TabNote]] = defaultdict(list)
    for note in notes:
        grouped[note.note.beat].append(note)
    return [(beat, tuple(sorted(notes_, key=lambda n: n.fingering.string))) for beat, notes_ in sorted(grouped.items())]


def _check_group(
    group: tuple[TabNote, ...],
    beat: Fraction,
    bar: int,
    profile: DifficultyProfile,
    tuning: Tuning,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    add = lambda code, message: issues.append(
        ValidationIssue(code=code, message=message, bar=bar, beat=beat)
    )

    strings = [n.fingering.string for n in group]
    if len(set(strings)) != len(strings):
        add("same_string_conflict", f"同弦冲突：{sorted(strings)}")

    if len(group) > profile.max_simultaneous:
        add("too_many_notes", f"同时发声 {len(group)} 音，超过上限 {profile.max_simultaneous}")

    for note in group:
        pitch = note.note.pitch
        if not enumerate_candidates(pitch, tuning, 15):
            add("unplayable_pitch", f"音高 {pitch} 无法在尤克里里上演奏")
        fret = note.fingering.fret
        if fret < 0 or fret > profile.max_fret:
            add("out_of_range", f"品 {fret} 超出难度范围 0-{profile.max_fret}")
        finger = note.fingering.finger_left
        if fret > 0 and (finger is None or not 1 <= finger <= 4):
            add("finger_conflict", f"按弦音缺少有效左手指法（品 {fret}）")
        if fret == 0 and finger is not None:
            add("finger_conflict", "开放弦不应分配左手指法")

    frets = [n.fingering.fret for n in group if n.fingering.fret > 0]
    if frets:
        span = max(frets) - min(frets)
        if span > profile.max_span:
            add("span_exceeded", f"跨度 {span} 超过上限 {profile.max_span}")

    issues.extend(_check_fingers(group, bar, beat, profile))
    return issues


def _check_fingers(
    group: tuple[TabNote, ...], bar: int, beat: Fraction, profile: DifficultyProfile
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_finger: dict[int, list[TabNote]] = defaultdict(list)
    for note in group:
        finger = note.fingering.finger_left
        if finger is not None:
            by_finger[finger].append(note)

    for finger, sharing in by_finger.items():
        if len(sharing) == 1:
            continue
        frets = {n.fingering.fret for n in sharing}
        strings = sorted(n.fingering.string for n in sharing)
        consecutive = all(b - a == 1 for a, b in zip(strings, strings[1:]))
        if len(frets) > 1 or not consecutive:
            issues.append(
                ValidationIssue(
                    code="finger_conflict",
                    message=f"手指 {finger} 同时按住不同品位/非相邻弦：{strings}",
                    bar=bar,
                    beat=beat,
                )
            )
        elif not profile.allow_barre:
            issues.append(
                ValidationIssue(
                    code="barre_not_allowed",
                    message=f"简易版禁止横按：手指 {finger} 覆盖弦 {strings}",
                    bar=bar,
                    beat=beat,
                )
            )

    # Monotonicity: a higher finger must not press a lower fret.
    finger_fret = {
        n.fingering.finger_left: n.fingering.fret
        for n in group
        if n.fingering.finger_left is not None
    }
    ordered = sorted(finger_fret.items())
    for (_, fret_low), (_, fret_high) in zip(ordered, ordered[1:]):
        if fret_high < fret_low:
            issues.append(
                ValidationIssue(
                    code="finger_conflict",
                    message=f"指法顺序不单调：手指-品位映射 {ordered}",
                    bar=bar,
                    beat=beat,
                )
            )
    return issues


def _barres_in_group(group: tuple[TabNote, ...]) -> int:
    by_finger: dict[int, list[TabNote]] = defaultdict(list)
    for note in group:
        if note.fingering.finger_left is not None:
            by_finger[note.fingering.finger_left].append(note)
    return sum(1 for sharing in by_finger.values() if len(sharing) >= 2)


def _check_per_beat(
    groups: Sequence[tuple[Fraction, tuple[TabNote, ...]]],
    profile: DifficultyProfile,
    time_signature: tuple[int, int],
    length: Fraction,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    counts: dict[Fraction, int] = defaultdict(int)
    for beat, group in groups:
        quarter = Fraction(int(beat / QUARTER)) * QUARTER
        counts[quarter] += len(group)
    for quarter, count in sorted(counts.items()):
        if count > profile.max_notes_per_beat:
            issues.append(
                ValidationIssue(
                    code="too_many_notes",
                    message=f"每拍 {count} 音超过上限 {profile.max_notes_per_beat}",
                    bar=int(quarter / length) + 1,
                    beat=quarter,
                )
            )
    return issues
