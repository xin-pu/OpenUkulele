"""Optional Demucs vocal-separation adapter tests."""

import pytest

from uketab.errors import InputError
from uketab.input.separation import separated_vocals


def test_separated_vocals_missing_demucs_gives_actionable_error(tmp_path, monkeypatch):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"x")
    monkeypatch.setattr("uketab.input.separation.find_spec", lambda name: None)

    with pytest.raises(InputError, match="separation extra"):
        with separated_vocals(song):
            pass
