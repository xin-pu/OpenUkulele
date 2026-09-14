"""High-G tuning mapping tests."""

from uketab.tuning import (
    HIGH_G,
    enumerate_candidates,
    pitch_name,
    playable_pitch_range,
)


def test_multiple_candidates_for_same_pitch():
    # G4 (67): open G string, fret 7 on C string, fret 3 on E string.
    assert set(enumerate_candidates(67, HIGH_G, 15)) == {(4, 0), (3, 7), (2, 3)}


def test_reentrant_g_never_treated_as_bass():
    # C4 (60) is only on the C string: G4 (67) is higher and must not match.
    assert enumerate_candidates(60, HIGH_G, 15) == ((3, 0),)


def test_unplayable_pitches_have_no_candidates():
    assert enumerate_candidates(59, HIGH_G, 15) == ()  # below C4
    assert enumerate_candidates(85, HIGH_G, 15) == ()  # above max fret 15


def test_fifteen_fret_boundary():
    low, high = playable_pitch_range(HIGH_G, 15)
    assert (low, high) == (60, 84)  # C4 .. C6 (A string fret 15)
    assert (4, 15) in enumerate_candidates(82, HIGH_G, 15)  # B5 on G string
    assert (1, 15) in enumerate_candidates(84, HIGH_G, 15)  # C6 on A string
    assert enumerate_candidates(84, HIGH_G, 14) == ()


def test_max_fret_limits_easy_candidates():
    # E5 (76) needs fret >= 7 -> invisible to the easy 0-5 window.
    assert enumerate_candidates(76, HIGH_G, 5) == ()
    assert len(enumerate_candidates(74, HIGH_G, 5)) == 1  # D5 only on A string fret 5


def test_pitch_names():
    assert pitch_name(69) == "A4"
    assert pitch_name(60) == "C4"
    assert pitch_name(67) == "G4"
