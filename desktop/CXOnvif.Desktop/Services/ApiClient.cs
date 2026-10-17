using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using CXOnvif.Desktop.Models;

namespace CXOnvif.Desktop.Services;

/// <summary>一次 REST 调用的结果。</summary>
public sealed class ApiResult
{
    public bool Ok { get; init; }

    public string? Error { get; init; }

    public int Status { get; init; }

    public string Raw { get; init; } = string.Empty;

    /// <summary>完整响应 JSON。</summary>
    public JsonElement Root { get; init; }

    /// <summary>响应中的 data 节点；没有 data 时等于根节点。</summary>
    public JsonElement Data { get; init; }

    internal static ApiResult Fail(string error, int status = 0) => new()
    {
        Ok = false,
        Error = error,
        Status = status,
        Raw = string.Empty,
    };
}

/// <summary>登录结果。</summary>
public sealed class LoginOutcome
{
    public bool Ok { get; init; }

    public string? Error { get; init; }

    public string? Token { get; init; }

    public string? Username { get; init; }

    public bool MustChangePassword { get; init; }
}

/// <summary>
/// 程星 ONVIF REST API v2 客户端。令牌只保存在内存中，绝不落盘。
/// </summary>
public sealed class ApiClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString,
    };

    private readonly HttpClient _http;

    public ApiClient(string baseUrl)
    {
        BaseUrl = NormalizeUrl(baseUrl);
        var handler = new HttpClientHandler
        {
            UseProxy = false,
            AllowAutoRedirect = true,
        };
        _http = new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(12),
        };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("CXOnvif.Desktop/1.0");
    }

    public string BaseUrl { get; private set; }

    public string? Token { get; private set; }

    public string? Username { get; private set; }

    public bool HasToken => !string.IsNullOrWhiteSpace(Token);

    public string SettingsPath => AppSettings.FilePath;

    public void UpdateBaseUrl(string baseUrl) => BaseUrl = NormalizeUrl(baseUrl);

    public void SetSession(string? token, string? username)
    {
        Token = string.IsNullOrWhiteSpace(token) ? null : token;
        Username = username;
    }

    public void ClearSession()
    {
        Token = null;
        Username = null;
    }

    public static T? Read<T>(JsonElement element)
    {
        if (element.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return default;
        }

        try
        {
            return element.Deserialize<T>(JsonOptions);
        }
        catch (JsonException)
        {
            return default;
        }
    }

    public static string? ReadMessage(ApiResult result)
    {
        foreach (var element in new[] { result.Data, result.Root })
        {
            if (element.ValueKind == JsonValueKind.Object
                && element.TryGetProperty("message", out var message)
                && message.ValueKind == JsonValueKind.String)
            {
                return message.GetString();
            }
        }

        return null;
    }

    // ------------------------------------------------------------------ 基础调用

    public Task<ApiResult> GetAsync(string path, bool authenticated = true, CancellationToken ct = default)
        => SendAsync(HttpMethod.Get, path, null, authenticated, ct);

    public Task<ApiResult> PostAsync(string path, object? body = null, bool authenticated = true, CancellationToken ct = default)
        => SendAsync(HttpMethod.Post, path, body, authenticated, ct);

    // ------------------------------------------------------------------ 具体接口

    /// <summary>GET /api/v2/health（无需登录）。失败返回 null。</summary>
    public async Task<HealthInfo?> GetHealthAsync(CancellationToken ct = default)
    {
        var result = await SendAsync(HttpMethod.Get, "/api/v2/health", null, false, ct, TimeSpan.FromSeconds(4));
        if (!result.Ok)
        {
            return null;
        }

        try
        {
            var health = JsonSerializer.Deserialize<HealthInfo>(result.Raw, JsonOptions);
            return health is { IsHealthy: true } ? health : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>GET /api/v2/auth/state（无需登录）。</summary>
    public async Task<AuthState?> GetAuthStateAsync(CancellationToken ct = default)
    {
        var result = await SendAsync(HttpMethod.Get, "/api/v2/auth/state", null, false, ct);
        return result.Ok ? Read<AuthState>(result.Data) : null;
    }

    /// <summary>POST /api/v2/auth/login。</summary>
    public async Task<LoginOutcome> LoginAsync(string username, string password, CancellationToken ct = default)
    {
        var result = await SendAsync(
            HttpMethod.Post,
            "/api/v2/auth/login",
            new { username, password },
            authenticated: false,
            ct);

        if (!result.Ok)
        {
            return new LoginOutcome { Ok = false, Error = result.Error ?? "登录失败" };
        }

        var login = Read<LoginResult>(result.Root);
        if (login?.Token is null)
        {
            return new LoginOutcome { Ok = false, Error = "服务返回的登录结果缺少令牌" };
        }

        return new LoginOutcome
        {
            Ok = true,
            Token = login.Token,
            Username = string.IsNullOrWhiteSpace(login.Username) ? username : login.Username,
            MustChangePassword = login.MustChangePassword,
        };
    }

    /// <summary>POST /api/v2/auth/logout（尽力而为）。</summary>
    public Task<ApiResult> LogoutAsync(CancellationToken ct = default)
        => SendAsync(HttpMethod.Post, "/api/v2/auth/logout", null, true, ct);

    /// <summary>POST /api/v2/auth/password。</summary>
    public Task<ApiResult> ChangePasswordAsync(string currentPassword, string newPassword, CancellationToken ct = default)
        => SendAsync(HttpMethod.Post, "/api/v2/auth/password", new { currentPassword, newPassword }, true, ct);

    /// <summary>POST /api/v2/system/shutdown。</summary>
    public Task<ApiResult> ShutdownAsync(CancellationToken ct = default)
        => SendAsync(HttpMethod.Post, "/api/v2/system/shutdown", null, true, ct);

    /// <summary>GET /api/v2/service/autostart。</summary>
    public Task<ApiResult> GetAutostartAsync(CancellationToken ct = default)
        => SendAsync(HttpMethod.Get, "/api/v2/service/autostart", null, true, ct);

    /// <summary>POST /api/v2/service/autostart。</summary>
    public Task<ApiResult> SetAutostartAsync(bool enabled, string mode = "auto", CancellationToken ct = default)
        => SendAsync(HttpMethod.Post, "/api/v2/service/autostart", new { enabled, mode }, true, ct);

    // ------------------------------------------------------------------ 传输层

    private async Task<ApiResult> SendAsync(
        HttpMethod method,
        string path,
        object? body,
        bool authenticated,
        CancellationToken ct,
        TimeSpan? timeout = null)
    {
        var url = BaseUrl + path;

        try
        {
            using var request = new HttpRequestMessage(method, url);

            if (authenticated && HasToken)
            {
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
            }

            if (body is not null)
            {
                var json = JsonSerializer.Serialize(body, JsonOptions);
                request.Content = new StringContent(json, Encoding.UTF8, "application/json");
            }

            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(timeout ?? TimeSpan.FromSeconds(10));

            using var response = await _http.SendAsync(request, cts.Token).ConfigureAwait(false);
            var text = await response.Content.ReadAsStringAsync(cts.Token).ConfigureAwait(false);
            var status = (int)response.StatusCode;

            try
            {
                using var document = JsonDocument.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text);
                var root = document.RootElement.Clone();
                var ok = response.IsSuccessStatusCode;
                string? error = null;

                if (root.ValueKind == JsonValueKind.Object)
                {
                    if (root.TryGetProperty("ok", out var okProperty)
                        && okProperty.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    {
                        ok = ok && okProperty.GetBoolean();
                    }

                    if (root.TryGetProperty("error", out var errorProperty)
                        && errorProperty.ValueKind == JsonValueKind.String)
                    {
                        error = errorProperty.GetString();
                    }
                }

                if (!ok && string.IsNullOrWhiteSpace(error))
                {
                    error = $"请求失败（HTTP {status}）";
                }

                var data = root;
                if (root.ValueKind == JsonValueKind.Object
                    && root.TryGetProperty("data", out var dataProperty))
                {
                    data = dataProperty;
                }

                return new ApiResult
                {
                    Ok = ok,
                    Error = ok ? null : error,
                    Status = status,
                    Raw = text,
                    Root = root,
                    Data = data,
                };
            }
            catch (JsonException)
            {
                var snippet = text.Length > 160 ? text[..160] : text;
                return ApiResult.Fail($"引擎返回了非 JSON 内容（HTTP {status}）：{snippet}", status);
            }
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return ApiResult.Fail("请求超时，引擎可能未启动或地址不可达");
        }
        catch (OperationCanceledException)
        {
            return ApiResult.Fail("操作已取消");
        }
        catch (HttpRequestException ex)
        {
            return ApiResult.Fail($"无法连接引擎（{ex.Message}）");
        }
        catch (Exception ex)
        {
            return ApiResult.Fail(ex.Message);
        }
    }

    private static string NormalizeUrl(string? baseUrl)
    {
        var value = string.IsNullOrWhiteSpace(baseUrl) ? AppSettings.DefaultEngineUrl : baseUrl.Trim();
        if (!value.Contains("://", StringComparison.Ordinal))
        {
            value = "http://" + value;
        }

        return value.TrimEnd('/');
    }
}
