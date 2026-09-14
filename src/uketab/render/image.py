"""Arrangement -> PNG tab image (offline, matplotlib).

Consumes a validated :class:`~uketab.models.Arrangement` only -- the same
data the ASCII renderer uses. Output is laid out on real A4 pages
(default landscape, optional portrait) so it prints 1:1; long pieces wrap
onto additional pages (PNG per page, or a multi-page PDF).

Professional touches:
- soft eye-friendly paper background with a subtle vertical gradient;
- string name labels (A/E/C/G) at the left of every staff;
- a fretboard position box at the start of the first bar on a row;
- measures separated by bar lines, numbered above each bar's first beat;
- a thin tick under the bottom line marks every beat, and beats are set
  apart with a wider gap so the pulse is visible;
- sustained notes draw an arced tie line; the note's release gets a small
  open tie head so the connection is unmistakable.

Role colors: melody black (bold), bass blue, harmony gray.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Ellipse, FancyArrowPatch, Rectangle  # noqa: E402

from ..models import Arrangement, TabNote  # noqa: E402
from ..timing import bar_length  # noqa: E402
from ..tuning import HIGH_G, Tuning, pitch_name  # noqa: E402

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

MM = 1 / 25.4
A4_LONG, A4_SHORT = 297 * MM, 210 * MM  # inches
DPI = 200

STRING_SPACING = 1.7  # vertical distance between adjacent staff lines
EIGHTH_W = 2.35  # one eighth-note grid step, in layout units (x)
BEAT_EXTRA_GAP = 1.7  # added to the inter-slot gap to show the beat
BAR_LINE_GAP = 2.6  # gap on both sides of a bar line
LEFT_LABEL_W = 2.8  # room for the string-name labels at each staff start

#: vertical extents (relative to the staff band) every bar line must span so
#: the leading line and every trailing/measure line share identical endpoints.
STAFF_SPAN_TOP = 0.55  # units above the top string line
STAFF_SPAN_BOTTOM = 0.55  # units below the bottom string line (before lane)

#: lyric lane sits above the staff; bar numbers/position box move higher when used
LYRIC_Y = 1.45  # syllable baseline height above the top string line
LYRIC_CLEARANCE = 1.75  # extra top space per row when lyrics are present
LYRIC_COLOR = "#2f2f2b"

#: soft, eye-friendly palette (top, bottom of a faint vertical wash)
PAGE_BG_TOP = "#fbfaf5"
PAGE_BG_BOTTOM = "#f3f1e6"
STAFF_INK = "#5b5b52"
STAFF_COLOR = "#6b6b60"
BAR_COLOR = "#3f3f38"
TICK_COLOR = "#a8a294"
LABEL_COLOR = "#8a8477"
TITLE_COLOR = "#2f2f2b"

#: watermark styling (email shown both as a large faint diagonal and a signature)
WATERMARK_COLOR = "#4a463c"
WATERMARK_DIAG_ALPHA = 0.06
WATERMARK_SIG_ALPHA = 0.62
DEFAULT_WATERMARK = "pu.xin@outlook.com"

STRING_LABELS = {1: "A", 2: "E", 3: "C", 4: "G"}
ROLE_COLORS = {"melody": "#1a1a1a", "bass": "#0f6aa5", "harmony": "#8a8a8a"}


def _steps_per_beat(grid: Fraction) -> int:
    return max(1, int(round(1 / grid)))


# ---------------------------------------------------------------- model


@dataclass(frozen=True)
class Rhythm:
    """A notehead to draw at a slot: single standard value plus optional dot."""

    value: Fraction  # note-value in beats (e.g. 1 = quarter, 0.5 = eighth)
    dotted: bool
    tie_from: Fraction | None  # slot of the previous note value, if tied here
    role: str = "melody"


@dataclass
class _Cell:
    """One grid slot in the layout with its sounding notes and rhythm plan."""

    x: float  # left edge in layout units
    width: float
    slot: Fraction  # grid position this cell renders
    notes: list[TabNote]
    beat_head: bool = False  # first slot of a beat -> gets a beat tick
    rhythm: tuple[Rhythm, ...] = ()  # notehead spec(s) under this slot


@dataclass
class _Measure:
    bar: int
    cells: list[_Cell]
    width: float  # total including trailing bar gap


@dataclass
class _Row:
    measures: list[_Measure]
    width: float

    def is_empty(self) -> bool:
        return not self.measures


def _sounding_by_slot(arrangement: Arrangement) -> dict[Fraction, list[TabNote]]:
    by_slot: dict[Fraction, list[TabNote]] = {}
    for note in arrangement.notes:
        by_slot.setdefault(note.note.beat, []).append(note)
    return by_slot


#: descending (value, dotted) note values that sum to any quantized duration
_STANDARD_VALUES: tuple[tuple[Fraction, bool], ...] = (
    (Fraction(4), False),      # whole
    (Fraction(3), True),       # dotted half
    (Fraction(2), False),      # half
    (Fraction(3, 2), True),    # dotted quarter
    (Fraction(1), False),      # quarter
    (Fraction(3, 4), True),    # dotted eighth
    (Fraction(1, 2), False),   # eighth
    (Fraction(3, 8), True),    # dotted sixteenth
    (Fraction(1, 4), False),   # sixteenth
)


def _decompose_duration(beats: Fraction) -> list[tuple[Fraction, bool]]:
    """Split a quantized duration into standard note values, longest first.

    A plain quarter/half/eighth returns one value; irregular lengths like
    2.5 beats split into half + eighth (which a tie then joins).
    """
    segments: list[tuple[Fraction, bool]] = []
    remaining = Fraction(beats)
    while remaining > 0:
        for value, dotted in _STANDARD_VALUES:
            if value <= remaining:
                segments.append((value, dotted))
                remaining -= value
                break
        else:  # sub-sixteenth residue: absorb into the last segment
            segments[-1] = (segments[-1][0], segments[-1][1])
            break
    return segments


def build_rhythm(arrangement: Arrangement) -> dict[Fraction, list[Rhythm]]:
    """slot -> noteheads to draw under that slot, with ties already chained."""
    events: dict[Fraction, list[Rhythm]] = {}
    for note in arrangement.notes:
        cursor = note.note.beat
        previous: Fraction | None = None
        for value, dotted in _decompose_duration(note.note.duration_beats):
            events.setdefault(cursor, []).append(
                Rhythm(value=value, dotted=dotted, tie_from=previous, role=note.note.role)
            )
            previous = cursor
            cursor += value
    return events


def _build_measures(
    arrangement: Arrangement,
) -> list[_Measure]:
    grid = arrangement.grid
    steps = _steps_per_beat(grid)
    length = bar_length(arrangement.time_signature)
    by_slot = _sounding_by_slot(arrangement)
    rhythm_map = build_rhythm(arrangement)

    last_beat = max(arrangement.notes, key=lambda n: n.note.beat).note.beat
    end_bar = int(last_beat / length) + 1

    slot_w = EIGHTH_W
    measures: list[_Measure] = []
    for bar in range(1, end_bar + 1):
        bar_start = (bar - 1) * length
        cells: list[_Cell] = []
        x = 0.0
        last_sound = _last_sound_before(arrangement, bar_start, length)
        cursor = bar_start
        while cursor <= last_sound:
            in_beat = int((cursor - bar_start) % 1 * steps)
            is_beat_head = in_beat == 0
            w = slot_w + (BEAT_EXTRA_GAP if is_beat_head and cells else 0)
            onset_notes = by_slot.get(cursor, [])
            cell = _Cell(
                x=x,
                width=slot_w,
                slot=cursor,
                notes=onset_notes,
                beat_head=is_beat_head,
                rhythm=tuple(rhythm_map.get(cursor, ())),
            )
            cells.append(cell)
            x += w
            cursor += grid
        measures.append(_Measure(bar=bar, cells=cells, width=x + BAR_LINE_GAP))
    return measures


def _last_sound_before(arrangement: Arrangement, bar_start: Fraction, length: Fraction) -> Fraction:
    grid = arrangement.grid
    end = bar_start + length
    last = bar_start
    for note in arrangement.notes:
        onset = note.note.beat
        if bar_start <= onset < end and onset > last:
            last = onset
        release = onset + note.note.duration_beats - grid
        if bar_start <= release < end and release > last:
            last = release
    # snap down to grid
    return Fraction(int(last / grid)) * grid


# ---------------------------------------------------------------- packing


def _pack_rows(measures: list[_Measure], usable_w: float) -> list[_Row]:
    rows: list[_Row] = [_Row([], 0.0)]
    for measure in measures:
        row = rows[-1]
        add = measure.width if row.is_empty() else BAR_LINE_GAP + measure.width
        if not row.is_empty() and row.width + add > usable_w:
            rows.append(_Row([measure], measure.width))
        else:
            if not row.is_empty():
                row.width += BAR_LINE_GAP
            row.measures.append(measure)
            row.width += measure.width
    return rows


@dataclass(frozen=True)
class _Geometry:
    """A4 page metrics in layout units."""

    usable_w_units: float
    usable_h_units: float
    header_units: float
    row_height_units: float
    unit_mm: float
    title_pt: float
    meta_pt: float
    fret_pt: float
    bar_no_pt: float
    lw: float
    tie_lw: float
    row_gap: float = 0.0  # extra breathing space between systems

    @property
    def max_rows(self) -> int:
        pitch = self.row_height_units + self.row_gap
        return max(1, int((self.usable_h_units - self.header_units) // pitch))

    @property
    def x_left(self) -> float:
        """Left data bound: negative room for the string-name labels."""
        return -LEFT_LABEL_W

    @property
    def x_right(self) -> float:
        return self.usable_w_units


def _geometry(
    arrangement: Arrangement, orientation: str, unit_mm: float, has_lyrics: bool = False
) -> _Geometry:
    if orientation == "portrait":
        usable_w_mm, usable_h_mm = A4_SHORT / MM - 2 * 18, A4_LONG / MM - 16 - 14
        header_mm = 15
    else:
        usable_w_mm, usable_h_mm = A4_LONG / MM - 2 * 14, A4_SHORT / MM - 13 - 12
        header_mm = 14
    # subtract the label gutter from staff width
    usable_w_mm -= LEFT_LABEL_W * unit_mm
    # row height = staff band + rhythm lane depth + header clearance (+ lyric line)
    lane_depth = max(HEAD_Y + STEM, RHYTHM_BOTTOM)  # deepest element below staff
    top_clearance = 1.3 + (LYRIC_CLEARANCE if has_lyrics else 0.0)
    row_height_units = 3.0 * STRING_SPACING + lane_depth + top_clearance
    row_gap = 2.4  # extra vertical breathing room between systems
    return _Geometry(
        usable_w_units=usable_w_mm / unit_mm,
        usable_h_units=usable_h_mm / unit_mm,
        header_units=header_mm / unit_mm,
        row_height_units=row_height_units,
        unit_mm=unit_mm,
        title_pt=unit_mm * 5.6,
        meta_pt=unit_mm * 3.3,
        fret_pt=unit_mm * 4.6,
        bar_no_pt=unit_mm * 2.9,
        lw=1.0,
        tie_lw=unit_mm * 0.36,
        row_gap=row_gap,
    )


# ---------------------------------------------------------------- drawing


def render_png(
    arrangement: Arrangement,
    path: str | Path,
    tuning: Tuning = HIGH_G,
    title: str | None = None,
    orientation: str = "landscape",
    unit_mm: float = 2.3,
    watermark: str = DEFAULT_WATERMARK,
    lyrics_map: dict[Fraction, str] | None = None,
) -> list[Path]:
    """Draw the arrangement onto A4 page images. Returns written paths.

    ``lyrics_map`` (beat -> syllable, melody onsets only) adds a lyric line
    above every staff.
    """
    geometry = _geometry(arrangement, orientation, unit_mm, has_lyrics=bool(lyrics_map))
    measures = _build_measures(arrangement)
    rows = _pack_rows(measures, geometry.usable_w_units)
    pages = [rows[i : i + geometry.max_rows] for i in range(0, len(rows), geometry.max_rows)] or [[]]

    base = Path(path)
    written: list[Path] = []
    for index, page_rows in enumerate(pages, start=1):
        target = (
            base
            if len(pages) == 1
            else base.with_name(f"{base.stem}-p{index:02d}{base.suffix}")
        )
        fig = _figure(
            page_rows, arrangement, tuning, title, geometry, orientation, index, len(pages),
            watermark, lyrics_map,
        )
        fig.savefig(target, dpi=DPI)
        plt.close(fig)
        written.append(target)
    return written


def render_pdf(
    arrangement: Arrangement,
    path: str | Path,
    tuning: Tuning = HIGH_G,
    title: str | None = None,
    orientation: str = "landscape",
    unit_mm: float = 2.3,
    watermark: str = DEFAULT_WATERMARK,
    lyrics_map: dict[Fraction, str] | None = None,
) -> Path:
    """Multi-page A4 PDF from the same engine as :func:`render_png`."""
    from matplotlib.backends.backend_pdf import PdfPages

    geometry = _geometry(arrangement, orientation, unit_mm, has_lyrics=bool(lyrics_map))
    measures = _build_measures(arrangement)
    rows = _pack_rows(measures, geometry.usable_w_units)
    pages = [rows[i : i + geometry.max_rows] for i in range(0, len(rows), geometry.max_rows)] or [[]]
    target = Path(path)
    with PdfPages(str(target)) as pdf:
        for index, page_rows in enumerate(pages, start=1):
            fig = _figure(
                page_rows, arrangement, tuning, title, geometry, orientation, index, len(pages),
                watermark, lyrics_map,
            )
            pdf.savefig(fig)
            plt.close(fig)
    return target


def _figure(
    page_rows, arrangement, tuning, title, geometry, orientation, index, total,
    watermark: str = DEFAULT_WATERMARK,
    lyrics_map: dict[Fraction, str] | None = None,
) -> "plt.Figure":
    if orientation == "portrait":
        fig_w_in, fig_h_in, margin_in, top_in = A4_SHORT, A4_LONG, 18 * MM, 16 * MM
    else:
        fig_w_in, fig_h_in, margin_in, top_in = A4_LONG, A4_SHORT, 14 * MM, 13 * MM
    usable_w_in = fig_w_in - 2 * margin_in
    usable_h_in = fig_h_in - top_in - 12 * MM

    fig = plt.figure(figsize=(fig_w_in, fig_h_in), facecolor=PAGE_BG_TOP)

    # Full-page soft vertical wash for an eye-friendly, printed-paper feel.
    ax_bg = fig.add_axes([0, 0, 1, 1], zorder=0)
    ax_bg.set_axis_off()
    wash = np.linspace(0, 1, 256).reshape(-1, 1, 1)
    top_rgb = np.array(matplotlib.colors.to_rgb(PAGE_BG_TOP))
    bottom_rgb = np.array(matplotlib.colors.to_rgb(PAGE_BG_BOTTOM))
    gradient = (top_rgb * (1 - wash) + bottom_rgb * wash)[..., ::-1]
    ax_bg.imshow(gradient, aspect="auto", extent=[0, 1, 0, 1])

    ax = fig.add_axes(
        [margin_in / fig_w_in, (12 * MM) / fig_h_in, usable_w_in / fig_w_in, usable_h_in / fig_h_in],
        zorder=1, facecolor="none",
    )
    ax.set_xlim(geometry.x_left, geometry.x_right)
    ax.set_ylim(geometry.usable_h_units, 0)  # y grows downward
    ax.set_aspect("equal")
    ax.axis("off")

    if watermark:
        _draw_watermark(ax, geometry, watermark)

    ax.text(geometry.x_left, 0.2, title or f"UkeTab · {arrangement.difficulty}",
            fontsize=geometry.title_pt, fontweight="bold", color=TITLE_COLOR, va="top", ha="left")
    ax.text(geometry.x_left, geometry.header_units * 0.62, _meta(arrangement, tuning),
            fontsize=geometry.meta_pt, color="#6a6a5f", va="top", ha="left")
    if total > 1:
        ax.text(geometry.x_right, 0.2, f"{index} / {total}",
                fontsize=geometry.meta_pt, color=LABEL_COLOR, va="top", ha="right")

    # vertically center the systems when the page is sparse (few rows)
    pitch = geometry.row_height_units + geometry.row_gap
    content_h = len(page_rows) * pitch - geometry.row_gap
    slack = geometry.usable_h_units - geometry.header_units - content_h
    y = geometry.header_units + max(0.0, slack) * 0.42
    for row_index, row in enumerate(page_rows):
        _draw_row(
            ax, row, y, geometry,
            show_position_box=row_index == 0,
            is_last_row=row_index == len(page_rows) - 1 and index == total,
            lyrics_map=lyrics_map,
        )
        y += pitch
    return fig


def _draw_watermark(ax, geometry: _Geometry, watermark: str) -> None:
    """Faint tiled diagonal watermark across the body + a readable signature.

    Tiles are drawn at the bottom z-order so staff lines, noteheads and fret
    numbers stay fully legible over them; the signature sits top-right of the
    footer so a printed page still carries the owner.
    """
    cols, rows = 3, 4
    step_x = (geometry.x_right - geometry.x_left) / cols
    step_y = (geometry.usable_h_units - geometry.header_units) / rows
    font = geometry.unit_mm * 6.4
    for iy in range(rows):
        brick = (step_x / 2) if iy % 2 else 0.0
        for ix in range(cols + 1):
            ax.text(
                geometry.x_left + brick + ix * step_x,
                geometry.header_units + (iy + 0.5) * step_y,
                watermark,
                fontsize=font, rotation=-24, ha="center", va="center",
                color=WATERMARK_COLOR, alpha=WATERMARK_DIAG_ALPHA, zorder=0.1,
            )
    ax.text(
        geometry.x_right, geometry.usable_h_units - 0.15, watermark,
        fontsize=geometry.meta_pt, ha="right", va="bottom",
        color=WATERMARK_COLOR, alpha=WATERMARK_SIG_ALPHA, zorder=5,
    )


def _bar_span(top_line: float, bottom_line: float) -> tuple[float, float]:
    """Every bar line shares these exact endpoints: aligned by construction."""
    return top_line - STAFF_SPAN_TOP, bottom_line + STAFF_SPAN_BOTTOM


def _draw_row(
    ax,
    row: _Row,
    top: float,
    geometry: _Geometry,
    show_position_box: bool = False,
    is_last_row: bool = False,
    lyrics_map: dict[Fraction, str] | None = None,
) -> None:
    string_y = {s: top + (s - 1) * STRING_SPACING for s in (1, 2, 3, 4)}
    top_line, bottom_line = string_y[1], string_y[4]
    span_top, span_bottom = _bar_span(top_line, bottom_line)
    lw = geometry.lw
    has_lyrics = bool(lyrics_map)
    number_y = top_line - (LYRIC_Y + 0.55 if has_lyrics else 0.5)

    # string-name labels (A/E/C/G) in the left gutter of every staff
    label_y = {s: string_y[s] for s in (1, 2, 3, 4)}
    for s in (1, 2, 3, 4):
        ax.text(
            geometry.x_left + LEFT_LABEL_W * 0.35, label_y[s], STRING_LABELS[s],
            fontsize=geometry.meta_pt * 0.95, color=LABEL_COLOR, ha="left", va="center",
        )

    # rhythm lane: collect noteheads first (so we can beam within each beat),
    # then draw stems/flags and connecting beams.
    heads: list[_Head] = []
    x0 = 0.0
    last_bar_x = 0.0
    for measure in row.measures:
        base_x = x0
        if not measure.cells:
            x0 += measure.width
            continue
        for cell in measure.cells:
            cx = base_x + cell.x
            for s in (1, 2, 3, 4):
                ax.hlines(string_y[s], cx, cx + cell.width, color=STAFF_COLOR, lw=lw)
            for rhythm in cell.rhythm:
                heads.append(_Head(x=cx + cell.width / 2, slot=cell.slot, rhythm=rhythm))
            for note in cell.notes:
                _draw_fret(
                    ax, cx + cell.width / 2, string_y[note.fingering.string], note, geometry,
                )
            if lyrics_map:
                syllable = lyrics_map.get(cell.slot)
                if syllable:
                    ax.text(
                        cx + cell.width / 2, top_line - LYRIC_Y, syllable,
                        fontsize=geometry.meta_pt * 1.25, color=LYRIC_COLOR,
                        ha="center", va="center", zorder=4,
                    )
        # bar line + measure number
        bar_x = base_x + measure.width - BAR_LINE_GAP
        ax.vlines(bar_x, span_top, span_bottom, color=BAR_COLOR, lw=lw * 1.4)
        ax.text(bar_x - 0.25, number_y - (0.28 if has_lyrics else 0.0), str(measure.bar),
                fontsize=geometry.bar_no_pt, color=LABEL_COLOR, va="bottom", ha="right")
        last_bar_x = bar_x
        x0 = base_x + measure.width
    # leading bar line: same endpoints as every other bar line
    ax.vlines(0.0, span_top, span_bottom, color=BAR_COLOR, lw=lw * 1.4)

    # final double barline closes the very last row of the piece
    if is_last_row and row.measures and last_bar_x > 0.0:
        ax.vlines(last_bar_x, span_top, span_bottom, color=BAR_COLOR, lw=lw * 1.4)
        ax.vlines(last_bar_x + 0.42, span_top, span_bottom, color=BAR_COLOR, lw=lw * 2.6)

    _draw_rhythm_lane(ax, heads, bottom_line, geometry, Fraction(1))

    # fretboard position box: lowest shifted fret used anywhere on this row
    frets = [
        note.fingering.fret
        for measure in row.measures
        for cell in measure.cells
        for note in cell.notes
        if note.fingering.fret >= 2
    ]
    if frets and show_position_box:
        _draw_position_box(ax, min(frets), top_line, geometry, has_lyrics=has_lyrics)


def _draw_position_box(
    ax, fret: int, top_line: float, geometry: _Geometry, has_lyrics: bool = False
) -> None:
    """Small rounded box above the row start naming the hand position."""
    ax.text(
        0.3, top_line - (0.45 + (LYRIC_Y + 0.55 if has_lyrics else 0.0)), f"{fret}",
        fontsize=geometry.bar_no_pt * 1.05, color="#7a7468",
        ha="left", va="bottom",
        bbox=dict(boxstyle="round,pad=0.28", fc="#eef0e4", ec="#b9b8a8", lw=geometry.lw * 0.8),
    )


#: rhythm lane geometry below the staff (layout units)
HEAD_Y = 1.9  # notehead center depth below the bottom staff line
HEAD_W = 1.12
HEAD_H = 0.8
STEM = 1.5  # stem length (both directions)
BEAM_THICK = 0.16
BEAM_LEVEL_GAP = 0.3  # vertical spacing between 1st/2nd beam lines
STEM_EDGE = 0.52  # stem offset from head center (fraction of HEAD_W)
FLAG_L = 0.7  # flag droop length; one per 8th level
RHYTHM_BOTTOM = 4.0  # bar line depth through the rhythm lane


@dataclass
class _Head:
    """One notehead to place in the rhythm lane."""

    x: float
    slot: Fraction
    rhythm: Rhythm

    @property
    def flags(self) -> int:
        return _flags_for(self.rhythm.value)

    @property
    def downward(self) -> bool:
        return self.rhythm.role == "bass"


def _flags_for(value: Fraction) -> int:
    """Number of flags/beams: 0=quarter-or-longer, 1=eighth, 2=sixteenth."""
    if value >= 1:
        return 0
    if value >= Fraction(1, 2):
        return 1
    return 2


def _hollow(value: Fraction) -> bool:
    return value >= 2


def _beam_key(head: _Head, slot_beats: Fraction) -> tuple:
    """Heads beamed only when eighth-or-shorter, same role, same beat group."""
    return (int(head.slot / slot_beats), head.rhythm.role, head.flags)


def _draw_rhythm_lane(
    ax, heads: list[_Head], bottom_line: float, geometry: _Geometry, beat_len: Fraction
) -> None:
    """Draw noteheads + stems, then beam consecutive short notes per beat."""
    head_y = bottom_line + HEAD_Y
    for head in heads:
        _draw_head_only(ax, head.x, head_y, head.rhythm, geometry)

    # group consecutive beamable heads (same beat + role + flag level)
    _draw_tie_arcs(ax, heads, head_y, geometry)
    groups: dict[tuple, list[_Head]] = {}
    for head in heads:
        if head.flags == 0 or head.rhythm.tie_from is not None:
            continue
        groups.setdefault(_beam_key(head, beat_len), []).append(head)

    beamed_ids: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda h: h.x)
        if members[-1].x - members[0].x < 0.5:  # same-slot chord: skip beam
            continue
        _draw_beam_group(ax, members, head_y, geometry)
        beamed_ids.update(id(m) for m in members)

    for head in heads:
        if id(head) in beamed_ids:
            continue
        _draw_stem(ax, head, head_y, geometry, flags=head.flags)


def _stem_x(head: _Head) -> float:
    sign = -1 if head.downward else 1
    return head.x + sign * HEAD_W * STEM_EDGE


def _draw_head_only(ax, x: float, head_y: float, rhythm: Rhythm, geometry: _Geometry) -> None:
    color = ROLE_COLORS.get(rhythm.role, "#1a1a1a")
    ax.add_patch(
        Ellipse(
            (x, head_y), HEAD_W, HEAD_H, angle=-18,
            facecolor="none" if _hollow(rhythm.value) else color,
            edgecolor=color, lw=geometry.lw * 1.1, zorder=3,
        )
    )
    if rhythm.value >= 4:  # whole note: bare head, no dot/stem
        return
    if rhythm.dotted:
        ax.plot([x + HEAD_W * 0.8], [head_y], marker="o", ms=geometry.fret_pt * 0.28,
                color=color, zorder=3)


def _draw_tie_arcs(ax, heads: list[_Head], head_y: float, geometry: _Geometry) -> None:
    """Arcs joining a multi-value note's segment noteheads (e.g. 2.5 beats)."""
    x_by_slot: dict[Fraction, float] = {}
    for head in heads:
        x_by_slot.setdefault(head.slot, head.x)
    for head in heads:
        previous = head.rhythm.tie_from
        if previous is not None and previous in x_by_slot:
            color = ROLE_COLORS.get(head.rhythm.role, "#1a1a1a")
            ax.add_patch(FancyArrowPatch(
                (x_by_slot[previous] + HEAD_W * 0.62, head_y),
                (head.x - HEAD_W * 0.62, head_y),
                connectionstyle="arc3,rad=0.32", arrowstyle="-",
                color=color, lw=geometry.tie_lw * 1.6, alpha=0.85,
            ))


