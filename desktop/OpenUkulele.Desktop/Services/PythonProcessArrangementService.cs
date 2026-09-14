using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OpenUkulele.Desktop.Models;

namespace OpenUkulele.Desktop.Services;

/// <summary>
/// Drives <c>python -m uketab arrange … --progress-json</c> as a controlled
/// subprocess and turns its NDJSON stream, stderr, and exit code into a typed
/// <see cref="ArrangementJobResult"/>. Unknown events, malformed JSON, and a
/// missing terminal event fail closed as protocol errors (ADR 0001).
/// </summary>
public sealed class PythonProcessArrangementService : IArrangementService
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = false };

    private readonly IProcessRunner _runner;
    private readonly DesktopOptions _options;
    private readonly ILogger<PythonProcessArrangementService> _logger;

    /// <summary>Creates the service with validated options and a process runner.</summary>
    public PythonProcessArrangementService(
        IProcessRunner runner,
        IOptions<DesktopOptions> options,
        ILogger<PythonProcessArrangementService> logger)
    {
        _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        _options = options?.Value ?? throw new ArgumentNullException(nameof(options));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <inheritdoc />
    public async Task<ArrangementJobResult> ArrangeAsync(
        ArrangementRequest request,
        IProgress<ArrangementProgress> progress,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(progress);

        var operationId = Guid.NewGuid().ToString("n");
        var stopwatch = Stopwatch.StartNew();
        var state = new StreamState();

        Task OnLine(string line)
        {
            state.Handle(line, operationId, progress);
            return Task.CompletedTask;
        }

        if (_logger.IsEnabled(LogLevel.Information))
        {
            _logger.LogInformation(
                "Operation {OperationId} starting stage={Stage} input={Input}",
                operationId, "input", request.InputPath);
        }

        var outcome = await _runner
            .RunAsync(BuildSpec(request, operationId), OnLine, cancellationToken)
            .ConfigureAwait(false);
        stopwatch.Stop();
        if (_logger.IsEnabled(LogLevel.Information))
        {
            _logger.LogInformation(
                "Operation {OperationId} ended end={End} exit={Exit} lines={Lines} elapsed={Elapsed}ms",
                operationId, outcome.End, outcome.ExitCode, outcome.StdoutLines.Count,
                stopwatch.ElapsedMilliseconds);
        }

        var result = BuildResult(operationId, outcome, state, request, stopwatch.Elapsed);
        return result;
    }

    private ProcessSpec BuildSpec(ArrangementRequest request, string operationId)
    {
        var args = new List<string>
        {
            "-m", _options.Module, "arrange", request.InputPath,
            "--output-dir", request.OutputDirectory,
            "--progress-json", "--operation-id", operationId,
        };
        if (request.TempoBpm is int tempo)
        {
            args.Add("--tempo");
            args.Add(tempo.ToString(CultureInfo.InvariantCulture));
        }

        if (request.ExportPng)
        {
            args.Add("--png");
        }

        if (request.ExportPdf)
        {
            args.Add("--pdf");
        }

        args.Add("--orientation");
        args.Add(request.Portrait ? "portrait" : "landscape");

        if (!string.IsNullOrEmpty(request.Watermark))
        {
            args.Add("--watermark");
            args.Add(request.Watermark);
        }

        if (!string.IsNullOrEmpty(request.LyricsPath))
        {
            args.Add("--lyrics");
            args.Add(request.LyricsPath);
        }

        var workingDir = Path.GetDirectoryName(_options.ResolvedPythonPath) ?? AppContext.BaseDirectory;
        var environment = new Dictionary<string, string>
        {
            ["PYTHONIOENCODING"] = "utf-8",
            ["PYTHONUNBUFFERED"] = "1",
        };
        if (!string.IsNullOrWhiteSpace(_options.ResolvedPythonSearchPath))
        {
            environment["PYTHONPATH"] = _options.ResolvedPythonSearchPath;
        }

        return new ProcessSpec(
            _options.ResolvedPythonPath, args, workingDir, environment,
            TimeSpan.FromSeconds(_options.ProcessTimeoutSeconds));
    }

    private ArrangementJobResult BuildResult(
        string operationId,
        ProcessOutcome outcome,
        StreamState state,
        ArrangementRequest request,
        TimeSpan elapsed)
    {
        if (outcome.End == ProcessEndReason.Cancelled)
        {
            return Terminal(operationId, elapsed, ArrangementStatus.Cancelled,
                error: (ArrangementErrorCodes.Cancelled, "生成已取消。", string.Empty));
        }

        if (outcome.End == ProcessEndReason.TimedOut)
        {
            return Terminal(operationId, elapsed, ArrangementStatus.TimedOut,
                error: (ArrangementErrorCodes.Timeout,
                    $"生成超过 {_options.ProcessTimeoutSeconds} 秒，进程树已强制终止。",
                    "换更短片段或 MIDI 输入，或调大超时设置。"));
        }

        if (state.ProtocolError is { } protocolError)
        {
            return Terminal(operationId, elapsed, ArrangementStatus.Failed,
                exitCode: outcome.ExitCode,
                error: (ArrangementErrorCodes.Protocol, protocolError, "子进程协议不匹配，请确认 uketab 版本与桌面端一致。"));
        }

        var terminal = state.Terminal;
        if (terminal is null)
        {
            var code = outcome.ExitCode == 2 ? ArrangementErrorCodes.Usage : ArrangementErrorCodes.Protocol;
            var message = outcome.ExitCode == 2
                ? "参数错误：uketab 未产出任何进度事件。"
                : "子进程结束但未上报终结事件。";
            return Terminal(operationId, elapsed, ArrangementStatus.Failed,
                exitCode: outcome.ExitCode,
                error: (code, message, TruncateStderr(outcome.StdErr)));
        }

        var exitCode = terminal.ExitCode ?? outcome.ExitCode;
        var partial = terminal.Code == ArrangementErrorCodes.ArrangementPartial;
        var status = terminal.Event == "completed"
            ? ArrangementStatus.Completed
            : partial ? ArrangementStatus.Partial : ArrangementStatus.Failed;
        (string Code, string Message, string Suggestion)? error = null;
        if (terminal.Event != "completed")
        {
            error = (terminal.Code ?? "exit", terminal.Message ?? "生成失败。", terminal.Suggestion ?? string.Empty);
        }

        var result = Terminal(
            operationId, elapsed, status, exitCode, error,
            outputDirectory: terminal.OutputDirectory, reportPath: terminal.ReportPath);

        var report = ReadReport(result.ReportPath, operationId);
        Dictionary<string, ArrangementFileSet> outputs = new();
        if (result.OutputDirectory is { } dir && Directory.Exists(dir))
        {
            outputs = DiscoverOutputs(dir, request.InputPath);
        }

        return new ArrangementJobResult
        {
            Status = result.Status,
            OperationId = result.OperationId,
            ExitCode = result.ExitCode,
            ErrorCode = result.ErrorCode,
            ErrorMessage = result.ErrorMessage,
            Suggestion = result.Suggestion,
            OutputDirectory = result.OutputDirectory,
            ReportPath = result.ReportPath,
            Warnings = report.Warnings,
            Summaries = report.Summaries,
            Outputs = outputs,
            Elapsed = result.Elapsed,
        };
    }

    private static ArrangementJobResult Terminal(
        string operationId,
        TimeSpan elapsed,
        ArrangementStatus status,
        int? exitCode = null,
        (string Code, string Message, string Suggestion)? error = null,
        string? outputDirectory = null,
        string? reportPath = null)
        => new()
        {
            Status = status,
            OperationId = operationId,
            ExitCode = exitCode,
            ErrorCode = error?.Code,
            ErrorMessage = error?.Message,
            Suggestion = error?.Suggestion,
            OutputDirectory = outputDirectory,
            ReportPath = reportPath,
            Warnings = [],
            Summaries = new Dictionary<string, DifficultySummary>(),
            Outputs = new Dictionary<string, ArrangementFileSet>(),
            Elapsed = elapsed,
        };

    private (IReadOnlyList<string> Warnings, IReadOnlyDictionary<string, DifficultySummary> Summaries)
        ReadReport(string? reportPath, string operationId)
    {
        var warnings = new List<string>();
        var summaries = new Dictionary<string, DifficultySummary>();
        if (reportPath is null || !File.Exists(reportPath))
        {
            return (warnings, summaries);
        }

        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(reportPath));
            var root = doc.RootElement;
            if (root.TryGetProperty("warnings", out var array) && array.ValueKind == JsonValueKind.Array)
            {
                warnings.AddRange(array.EnumerateArray().Select(w => w.GetString()).Where(t => t is not null)!);
            }

            if (root.TryGetProperty("arrangements", out var arrangements)
                && arrangements.ValueKind == JsonValueKind.Object)
            {
                foreach (var property in arrangements.EnumerateObject())
                {
                    var summary = ParseSummary(property.Value);
                    if (summary is not null)
                    {
                        summaries[property.Name] = summary;
                    }
                }
            }
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning(
                ex, "Operation {OperationId} stage={Stage} report unreadable path={Report}",
                operationId, "export", reportPath);
        }

        return (warnings, summaries);
    }

    private static DifficultySummary? ParseSummary(JsonElement element)
    {
        try
        {
            var validation = element.TryGetProperty("validation", out var v) && v.ValueKind == JsonValueKind.Object
                ? v
                : default;
            return new DifficultySummary(
                Notes: GetInt(element, "notes"),
                Bars: GetInt(element, "bars"),
                Passed: element.TryGetProperty("passed", out var p) && p.ValueKind == JsonValueKind.True,
                ShiftCount: GetInt(validation, "shift_count"),
                MaxSpan: GetInt(validation, "max_span"),
                BarreCount: GetInt(validation, "barre_count"),
                DifficultyScore: GetDouble(validation, "difficulty_score"),
                IssueCount: GetArrayLength(validation, "issues"));
        }
        catch (InvalidOperationException)
        {
            return null; // shape mismatch: UI falls back to "no summary"
        }
    }

    private static int GetInt(JsonElement element, string name)
        => element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value)
            && value.TryGetInt32(out var number) ? number : 0;

    private static int GetArrayLength(JsonElement element, string name)
        => element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value)
            && value.ValueKind == JsonValueKind.Array ? value.GetArrayLength() : 0;

    private static double GetDouble(JsonElement element, string name)
        => element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value)
            && value.TryGetDouble(out var number) ? number : 0d;

    private static Dictionary<string, ArrangementFileSet> DiscoverOutputs(
        string directory, string inputPath)
    {
        var stem = Path.GetFileNameWithoutExtension(inputPath);
        var outputs = new Dictionary<string, ArrangementFileSet>();
        foreach (var difficulty in new[] { "easy", "hard" })
        {
            var pages = Directory
                .GetFiles(directory, $"{stem}-{difficulty}-p*.png")
                .OrderBy(f => f, StringComparer.Ordinal)
                .ToList();
            var single = Find(Path.Combine(directory, $"{stem}-{difficulty}.png"));
            var pngPages = pages.Count > 0
                ? pages
                : single is not null ? new List<string> { single } : new List<string>();
            var set = new ArrangementFileSet(
                Txt: Find(Path.Combine(directory, $"{stem}-{difficulty}.txt")),
                Gp5: Find(Path.Combine(directory, $"{stem}-{difficulty}.gp5")),
                Png: single ?? pages.FirstOrDefault(),
                Pdf: Find(Path.Combine(directory, $"{stem}-{difficulty}.pdf")),
                PngPages: pngPages);
            if (set.Txt is not null || set.Gp5 is not null || set.Png is not null || set.Pdf is not null)
            {
                outputs[difficulty] = set;
            }
        }

        return outputs;

        static string? Find(string path) => File.Exists(path) ? path : null;
    }

    private static string TruncateStderr(string stderr)
        => string.IsNullOrEmpty(stderr)
            ? string.Empty
            : stderr.Length > 800 ? stderr[..800] + "…" : stderr;

    /// <summary>Mutable NDJSON accumulator isolated from concurrent stream callbacks.</summary>
    private sealed class StreamState
    {
        private readonly Lock _gate = new();

        public ProtocolEvent? Terminal { get; private set; }

        public string? ProtocolError { get; private set; }

        private int LastPercent;

        public void Handle(string line, string operationId, IProgress<ArrangementProgress> progress)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                return;
            }

            ProtocolEvent? evt;
            lock (_gate)
            {
                try
                {
                    evt = JsonSerializer.Deserialize<ProtocolEvent>(line, JsonOptions);
                }
                catch (JsonException)
                {
                    ProtocolError ??= $"无法解析进度事件：{Truncate(line)}";
                    return;
                }

                switch (evt?.Event)
                {
                    case "progress":
                        ReportProgress(evt, operationId, progress);
                        return;
                    case "completed":
                    case "failed":
                        Terminal = evt;
                        return;
                    case "started":
                        return;
                    case null:
                        ProtocolError ??= "进度事件缺少 event 字段";
                        return;
                    default:
                        ProtocolError ??= $"未知事件类型 {evt.Event}";
                        return;
                }
            }
        }

        private void ReportProgress(ProtocolEvent evt, string operationId, IProgress<ArrangementProgress> progress)
        {
            if (!ArrangementStageParser.TryParse(evt.Stage, out var stage))
            {
                ProtocolError ??= $"未知进度阶段 {evt.Stage}";
                return;
            }

            LastPercent = Math.Max(LastPercent, evt.Percent ?? LastPercent);
            progress.Report(new ArrangementProgress(
                evt.OperationId ?? operationId, stage, LastPercent, evt.Message ?? string.Empty));
        }

        private static string Truncate(string line) => line.Length > 120 ? line[..120] + "…" : line;
    }
}
