# 程星 ONVIF · REST API v2

所有接口以 `/api/v2` 为前缀，返回 JSON：`{"ok": true, "data": ...}` 或 `{"ok": false, "error": "..."}`。
除 `health`、`auth/*`、`internal/*` 外，需要请求头 `Authorization: Bearer <token>`。
首次启动默认账号 `admin` / `cx123456`（登录后强制改密）。

## 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/auth/state` | 登录状态、是否需要改密 |
| POST | `/auth/login` | `{username,password}` → `{token,expires,mustChangePassword}` |
| POST | `/auth/logout` | 注销当前令牌 |
| GET | `/auth/session` | 当前会话 |
| POST | `/auth/password` | `{currentPassword,newPassword}` |

## 系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 无需登录，返回版本/运行状态 |
| GET | `/system/info` | 品牌、版本、端口、硬件、链接 |
| GET | `/system/status` | 摄像机运行状态 + MediaMTX 状态 |
| GET | `/system/settings` | 设置 + 认证信息 |
| PUT | `/system/settings` | 更新设置，返回 `restartRequired` |
| GET | `/system/logs?limit=300&level=INFO` | 日志尾部 |
| GET | `/system/events?since=0` | 事件增量 |
| GET | `/system/events/stream?token=...` | SSE 实时事件流 |
| POST | `/system/restart` | 重启服务 |
| POST | `/system/shutdown` | 停止服务 |
| GET | `/system/config/export` | 导出完整配置 JSON |
| POST | `/import/tonys` | `{path}` 导入旧版配置 |

## 摄像机

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/cameras` | 列表（含运行状态） |
| POST | `/cameras` | 新建（body 见下） |
| GET | `/cameras/{id}` | 详情 |
| PUT | `/cameras/{id}` | 修改并自动重启 |
| DELETE | `/cameras/{id}` | 删除 |
| POST | `/cameras/{id}/start` | 启动 |
| POST | `/cameras/{id}/stop` | 停止 |
| POST | `/cameras/{id}/restart` | 重启 |
| POST | `/cameras/{id}/test-event` | 触发一次模拟检测事件（ONVIF + 推送） |
| POST | `/cameras/{id}/push-test` | 单独测试 HTTP 推送 |
| GET | `/cameras/{id}/snapshot` | 当前 JPEG 画面 |
| GET | `/cameras/{id}/events` | 该摄像机最近事件 |
| POST | `/probe` | `{url}` 探测 RTSP 流 |
| GET | `/probe/templates?host=` | 各品牌常见 RTSP 地址模板 |

摄像机 body 主要字段：

```json
{
  "name": "前门",
  "enabled": true,
  "autoStart": true,
  "pathName": "cam1_qianmen",
  "source": {
    "mainUrl": "rtsp://user:pass@192.168.1.10:554/Streaming/Channels/101",
    "subUrl": "",
    "mainWidth": 1920, "mainHeight": 1080, "mainFramerate": 25,
    "subWidth": 640, "subHeight": 480, "subFramerate": 15,
    "transport": "tcp"
  },
  "onvif": {
    "enabled": true, "port": 8001, "username": "admin", "password": "******",
    "profile": "mercury", "wsDiscovery": true, "sendMotion": true, "sendSmart": true
  },
  "detect": {
    "enabled": true, "model": "yolo11n", "backend": "auto", "device": "auto",
    "confidence": 0.45, "fps": 5, "targets": ["person", "vehicle"],
    "motionGate": true, "motionSensitivity": 55, "cooldown": 5,
    "zones": [{"id":"z1","name":"门廊","type":"include","points":[[0.1,0.2],[0.8,0.2],[0.8,0.9]]}]
  },
  "overlay": {
    "enabled": true, "width": 1280, "height": 720, "fps": 10,
    "encoder": "auto", "bitrate": 2000, "showLabels": true
  },
  "mercury": {
    "enabled": true, "pushEnabled": false, "pushUrl": "",
    "pushFormat": "json", "includeSnapshot": true
  }
}
```

## 模型与硬件

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/models` | 内置模型注册表 + 本机自定义模型 + 推理后端 |
| POST | `/models/{key}/download` | 后台任务下载 |
| DELETE | `/models/{key}` | 删除模型文件 |
| POST | `/models/{key}/export` | `{format:"onnx"\|"openvino"}` 后台导出 |
| GET | `/jobs` / `/jobs/{id}` | 后台任务进度 |
| GET | `/hardware` | GPU、编码器、推理后端、推荐项 |
| POST | `/hardware/refresh` | 重新探测（后台任务） |
| GET | `/onvif/profiles` | 厂商画像列表 |

## 内部接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/internal/mediamtx/auth` | MediaMTX 鉴权回调（仅本机） |
