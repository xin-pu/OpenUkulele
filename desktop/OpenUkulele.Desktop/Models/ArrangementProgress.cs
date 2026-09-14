namespace OpenUkulele.Desktop.Models;

/// <summary>A progress report from the running job.</summary>
/// <param name="OperationId">Correlation id shared with the Python process.</param>
/// <param name="Stage">Current pipeline stage.</param>
/// <param name="Percent">0–100, monotonic per job.</param>
/// <param name="Message">Human-readable Chinese message for display only.</param>
public sealed record ArrangementProgress(
    string OperationId,
    ArrangementStage Stage,
    int Percent,
    string Message);