def _draw_stem(ax, head: _Head, head_y: float, geometry: _Geometry, flags: int = 0) -> None:
    if head.rhythm.value >= 4:
        return
    color = ROLE_COLORS.get(head.rhythm.role, "#1a1a1a")
    sx = _stem_x(head)
    if head.downward:
        tip = head_y + STEM
        ax.vlines(sx, head_y, tip, color=color, lw=geometry.lw * 1.2)
        for f in range(flags):
            y0 = tip + f * 0.32
            ax.add_patch(FancyArrowPatch(
                (sx, y0), (sx - FLAG_L, y0 - 0.6),
                connectionstyle="arc3,rad=-0.42", arrowstyle="-", color=color,
                lw=geometry.lw * 1.7,
            ))
    else:
        tip = head_y - STEM
        ax.vlines(sx, tip, head_y, color=color, lw=geometry.lw * 1.2)
        for f in range(flags):
            y0 = tip + f * 0.32
            ax.add_patch(FancyArrowPatch(
                (sx, y0), (sx + FLAG_L, y0 + 0.6),
                connectionstyle="arc3,rad=0.42", arrowstyle="-", color=color,
                lw=geometry.lw * 1.7,
            ))


def _draw_beam_group(ax, members: list[_Head], head_y: float, geometry: _Geometry) -> None:
    """Uniform-length stems joined by a beam bar; a 2nd beam for 16ths."""
    downward = members[0].downward
    color = ROLE_COLORS.get(members[0].rhythm.role, "#1a1a1a")
    first, last = members[0], members[-1]
    x_left, x_right = _stem_x(first), _stem_x(last)
    # stems to a common tip line
    tip = head_y + STEM if downward else head_y - STEM
    for head in members:
        sx = _stem_x(head)
        ax.vlines(sx, min(head_y, tip), max(head_y, tip), color=color, lw=geometry.lw * 1.2)
    beam0 = tip - BEAM_THICK / 2
    ax.add_patch(Rectangle(
        (x_left, beam0), x_right - x_left, BEAM_THICK, facecolor=color, edgecolor="none", zorder=4,
    ))
    if members[0].flags == 2:
        # 16th-level secondary beam sits on the head side of the primary
        offset = -(BEAM_THICK + BEAM_LEVEL_GAP) if downward else BEAM_THICK + BEAM_LEVEL_GAP
        beam1 = beam0 + offset
        for run in _flag_runs(members):
            if run[1] - run[0] < 2:
                continue
            a, b = members[run[0]], members[run[1] - 1]
            ax.add_patch(Rectangle(
                (_stem_x(a), beam1), _stem_x(b) - _stem_x(a), BEAM_THICK,
                facecolor=color, edgecolor="none", zorder=4,
            ))


