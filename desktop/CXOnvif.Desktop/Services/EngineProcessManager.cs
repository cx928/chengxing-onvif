using System.Diagnostics;
using CXOnvif.Desktop.Models;

namespace CXOnvif.Desktop.Services;

/// <summary>启动/停止/重启引擎的返回。</summary>
public sealed record EngineActionResult(bool Ok, string Message);

/// <summary>
/// 以隐藏窗口方式启动 <c>python -m cxonvif serve --silent</c>，并负责停止它。
/// 引擎进程 PID 记录在 <c>%LOCALAPPDATA%\ChengXingOnvif.Desktop\engine.pid</c>，
/// 便于下次启动桌面端时仍能停止上次由桌面端拉起的引擎。
/// </summary>
public sealed class EngineProcessManager
{
    private static readonly string[] PythonFileNames = { "pythonw.exe", "python.exe" };

    private readonly AppSettings _settings;
    private Process? _process;

    public EngineProcessManager(AppSettings settings) => _settings = settings;

    public static string AppDataDirectory => AppSettings.DirectoryPath;

    public static string PidFilePath => Path.Combine(AppDataDirectory, "engine.pid");

    /// <summary>最近一次探测到的 Python 解释器。</summary>
    public string? ResolvedPython { get; private set; }

    // ------------------------------------------------------------------ 探测

    /// <summary>自动探测 pythonw.exe，其次 python.exe（可在设置中覆盖）。</summary>
    public string? FindPython()
    {
        var configured = _settings.PythonPath;
        if (!string.IsNullOrWhiteSpace(configured))
        {
            if (File.Exists(configured))
            {
                return configured;
            }

            if (Directory.Exists(configured))
            {
                foreach (var name in PythonFileNames)
                {
                    var candidate = Path.Combine(configured, name);
                    if (File.Exists(candidate))
                    {
                        return candidate;
                    }
                }
            }
        }

        foreach (var name in PythonFileNames)
        {
            foreach (var directory in CandidateDirectories())
            {
                try
                {
                    var candidate = Path.Combine(directory, name);
                    if (File.Exists(candidate))
                    {
                        return candidate;
                    }
                }
                catch
                {
                    // 非法路径直接跳过
                }
            }
        }

        return null;
    }

    // ------------------------------------------------------------------ 启动

    public EngineActionResult Start()
    {
        if (TrackedProcessAlive())
        {
            return new EngineActionResult(true, "引擎进程已在运行（由桌面端启动）。");
        }

        var python = FindPython();
        if (python is null)
        {
            return new EngineActionResult(
                false,
                "未找到 Python。请安装 Python 3，或在设置中填写 pythonw.exe / python.exe 的完整路径。");
        }

        ResolvedPython = python;

        var workingDirectory = _settings.RepositoryRoot;
        if (string.IsNullOrWhiteSpace(workingDirectory) || !Directory.Exists(workingDirectory))
        {
            return new EngineActionResult(false, $"仓库目录不存在：{workingDirectory}");
        }

        var arguments = string.IsNullOrWhiteSpace(_settings.EngineArguments)
            ? AppSettings.DefaultEngineArguments
            : _settings.EngineArguments;

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            };

            // 即使 cxonvif 未 pip 安装，也能从仓库根目录以 -m 方式导入
            var pythonPath = Environment.GetEnvironmentVariable("PYTHONPATH");
            startInfo.Environment["PYTHONPATH"] = string.IsNullOrWhiteSpace(pythonPath)
                ? workingDirectory
                : workingDirectory + ";" + pythonPath;
            startInfo.Environment["PYTHONUTF8"] = "1";
            startInfo.Environment["PYTHONIOENCODING"] = "utf-8";

            var process = Process.Start(startInfo);
            if (process is null)
            {
                return new EngineActionResult(false, "创建引擎进程失败。");
            }

            _process = process;
            SavePid(process.Id);

