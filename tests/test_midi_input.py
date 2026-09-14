"""MIDI input adapter tests."""

import mido
import pytest

from uketab.errors import InputError
from uketab.input.midi import load_midi

from conftest import write_midi


def test_pairs_notes_and_converts_time(tmp_path):
    path = tmp_path / "a.mid"
    write_midi(path, [(72, 0, 1), (74, 1, 0.5)])
    events, tempo, ts, _ = load_midi(path)
    assert tempo == 120.0
    assert ts == (4, 4)
    assert [(e.pitch, round(e.onset, 4), round(e.duration, 4)) for e in events] == [
        (72, 0.0, 0.5),
        (74, 0.5, 0.25),
    ]
    assert all(e.source == "midi" for e in events)


def test_tempo_and_time_signature_from_file(tmp_path):
    path = tmp_path / "a.mid"
    write_midi(path, [(60, 0, 1)], tempo_bpm=90, ts=(3, 4))
    events, tempo, ts, _ = load_midi(path)
    assert tempo == pytest.approx(90.0, abs=0.01)  # integer microseconds per beat
    assert ts == (3, 4)


def test_missing_time_signature_defaults_to_4_4(tmp_path):
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    path = tmp_path / "no_ts.mid"
    mid.save(str(path))
    _, _, ts, _ = load_midi(path)
    assert ts == (4, 4)


def test_multitrack_merge(tmp_path):
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    for pitches in ((60,), (67,)):
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message("note_on", note=pitches[0], velocity=90, time=0))
        track.append(mido.Message("note_off", note=pitches[0], velocity=0, time=480))
    path = tmp_path / "multi.mid"
    mid.save(str(path))
    events, _, _, _ = load_midi(path)
    assert sorted(e.pitch for e in events) == [60, 67]


def test_empty_file_no_notes(tmp_path):
    mid = mido.MidiFile(type=0)
    mid.tracks.append(mido.MidiTrack())
    path = tmp_path / "empty.mid"
    mid.save(str(path))
    with pytest.raises(InputError, match="没有音符"):
        load_midi(path)


def test_corrupt_file(tmp_path):
    path = tmp_path / "bad.mid"
    path.write_bytes(b"not a midi file at all")
    with pytest.raises(InputError, match="无法读取"):
        load_midi(path)


def test_missing_file(tmp_path):
    with pytest.raises(InputError, match="不存在"):
        load_midi(tmp_path / "ghost.mid")


def test_dangling_note_on(tmp_path):
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_on", note=64, velocity=90, time=0))
    track.append(mido.Message("note_off", note=64, velocity=0, time=480))
    path = tmp_path / "dangling.mid"
    mid.save(str(path))
    with pytest.raises(InputError, match="悬空 note-on"):
        load_midi(path)


def test_dangling_note_off(tmp_path):
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_off", note=60, velocity=0, time=0))
    path = tmp_path / "dangling_off.mid"
    mid.save(str(path))
    with pytest.raises(InputError, match="悬空 note-off"):
        load_midi(path)


def test_zero_duration_note(tmp_path):
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=0))
    path = tmp_path / "zero.mid"
    mid.save(str(path))
    with pytest.raises(InputError, match="零时值"):
        load_midi(path)


def test_type2_rejected(tmp_path):
    mid = mido.MidiFile(type=2, ticks_per_beat=480)
    mid.tracks.append(mido.MidiTrack())
    path = tmp_path / "t2.mid"
    mid.save(str(path))
    with pytest.raises(InputError, match="类型 2"):
        load_midi(path)


def test_note_on_velocity_zero_counts_as_off(tmp_path):
    mid = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_on", note=60, velocity=0, time=480))
    path = tmp_path / "vel0.mid"
    mid.save(str(path))
    events, _, _, _ = load_midi(path)
    assert len(events) == 1
    assert events[0].duration == pytest.approx(0.5)
