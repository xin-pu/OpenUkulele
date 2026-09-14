"""High-G re-entrant tuning: pitch <-> (string, fret) mapping.

String numbering is 1..4 for A4, E4, C4, G4 (display order, thinnest first).
The 4th string G4 (MIDI 67) is *higher* than the 3rd string C4 (MIDI 60);
nothing in this module may assume string number correlates monotonically
with pitch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import STRING_COUNT

#: Open-string MIDI pitches by string number: 1=A4, 2=E4, 3=C4, 4=G4.
#: The re-entrant high G means string 4 (67) sounds above string 3 (60).
HIGH_G_OPEN_PITCHES: dict[int, int] = {1: 69, 2: 64, 3: 60, 4: 67}


@dataclass(frozen=True)
class Tuning:
    """Ordered open-string pitches; index i holds the pitch of string i+1."""

    open_pitches: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.open_pitches) != STRING_COUNT:
            raise ValueError(
                f"tuning must define exactly {STRING_COUNT} strings, got {len(self.open_pitches)}"
            )

    def open_pitch(self, string: int) -> int:
        self._check_string(string)
        return self.open_pitches[string - 1]

    def fret_for_pitch(self, string: int, pitch: int) -> int | None:
        """Fret on ``string`` producing ``pitch``, or None if impossible."""
        self._check_string(string)
        fret = pitch - self.open_pitches[string - 1]
        return fret if fret >= 0 else None

    def pitch_at(self, string: int, fret: int) -> int:
        self._check_string(string)
        return self.open_pitches[string - 1] + fret

    @property
    def lowest_pitch(self) -> int:
        return min(self.open_pitches)

    @property
    def highest_pitch(self) -> int:
        return max(self.open_pitches)

    def _check_string(self, string: int) -> None:
        if not 1 <= string <= STRING_COUNT:
            raise ValueError(f"string number must be 1..{STRING_COUNT}, got {string}")


#: Default instrument: high-G (re-entrant) re-entrant ukulele.
HIGH_G = Tuning(
    open_pitches=tuple(HIGH_G_OPEN_PITCHES[i] for i in range(1, STRING_COUNT + 1))
)


def enumerate_candidates(
    pitch: int, tuning: Tuning = HIGH_G, max_fret: int = 15
) -> tuple[tuple[int, int], ...]:
    """All ``(string, fret)`` pairs sounding ``pitch``.

    Strings are returned in display order 1..4. A pitch is reachable when it
    lies between the lowest open string and the highest ``string+max_fret``;
    candidates never assume pitch monotonicity across strings.
    """
    candidates: list[tuple[int, int]] = []
    for string in range(1, STRING_COUNT + 1):
        fret = tuning.fret_for_pitch(string, pitch)
        if fret is not None and fret <= max_fret:
            candidates.append((string, fret))
    return tuple(candidates)


def playable_pitch_range(tuning: Tuning = HIGH_G, max_fret: int = 15) -> tuple[int, int]:
    """Inclusive (lowest, highest) MIDI pitch reachable on the instrument."""
    lowest = tuning.lowest_pitch
    highest = max(tuning.pitch_at(s, max_fret) for s in range(1, STRING_COUNT + 1))
    return lowest, highest


PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def pitch_name(pitch: int) -> str:
    """Scientific-pitch label, e.g. 69 -> 'A4'."""
    octave = pitch // 12 - 1
    return f"{PITCH_NAMES[pitch % 12]}{octave}"
