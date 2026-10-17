# 常见问题排查

## 安装与启动

### 提示“未找到 Python 3.10+”

安装 Python 3.12（勾选 Add to PATH），或指定解释器：

```powershell
.\install.ps1 -PythonExe "C:\Python312\python.exe"
```

### `python -m cxonvif` 报 `ModuleNotFoundError`

确认在项目根目录执行，或已 `pip install -e .`。使用虚拟环境时：

```powershell
.\.venv\Scripts\python.exe -m cxonvif serve
```

### 端口被占用

```powershell
netstat -ano | findstr :5552
```

修改端口：

```powershell
python -m cxonvif serve --port 5560
```

或编辑数据目录 `config.json` 的 `settings.webPort` / `rtspPort` / `onvifPortStart`。

### MediaMTX 下载失败

网络受限时手动下载：
<https://github.com/bluenviron/mediamtx/releases> → 解压 `mediamtx.exe` 到
`vendor/mediamtx/mediamtx.exe`，或在「系统设置」填写 `MediaMTX 路径`。

### FFmpeg 未找到

* Windows：`vendor/ffmpeg/ffmpeg.exe`
* Linux/macOS：`which ffmpeg`
* 或在设置中填写 FFmpeg 路径

检查：

```bash
python -m cxonvif doctor
```

## 摄像机与预览

### 卡片一直“启动中”或没有画面

1. 打开日志：系统设置 → 维护 → 日志
2. 用 `python -m cxonvif probe rtsp://...` 验证源地址
3. 检查用户名密码、编码格式（H.264）、RTSP 端口
4. 部分摄像机限制并发连接，先关闭其他客户端

### 网页预览黑屏，但 NVR 正常

H.265 浏览器无法直接播放。改为 H.264，或在摄像机「高级」中开启转码。
也可在卡片上查看快照（自动回退）。

### WebRTC 预览失败

* 确认 8889/TCP 与 8189/UDP 未被防火墙拦截
* 通过局域网 IP 访问（不要用被代理的域名）
* 反向代理/HTTPS 场景下，WebRTC 需要额外配置，建议直接访问端口

### 叠加流没有画面

```bash
ffplay rtsp://127.0.0.1:8554/<路径>_overlay
```

* 确认「叠加输出」已开启且摄像机运行
* 查看「硬件加速」页编码器是否可用；失败会自动降级 libx264
* 检查磁盘与 CPU（编码管道阻塞会体现为 fps=0）

## 录像机 / ONVIF

### NVR 搜索不到设备

* 防火墙放行 TCP 5552/8554/8001+ 与 UDP 3702
* 摄像机与 NVR 是否同网段
* 虚拟机需开启混杂模式
* 手动添加：`http://<IP>:<ONVIF端口>/onvif/device_service`

### NVR 添加成功但无画面

* 用 `ffplay rtsp://<IP>:8554/<路径>_main` 验证
* 若开启 RTSP 认证，NVR 中要填写相同用户名密码
* 检查 MediaMTX 日志（`logs/mediamtx.log`）

### 事件不上报

* 摄像机编辑 → ONVIF / 水星：确认「上报移动事件」与「上报人形/车辆」已开启
* 点「发送测试事件」，在「检测事件」页是否出现
* 用 ODM 订阅 PullPoint 验证（见 [MERCURY.md](MERCURY.md)）
* 第三方 NVR 可能不支持智能事件，切换画像或只用移动事件

### ONVIF 认证失败

* 确认输入的是该摄像机的 ONVIF 密码（不是网页管理员密码）
* 修改密码后需要重启该摄像机
* 某些 NVR 只支持 Basic 认证，已兼容

## AI 检测

### 检测器加载失败

* 模型未下载：模型库点「下载」
* 未安装 ultralytics / torch：`pip install ultralytics`
* ONNX 模型但未安装 onnxruntime：`pip install onnxruntime`
* 查看摄像机检测状态里的 `lastError`

### 一直检测不到

* 目标是否在 `targets` 中（人形/车辆/动物/物品）
* 置信度太高：降到 0.35 试试
* 区域（zone）是否把目标排除了
* 运动门控灵敏度太低：调高或关闭门控
* 夜间画面质量差：使用更大模型或红外模式

### 事件太频繁 / 误报

* 提高置信度（0.5–0.6）
* 缩短/开启区域限制
* 增大事件冷却（5–10 秒）
* 使用 `yolov8n-human` 专用人形模型

### 推理太慢

* 降低检测 FPS（3–5）
* 降低分析宽度（默认 960）
* 使用 GPU 后端（OpenVINO / CUDA / DirectML）
* 开启运动门控

## 开机自启

### Windows 自启无效

```powershell
python -m cxonvif autostart status
schtasks /Query /TN ChengXingOnvif /V /FO LIST
```

以管理员身份重新安装：

```powershell
python -m cxonvif autostart install
```

非管理员时只会加入当前用户启动文件夹（登录后启动）。

### 服务启动了但网页打不开

* 查看 `C:\ProgramData\ChengXingOnvif\logs\cxonvif.log`
* 启动用户是否有权限写入数据目录
* 端口是否被占用

## 数据与密码

### 忘记管理员密码

```powershell
python -m cxonvif password 新密码
```

或删除 `config.json` 中的 `auth.passwordHash` / `passwordSalt` 后重启（恢复默认密码）。

### 数据目录在哪

```powershell
python -m cxonvif doctor
```

或查看 `config.json` 所在目录；可用 `CXONVIF_HOME` 自定义。

### 如何备份 / 迁移

系统设置 → 维护 → 「导出配置」，包含全部摄像机与设置（不含模型文件）。
把 `config.json` 与 `models/` 复制到新机器的数据目录即可完整迁移。

## 性能

### CPU 占用高

* 使用硬件编码（QSV/NVENC/AMF）
* 减少叠加路数或降低分辨率/帧率
* 启用运动门控
* 检查是否开启了转码（应仅在 H.265 兼容问题时开启）

### 内存持续增长

* 事件截图过多：自动保留最近 400 张，可手动清理 `snapshots/`
* 长时间运行建议每日重启一次（计划任务）
* 若异常增长，请附日志提交 Issue

## 获取帮助

提交 Issue 时请附上：

1. `python -m cxonvif doctor` 输出
2. `logs/cxonvif.log` 最近 100 行
3. 摄像机配置（隐去密码）
4. NVR 品牌型号与现象

<https://github.com/cx928/chengxing-onvif/issues>
