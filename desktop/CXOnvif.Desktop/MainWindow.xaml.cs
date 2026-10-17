using CXOnvif.Desktop.Pages;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;
using Windows.UI;

namespace CXOnvif.Desktop;

public sealed partial class MainWindow : Window
{
    private const int DefaultWidth = 980;
    private const int DefaultHeight = 680;

    public MainWindow()
    {
        InitializeComponent();
        Title = "程星 ONVIF 控制台";

        ApplyWindowSize();

        ContentFrame.Navigate(typeof(OverviewPage));
        Nav.SelectedItem = Nav.MenuItems[0];
    }

    // ------------------------------------------------------------------ 导航

    private void Nav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem item || item.Tag is not string tag)
        {
            return;
        }

        var pageType = tag switch
        {
            "security" => typeof(SecurityPage),
            "autostart" => typeof(AutostartPage),
            "about" => typeof(AboutPage),
            _ => typeof(OverviewPage),
        };

        if (ContentFrame.CurrentSourcePageType != pageType)
        {
            ContentFrame.Navigate(pageType);
        }
    }

    // ------------------------------------------------------------------ 窗口外观

    private void ApplyWindowSize()
    {
        try
        {
            var appWindow = AppWindow;
            var displayArea = DisplayArea.GetFromWindowId(appWindow.Id, DisplayAreaFallback.Primary);

            if (displayArea is null)
            {
                appWindow.Resize(new SizeInt32(DefaultWidth, DefaultHeight));
            }
            else
            {
                var workArea = displayArea.WorkArea;
                var width = Math.Min(DefaultWidth, workArea.Width);
                var height = Math.Min(DefaultHeight, workArea.Height);
                var x = workArea.X + Math.Max(0, (workArea.Width - width) / 2);
                var y = workArea.Y + Math.Max(0, (workArea.Height - height) / 2);
                appWindow.MoveAndResize(new RectInt32(x, y, width, height));
            }

            ApplyTitleBarTheme(appWindow);
        }
        catch
        {
            // 窗口尺寸/标题栏配色失败不影响使用
        }
    }

    private static void ApplyTitleBarTheme(AppWindow appWindow)
    {
        var titleBar = appWindow.TitleBar;
        var background = Color.FromArgb(255, 20, 20, 24);
        var foreground = Color.FromArgb(255, 243, 245, 249);
        var muted = Color.FromArgb(255, 140, 146, 158);

        titleBar.BackgroundColor = background;
        titleBar.ForegroundColor = foreground;
        titleBar.InactiveBackgroundColor = background;
        titleBar.InactiveForegroundColor = muted;
        titleBar.ButtonBackgroundColor = background;
        titleBar.ButtonForegroundColor = foreground;
        titleBar.ButtonHoverBackgroundColor = Color.FromArgb(255, 43, 45, 53);
        titleBar.ButtonHoverForegroundColor = foreground;
        titleBar.ButtonPressedBackgroundColor = Color.FromArgb(255, 58, 61, 71);
        titleBar.ButtonPressedForegroundColor = foreground;
        titleBar.ButtonInactiveBackgroundColor = background;
        titleBar.ButtonInactiveForegroundColor = muted;
    }
}
