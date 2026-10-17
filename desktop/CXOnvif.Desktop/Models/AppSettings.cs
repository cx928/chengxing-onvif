using System.Text.Json;
using System.Text.Json.Serialization;

namespace CXOnvif.Desktop.Models;

/// <summary>
/// 桌面端本地设置，保存在 <c>%LOCALAPPDATA%\ChengXingOnvif.Desktop\settings.json</c>。
/// 不保存任何密码或登录令牌。
/// </summary>
public sealed class AppSettings
{
    public const string DefaultEngineUrl = "http://127.0.0.1:5552";
    public const string DefaultRepositoryRoot = @"C:\ChengXing-ONVIF";
    public const string DefaultEngineArguments = "-m cxonvif serve --silent";

    /// <summary>引擎 REST 地址，例如 http://127.0.0.1:5552。</summary>
    public string EngineUrl { get; set; } = DefaultEngineUrl;

    /// <summary>Python 引擎仓库根目录（启动引擎时的工作目录）。</summary>
    public string RepositoryRoot { get; set; } = DefaultRepositoryRoot;

    /// <summary>Python 解释器完整路径；留空则自动探测 pythonw.exe / python.exe。</summary>
    public string PythonPath { get; set; } = string.Empty;

    /// <summary>启动引擎时传给 Python 的参数。</summary>
    public string EngineArguments { get; set; } = DefaultEngineArguments;

    [JsonIgnore]
    public static string DirectoryPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ChengXingOnvif.Desktop");

    [JsonIgnore]
    public static string FilePath => Path.Combine(DirectoryPath, "settings.json");

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
            {
                var json = File.ReadAllText(FilePath);
                var loaded = JsonSerializer.Deserialize<AppSettings>(json, SerializerOptions);
                if (loaded is not null)
                {
                    loaded.Normalize();
                    return loaded;
                }
            }
        }
        catch
        {
            // 配置损坏时回落到默认值，不阻塞启动
        }

        var fresh = new AppSettings();
        fresh.Save();
        return fresh;
    }

    public void Save()
    {
        Normalize();
        Directory.CreateDirectory(DirectoryPath);
        File.WriteAllText(FilePath, JsonSerializer.Serialize(this, SerializerOptions));
    }

    private void Normalize()
    {
        EngineUrl = string.IsNullOrWhiteSpace(EngineUrl)
            ? DefaultEngineUrl
            : EngineUrl.Trim().TrimEnd('/');

        RepositoryRoot = string.IsNullOrWhiteSpace(RepositoryRoot)
            ? DefaultRepositoryRoot
            : RepositoryRoot.Trim().Trim('"');

        PythonPath = (PythonPath ?? string.Empty).Trim().Trim('"');

        EngineArguments = string.IsNullOrWhiteSpace(EngineArguments)
            ? DefaultEngineArguments
            : EngineArguments.Trim();
    }
}
