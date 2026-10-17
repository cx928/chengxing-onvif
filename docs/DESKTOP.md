# 程星 ONVIF 桌面控制台（desktop/CXOnvif.Desktop）

WinUI 3（Windows App SDK）桌面“遥控器”：启动 / 停止引擎、查看运行状态、管理员登录与改密、开机自启、打开 Web 控制台、关于页。
引擎本身（`cxonvif/` 下的 Python 代码）未被修改，桌面端只通过 REST API v2 与它通信。

- 品牌：程星 ONVIF
- 目标框架：`net8.0-windows10.0.19041.0`，x64
- 打包方式：**unpackaged**（`WindowsPackageType=None`）+ 自包含（`WindowsAppSDKSelfContained=true`、`SelfContained=true`）
- 主界面：单窗口 980×680、`NavigationView` 左侧导航、深色主题、中文界面
- 图标：Segoe Fluent Icons 字形（`\uE...`），不依赖任何图片资源

## 1. 构建环境

本机初始只有 .NET Runtime，没有 SDK。构建环境如下：

| 组件 | 版本 / 位置 |
| --- | --- |
| .NET SDK | **8.0.426**（`C:\Program Files\dotnet\sdk`，`dotnet --version` 已确认） |
| MSBuild | 随 SDK（.NET SDK 自带，无需 Visual Studio） |
| Microsoft.WindowsAppSDK | 1.7.250909003 |
| Microsoft.Windows.SDK.BuildTools | 10.0.26100.4948 |
| Microsoft.Windows.SDK.BuildTools.MSIX | 1.7.260930100（命令行构建必需，见第 6 节） |
| 目标运行时 | win-x64（自包含，输出约 166 MB / 486 个文件） |

SDK 安装方式（`winget` 与 `dotnet-install.ps1` 在本机因网络/代理原因卡死，最终用官方 zip 直装）：

```powershell
# 官方渠道：winget install --id Microsoft.DotNet.SDK.8 -e --accept-source-agreements --accept-package-agreements
# 或：dotnet-install.ps1 -Channel 8.0 -InstallDir "C:\Program Files\dotnet"
# 本机实际采用（curl 直下官方 SDK zip，SHA512 与 releases.json 一致，tar 解压）：
curl.exe -sSL -o C:\Temp\dotnet\dotnet-sdk-8.0.426-win-x64.zip https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.426/dotnet-sdk-8.0.426-win-x64.zip
tar.exe -xf C:\Temp\dotnet\dotnet-sdk-8.0.426-win-x64.zip -C "C:\Program Files\dotnet"
& "C:\Program Files\dotnet\dotnet.exe" --list-sdks   # 8.0.426 [C:\Program Files\dotnet\sdk]
```

## 2. 构建命令

```powershell
cd C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop

# 1) 普通构建（要求 0 error）
dotnet build -c Release

# 2) 一键自包含发布（还原 + publish 到 desktop\dist）
powershell -ExecutionPolicy Bypass -File .\build.ps1
# 可附加：-Configuration Debug / -BuildOnly / -OutputDirectory <目录>
```

> `build.ps1` 会把 `NUGET_CERT_REVOCATION_MODE` 设为 `offline`（本机在线吊销检查会长期挂起，见第 6 节），并检查发布产物是否存在。

## 3. 构建结果（实际执行，0 error 0 warning）

```text
dotnet build -c Release --no-incremental -v n    # 最后 15 行

         正在将文件从“C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\bin\Release\net8.0-windows10.0.19041.0\win-x64\Pages\SecurityPage.xbf”复制到“C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\embed\Pages\SecurityPage.xbf”。
       _GenerateProjectPriFileCore:
         C:\Users\Administrator\.nuget\packages\microsoft.windows.sdk.buildtools\10.0.26100.4948\bin\10.0.26100.0\x64\makepri.exe New -ProjectRoot "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\\" -ConfigXml "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\priconfig.xml" -OutputFile "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\bin\Release\net8.0-windows10.0.19041.0\win-x64\CXOnvif.Desktop.pri" -IndexName CXOnvif.Desktop -Verbose -Overwrite
       _ExpandPriFiles:
         C:\Users\Administrator\.nuget\packages\microsoft.windows.sdk.buildtools\10.0.26100.4948\bin\10.0.26100.0\x64\makepri.exe Dump -IndexFile "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\MsixContent\Microsoft.UI.pri" -OutputFile "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\Microsoft.UI.pri.xml" -Verbose -Overwrite
         C:\Users\Administrator\.nuget\packages\microsoft.windows.sdk.buildtools\10.0.26100.4948\bin\10.0.26100.0\x64\makepri.exe Dump -IndexFile "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\MsixContent\Microsoft.UI.Xaml.Controls.pri" -OutputFile "\\?\C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\Microsoft.UI.Xaml.Controls.pri.xml" -Verbose -Overwrite
         Adding payload file 'Microsoft.UI.Xaml\Assets\map.html' from 'C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\MsixContent\Microsoft.UI.Xaml\Assets\map.html'.
         Adding payload file 'Microsoft.UI.Xaml\Assets\NoiseAsset_256X256_PNG.png' from 'C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\obj\Release\net8.0-windows10.0.19041.0\win-x64\MsixContent\Microsoft.UI.Xaml\Assets\NoiseAsset_256X256_PNG.png'.
     1>已完成生成项目“C:\ChengXing-ONVIF\desktop\CXOnvif.Desktop\CXOnvif.Desktop.csproj”(Rebuild 个目标)的操作。

已成功生成。
    0 个警告
    0 个错误

已用时间 00:00:18.64
```

