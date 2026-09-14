"""Easy / hard retention policy tests."""

from fractions import Fraction

from uketab.arrangement import EASY_PROFILE, arrange, hard_profile
from uketab.timing import EIGHTH, SIXTEENTH, normalize_events
from uketab.models import NoteEvent

from conftest import tp


def events(notes, tempo=120):
    return [
        NoteEvent(onset=beat * 60 / tempo, duration=dur * 60 / tempo, pitch=p, velocity=0.8, source="midi")
        for beat, dur, p in notes
    ]


def test_easy_keeps_highest_as_melody():
    pitches = [tp(0, 72), tp(0, 60), tp(0, 67)]
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    notes = bars[0].slices[0].notes
    assert len(notes) == 2  # melody + at most one bass
    assert notes[0].pitch == 72 and notes[0].role == "melody"


def test_easy_max_two_simultaneous():
    pitches = [tp(0, 72), tp(0, 67), tp(0, 64), tp(0, 60)]
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    assert len(bars[0].slices[0].notes) <= 2


def test_easy_bass_only_on_beats_one_and_three():
    # Off-beat slice keeps melody alone.
    pitches = [tp(0, 72), tp(0, 60), tp(1, 74), tp(1, 62)]
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    beat0 = bars[0].slices[0].notes
    beat1 = bars[0].slices[1].notes
    assert any(n.role == "bass" for n in beat0)
    assert not any(n.role == "bass" for n in beat1)


def test_easy_bass_must_be_in_fret_range():
    # 54 (F#3) is below the instrument: no bass is added.
    pitches = [tp(0, 72), tp(0, 54)]
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    assert [n.role for n in bars[0].slices[0].notes] == ["melody"]


def test_hard_keeps_melody_bass_and_two_harmony():
    pitches = [tp(0, 72), tp(0, 69), tp(0, 67), tp(0, 64), tp(0, 60)]
    bars = arrange(pitches, (4, 4), hard_profile(EIGHTH))
    notes = bars[0].slices[0].notes
    assert len(notes) == 4
    assert [n.role for n in notes] == ["melody", "bass", "harmony", "harmony"]
    assert notes[0].pitch == 72 and notes[1].pitch == 60


def test_hard_caps_notes_per_beat():
    # Two 16th slices in one quarter: at most 4 notes across the beat.
    s = Fraction(1, 4)
    pitches = [tp(0, 72, dur=s), tp(0, 67, dur=s), tp(s, 74, dur=s), tp(s, 69, dur=s)]
    bars = arrange(pitches, (4, 4), hard_profile(SIXTEENTH))
    total = sum(len(s.notes) for s in bars[0].slices)
    assert total <= 4


def test_hard_prioritizes_melody_under_per_beat_cap():
    s = Fraction(1, 4)
    pitches = [tp(0, 72, dur=s), tp(0, 67, dur=s), tp(s, 74, dur=s), tp(s, 60, dur=s)]
    bars = arrange(pitches, (4, 4), hard_profile(SIXTEENTH))
    kept = [n.pitch for s in bars[0].slices for n in s.notes]
    assert 72 in kept and 74 in kept  # melodies survive the cap
    assert len(kept) <= 4


def test_arranger_never_invents_pitches():
    pitches = [tp(0, 72)]
    bars = arrange(pitches, (4, 4), hard_profile(EIGHTH))
    result = {n.pitch for s in bars[0].slices for n in s.notes}
    assert result <= {72}


def test_partial_bar_gets_bass_only_on_first_beat():
    # Bar shorter than a full 4/4: only offset 0 may carry bass.
    pitches = [tp(0, 72), tp(0, 60), tp(1, 74), tp(1, 62)]
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    # a single partial bar: beat 1 has no bass
    assert not any(n.role == "bass" for n in bars[0].slices[1].notes)


def test_normalize_then_arrange_end_to_end_roles():
    evs = events([(0, 0.5, 72), (0, 0.5, 60), (0.5, 0.5, 74)])
    pitches = normalize_events(evs, 120, EIGHTH)
    bars = arrange(pitches, (4, 4), EASY_PROFILE)
    assert [n.pitch for n in bars[0].slices[0].notes] == [72, 60]
    assert [n.pitch for n in bars[0].slices[1].notes] == [74]
