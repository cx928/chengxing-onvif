# 架构说明

## 1. 总体结构

```
┌──────────────────────────────────────────────────────────────────┐
│                        Web 控制台 / WinUI 桌面端                  │
│                    HTTP + SSE（REST API v2）                      │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│                         cxonvif 引擎                              │
│                                                                  │
│  CameraManager ──► VirtualCamera × N                              │
│      │                 ├── ONVIFService（设备/媒体/事件）          │
│      │                 ├── FrameSource（FFmpeg 解码）             │
│      │                 ├── AnalyticsPipeline（检测）              │
│      │                 ├── OverlayStream（绘制 + 硬件编码）        │
│      │                 └── MercuryEmulator（事件模拟 + 推送）      │
│      │                                                            │
│      ├── MediaMTXManager（RTSP/WebRTC/HLS 服务）                  │
│      ├── HardwareProfile（GPU / 编码器 / 推理后端）               │
│      └── EventBus（SSE 实时事件）                                 │
└──────────────────────────────────────────────────────────────────┘
```

## 2. 数据流

### 2.1 视频

```
摄像机 RTSP
   │  FFmpeg 解码（可选硬件加速）
   ▼
FrameSource ──最新帧──┬──► AnalyticsPipeline（运动门控 → 推理 → 跟踪 → 区域）
   │                  │
   │                  └──► OverlayStream（绘制检测框 → 硬件编码）
   │                              │
   └──► MediaMTX ◄────────────────┘
          ├── /<路径>_main     （原始流，on-demand 拉源）
          ├── /<路径>_sub      （子码流，可选）
          └── /<路径>_overlay  （叠加流，由引擎推流）
```

* 每路摄像机只解码一次，检测与叠加共享帧；
* MediaMTX 对原始流采用 `sourceOnDemand`，无人观看时不拉流；
* 叠加流由引擎主动推送（`-f rtsp`），即使无人观看也持续编码（便于 NVR 稳定录像）。

### 2.2 事件

```
检测结果 ──► 目标组状态机（激活/结束 + 冷却）
                 │
                 ├──► MercuryEmulator.build_events()
                 │        ├── ONVIF 主题（按厂商画像）
                 │        │      └── 推入每个 PullPoint 订阅队列
                 │        └── HTTP 推送（可选，多种格式）
                 │
                 └──► EventBus → SSE → 网页 / 桌面端
```

## 3. 线程模型

| 线程 | 数量 | 职责 |
| --- | --- | --- |
| Web（Werkzeug） | 1 + 请求线程 | REST API、静态资源、SSE |
| ONVIF 服务 | 每路 1 | 独立端口的 SOAP 服务 |
| WS-Discovery | 每路 1 | UDP 3702 响应 Probe |
| FrameSource | 每路 1 | FFmpeg 解码、断线重连 |
| AnalyticsPipeline | 每路 1 | 推理与事件状态机 |
| OverlayStream | 每路 1 | 绘制与编码管道 |
| Mercury 心跳 | 每路 1 | 刷新订阅活跃时间 |
| MediaMTX | 进程 | RTSP/WebRTC/HLS |

所有线程均为 daemon，服务停止时按顺序 shutdown（带超时兜底）。

## 4. 模块职责

| 模块 | 说明 |
| --- | --- |
| `cxonvif/config.py` | 数据模型（dataclass）+ 原子持久化 + 旧配置导入 |
| `cxonvif/hw/` | FFmpeg 定位、GPU/编码器/推理探测、编码参数 |
| `cxonvif/detect/` | 模型注册表、后端、后处理、跟踪、区域、叠加、管线 |
| `cxonvif/stream/` | 帧源、MediaMTX 进程与配置、叠加推流 |
| `cxonvif/onvif/` | SOAP 服务、厂商画像、场景事件主题 |
| `cxonvif/emulate/` | 水星事件模拟、HTTP 推送 |
| `cxonvif/api/` | Flask 应用、鉴权、任务、REST 路由 |
| `cxonvif/core/` | 摄像机运行时、管理器、自启、服务循环 |

## 5. 扩展点

### 新增检测后端

实现 `cxonvif.detect.base.Detector`：

```python
class MyDetector(Detector):
    backend = "mybackend"
    display_name = "My Backend"

    def load(self): ...
    def infer(self, frame, *, confidence, iou) -> list[Detection]: ...
```

在 `create_detector()` 中注册分支即可。

### 新增厂商画像

在 `cxonvif/onvif/profiles.py` 中 `_register(VendorProfile(...))`，
指定身份字段与 `TopicDef` 列表；Web 端会自动出现在画像下拉框。

### 新增推送格式

在 `cxonvif/emulate/push.py` 的 `build_payload()` 中增加分支，
返回 `(body, content_type, headers)`。

### 新增 API

在 `cxonvif/api/routes.py` 添加路由，使用 `@login_required` 保护。

## 6. 存储

```
<数据目录>/
  config.json        配置（含相机、设置、密码哈希）
  config.json.bak    上次写入的备份
  models/            模型文件（.pt/.onnx/.xml）
  snapshots/         事件截图（自动保留最近 400 张）
  cache/             硬件画像缓存
  logs/              cxonvif.log、mediamtx.log
  mediamtx.yml       由引擎生成
```

写入采用「临时文件 + fsync + 原子替换」，避免断电损坏。

## 7. 安全

* 管理员密码使用 PBKDF2-HMAC-SHA256（260k 次）+ 随机盐；
* 登录令牌为随机 32 字节，内存会话，默认 24 小时过期；
* 登录失败限速（8 次 / 5 分钟，锁定 2 分钟）；
* MediaMTX 鉴权回调：允许本机推流，读取按设置决定是否校验 RTSP 凭据；
* ONVIF 使用 Basic / WS-UsernameToken（Digest）；
* 网页默认仅暴露必要接口，SSE 使用一次性查询令牌。

> 默认仅建议部署在可信内网；如需公网访问，请置于反向代理与 HTTPS 之后。

## 8. 兼容性

* Python 3.10–3.14（Windows / Linux / macOS）
* MediaMTX v1.18+
* FFmpeg 6.0+（建议 7/8，需包含所需编码器）
* 浏览器：Edge / Chrome / Safari 最新版（WebRTC 预览）
