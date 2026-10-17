# 程星 ONVIF v1.0.0

把任意 RTSP 摄像头变成支持**多模型 AI 检测**的 ONVIF 虚拟摄像机，检测框实时叠加进视频流，并以**水星安防（MERCURY）设备身份**向录像机上报检测事件。

## 下载

| 安装包 | 大小 | 适用 |
| --- | --- | --- |
| [ChengXing-ONVIF-1.0.0-x64.msi](https://github.com/cx928/chengxing-onvif/releases/download/v1.0.0/ChengXing-ONVIF-1.0.0-x64.msi) | 212 MB | Windows 10/11 x64，推荐 |
| [ChengXing-ONVIF-1.0.0-portable-win-x64.zip](https://github.com/cx928/chengxing-onvif/releases/download/v1.0.0/ChengXing-ONVIF-1.0.0-portable-win-x64.zip) | 255 MB | 免安装便携版 |

校验（PowerShell）：

```powershell
Get-FileHash .\ChengXing-ONVIF-1.0.0-x64.msi -Algorithm SHA256
Get-FileHash .\ChengXing-ONVIF-1.0.0-portable-win-x64.zip -Algorithm SHA256
```

```
MSI  : 9b98d74d0049307861275233aede8d1872a34a75a306dbbd82a7f430664d0072
ZIP  : f63050902f29455532ad3e39e1e660f615aaa9f994cffd52eddcdc27824a3e4f
```

## 安装包内置

* Python 3.12 运行时（无需安装 Python）
* FFmpeg 8.1（含 QSV / NVENC / AMF / VAAPI 编码支持）
* MediaMTX 1.18（RTSP / WebRTC / HLS）
* ONNX Runtime 1.31 + YOLO11n ONNX 模型（开箱即可人形/车辆检测，无需 PyTorch）
* WinUI 3 桌面控制台（自包含，无需 .NET 运行时）
* 网页控制台、完整文档

需要 `.pt` 模型（YOLO26/11/8、RT-DETR、YOLO-World）时，运行包内「安装 AI 组件」脚本即可安装 PyTorch + Ultralytics。

## 安装 / 启动

**MSI**：双击安装 → 开始菜单「程星 ONVIF」启动 → 浏览器打开 <http://localhost:5552>

**ZIP**：解压 → 双击「启动程星 ONVIF.vbs」

* 默认账号：`admin`
* 默认密码：`cx123456`（首次登录强制修改）
* 数据目录：`C:\ProgramData\ChengXingOnvif`
* 安装版默认登录自启；可在「系统设置 → 开机自启」改为开机级 SYSTEM 静默启动

## 主要能力

* 多模型：YOLO26 / 11 / 8 / 10 / 12、RT-DETR、YOLO-World、任意 ONNX / OpenVINO、自定义模型
* 水星安防模拟：MERCURY 设备身份、WS-Discovery、PullPoint 事件、HTTP 主动推送
* 检测框叠加：独立 RTSP 流，QSV / NVENC / AMF / VAAPI 硬件编码
* 硬件加速：Intel 核显/独显、NVIDIA、AMD 自动探测与降级
* 双版本：纯网页控制台 + WinUI 3 桌面控制台

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


