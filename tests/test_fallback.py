"""Fallback ladder tests: degradation order and terminal failure.

Bars are built directly (not via arrange()) so the roles under test stay
exactly as specified. Scenarios were verified against the real candidate
enumeration:
  A 74m+83h+67b hard: every 3-note combo dies on span/fingers; melody+bass
    is fine  -> remove_harmony
  B 74m+65b easy: (1,5)+(2,1) needs a 5th finger; (1,5)+(3,5) is a
    non-adjacent same-fret conflict -> remove_bass
  C 79m+83h+62b hard: harmony and bass each block -> chained steps
"""

from fractions import Fraction

from uketab.arrangement import EASY_PROFILE, hard_profile
from uketab.fallback import LADDER, resolve_with_fallback
from uketab.models import TimedPitch
from uketab.timing import EIGHTH, Bar, TimeSlice


def tp(pitch, role):
    return TimedPitch(
        beat=Fraction(0), duration_beats=Fraction(1, 2), pitch=pitch, velocity=0.8, role=role
    )


def bar_of(*specs):
    slice_ = TimeSlice(beat=Fraction(0), notes=tuple(tp(p, r) for p, r in specs))
    return (Bar(index=1, start=Fraction(0), slices=(slice_,)),)


def resolve(bars, profile):
    return resolve_with_fallback(bars, profile, (4, 4))


def test_ladder_order_is_harmony_then_bass_then_melody():
    assert LADDER == ("remove_harmony", "remove_bass", "melody_only")


def test_remove_harmony_recovers_hard_bar():
    result = resolve(bar_of((74, "melody"), (83, "harmony"), (67, "bass")), hard_profile(EIGHTH))
    assert result.success
    assert [(a.bar, a.step) for a in result.actions] == [(1, "remove_harmony")]
    kept_roles = {n.note.role for n in result.solutions[0].notes}
    assert kept_roles == {"melody", "bass"}


def test_remove_bass_when_harmony_absent():
    result = resolve(bar_of((74, "melody"), (65, "bass")), EASY_PROFILE)
    assert result.success
    assert [(a.bar, a.step) for a in result.actions] == [(1, "remove_bass")]
    assert all(n.note.role == "melody" for n in result.solutions[0].notes)


def test_ladder_chains_steps():
    result = resolve(
        bar_of((79, "melody"), (83, "harmony"), (62, "bass")), hard_profile(EIGHTH)
    )
    assert result.success
    assert [a.step for a in result.actions] == ["remove_harmony", "remove_bass"]
    assert all(n.note.role == "melody" for n in result.solutions[0].notes)


def test_terminal_failure_reports_bar():
    bars = bar_of((85, "melody"))
    result = resolve(bars, hard_profile(EIGHTH))
    assert not result.success
    assert result.failed_bars == (1,)
    assert result.solutions[0].notes == ()


def test_clean_bar_needs_no_fallback():
    result = resolve(bar_of((72, "melody"), (60, "bass")), hard_profile(EIGHTH))
    assert result.success
    assert result.actions == ()
    assert result.report.passed


def test_failed_bar_kept_alongside_solved_bar():
    bad = Bar(
        index=1,
        start=Fraction(0),
        slices=(TimeSlice(beat=Fraction(0), notes=(tp(85, "melody"),)),),
    )
    good_slice = TimeSlice(beat=Fraction(4), notes=(tp(72, "melody"),))
    good = Bar(index=2, start=Fraction(4), slices=(good_slice,))
    result = resolve((bad, good), hard_profile(EIGHTH))
    assert not result.success
    assert result.failed_bars == (1,)
    assert result.solutions[1].feasible  # bar 2 survives bar 1's failure
