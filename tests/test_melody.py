"""Audio-candidate melody selection tests."""

from uketab.melody import select_melody
from uketab.models import NoteEvent


def event(onset: float, pitch: int, duration: float = 0.4) -> NoteEvent:
    return NoteEvent(onset=onset, duration=duration, pitch=pitch, velocity=0.8, source="audio")


def test_select_melody_simultaneous_high_artifact_keeps_continuous_pitch():
    candidates = [
        event(0.0, 72),
        event(0.0, 65),
        event(0.5, 67),
        event(0.5, 84, 0.08),
        event(1.0, 69),
    ]

    selected = select_melody(candidates)

    assert [note.pitch for note in selected] == [72, 67, 69]


def test_select_melody_preserves_separate_phrases():
    candidates = [event(0.0, 72), event(2.0, 60)]

    selected = select_melody(candidates)

    assert [note.pitch for note in selected] == [72, 60]
