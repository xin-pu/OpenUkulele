"""Easy / hard retention policy.

The arranger decides which pitches survive in each time slice and what
musical role they carry; it never invents pitches that are not present in
the input. Fret/string assignment is *not* decided here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Sequence

from .errors import ArrangementError
from .models import Difficulty, TimedPitch
from .timing import (
    EIGHTH,
    QUARTER,
    SIXTEENTH,
    Bar,
    TimeSlice,
    bar_length,
    group_slices,
    split_bars,
)
from .tuning import HIGH_G, Tuning, enumerate_candidates


@dataclass(frozen=True)
class DifficultyProfile:
    """Constraints a difficulty imposes on candidate fingerings."""

    difficulty: Difficulty
    grid: Fraction
    max_fret: int
    max_span: int
    allow_barre: bool
    max_simultaneous: int
    max_notes_per_beat: int


#: Easy: open strings and frets 0-5, at most two simultaneous notes, no barre.
EASY_PROFILE = DifficultyProfile(
    difficulty="easy",
    grid=EIGHTH,
    max_fret=5,
    max_span=4,
    allow_barre=False,
    max_simultaneous=2,
    max_notes_per_beat=8,
)

#: Hard: frets 0-15, up to four notes per beat, barre allowed (reported).
HARD_PROFILE = DifficultyProfile(
    difficulty="hard",
    grid=SIXTEENTH,
    max_fret=15,
    max_span=5,
    allow_barre=True,
    max_simultaneous=4,
    max_notes_per_beat=4,
)


def hard_profile(grid: Fraction) -> DifficultyProfile:
    """Hard profile bound to the detected grid (eighth or sixteenth)."""
    return replace(HARD_PROFILE, grid=grid)


def arrange(
    pitches: Sequence[TimedPitch],
    time_signature: tuple[int, int],
    profile: DifficultyProfile,
    tuning: Tuning = HIGH_G,
) -> tuple[Bar, ...]:
    """Assign roles per time slice according to the difficulty policy."""
    if not pitches:
        raise ArrangementError("没有可用于编配的音符", "检查输入文件的音符事件")

    bars = split_bars(group_slices(pitches), time_signature)
    arranged: list[Bar] = []
    for bar in bars:
        bass_offsets = _bass_offsets(bar, time_signature)
        new_slices = []
        for slice_ in bar.slices:
            offset = slice_.beat - bar.start
            allow_bass = profile.difficulty == "hard" or offset in bass_offsets
            arranged_slice = _arrange_slice(slice_, profile, tuning, allow_bass)
            if arranged_slice.notes:
                new_slices.append(arranged_slice)
        if profile.difficulty == "hard":
            new_slices = _limit_notes_per_beat(new_slices, profile)
        arranged.append(replace(bar, slices=tuple(new_slices)))
    return tuple(arranged)


def arrange_easy(
    pitches: Sequence[TimedPitch], time_signature: tuple[int, int], tuning: Tuning = HIGH_G
) -> tuple[Bar, ...]:
    return arrange(pitches, time_signature, EASY_PROFILE, tuning)


def arrange_hard(
    pitches: Sequence[TimedPitch],
    time_signature: tuple[int, int],
    grid: Fraction = SIXTEENTH,
    tuning: Tuning = HIGH_G,
) -> tuple[Bar, ...]:
    return arrange(pitches, time_signature, hard_profile(grid), tuning)


def _in_playable_range(pitch: int, profile: DifficultyProfile, tuning: Tuning) -> bool:
    return len(enumerate_candidates(pitch, tuning, profile.max_fret)) > 0


def _with_role(pitch: TimedPitch, role: str) -> TimedPitch:
    return replace(pitch, role=role)


def _bass_offsets(bar: Bar, time_signature: tuple[int, int]) -> tuple[Fraction, ...]:
    """Downbeat positions that may carry bass: beats 1 and 3 in 4/4.

    A partial (short) bar only allows its first beat. Half-bar positions
    are only used when they land on an integer beat (e.g. 4/4, not 3/4).
    """
    if not bar.slices:
        return ()
    length = bar_length(time_signature)
    covered = bar.slices[-1].beat + bar.slices[-1].notes[0].duration_beats - bar.start
    if covered < length:
        return (Fraction(0),)
    half = Fraction(length, 2)
    if half.denominator == 1 and half > 0:
        return (Fraction(0), half)
    return (Fraction(0),)


def _arrange_slice(
    slice_: TimeSlice,
    profile: DifficultyProfile,
    tuning: Tuning,
    allow_bass: bool,
) -> TimeSlice:
    notes = slice_.notes  # group_slices sorts by descending pitch
    melody = _with_role(notes[0], "melody")

    if profile.difficulty == "easy":
        if not allow_bass:
            return TimeSlice(beat=slice_.beat, notes=(melody,))
        rest = [n for n in notes[1:] if _in_playable_range(n.pitch, profile, tuning)]
        selected = [melody]
        if rest:
            selected.append(_with_role(rest[0], "bass"))  # lowest playable remaining pitch
        return TimeSlice(beat=slice_.beat, notes=tuple(selected))

    # Hard: melody + bass + up to two harmony notes.
    selected = [melody]
    rest = [n for n in notes[1:] if _in_playable_range(n.pitch, profile, tuning)]
    if rest:
        selected.append(_with_role(rest[-1], "bass"))  # lowest remaining pitch
        harmony_budget = profile.max_simultaneous - 2
        selected.extend(_with_role(n, "harmony") for n in rest[:-1][:harmony_budget])
    return TimeSlice(beat=slice_.beat, notes=tuple(selected[: profile.max_simultaneous]))


def _limit_notes_per_beat(slices: Sequence[TimeSlice], profile: DifficultyProfile) -> list[TimeSlice]:
    """Enforce ``max_notes_per_beat`` by dropping lowest-priority notes.

    Priority: melody > bass > harmony; earlier onsets and higher pitches
    win within the same role. Quarter-beat windows never cross bar lines
    for standard dyadic time signatures.
    """
    role_rank = {"melody": 0, "bass": 1, "harmony": 2}
    by_quarter: dict[Fraction, list[tuple]] = {}
    for slice_ in slices:
        quarter = Fraction(int(slice_.beat / QUARTER)) * QUARTER
        for index, note in enumerate(slice_.notes):
            # index breaks ties between identical pitches (audio input
            # can transcribe duplicates) without ordering TimedPitch.
            by_quarter.setdefault(quarter, []).append(
                (role_rank[note.role], slice_.beat, -note.pitch, index, note)
            )

    kept: set[int] = set()
    for quarter in sorted(by_quarter):
        bucket = sorted(by_quarter[quarter])
        kept.update(id(entry[-1]) for entry in bucket[: profile.max_notes_per_beat])

    result = []
    for slice_ in slices:
        remaining = tuple(n for n in slice_.notes if id(n) in kept)
        if remaining:
            result.append(TimeSlice(beat=slice_.beat, notes=remaining))
    return result
