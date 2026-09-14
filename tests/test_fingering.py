"""Fingering solver tests: candidates, finger assignment, DP, barre."""

from fractions import Fraction

from uketab.arrangement import EASY_PROFILE, hard_profile
from uketab.fingering import (
    COST_BARRE,
    COST_NON_OPEN,
    COST_SPAN,
    generate_candidates,
    solve_bar,
)
from uketab.timing import EIGHTH, group_slices, split_bars

from conftest import tp


def slice_of(*pitches, beat=0, roles=None):
    notes = [
        tp(beat, p, role=(roles[i] if roles else "melody"))
        for i, p in enumerate(pitches)
    ]
    return group_slices(notes)[0]


def solve_single(*pitches, profile, beat=0, roles=None, ts=(4, 4)):
    slice_ = slice_of(*pitches, beat=beat, roles=roles)
    bars = split_bars([slice_], ts)
    return solve_bar(bars[0], profile)


def test_open_string_candidates_are_fingerless():
    candidates = generate_candidates(slice_of(60), EASY_PROFILE)
    assert candidates
    for candidate in candidates:
        frets = {f.fret for f in candidate.fingerings}
        if frets == {0}:
            assert all(f.finger_left is None for f in candidate.fingerings)


def test_same_string_combinations_pruned():
    # 67 and 60 both want the C string; combos must avoid string collisions.
    candidates = generate_candidates(slice_of(67, 60), EASY_PROFILE)
    assert candidates
    for candidate in candidates:
        strings = [f.string for f in candidate.fingerings]
        assert len(set(strings)) == len(strings)


def test_unreachable_pitch_yields_no_candidates():
    assert generate_candidates(slice_of(76), EASY_PROFILE) == ()  # > fret 5
    assert generate_candidates(slice_of(59), hard_profile(EIGHTH)) == ()  # below C4


def test_span_pruned_for_easy():
    # E5 needs fret >= 7 everywhere; alone it is simply unreachable at 0-5.
    candidates = generate_candidates(slice_of(74, 60), EASY_PROFILE)  # D5 + C4
    for candidate in candidates:
        assert candidate.span <= EASY_PROFILE.max_span


def test_hard_barre_detected_on_consecutive_strings():
    # E5 (1,7) + B4 (2,7): same fret, adjacent strings. The barre shape
    # (cost 8) beats every alternative (next best costs 21), so the DP
    # lands on one shared finger.
    solution = solve_single(76, 71, profile=hard_profile(EIGHTH))
    assert solution.feasible
    fingers = [n.fingering.finger_left for n in solution.notes]
    frets = [n.fingering.fret for n in solution.notes]
    assert frets == [7, 7]
    assert len(fingers) == 2 and len(set(fingers)) == 1  # shared finger = barre


def test_easy_avoids_shared_fingers():
    # G4 + D#4: easy forbids barre, so the solver uses open G + one finger.
    solution = solve_single(67, 63, profile=EASY_PROFILE)
    assert solution.feasible
    fingers = [n.fingering.finger_left for n in solution.notes]
    assert len([f for f in fingers if f is not None]) == len(set(f for f in fingers if f is not None))


def test_finger_assignment_monotonic_with_fret():
    # C5 (1,3) + E4 (2,0): fret 3 gets finger 1, open string none.
    solution = solve_single(72, 64, profile=hard_profile(EIGHTH))
    assert solution.feasible
    by_string = {n.fingering.string: n.fingering for n in solution.notes}
    assert by_string[1].fret == 3 and by_string[1].finger_left == 1
    assert by_string[2].fret == 0 and by_string[2].finger_left is None


def test_right_hand_assignment():
    # melody by string map, bass gets p
    solution = solve_single(
        72, 60, profile=hard_profile(EIGHTH), roles=["melody", "bass"]
    )
    rights = {n.note.role: n.fingering.finger_right for n in solution.notes}
    assert rights["bass"] == "p"
    assert rights["melody"] in {"a", "m", "i"}


def test_dp_finds_minimum_cost_path():
    # G4-G#4-A4: the cheapest realization ends on the open A string and
    # costs 3 (0 for the open G, 3 for one fretted note, 3 for the open A;
    # no shifts because open strings carry no position).
    notes = [tp(0, 67), tp(Fraction(1, 2), 68), tp(1, 69)]
    bars = split_bars(group_slices(notes), (4, 4))
    solution = solve_bar(bars[0], EASY_PROFILE)
    assert solution.feasible
    assert solution.cost == 3

    # Brute-force optimality: no candidate path is cheaper.
    from uketab.fingering import generate_candidates, _transfer_cost

    per_slice = [generate_candidates(s, EASY_PROFILE) for s in bars[0].slices]
    import itertools

    best = min(
        path[0].static_cost
        + sum(_transfer_cost(a, b) for a, b in zip(path, path[1:]))
        for path in itertools.product(*per_slice)
    )
    assert solution.cost == best


def test_infeasible_slice_reports_zero_candidates():
    solution = solve_single(85, profile=hard_profile(EIGHTH))
    assert not solution.feasible
    assert solution.slice_candidate_counts == (0,)


def test_transfer_cost_components():
    from uketab.fingering import _transfer_cost
    from uketab.models import Fingering

    def candidate(spec):  # spec: list of (string, fret)
        frets = [f for _, f in spec if f > 0]
        span = max(frets) - min(frets) if frets else 0
        fret_map = dict(spec)
        return type("C", (), {
            "fingerings": tuple(Fingering(string=s, fret=f) for s, f in spec),
            "span": span,
            "barre_count": 0,
            "non_open": len(frets),
            "position": min(frets) if frets else None,
            "static_cost": COST_SPAN * span + COST_NON_OPEN * len(frets) + COST_BARRE * 0,
            "fret_on": lambda self, string: fret_map.get(string),
        })()

    open_c = candidate([(3, 0)])
    fret5 = candidate([(1, 5)])
    same = candidate([(1, 5)])
    # No shift between identical positions; movement counted on shared strings.
    cost = _transfer_cost(fret5, same)
    assert cost == 0 + 0 + fret5.static_cost
    # Shift from open (position None) is not counted as a move.
    assert _transfer_cost(open_c, fret5) == 0 + 0 + fret5.static_cost
