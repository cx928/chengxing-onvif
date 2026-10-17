# 更新日志 / Changelog

## v1.0.0 — 2026-06

首个公开版本（品牌：**程星 ONVIF / ChengXing ONVIF**）。

### 新增

**引擎**

* ONVIF 虚拟摄像机：设备 / 媒体 / 事件服务、WS-Discovery、多码流 Profile、快照、PullPoint 订阅
* MediaMTX 集成：自动下载、配置生成、鉴权回调、原始流 / 叠加流 / WebRTC / HLS
* 每路摄像机独立 ONVIF 端口与凭据

**检测**

* 多模型：YOLO26 / YOLO11 / YOLOv8 / YOLOv10 / YOLO12 / RT-DETR / YOLO-World
* 多格式：PyTorch `.pt`、ONNX `.onnx`、OpenVINO IR `.xml`、自定义模型目录
* 推理后端：Ultralytics、ONNX Runtime（CPU / CUDA / TensorRT / DirectML / OpenVINO EP）、OpenVINO
* 运动门控、IoU 跟踪、区域规则（包含 / 排除）、目标分组、事件冷却
* 模型库一键下载、后台导出 ONNX / OpenVINO

**水星安防模拟**

* 厂商画像：MERCURY、TP-LINK VIGI、海康、大华、宇视、UniFi、通用
* 设备身份、URI 作用域、事件主题集、规则与数据项均按画像生成
* ONVIF 事件：移动、移动报警、人形、车辆、区域入侵、越界、动物、物品
* HTTP 主动推送：通用 JSON、大华、海康、水星/TP-LINK、表单

**叠加输出**

* 检测框、中文标签、置信度、时间戳、自定义文字、区域绘制
* 独立 RTSP 叠加流：`<路径>_overlay`
* 硬件编码：Intel QSV、NVIDIA NVENC、AMD AMF、VAAPI、VideoToolbox、libx264，失败自动降级

**硬件加速**

* GPU 探测（Windows / Linux / macOS）
* 编码器逐个实测与缓存
* 推理后端与设备自动推荐

**部署**

* Windows 计划任务（SYSTEM，开机静默）/ 启动文件夹
* systemd / launchd
* `install.ps1` / `install.sh` 一键安装
* Dockerfile 与 docker-compose

**界面**

* 纯网页控制台：概览、摄像机、检测事件、模型库、硬件加速、系统设置、关于
* WinUI 3 桌面控制台：启动/停止/重启引擎、修改密码、开机自启、打开 Web

**文档与测试**

* 快速上手、水星对接、模型、硬件加速、API、架构、排障、桌面端
* 27 个单元测试 + 端到端冒烟测试脚本

### 已知限制

* WinUI 桌面端已完成编译与自包含发布，但未做长时间 GUI 交互测试
* 第三方 NVR 对非本品牌摄像机的智能事件支持存在差异，详见 `docs/MERCURY.md`
* 浏览器无法直接播放 H.265，网页预览建议 H.264 或开启转码
* 暂无移动端 App
