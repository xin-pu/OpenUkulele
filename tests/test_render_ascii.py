"""ASCII renderer tests: alignment, header, bar lines."""



from uketab.models import Arrangement, Fingering, TabNote
from uketab.render.ascii import render_ascii
from uketab.timing import EIGHTH

from conftest import tp


def arrangement_of(notes, difficulty="easy", grid=EIGHTH):
    tab_notes = tuple(
        TabNote(
            note=n,
            fingering=Fingering(string=s, fret=f, finger_left=None if f == 0 else 1),
        )
        for n, s, f in notes
    )
    return Arrangement(
        difficulty=difficulty,
        tempo_bpm=120.0,
        time_signature=(4, 4),
        notes=tab_notes,
        grid=grid,
    )


def test_header_contains_tempo_and_tuning():
    text = render_ascii(arrangement_of([(tp(0, 60), 3, 0)]))
    assert "tempo 120" in text
    assert "A=A4" in text and "E=E4" in text and "C=C4" in text and "G=G4" in text
    assert "4/4" in text


def test_four_lines_per_bar_equal_length():
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(0, 67), 4, 0), (tp(1, 72), 1, 3)])
    text = render_ascii(arr)
    lines = text.splitlines()
    staff = [line for line in lines if line[:2] in ("A|", "E|", "C|", "G|")]
    assert len(staff) == 4
    lengths = {len(line) for line in staff}
    assert len(lengths) == 1  # vertical alignment


def test_bar_line_and_number_present():
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(5, 62), 3, 2)])
    text = render_ascii(arr)
    assert "[1]" in text and "[2]" in text
    assert text.count("|") >= 8


def test_simultaneous_group_shares_one_column():
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(0, 67), 4, 0), (tp(1, 69), 1, 0)])
    text = render_ascii(arr)
    c_line = next(line for line in text.splitlines() if line.startswith("C|"))
    g_line = next(line for line in text.splitlines() if line.startswith("G|"))
    a_line = next(line for line in text.splitlines() if line.startswith("A|"))
    # C and G sound in the same (first) column; A sounds in a later one.
    assert c_line.index("0") == g_line.index("0")
    assert a_line.index("0") > c_line.index("0")


def test_two_digit_frets_keep_alignment():
    arr = arrangement_of([(tp(0, 81), 1, 12), (tp(1, 60), 3, 0)])
    text = render_ascii(arr)
    staff = [line for line in text.splitlines() if line[:2] in ("A|", "E|", "C|", "G|")]
    assert len({len(line) for line in staff}) == 1
    assert "12" in staff[0]


def test_rest_columns_keep_time():
    # Notes on beats 0 and 2: the gap renders as rest columns.
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(2, 62), 3, 2)])
    text = render_ascii(arr)
    c_line = next(line for line in text.splitlines() if line.startswith("C|"))
    # After the prefix "[1]", the second 0 appears exactly four cells later.
    body = c_line.split("[1]")[1]
    cells = [body[i : i + 3] for i in range(0, len(body.rstrip("|")), 3)]
    assert cells[0].startswith("0")
    assert all(set(cell) == {"-"} for cell in cells[1:4])
    assert cells[4].startswith("2")
