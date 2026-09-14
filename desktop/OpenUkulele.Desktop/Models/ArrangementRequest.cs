namespace OpenUkulele.Desktop.Models;

/// <summary>Immutable request describing one arrangement job.</summary>
/// <param name="InputPath">MIDI or audio file to convert.</param>
/// <param name="OutputDirectory">Target directory (must not exist or be empty).</param>
/// <param name="LyricsPath">Optional LRC/TXT lyrics file.</param>
/// <param name="TempoBpm">Optional tempo override, 40–240.</param>
/// <param name="ExportPng">Export A4 PNG sheets.</param>
/// <param name="ExportPdf">Export A4 PDF.</param>
/// <param name="Portrait">Use portrait A4 instead of landscape.</param>
/// <param name="Watermark">Optional watermark text; null/empty means none.</param>
public sealed record ArrangementRequest(
    string InputPath,
    string OutputDirectory,
    string? LyricsPath = null,
    int? TempoBpm = null,
    bool ExportPng = true,
    bool ExportPdf = false,
    bool Portrait = false,
    string? Watermark = null);
