"""Readable four-line ASCII tab.

Strings are printed in display order A, E, C, G (1..4, thinnest first).
Every grid slot occupies a fixed-width column so simultaneous groups stay
vertically aligned; empty slots become rest columns. Each measure renders
as its own four-line block.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from ..models import Arrangement, TabNote
from ..timing import bar_length
from ..tuning import HIGH_G, Tuning, pitch_name

COLUMN_WIDTH = 3
#: Split long measures into multiple four-line rows after this many columns.
COLUMNS_PER_LINE = 24

_STRING_LABELS = {1: "A", 2: "E", 3: "C", 4: "G"}


def render_ascii(arrangement: Arrangement, tuning: Tuning = HIGH_G) -> str:
    header = _header(arrangement, tuning)
    staff = _staff(arrangement)
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


def _staff(arrangement: Arrangement) -> str:
    length = bar_length(arrangement.time_signature)
    grid = arrangement.grid
    groups = _groups_by_beat(arrangement.notes)
    if not groups:
        return "(no notes)"

    blocks: list[str] = []
    bar_indices = sorted({int(beat / length) + 1 for beat in groups})
    for bar_index in bar_indices:
        bar_start = (bar_index - 1) * length
        beats = sorted(beat for beat in groups if bar_start <= beat < bar_start + length)
        last = beats[-1]
        slots = [bar_start]
        cursor = bar_start + grid
        while cursor <= last:
            slots.append(cursor)
            cursor += grid
        cells_by_string = {string: [] for string in (1, 2, 3, 4)}
        for slot in slots:
            _append_group(cells_by_string, groups.get(slot))
        blocks.extend(_render_bar(cells_by_string, bar_index))
    return "\n".join(blocks)


def _append_group(
    cells_by_string: dict[int, list[str]], group: tuple[TabNote, ...] | None
) -> None:
    by_string = {note.fingering.string: note.fingering.fret for note in group} if group else {}
    for string in (1, 2, 3, 4):
        fret = by_string.get(string)
        cells_by_string[string].append("-" * COLUMN_WIDTH if fret is None else _cell(fret))


def _render_bar(cells_by_string: dict[int, list[str]], bar_index: int) -> list[str]:
    rows: list[str] = []
    total = len(next(iter(cells_by_string.values())))
    start = 0
    while start < total:
        chunk_lines = []
        for string in (1, 2, 3, 4):
            cells = cells_by_string[string][start : start + COLUMNS_PER_LINE]
            prefix = f"{_STRING_LABELS[string]}|"
            if start == 0:
                prefix += f"[{bar_index}]"
            chunk_lines.append(prefix + "".join(cells) + "|")
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
