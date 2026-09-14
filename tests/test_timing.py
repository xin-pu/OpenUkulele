"""Quantization, slicing and bar-division tests."""

from fractions import Fraction

import pytest

from uketab.errors import InputError
from uketab.models import NoteEvent
from uketab.timing import (
    EIGHTH,
    SIXTEENTH,
    bar_length,
    group_slices,
    has_sixteenth_precision,
    normalize_events,
    quantize_duration,
    quantize_onset,
    seconds_to_beats,
    split_bars,
)


def ev(onset, duration=0.25, pitch=72):
    return NoteEvent(onset=onset, duration=duration, pitch=pitch, velocity=0.8, source="midi")


def test_seconds_to_beats():
    assert seconds_to_beats(0.5, 120) == 1
    assert seconds_to_beats(1.0, 90) == Fraction(3, 2)


def test_seconds_to_beats_rejects_bad_tempo():
    with pytest.raises(InputError):
        seconds_to_beats(1.0, 0)


def test_onset_snaps_to_nearest_eighth():
    assert quantize_onset(Fraction(11, 20), EIGHTH) == Fraction(1, 2)
    assert quantize_onset(Fraction(3, 10), EIGHTH) == Fraction(1, 2)
    assert quantize_onset(Fraction(1, 5), EIGHTH) == 0


def test_duration_bumped_to_one_grid():
    assert quantize_duration(Fraction(1, 20), EIGHTH) == EIGHTH
    assert quantize_duration(Fraction(3, 4), EIGHTH) == 1  # rounds to whole beat
    assert quantize_duration(Fraction(5, 8), EIGHTH) == Fraction(1, 2)  # 1.25 grids -> 1


def test_normalize_events_quantizes():
    events = [ev(0.26, 0.1)]  # 0.52 beats -> 1/2; 0.2 beats -> 1 grid
    pitches = normalize_events(events, 120, EIGHTH)
    assert len(pitches) == 1
    assert pitches[0].beat == Fraction(1, 2)
    assert pitches[0].duration_beats == EIGHTH


def test_sixteenth_precision_detected():
    events = [ev(0.0), ev(0.125)]  # 0 and 1/4 beat at 120 BPM
    assert has_sixteenth_precision(events, 120) is True


def test_no_sixteenth_precision_for_eighth_grid():
    events = [ev(0.0), ev(0.25), ev(0.5)]
    assert has_sixteenth_precision(events, 120) is False


def test_no_triplets_produced():
    # 1/3 of a beat snaps to the dyadic grid, never to a triplet position.
    assert quantize_onset(Fraction(1, 3), EIGHTH) == Fraction(1, 2)
    assert quantize_onset(Fraction(1, 3), SIXTEENTH) == Fraction(1, 4)


def test_group_slices_sorts_by_descending_pitch():
    pitches = normalize_events(
        [ev(0.0, 0.25, pitch=72), ev(0.0, 0.25, pitch=60), ev(0.0, 0.25, pitch=67)],
        120,
        EIGHTH,
    )
    slices = group_slices(pitches)
    assert len(slices) == 1
    assert [p.pitch for p in slices[0].notes] == [72, 67, 60]


def test_split_bars_and_partial_last_bar():
    pitches = normalize_events(
        [ev(0.0), ev(0.25), ev(1.0), ev(1.25), ev(2.5)], 120, EIGHTH
    )
    bars = split_bars(group_slices(pitches), (4, 4))
    assert [b.index for b in bars] == [1, 2]
    assert bars[0].start == 0
    assert bars[1].start == 4
    assert len(bars[1].slices) == 1  # partial bar holds only its sounding slot


def test_bar_length():
    assert bar_length((4, 4)) == 4
    assert bar_length((3, 4)) == 3
    assert bar_length((6, 8)) == 3
