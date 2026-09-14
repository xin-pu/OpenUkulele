using Microsoft.Extensions.DependencyInjection;
using OpenUkulele.Desktop.ViewModels;

namespace OpenUkulele.Desktop.Views;

/// <summary>Main application window (chrome only; content lives in ArrangeView).</summary>
public partial class MainWindow
{
    /// <summary>Creates the window and binds the root view model.</summary>
    public MainWindow()
    {
        InitializeComponent();
        DataContext = App.Services.GetRequiredService<MainWindowViewModel>();
        ArrangePage.DataContext = App.Services.GetRequiredService<ArrangeViewModel>();
    }
}
