# 程星 ONVIF v1.0.1

修复 **多实例抢占端口** 导致的登录串台、MediaMTX 反复重启与双重自启问题，并内置 **YOLO26n ONNX** 模型。

## 修复

* **单实例保护**：启动时检测同端口是否已有程星 ONVIF，存在则复用并打开浏览器，不再启动第二个进程
* **Windows 端口复用**：Web 服务禁用 `SO_REUSEADDR`，避免两个引擎绑定同一端口
* **双栈端口检测**：同时检查 IPv4 / IPv6，修复 MediaMTX 双栈监听被漏判的问题
* **MediaMTX 归属校验**：启动后校验 RTSP 端口归属进程，被占用时明确报错，不再误报“已启动”
* **自启去重**：安装开机计划任务时移除登录 Run 键，卸载时同时清理两者

## 下载

| 安装包 | 大小 | 链接 |
| --- | --- | --- |
| **MSI 安装版** | 220.5 MB | [ChengXing-ONVIF-1.0.1-x64.msi](https://github.com/cx928/chengxing-onvif/releases/download/v1.0.1/ChengXing-ONVIF-1.0.1-x64.msi) |
| **便携 ZIP** | 262.8 MB | [ChengXing-ONVIF-1.0.1-portable-win-x64.zip](https://github.com/cx928/chengxing-onvif/releases/download/v1.0.1/ChengXing-ONVIF-1.0.1-portable-win-x64.zip) |
| 校验值 | — | [SHA256SUMS.txt](https://github.com/cx928/chengxing-onvif/releases/download/v1.0.1/SHA256SUMS.txt) |

SHA256：

```text
76061cf6091bc5c54bf13635d3d2fc4b62a5543f7752829170a4cd7f5e03ef8f  ChengXing-ONVIF-1.0.1-x64.msi
7a2bf7f166a0a2900e04b9b8788763cb96ebb69714f7f037a0c699e7bb1a1667  ChengXing-ONVIF-1.0.1-portable-win-x64.zip
```

## 内置组件

* Python 3.12 运行时、FFmpeg 8.1、MediaMTX 1.18、ONNX Runtime 1.31
* **YOLO26n ONNX**（默认检测模型）与 YOLO11n ONNX（备用）
* WinUI 3 桌面控制台（自包含）
* 网页控制台与完整文档

## 升级说明

* 1.0.1 与 1.0.0 使用相同 UpgradeCode，**可直接覆盖安装升级**，配置与数据保留
* 已安装 1.0.0 的用户建议升级；1.0.0 存在多实例端口问题
* 安装后 Web 端口默认 `5552`；若旧配置曾被改为其他端口，可在设置中修改或删除配置中的 `settings.webPort`

## 安装

**MSI**：双击安装 → 开始菜单「程星 ONVIF」→ <http://localhost:5552>

**ZIP**：解压 → 双击「启动程星 ONVIF.vbs」

* 默认账号：`admin`
* 默认密码：`cx123456`（首次登录强制修改）
* 数据目录：`C:\ProgramData\ChengXingOnvif`

## 已知限制

* 本机验证环境为 Intel UHD 730：QSV 编码实测通过；NVENC / AMF / VAAPI 已实现探测与自动降级，未在对应硬件实测
* 第三方 NVR 对非本品牌摄像机的智能事件支持存在差异，可切换设备画像
* 浏览器无法直接播放 H.265，网页预览建议 H.264 或开启转码
* 桌面控制台已完成编译与自包含发布，未做长时间 GUI 交互测试

## 文档

* [快速上手](https://github.com/cx928/chengxing-onvif/blob/main/docs/QUICKSTART.md)
* [水星安防事件模拟](https://github.com/cx928/chengxing-onvif/blob/main/docs/MERCURY.md)
* [模型与推理后端](https://github.com/cx928/chengxing-onvif/blob/main/docs/MODELS.md)
* [硬件加速](https://github.com/cx928/chengxing-onvif/blob/main/docs/ACCELERATION.md)
* [打包说明](https://github.com/cx928/chengxing-onvif/blob/main/packaging/README.md)

---

B 站：<https://space.bilibili.com/1765875510> · GitHub：<https://github.com/cx928> · 邮箱：wanghaotian@cxdx.edu.kg

