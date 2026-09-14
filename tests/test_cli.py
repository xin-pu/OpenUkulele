"""CLI end-to-end tests with generated MIDI fixtures."""

import json
import sys
import types

from uketab.cli import main
from uketab.errors import EXIT_ARRANGE, EXIT_INPUT, EXIT_OK, EXIT_USAGE

from conftest import write_midi


def run(*args):
    return main(list(args))


def test_happy_path_both_difficulties(tmp_path, twinkle_mid, capsys):
    out = tmp_path / "out"
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out))
    assert code == EXIT_OK
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "twinkle-easy.gp5",
        "twinkle-easy.txt",
        "twinkle-hard.gp5",
        "twinkle-hard.txt",
        "twinkle-report.json",
    ]
    report = json.loads((out / "twinkle-report.json").read_text(encoding="utf-8"))
    assert report["arrangements"]["easy"]["passed"] is True
    assert report["arrangements"]["hard"]["passed"] is True
    assert report["warnings"] == []
    # no stray temp directories left behind
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".uketab-tmp-")]


def test_out_of_range_melody_fails_easy_but_keeps_hard(tmp_path, capsys):
    # C5..A5 melody exceeds the easy 0-5 fret ceiling.
    path = tmp_path / "high.mid"
    write_midi(path, [(72, 0, 0.5), (76, 0.5, 0.5), (79, 1, 0.5), (76, 1.5, 0.5)])
    out = tmp_path / "out"
    code = run("arrange", str(path), "--output-dir", str(out))
    assert code == EXIT_ARRANGE
    names = sorted(p.name for p in out.iterdir())
    assert "high-easy.txt" not in names
    assert "high-easy.gp5" not in names
    assert "high-hard.txt" in names
    assert "high-report.json" in names
    report = json.loads((out / "high-report.json").read_text(encoding="utf-8"))
    assert "easy" not in report["arrangements"]
    assert any("easy" in w and "无法生成" in w for w in report["warnings"])


def test_unplayable_for_both_exits_arrange(tmp_path):
    path = tmp_path / "alien.mid"
    write_midi(path, [(30, 0, 1)])  # far below the instrument
    out = tmp_path / "out"
    code = run("arrange", str(path), "--output-dir", str(out))
    assert code == EXIT_ARRANGE
    report = json.loads((out / "alien-report.json").read_text(encoding="utf-8"))
    assert report["arrangements"] == {}


def test_nonempty_output_dir_rejected(tmp_path, twinkle_mid):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("x")
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out))
    assert code == EXIT_USAGE
    assert (out / "stale.txt").exists()  # untouched


def test_empty_existing_output_dir_accepted(tmp_path, twinkle_mid):
    out = tmp_path / "out"
    out.mkdir()
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out))
    assert code == EXIT_OK


def test_unsupported_extension_is_usage_error(tmp_path):
    path = tmp_path / "song.flac"
    path.write_bytes(b"x")
    code = run("arrange", str(path), "--output-dir", str(tmp_path / "o"))
    assert code == EXIT_USAGE


def test_missing_input_file_is_input_error(tmp_path):
    code = run("arrange", str(tmp_path / "ghost.mid"), "--output-dir", str(tmp_path / "o"))
    assert code == EXIT_INPUT


def test_tempo_override(tmp_path, twinkle_mid):
    out = tmp_path / "out"
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out), "--tempo", "100")
    assert code == EXIT_OK
    report = json.loads((out / "twinkle-report.json").read_text(encoding="utf-8"))
    assert report["input"]["tempo_bpm"] == 100
    assert report["input"]["tempo_provided"] is True
    assert any("--tempo" in w for w in report["warnings"])


def test_verbose_prints_stages(tmp_path, twinkle_mid, capsys):
    out = tmp_path / "out"
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out), "--verbose")
    assert code == EXIT_OK
    captured = capsys.readouterr().out
    assert "输入" in captured
    assert "量化网格" in captured


def test_melody_with_bass(tmp_path, melody_bass_mid):
    out = tmp_path / "out"
    code = run("arrange", str(melody_bass_mid), "--output-dir", str(out))
    assert code == EXIT_OK
    report = json.loads((out / "melody_bass-report.json").read_text(encoding="utf-8"))
    roles = report["arrangements"]["hard"]["roles"]
    assert roles.get("bass", 0) > 0
    assert roles.get("melody", 0) > 0


def test_png_flag_writes_images(tmp_path, twinkle_mid):
    import pytest

    pytest.importorskip("matplotlib")
    out = tmp_path / "out"
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out), "--png")
    assert code == EXIT_OK
    names = sorted(p.name for p in out.iterdir())
    assert "twinkle-easy.png" in names
    assert "twinkle-hard.png" in names


def test_no_png_by_default(tmp_path, twinkle_mid):
    out = tmp_path / "out"
    code = run("arrange", str(twinkle_mid), "--output-dir", str(out))
    assert code == EXIT_OK
    assert not [p for p in out.iterdir() if p.suffix == ".png"]


def test_mocked_audio_end_to_end(tmp_path, monkeypatch):
    bp = types.ModuleType("basic_pitch")
    bp.ICASSP_2022_MODEL_PATH = "/fake/models/nmp"
    inference = types.ModuleType("basic_pitch.inference")
    inference.predict = (
        lambda path, model_path=None, onset_threshold=0.5: (object(), None, [(0.0, 0.5, 72, 0.9), (0.5, 1.0, 74, 0.8)])
    )
    monkeypatch.setitem(sys.modules, "basic_pitch", bp)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inference)

    audio = tmp_path / "hum.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 32)
    out = tmp_path / "out"
    code = run("arrange", str(audio), "--tempo", "96", "--output-dir", str(out))
    assert code == EXIT_OK
    report = json.loads((out / "hum-report.json").read_text(encoding="utf-8"))
    assert report["input"]["source"] == "audio"
    assert report["input"]["tempo_bpm"] == 96
    assert any("人工听辨" in w for w in report["warnings"])


def test_mocked_audio_default_tempo_warning(tmp_path, monkeypatch):
    bp = types.ModuleType("basic_pitch")
    bp.ICASSP_2022_MODEL_PATH = "/fake/models/nmp"
    inference = types.ModuleType("basic_pitch.inference")
    inference.predict = (
        lambda path, model_path=None, onset_threshold=0.5: (object(), None, [(0.0, 0.5, 72, 0.9)])
    )
    monkeypatch.setitem(sys.modules, "basic_pitch", bp)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inference)

    audio = tmp_path / "hum.ogg"
    audio.write_bytes(b"OggS" + b"\x00" * 32)
    out = tmp_path / "out"
    code = run("arrange", str(audio), "--output-dir", str(out))
    assert code == EXIT_OK
    report = json.loads((out / "hum-report.json").read_text(encoding="utf-8"))
    assert report["input"]["tempo_bpm"] == 80
    assert report["input"]["tempo_provided"] is False
    assert any("默认 80" in w for w in report["warnings"])
