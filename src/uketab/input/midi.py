"""MIDI -> NoteEvent adapter.

Merges all tracks, converts ticks to seconds by accumulating ``set_tempo``
meta messages, and pairs note-on/note-off per (channel, pitch). The adapter
only produces events; it makes no ukulele or difficulty decisions.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import mido

from ..errors import InputError
from ..models import NoteEvent

MIDI_EXTENSIONS = {".mid", ".midi"}


def load_midi(path: str | Path) -> tuple[list[NoteEvent], float, tuple[int, int], list[str]]:
    """Parse a MIDI file.

    Returns ``(events, tempo_bpm, time_signature, warnings)``. Raises
    :class:`~uketab.errors.InputError` (exit code 3) for empty files,
    zero-duration notes, dangling note-ons and unsupported timing.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise InputError(f"MIDI 文件不存在: {file_path}", "检查输入路径")

    try:
        mid = mido.MidiFile(file_path)
    except (OSError, EOFError, ValueError) as exc:
        raise InputError(f"无法读取 MIDI 文件: {file_path} ({exc})", "确认文件是标准 MIDI 格式") from exc

    if mid.type == 2:
        raise InputError("不支持的 MIDI 类型 2（异步独立轨道）", "导出为类型 0 或 1 的 MIDI 文件")

    ticks_per_beat = mid.ticks_per_beat
    if ticks_per_beat <= 0:  # SMPTE division appears as a negative raw value
        raise InputError("不支持的 SMPTE 时间格式", "导出使用拍/秒格式的 MIDI 文件")

    warnings: list[str] = []
    default_tempo = 500_000  # microseconds per quarter note (120 BPM)
    tempos = _collect_tempo_map(mid, default_tempo)

    time_signature = (4, 4)
    notes: list[tuple[float, float, int, int]] = []  # (onset_s, duration_s, pitch, velocity)
    open_notes: dict[tuple[int, int], list[tuple[float, int]]] = defaultdict(list)
    saw_time_signature = False

    # merge_tracks() yields delta times; accumulate them into absolute ticks.
    absolute_tick = 0
    for msg in mido.merge_tracks(mid.tracks):
        absolute_tick += msg.time
        tick_seconds = _seconds_at_tick(absolute_tick, ticks_per_beat, tempos, default_tempo)
        if msg.type == "set_tempo":
            continue  # already folded into the tempo map
        if msg.type == "time_signature":
            sig = (msg.numerator, msg.denominator)
            if not saw_time_signature:
                time_signature = sig
                saw_time_signature = True
            elif sig != time_signature:
                warnings.append(
                    f"MIDI 含多个拍号，仅使用首个 {time_signature[0]}/{time_signature[1]}"
                )
            continue
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes[(msg.channel, msg.note)].append((tick_seconds, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if not open_notes[key]:
                raise InputError(
                    f"悬空 note-off：通道 {msg.channel} 音高 {msg.note} 没有对应的 note-on",
                    "检查 MIDI 文件的音符配对",
                )
            onset, velocity = open_notes[key].pop(0)
            duration = tick_seconds - onset
            if duration <= 0:
                raise InputError(
                    f"零时值音符：通道 {msg.channel} 音高 {msg.note} 于 {onset:.3f}s",
                    "移除或修复 MIDI 中的零时值音符",
                )
            notes.append((onset, duration, msg.note, velocity))

    dangling = {k: v for k, v in open_notes.items() if v}
    if dangling:
        channel, pitch = sorted(dangling)[0]
        raise InputError(
            f"悬空 note-on：通道 {channel} 音高 {pitch} 未收到 note-off",
            "检查 MIDI 文件的音符配对",
        )
    if not notes:
        raise InputError(f"MIDI 文件没有音符事件: {file_path}", "提供一个包含音符的 MIDI 文件")

    notes.sort(key=lambda n: (n[0], n[2]))
    events = [
        NoteEvent(
            onset=onset,
            duration=duration,
            pitch=pitch,
            velocity=min(max(velocity / 127.0, 0.0), 1.0),
            source="midi",
        )
        for onset, duration, pitch, velocity in notes
    ]
    tempo_bpm = 60_000_000 / tempos[0][1] if tempos else 60_000_000 / default_tempo
    if len({t for _, t in tempos}) > 1:
        warnings.append(f"MIDI 含 {len(tempos)} 个速度变化，谱面使用首个速度 {tempo_bpm:.1f} BPM")
    return events, tempo_bpm, time_signature, warnings


def _collect_tempo_map(mid: mido.MidiFile, default_tempo: int) -> list[tuple[int, int]]:
    """Ordered (tick, tempo_us) changes; first entry is the initial tempo."""
    tempo_events: list[tuple[int, int]] = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                tempo_events.append((tick, msg.tempo))
    tempo_events.sort(key=lambda t: t[0])
    if not tempo_events:
        return [(0, default_tempo)]
    # The tempo in effect at tick 0 wins; later same-tick events keep the last.
    head = tempo_events[0]
    if head[0] > 0:
        return [(0, default_tempo), *tempo_events]
    deduped = [head]
    for tick, tempo in tempo_events[1:]:
        if tick != deduped[-1][0]:
            deduped.append((tick, tempo))
        else:
            deduped[-1] = (tick, tempo)
    return deduped


def _seconds_at_tick(
    tick: int, ticks_per_beat: int, tempos: list[tuple[int, int]], default_tempo: int
) -> float:
    """Accumulate seconds up to ``tick`` across tempo segments (absolute ticks)."""
    seconds = 0.0
    cursor = 0
    tempo = default_tempo
    for seg_tick, seg_tempo in tempos:
        if seg_tick >= tick:
            break
        seconds += (seg_tick - cursor) * tempo / (ticks_per_beat * 1_000_000)
        cursor = seg_tick
        tempo = seg_tempo
    seconds += (tick - cursor) * tempo / (ticks_per_beat * 1_000_000)
    return seconds
