using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using OpenUkulele.Desktop.Models;
using OpenUkulele.Desktop.Services;

namespace OpenUkulele.Desktop.Tests.Services;

/// <summary>Test double that replays scripted stdout lines and honors cancellation.</summary>
internal sealed class FakeProcessRunner : IProcessRunner
{
    private readonly Func<ProcessSpec, Func<string, Task>, CancellationToken, Task<ProcessOutcome>> _behavior;

    public ProcessSpec? LastSpec { get; private set; }

    public FakeProcessRunner(
        Func<ProcessSpec, Func<string, Task>, CancellationToken, Task<ProcessOutcome>> behavior)
    {
        _behavior = behavior;
    }

    /// <summary>Replays fixed stdout lines, then reports a normal exit.</summary>
    public static FakeProcessRunner Emitting(IEnumerable<string> stdoutLines, int exitCode = 0)
        => Run(async (spec, onLine, _) =>
        {
            foreach (var line in stdoutLines)
            {
                if (!string.IsNullOrWhiteSpace(line))
                {
                    await onLine(line);
                }
            }

            return new ProcessOutcome(ProcessEndReason.Exited, exitCode, [.. stdoutLines], string.Empty);
        });

    public static FakeProcessRunner Run(
        Func<ProcessSpec, Func<string, Task>, CancellationToken, Task<ProcessOutcome>> behavior)
        => new(behavior);

    public Task<ProcessOutcome> RunAsync(
        ProcessSpec spec,
        Func<string, Task> onStdoutLine,
        CancellationToken cancellationToken)
    {
        LastSpec = spec;
        return _behavior(spec, onStdoutLine, cancellationToken);
    }
}

internal static class ServiceHarness
{
    public static PythonProcessArrangementService Create(
        IProcessRunner runner, DesktopOptions? options = null)
    {
        // Environment.ProcessPath is a guaranteed-existing absolute file path.
        options ??= new DesktopOptions
        {
            PythonExecutable = Environment.ProcessPath ?? "python",
            Module = "uketab",
            ProcessTimeoutSeconds = 60,
        };
        return new PythonProcessArrangementService(
            runner, Options.Create(options), NullLogger<PythonProcessArrangementService>.Instance);
    }

    /// <summary>Synchronous IProgress so tests observe reports deterministically.</summary>
    public static IProgress<ArrangementProgress> Collecting(List<ArrangementProgress> sink)
        => new SyncProgress<ArrangementProgress>(sink.Add);

    private sealed class SyncProgress<T>(Action<T> handler) : IProgress<T>
    {
        public void Report(T value) => handler(value);
    }
}