def _flag_runs(members: list[_Head]) -> list[tuple[int, int]]:
    """Maximal [start,end) index runs of members sharing the top flag level."""
    runs: list[tuple[int, int]] = []
    level = members[0].flags
    start = 0
    for i in range(1, len(members) + 1):
        if i == len(members) or members[i].flags != level:
            runs.append((start, i))
            if i < len(members):
                level, start = members[i].flags, i
    return runs


def _draw_fret(ax, x: float, y: float, note: TabNote, geometry: _Geometry) -> None:
    ax.text(
        x, y, str(note.fingering.fret),
        fontsize=geometry.fret_pt, ha="center", va="center",
        fontweight="bold" if note.note.role == "melody" else "normal",
        color=ROLE_COLORS.get(note.note.role, "#1a1a1a"),
        bbox=dict(boxstyle="square,pad=0.08", fc=PAGE_BG_TOP, ec="none"),
    )


def _meta(arrangement, tuning) -> str:
    numerator, denominator = arrangement.time_signature
    grid_value = int(round(1 / arrangement.grid))
    tuning_desc = " ".join(
        f"{STRING_LABELS[s]}={pitch_name(tuning.open_pitch(s))}" for s in sorted(STRING_LABELS)
    )
    return (
        f"UkeTab {arrangement.difficulty}  |  {arrangement.tempo_bpm:g} BPM  |  "
        f"{numerator}/{denominator}  |  网格 1/{grid_value}  |  调弦(高G): {tuning_desc}  |  "
        "黑=旋律 蓝=低音 灰=和声"
    )
