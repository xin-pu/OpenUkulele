"""Validation tests: one test per issue code plus statistics."""

from fractions import Fraction

from uketab.arrangement import EASY_PROFILE, hard_profile
from uketab.models import Fingering, TabNote
from uketab.timing import EIGHTH
from uketab.validation import validate_notes

from conftest import tp


def tab(beat, pitch, string, fret, finger=None, right="i", role="melody", dur=None):
    note = tp(beat, pitch, role=role, dur=dur)
    fingering = Fingering(string=string, fret=fret, finger_left=finger, finger_right=right)
    return TabNote(note=note, fingering=fingering)


def codes(report):
    return {issue.code for issue in report.errors}


def test_same_string_conflict():
    notes = [tab(0, 72, 1, 3, finger=1), tab(0, 67, 1, 0)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "same_string_conflict" in codes(report)
    assert not report.passed


def test_out_of_range():
    notes = [tab(0, 76, 1, 7, finger=1)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "out_of_range" in codes(report)


def test_too_many_notes_simultaneous():
    notes = [
        tab(0, 72, 1, 3, finger=1),
        tab(0, 67, 2, 3, finger=1),
        tab(0, 64, 3, 4, finger=2),
    ]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "too_many_notes" in codes(report)


def test_too_many_notes_per_beat_hard():
    s = Fraction(1, 4)
    notes = [
        tab(0, 72, 1, 3, finger=1),
        tab(s, 71, 1, 2, finger=1),
        tab(2 * s, 69, 1, 0),
        tab(3 * s, 67, 2, 3, finger=1),
        tab(3 * s, 64, 3, 4, finger=2),
    ]
    report = validate_notes(notes, (4, 4), hard_profile(EIGHTH))
    assert "too_many_notes" in codes(report)


def test_span_exceeded():
    # Span counts fretted notes only; frets 1 and 7 span 6 (hard limit 5).
    notes = [tab(0, 70, 1, 1, finger=1), tab(0, 71, 2, 7, finger=4)]
    report = validate_notes(notes, (4, 4), hard_profile(EIGHTH))
    assert "span_exceeded" in codes(report)


def test_finger_conflict_two_frets_one_finger():
    notes = [tab(0, 72, 1, 3, finger=1), tab(0, 66, 2, 2, finger=1)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "finger_conflict" in codes(report)


def test_finger_conflict_missing_finger():
    notes = [tab(0, 72, 1, 3, finger=None)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "finger_conflict" in codes(report)


def test_barre_not_allowed_in_easy():
    notes = [tab(0, 67, 2, 3, finger=1), tab(0, 63, 3, 3, finger=1)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "barre_not_allowed" in codes(report)
    # the same shape is fine for hard
    report_hard = validate_notes(notes, (4, 4), hard_profile(EIGHTH))
    assert "barre_not_allowed" not in codes(report_hard)


def test_unplayable_pitch():
    notes = [tab(0, 59, 3, -1)]  # below the instrument
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert "unplayable_pitch" in codes(report)


def test_valid_arrangement_passes_with_stats():
    notes = [
        tab(0, 72, 1, 3, finger=1),
        tab(Fraction(1, 2), 74, 1, 5, finger=1),
        tab(1, 72, 1, 3, finger=1),
    ]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    assert report.passed
    assert report.max_span == 0  # single fretted note per group
    assert report.shift_count == 2  # position 3 -> 5 -> 3
    assert 0.0 <= report.difficulty_score <= 1.0


def test_shift_and_span_statistics():
    # Group 1: frets 3+7 (span 4, position 3); group 2: frets 5+7 (span 2,
    # position 5) -> one shift, max span 4.
    notes = [
        tab(0, 72, 1, 3, finger=1),
        tab(0, 71, 2, 7, finger=4),
        tab(Fraction(1, 2), 74, 1, 5, finger=1),
        tab(Fraction(1, 2), 71, 2, 7, finger=2),
    ]
    report = validate_notes(notes, (4, 4), hard_profile(EIGHTH))
    assert report.shift_count == 1
    assert report.max_span == 4
    assert report.barre_count == 0


def test_barre_counted_in_hard():
    notes = [tab(0, 67, 2, 3, finger=1), tab(0, 63, 3, 3, finger=1)]
    report = validate_notes(notes, (4, 4), hard_profile(EIGHTH))
    assert report.barre_count == 1


def test_issue_carries_bar_and_beat():
    notes = [tab(Fraction(9, 2), 72, 1, 3, finger=1), tab(Fraction(9, 2), 67, 1, 0)]
    report = validate_notes(notes, (4, 4), EASY_PROFILE)
    issue = next(i for i in report.errors if i.code == "same_string_conflict")
    assert issue.bar == 2  # beats 4-8 form the second 4/4 measure
    assert issue.beat == Fraction(9, 2)
