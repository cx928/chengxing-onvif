# 硬件加速

程星 ONVIF 在启动时探测：显卡、可用编码器（真机实测）、推理后端与设备，
并据此给出推荐项。所有结果可在「硬件加速」页查看，也可通过
`GET /api/v2/hardware` 获取。

## 1. 探测内容

* 显卡列表（厂商、类型、驱动、显存）
  * Windows：`EnumDisplayDevices`（真实显示适配器，过滤虚拟显卡）
  * Linux：`lspci`
  * macOS：`system_profiler`
  * NVIDIA 额外读取 `nvidia-smi`（显存/驱动）
* 编码器：`ffmpeg -encoders` + 每个候选编码器 **2 帧实测**
  （避免“编译了但驱动不可用”的误判）
* 解码加速：`ffmpeg -hwaccels`
* 推理后端：ONNX Runtime providers、OpenVINO 设备、PyTorch CUDA / DirectML / XPU

结果缓存于 `cache/hw_profile.json`，默认 1 小时；可在页面点「重新探测」。

## 2. 编码器矩阵

| 编码器 | 平台 | 硬件 |
| --- | --- | --- |
| `h264_qsv` / `hevc_qsv` | Windows / Linux | Intel 核显、Intel Arc |
| `h264_nvenc` / `hevc_nvenc` | Windows / Linux | NVIDIA GTX/RTX/Quadro |
| `h264_amf` / `hevc_amf` | Windows | AMD Radeon |
| `h264_vaapi` / `hevc_vaapi` | Linux | Intel / AMD（`/dev/dri`） |
| `h264_videotoolbox` / `hevc_videotoolbox` | macOS | Apple Silicon / Intel Mac |
| `h264_mf` | Windows | Media Foundation 兜底 |
| `libx264` | 全平台 | CPU 软件编码 |

选择顺序：用户指定 → 独显厂商 → 核显 → 通用硬件 → `libx264`。
运行期若硬件编码器初始化失败，会自动降级到 `libx264`，不会中断叠加流。

### 让编码器可用

* **Intel QSV**：安装最新核显驱动（Intel Graphics Driver），FFmpeg 需带 `libvpl`；
  项目中提供的 gyan.dev 构建已包含。
  * 部分老平台需要在 BIOS 开启核显，并使用 `-init_hw_device qsv`（本项目自动处理）。
* **NVIDIA NVENC**：安装 NVIDIA 驱动（含 NVENC），FFmpeg 需带 `--enable-nvenc`。
  桌面版 GTX/RTX 消费卡对并发 NVENC 会话有限制。
* **AMD AMF**：安装 AMD Adrenalin 驱动；Windows 可用，Linux 建议用 VAAPI。
* **VAAPI**：确保当前用户对 `/dev/dri/renderD128` 有权限（加入 `render` 组）。

## 3. 推理加速

| 硬件 | 推荐 | 安装 |
| --- | --- | --- |
| Intel 核显 / Arc / NPU | OpenVINO | `pip install openvino` |
| Intel（通用） | ONNX Runtime DirectML | `pip install onnxruntime-directml` |
| NVIDIA | ONNX Runtime CUDA / TensorRT | `pip install onnxruntime-gpu` |
| AMD | ONNX Runtime DirectML（Windows） | `pip install onnxruntime-directml` |
| AMD（Linux） | ROCm / MIGraphX | 使用 ROCm 版运行时 |
| Apple | PyTorch MPS / CoreML | `pip install ultralytics` |

> CPU 推理完全可用：i5-12400 上 YOLO11n 约 170ms/帧（约 6 FPS），
> 配合运动门控单路 1080p 场景足够。

## 4. 解码加速

默认使用**软件解码**（兼容性最好）。可在「系统设置 → 硬件解码」显式选择：

* `qsv`（Intel）：部分 H.264 码流需要特定 profile，失败会自动回退软件
* `cuda`（NVIDIA）
* `d3d11va`（Windows 通用）
* `vaapi`（Linux）

解码失败时帧源会自动去掉 `-hwaccel` 重试，并在日志中提示。

## 5. 叠加推流的资源占用

```
RTSP 源 ──解码──► 帧（1280×720 @10fps）
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   AI 检测（5fps）         绘制检测框
                                │
                                ▼
                     硬件编码（QSV/NVENC/AMF）
                                │
                                ▼
                 RTSP: <路径>_overlay（供 NVR）
```

* 单路 720p@10fps + QSV：CPU 占用通常 < 10%（i5 级）
* 叠加分辨率：`overlay.width/height`，默认 1280×720；越高越吃资源
* 叠加帧率：`overlay.fps`，默认 10；NVR 录像 10–15 FPS 已足够
* 码率：`overlay.bitrate`，默认 2000 kbps

## 6. 排查

| 现象 | 处理 |
| --- | --- |
| 硬件编码器显示“不可用” | 更新显卡驱动；确认 FFmpeg 构建包含该编码器；查看实测错误 |
| 叠加流卡顿 | 降低叠加分辨率/帧率/码率；关闭转码；检查 CPU 与磁盘 |
| 推理仍是 CPU | 确认已安装对应运行时，且设备选择不是 `cpu`；OpenVINO 需先导出 IR |
| DirectML 报错 | 更新显卡驱动；DirectML 对算子有限制，改用 OpenVINO / CUDA |
| QSV 初始化失败 | 确认显示器接在核显或核显已启用；更新 Intel 驱动 |
