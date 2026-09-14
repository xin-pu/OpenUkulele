"""Lyric ingestion and alignment to melody notes.

Lyrics are attached to the *melody* line only: bass/harmony notes are
accompaniment and stay lyric-free. Two source shapes are supported:

- LRC (``[mm:ss.xx]line``): lines carry real timestamps, converted to beats
  with the piece tempo; each line's syllables are distributed across the
  melody notes that start inside the line's beat window, in order.
- plain text: no timing; syllables zip onto melody notes in global order.

Alignment never invents positions: a syllable only lands on an actual
melody-note onset, so ASCII/image renderers can key off note beats alone.
CJK characters are one syllable each; Latin runs are grouped by word
(best-effort; syllable-accurate splitting for non-CJK is out of scope).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .errors import InputError
from .models import TabNote

_LRC_LINE = re.compile(r"\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\](.*)")
_TOKEN = re.compile(r"[A-Za-z0-9'’\-]+|.")  # latin word, else single char


@dataclass(frozen=True)
class LyricLine:
    start_seconds: float
    text: str


def parse_lrc(path: str | Path) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LRC_LINE.search(raw.strip())
        if not match:
            continue
        minutes, seconds, text = match.groups()
        text = text.strip()
        if text:
            lines.append(LyricLine(float(minutes) * 60 + float(seconds), text))
    if not lines:
        raise InputError(f"LRC 文件没有可解析的时间行: {path}", "确认每行以 [mm:ss.xx] 开头")
    lines.sort(key=lambda line: line.start_seconds)
    return lines


def parse_plain(path: str | Path) -> list[LyricLine]:
    text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise InputError(f"歌词文件为空: {path}", "检查文件内容")
    return [LyricLine(0.0, text)]  # single untimed line


def load_lyrics(path: str | Path) -> list[LyricLine]:
    """Parse ``.lrc`` by stamp lines, otherwise treat the file as plain text."""
    file_path = Path(path)
    if not file_path.exists():
        raise InputError(f"歌词文件不存在: {file_path}", "检查 --lyrics 路径")
    if file_path.suffix.lower() == ".lrc":
        return parse_lrc(file_path)
    lines = parse_plain(file_path)
    if any(_LRC_LINE.search(line) for line in file_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        return parse_lrc(file_path)  # extension lied; it is stamped
    return lines


def tokenize(text: str) -> list[str]:
    """Split a lyric line into singable tokens (CJK per char, latin per word)."""
    stripped = re.sub(r"[\s，。、！？；：,.!?;:\"“”‘’()（）—·]+", " ", text).strip()
    return [token for token in _TOKEN.findall(stripped) if token.strip()]


def beats_at_onsets(notes: list[TabNote]) -> list[Fraction]:
    """Onset beats of melody notes, ascending (deduped by identical beat)."""
    beats = sorted({note.note.beat for note in notes if note.note.role == "melody"})
    return beats


def align(
    lines: list[LyricLine],
    melody_beats: list[Fraction],
    tempo_bpm: float,
    window_tolerance_beats: Fraction = Fraction(0),
) -> dict[Fraction, str]:
    """Return ``beat -> lyric text`` for melody onsets.

    Each LRC line claims the melody notes starting in its window
    ``[start, next_start)``; its tokens are assigned to those notes in
    order. Timestamped lines use non-overlapping half-open windows by
    default, so one line cannot consume the next line's onset. Plain-text
    input (single line at t=0) covers the whole piece: tokens zip across
    every melody note.
    """
    if not melody_beats:
        return {}

    def to_beat(seconds: float) -> Fraction:
        return Fraction(str(seconds * tempo_bpm / 60.0)).limit_denominator(10**6)

    bounds = [to_beat(line.start_seconds) for line in lines]
    mapping: dict[Fraction, str] = {}

    for index, line in enumerate(lines):
        tokens = tokenize(line.text)
        if not tokens:
            continue
        start = bounds[index]
        # The default zero tolerance keeps adjacent LRC windows disjoint.
        # A caller may explicitly opt into a tolerance for a known offset.
        if index + 1 < len(lines):
            end = bounds[index + 1]
        else:
            end = melody_beats[-1] + 1
        window = [
            beat
            for beat in melody_beats
            if start - window_tolerance_beats <= beat < end and beat not in mapping
        ]
        for beat, token in zip(window, tokens):
            mapping[beat] = token
    return mapping


def attach(
    path: str | Path, notes: list[TabNote], tempo_bpm: float
) -> tuple[dict[Fraction, str], list[str]]:
    """Convenience: load, align, and report drops. Returns (mapping, warnings)."""
    lines = load_lyrics(path)
    beats = beats_at_onsets(notes)
    mapping = align(lines, beats, tempo_bpm)
    warnings: list[str] = []
    total_tokens = sum(len(tokenize(line.text)) for line in lines)
    if total_tokens > len(beats):
        warnings.append(
            f"歌词音节 {total_tokens} 个多于旋律音 {len(beats)} 个，"
            f"多余音节未显示（常见：转写漏音或歌词超出音频片段）"
        )
    elif total_tokens < len(beats):
        warnings.append(
            f"歌词音节 {total_tokens} 个少于旋律音 {len(beats)} 个，部分音符无词"
        )
    return mapping, warnings
