"""Audio -> NoteEvent adapter (optional Basic Pitch dependency).

Accepts ordinary media files (WAV/MP3/M4A/OGG) up to 100 MB and 5
minutes, runs local Basic Pitch inference, and converts confident note
events to :class:`~uketab.models.NoteEvent` with ``source="audio"``.

No silence trimming, pitch shifting or source separation is performed.
Transcribed candidates need human listening verification -- the CLI adds
that warning to the report.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import InputError
from ..models import NoteEvent

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg"}
MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 5 * 60
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


def load_audio(
    path: str | Path, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
) -> tuple[list[NoteEvent], list[str]]:
    """Transcribe an audio file locally.

    Returns ``(events, warnings)``; warnings always include the manual
    listening-verification notice.
    """
    file_path = Path(path)
    warnings = ["转写候选需要人工听辨：Basic Pitch 输出可能包含错音/漏音"]

    if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise InputError(
            f"不支持的音频格式: {file_path.suffix or '(无扩展名)'}",
            "使用 WAV、MP3、M4A 或 OGG，或改用 MIDI 输入",
        )
    if not file_path.exists():
        raise InputError(f"音频文件不存在: {file_path}", "检查输入路径")
    size = file_path.stat().st_size
    if size > MAX_BYTES:
        raise InputError(
            f"音频文件过大: {size / 1024 / 1024:.1f} MB（上限 100 MB）",
            "裁剪或压缩音频后重试",
        )

    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict as bp_predict
    except ImportError as exc:
        raise InputError(
            "音频转写不可用：未安装 basic-pitch",
            "安装项目的 audio extra（pip install uketab[audio]），或改用 MIDI",
        ) from exc

    try:
        duration = _audio_duration(file_path)
    except Exception:
        duration = None  # no local decoder for this container: skip the check
    if duration is not None and duration > MAX_SECONDS:
        raise InputError(
            f"音频时长 {duration:.0f}s 超过 5 分钟上限",
            "裁剪到 5 分钟以内（推荐 30-60 秒单声部片段）",
        )

    try:
        result = bp_predict(
            str(file_path),
            _model_path(ICASSP_2022_MODEL_PATH),
            onset_threshold=confidence_threshold,
        )
        note_events = result[2]  # List[(start_s, end_s, pitch, amplitude, ...)]
    except Exception as exc:  # basic_pitch raises varied backend errors
        raise InputError(
            f"音频推理失败: {exc}", "确认文件可解码（非损坏、非 DRM 加密），或改用 MIDI",
        ) from exc

    events: list[NoteEvent] = []
    for start, end, pitch, amplitude, *_ in note_events:
        duration_s = float(end) - float(start)
        if duration_s <= 0:
            continue
        events.append(
            NoteEvent(
                onset=float(start),
                duration=duration_s,
                pitch=int(round(pitch)),
                velocity=min(max(float(amplitude), 0.0), 1.0),
                source="audio",
            )
        )
    events.sort(key=lambda e: (e.onset, e.pitch))
    if not events:
        raise InputError(
            "音频中没有检测到足够置信度的音符",
            "尝试更干净、更近的录音，或改用 MIDI 输入",
        )
    return events, warnings


def _model_path(default_model_path) -> str:
    """Pick a model file the installed backend can actually load.

    basic-pitch 0.4.0's bundled TensorFlow SavedModel predates TF 2.16's
    loading changes and fails on modern TF; the identical ONNX export
    loads reliably via onnxruntime, so prefer it when available.
    """
    try:
        import onnxruntime  # noqa: F401

        return f"{default_model_path}.onnx"
    except ImportError:
        return str(default_model_path)


def _audio_duration(file_path: Path) -> float | None:
    """Best-effort duration probe; returns None when nothing can decode it."""
    try:
        import soundfile as sf  # type: ignore

        return float(sf.info(str(file_path)).duration)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        import librosa  # type: ignore

        return float(librosa.get_duration(path=str(file_path)))  # pragma: no cover
    except ImportError:
        return None
