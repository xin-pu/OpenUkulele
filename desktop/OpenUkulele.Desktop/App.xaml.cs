using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Windows;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OpenUkulele.Desktop.Models;
using OpenUkulele.Desktop.Services;
using OpenUkulele.Desktop.ViewModels;
using OpenUkulele.Desktop.Views;

namespace OpenUkulele.Desktop;

/// <summary>Composition root: builds the DI container and validates configuration at startup.</summary>
public partial class App : System.Windows.Application
{
    private ServiceProvider? _services;

    /// <summary>Root provider, available after <see cref="OnStartup"/> to view code-behind.</summary>
    public static IServiceProvider Services { get; private set; } = null!;

    /// <inheritdoc />
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var configPath = Path.Combine(AppContext.BaseDirectory, "appsettings.json");
        var configuration = new ConfigurationBuilder()
            .AddJsonFile(configPath, optional: !File.Exists(configPath), reloadOnChange: false)
            .Build();

        var options = new DesktopOptions();
        configuration.GetSection(DesktopOptions.SectionName).Bind(options);

        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(configuration);
        services.AddSingleton<IOptions<DesktopOptions>>(Microsoft.Extensions.Options.Options.Create(options));
        services.AddLogging(builder => builder.AddDebug());

        services.AddSingleton<IProcessRunner, ProcessRunner>();
        services.AddSingleton<IArrangementService, PythonProcessArrangementService>();
        services.AddSingleton<IFileDialogService, FileDialogService>();
        services.AddSingleton<IFileLauncher, FileLauncher>();

        services.AddSingleton<MainWindowViewModel>();
        services.AddSingleton<ArrangeViewModel>();
        services.AddSingleton<MainWindow>();

        _services = services.BuildServiceProvider();
        Services = _services;

        // Fail fast with an actionable message on invalid configuration (design §7).
        var failures = new List<ValidationResult>();
        if (!Validator.TryValidateObject(options, new ValidationContext(options), failures, true))
        {
            MessageBox.Show(
                "配置无效，无法生成谱面：\n" +
                string.Join("\n", failures.Select(f => f.ErrorMessage)) +
                $"\n\n请修正 {configPath}",
                "OpenUkulele 配置错误",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
        }

        MainWindow = new MainWindow();
        MainWindow.Show();
    }

    /// <inheritdoc />
    protected override void OnExit(ExitEventArgs e)
    {
        _services?.Dispose();
        base.OnExit(e);
    }
}
