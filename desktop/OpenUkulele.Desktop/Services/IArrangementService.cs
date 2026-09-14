using OpenUkulele.Desktop.Models;

namespace OpenUkulele.Desktop.Services;

/// <summary>Boundary that drives tab generation in a Python subprocess.</summary>
public interface IArrangementService
{
    /// <summary>
    /// Run one arrange job to completion, reporting progress as NDJSON events
    /// arrive. Returns a result describing success, partial failure, cancellation,
    /// timeout, or a protocol/exit error; never throws for expected failures.
    /// </summary>
    /// <param name="request">Job parameters.</param>
    /// <param name="progress">Progress sink; safe to report from background threads.</param>
    /// <param name="cancellationToken">Cancel to kill the process tree.</param>
    /// <returns>The terminal result.</returns>
    Task<ArrangementJobResult> ArrangeAsync(
        ArrangementRequest request,
        IProgress<ArrangementProgress> progress,
        CancellationToken cancellationToken);
}
