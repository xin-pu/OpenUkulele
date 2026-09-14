namespace OpenUkulele.Desktop.Models;

/// <summary>Fixed progress stage vocabulary agreed with the Python protocol (design §4.1).</summary>
public enum ArrangementStage
{
    /// <summary>Reading and parsing the input file.</summary>
    Input,

    /// <summary>Audio transcription (Basic Pitch) — audio inputs only.</summary>
    Transcribe,

    /// <summary>Quantization and timing normalization.</summary>
    Normalize,

    /// <summary>Arrangement and fingering solving.</summary>
    Arrange,

    /// <summary>Lyric alignment — only when a lyric file is supplied.</summary>
    Lyrics,

    /// <summary>Exporting txt/GP5/image/PDF and the report.</summary>
    Export,
}

/// <summary>Maps protocol stage strings; unknown names are protocol errors upstream.</summary>
public static class ArrangementStageParser
{
    /// <summary>Try to parse a stage token from an NDJSON progress event.</summary>
    /// <param name="value">Raw stage string.</param>
    /// <param name="stage">Parsed stage when successful.</param>
    /// <returns>Whether the token belongs to the fixed vocabulary.</returns>
    public static bool TryParse(string? value, out ArrangementStage stage)
    {
        stage = value switch
        {
            "input" => ArrangementStage.Input,
            "transcribe" => ArrangementStage.Transcribe,
            "normalize" => ArrangementStage.Normalize,
            "arrange" => ArrangementStage.Arrange,
            "lyrics" => ArrangementStage.Lyrics,
            "export" => ArrangementStage.Export,
            _ => default,
        };
        return value is "input" or "transcribe" or "normalize" or "arrange" or "lyrics" or "export";
    }
}

/// <summary>Stable machine error codes (design §4.2); never localized for logic.</summary>
public static class ArrangementErrorCodes
{
    /// <summary>Bad command line or missing argument.</summary>
    public const string Usage = "usage_error";

    /// <summary>Input file missing, corrupt, or unsupported.</summary>
    public const string Input = "input_error";

    /// <summary>At least one arrangement could not be produced; partial results may exist.</summary>
    public const string ArrangementPartial = "arrangement_partial";

    /// <summary>Export or filesystem failure.</summary>
    public const string Export = "export_error";

    /// <summary>stdout was not valid NDJSON or lacked a terminal event.</summary>
    public const string Protocol = "process_protocol_error";

    /// <summary>Process exceeded the configured timeout.</summary>
    public const string Timeout = "timeout";

    /// <summary>Job cancelled by the user or window close.</summary>
    public const string Cancelled = "cancelled";
}
