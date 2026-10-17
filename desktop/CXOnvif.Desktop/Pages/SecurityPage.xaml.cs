using CXOnvif.Desktop.Models;
using CXOnvif.Desktop.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace CXOnvif.Desktop.Pages;

public sealed partial class SecurityPage : Page
{
    private bool _busy;

    public SecurityPage()
    {
        InitializeComponent();
        Loaded += SecurityPage_Loaded;
    }

    private async void SecurityPage_Loaded(object sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(App.Api.Username))
        {
            UsernameBox.Text = App.Api.Username;
        }

        UpdateSessionUi();
        await LoadAuthStateAsync();
    }

    private async Task LoadAuthStateAsync()
    {
        var state = await App.Api.GetAuthStateAsync();
        if (state is null)
        {
            MustChangeBar.IsOpen = false;
            AuthStateText.Text = "无法读取服务端登录状态（引擎可能未运行）。";
            return;
        }

        MustChangeBar.IsOpen = state.MustChangePassword;
        AuthStateText.Text = state.RequireLogin
            ? $"服务端已开启登录校验，管理员账号：{state.Username ?? "admin"}。"
            : "服务端未开启登录校验（requireLogin = false），可直接修改密码或管理启动项。";
    }

    private void UpdateSessionUi()
    {
        SessionText.Text = App.Api.HasToken
            ? $"已登录：{App.Api.Username}"
            : "当前未登录";
        LoginButton.IsEnabled = !_busy;
        LogoutButton.IsEnabled = !_busy && App.Api.HasToken;
        ChangeButton.IsEnabled = !_busy;
        UsernameBox.IsEnabled = !_busy;
        PasswordBox.IsEnabled = !_busy;
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        UpdateSessionUi();
    }

    private async void Login_Click(object sender, RoutedEventArgs e)
    {
        await LoginAsync();
    }

    private async void PasswordBox_KeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Enter)
        {
            e.Handled = true;
            await LoginAsync();
        }
    }

    private async Task LoginAsync()
    {
        if (_busy)
        {
            return;
        }

        var username = string.IsNullOrWhiteSpace(UsernameBox.Text) ? "admin" : UsernameBox.Text.Trim();
        var password = PasswordBox.Password;
        if (string.IsNullOrEmpty(password))
        {
            ShowMessage(InfoBarSeverity.Error, "登录", "请输入密码。");
            return;
        }

        SetBusy(true);
        try
        {
            var result = await App.Api.LoginAsync(username, password);
            if (!result.Ok)
            {
                ShowMessage(InfoBarSeverity.Error, "登录", result.Error ?? "登录失败");
                return;
            }

            App.Api.SetSession(result.Token, result.Username);
            PasswordBox.Password = string.Empty;
            MustChangeBar.IsOpen = result.MustChangePassword;
            UsernameBox.Text = result.Username ?? username;
            ShowMessage(
                InfoBarSeverity.Success,
                "登录",
                result.MustChangePassword ? "登录成功。当前账号仍使用初始密码，请立即修改。" : "登录成功。");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void Logout_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true);
        try
        {
            await App.Api.LogoutAsync();
            App.Api.ClearSession();
            ShowMessage(InfoBarSeverity.Informational, "注销", "已退出登录，内存中的令牌已清除。");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void ChangePassword_Click(object sender, RoutedEventArgs e)
    {
        if (_busy)
        {
            return;
        }

        var current = CurrentPasswordBox.Password;
        var next = NewPasswordBox.Password;
        var confirm = ConfirmPasswordBox.Password;

        if (string.IsNullOrEmpty(current))
        {
            ShowMessage(InfoBarSeverity.Error, "修改密码", "请输入当前密码。");
            return;
        }

        if (next.Length < 8)
        {
            ShowMessage(InfoBarSeverity.Error, "修改密码", "新密码至少 8 位。");
            return;
        }

        if (next != confirm)
        {
            ShowMessage(InfoBarSeverity.Error, "修改密码", "两次输入的新密码不一致。");
            return;
        }

        if (next == current)
        {
            ShowMessage(InfoBarSeverity.Error, "修改密码", "新密码不能与当前密码相同。");
            return;
        }

        if (!App.Api.HasToken)
        {
            ShowMessage(InfoBarSeverity.Warning, "修改密码", "请先登录，再修改密码。");
            return;
        }

        SetBusy(true);
        try
        {
            var result = await App.Api.ChangePasswordAsync(current, next);
            var message = ApiClient.ReadMessage(result);
            if (!result.Ok)
            {
                ShowMessage(InfoBarSeverity.Error, "修改密码", result.Error ?? "修改失败");
                return;
            }

            App.Api.ClearSession();
            MustChangeBar.IsOpen = false;
            CurrentPasswordBox.Password = string.Empty;
            NewPasswordBox.Password = string.Empty;
            ConfirmPasswordBox.Password = string.Empty;
            ShowMessage(
                InfoBarSeverity.Success,
                "修改密码",
                message ?? "密码已更新，请使用新密码重新登录。");
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
