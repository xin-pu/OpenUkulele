"""Arrangement -> GP5 export via PyGuitarPro.

One four-string track with display tuning A4/E4/C4/G4 (string 1..4),
fret count 15, GM ukulele instrument. Ticks follow the library
convention: 960 per quarter, first measure starting at tick 960.

GP5 serializes beats sequentially by duration, so each sounding slot
becomes one beat lasting until the next sounding slot (or the bar line);
non-dyadic remainders become rest beats.

Compatibility target is TuxGuitar (manual acceptance per design doc).
"""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path

import guitarpro as gp

from ..errors import ExportError
from ..models import Arrangement

#: string 1..4 -> open pitch (A4, E4, C4, G4)
GP_STRING_PITCHES = (69, 64, 60, 67)
GM_UKULELE = 24
FRET_COUNT = 15

_QUARTER_TICKS = gp.Duration.quarterTime  # 960

#: note-length in beats -> GP duration value
_DYADIC_VALUES = {
    Fraction(4): 1,  # whole note
    Fraction(2): 2,  # half
    Fraction(1): 4,  # quarter
    Fraction(1, 2): 8,  # eighth
    Fraction(1, 4): 16,  # sixteenth
}
_BEATS_BY_VALUE = {value: beats for beats, value in _DYADIC_VALUES.items()}


def write_gp5(arrangement: Arrangement, path: str | Path, title: str = "") -> None:
    try:
        song = _build_song(arrangement, title)
        buffer = io.BytesIO()
        gp.write(song, buffer)
        Path(path).write_bytes(buffer.getvalue())
    except gp.GPException as exc:  # pragma: no cover - library-level failure
        raise ExportError(f"GP5 导出失败: {exc}", "提交 issue 并附上输入文件") from exc
    except OSError as exc:
        raise ExportError(f"GP5 写入失败: {path} ({exc})", "检查输出目录权限") from exc


def _build_song(arrangement: Arrangement, title: str) -> gp.Song:
    song = gp.Song()
    # GP5 metadata is byte-length-prefixed cp1252; CJK and other
    # non-Latin1 titles would crash the writer, so fold them to '?'.
    song.title = title.encode("cp1252", errors="replace").decode("cp1252")
    song.tempo = max(30, min(300, int(round(arrangement.tempo_bpm))))
    numerator, denominator = arrangement.time_signature

    track = song.tracks[0]
    track.name = f"Ukulele ({arrangement.difficulty})"
    track.fretCount = FRET_COUNT
    track.strings[:] = [
        gp.GuitarString(number, pitch) for number, pitch in enumerate(GP_STRING_PITCHES, 1)
    ]
    track.channel.instrument = GM_UKULELE

    song.measureHeaders[0].timeSignature = gp.TimeSignature(
        numerator, gp.Duration(value=denominator)
    )

    length = Fraction(numerator * 4, denominator)
    groups = _groups_by_beat(arrangement.notes)
    beats = sorted(groups)

    bar_indices = sorted({int(beat / length) + 1 for beat in beats})
    for _ in range(max(0, len(bar_indices) - 1)):
        song.newMeasure()
    # song.newMeasure() appends plain MeasureHeader()s; recompute their
    # starts/numbers so every measure is contiguous and ordered.
    start = _QUARTER_TICKS
    for number, header in enumerate(song.measureHeaders, start=1):
        header.number = number
        header.start = start
        if number > 1:
            header.timeSignature = gp.TimeSignature(
                numerator, gp.Duration(value=denominator)
            )
        start += header.length

    for bar_index in bar_indices:
        bar_start = (bar_index - 1) * length
        measure = track.measures[bar_index - 1]
        voice = measure.voices[0]
        slots = sorted(beat for beat in beats if bar_start <= beat < bar_start + length)
        boundaries = slots[1:] + [bar_start + length]
        for slot, boundary in zip(slots, boundaries):
            _append_group_beats(voice, measure.start, slot - bar_start, boundary - slot, groups[slot])

    return song


def _append_group_beats(
    voice: gp.Voice, measure_start: int, offset_beats: Fraction, gap: Fraction, group: list
) -> None:
    """Emit the sounding beat plus rest beats covering a non-dyadic gap."""
    remaining = Fraction(gap)
    first = True
    tick = measure_start + int(offset_beats) * _QUARTER_TICKS
    while remaining > 0:
        duration = _duration(remaining)
        status = gp.BeatStatus.normal if first else gp.BeatStatus.rest
        beat = gp.Beat(voice, start=tick, duration=duration, status=status)
        voice.beats.append(beat)
        if first:
            for note in sorted(group, key=lambda n: n.fingering.string):
                beat.notes.append(
                    gp.Note(
                        beat,
                        value=note.fingering.fret,
                        string=note.fingering.string,
                        velocity=_velocity(note.note.velocity),
                        type=gp.NoteType.normal,
                    )
                )
            first = False
        span = _BEATS_BY_VALUE[duration.value]
        remaining -= span
        tick += int(span) * _QUARTER_TICKS


def _groups_by_beat(notes) -> dict[Fraction, list]:
    grouped: dict[Fraction, list] = {}
    for note in notes:
        grouped.setdefault(note.note.beat, []).append(note)
    return grouped


def _duration(beats: Fraction) -> gp.Duration:
    beats = Fraction(beats)
    if beats in _DYADIC_VALUES:
        return gp.Duration(value=_DYADIC_VALUES[beats])
    # Dotted or otherwise odd lengths: largest dyadic note not exceeding it.
    value = 16
    for candidate in sorted(_DYADIC_VALUES):
        if candidate <= beats:
            value = _DYADIC_VALUES[candidate]
    return gp.Duration(value=value)


def _velocity(velocity: float) -> int:
    return max(1, min(127, int(round(64 + velocity * 63))))
