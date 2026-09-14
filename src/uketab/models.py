"""Immutable domain models shared across the pipeline.

Time is stored in seconds at the input boundary (:class:`NoteEvent`) and in
beats (exact :class:`fractions.Fraction`) after normalization
(:class:`TimedPitch`), so no original timing precision is lost at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

Difficulty = Literal["easy", "hard"]
Role = Literal["melody", "bass", "harmony"]
RightHand = Literal["p", "i", "m", "a"]

#: String numbers 1..4 correspond to A4, E4, C4, G4 (thinnest to thickest).
STRING_COUNT = 4
MAX_FRET = 15


@dataclass(frozen=True)
class NoteEvent:
    """A single sounded note, seconds-based, straight from an input adapter."""

    onset: float
    duration: float
    pitch: int  # MIDI 0..127
    velocity: float  # 0.0..1.0
    source: str  # "midi" or "audio"


@dataclass(frozen=True)
class TimedPitch:
    """A pitch placed on the beat grid, with its musical role."""

    beat: Fraction
    duration_beats: Fraction
    pitch: int
    velocity: float
    role: Role = "melody"


@dataclass(frozen=True)
class Fingering:
    """How one pitch is produced on the instrument."""

    string: int  # 1..4: A, E, C, G; same numbering is used for display
    fret: int  # 0..15
    finger_left: int | None = None  # 1..4; None for open strings
    finger_right: RightHand | None = None


@dataclass(frozen=True)
class TabNote:
    note: TimedPitch
    fingering: Fingering


@dataclass(frozen=True)
class Arrangement:
    """A complete, validated arrangement for one difficulty."""

    difficulty: Difficulty
    tempo_bpm: float
    time_signature: tuple[int, int]
    notes: tuple[TabNote, ...]
    grid: Fraction  # shortest represented subdivision, in beats


@dataclass(frozen=True)
class ValidationIssue:
    code: str  # one of validation.ISSUE_CODES
    message: str
    bar: int | None = None  # 1-based measure number
    beat: Fraction | None = None  # beat position within the piece


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    errors: tuple[ValidationIssue, ...]
    shift_count: int
    max_span: int
    barre_count: int
    difficulty_score: float
