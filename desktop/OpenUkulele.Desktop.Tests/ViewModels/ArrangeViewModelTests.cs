using System.IO;
using OpenUkulele.Desktop.Models;
using OpenUkulele.Desktop.Services;
using OpenUkulele.Desktop.ViewModels;
using Shouldly;
using Xunit;

namespace OpenUkulele.Desktop.Tests.ViewModels;

internal sealed class StubDialogs : IFileDialogService
{
    public string? PickFile(string filter, string title) => null;

    public string? PickFolder(string title) => null;
}

internal sealed class RecordingLauncher : IFileLauncher
{
    public List<string> Opened { get; } = [];

    public bool TryOpen(string path, string allowedRoot)
    {
        Opened.Add(path);
        return true;
    }

    public bool TryReveal(string path, string allowedRoot) => true;
}

internal sealed class StubArrangementService(Func<ArrangementRequest, CancellationToken, Task<ArrangementJobResult>> behavior) : IArrangementService
{
    public Task<ArrangementJobResult> ArrangeAsync(
        ArrangementRequest request, IProgress<ArrangementProgress> progress, CancellationToken cancellationToken)
        => behavior(request, cancellationToken);
}

internal static class ArrangeVm
{
    public static (ArrangeViewModel Vm, string Input, string OutDir) Create(
        IArrangementService? service = null, IFileLauncher? launcher = null)
    {
        var dir = Path.Combine(Path.GetTempPath(), "ukvm-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(dir);
        var input = Path.Combine(dir, "song.mid");
        File.WriteAllBytes(input, [0x4D, 0x54, 0x68, 0x64]);
        var vm = new ArrangeViewModel(
            service ?? new StubArrangementService((_, _) => Task.FromResult(Done(dir))),
            new StubDialogs(),
            launcher ?? new RecordingLauncher());
        vm.InputPath = input;
        vm.OutputDirectory = dir;
        return (vm, input, dir);
    }

    public static ArrangementJobResult Done(string dir) => new()
    {
        Status = ArrangementStatus.Completed,
        OperationId = "op",
        ExitCode = 0,
        OutputDirectory = dir,
        ReportPath = Path.Combine(dir, "song-report.json"),
        Warnings = [],
        Summaries = new Dictionary<string, DifficultySummary>(),
        Outputs = new Dictionary<string, ArrangementFileSet>(),
    };
}

public class ArrangeViewModelTests : IDisposable
{
    private readonly List<string> _dirs = [];

    [Fact]
    public void Generate_NoInput_CannotExecute()
    {
        var vm = new ArrangeViewModel(
            new StubArrangementService((_, _) => Task.FromResult(ArrangeVm.Done("."))),
            new StubDialogs(), new RecordingLauncher());
        vm.GenerateCommand.CanExecute(null).ShouldBeFalse();
    }

    [Fact]
    public void Generate_ValidInputs_CanExecute()
    {
        var (vm, _, dir) = ArrangeVm.Create();
        _dirs.Add(dir);
        vm.GenerateCommand.CanExecute(null).ShouldBeTrue();
    }

    [Fact]
    public void Generate_BadTempo_CannotExecute()
    {
        var (vm, _, dir) = ArrangeVm.Create();
        _dirs.Add(dir);
        vm.TempoText = "999";
        vm.GenerateCommand.CanExecute(null).ShouldBeFalse();
    }

    [Fact]
    public async Task RunningJob_SetsIsRunningAndEnablesCancel()
    {
        var dir = Path.Combine(Path.GetTempPath(), "ukvm-" + Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(dir);
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var (vm, _, _) = ArrangeVm.Create(new StubArrangementService(async (_, ct) =>
        {
            await gate.Task.WaitAsync(ct);
            return ArrangeVm.Done(dir);
        }));
        _dirs.Add(dir);

        var job = vm.GenerateCommand.ExecuteAsync(null);
        vm.IsRunning.ShouldBeTrue();
        vm.CancelCommand.CanExecute(null).ShouldBeTrue();
        vm.GenerateCommand.CanExecute(null).ShouldBeFalse();

        gate.SetResult();
        await job;
        vm.IsRunning.ShouldBeFalse();
        vm.CancelCommand.CanExecute(null).ShouldBeFalse();
    }

    [Fact]
    public async Task CancelledJob_SetsCancelledStatus()
    {
        var (vm, _, dir) = ArrangeVm.Create(new StubArrangementService((_, _) => Task.FromResult(new ArrangementJobResult
        {
            Status = ArrangementStatus.Cancelled,
            OperationId = "op",
            Warnings = [],
            Summaries = new Dictionary<string, DifficultySummary>(),
            Outputs = new Dictionary<string, ArrangementFileSet>(),
        })));
        _dirs.Add(dir);

        await vm.GenerateCommand.ExecuteAsync(null);
        vm.HasError.ShouldBeFalse();
        vm.CurrentMessage.ShouldContain("取消");
    }

    [Fact]
    public async Task FailedJob_ShowsErrorWithSuggestion()
    {
        var (vm, _, dir) = ArrangeVm.Create(new StubArrangementService((_, _) => Task.FromResult(new ArrangementJobResult
        {
            Status = ArrangementStatus.Failed,
            OperationId = "op",
            ErrorCode = ArrangementErrorCodes.Input,
            ErrorMessage = "MIDI 文件不存在。",
            Suggestion = "检查输入路径",
            Warnings = [],
            Summaries = new Dictionary<string, DifficultySummary>(),
            Outputs = new Dictionary<string, ArrangementFileSet>(),
        })));
        _dirs.Add(dir);

        await vm.GenerateCommand.ExecuteAsync(null);
        vm.HasError.ShouldBeTrue();
        vm.ErrorDetail.ShouldContain("不存在");
        vm.ErrorSuggestion.ShouldBe("检查输入路径");
    }

    public void Dispose()
    {
        GC.SuppressFinalize(this);
        foreach (var dir in _dirs)
        {
            try
            {
                Directory.Delete(dir, recursive: true);
            }
            catch (IOException)
            {
                // best-effort temp cleanup
            }
        }
    }
}
