using System.Collections.ObjectModel;
using System.Globalization;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using OpenUkulele.Desktop.Models;
using OpenUkulele.Desktop.Services;

namespace OpenUkulele.Desktop.ViewModels;

/// <summary>
/// State and commands for the arrange page. Performs local input validation,
/// drives one cancellable job, and exposes progress, result, and error state.
/// Talks only to injected services (no Process/dialogs/files directly).
/// </summary>
public sealed partial class ArrangeViewModel : ObservableObject, IDisposable
{
    private static readonly string[] InputExtensions = [".mid", ".midi", ".wav", ".mp3", ".m4a", ".ogg"];
    private static readonly string[] LyricsExtensions = [".lrc", ".txt"];

    private readonly IArrangementService _arrangement;
    private readonly IFileDialogService _dialogs;
    private readonly IFileLauncher _launcher;
    private CancellationTokenSource? _cts;
    private ArrangementJobResult? _lastResult;

    /// <summary>Creates the page model.</summary>
    public ArrangeViewModel(
        IArrangementService arrangement,
        IFileDialogService dialogs,
        IFileLauncher launcher)
    {
        _arrangement = arrangement;
        _dialogs = dialogs;
        _launcher = launcher;
    }

    // ---- inputs -----------------------------------------------------------

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(GenerateCommand))]
    private string? inputPath;

    [ObservableProperty]
    private string? lyricsPath;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(GenerateCommand))]
    private string? outputDirectory;

    [ObservableProperty]
    private string tempoText = string.Empty;

    [ObservableProperty]
    private bool exportPng = true;

    [ObservableProperty]
    private bool exportPdf;

    [ObservableProperty]
    private bool portrait;

    [ObservableProperty]
    private string watermarkText = string.Empty;

    [ObservableProperty]
    private string inputHint = "支持 .mid/.midi/.wav/.mp3/.m4a/.ogg";

    // ---- runtime state ----------------------------------------------------

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(GenerateCommand))]
    [NotifyCanExecuteChangedFor(nameof(CancelCommand))]
    private bool isRunning;

    [ObservableProperty]
    private int percent;

    [ObservableProperty]
    private string stageText = string.Empty;

    [ObservableProperty]
    private string currentMessage = string.Empty;

    [ObservableProperty]
    private bool hasError;

    [ObservableProperty]
    private string errorTitle = string.Empty;

    [ObservableProperty]
    private string errorDetail = string.Empty;

    [ObservableProperty]
    private string errorSuggestion = string.Empty;

    /// <summary>Warnings extracted from the latest report.</summary>
    public ObservableCollection<string> Warnings { get; } = [];

    /// <summary>Easy-tab result pane.</summary>
    public DifficultyViewModel Easy { get; } = new("简易版");

    /// <summary>Hard-tab result pane.</summary>
    public DifficultyViewModel Hard { get; } = new("困难版");

    /// <summary>Whether the result tabs should show.</summary>
    public bool HasResult { get; private set; }

    private bool CanGenerate()
        => !IsRunning && HasValidInput(out _);

    private bool HasValidInput(out string? problem)
    {
        problem = null;
        if (string.IsNullOrWhiteSpace(InputPath) || !File.Exists(InputPath))
        {
            problem = "请先选择存在的输入文件。";
            return false;
        }

        if (!InputExtensions.Contains(Path.GetExtension(InputPath).ToLowerInvariant()))
        {
            problem = "不支持的输入格式。";
            return false;
        }

        if (string.IsNullOrWhiteSpace(OutputDirectory))
        {
            problem = "请选择输出文件夹。";
            return false;
        }

        if (!string.IsNullOrEmpty(LyricsPath)
            && !LyricsExtensions.Contains(Path.GetExtension(LyricsPath).ToLowerInvariant()))
        {
            problem = "歌词文件仅支持 .lrc/.txt。";
            return false;
        }

        if (!TryParseTempo(out problem))
        {
            return false;
        }

        return true;
    }

    private bool TryParseTempo(out string? problem)
    {
        problem = null;
        if (string.IsNullOrWhiteSpace(TempoText))
        {
            return true;
        }

        if (!int.TryParse(TempoText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var tempo)
            || tempo is < 40 or > 240)
        {
            problem = "Tempo 必须是 40–240 的整数。";
            return false;
        }

        return true;
    }

    partial void OnInputPathChanged(string? value)
    {
        InputHint = value is null
            ? "支持 .mid/.midi/.wav/.mp3/.m4a/.ogg"
            : Path.GetExtension(value).ToLowerInvariant() is { Length: > 1 } ext && InputExtensions.Contains(ext)
                ? $"扩展名 {ext} 已识别"
                : $"扩展名 {Path.GetExtension(value)} 不受支持";
    }

    // ---- commands ---------------------------------------------------------

    /// <summary>Pick the MIDI/audio input.</summary>
    [RelayCommand]
    private void PickInput()
    {
        var chosen = _dialogs.PickFile(
            "MIDI (*.mid;*.midi)|*.mid;*.midi|音频 (*.mp3;*.wav;*.m4a;*.ogg)|*.mp3;*.wav;*.m4a;*.ogg|所有文件 (*.*)|*.*",
            "选择 MIDI 或音频文件");
        if (chosen is not null)
        {
            InputPath = chosen;
        }
    }

    /// <summary>Pick an optional lyrics file.</summary>
    [RelayCommand]
    private void PickLyrics()
    {
        var chosen = _dialogs.PickFile("歌词 (*.lrc;*.txt)|*.lrc;*.txt", "选择歌词文件（可选）");
        if (chosen is not null)
        {
            LyricsPath = chosen;
        }
    }

    /// <summary>Pick the output directory.</summary>
    [RelayCommand]
    private void PickOutput()
    {
        var chosen = _dialogs.PickFolder("选择输出文件夹");
        if (chosen is not null)
        {
            OutputDirectory = chosen;
        }
    }

    /// <summary>Run one generation job.</summary>
    [RelayCommand(CanExecute = nameof(CanGenerate))]
    private async Task GenerateAsync()
    {
        if (!HasValidInput(out var problem))
        {
            ShowError("输入不完整", problem ?? string.Empty, string.Empty);
            return;
        }

        TryParseTempo(out _);
        ClearError();
        HasResult = false;
        IsRunning = true;
        Percent = 0;
        StageText = "input";
        CurrentMessage = "开始生成…";
        Warnings.Clear();
        Easy.Clear();
        Hard.Clear();

        _cts = new CancellationTokenSource();
        var progress = new Progress<ArrangementProgress>(ApplyProgress);
        var request = new ArrangementRequest(
            InputPath!, OutputDirectory!, LyricsPath,
            int.TryParse(TempoText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var t) ? t : null,
            ExportPng, ExportPdf, Portrait,
            string.IsNullOrWhiteSpace(WatermarkText) ? null : WatermarkText);

        try
        {
            var result = await _arrangement.ArrangeAsync(request, progress, _cts.Token);
            _lastResult = result;
            ApplyResult(result);
        }
        catch (Exception ex)
        {
            ShowError("未预期的错误", ex.Message, string.Empty);
        }
        finally
        {
            _cts.Dispose();
            _cts = null;
            IsRunning = false;
        }
    }

    /// <summary>Cancel the running job (kills the process tree in the service).</summary>
    [RelayCommand(CanExecute = nameof(IsRunning))]
    private void Cancel()
    {
        _cts?.Cancel();
    }

    private void ApplyProgress(ArrangementProgress p)
    {
        Percent = p.Percent;
        StageText = p.Stage.ToString().ToLowerInvariant();
        CurrentMessage = p.Message;
    }

    private void ApplyResult(ArrangementJobResult result)
    {
        switch (result.Status)
        {
            case ArrangementStatus.Completed:
            case ArrangementStatus.Partial:
                HasResult = true;
                Easy.Apply(result, "easy");
                Hard.Apply(result, "hard");
                foreach (var w in result.Warnings)
                {
                    Warnings.Add(w);
                }

                if (result.Status == ArrangementStatus.Partial)
                {
                    ShowError("部分成功", result.ErrorMessage ?? "有一个版本无法生成。", result.Suggestion ?? string.Empty);
                }

                break;
            case ArrangementStatus.Cancelled:
                CurrentMessage = "已取消。";
                break;
            default:
                ShowError(
                    result.ErrorCode ?? "error",
                    result.ErrorMessage ?? "生成失败。",
                    result.Suggestion ?? string.Empty);
                break;
        }

        OnPropertyChanged(nameof(HasResult));
    }

    private void ShowError(string title, string detail, string suggestion)
    {
        ErrorTitle = title;
        ErrorDetail = detail;
        ErrorSuggestion = suggestion;
        HasError = true;
    }

    private void ClearError() => HasError = false;

    /// <summary>Open a produced file in the OS default handler (output-dir guarded).</summary>
    [RelayCommand]
    private void OpenFile(string? path)
    {
        if (path is null || _lastResult?.OutputDirectory is not { } root)
        {
            return;
        }

        _launcher.TryOpen(path, root);
    }

    /// <summary>Reveal a produced file in Explorer.</summary>
    [RelayCommand]
    private void RevealFile(string? path)
    {
        if (path is null || _lastResult?.OutputDirectory is not { } root)
        {
            return;
        }

        _launcher.TryReveal(path, root);
    }

    /// <summary>Open the output folder.</summary>
    [RelayCommand]
    private void OpenOutputFolder()
    {
        if (_lastResult?.OutputDirectory is { } root)
        {
            _launcher.TryOpen(root, root);
        }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _cts = null;
    }
}

