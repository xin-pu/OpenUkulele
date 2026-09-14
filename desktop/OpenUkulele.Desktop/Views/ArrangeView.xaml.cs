using System.Windows.Controls;

namespace OpenUkulele.Desktop.Views;

/// <summary>Arrange page; DataContext (ArrangeViewModel) is injected by MainWindow.</summary>
public partial class ArrangeView : UserControl
{
    /// <summary>Initializes the component. No logic lives in view code-behind (design §6).</summary>
    public ArrangeView()
    {
        InitializeComponent();
    }
}
