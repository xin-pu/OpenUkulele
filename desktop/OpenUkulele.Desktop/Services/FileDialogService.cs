using Microsoft.Win32;

namespace OpenUkulele.Desktop.Services;

/// <summary>WPF <see cref="OpenFileDialog"/>/<see cref="OpenFolderDialog"/> implementation.</summary>
public sealed class FileDialogService : IFileDialogService
{
    /// <inheritdoc />
    public string? PickFile(string filter, string title)
    {
        var dialog = new OpenFileDialog
        {
            Filter = filter,
            Title = title,
            CheckFileExists = true,
            Multiselect = false,
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }

    /// <inheritdoc />
    public string? PickFolder(string title)
    {
        var dialog = new OpenFolderDialog { Title = title };
        return dialog.ShowDialog() == true ? dialog.FolderName : null;
    }
}
