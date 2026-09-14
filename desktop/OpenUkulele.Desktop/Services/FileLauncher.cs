using System.IO;
using System.Runtime.InteropServices;

namespace OpenUkulele.Desktop.Services;

/// <summary>Shell-execute launcher that refuses any path escaping the allowed root (design §5.3).</summary>
public sealed class FileLauncher : IFileLauncher
{
    /// <inheritdoc />
    public bool TryOpen(string path, string allowedRoot) => Start(path, allowedRoot, arguments: null);

    /// <inheritdoc />
    public bool TryReveal(string path, string allowedRoot)
    {
        if (!IsWithin(path, allowedRoot))
        {
            return false;
        }

        return Start(
            "explorer.exe",
            allowedRoot,
            $"/select,\"{Path.GetFullPath(path)}\"",
            shellExecute: true);
    }

    private static bool Start(
        string path, string allowedRoot, string? arguments, bool shellExecute = false)
    {
        if (!IsWithin(path, allowedRoot))
        {
            return false;
        }

        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = path,
            UseShellExecute = shellExecute || RuntimeInformation.IsOSPlatform(OSPlatform.Windows),
        };
        if (arguments is not null)
        {
            psi.Arguments = arguments;
        }

        try
        {
            using var process = System.Diagnostics.Process.Start(psi);
            return process is not null;
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return false; // no registered handler: UI shows a message instead of crashing
        }
    }

    /// <summary>True when <paramref name="path"/> resolves at or under <paramref name="allowedRoot"/>.</summary>
    internal static bool IsWithin(string path, string allowedRoot)
    {
        if (string.IsNullOrEmpty(allowedRoot))
        {
            return false;
        }

        try
        {
            var full = Path.GetFullPath(path);
            var root = Path.GetFullPath(allowedRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            return full.Equals(root, PathComparison)
                || full.StartsWith(root + Path.DirectorySeparatorChar, PathComparison);
        }
        catch (Exception ex) when (ex is ArgumentException or PathTooLongException or NotSupportedException)
        {
            return false;
        }
    }

    private static StringComparison PathComparison =>
        OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
}
