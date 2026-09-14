"""A4 image renderer tests (skipped when matplotlib is absent)."""

import pytest

pytest.importorskip("matplotlib")

from fractions import Fraction

from uketab.models import Arrangement, Fingering, TabNote
from uketab.render.image import _decompose_duration, build_rhythm, render_pdf, render_png
from uketab.timing import EIGHTH

from conftest import tp


def arrangement_of(notes, difficulty="easy", grid=EIGHTH):
    tab_notes = tuple(
        TabNote(note=n, fingering=Fingering(string=s, fret=f)) for n, s, f in notes
    )
    return Arrangement(
        difficulty=difficulty,
        tempo_bpm=120.0,
        time_signature=(4, 4),
        notes=tab_notes,
        grid=grid,
    )


def test_render_png_single_page(tmp_path):
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(1, 62), 3, 2), (tp(2, 64), 2, 0)])
    paths = render_png(arr, tmp_path / "out.png", title="测试")
    assert len(paths) == 1 and paths[0].name == "out.png"
    raw = paths[0].read_bytes()
    assert raw.startswith(b"\x89PNG")
    assert len(raw) > 10_000


def test_render_png_paginates_long_piece(tmp_path):
    notes = []
    for beat in range(600):  # 150 bars of 4/4
        notes.append((tp(Fraction(beat), 60 + (beat % 12)), 3, beat % 5))
    arr = arrangement_of(notes)
    paths = render_png(arr, tmp_path / "long.png")
    assert len(paths) >= 2
    assert paths[0].name == "long-p01.png"
    assert all(p.exists() for p in paths)


def test_render_pdf(tmp_path):
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(2, 64), 2, 0)])
    path = render_pdf(arr, tmp_path / "out.pdf")
    assert path.read_bytes().startswith(b"%PDF")


def test_portrait_and_landscape_both_work(tmp_path):
    arr = arrangement_of([(tp(0, 60), 3, 0)])
    for orientation in ("portrait", "landscape"):
        paths = render_png(arr, tmp_path / f"{orientation}.png", orientation=orientation)
        assert paths and paths[0].stat().st_size > 10_000


def test_render_with_lyrics_smoke(tmp_path):
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(1, 62), 3, 2), (tp(2, 64), 2, 0)])
    paths = render_png(
        arr, tmp_path / "lyric.png",
        lyrics_map={Fraction(0): "一", Fraction(1): "切", Fraction(2): "风"},
    )
    assert paths and paths[0].stat().st_size > 12_000


def test_ascii_with_lyrics_row(tmp_path):
    from uketab.render.ascii import render_ascii

    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(1, 62), 3, 2)])
    text = render_ascii(arr, lyrics_map={Fraction(0): "春", Fraction(1): "风"})
    lines = [line for line in text.splitlines() if line.strip()]
    assert any("春" in line and "风" in line for line in lines)  # lyric row present


def test_decompose_duration_to_standard_noteheads():
    assert _decompose_duration(Fraction(1)) == [(Fraction(1), False)]          # quarter
    assert _decompose_duration(Fraction(2)) == [(Fraction(2), False)]          # half
    assert _decompose_duration(Fraction(3, 2)) == [(Fraction(3, 2), True)]    # dotted quarter
    # 2.5 beats is not a single note value: half + eighth, later joined by a tie
    assert _decompose_duration(Fraction(5, 2)) == [(Fraction(2), False), (Fraction(1, 2), False)]
    # pieces must always sum back to the original duration
    for beats in (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(2), Fraction(4)):
        parts = _decompose_duration(beats)
        assert sum(value for value, _ in parts) == beats


def test_build_rhythm_chains_ties():
    note = TabNote(note=tp(0, 60, dur=Fraction(5, 2)), fingering=Fingering(string=3, fret=0))
    arr = Arrangement(difficulty="easy", tempo_bpm=120.0, time_signature=(4, 4),
                      notes=(note,), grid=EIGHTH)
    events = build_rhythm(arr)
    half_head = events[Fraction(0)][0]
    eighth_head = events[Fraction(2)][0]
    assert half_head.value == Fraction(2) and not half_head.tie_from
    assert eighth_head.value == Fraction(1, 2) and eighth_head.tie_from == Fraction(0)
