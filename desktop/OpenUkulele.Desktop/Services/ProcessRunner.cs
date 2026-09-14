using System.Diagnostics;
using System.Text;

namespace OpenUkulele.Desktop.Services;

/// <summary>
/// Runs a child process via <see cref="Process"/> with <c>UseShellExecute=false</c>,
/// redirecting stdout/stderr in UTF-8. On timeout or cancellation it kills the
/// whole process tree so no orphan Python lingers (design §4.2, ADR 0001).
/// </summary>
public sealed class ProcessRunner : IProcessRunner
{
    /// <inheritdoc />
    public async Task<ProcessOutcome> RunAsync(
        ProcessSpec spec,
        Func<string, Task> onStdoutLine,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(spec);
        ArgumentNullException.ThrowIfNull(onStdoutLine);

        using var process = new Process { StartInfo = BuildStartInfo(spec) };
        var lines = new List<string>();
        var stderr = new StringBuilder();

        // OutputDataReceived fires on pool threads; serialize async callbacks to
        // preserve per-line ordering without blocking the event handler.
        var gate = new object();
        Task dispatch = Task.CompletedTask;

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null)
            {
                return;
            }

            var captured = e.Data;
            lock (lines)
            {
                lines.Add(captured);
            }

            lock (gate)
            {
                dispatch = dispatch
                    .ContinueWith(
                        _ => onStdoutLine(captured),
                        CancellationToken.None,
                        TaskContinuationOptions.None,
                        TaskScheduler.Default)
                    .Unwrap();
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null)
            {
                lock (stderr)
                {
                    stderr.AppendLine(e.Data);
                }
            }
        };

        using var timeoutCts = new CancellationTokenSource(spec.Timeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, timeoutCts.Token);

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        var endReason = ProcessEndReason.Exited;
        try
        {
            await process.WaitForExitAsync(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            endReason = timeoutCts.IsCancellationRequested
                ? ProcessEndReason.TimedOut
                : ProcessEndReason.Cancelled;
            KillTree(process);
            await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
        }

        await dispatch.ConfigureAwait(false);

        int? exitCode = endReason == ProcessEndReason.Exited ? process.ExitCode : null;
        string[] snapshot;
        lock (lines)
        {
            snapshot = [.. lines];
        }

        string stdErrText;
        lock (stderr)
        {
            stdErrText = stderr.ToString();
        }

        return new ProcessOutcome(endReason, exitCode, snapshot, stdErrText);
    }

    private static ProcessStartInfo BuildStartInfo(ProcessSpec spec)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = spec.FileName,
            WorkingDirectory = spec.WorkingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = false,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var argument in spec.Arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        foreach (var (key, value) in spec.Environment)
        {
            startInfo.Environment[key] = value;
        }

        return startInfo;
    }

    private static void KillTree(Process process)
    {
        try
        {
            process.Kill(entireProcessTree: true);
        }
        catch (InvalidOperationException)
        {
            // Exited between the cancellation check and the kill; benign.
        }
    }
}
