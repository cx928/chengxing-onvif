using CXOnvif.Desktop.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace CXOnvif.Desktop.Pages;

public sealed partial class AboutPage : Page
{
    private const string BilibiliUrl = "https://space.bilibili.com/1765875510";
    private const string GithubUrl = "https://github.com/cx928";
    private const string EmailAddress = "wanghaotian@cxdx.edu.kg";

    public AboutPage()
    {
        InitializeComponent();
        Loaded += AboutPage_Loaded;
    }

    private async void AboutPage_Loaded(object sender, RoutedEventArgs e)
    {
        EngineUrlText.Text = App.Api.BaseUrl;
        DesktopVersionText.Text = GetDesktopVersion();

        var health = await App.Api.GetHealthAsync();
        if (health is null)
        {
            EngineVersionText.Text = "—";
            EngineStateText.Text = "引擎未运行，无法读取版本信息。";
            return;
        }

        EngineVersionText.Text = string.IsNullOrWhiteSpace(health.Version) ? "—" : health.Version;
        var brand = string.IsNullOrWhiteSpace(health.Brand) ? "程星 ONVIF" : health.Brand;
        EngineStateText.Text = $"{brand} 引擎运行中 · 摄像机 {health.Running} / {health.Cameras} 路运行";
    }

    private static string GetDesktopVersion()
    {
        var version = typeof(App).Assembly.GetName().Version;
        return version is null ? "1.0.0" : $"{version.Major}.{version.Minor}.{version.Build}";
    }

    private void OpenBilibili_Click(object sender, RoutedEventArgs e) => OpenLink(BilibiliUrl);

    private void OpenGithub_Click(object sender, RoutedEventArgs e) => OpenLink(GithubUrl);

    private void OpenEmail_Click(object sender, RoutedEventArgs e) => OpenLink("mailto:" + EmailAddress);

    private static void OpenLink(string target) => ShellLauncher.Open(target);
}
