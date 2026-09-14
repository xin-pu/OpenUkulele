namespace OpenUkulele.Desktop.Services;

/// <summary>Opens a file or folder in the OS default handler, path-restricted to an allowed root.</summary>
public interface IFileLauncher
{
    /// <summary>
    /// Opens <paramref name="path"/> only if it resolves under <paramref name="allowedRoot"/>.
    /// Returns false (without launching) when the guard rejects the path.
    /// </summary>
    /// <param name="path">File or directory to open.</param>
    /// <param name="allowedRoot">The confirmed output directory.</param>
    /// <returns>Whether a launch was issued.</returns>
    bool TryOpen(string path, string allowedRoot);

    /// <summary>Reveals a file in the OS file manager, guarded the same way as <see cref="TryOpen"/>.</summary>
    /// <param name="path">File to select in Explorer.</param>
    /// <param name="allowedRoot">The confirmed output directory.</param>
    /// <returns>Whether a launch was issued.</returns>
    bool TryReveal(string path, string allowedRoot);
}
