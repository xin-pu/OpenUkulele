"""Lyric parsing and melody alignment tests."""

from fractions import Fraction

import pytest

from uketab.errors import InputError
from uketab.lyrics import align, load_lyrics, parse_lrc, tokenize
from uketab.models import Fingering, TabNote

from conftest import tp


def tab_note(beat, pitch, role="melody"):
    return TabNote(note=tp(beat, pitch, role), fingering=Fingering(string=3, fret=0))


def test_parse_lrc(tmp_path):
    path = tmp_path / "a.lrc"
    path.write_text("[00:12.50]第一行\n[00:05.00]第二行\n空行忽略\n", encoding="utf-8")
    lines = parse_lrc(path)
    assert [line.start_seconds for line in lines] == [5.0, 12.5]  # sorted by time
    assert lines[0].text == "第二行"


def test_load_plain_text_and_lyric_extensionless(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("风吹过 雨落下\n", encoding="utf-8")
    lines = load_lyrics(path)
    assert len(lines) == 1 and lines[0].text == "风吹过 雨落下"

    sneaky = tmp_path / "real.txt"  # stamped content with wrong extension
    sneaky.write_text("[00:01.00]真歌词\n", encoding="utf-8")
    assert load_lyrics(sneaky)[0].start_seconds == 1.0
    assert load_lyrics(sneaky)[0].text == "真歌词"


def test_tokenize_cjk_per_char_latin_per_word():
    assert tokenize("风 wind go-bye") == ["风", "wind", "go-bye"]
    assert tokenize("一切都像风，追") == ["一", "切", "都", "像", "风", "追"]  # 标点跳过


def test_align_lrc_lines_to_melody_notes_in_order():
    notes = [tab_note(Fraction(0), 72), tab_note(Fraction(1), 74), tab_note(Fraction(2), 76),
             tab_note(Fraction(6), 77), tab_note(Fraction(7), 79)]
    path_lines = "[00:00.00]你好吗\n[00:03.00]再见\n"
    # tempo 120 → line1 at beat 0 covers beats [0..6), line2 from beat 6
    beats = sorted({n.note.beat for n in notes if n.note.role == "melody"})
    mapping = align(load_lyrics_from_text(path_lines), beats, 120.0)
    assert mapping[Fraction(0)] == "你"
    assert mapping[Fraction(1)] == "好"
    assert mapping[Fraction(2)] == "吗"
    assert mapping[Fraction(6)] == "再"
    assert mapping[Fraction(7)] == "见"


def test_align_ignores_bass_and_skips_unmatched_notes():
    notes = [tab_note(Fraction(0), 72), tab_note(Fraction(1, 2), 60, role="bass"),
             tab_note(Fraction(1), 74)]
    beats = sorted({n.note.beat for n in notes if n.note.role == "melody"})
    mapping = align(load_lyrics_from_text("[00:00.00]啊哦咦\n"), beats, 120.0)
    assert mapping == {Fraction(0): "啊", Fraction(1): "哦"}  # 咦 dropped: no note left


def test_plain_text_zips_across_all_melody_notes():
    notes = [tab_note(Fraction(b), 72) for b in range(4)]
    mapping = align(load_lyrics_from_text("春天来了", ".txt"), [n.note.beat for n in notes], 120.0)
    assert [mapping[Fraction(0)], mapping[Fraction(1)], mapping[Fraction(2)], mapping[Fraction(3)]] == ["春", "天", "来", "了"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(InputError, match="不存在"):
        load_lyrics(tmp_path / "ghost.lrc")


def load_lyrics_from_text(text, suffix=".lrc"):
    """Parse lyric text through the real code path via a temp file.

    Windows locks NamedTemporaryFile against reopening while open, so use
    mkstemp + explicit close before reading.
    """
    import os
    import tempfile
    from pathlib import Path

    handle, name = tempfile.mkstemp(suffix=suffix)
    os.close(handle)
    path = Path(name)
    try:
        path.write_text(text, encoding="utf-8")
        return load_lyrics(path)
    finally:
        path.unlink(missing_ok=True)
