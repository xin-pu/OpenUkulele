namespace OpenUkulele.Desktop.Services;

/// <summary>File and folder picking boundary so ViewModels avoid WPF dialogs (design §6).</summary>
public interface IFileDialogService
{
    /// <summary>Picks an input file (MIDI/audio) or a lyrics file.</summary>
    /// <param name="filter">OpenFileDialog filter string.</param>
    /// <param name="title">Dialog title.</param>
    /// <returns>Chosen path or null when cancelled.</returns>
    string? PickFile(string filter, string title);

    /// <summary>Picks an output directory.</summary>
    /// <param name="title">Dialog title.</param>
    /// <returns>Chosen folder or null when cancelled.</returns>
    string? PickFolder(string title);
}
