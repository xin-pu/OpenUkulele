"""Shared fixtures and helpers."""

from __future__ import annotations

from fractions import Fraction

import mido
import pytest

from uketab.models import TimedPitch


def write_midi(path, notes, tempo_bpm=120, ts=(4, 4), tpb=480):
    """Write a type-1 MIDI file.

    ``notes`` is a list of ``(pitch, start_beat, dur_beat)`` tuples.
    """
    mid = mido.MidiFile(type=1, ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=int(60_000_000 / tempo_bpm), time=0))
    track.append(mido.MetaMessage("time_signature", numerator=ts[0], denominator=ts[1], time=0))

    events = []
    for pitch, start, dur in notes:
        events.append((int(start * tpb), "on", pitch))
        events.append((int((start + dur) * tpb), "off", pitch))
    # "off" sorts before "on" at equal ticks: end notes precede new ones.
    events.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for tick, kind, pitch in events:
        track.append(
            mido.Message(
                "note_on" if kind == "on" else "note_off",
                note=pitch,
                velocity=90 if kind == "on" else 0,
                time=tick - last,
            )
        )
        last = tick
    mid.save(str(path))


def tp(beat, pitch, role="melody", dur=None):
    """TimedPitch at a fractional beat; duration defaults to one eighth."""
    return TimedPitch(
        beat=Fraction(beat),
        duration_beats=Fraction(dur) if dur is not None else Fraction(1, 2),
        pitch=pitch,
        velocity=0.8,
        role=role,
    )


@pytest.fixture
def twinkle_mid(tmp_path):
    """Single-line melody fully inside the easy 0-5 fret range."""
    melody = [
        (60, 0, 1), (60, 1, 1), (67, 2, 1), (67, 3, 1),
        (69, 4, 1), (69, 5, 1), (67, 6, 2),
        (65, 8, 1), (65, 9, 1), (64, 10, 1), (64, 11, 1),
        (62, 12, 1), (62, 13, 1), (60, 14, 2),
    ]
    path = tmp_path / "twinkle.mid"
    write_midi(path, melody)
    return path


@pytest.fixture
def melody_bass_mid(tmp_path):
    """Melody within the easy fret window plus playable bass notes."""
    notes = [
        (72, 0, 1), (74, 1, 1), (72, 2, 1), (71, 3, 1),
        (60, 0, 2), (67, 2, 2),
        (69, 4, 1), (67, 5, 1), (69, 6, 1), (71, 7, 1),
        (60, 4, 2), (64, 6, 2),
    ]
    path = tmp_path / "melody_bass.mid"
    write_midi(path, notes)
    return path