发布结果：

```text
dotnet publish -c Release -r win-x64 --self-contained true -p:Platform=x64
  -p:WindowsPackageType=None -p:WindowsAppSDKSelfContained=true -o desktop\dist

发布成功：C:\ChengXing-ONVIF\desktop\dist\CXOnvif.Desktop.exe
输出目录大小：166.3 MB（486 个文件）
```

- 可执行文件：`C:\ChengXing-ONVIF\desktop\dist\CXOnvif.Desktop.exe`
- 普通构建产物：`desktop\CXOnvif.Desktop\bin\Release\net8.0-windows10.0.19041.0\win-x64\CXOnvif.Desktop.exe`

## 4. 项目结构

```text
desktop/
├─ dist/                                   # build.ps1 的自包含发布输出（可执行文件在此）
└─ CXOnvif.Desktop/
   ├─ CXOnvif.Desktop.csproj               # WinUI 3 / unpackaged / 自包含配置
   ├─ app.manifest                         # PerMonitorV2 DPI、Win10/11 supportedOS
   ├─ build.ps1                            # 一键还原 + 发布到 desktop\dist
   ├─ App.xaml / App.xaml.cs               # 深色主题、配色与样式、应用级单例
   ├─ MainWindow.xaml / .cs                # NavigationView 单窗口（980×680）、标题栏深色
   ├─ Models/
   │  ├─ AppSettings.cs                    # settings.json 读写（%LOCALAPPDATA%）
   │  └─ ApiModels.cs                      # health / login / autostart 等模型
   ├─ Services/
   │  ├─ ApiClient.cs                      # REST v2 客户端（令牌仅内存）
   │  ├─ EngineProcessManager.cs           # pythonw 启动 / 停止 / 重启引擎
   │  └─ ShellLauncher.cs                  # 打开浏览器、mailto
   └─ Pages/
      ├─ OverviewPage.xaml / .cs           # 概览：状态轮询、启动/停止/重启/Web、地址设置
      ├─ SecurityPage.xaml / .cs           # 安全：登录、改密、强制改密提示
      ├─ AutostartPage.xaml / .cs          # 启动项：读取/切换开机自启
      └─ AboutPage.xaml / .cs              # 关于：品牌、版本、链接、MIT
```

## 5. 功能与 API 对应

