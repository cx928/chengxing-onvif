# 更新日志 / Changelog

## v1.0.1 — 2026-10

修复多实例抢占端口导致的登录串台、MediaMTX 反复重启与双重自启问题。

### 修复

* **单实例保护**：启动时检测同一端口是否已有程星 ONVIF，存在则复用并打开浏览器，不再启动第二个进程
* **Windows 端口复用**：Web 服务禁用 `SO_REUSEADDR`，避免两个引擎绑定同一端口
* **双栈端口检测**：`port_free` 同时检查 IPv4 与 IPv6，修复 MediaMTX 双栈监听被漏判的问题
* **MediaMTX 归属校验**：启动后校验 RTSP 端口归属进程，被占用时明确报错，不再误报“已启动”
* **自启去重**：安装开机计划任务时移除登录 Run 键；卸载自启时同时清理两者

### 新增

* 安装包内置 **YOLO26n ONNX** 模型（与 YOLO11n 并存），安装版默认使用 YOLO26n 推理
* MSI 版本号升至 1.0.1，可直接覆盖升级 1.0.0

### 说明

* 已安装 1.0.0 的用户建议直接安装 1.0.1（同 UpgradeCode，自动升级）
* 1.0.0 安装包仍保留在 Releases 中，但存在上述多实例问题，不建议继续使用

## v1.0.0 — 2026-06

首个公开版本（品牌：**程星 ONVIF / ChengXing ONVIF**）。

### 新增

**安装包**

* Windows MSI 安装包（WiX 3.14）：内置 Python 3.12、FFmpeg、MediaMTX、ONNX Runtime、YOLO11n ONNX 模型与 WinUI 桌面控制台
* 便携 ZIP（免安装）：解压即用，内置静默启动/控制台启动脚本与 AI 组件安装脚本
* 开始菜单 / 桌面快捷方式、登录自启、静默安装与卸载
* 打包脚本 `packaging/build-installers.ps1` 可一键复现

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
