using System.Text.Json.Serialization;

namespace OpenUkulele.Desktop.Models;

/// <summary>One NDJSON line from <c>uketab --progress-json</c> (design §4.1). All fields optional by event type.</summary>
internal sealed record ProtocolEvent
{
    /// <summary>started | progress | completed | failed.</summary>
    [JsonPropertyName("event")]
    public string? Event { get; init; }

    /// <summary>Correlation id echoed by Python.</summary>
    [JsonPropertyName("operationId")]
    public string? OperationId { get; init; }

    /// <summary>Stage token for progress events.</summary>
    [JsonPropertyName("stage")]
    public string? Stage { get; init; }

    /// <summary>Percent 0–100 for progress events.</summary>
    [JsonPropertyName("percent")]
    public int? Percent { get; init; }

    /// <summary>Human message.</summary>
    [JsonPropertyName("message")]
    public string? Message { get; init; }

    /// <summary>Stable machine code on failed events.</summary>
    [JsonPropertyName("code")]
    public string? Code { get; init; }

    /// <summary>Suggestion on failed events.</summary>
    [JsonPropertyName("suggestion")]
    public string? Suggestion { get; init; }

    /// <summary>Exit code on terminal events.</summary>
    [JsonPropertyName("exitCode")]
    public int? ExitCode { get; init; }

    /// <summary>Output directory on terminal events.</summary>
    [JsonPropertyName("outputDirectory")]
    public string? OutputDirectory { get; init; }

    /// <summary>report.json path on terminal events.</summary>
    [JsonPropertyName("reportPath")]
    public string? ReportPath { get; init; }

    /// <summary>Input path echoed by the started event.</summary>
    [JsonPropertyName("inputPath")]
    public string? InputPath { get; init; }
}
