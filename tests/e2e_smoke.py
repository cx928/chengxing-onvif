"""端到端冒烟测试（需要正在运行的服务）。

用法::

    set CXONVIF_WEB=http://127.0.0.1:5552
    set CXONVIF_PASSWORD=cx123456
    python tests/e2e_smoke.py

会检查：健康接口、登录、系统信息、摄像机运行、检测管线、叠加推流、ONVIF
设备/事件/快照、MediaMTX 路径与静态资源。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

import requests

BASE = os.environ.get("CXONVIF_WEB", "http://127.0.0.1:5552").rstrip("/")
PASSWORD = os.environ.get("CXONVIF_PASSWORD", "cx123456")
CAMERA_ID = int(os.environ.get("CXONVIF_CAMERA", "1"))
ONVIF_PORT = int(os.environ.get("CXONVIF_ONVIF_PORT", "8001"))
ONVIF_USER = os.environ.get("CXONVIF_ONVIF_USER", "admin")
ONVIF_PASSWORD = os.environ.get("CXONVIF_ONVIF_PASSWORD", "")
FFPROBE = os.environ.get("CXONVIF_FFPROBE", "ffprobe")

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("PASS  " if condition else "FAIL  ") + message)
    if not condition:
        FAILURES.append(message)


def main() -> int:
    health = requests.get(f"{BASE}/api/v2/health", timeout=10).json()
    check(health.get("status") == "ok", f"健康检查 v{health.get('version')} · 摄像机 {health.get('cameras')}")

    state = requests.get(f"{BASE}/api/v2/auth/state", timeout=10).json()["data"]
    if state.get("requireLogin"):
        login = requests.post(
            f"{BASE}/api/v2/auth/login",
            json={"username": "admin", "password": PASSWORD},
            timeout=10,
        ).json()
        check(bool(login.get("token")), "管理员登录")
        headers = {"Authorization": f"Bearer {login['token']}"}
        bad = requests.post(
            f"{BASE}/api/v2/auth/login",
            json={"username": "admin", "password": "definitely-wrong"},
            timeout=10,
        )
        check(bad.status_code == 401, "错误密码被拒绝")
    else:
        headers = {}

    info = requests.get(f"{BASE}/api/v2/system/info", headers=headers, timeout=20).json()["data"]
    check(bool(info["hardware"]["cpu"]), f"CPU: {info['hardware']['cpu']}")
    check(bool(info["hardware"]["recommendedEncoder"]), f"推荐编码器: {info['hardware']['recommendedEncoder']}")
    check(info["links"]["bilibili"].startswith("https://space.bilibili.com/"), "品牌链接")

    cameras = requests.get(f"{BASE}/api/v2/cameras", headers=headers, timeout=20).json()["data"]["cameras"]
    check(bool(cameras), f"摄像机数量: {len(cameras)}")
    camera = next((c for c in cameras if c["id"] == CAMERA_ID), cameras[0] if cameras else None)
    if camera and camera.get("status") == "running":
        check(camera["frame"]["frames"] > 0, f"帧源已出帧: {camera['frame']['frames']}")
        overlay = camera.get("overlay", {}).get("stats", {})
        check(bool(overlay.get("encoder")), f"叠加编码器: {overlay.get('encoder')}")
        check(camera.get("mercury", {}).get("manufacturer") in ("MERCURY", "TP-LINK", "Hikvision", "Dahua", "UNV"),
              f"ONVIF 厂商画像: {camera.get('mercury', {}).get('manufacturer')}")
    else:
        check(False, "摄像机未运行（跳过运行态检查）")

    # ONVIF
    soap_headers = {"Content-Type": "application/soap+xml"}
    onvif_auth = (ONVIF_USER, ONVIF_PASSWORD)

    def soap(inner: str, path: str = "/onvif/device_service") -> requests.Response:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
            f"<s:Body>{inner}</s:Body></s:Envelope>"
        )
        return requests.post(
            f"http://127.0.0.1:{ONVIF_PORT}{path}",
            data=body.encode(),
            headers=soap_headers,
            auth=onvif_auth,
            timeout=12,
        )

    device = soap("<GetDeviceInformation/>").text
    check("Manufacturer" in device, "ONVIF 设备信息")
    topics = soap("<GetEventProperties/>", "/onvif/events_service").text
    check("CellMotionDetector" in topics, "ONVIF 事件主题集")

    sub = soap("<CreatePullPointSubscription/>", "/onvif/events_service")
    match = re.search(r"<wsa:Address>(.*?)</wsa:Address>", sub.text)
    check(bool(match), "PullPoint 订阅创建")
    if match:
        reference = re.sub(r"^http://[^/]+", f"http://127.0.0.1:{ONVIF_PORT}", match.group(1))
        requests.post(f"{BASE}/api/v2/cameras/{CAMERA_ID}/test-event", headers=headers, timeout=10)
        time.sleep(1.0)
        try:
            pull = requests.post(
                reference,
                data=(
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>'
                    "<PullMessages><Timeout>PT3S</Timeout><MessageLimit>10</MessageLimit></PullMessages>"
                    "</s:Body></s:Envelope>"
                ),
                headers=soap_headers,
                auth=onvif_auth,
                timeout=12,
            )
            check("IsMotion" in pull.text or "NotificationMessage" in pull.text, "PullPoint 事件下发")
        except requests.RequestException as exc:
            check(False, f"PullPoint 拉取失败: {exc}")

    snapshot = requests.get(f"http://127.0.0.1:{ONVIF_PORT}/onvif/snapshot", auth=onvif_auth, timeout=15)
    check(snapshot.status_code == 200 and len(snapshot.content) > 5000, f"ONVIF 快照 {len(snapshot.content)} 字节")

    # 叠加流（可选）
    camera_config = camera.get("config", {}) if camera else {}
    overlay_path = camera.get("overlay", {}).get("path") or camera_config.get("overlay", {}).get("paths")
    if overlay_path and camera and camera.get("status") == "running":
        rtsp_port = info["ports"]["rtsp"]
        try:
            result = subprocess.run(
                [FFPROBE, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
                 "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height",
                 "-of", "csv", "-i", f"rtsp://127.0.0.1:{rtsp_port}/{overlay_path}"],
                capture_output=True, text=True, timeout=25,
            )
            check("h264" in result.stdout or "hevc" in result.stdout, f"叠加流可播放: {result.stdout.strip()}")
        except (OSError, subprocess.SubprocessError) as exc:
            check(False, f"叠加流探测失败: {exc}")

    # 静态资源
    index = requests.get(f"{BASE}/", timeout=10)
    check(index.status_code == 200 and "程星 ONVIF" in index.text, "Web 首页")
    css = requests.get(f"{BASE}/assets/app.css", timeout=10)
    check(css.status_code == 200 and len(css.content) > 5000, "Web 样式")
    js = requests.get(f"{BASE}/assets/js/app.js", timeout=10)
    check(js.status_code == 200 and "function boot" in js.text, "Web 脚本")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} 项失败")
        for item in FAILURES:
            print("  -", item)
        return 1
    print("全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
