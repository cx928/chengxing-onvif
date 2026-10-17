# 安装包构建 / Packaging

本目录用于把程星 ONVIF 打包成 **便携 ZIP** 与 **MSI 安装包**。

## 产物

| 产物 | 说明 |
| --- | --- |
| `build\ChengXing-ONVIF-<版本>-portable-win-x64.zip` | 免安装便携版，解压即用（内置 Python 3.12、FFmpeg、MediaMTX、ONNX 模型、桌面控制台） |
| `build\msi\ChengXing-ONVIF-<版本>-x64.msi` | 系统安装包，安装到 `C:\Program Files\ChengXing ONVIF`，含开始菜单/桌面快捷方式与登录自启 |

两者内容一致：

```
app\        引擎源码 + 网页控制台 + FFmpeg + MediaMTX + models\yolo11n.onnx
python\     嵌入式 Python 3.12（flask / numpy / opencv / onnxruntime）
desktop\    WinUI 3 桌面控制台（自包含）
```

## 一键构建

```powershell
# 1) 准备依赖（任选其一）
#    - 把 ffmpeg.exe / ffprobe.exe 放到 vendor\ffmpeg\
#    - 把 mediamtx.exe 放到 vendor\mediamtx\
#    - 桌面端先发布：desktop\CXOnvif.Desktop\build.ps1  → desktop\dist

# 2) 构建
powershell -ExecutionPolicy Bypass -File .\packaging\build-installers.ps1
```

参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-Version` | `1.0.1` | 包版本号 |
| `-PythonVersion` | `3.12.10` | 嵌入式 Python 版本 |
| `-PipIndex` | 清华镜像 | pip 源，可改为官方或其他镜像 |
| `-NoMsi` / `-NoZip` | 否 | 只构建其中一种 |
| `-ReusePython` | 否 | 复用已有 `build\pkg\...\python`，加快二次构建 |

脚本会自动下载：嵌入式 Python、get-pip、运行依赖、YOLO11n ONNX 模型、WiX 3.14（仅 MSI）。

## MSI 说明

* 安装目录：`C:\Program Files\ChengXing ONVIF`
* 数据目录：`C:\ProgramData\ChengXingOnvif`
* 开始菜单：启动 / 桌面控制台 / 静默启动 / 使用说明 / 卸载
* 桌面快捷方式：启动并打开网页控制台
* 登录自启：写入 `HKLM\Software\Microsoft\Windows\CurrentVersion\Run`（`-m cxonvif serve --silent`）
  需要**开机级**自启时，在网页「系统设置 → 开机自启」或运行：
  `python\python.exe -m cxonvif autostart install`（创建 SYSTEM 计划任务）
* 卸载：控制面板 → 程序和功能 → 程星 ONVIF；卸载时移除快捷方式与自启项，数据目录保留

### 静默安装 / 卸载

```powershell
msiexec /i ChengXing-ONVIF-1.0.1-x64.msi /qn
msiexec /x ChengXing-ONVIF-1.0.1-x64.msi /qn
```

### 自定义安装目录

```powershell
msiexec /i ChengXing-ONVIF-1.0.1-x64.msi INSTALLDIR="D:\Apps\ChengXing ONVIF" /qn
```

## 便携版说明

解压后双击「启动程星 ONVIF.vbs」即可（静默启动并打开浏览器）。
详见包内 `使用说明.txt`。

## 文件

```
packaging/
  build-installers.ps1     一键构建脚本
  portable/                便携版启动脚本与说明
  msi/Product.wxs          MSI 定义（目录、快捷方式、自启、ARP）
  msi/license.rtf          安装向导中的许可页
```

