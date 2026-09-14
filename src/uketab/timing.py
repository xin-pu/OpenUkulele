"""Tempo handling, dyadic quantization, time slices and bar division.

Beats are exact :class:`~fractions.Fraction` values. Quantization snaps
onsets to the nearest grid position (eighth or sixteenth); durations become
whole grid multiples with a minimum of one grid. Triplets are never
produced.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence

from .errors import InputError
from .models import NoteEvent, TimedPitch

# Grid constants are expressed in beats: one beat equals a quarter note.
EIGHTH = Fraction(1, 2)  # eighth note
SIXTEENTH = Fraction(1, 4)  # sixteenth note
QUARTER = Fraction(1)  # quarter note

#: Rationale for limit_denominator: float onsets carry binary noise; a
#: million-denominator rational is far finer than any audible timing while
#: keeping the beat arithmetic exact afterwards.
_FLOAT_DENOM_LIMIT = 10**6


@dataclass(frozen=True)
class TimeSlice:
    """All pitches sounding at one grid position."""

    beat: Fraction
    notes: tuple[TimedPitch, ...]


@dataclass(frozen=True)
class Bar:
    """A measure holding its quantized slices; 1-based ``index``."""

    index: int
    start: Fraction
    slices: tuple[TimeSlice, ...]


def bar_length(time_signature: tuple[int, int]) -> Fraction:
    numerator, denominator = time_signature
    return Fraction(numerator * 4, denominator)


def _to_fraction(value: float) -> Fraction:
    return Fraction(value).limit_denominator(_FLOAT_DENOM_LIMIT)


def seconds_to_beats(onset_seconds: float, tempo_bpm: float) -> Fraction:
    if tempo_bpm <= 0:
        raise InputError(f"速度必须为正数，收到 {tempo_bpm}", "使用 --tempo 提供正的 BPM")
    return _to_fraction(onset_seconds) * _to_fraction(tempo_bpm) / 60


def quantize_onset(beat: Fraction, grid: Fraction) -> Fraction:
    return Fraction(round(beat / grid)) * grid


def quantize_duration(duration_beats: Fraction, grid: Fraction) -> Fraction:
    multiples = round(duration_beats / grid)
    return grid * max(multiples, 1)


def normalize_events(
    events: Sequence[NoteEvent], tempo_bpm: float, grid: Fraction = EIGHTH
) -> tuple[TimedPitch, ...]:
    """Convert second-based events to beat-based, quantized pitches.

    Roles are provisional here (``melody``); :mod:`uketab.arrangement`
    assigns the final musical roles.
    """
    normalized: list[TimedPitch] = []
    for event in events:
        beat = quantize_onset(seconds_to_beats(event.onset, tempo_bpm), grid)
        duration = quantize_duration(seconds_to_beats(event.duration, tempo_bpm), grid)
        normalized.append(
            TimedPitch(
                beat=beat,
                duration_beats=duration,
                pitch=event.pitch,
                velocity=event.velocity,
                role="melody",
            )
        )
    normalized.sort(key=lambda p: (p.beat, -p.pitch))
    return tuple(normalized)


def has_sixteenth_precision(events: Sequence[NoteEvent], tempo_bpm: float) -> bool:
    """True when any raw onset lands on a sixteenth but not an eighth.

    Detection quantizes each onset to the nearest sixteenth and checks for
    an odd sixteenth index; events aligned to the eighth grid can never
    trigger it.
    """
    for event in events:
        beat = seconds_to_beats(event.onset, tempo_bpm)
        snapped = Fraction(round(beat / SIXTEENTH))
        if snapped % 2 == 1:
            return True
    return False


def group_slices(pitches: Iterable[TimedPitch]) -> list[TimeSlice]:
    """Group pitches by identical (quantized) beat position."""
    by_beat: dict[Fraction, list[TimedPitch]] = {}
    for pitch in pitches:
        by_beat.setdefault(pitch.beat, []).append(pitch)
    return [
        TimeSlice(beat=beat, notes=tuple(sorted(notes, key=lambda p: -p.pitch)))
        for beat, notes in sorted(by_beat.items())
    ]


def split_bars(slices: Sequence[TimeSlice], time_signature: tuple[int, int]) -> list[Bar]:
    """Distribute slices into measures; the final bar may be partial."""
    length = bar_length(time_signature)
    bars: list[tuple[Fraction, list[TimeSlice]]] = []
    for slice_ in slices:
        index = int(slice_.beat / length)
        start = index * length
        if not bars or bars[-1][0] != start:
            bars.append((start, []))
        bars[-1][1].append(slice_)
    return [
        Bar(index=i + 1, start=start, slices=tuple(group)) for i, (start, group) in enumerate(bars)
    ]
