"""Structured user-facing errors carrying CLI exit codes.

Exit codes (see design doc):
  0  both arrangements succeeded
  2  argument or format error
  3  input / transcription error
  4  at least one arrangement could not be produced
  5  export error
"""

from __future__ import annotations

from dataclasses import dataclass

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_ARRANGE = 4
EXIT_EXPORT = 5


@dataclass(frozen=True)
class UketabError(Exception):
    """An actionable error surfaced to the CLI as a message + exit code."""

    message: str
    suggestion: str = ""
    exit_code: int = EXIT_INPUT

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if self.suggestion:
            return f"{self.message} ({self.suggestion})"
        return self.message


class UsageError(UketabError):
    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message, suggestion, EXIT_USAGE)


class InputError(UketabError):
    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message, suggestion, EXIT_INPUT)


class ArrangementError(UketabError):
    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message, suggestion, EXIT_ARRANGE)


class ExportError(UketabError):
    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message, suggestion, EXIT_EXPORT)
