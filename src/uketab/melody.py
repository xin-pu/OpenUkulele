"""Select a stable monophonic melody trajectory from audio candidates."""

from __future__ import annotations

from collections.abc import Sequence

from .models import NoteEvent

ONSET_TOLERANCE_SECONDS = 0.04
PHRASE_GAP_SECONDS = 1.5


def select_melody(events: Sequence[NoteEvent]) -> list[NoteEvent]:
    """Return one continuity-weighted candidate for each simultaneous onset group.

    Basic Pitch may emit several pitches for one vocal onset.  This small
    deterministic filter avoids treating the highest short artifact as melody;
    it is intentionally not a substitute for source separation.
    """
    groups = _onset_groups(sorted(events, key=lambda event: (event.onset, event.pitch)))
    selected: list[NoteEvent] = []
    previous: NoteEvent | None = None
    for group in groups:
        if previous is None or group[0].onset - previous.onset > PHRASE_GAP_SECONDS:
            choice = max(group, key=lambda event: (event.duration, event.pitch))
        else:
            choice = min(
                group,
                key=lambda event: (
                    abs(event.pitch - previous.pitch)
                    + (6 if abs(event.pitch - previous.pitch) > 7 else 0)
                    - min(event.duration, 1.0) * 0.2,
                    -event.duration,
                ),
            )
        selected.append(choice)
        previous = choice
    return selected


def _onset_groups(events: Sequence[NoteEvent]) -> list[list[NoteEvent]]:
    groups: list[list[NoteEvent]] = []
    for event in events:
        if not groups or event.onset - groups[-1][0].onset > ONSET_TOLERANCE_SECONDS:
            groups.append([event])
        else:
            groups[-1].append(event)
    return groups
