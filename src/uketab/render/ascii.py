"""Readable four-line ASCII tab.

Strings are printed in display order A, E, C, G (1..4, thinnest first).
Every grid slot occupies a fixed-width column so simultaneous groups stay
vertically aligned; empty slots become rest columns. With a lyric map, one
extra line under each staff shows syllables under their melody note.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from ..models import Arrangement, TabNote
from ..timing import bar_length
from ..tuning import HIGH_G, Tuning, pitch_name

COLUMN_WIDTH = 3
#: Break the staff after this many columns to keep lines readable.
COLUMNS_PER_LINE = 24

_STRING_LABELS = {1: "A", 2: "E", 3: "C", 4: "G"}
_LYRIC_KEY = 0  # pseudo-string index for the lyric row


def render_ascii(
    arrangement: Arrangement,
    tuning: Tuning = HIGH_G,
    lyrics_map: dict[Fraction, str] | None = None,
) -> str:
    header = _header(arrangement, tuning)
    staff = _staff(arrangement, lyrics_map)
    return "\n".join([header, "", staff, ""])


def _header(arrangement: Arrangement, tuning: Tuning) -> str:
    numerator, denominator = arrangement.time_signature
    tuning_desc = " ".join(
        f"{_STRING_LABELS[string]}={pitch_name(tuning.open_pitch(string))}"
        for string in sorted(_STRING_LABELS)
    )
    grid_value = int(round(4 / arrangement.grid))  # note-value denominator
    return (
        f"UkeTab {arrangement.difficulty} | tempo {arrangement.tempo_bpm:g} | "
        f"{numerator}/{denominator} | grid 1/{grid_value} | tuning (high G): {tuning_desc}"
    )


def _staff(arrangement: Arrangement, lyrics_map: dict[Fraction, str] | None) -> str:
    length = bar_length(arrangement.time_signature)
    grid = arrangement.grid
    groups = _groups_by_beat(arrangement.notes)
    beats = sorted(groups)
    if not groups:
        return "(no notes)"

    blocks: list[str] = []
    bar_indices = sorted({int(beat / length) + 1 for beat in beats})
    for bar_index in bar_indices:
        bar_start = (bar_index - 1) * length
        in_bar = sorted(beat for beat in beats if bar_start <= beat < bar_start + length)
        last = in_bar[-1]
        slots = []
        cursor = bar_start
        while cursor <= last:
            slots.append(cursor)
            cursor += grid
        cells: dict[int, list[str]] = {string: [] for string in (1, 2, 3, 4, _LYRIC_KEY)}
        for slot in slots:
            _append_group(cells, groups.get(slot))
            _append_lyric(cells, slot, lyrics_map)
        blocks.extend(_render_bar(cells, bar_index, bool(lyrics_map)))
    return "\n".join(blocks)


def _append_group(cells: dict[int, list[str]], group: tuple[TabNote, ...] | None) -> None:
    by_string = {note.fingering.string: note.fingering.fret for note in group} if group else {}
    for string in (1, 2, 3, 4):
        fret = by_string.get(string)
        cells[string].append("-" * COLUMN_WIDTH if fret is None else _cell(fret))


def _append_lyric(
    cells: dict[int, list[str]], slot: Fraction, lyrics_map: dict[Fraction, str] | None
) -> None:
    if not lyrics_map:
        return
    syllable = lyrics_map.get(slot, "")
    pad = COLUMN_WIDTH - len(syllable)
    left = pad // 2
    cells[_LYRIC_KEY].append(" " * left + syllable + " " * (pad - left))


def _render_bar(
    cells: dict[int, list[str]], bar_index: int, has_lyrics: bool
) -> list[str]:
    rows: list[str] = []
    total = len(cells[1])
    start = 0
    while start < total:
        chunk_lines = []
        for string in (1, 2, 3, 4):
            row_cells = cells[string][start : start + COLUMNS_PER_LINE]
            prefix = f"{_STRING_LABELS[string]}|"
            if start == 0:
                prefix += f"[{bar_index}]"
            chunk_lines.append(prefix + "".join(row_cells) + "|")
        if has_lyrics:
            lyric_cells = cells[_LYRIC_KEY][start : start + COLUMNS_PER_LINE]
            # 3-space gutter keeps alignment with the "A|" string prefixes
            chunk_lines.append("   " + "".join(lyric_cells))
        rows.append("\n".join(chunk_lines))
        start += COLUMNS_PER_LINE
    return rows


def _groups_by_beat(notes: Sequence[TabNote]) -> dict[Fraction, tuple[TabNote, ...]]:
    grouped: dict[Fraction, list[TabNote]] = {}
    for note in notes:
        grouped.setdefault(note.note.beat, []).append(note)
    return {beat: tuple(group) for beat, group in grouped.items()}


def _cell(fret: int) -> str:
    text = str(fret)
    return text + "-" * (COLUMN_WIDTH - len(text))
