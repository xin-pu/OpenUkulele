"""--transpose unit tests."""

import pytest

from uketab.cli import apply_transpose
from uketab.errors import ArrangementError
from uketab.models import NoteEvent


def ev(pitch):
    return NoteEvent(onset=0.0, duration=0.5, pitch=pitch, velocity=0.8, source="midi")


def test_apply_transpose_preserves_intervals():
    events = [ev(60), ev(62), ev(64)]
    out, folded = apply_transpose(events, 3)
    assert [e.pitch for e in out] == [63, 65, 67]
    assert folded == 0


def test_apply_transpose_rejects_notes_outside_instrument_range():
    with pytest.raises(ArrangementError, match="超出尤克里里音域"):
        apply_transpose([ev(48), ev(96)], 0)


def test_apply_transpose_rejects_shift_that_exceeds_instrument_range():
    with pytest.raises(ArrangementError, match="超出尤克里里音域"):
        apply_transpose([ev(70)], 24)


def test_apply_transpose_rejects_mixed_range_instead_of_breaking_interval():
    # C4 stays in range while B3 would be folded to B4 by the old algorithm,
    # changing the original one-semitone interval into an eleven-semitone leap.
    with pytest.raises(ArrangementError, match="超出尤克里里音域"):
        apply_transpose([ev(59), ev(60)], 0)


def test_apply_transpose_zero_returns_same():
    events = [ev(60), ev(72)]
    out, folded = apply_transpose(events, 0)
    assert [e.pitch for e in out] == [60, 72]
    assert folded == 0
