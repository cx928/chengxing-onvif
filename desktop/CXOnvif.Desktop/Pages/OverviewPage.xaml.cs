using CXOnvif.Desktop.Models;
using CXOnvif.Desktop.Services;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace CXOnvif.Desktop.Pages;

public sealed partial class OverviewPage : Page
{
    private DispatcherQueueTimer? _timer;
    private HealthInfo? _health;
    private bool _polling;
    private bool _busy;

    public OverviewPage()
    {
        InitializeComponent();
        Loaded += OverviewPage_Loaded;
        Unloaded += OverviewPage_Unloaded;
    }

    private async void OverviewPage_Loaded(object sender, RoutedEventArgs e)
    {
        LoadSettingsIntoUi();
        StartTimer();
        await RefreshHealthAsync();
    }

    private void OverviewPage_Unloaded(object sender, RoutedEventArgs e)
    {
        _timer?.Stop();
        _timer = null;
    }

    private void StartTimer()
    {
        if (_timer is not null)
        {
            return;
        }

        _timer = DispatcherQueue.CreateTimer();
        _timer.Interval = TimeSpan.FromSeconds(3);
        _timer.IsRepeating = true;
        _timer.Tick += async (timer, args) => await RefreshHealthAsync();
        _timer.Start();
    }

    // ------------------------------------------------------------------ 状态刷新

    private async Task RefreshHealthAsync()
    {
        if (_polling)
        {
            return;
        }

        _polling = true;
        try
        {
            var health = await App.Api.GetHealthAsync();
            ApplyHealth(health);
        }
        finally
        {
            _polling = false;
        }
    }

    private void ApplyHealth(HealthInfo? health)
    {
        _health = health;
        var running = health is not null;

        StatusText.Text = running ? "运行中" : "未运行";
        StatusHintText.Text = running
            ? $"{App.Api.BaseUrl} · 已连接"
            : $"{App.Api.BaseUrl} · 无法连接";

        StatusDot.Fill = Solid(running ? (byte)63 : (byte)248, running ? (byte)185 : (byte)81, running ? (byte)80 : (byte)73);
        StatusBadge.Background = Solid(
            running ? (byte)63 : (byte)248,
            running ? (byte)185 : (byte)81,
            running ? (byte)80 : (byte)73,
            0x33);
        StatusBadgeText.Text = running ? "在线" : "离线";
        StatusBadgeText.Foreground = Solid(
            running ? (byte)63 : (byte)248,
            running ? (byte)185 : (byte)81,
            running ? (byte)80 : (byte)73);

        VersionText.Text = running && !string.IsNullOrWhiteSpace(health!.Version) ? health.Version : "—";
        CameraText.Text = running ? $"{health!.Running} / {health.Cameras}" : "—";
        UptimeText.Text = running ? FormatUptime(health!.Uptime) : "—";

        LastCheckText.Text = "最后检查 " + DateTime.Now.ToString("HH:mm:ss");
        UpdateButtons(running);
    }

    private static string FormatUptime(long seconds)
    {
        if (seconds <= 0)
        {
            return "—";
        }

        var span = TimeSpan.FromSeconds(seconds);
        if (span.TotalDays >= 1)
        {
            return $"{(int)span.TotalDays} 天 {span.Hours} 小时";
        }

        if (span.TotalHours >= 1)
        {
            return $"{(int)span.TotalHours} 小时 {span.Minutes} 分";
        }

        if (span.TotalMinutes >= 1)
        {
            return $"{(int)span.TotalMinutes} 分 {span.Seconds} 秒";
        }

        return $"{span.Seconds} 秒";
    }

    private static SolidColorBrush Solid(byte r, byte g, byte b, byte a = 255)
        => new(Windows.UI.Color.FromArgb(a, r, g, b));

    private void UpdateButtons(bool running)
    {
        StartButton.IsEnabled = !_busy && !running;
        StopButton.IsEnabled = !_busy && running;
        RestartButton.IsEnabled = !_busy;
        WebButton.IsEnabled = !_busy;
        RefreshButton.IsEnabled = !_busy;
        SaveButton.IsEnabled = !_busy;
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        BusyRing.IsActive = busy;
        UpdateButtons(_health is not null);
    }