| 功能 | 实现 | API |
| --- | --- | --- |
| 引擎状态（每 3 秒轮询） | `OverviewPage` + `ApiClient.GetHealthAsync` | `GET /api/v2/health`（免登录） |
| 版本 / 摄像机 / 运行时长 | 读取 health 的 `version`、`cameras`、`running`、`uptime` | 同上 |
| 启动引擎 | `EngineProcessManager.Start`：`ProcessStartInfo` + `UseShellExecute=false` + `CreateNoWindow=true`，隐藏窗口执行 `-m cxonvif serve --silent`，工作目录为仓库根目录；Python 自动探测 `pythonw.exe` → `python.exe`（仓库 venv → PATH → 常见安装目录） | 进程启动，随后轮询 health 等待就绪 |
| 停止引擎 | 先 `POST /api/v2/system/shutdown`（Bearer），超时未下线则结束进程（优先本次启动的进程，其次 `engine.pid` 记录） | `POST /api/v2/system/shutdown` |
| 重启引擎 | 停止 + 等待 0.8s + 启动 + 最多 30s 健康等待 | 同上 |
| 打开 Web 控制台 | `ShellLauncher.Open(engineUrl)` | 浏览器打开 |
| 引擎地址设置 | TextBox + 保存 → `settings.json`；保存后立即切换 API 基址 | — |
| 管理员登录 | 用户名/密码 → 令牌仅存内存，不落盘 | `POST /api/v2/auth/login` |
| 强制改密提示 | 登录返回 `mustChangePassword` + `GET /auth/state` 双重判断，显示醒目 InfoBar | `GET /api/v2/auth/state` |
| 修改密码 | 校验长度/一致性 → Bearer 提交，成功后清空令牌与输入 | `POST /api/v2/auth/password` |
| 开机自启状态 | 显示是否安装、平台、是否管理员、计划任务/启动文件夹、启动器、详情 | `GET /api/v2/service/autostart` |
| 开机自启开关 | ToggleSwitch → `{enabled, mode:"auto"}`，展示返回消息并刷新状态 | `POST /api/v2/service/autostart` |
| 关于页 | 品牌、引擎版本（`/health`）、桌面端版本、B站/GitHub/邮箱链接、MIT 与技术栈 | `GET /api/v2/health` |

本地文件：

- 设置：`%LOCALAPPDATA%\ChengXingOnvif.Desktop\settings.json`（引擎地址、仓库根目录、Python 路径、启动参数）
- 引擎 PID：`%LOCALAPPDATA%\ChengXingOnvif.Desktop\engine.pid`（仅用于停止由桌面端拉起的引擎）
- **不保存**任何密码或令牌；关闭窗口即退出进程，引擎继续在后台运行（符合“遥控器”定位）。

## 6. 构建环境问题与解决（重要）

1. **`winget` / `dotnet-install.ps1` 卡住**
   本机 `winget` 无输出、`dotnet-install.ps1` 长时间无进展（其网络栈受系统代理/TLS 环境影响）。
   改为用 `curl.exe` 直下官方 SDK zip、`tar.exe` 解压到 `C:\Program Files\dotnet`，并用 releases.json 中的 SHA512 校验，随后 `dotnet --list-sdks` 确认 **8.0.426** 可用。

2. **NuGet 还原长时间挂起（无任何下载）**
   现象：`dotnet restore` 停在 `Restoring packages...`，CPU 与网络均无进展；而 `curl` 访问同一 NuGet CDN 速度约 7 MB/s。
   原因：NuGet 的在线证书吊销检查（CRL/OCSP）在该网络环境下阻塞。
   解决：设置环境变量 `NUGET_CERT_REVOCATION_MODE=offline`（`build.ps1` 已内置），还原 11 秒完成。

3. **`dotnet build` 报 MSB4062：找不到 `Microsoft.Build.Packaging.Pri.Tasks.dll`**
   原因：`Microsoft.WindowsAppSDK` 自带的 `MrtCore.PriGen.targets` 默认引用 Visual Studio 的 AppxPackage MSBuild 任务；本机只有 .NET SDK，没有 VS 的 MSIX 工具。
   解决：项目额外引用 **`Microsoft.Windows.SDK.BuildTools.MSIX` 1.7.260930100**，它提供 `WinAppSdkExpandPriContent` 任务与 `makepri.exe`，使 `dotnet build` 无需 Visual Studio 即可生成 PRI。该包版本与 WindowsAppSDK 1.7 对应；升级 WindowsAppSDK 时请同步升级此包。

## 7. 已知限制 / 未完成项

- **托盘图标未实现**：关闭窗口即退出桌面端（引擎独立运行）。托盘需要额外 Win32 互操作，本次未做。
- **未做真实 GUI 运行测试**：按任务要求只验证编译与发布，未启动窗口做长时间交互测试。
- “停止引擎”在**未登录**时无法调用 shutdown 接口，只能结束由桌面端（或 PID 文件记录）启动的进程；由开机自启等其它方式启动且已登录的引擎，请先在“安全”页登录再停止。
- Python 自动探测覆盖仓库 venv、PATH、`%LOCALAPPDATA%\Programs\Python`、`Program Files`、`C:\Python3*`；其它自定义位置可在设置中手动填写。
- 图标字体使用 `Segoe Fluent Icons`（Windows 11 自带）；在缺少该字体的旧版 Windows 10 上图标可能显示为方框，其余功能不受影响。
- 窗口尺寸按物理像素设置为 980×680 并居中，高 DPI 缩放下物理尺寸不变、可用内容略少。
- 页面 XAML 为深色固定配色（未做浅色主题适配）。
