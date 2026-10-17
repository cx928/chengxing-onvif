using CXOnvif.Desktop.Models;
using CXOnvif.Desktop.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace CXOnvif.Desktop.Pages;

public sealed partial class AutostartPage : Page
{
    private bool _suppressToggle;
    private bool _busy;
    private bool _available;

    public AutostartPage()
    {
        InitializeComponent();
        Loaded += AutostartPage_Loaded;
    }

    private async void AutostartPage_Loaded(object sender, RoutedEventArgs e)
    {
        await LoadStatusAsync();
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        BusyRing.IsActive = busy;
        AutostartToggle.IsEnabled = !busy && _available;
        RefreshButton.IsEnabled = !busy;
    }

    private async Task LoadStatusAsync()
    {
        var result = await App.Api.GetAutostartAsync();
        LoginStateText.Text = App.Api.HasToken ? $"已登录：{App.Api.Username}" : "未登录";

        if (!result.Ok)
        {
            _available = false;
            _suppressToggle = true;
            AutostartToggle.IsOn = false;
            _suppressToggle = false;
            AutostartToggle.IsEnabled = false;

            InstalledText.Text = "无法读取";
            PlatformText.Text = "—";
            AdminText.Text = "—";
            TaskText.Text = "—";
            StartupFolderText.Text = "—";
            LauncherText.Text = "—";
            DetailText.Text = result.Error ?? string.Empty;
            UpdatedText.Text = "读取失败 " + DateTime.Now.ToString("HH:mm:ss");
            ShowMessage(InfoBarSeverity.Warning, "启动项状态", result.Error ?? "读取启动项状态失败，请先登录。");
            return;
        }

        var status = ApiClient.Read<AutostartStatus>(result.Data) ?? new AutostartStatus();
        _available = true;
        _suppressToggle = true;
        AutostartToggle.IsOn = status.Installed;
        _suppressToggle = false;
        AutostartToggle.IsEnabled = true;

        InstalledText.Text = status.Installed ? "已安装" : "未安装";
        PlatformText.Text = status.PlatformDisplay;
        AdminText.Text = status.Admin ? "是" : "否";
        TaskText.Text = status.Task ? "已创建" : "无";
        StartupFolderText.Text = status.StartupFolder ? "已创建" : "无";
        LauncherText.Text = string.IsNullOrWhiteSpace(status.Launcher) ? "—" : status.Launcher;
        DetailText.Text = string.IsNullOrWhiteSpace(status.Detail) ? "—" : status.Detail;
        UpdatedText.Text = "更新于 " + DateTime.Now.ToString("HH:mm:ss");
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true);
        try
        {
            await LoadStatusAsync();
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void AutostartToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (_suppressToggle || _busy)
        {
            return;
        }

        if (!App.Api.HasToken)
        {
            _suppressToggle = true;
            AutostartToggle.IsOn = !AutostartToggle.IsOn;
            _suppressToggle = false;
            ShowMessage(InfoBarSeverity.Warning, "启动项", "请先在“安全”页登录管理员账号，再修改开机自启。");
            return;
        }

        var enabled = AutostartToggle.IsOn;
        SetBusy(true);
        try
        {
            var result = await App.Api.SetAutostartAsync(enabled, "auto");
            var message = ApiClient.ReadMessage(result);
            if (!result.Ok)
            {
                ShowMessage(InfoBarSeverity.Error, "启动项", result.Error ?? "设置开机自启失败");
            }
            else
            {
                ShowMessage(
                    InfoBarSeverity.Success,
                    "启动项",
                    message ?? (enabled ? "已开启开机自动启动。" : "已关闭开机自动启动。"));
            }

            await LoadStatusAsync();
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void ShowMessage(InfoBarSeverity severity, string title, string message)
    {
        MessageBar.Severity = severity;
        MessageBar.Title = title;
        MessageBar.Message = message;
        MessageBar.IsOpen = true;
    }
}
