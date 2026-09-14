using CommunityToolkit.Mvvm.ComponentModel;

namespace OpenUkulele.Desktop.ViewModels;

/// <summary>Window-level state: title and navigation root.</summary>
public sealed partial class MainWindowViewModel : ObservableObject
{
    /// <summary>App title shown in the title bar.</summary>
    public string Title { get; } = "OpenUkulele";
}
