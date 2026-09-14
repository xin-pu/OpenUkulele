namespace OpenUkulele.Desktop.Models;

/// <summary>Terminal status of a job.</summary>
public enum ArrangementStatus
{
    /// <summary>Both arrangements exported successfully.</summary>
    Completed,

    /// <summary>At least one version produced; the other could not be arranged.</summary>
    Partial,

    /// <summary>No output; see error fields.</summary>
    Failed,

    /// <summary>Cancelled by the user or window close.</summary>
    Cancelled,

    /// <summary>Killed after the configured timeout.</summary>
    TimedOut,
}

/// <summary>Files produced for one difficulty (paths; missing exports are null).</summary>
/// <param name="Txt">ASCII tab path.</param>
/// <param name="Gp5">GP5 path.</param>
/// <param name="Png">First PNG page, when present.</param>
/// <param name="Pdf">PDF path, when present.</param>
/// <param name="PngPages">All PNG pages in order (multi-page pieces).</param>
public sealed record ArrangementFileSet(
    string? Txt,
    string? Gp5,
    string? Png,
    string? Pdf,
    IReadOnlyList<string> PngPages);

/// <summary>Per-difficulty summary extracted from report.json (design §5.3).</summary>
/// <param name="Notes">Total tab notes.</param>
/// <param name="Bars">Bar count spanned.</param>
/// <param name="Passed">Validation passed flag.</param>
/// <param name="ShiftCount">Position shifts.</param>
/// <param name="MaxSpan">Largest fret span.</param>
/// <param name="BarreCount">Barre occurrences.</param>
/// <param name="DifficultyScore">Interpretive difficulty score 0–1.</param>
/// <param name="IssueCount">Validation issue count.</param>
public sealed record DifficultySummary(
    int Notes,
    int Bars,
    bool Passed,
    int ShiftCount,
    int MaxSpan,
    int BarreCount,
    double DifficultyScore,
    int IssueCount);

/// <summary>Outcome of one arrangement job: status, paths, warnings, and stable error info.</summary>
public sealed class ArrangementJobResult
{
    /// <summary>Terminal status.</summary>
    public required ArrangementStatus Status { get; init; }

    /// <summary>Correlation id for logs.</summary>
    public required string OperationId { get; init; }

    /// <summary>Process exit code when the process actually ran to completion.</summary>
    public int? ExitCode { get; init; }

    /// <summary>Stable machine error code (see <see cref="ArrangementErrorCodes"/>); null on success.</summary>
    public string? ErrorCode { get; init; }

    /// <summary>Human-readable failure message (Chinese, from the tool).</summary>
    public string? ErrorMessage { get; init; }

    /// <summary>Actionable suggestion for the failure.</summary>
    public string? Suggestion { get; init; }

    /// <summary>Report JSON path when the run produced one (also for partial results).</summary>
    public string? ReportPath { get; init; }

    /// <summary>Output directory when publishing happened.</summary>
    public string? OutputDirectory { get; init; }

    /// <summary>Warnings extracted from report.json.</summary>
    public IReadOnlyList<string> Warnings { get; init; } = [];

    /// <summary>Per-difficulty output files; empty when nothing was produced.</summary>
    public IReadOnlyDictionary<string, ArrangementFileSet> Outputs { get; init; }
        = new Dictionary<string, ArrangementFileSet>();

    /// <summary>Per-difficulty validation/role summary parsed from report.json.</summary>
    public IReadOnlyDictionary<string, DifficultySummary> Summaries { get; init; }
        = new Dictionary<string, DifficultySummary>();

    /// <summary>Wall-clock duration of the job.</summary>
    public TimeSpan Elapsed { get; init; }

    /// <summary>Whether results can be previewed (Completed or Partial).</summary>
    public bool HasResults => Status is ArrangementStatus.Completed or ArrangementStatus.Partial;
}
