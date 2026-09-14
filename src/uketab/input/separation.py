"""Optional local Demucs vocal-stem extraction."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from contextlib import contextmanager
from importlib.util import find_spec
from pathlib import Path
from typing import Iterator

from ..errors import InputError


@contextmanager
def separated_vocals(audio_path: str | Path) -> Iterator[Path]:
    """Yield a temporary Demucs vocals stem and remove it on context exit."""
    if find_spec("demucs") is None:
        raise InputError(
            "人声分离不可用：未安装 demucs",
            "安装 separation extra（pip install uketab[separation]），或去掉 --separate-vocals",
        )
    source = Path(audio_path)
    with tempfile.TemporaryDirectory(prefix="uketab-demucs-") as output:
        try:
            subprocess.run(
                [sys.executable, "-m", "demucs.separate", "--two-stems", "vocals", "--out", output, str(source)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise InputError("人声分离超时", "缩短音频片段到 30-60 秒后重试") from exc
        except subprocess.CalledProcessError as exc:
            raise InputError("人声分离失败", exc.stderr[-500:] or "确认音频可解码并已安装 ffmpeg") from exc
        stem = Path(output) / "htdemucs" / source.stem / "vocals.wav"
        if not stem.exists():
            raise InputError("人声分离未生成 vocals stem", "确认 demucs 模型安装完整")
        yield stem
