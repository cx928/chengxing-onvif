using System.Text.Json.Serialization;

namespace CXOnvif.Desktop.Models;

/// <summary>GET /api/v2/health 的返回（裸 JSON，无 data 包装）。</summary>
public sealed class HealthInfo
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("brand")]
    public string Brand { get; set; } = string.Empty;

    [JsonPropertyName("version")]
    public string Version { get; set; } = string.Empty;

    [JsonPropertyName("uptime")]
    public long Uptime { get; set; }

    [JsonPropertyName("cameras")]
    public int Cameras { get; set; }

    [JsonPropertyName("running")]
    public int Running { get; set; }

    public bool IsHealthy => string.Equals(Status, "ok", StringComparison.OrdinalIgnoreCase);
}

/// <summary>POST /api/v2/auth/login 的返回（裸 JSON）。</summary>
public sealed class LoginResult
{
    public bool Ok { get; set; }

    public string? Token { get; set; }

    public string? Username { get; set; }

    public bool MustChangePassword { get; set; }

    public string? Error { get; set; }
}

/// <summary>GET /api/v2/auth/state。</summary>
public sealed class AuthState
{
    [JsonPropertyName("requireLogin")]
    public bool RequireLogin { get; set; }

    [JsonPropertyName("username")]
    public string? Username { get; set; }

    [JsonPropertyName("mustChangePassword")]
    public bool MustChangePassword { get; set; }

    [JsonPropertyName("brand")]
    public string? Brand { get; set; }
}

/// <summary>GET/POST /api/v2/service/autostart 的 status 结构。</summary>
public sealed class AutostartStatus
{
    [JsonPropertyName("platform")]
    public string? Platform { get; set; }

    [JsonPropertyName("installed")]
    public bool Installed { get; set; }

    [JsonPropertyName("task")]
    public bool Task { get; set; }

    [JsonPropertyName("startupFolder")]
    public bool StartupFolder { get; set; }

    [JsonPropertyName("admin")]
    public bool Admin { get; set; }

    [JsonPropertyName("detail")]
    public string? Detail { get; set; }

    [JsonPropertyName("launcher")]
    public string? Launcher { get; set; }

    [JsonPropertyName("active")]
    public bool? Active { get; set; }

    [JsonPropertyName("unit")]
    public string? Unit { get; set; }

    public string PlatformDisplay => Platform?.ToLowerInvariant() switch
    {
        "windows" => "Windows（计划任务 / 启动文件夹）",
        "linux" => "Linux（systemd）",
        "macos" => "macOS（launchd）",
        null or "" => "未知",
        _ => Platform!,
    };
}

/// <summary>POST /api/v2/service/autostart 的 data。</summary>
public sealed class AutostartSetResult
{
    [JsonPropertyName("message")]
    public string? Message { get; set; }

    [JsonPropertyName("status")]
    public AutostartStatus? Status { get; set; }
}
