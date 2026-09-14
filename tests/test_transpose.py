"""--transpose unit tests."""

from uketab.cli import apply_transpose
from uketab.models import NoteEvent


def ev(pitch):
    return NoteEvent(onset=0.0, duration=0.5, pitch=pitch, velocity=0.8, source="midi")


def test_apply_transpose_preserves_intervals():
    events = [ev(60), ev(62), ev(64)]
    out, folded = apply_transpose(events, 3)
    assert [e.pitch for e in out] == [63, 65, 67]
    assert folded == 0


def test_apply_transpose_folds_out_of_range_octaves():
    # 48 (C3) + 0 stays below range -> must fold up one octave to 60.
    events = [ev(48), ev(96)]  # C3 and C7
    out, folded = apply_transpose(events, 0)
    assert [e.pitch for e in out] == [60, 84]  # folded into C4..C6
    assert folded == 2


def test_apply_transpose_shift_then_fold():
    events = [ev(70)]  # Bb4
    out, folded = apply_transpose(events, 24)  # +2 octaves = 94 -> fold -12 -> 82
    assert [e.pitch for e in out] == [82]
    assert folded == 1


def test_apply_transpose_zero_returns_same():
    events = [ev(60), ev(72)]
    out, folded = apply_transpose(events, 0)
    assert [e.pitch for e in out] == [60, 72]
    assert folded == 0
