# 快速上手（5 分钟）

## 1. 安装

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithAI
```

Linux / macOS：

```bash
sudo ./install.sh --with-ai
```

只想先看看界面、不跑 AI？去掉 `-WithAI` / `--with-ai` 即可，之后可在网页里按需安装。

## 2. 启动

```powershell
.\start.ps1
```

浏览器打开 <http://localhost:5552>。

* 默认账号：`admin`
* 默认密码：`cx123456`
* 首次登录会强制修改密码

## 3. 添加摄像机

1. 进入 **摄像机 → 添加摄像机**
2. 名称随意，主码流填摄像机的 RTSP 地址：
   * 海康 `rtsp://admin:密码@192.168.1.64:554/Streaming/Channels/101`
   * 大华 `rtsp://admin:密码@192.168.1.65:554/cam/realmonitor?channel=1&subtype=0`
   * 水星 / TP-LINK `rtsp://admin:密码@192.168.1.66:554/stream1`
   * 通用 `rtsp://admin:密码@IP:554/`
3. 点「探测」，确认分辨率自动回填
4. 切到 **AI 检测**：选择模型（首次会提示下载）、勾选目标（人形/车辆）、保存
5. 回到列表，点「启动」；卡片出现画面即成功

> 没有真实摄像机？可以把 `AI 检测 → 推理后端` 改成「模拟检测器」，用任意测试流体验完整流程。

## 4. 让录像机接入

在 NVR / VMS 中「手动添加 ONVIF 设备」：

| 字段 | 值 |
| --- | --- |
| IP | 运行程星 ONVIF 的电脑局域网 IP |
| 端口 | 摄像机卡片显示的 `ONVIF :8061` 等 |
| 用户名 | 摄像机编辑页的 ONVIF 用户名（默认 `admin`） |
| 密码 | 摄像机编辑页的 ONVIF 密码 |

也可以在 NVR 里直接添加 RTSP：

```
rtsp://<IP>:8554/<路径>_main      # 原始画面
rtsp://<IP>:8554/<路径>_overlay   # 带检测框的画面
```

## 5. 验证检测事件

1. 摄像机编辑 → **ONVIF / 水星**
2. 设备画像选 **水星安防 MERCURY**
3. 打开「上报移动事件」「上报人形/车辆等智能事件」
4. 保存 → 点「发送测试事件」
5. 在 **检测事件** 页应看到一条事件；NVR 端应收到报警

## 6. 开机自启

网页：**系统设置 → 开机自启 → 启用**（推荐管理员身份，创建 SYSTEM 计划任务）。

命令行：

```powershell
.\.venv\Scripts\python.exe -m cxonvif autostart install
```

## 7. 端口与防火墙

| 端口 | 协议 | 用途 |
| --- | --- | --- |
| 5552 | TCP | Web 控制台 / REST API |
| 8554 | TCP | RTSP 输出（主/子/叠加流） |
| 8001+ | TCP | ONVIF 虚拟摄像机（每路一个） |
| 3702 | UDP | WS-Discovery 自动发现 |
| 8888 | TCP | HLS |
| 8889 | TCP | WebRTC（网页预览） |
| 8189 | UDP | WebRTC ICE |

Windows 首次启动会弹出防火墙提示，请勾选「专用网络」并允许。

## 下一步

* [水星安防事件模拟](MERCURY.md)
* [模型与推理后端](MODELS.md)
* [硬件加速](ACCELERATION.md)
* [常见问题](TROUBLESHOOTING.md)
