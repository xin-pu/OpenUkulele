using System.IO;
using OpenUkulele.Desktop.Services;
using Shouldly;
using Xunit;

namespace OpenUkulele.Desktop.Tests.Services;

public class FileLauncherTests
{
    [Fact]
    public void IsWithin_FileInsideRoot_IsTrue()
    {
        var root = Path.Combine(Path.GetTempPath(), "ukroot");
        var inside = Path.Combine(root, "song-easy.png");
        FileLauncher.IsWithin(inside, root).ShouldBeTrue();
    }

    [Fact]
    public void IsWithin_PathOutsideOutputDirectory_IsFalse()
    {
        var root = Path.Combine(Path.GetTempPath(), "ukroot");
        var outside = Path.Combine(Path.GetTempPath(), "elsewhere", "evil.exe");
        FileLauncher.IsWithin(outside, root).ShouldBeFalse();
    }

    [Fact]
    public void IsWithin_PathTraversalEscape_IsFalse()
    {
        var root = Path.Combine(Path.GetTempPath(), "ukroot", "nested");
        var escape = Path.GetFullPath(Path.Combine(root, "..", "..", "outside.txt"));
        FileLauncher.IsWithin(escape, root).ShouldBeFalse();
    }

    [Fact]
    public void IsWithin_RootItself_IsTrue()
    {
        var root = Path.Combine(Path.GetTempPath(), "ukroot");
        FileLauncher.IsWithin(root, root).ShouldBeTrue();
    }

    [Fact]
    public void TryOpen_PathOutsideOutputDirectory_RejectsLaunch()
    {
        var launcher = new FileLauncher();
        var root = Path.Combine(Path.GetTempPath(), "ukroot-" + Guid.NewGuid().ToString("n"));
        // A path that does not exist and is outside the root must be refused without launching.
        launcher.TryOpen(Path.Combine(Path.GetTempPath(), "definitely-not-inside.exe"), root)
            .ShouldBeFalse();
    }
}