            return new EngineActionResult(
                true,
                $"已启动引擎：{Path.GetFileName(python)}（PID {process.Id}），正在等待服务就绪…");
        }
        catch (Exception ex)
        {
            return new EngineActionResult(false, $"启动引擎失败：{ex.Message}");
        }
    }

    // ------------------------------------------------------------------ 停止

    /// <summary>先尝试 API 关闭（需要令牌），失败或超时后结束进程。</summary>
    public async Task<EngineActionResult> StopAsync(ApiClient api, CancellationToken ct = default)
    {
        var notes = new List<string>();
        var apiRequested = false;

        if (api.HasToken)
        {
            var shutdown = await api.ShutdownAsync(ct).ConfigureAwait(false);
            apiRequested = shutdown.Ok;
            notes.Add(apiRequested ? "已通过 API 请求关闭" : $"API 关闭失败：{shutdown.Error}");
        }
        else
        {
            notes.Add("未登录，跳过 API 关闭（可在“安全”页登录）");
        }

        if (apiRequested && await WaitForDownAsync(api, TimeSpan.FromSeconds(9), ct).ConfigureAwait(false))
        {
            ClearPid();
            return new EngineActionResult(true, string.Join("；", notes) + "；引擎已停止。");
        }

        if (apiRequested)
        {
            notes.Add("服务仍在运行，改为结束进程");
        }

        var killed = KillTrackedProcess(out var detail);
        notes.Add(detail);

        if (killed)
        {
            var down = await WaitForDownAsync(api, TimeSpan.FromSeconds(6), ct).ConfigureAwait(false);
            if (!down)
            {
                notes.Add("进程已结束，但服务仍可访问");
            }

            return new EngineActionResult(true, string.Join("；", notes));
        }

        return new EngineActionResult(false, string.Join("；", notes));
    }

    public async Task<EngineActionResult> RestartAsync(ApiClient api, CancellationToken ct = default)
    {
        var stop = await StopAsync(api, ct).ConfigureAwait(false);
        if (!stop.Ok)
        {
            return new EngineActionResult(false, $"重启失败：{stop.Message}");
        }

        try
        {
            await Task.Delay(800, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            return new EngineActionResult(false, "操作已取消");
        }

        var start = Start();
        if (!start.Ok)
        {
            return start;
        }

        var healthy = await WaitForHealthyAsync(api, TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
        return new EngineActionResult(
            true,
            healthy ? "引擎已重启，服务已恢复。" : "引擎已重启，但服务尚未就绪，请稍后刷新。");
    }

    // ------------------------------------------------------------------ 健康等待

    public async Task<bool> WaitForHealthyAsync(ApiClient api, TimeSpan timeout, CancellationToken ct = default)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            var health = await api.GetHealthAsync(ct).ConfigureAwait(false);
            if (health is not null)
            {
                return true;
            }

            try
            {
                await Task.Delay(700, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return false;
            }
        }

        return false;
    }

    private static async Task<bool> WaitForDownAsync(ApiClient api, TimeSpan timeout, CancellationToken ct)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            var health = await api.GetHealthAsync(ct).ConfigureAwait(false);
            if (health is null)
            {
                return true;
            }

            try
            {
                await Task.Delay(600, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return false;
            }
        }

        return false;
    }

    // ------------------------------------------------------------------ 进程跟踪

    public bool TrackedProcessAlive()
    {
        if (_process is { } process)
        {
            try
            {
                if (!process.HasExited)
                {
                    return true;
                }
            }
            catch
            {
                // 忽略：进程句柄可能已失效
            }
        }

        var pid = LoadPid();
        if (pid is null)
        {
            return false;
        }

        try
        {
            using var existing = Process.GetProcessById(pid.Value);
            return !existing.HasExited && IsPythonProcess(existing);
        }
        catch
        {
            return false;
        }
    }

    private bool KillTrackedProcess(out string detail)
    {
        if (_process is { } process)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                    process.WaitForExit(5000);
                    ClearPid();
                    _process = null;
                    detail = $"已结束引擎进程（PID {process.Id}）";
                    return true;
                }
            }
            catch (Exception ex)
            {
                detail = $"结束引擎进程失败：{ex.Message}";
                ClearPid();
                return false;
            }
        }

        var pid = LoadPid();
        if (pid is null)
        {
            detail = "没有可结束的引擎进程记录（可能由开机自启或其它方式启动）";
            return false;
        }

        try
        {
            using var existing = Process.GetProcessById(pid.Value);
            if (existing.HasExited)
            {
                ClearPid();
                detail = "引擎进程已退出";
                return false;
            }

            if (!IsPythonProcess(existing))
            {
                ClearPid();
                detail = $"PID {pid.Value} 已不是 Python 进程，忽略";
                return false;
            }

            existing.Kill(entireProcessTree: true);
            existing.WaitForExit(5000);
            ClearPid();
            detail = $"已结束引擎进程（PID {pid.Value}）";
            return true;
        }
        catch (ArgumentException)
        {
            ClearPid();
            detail = "引擎进程已退出";
            return false;
        }
        catch (Exception ex)
        {
            ClearPid();
            detail = $"结束进程失败：{ex.Message}";
            return false;
        }
    }

    private static bool IsPythonProcess(Process process)
    {
        try
        {
            return process.ProcessName.Contains("python", StringComparison.OrdinalIgnoreCase)
                || process.ProcessName.Contains("pyw", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static void SavePid(int pid)
    {
        try
        {
            Directory.CreateDirectory(AppDataDirectory);
            File.WriteAllText(PidFilePath, pid.ToString());
        }
        catch
        {
            // PID 文件只是辅助信息，写入失败不影响启动
        }
    }

    private static int? LoadPid()
    {
        try
        {
            if (!File.Exists(PidFilePath))
            {
                return null;
            }

            var text = File.ReadAllText(PidFilePath).Trim();
            return int.TryParse(text, out var pid) && pid > 0 ? pid : null;
        }
        catch
        {
            return null;
        }
    }

    private static void ClearPid()
    {
        try
        {
            if (File.Exists(PidFilePath))
            {
                File.Delete(PidFilePath);
            }
        }
        catch
        {
            // 忽略
        }
    }

    // ------------------------------------------------------------------ 候选目录

    private IEnumerable<string> CandidateDirectories()
    {
        // 1) 仓库内的虚拟环境优先
        yield return Path.Combine(_settings.RepositoryRoot, ".venv", "Scripts");
        yield return Path.Combine(_settings.RepositoryRoot, "venv", "Scripts");
        yield return Path.Combine(_settings.RepositoryRoot, "env", "Scripts");

        // 2) PATH
        var path = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        foreach (var segment in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = segment.Trim().Trim('"');
            if (!string.IsNullOrWhiteSpace(trimmed))
            {
                yield return trimmed;
            }
        }

        // 3) 常见安装位置
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        var programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);

        yield return Path.Combine(localAppData, "Microsoft", "WindowsApps");
        yield return Path.Combine(localAppData, "Programs", "Python", "Launcher");

        var roots = new List<string>
        {
            Path.Combine(localAppData, "Programs", "Python"),
            programFiles,
            programFilesX86,
            "C:\\",
        };

        foreach (var root in roots)
        {
            string[] directories;
            try
            {
                directories = Directory.GetDirectories(root, "Python3*");
            }
            catch
            {
                continue;
            }

            foreach (var directory in directories.OrderByDescending(d => d, StringComparer.OrdinalIgnoreCase))
            {
                yield return directory;
            }
        }
    }
}
