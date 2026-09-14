using OpenUkulele.Desktop.Models;
using OpenUkulele.Desktop.Services;
using Shouldly;
using Xunit;

namespace OpenUkulele.Desktop.Tests.Services;

public class PythonProcessArrangementServiceTests
{
    private static ArrangementRequest Request(string outDir)
        => new(@"C:\media\song.mid", outDir);

    private static string[] HappyNdjson(string outDir, string reportPath) =>
    [
        """{"event":"started","operationId":"op","inputPath":"C:\\media\\song.mid"}""",
        """{"event":"progress","operationId":"op","stage":"input","percent":5,"message":"读取"}""",
        """{"event":"progress","operationId":"op","stage":"normalize","percent":25,"message":"量化"}""",
        """{"event":"progress","operationId":"op","stage":"arrange","percent":50,"message":"编配"}""",
        """{"event":"progress","operationId":"op","stage":"export","percent":85,"message":"导出"}""",
        $$"""{"event":"completed","operationId":"op","outputDirectory":"{{outDir.Replace("\\","\\\\")}}","reportPath":"{{reportPath.Replace("\\","\\\\")}}","exitCode":0}""",
    ];

    [Fact]
    public async Task ArrangeAsync_ProgressJson_ReportsMappedStage()
    {
        var outDir = Path.Combine(Path.GetTempPath(), "uk-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(outDir);
        var progress = new List<ArrangementProgress>();
        var service = ServiceHarness.Create(FakeProcessRunner.Emitting(HappyNdjson(outDir, Path.Combine(outDir, "x.json"))));
        try
        {
            var result = await service.ArrangeAsync(Request(outDir), ServiceHarness.Collecting(progress), CancellationToken.None);

            result.Status.ShouldBe(ArrangementStatus.Completed);
            result.ErrorMessage.ShouldBeNull();
            progress.Select(p => p.Stage).ShouldBe(
                [ArrangementStage.Input, ArrangementStage.Normalize, ArrangementStage.Arrange, ArrangementStage.Export]);
            progress.Select(p => p.Percent).ShouldBe([5, 25, 50, 85]);
        }
        finally
        {
            Directory.Delete(outDir, recursive: true);
        }
    }

    [Fact]
    public async Task ArrangeAsync_MalformedProgress_ReturnsProtocolError()
    {
        var lines = new[]
        {
            """{"event":"started","operationId":"op","inputPath":"x"}""",
            "这不是 JSON",
        };
        var service = ServiceHarness.Create(FakeProcessRunner.Emitting(lines, exitCode: 3));
        var result = await service.ArrangeAsync(
            Request(Path.GetTempPath()), new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

        result.Status.ShouldBe(ArrangementStatus.Failed);
        result.ErrorCode.ShouldBe(ArrangementErrorCodes.Protocol);
    }

    [Fact]
    public async Task ArrangeAsync_UnknownStage_ReturnsProtocolError()
    {
        var lines = new[]
        {
            """{"event":"progress","operationId":"op","stage":"teleport","percent":50,"message":"?"}""",
        };
        var service = ServiceHarness.Create(FakeProcessRunner.Emitting(lines, exitCode: 3));
        var result = await service.ArrangeAsync(
            Request(Path.GetTempPath()), new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

        result.ErrorCode.ShouldBe(ArrangementErrorCodes.Protocol);
    }

    [Fact]
    public async Task ArrangeAsync_NoTerminalEvent_Exit2_MapsUsageError()
    {
        var service = ServiceHarness.Create(FakeProcessRunner.Emitting([], exitCode: 2));
        var result = await service.ArrangeAsync(
            Request(Path.GetTempPath()), new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

        result.Status.ShouldBe(ArrangementStatus.Failed);
        result.ErrorCode.ShouldBe(ArrangementErrorCodes.Usage);
        result.ExitCode.ShouldBe(2);
    }

    [Fact]
    public async Task ArrangeAsync_Cancelled_ReturnsCancelledAndKills()
    {
        using var cts = new CancellationTokenSource();
        var runner = FakeProcessRunner.Run(async (_, _, token) =>
        {
            await Task.CompletedTask;
            // The real ProcessRunner converts cancellation into a Cancelled
            // ProcessOutcome; here we mimic that contract directly.
            return new ProcessOutcome(ProcessEndReason.Cancelled, null, [], "cancelled");
        });
        var service = ServiceHarness.Create(runner);

        await cts.CancelAsync();
        var result = await service.ArrangeAsync(
            Request(Path.GetTempPath()), new Progress<ArrangementProgress>(_ => { }), cts.Token);

        result.Status.ShouldBe(ArrangementStatus.Cancelled);
        result.ErrorCode.ShouldBe(ArrangementErrorCodes.Cancelled);
    }

    [Fact]
    public async Task ArrangeAsync_ArrangementPartialWithReport_ParsesSummaryAndWarnings()
    {
        var outDir = Path.Combine(Path.GetTempPath(), "uk-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(outDir);
        try
        {
            var reportPath = Path.Combine(outDir, "song-report.json");
            File.WriteAllText(reportPath, """
                {"warnings":["歌词音节少于旋律音"],"arrangements":{
                  "easy":{"notes":14,"bars":4,"passed":true,
                    "validation":{"passed":true,"shift_count":0,"max_span":0,"barre_count":0,"difficulty_score":0.09,"issues":[]}}}}
                """);
            File.WriteAllText(Path.Combine(outDir, "song-easy.txt"), "tab");
            File.WriteAllText(Path.Combine(outDir, "song-easy.png"), "png");
            var lines = new[]
            {
                $$"""{"event":"failed","operationId":"op","code":"arrangement_partial","message":"hard 版本不可生成","suggestion":"改用旋律更单一的输入","exitCode":4,"outputDirectory":"{{outDir.Replace("\\","\\\\")}}","reportPath":"{{reportPath.Replace("\\","\\\\")}}"}""",
            };
            var service = ServiceHarness.Create(FakeProcessRunner.Emitting(lines, exitCode: 4));

            var result = await service.ArrangeAsync(
                Request(outDir), new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

            result.Status.ShouldBe(ArrangementStatus.Partial);
            result.HasResults.ShouldBeTrue();
            result.Warnings.ShouldContain(w => w.Contains("歌词"));
            result.Summaries.ShouldContainKey("easy");
            result.Summaries["easy"].Notes.ShouldBe(14);
            result.Summaries["easy"].Passed.ShouldBeTrue();
            result.Outputs["easy"].Txt.ShouldBe(Path.Combine(outDir, "song-easy.txt"));
            result.Outputs["easy"].Png.ShouldNotBeNull();
            result.Outputs.ShouldNotContainKey("hard");
        }
        finally
        {
            Directory.Delete(outDir, recursive: true);
        }
    }

    [Fact]
    public async Task ArrangeAsync_BuildsArgumentsIncludingProgressProtocol()
    {
        var runner = FakeProcessRunner.Emitting([], exitCode: 2);
        var service = ServiceHarness.Create(runner);
        await service.ArrangeAsync(
            new ArrangementRequest(@"C:\m\s.mid", @"C:\out", LyricsPath: @"C:\m\l.lrc",
                TempoBpm: 96, ExportPdf: true, Portrait: true, Watermark: "me@x"),
            new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

        var args = runner.LastSpec!.Arguments;
        string.Join(" ", args.Take(4)).ShouldBe(string.Join(' ', "-m", "uketab", "arrange", @"C:\m\s.mid"));
        args.ShouldContain("--progress-json");
        args.ShouldContain("--operation-id");
        args.ShouldContain("--lyrics");
        args.ShouldContain("96");
        args.ShouldContain("--pdf");
        var idx = args.ToList().IndexOf("--orientation");
        args[idx + 1].ShouldBe("portrait");
        args.ShouldContain("--watermark");
    }

    [Fact]
    public async Task ArrangeAsync_PythonPathConfigured_InjectsPythonPathEnv()
    {
        var runner = FakeProcessRunner.Emitting([], exitCode: 2);
        var options = new DesktopOptions
        {
            PythonExecutable = Environment.ProcessPath ?? "python",
            Module = "uketab",
            ProcessTimeoutSeconds = 60,
            PythonPath = Path.GetTempPath(),
        };
        var service = ServiceHarness.Create(runner, options);
        await service.ArrangeAsync(
            Request(Path.GetTempPath()), new Progress<ArrangementProgress>(_ => { }), CancellationToken.None);

        runner.LastSpec!.Environment["PYTHONPATH"].ShouldBe(Path.GetTempPath());
    }
}
