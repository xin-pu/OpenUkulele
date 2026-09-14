using System.IO;
using OpenUkulele.Desktop.Services;
using Shouldly;
using Xunit;

namespace OpenUkulele.Desktop.Tests.Services;

/// <summary>
/// Runs the real ProcessRunner against a short, controlled python script.
/// Requires python on PATH (dev worktree has it); skips cleanly otherwise.
/// Never touches transcription models — only stdout/exit/cancel semantics.
/// </summary>
public class ProcessRunnerIntegrationTests
{
    private static string? FindPython()
    {
        foreach (var name in new[] { "python", "python3", "py" })
        {
            foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? string.Empty)
                         .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            {
                var candidate = Path.Combine(dir, OperatingSystem.IsWindows() ? name + ".exe" : name);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
        }

        return null;
    }

    private static ProcessSpec Spec(string python, string script, int timeoutSeconds = 60) => new(
        python,
        ["-u", "-c", script],
        Path.GetTempPath(),
        new Dictionary<string, string> { ["PYTHONIOENCODING"] = "utf-8" },
        TimeSpan.FromSeconds(timeoutSeconds));

    [Fact]
    public async Task RunAsync_RealPython_NdjsonLinesDeliveredInOrder()
    {
        var python = FindPython();
        if (python is null) { return; } // no python on PATH: nothing to verify here
        const string script = """
            import json, sys
            for percent, stage in ((5, "input"), (50, "arrange"), (100, "export")):
                print(json.dumps({"event": "progress", "stage": stage, "percent": percent}), flush=True)
            print(json.dumps({"event": "completed", "exitCode": 0}), flush=True)
            sys.exit(0)
            """;

        var seen = new List<string>();
        var outcome = await new ProcessRunner().RunAsync(
            Spec(python!, script), line => { lock (seen) { seen.Add(line); } return Task.CompletedTask; },
            CancellationToken.None);

        outcome.End.ShouldBe(ProcessEndReason.Exited);
        outcome.ExitCode.ShouldBe(0);
        seen.Count.ShouldBe(4);
        seen[0].ShouldContain("input");
        seen[^1].ShouldContain("completed");
    }

    [Fact]
    public async Task RunAsync_Cancel_KillsProcessTree()
    {
        var python = FindPython();
        if (python is null) { return; } // no python on PATH: nothing to verify here
        const string script = """
            import sys, time
            print("ready", flush=True)
            time.sleep(30)
            sys.exit(0)
            """;
        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(1500));

        var outcome = await new ProcessRunner().RunAsync(
            Spec(python!, script, timeoutSeconds: 60),
            _ => Task.CompletedTask,
            cts.Token);

        outcome.End.ShouldBe(ProcessEndReason.Cancelled);
        outcome.ExitCode.ShouldBeNull();
    }

    [Fact]
    public async Task RunAsync_Timeout_KillsProcessTree()
    {
        var python = FindPython();
        if (python is null) { return; } // no python on PATH: nothing to verify here
        const string script = """
            import sys, time
            time.sleep(30)
            sys.exit(0)
            """;

        var outcome = await new ProcessRunner().RunAsync(
            Spec(python!, script, timeoutSeconds: 30) with { Timeout = TimeSpan.FromSeconds(1) },
            _ => Task.CompletedTask,
            CancellationToken.None);

        outcome.End.ShouldBe(ProcessEndReason.TimedOut);
    }
}
