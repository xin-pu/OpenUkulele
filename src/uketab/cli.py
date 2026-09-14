"""Command-line entry point: argument parsing, orchestration, exit codes.

    uketab arrange <input> --output-dir <dir> [--tempo BPM] [--verbose] [--debug]
                       [--png --pdf --orientation] [--watermark T] [--lyrics F]
                       [--progress-json --operation-id <uuid>]

Exit codes:
  0  both arrangements succeeded
  2  argument or format error
  3  input / transcription error
  4  at least one arrangement could not be produced
  5  export error

With ``--progress-json`` stdout carries only NDJSON events (see
``progress.py``); human text and verbose logs move to stderr.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .arrangement import EASY_PROFILE, arrange, hard_profile
from .errors import (
    ArrangementError,
    EXIT_ARRANGE,
    EXIT_EXPORT,
    EXIT_OK,
    UketabError,
    UsageError,
)
from .fallback import resolve_with_fallback
from .input.audio import AUDIO_EXTENSIONS
from .input.midi import MIDI_EXTENSIONS, load_midi
from .models import Arrangement
from .progress import ProgressReporter
from .render.ascii import render_ascii
from .render.gp5 import write_gp5
from .report import build_report, write_report
from .timing import EIGHTH, SIXTEENTH, has_sixteenth_precision, normalize_events

DEFAULT_AUDIO_TEMPO = 80.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uketab",
        description="离线尤克里里指弹谱生成器（高 G 调弦，简易/困难双版本）",
    )
    parser.add_argument("--version", action="version", version=f"uketab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    arrange_parser = sub.add_parser("arrange", help="从 MIDI 或音频生成指弹谱")
    arrange_parser.add_argument("input", help="输入文件（.mid/.midi 或音频）")
    arrange_parser.add_argument(
        "--output-dir", required=True, help="输出目录（必须不存在或为空）"
    )
    arrange_parser.add_argument(
        "--tempo", type=float, default=None, help="BPM（音频输入未提供时默认 80 并警告）"
    )
    arrange_parser.add_argument("--verbose", action="store_true", help="打印各阶段细节")
    arrange_parser.add_argument("--debug", action="store_true", help="显示原始堆栈")
    arrange_parser.add_argument("--png", action="store_true", help="额外输出 A4 图片谱 (PNG)")
    arrange_parser.add_argument("--pdf", action="store_true", help="额外输出 A4 图片谱 (PDF)")
    arrange_parser.add_argument(
        "--orientation",
        choices=("landscape", "portrait"),
        default="landscape",
        help="图片谱纸张方向（默认横向 A4）",
    )
    arrange_parser.add_argument(
        "--watermark",
        default="",
        help="图片谱水印文字（默认关闭；传入非空文本启用）",
    )
    arrange_parser.add_argument(
        "--lyrics",
        default=None,
        metavar="PATH",
        help="歌词文件（.lrc 带时间轴，或纯文本逐音节对齐旋律音），渲染到谱面上方",
    )
    arrange_parser.add_argument(
        "--transpose",
        type=int,
        default=0,
        metavar="SEMITONES",
        help="将所有输入音符统一移调 N 个半音（可为负）；超出琴音域的音按八度归一并在报告警告",
    )
    arrange_parser.add_argument(
        "--progress-json",
        action="store_true",
        help="stdout 只输出 NDJSON 进度事件（供 WPF 子进程消费）；默认行为不变",
    )
    arrange_parser.add_argument(
        "--operation-id",
        default="",
        help="--progress-json 模式下回显的操作标识，用于跨进程日志关联",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = ProgressReporter.from_args(args)
    if reporter.enabled:
        # stdout is a pure NDJSON channel in progress mode: no console
        # encoding surprises for the reader, human text moves to stderr.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):  # pragma: no cover - exotic streams
            pass
        reporter.started(args.input)
    try:
        return _run_arrange(args, parser, reporter)
    except UketabError as error:
        if args.debug:
            raise
        print(f"错误：{error.message}", file=sys.stderr)
        if error.suggestion:
            print(f"建议：{error.suggestion}", file=sys.stderr)
        if reporter.enabled and not reporter.finished:
            reporter.failed(error.exit_code, error.message, error.suggestion)
        return error.exit_code


def _run_arrange(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    reporter: ProgressReporter | None = None,
) -> int:
    reporter = reporter or ProgressReporter(False, "")
    verbose = _logger(args.verbose, sink=sys.stderr if reporter.enabled else sys.stdout)
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    warnings: list[str] = []

    if args.png or args.pdf:
        import importlib.util

        if importlib.util.find_spec("matplotlib") is None:
            raise UsageError(
                "图片谱导出需要 matplotlib",
                "安装项目的 image extra（pip install uketab[image]），或去掉 --png/--pdf",
            )

    reporter.progress("input", 5, "正在读取输入")
    if suffix in MIDI_EXTENSIONS:
        events, tempo_bpm, time_signature, midi_warnings = load_midi(input_path)
        warnings.extend(midi_warnings)
        tempo_provided = False
        source = "midi"
        if args.tempo is not None:
            tempo_bpm = args.tempo
            tempo_provided = True
            warnings.append(f"已用 --tempo {args.tempo:g} 覆盖 MIDI 自带速度")
    elif suffix in AUDIO_EXTENSIONS:
        from .input.audio import load_audio

        reporter.progress("transcribe", 15, "正在转写音频")
        events, audio_warnings = load_audio(input_path)
        warnings.extend(audio_warnings)
        time_signature = (4, 4)
        source = "audio"
        if args.tempo is not None:
            tempo_bpm = args.tempo
            tempo_provided = True
        else:
            tempo_bpm = DEFAULT_AUDIO_TEMPO
            tempo_provided = False
            warnings.append(f"音频输入未提供 --tempo，默认 {DEFAULT_AUDIO_TEMPO:g} BPM")
    else:
        raise UsageError(
            f"不支持的输入格式: '{suffix or '无扩展名'}'",
            "使用 .mid/.midi 或 WAV/MP3/M4A/OGG",
        )

    verbose(f"输入: {input_path}（source={source}, {len(events)} 个音符事件）")
    verbose(f"速度 {tempo_bpm:g} BPM，拍号 {time_signature[0]}/{time_signature[1]}")

    from .tuning import playable_pitch_range

    if args.transpose:
        if not -24 <= args.transpose <= 24:
            raise UsageError("--transpose 超出范围", "半音数必须在 -24 到 +24 之间")
        events, _ = apply_transpose(events, args.transpose)
        warnings.append(f"已整体移调 {args.transpose:+d} 个半音（音程关系保持不变）")

    lowest, highest = playable_pitch_range()
    below = sum(1 for e in events if e.pitch < lowest)
    above = sum(1 for e in events if e.pitch > highest)
    if below or above:
        parts = []
        if below:
            parts.append(f"{below} 个音符低于 {lowest}（{pitch_label(lowest)}）")
        if above:
            parts.append(f"{above} 个音符高于 {highest}（{pitch_label(highest)}）")
        warnings.append(
            "超出尤克里里音域：" + "，".join(parts)
            + "；这些音符所在小节无法编配。可先移调到 C4-C6 区间，或改用 MIDI 输入"
        )

    use_sixteenths = has_sixteenth_precision(events, tempo_bpm)
    grid_hard = SIXTEENTH if use_sixteenths else EIGHTH
    verbose(f"量化网格: easy=1/8, hard={'1/16' if use_sixteenths else '1/8'}")

    reporter.progress("normalize", 25, "正在量化与节拍归一")
    normalized_easy = normalize_events(events, tempo_bpm, EIGHTH)
    normalized_hard = normalize_events(events, tempo_bpm, grid_hard)

    results: dict[str, tuple[Arrangement, object] | None] = {"easy": None, "hard": None}
    failures: list[str] = []

    reporter.progress("arrange", 50, "正在编配与求解指法")

    for difficulty, normalized, grid in (
        ("easy", normalized_easy, EIGHTH),
        ("hard", normalized_hard, grid_hard),
    ):
        profile = EASY_PROFILE if difficulty == "easy" else hard_profile(grid)
        bars = arrange(normalized, time_signature, profile)
        resolution = resolve_with_fallback(bars, profile, time_signature)
        for action in resolution.actions:
            verbose(f"降级: 小节 {action.bar} 执行 {action.step}（{action.reason}）")
        if not resolution.success:
            failed = sorted(resolution.failed_bars) or [
                issue.bar
                for issue in resolution.report.errors
                if issue.bar is not None
            ]
            warnings.append(
                f"{difficulty} 版本无法生成：失败小节 {sorted(set(failed))}（详见报告）"
            )
            failures.append(difficulty)
            continue
        notes = tuple(note for solution in resolution.solutions for note in solution.notes)
        arrangement = Arrangement(
            difficulty=difficulty,  # type: ignore[arg-type]
            tempo_bpm=tempo_bpm,
            time_signature=time_signature,
            notes=notes,
            grid=grid,
        )
        if not resolution.report.passed:  # pragma: no cover - solver guarantees this
            warnings.append(f"{difficulty} 版本校验未通过，不输出谱面")
            failures.append(difficulty)
            continue
        results[difficulty] = (arrangement, resolution)
        report = resolution.report
        verbose(
            f"{difficulty}: {len(notes)} 音符, {report.shift_count} 次换把, "
            f"最大跨度 {report.max_span}, 横按 {report.barre_count}, "
            f"难度分 {report.difficulty_score}"
        )

    lyrics_by_difficulty: dict = {}
    if args.lyrics:
        from .lyrics import attach

        reporter.progress("lyrics", 65, "正在对齐歌词")
        lyric_warnings_done = False
        for difficulty in ("easy", "hard"):
            entry = results[difficulty]
            if entry is None:
                continue
            mapping, lyric_warnings = attach(args.lyrics, list(entry[0].notes), tempo_bpm)
            lyrics_by_difficulty[difficulty] = mapping
            if not lyric_warnings_done:
                warnings.extend(lyric_warnings)
                lyric_warnings_done = True

    output_dir = _prepare_output_dir(Path(args.output_dir))
    stem = input_path.stem
    reporter.progress("export", 85, "正在导出文件")
    temp_dir = Path(tempfile.mkdtemp(prefix=".uketab-tmp-", dir=output_dir.parent))
    try:
        for difficulty in ("easy", "hard"):
            entry = results[difficulty]
            if entry is None:
                continue
            arrangement, _ = entry
            lyrics_map = lyrics_by_difficulty.get(difficulty)
            ascii_text = render_ascii(arrangement, lyrics_map=lyrics_map)
            (temp_dir / f"{stem}-{difficulty}.txt").write_text(ascii_text, encoding="utf-8")
            write_gp5(arrangement, temp_dir / f"{stem}-{difficulty}.gp5", title=stem)
            written_files = f"{stem}-{difficulty}.txt / {stem}-{difficulty}.gp5"
            if args.png:
                from .render.image import render_png

                png_paths = render_png(
                    arrangement,
                    temp_dir / f"{stem}-{difficulty}.png",
                    title=stem,
                    orientation=args.orientation,
                    watermark=args.watermark,
                    lyrics_map=lyrics_map,
                )
                written_files += " / " + ", ".join(p.name for p in png_paths)
            if args.pdf:
                from .render.image import render_pdf

                render_pdf(
                    arrangement,
                    temp_dir / f"{stem}-{difficulty}.pdf",
                    title=stem,
                    orientation=args.orientation,
                    watermark=args.watermark,
                    lyrics_map=lyrics_map,
                )
                written_files += f" / {stem}-{difficulty}.pdf"
            verbose(f"写出 {written_files}")

        report = build_report(
            input_path=str(input_path),
            source=source,
            event_count=len(events),
            tempo_bpm=tempo_bpm,
            tempo_provided=tempo_provided,
            time_signature=time_signature,
            grid_easy=EIGHTH,
            grid_hard=grid_hard,
            easy=results["easy"],
            hard=results["hard"],
            warnings=warnings,
        )
        write_report(report, temp_dir / f"{stem}-report.json")
        _publish(temp_dir, output_dir)
    except UketabError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise UketabError(
            f"输出失败: {exc}", "检查输出目录权限与磁盘空间", EXIT_EXPORT
        ) from exc
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    verbose(f"输出目录: {output_dir}")
    report_path = str(output_dir / f"{stem}-report.json")
    if failures:
        summary = f"{'、'.join(failures)} 版本不可生成，详见报告失败小节列表"
        if reporter.enabled:
            reporter.failed(
                EXIT_ARRANGE,
                summary,
                "打开报告查看失败小节；或降低要求改用旋律更单一的输入",
                code="arrangement_partial",
                output_dir=str(output_dir),
                report_path=report_path,
            )
        else:
            print(f"完成（{summary}，退出码 {EXIT_ARRANGE}）")
        return EXIT_ARRANGE
    if reporter.enabled:
        reporter.completed(str(output_dir), report_path, EXIT_OK)
    else:
        print(f"完成：简易版与困难版均已生成于 {output_dir}")
    return EXIT_OK


def pitch_label(pitch: int) -> str:
    from .tuning import pitch_name

    return pitch_name(pitch)


def apply_transpose(events, semitones: int):
    """Shift every event by one interval-preserving number of semitones.

    A global transposition is only valid when every resulting pitch is in the
    instrument range.  Per-note octave folding is intentionally forbidden: it
    changes melodic and harmonic intervals.
    """
    from dataclasses import replace

    from .tuning import playable_pitch_range

    lowest, highest = playable_pitch_range()
    out = [replace(event, pitch=event.pitch + semitones) for event in events]
    outside = [event.pitch for event in out if not lowest <= event.pitch <= highest]
    if outside:
        raise ArrangementError(
            "整体移调后仍有音符超出尤克里里音域",
            "改用较小的移调值、提供旋律更单一的输入，或在后续编辑中手动改写超域音",
        )
    return out, 0


def _prepare_output_dir(output_dir: Path) -> Path:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise UsageError(f"输出路径已存在且不是目录: {output_dir}", "另选输出目录")
        if any(output_dir.iterdir()):
            raise UsageError(f"输出目录不为空: {output_dir}", "清空该目录或另选路径")
    parent = output_dir.parent if str(output_dir.parent) else Path(".")
    if not parent.exists():
        raise UsageError(f"输出目录的父目录不存在: {parent}", "先创建父目录")
    return output_dir


def _publish(temp_dir: Path, output_dir: Path) -> None:
    """Move the finished temp directory into place atomically."""
    if output_dir.exists():
        output_dir.rmdir()  # guaranteed empty by _prepare_output_dir
    os.replace(temp_dir, output_dir)


def _logger(enabled: bool, sink=None):
    def log(message: str) -> None:
        if enabled:
            print(f"[uketab] {message}", file=sink)

    return log


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
