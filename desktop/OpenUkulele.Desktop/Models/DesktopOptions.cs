using System.ComponentModel.DataAnnotations;
using System.IO;

namespace OpenUkulele.Desktop.Models;

/// <summary>Bound from the "UkeTab" section of appsettings.json and validated at startup.</summary>
public sealed class DesktopOptions : IValidatableObject
{
    /// <summary>Configuration section name.</summary>
    public const string SectionName = "UkeTab";

    /// <summary>Path to python.exe (dev) — resolved relative to the app base directory.</summary>
    [Required]
    public string PythonExecutable { get; set; } = string.Empty;

    /// <summary>Python module invoked as <c>python -m &lt;Module&gt;</c> (or exe subcommand).</summary>
    [Required]
    public string Module { get; set; } = "uketab";

    /// <summary>Kill the process tree beyond this many seconds (design §4.2: 30–900).</summary>
    [Range(30, 900)]
    public int ProcessTimeoutSeconds { get; set; } = 300;

    /// <summary>
    /// Optional directory prepended to the child's PYTHONPATH — for dev setups
    /// where uketab is not installed into the venv (e.g. the repo "src" folder).
    /// </summary>
    public string PythonPath { get; set; } = string.Empty;

    /// <summary>Resolved <see cref="PythonPath"/>; empty when unset.</summary>
    public string ResolvedPythonSearchPath =>
        string.IsNullOrWhiteSpace(PythonPath)
            ? string.Empty
            : Path.IsPathRooted(PythonPath)
                ? PythonPath
                : Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, PythonPath));

    /// <summary>Validate all invariants (DataAnnotations plus file/path checks).</summary>
    /// <returns>Validation failures; empty when everything is usable.</returns>
    public IEnumerable<ValidationResult> Validate()
    {
        var context = new ValidationContext(this);
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(this, context, results, validateAllProperties: true);
        return results;
    }

    /// <summary>Cross-field checks invoked by the DataAnnotations framework.</summary>
    IEnumerable<ValidationResult> IValidatableObject.Validate(ValidationContext validationContext)
    {
        var looksLikePath = Path.IsPathRooted(PythonExecutable)
            || PythonExecutable.Contains(Path.DirectorySeparatorChar);
        if (looksLikePath && !File.Exists(ResolvedPythonPath))
        {
            yield return new ValidationResult(
                $"Python 可执行文件不存在：{ResolvedPythonPath}",
                [nameof(PythonExecutable)]);
        }

        if (string.IsNullOrWhiteSpace(Module))
        {
            yield return new ValidationResult("Module 不能为空", [nameof(Module)]);
        }
    }

    /// <summary>
    /// Absolute python path; relative values with separators resolve beside the
    /// app, bare command names (e.g. "python") are used as-is for PATH lookup.
    /// </summary>
    public string ResolvedPythonPath =>
        Path.IsPathRooted(PythonExecutable) || PythonExecutable.Contains(Path.DirectorySeparatorChar)
            ? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, PythonExecutable))
            : PythonExecutable;
}
