"""GP5 writer and JSON report tests."""

import json
from fractions import Fraction

import guitarpro as gp

import uketab.report as report_mod
from uketab.models import Arrangement, Fingering, TabNote
from uketab.render.gp5 import write_gp5
from uketab.timing import EIGHTH

from conftest import tp


def arrangement_of(notes, difficulty="easy", grid=EIGHTH, ts=(4, 4)):
    tab_notes = tuple(
        TabNote(note=n, fingering=Fingering(string=s, fret=f)) for n, s, f in notes
    )
    return Arrangement(
        difficulty=difficulty,
        tempo_bpm=120.0,
        time_signature=ts,
        notes=tab_notes,
        grid=grid,
    )


def test_gp5_file_nonempty_and_parses(tmp_path):
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(1, 67), 4, 0), (tp(2, 72), 1, 3)])
    path = tmp_path / "out.gp5"
    write_gp5(arr, path, title="test")
    raw = path.read_bytes()
    assert len(raw) > 1000
    assert raw.startswith(b"\x18FICHIER") or b"FICHIER" in raw[:16]

    song = gp.parse(str(path))
    track = song.tracks[0]
    assert len(song.tracks) == 1
    assert song.tempo == 120
    assert [s.value for s in track.strings] == [69, 64, 60, 67]
    assert track.fretCount == 15
    notes = [
        (b.start, n.string, n.value)
        for m in track.measures
        for b in m.voices[0].beats
        for n in b.notes
    ]
    assert notes == [(960, 3, 0), (1920, 4, 0), (2880, 1, 3)]


def test_gp5_beat_timing_sequential_and_correct(tmp_path):
    # Quarter-note melody: beats at 960, 1920, 2880... half note lasts 2 beats.
    arr = arrangement_of(
        [(tp(0, 60), 3, 0), (tp(1, 62), 3, 2), (tp(2, 64), 2, 0, ), (tp(4, 60), 3, 0)]
    )
    path = tmp_path / "timing.gp5"
    write_gp5(arr, path)
    song = gp.parse(str(path))
    beats = [
        (m.header.number, b.start, b.duration.value, len(b.notes))
        for m in song.tracks[0].measures
        for b in m.voices[0].beats
    ]
    starts = [b[1] for b in beats]
    assert starts == [960, 1920, 2880, 4800]
    # third note is a half note (value 2)
    assert beats[2][2] == 2


def test_gp5_non_dyadic_gap_gets_rest(tmp_path):
    # Gap of 1.5 beats -> quarter note + eighth rest; the final 2.5-beat
    # gap -> half note + eighth rest. Total fills the 4/4 measure.
    arr = arrangement_of([(tp(0, 60), 3, 0), (tp(Fraction(3, 2), 62), 3, 2)])
    path = tmp_path / "dotted.gp5"
    write_gp5(arr, path)
    song = gp.parse(str(path))
    beats = [
        (b.duration.value, len(b.notes))
        for m in song.tracks[0].measures
        for b in m.voices[0].beats
    ]
    assert beats == [(4, 1), (8, 0), (2, 1), (8, 0)]
    lengths = {4: 1, 2: 2, 8: 0.5, 16: 0.25, 1: 4}
    assert sum(lengths[value] for value, _ in beats) == 4


def test_report_structure(tmp_path):
    from uketab.fallback import ResolutionResult
    from uketab.validation import ValidationReport

    arr = arrangement_of([(tp(0, 60), 3, 0)])
    validation = ValidationReport(
        passed=True,
        errors=(),
        shift_count=0,
        max_span=0,
        barre_count=0,
        difficulty_score=0.1,
    )
    from uketab.fingering import BarSolution

    resolution = ResolutionResult(
        solutions=(BarSolution(1, (), (), 0, True),),
        actions=(),
        report=validation,
        failed_bars=(),
    )
    report = report_mod.build_report(
        input_path="x.mid",
        source="midi",
        event_count=3,
        tempo_bpm=120.0,
        tempo_provided=False,
        time_signature=(4, 4),
        grid_easy=EIGHTH,
        grid_hard=EIGHTH,
        easy=(arr, resolution),
        hard=None,
        warnings=["w1"],
    )
    assert report["version"]
    assert report["input"]["source"] == "midi"
    assert report["input"]["time_signature"] == [4, 4]
    assert report["quantization"]["grid_easy"] == "1/2"
    assert report["arrangements"]["easy"]["passed"] is True
    assert report["arrangements"]["easy"]["validation"]["issues"] == []
    assert "hard" not in report["arrangements"]
    assert report["warnings"] == ["w1"]

    path = tmp_path / "report.json"
    report_mod.write_report(report, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == report
