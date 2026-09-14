namespace OpenUkulele.Desktop.Services;

/// <summary>How the child process ended.</summary>
public enum ProcessEndReason
{
    /// <summary>The process exited on its own.</summary>
    Exited,

    /// <summary>Killed because the configured timeout elapsed.</summary>
    TimedOut,

    /// <summary>Killed because cancellation was requested.</summary>
    Cancelled,
}

/// <summary>Specification for one short-lived external process.</summary>
/// <param name="FileName">Executable to run.</param>
/// <param name="Arguments">Argument list (never a shell string).</param>
/// <param name="WorkingDirectory">Process working directory.</param>
/// <param name="Environment">Environment variable overrides (merged over the parent).</param>
/// <param name="Timeout">Hard kill deadline.</param>
public sealed record ProcessSpec(
    string FileName,
    IReadOnlyList<string> Arguments,
    string WorkingDirectory,
    IReadOnlyDictionary<string, string> Environment,
    TimeSpan Timeout);

/// <summary>Result of a run: how it ended, exit code, all stdout lines, stderr text.</summary>
/// <param name="End">Termination reason.</param>
/// <param name="ExitCode">Process exit code, when it exited normally.</param>
/// <param name="StdoutLines">Every stdout line observed (NDJSON in our protocol).</param>
/// <param name="StdErr">Full stderr text for diagnostics.</param>
public sealed record ProcessOutcome(
    ProcessEndReason End,
    int? ExitCode,
    IReadOnlyList<string> StdoutLines,
    string StdErr);

/// <summary>Process boundary for deterministic tests (design §4.2).</summary>
public interface IProcessRunner
{
    /// <summary>
    /// Run <paramref name="spec"/>; every stdout line is delivered to
    /// <paramref name="onStdoutLine"/> before the call returns, in order.
    /// Timeout or cancellation kills the whole process tree.
    /// </summary>
    /// <param name="spec">Process specification.</param>
    /// <param name="onStdoutLine">Ordered line callback (fast, non-blocking work only).</param>
    /// <param name="cancellationToken">Cancel to kill the tree.</param>
    /// <returns>The observed outcome.</returns>
    Task<ProcessOutcome> RunAsync(
        ProcessSpec spec,
        Func<string, Task> onStdoutLine,
        CancellationToken cancellationToken);
}
