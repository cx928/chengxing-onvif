using CXOnvif.Desktop.Models;
using CXOnvif.Desktop.Services;
using Microsoft.UI.Xaml;

namespace CXOnvif.Desktop;

/// <summary>
/// 程星 ONVIF 桌面控制台。应用级单例：设置、API 客户端、引擎进程管理器。
/// </summary>
public partial class App : Application
{
    public static AppSettings Settings { get; private set; } = new();

    public static ApiClient Api { get; private set; } = null!;

    public static EngineProcessManager Engine { get; private set; } = null!;

    private Window? _window;

    public App()
    {
        // 固定深色主题，保证卡片/文字配色一致
        RequestedTheme = ApplicationTheme.Dark;
        InitializeComponent();

        Settings = AppSettings.Load();
        Api = new ApiClient(Settings.EngineUrl);
        Engine = new EngineProcessManager(Settings);
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _window = new MainWindow();
        _window.Activate();
    }
}
