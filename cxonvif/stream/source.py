"""流地址工具 / Stream URL helpers."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit, urlunsplit


def split_credentials(url: str) -> tuple[str, str, str]:
    """拆分 ``rtsp://user:pass@host/path`` → (host_url_without_credentials, user, password)。"""
    if not url:
        return "", "", ""
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url, "", ""
    creds, host = parts.netloc.rsplit("@", 1)
    user = passwd = ""
    if ":" in creds:
        user, passwd = creds.split(":", 1)
    else:
        user = creds
    netloc = host
    rebuilt = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return rebuilt, unquote(user), unquote(passwd)


def with_credentials(url: str, username: str, password: str) -> str:
    if not username:
        return url
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    creds = quote(username, safe="")
    if password:
        creds += ":" + quote(password, safe="")
    return urlunsplit((parts.scheme, f"{creds}@{host}", parts.path, parts.query, parts.fragment))


def guess_stream_urls(host: str, username: str, password: str, channels: int = 1) -> dict[str, list[str]]:
    """按常见品牌给出主/子码流候选地址（用于“一键探测”）。"""
    base = [f"rtsp://{host}:554"]
    patterns = [
        ("海康 Hikvision", "/Streaming/Channels/101", "/Streaming/Channels/102"),
        ("海康旧版", "/h264/ch1/main/av_stream", "/h264/ch1/sub/av_stream"),
        ("大华 Dahua", "/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1"),
        ("宇视 Uniview", "/media/video1", "/media/video2"),
        ("水星/TP-LINK", "/stream1", "/stream2"),
        ("雄迈 XM", "/user=admin_password=_channel=1_stream=0.sdp?real_stream", "/user=admin_password=_channel=1_stream=1.sdp?real_stream"),
        ("通用 ONVIF", "/onvif1", "/onvif2"),
    ]
    result: dict[str, list[str]] = {}
    for name, main, sub in patterns:
        result[name] = [base[0] + main, base[0] + sub]
    return result