    // ------------------------------------------------------------------ 引擎操作

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true);
        try
        {
            var start = App.Engine.Start();
            ShowMessage(start.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Error, "启动引擎", start.Message);

            if (start.Ok)
            {
                var healthy = await App.Engine.WaitForHealthyAsync(App.Api, TimeSpan.FromSeconds(30));
                ShowMessage(
                    healthy ? InfoBarSeverity.Success : InfoBarSeverity.Warning,
                    "启动引擎",
                    healthy
                        ? "引擎已就绪，可以打开 Web 控制台。"
                        : "进程已启动，但 30 秒内未检测到服务，请检查 Python 环境、端口与启动参数。");
            }
        }
        finally
        {
            SetBusy(false);
            await RefreshHealthAsync();
        }
    }

    private async void Stop_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true);
        try
        {
            var stop = await App.Engine.StopAsync(App.Api);
            ShowMessage(stop.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Error, "停止引擎", stop.Message);
        }
        finally
        {
            SetBusy(false);
            await RefreshHealthAsync();
        }
    }

    private async void Restart_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true);
        try
        {
            var restart = await App.Engine.RestartAsync(App.Api);
            ShowMessage(restart.Ok ? InfoBarSeverity.Success : InfoBarSeverity.Error, "重启引擎", restart.Message);
        }
        finally
        {
            SetBusy(false);
            await RefreshHealthAsync();
        }
    }

    private void OpenWeb_Click(object sender, RoutedEventArgs e)
    {
        var url = App.Api.BaseUrl + "/";
        if (ShellLauncher.Open(url))
        {
            ShowMessage(InfoBarSeverity.Informational, "Web 控制台", $"已用默认浏览器打开 {url}");
        }
        else
        {
            ShowMessage(InfoBarSeverity.Error, "Web 控制台", $"无法打开浏览器，请手动访问 {url}");
        }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e)
    {
        await RefreshHealthAsync();
    }

    // ------------------------------------------------------------------ 设置

    private void LoadSettingsIntoUi()
    {
        EngineUrlBox.Text = App.Settings.EngineUrl;
        RepoBox.Text = App.Settings.RepositoryRoot;
        PythonBox.Text = App.Settings.PythonPath;
        ArgsBox.Text = App.Settings.EngineArguments;
        SettingsPathText.Text = AppSettings.FilePath;

        var python = App.Engine.FindPython();
        PythonHintText.Text = python is null
            ? "自动探测结果：未找到 Python，请手动填写解释器路径。"
            : $"自动探测结果：{python}";
    }

    private async void SaveSettings_Click(object sender, RoutedEventArgs e)
    {
        var url = EngineUrlBox.Text.Trim();
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            ShowMessage(InfoBarSeverity.Error, "保存设置", "引擎地址必须是 http:// 或 https:// 开头的完整地址。");
            return;
        }

        App.Settings.EngineUrl = uri.ToString();
        App.Settings.RepositoryRoot = RepoBox.Text.Trim();
        App.Settings.PythonPath = PythonBox.Text.Trim();
        App.Settings.EngineArguments = ArgsBox.Text.Trim();

        try
        {
            App.Settings.Save();
            App.Api.UpdateBaseUrl(App.Settings.EngineUrl);
            EngineUrlBox.Text = App.Settings.EngineUrl;
            SettingsPathText.Text = AppSettings.FilePath;
            var python = App.Engine.FindPython();
            PythonHintText.Text = python is null
                ? "自动探测结果：未找到 Python，请手动填写解释器路径。"
                : $"自动探测结果：{python}";
            ShowMessage(InfoBarSeverity.Success, "保存设置", $"已保存到 {AppSettings.FilePath}");
        }
        catch (Exception ex)
        {
            ShowMessage(InfoBarSeverity.Error, "保存设置", $"写入设置失败：{ex.Message}");
        }

        await RefreshHealthAsync();
    }

    private void ShowMessage(InfoBarSeverity severity, string title, string message)
    {
        MessageBar.Severity = severity;
        MessageBar.Title = title;
        MessageBar.Message = message;
        MessageBar.IsOpen = true;
    }
}
