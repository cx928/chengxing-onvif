using System.Diagnostics;

namespace CXOnvif.Desktop.Services;

/// <summary>用系统默认程序打开链接（网页、邮件）。</summary>
public static class ShellLauncher
{
    public static bool Open(string target)
    {
        if (string.IsNullOrWhiteSpace(target))
        {
            return false;
        }

        try
        {
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            return true;
        }
        catch
        {
            return false;
        }
    }
}
