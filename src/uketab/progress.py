"""NDJSON progress protocol for machine consumers (WPF desktop shell).

When ``--progress-json`` is set, stdout carries exactly one JSON object per
line and *only* JSON — human completion text is suppressed and diagnostics
go to stderr. Percentages never move backwards within a job. Stage names
are the fixed vocabulary agreed in the desktop design; anything else is a
protocol error the caller is expected to fail closed on.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

STAGES = ("input", "transcribe", "normalize", "arrange", "lyrics", "export")

# Stable UI error codes keyed by process exit code (design §4.2).
EXIT_TO_CODE = {
    2: "usage_error",
    3: "input_error",
    4: "arrangement_partial",
    5: "export_error",
}


class ProgressReporter:
    """Emit started/progress/completed/failed events; inert when disabled."""

    def __init__(self, enabled: bool, operation_id: str, stream: TextIO | None = None) -> None:
        self.enabled = enabled
        self.operation_id = operation_id
        self._stream = stream if stream is not None else sys.stdout
        self._percent = -1
        self._finished = False

    @classmethod
    def from_args(cls, args: "object") -> "ProgressReporter":
        enabled = bool(getattr(args, "progress_json", False))
        operation_id = str(getattr(args, "operation_id", "") or "")
        return cls(enabled, operation_id)

    def started(self, input_path: str) -> None:
        self._emit({"event": "started", "operationId": self.operation_id, "inputPath": input_path})

    def progress(self, stage: str, percent: int, message: str) -> None:
        if stage not in STAGES:
            raise ValueError(f"unknown progress stage {stage!r}")
        self._emit({
            "event": "progress",
            "operationId": self.operation_id,
            "stage": stage,
            "percent": percent,
            "message": message,
        })

    def completed(self, output_dir: str, report_path: str, exit_code: int) -> None:
        self._finished = True
        self._emit({
            "event": "completed",
            "operationId": self.operation_id,
            "outputDirectory": output_dir,
            "reportPath": report_path,
            "exitCode": exit_code,
        })

    def failed(
        self,
        exit_code: int,
        message: str,
        suggestion: str,
        code: str | None = None,
        output_dir: str | None = None,
        report_path: str | None = None,
    ) -> None:
        self._finished = True
        payload = {
            "event": "failed",
            "operationId": self.operation_id,
            "code": code or EXIT_TO_CODE.get(exit_code, f"exit_{exit_code}"),
            "message": message,
            "suggestion": suggestion,
            "exitCode": exit_code,
        }
        # Partial results (e.g. arrangement_partial) may still be openable.
        if output_dir is not None:
            payload["outputDirectory"] = output_dir
        if report_path is not None:
            payload["reportPath"] = report_path
        self._emit(payload)

    @property
    def finished(self) -> bool:
        return self._finished

    def _emit(self, payload: dict) -> None:
        if not self.enabled:
            return
        if payload.get("event") == "progress":
            # Contract: percent must not regress within a job.
            self._percent = max(self._percent, int(payload["percent"]))
            payload["percent"] = self._percent
        self._stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._stream.flush()