/// <summary>Per-difficulty result pane state (preview image, summary, files).</summary>
public sealed partial class DifficultyViewModel : ObservableObject
{
    /// <summary>Creates the pane with its display label.</summary>
    public DifficultyViewModel(string label)
    {
        Label = label;
    }

    /// <summary>Chinese pane label.</summary>
    public string Label { get; }

    /// <summary>First PNG page path for preview (null → no image).</summary>
    [ObservableProperty]
    private string? previewPath;

    /// <summary>Summary line (换把/跨度/横按/难度分).</summary>
    [ObservableProperty]
    private string summaryText = "未生成";

    /// <summary>Whether any file exists for this difficulty.</summary>
    public bool HasOutput { get; private set; }

    /// <summary>Paths for the result action buttons.</summary>
    public string? TxtPath { get; private set; }

    /// <summary>See <see cref="TxtPath"/>.</summary>
    public string? Gp5Path { get; private set; }

    /// <summary>See <see cref="TxtPath"/>.</summary>
    public string? PdfPath { get; private set; }

    /// <summary>Whether a preview image is available.</summary>
    public bool HasPreview => PreviewPath is not null;

    /// <summary>Load result data for this difficulty key.</summary>
    public void Apply(ArrangementJobResult result, string key)
    {
        if (result.Outputs.TryGetValue(key, out var files))
        {
            TxtPath = files.Txt;
            Gp5Path = files.Gp5;
            PdfPath = files.Pdf;
            PreviewPath = files.Png;
            HasOutput = true;
            SummaryText = result.Summaries.TryGetValue(key, out var s)
                ? $"{s.Notes} 音符 · {s.Bars} 小节 · 换把 {s.ShiftCount} · 跨度 {s.MaxSpan} · 横按 {s.BarreCount} · 难度 {s.DifficultyScore:F2}"
                : "已生成";
        }
        else
        {
            Clear();
        }

        OnPropertyChanged(nameof(HasOutput));
        OnPropertyChanged(nameof(HasPreview));
    }

    /// <summary>Reset the pane.</summary>
    public void Clear()
    {
        TxtPath = Gp5Path = PdfPath = null;
        PreviewPath = null;
        HasOutput = false;
        SummaryText = "未生成";
        OnPropertyChanged(nameof(HasOutput));
        OnPropertyChanged(nameof(HasPreview));
    }
}
