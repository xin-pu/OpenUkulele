"""Audio adapter tests with a fully mocked Basic Pitch."""

import sys
import types


import pytest

from uketab.errors import InputError
from uketab.input.audio import load_audio


@pytest.fixture
def fake_basic_pitch(monkeypatch):
    """Install a fake basic_pitch package into sys.modules."""
    bp = types.ModuleType("basic_pitch")
    bp.ICASSP_2022_MODEL_PATH = "/fake/models/nmp"
    inference = types.ModuleType("basic_pitch.inference")
    notes = {"note": [(0.0, 0.5, 72, 0.9, 1.0), (0.5, 1.0, 74, 0.8, 1.0)]}

    def predict(path, model_path=None, onset_threshold=0.5):
        return (object(), None, [(0.0, 0.5, 72, 0.9), (0.5, 1.0, 74, 0.8)])

    inference.predict = predict
    monkeypatch.setitem(sys.modules, "basic_pitch", bp)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inference)
    return notes


def test_load_audio_returns_events_and_warning(tmp_path, fake_basic_pitch):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 64)
    events, warnings = load_audio(audio)
    assert [(e.pitch, e.onset, e.duration, e.source) for e in events] == [
        (72, 0.0, 0.5, "audio"),
        (74, 0.5, 0.5, "audio"),
    ]
    assert any("人工听辨" in w for w in warnings)


def test_rejects_unknown_extension(tmp_path):
    audio = tmp_path / "song.flac"
    audio.write_bytes(b"x")
    with pytest.raises(InputError, match="不支持的音频格式"):
        load_audio(audio)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(InputError, match="不存在"):
        load_audio(tmp_path / "ghost.wav")


def test_rejects_oversized_file(tmp_path, monkeypatch):
    audio = tmp_path / "big.wav"
    audio.write_bytes(b"x")
    monkeypatch.setattr(
        type(audio), "stat", lambda self, **kw: types.SimpleNamespace(st_size=200 * 1024 * 1024)
    )
    with pytest.raises(InputError, match="过大"):
        load_audio(audio)


def test_model_missing_gives_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "basic_pitch", None)  # import -> None fails
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    with pytest.raises(InputError, match="audio extra"):
        load_audio(audio)


def test_inference_failure_wrapped(tmp_path, fake_basic_pitch, monkeypatch):
    def boom(path):
        raise RuntimeError("decoder blew up")

    monkeypatch.setattr(sys.modules["basic_pitch.inference"], "predict", boom)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    with pytest.raises(InputError, match="音频推理失败"):
        load_audio(audio)


def test_no_confident_notes(tmp_path, fake_basic_pitch, monkeypatch):
    monkeypatch.setattr(
        sys.modules["basic_pitch.inference"],
        "predict",
        lambda path, model_path=None, onset_threshold=0.5: (object(), None, []),
    )
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    with pytest.raises(InputError, match="没有检测到"):
        load_audio(audio)
