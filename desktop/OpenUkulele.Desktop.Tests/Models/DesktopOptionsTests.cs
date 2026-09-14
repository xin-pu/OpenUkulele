using System.ComponentModel.DataAnnotations;
using System.IO;
using OpenUkulele.Desktop.Models;
using Shouldly;
using Xunit;

namespace OpenUkulele.Desktop.Tests.Models;

public class DesktopOptionsTests
{
    private static List<ValidationResult> Validate(DesktopOptions options) => [.. options.Validate()];

    [Fact]
    public void Validate_TimeoutBelowRange_IsInvalid()
    {
        var options = new DesktopOptions
        {
            PythonExecutable = Environment.ProcessPath ?? "python",
            Module = "uketab",
            ProcessTimeoutSeconds = 10,
        };
        var errors = Validate(options);
        errors.ShouldContain(r => r.MemberNames.Contains(nameof(DesktopOptions.ProcessTimeoutSeconds)));
    }

    [Fact]
    public void Validate_TimeoutAboveRange_IsInvalid()
    {
        var options = new DesktopOptions
        {
            PythonExecutable = Environment.ProcessPath ?? "python",
            Module = "uketab",
            ProcessTimeoutSeconds = 5000,
        };
        Validate(options).ShouldContain(r => r.MemberNames.Contains(nameof(DesktopOptions.ProcessTimeoutSeconds)));
    }

    [Fact]
    public void Validate_MissingExecutablePath_IsInvalid()
    {
        var options = new DesktopOptions
        {
            PythonExecutable = Path.Combine(Path.GetTempPath(), "nope", "python.exe"),
            Module = "uketab",
            ProcessTimeoutSeconds = 300,
        };
        Validate(options).ShouldContain(r => r.MemberNames.Contains(nameof(DesktopOptions.PythonExecutable)));
    }

    [Fact]
    public void Validate_AllValid_HasNoErrors()
    {
        var options = new DesktopOptions
        {
            PythonExecutable = Environment.ProcessPath ?? "python",
            Module = "uketab",
            ProcessTimeoutSeconds = 300,
        };
        Validate(options).ShouldBeEmpty();
    }

    [Fact]
    public void ResolvedPythonPath_BareCommand_IsUsedAsIs()
    {
        var options = new DesktopOptions { PythonExecutable = "python", Module = "uketab" };
        options.ResolvedPythonPath.ShouldBe("python");
    }
}
