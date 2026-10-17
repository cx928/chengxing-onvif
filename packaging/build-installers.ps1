<#
.SYNOPSIS
    构建程星 ONVIF 的便携 ZIP 与 MSI 安装包。
.DESCRIPTION
    产物：
      build\ChengXing-ONVIF-<版本>-portable-win-x64.zip
      build\msi\ChengXing-ONVIF-<版本>-x64.msi
    依赖：PowerShell 7、7-Zip（可选，缺失时用 Compress-Archive）、联网下载 Python/依赖/模型/WiX。
.EXAMPLE
    .\build-installers.ps1
    .\build-installers.ps1 -Version 1.0.1 -NoMsi
#>
[CmdletBinding()]
param(
    [string]$Version = "1.0.1",
    [string]$PythonVersion = "3.12.10",
    [string]$FFmpegDir = "",
    [string]$MediaMTXExe = "",
    [string]$DesktopDist = "",
    [string]$PipIndex = "https://pypi.tuna.tsinghua.edu.cn/simple",
    [switch]$NoMsi,
    [switch]$NoZip,
    [switch]$ReusePython
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Packaging = $PSScriptRoot
$Build = Join-Path $Root "build"
$Downloads = Join-Path $Build "downloads"
$PkgName = "ChengXing-ONVIF-$Version"
$PkgRoot = Join-Path $Build "pkg\$PkgName"
$AppDir = Join-Path $PkgRoot "app"
$PythonDir = Join-Path $PkgRoot "python"
$WixDir = Join-Path $Build "wix"
$MsiDir = Join-Path $Build "msi"

if (-not $FFmpegDir) { $FFmpegDir = Join-Path $Root "vendor\ffmpeg" }
if (-not $MediaMTXExe) { $MediaMTXExe = Join-Path $Root "vendor\mediamtx\mediamtx.exe" }
if (-not $DesktopDist) { $DesktopDist = Join-Path $Root "desktop\dist" }

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Ok($text) { Write-Host "  [OK] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "  [!] $text" -ForegroundColor Yellow }
function Download($url, $out) {
    if (Test-Path $out) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
    Write-Host "  下载 $url" -ForegroundColor Gray
    curl.exe -L --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 600 -o $out $url
    if (-not (Test-Path $out) -or (Get-Item $out).Length -lt 1024) { throw "下载失败：$url" }
}

Step "检查构建环境"
foreach ($required in @($Root, $Packaging)) { if (-not (Test-Path $required)) { throw "路径不存在：$required" } }
if (-not (Test-Path (Join-Path $Root "cxonvif"))) { throw "请在项目根目录下运行" }
$sevenZip = (Get-Command 7z -ErrorAction SilentlyContinue).Source
if ($sevenZip) { Ok "7-Zip: $sevenZip" } else { Warn "未找到 7-Zip，将使用 Compress-Archive（较慢）" }
if (-not (Test-Path $DesktopDist)) { Warn "桌面端发布目录不存在：$DesktopDist（将跳过桌面控制台）" }
New-Item -ItemType Directory -Force -Path $Downloads, $Build | Out-Null

Step "准备嵌入式 Python $PythonVersion"
$pyZip = Join-Path $Downloads "python-$PythonVersion-embed-amd64.zip"
if (-not $ReusePython -or -not (Test-Path "$PythonDir\python.exe")) {
    if (-not (Test-Path $pyZip)) {
        Download "https://mirrors.aliyun.com/python-release/windows/python-$PythonVersion-embed-amd64.zip" $pyZip
    }
    Remove-Item -Recurse -Force $PkgRoot -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $PythonDir, $AppDir | Out-Null
    Expand-Archive -Path $pyZip -DestinationPath $PythonDir -Force
    $pth = Get-ChildItem $PythonDir -Filter "python*._pth" | Select-Object -First 1
    $zipName = (Get-ChildItem $PythonDir -Filter "python*.zip" | Select-Object -First 1).Name
    @"
$zipName
.
..\app
import site
"@ | Set-Content $pth.FullName -Encoding ASCII
    Ok "Python 已解压到 $PythonDir"

    Step "安装运行依赖"
    $getPip = Join-Path $Downloads "get-pip.py"
    Download "https://bootstrap.pypa.io/get-pip.py" $getPip
    & "$PythonDir\python.exe" $getPip --no-warn-script-location --disable-pip-version-check -i $PipIndex
    if ($LASTEXITCODE -ne 0) { throw "get-pip 失败" }
    & "$PythonDir\python.exe" -m pip install --no-cache-dir --disable-pip-version-check -i $PipIndex `
        flask flask-cors requests pyyaml psutil numpy pillow opencv-python-headless onnxruntime
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }
    Ok "依赖安装完成"
} else {
    Ok "复用已有 Python 运行时"
}

Step "组装应用目录"
Copy-Item (Join-Path $Root "cxonvif") $AppDir -Recurse -Force
Copy-Item (Join-Path $Root "web") $AppDir -Recurse -Force
Copy-Item (Join-Path $Root "docs") $AppDir -Recurse -Force
Copy-Item (Join-Path $Root "README.md"), (Join-Path $Root "LICENSE"), (Join-Path $Root "NOTICE"), (Join-Path $Root "CHANGELOG.md") $AppDir -Force
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "models"), (Join-Path $AppDir "ffmpeg"), (Join-Path $AppDir "mediamtx") | Out-Null
Get-ChildItem $AppDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $AppDir -Recurse -Include "*.pyc", "*.pyo" -File | Remove-Item -Force -ErrorAction SilentlyContinue

# 保持与发布版一致的默认模型（ONNX，无需 PyTorch）
@"
{
  "settings": {
    "defaultModel": "yolo11n-onnx",
    "defaultBackend": "auto"
  },
  "detect": {
    "model": "yolo11n-onnx"
  }
}
"@ | Set-Content (Join-Path $AppDir "defaults.json") -Encoding UTF8

Step "复制 FFmpeg / MediaMTX / 模型 / 桌面端"
if ((Test-Path $FFmpegDir) -and (Test-Path (Join-Path $FFmpegDir "ffmpeg.exe"))) {
    Copy-Item (Join-Path $FFmpegDir "ffmpeg.exe") (Join-Path $AppDir "ffmpeg") -Force
    if (Test-Path (Join-Path $FFmpegDir "ffprobe.exe")) {
        Copy-Item (Join-Path $FFmpegDir "ffprobe.exe") (Join-Path $AppDir "ffmpeg") -Force
    }
    Ok "FFmpeg 已复制"
} else {
    Warn "未找到 FFmpeg：请把 ffmpeg.exe / ffprobe.exe 放到 $FFmpegDir"
}
if (Test-Path $MediaMTXExe) {
    Copy-Item $MediaMTXExe (Join-Path $AppDir "mediamtx\mediamtx.exe") -Force
    Ok "MediaMTX 已复制"
} else {
    Warn "未找到 MediaMTX：$MediaMTXExe（首次启动会尝试自动下载）"
}
$modelFile = Join-Path $AppDir "models\yolo11n.onnx"
if (-not (Test-Path $modelFile)) {
    try {
        Download "https://ghfast.top/https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.onnx" $modelFile
        Ok "已下载内置 ONNX 模型"
    } catch {
        Warn "ONNX 模型下载失败，首次运行需在模型库手动下载"
    }
}
if ((Test-Path $DesktopDist) -and (Test-Path (Join-Path $DesktopDist "CXOnvif.Desktop.exe"))) {
    Copy-Item $DesktopDist (Join-Path $PkgRoot "desktop") -Recurse -Force
    Ok "桌面控制台已复制"
}

Step "写入启动脚本"
Copy-Item (Join-Path $Packaging "portable\*") $PkgRoot -Force
Ok "启动脚本已写入"

Step "生成 ZIP"
if (-not $NoZip) {
    $zipPath = Join-Path $Build "$PkgName-portable-win-x64.zip"
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    if ($sevenZip) {
        Push-Location (Split-Path $PkgRoot)
        & $sevenZip a -tzip -mx=5 -mmt=4 $zipPath $PkgName | Out-Null
        Pop-Location
    } else {
        Compress-Archive -Path $PkgRoot -DestinationPath $zipPath -CompressionLevel Optimal
    }
    Ok ("ZIP: {0} ({1:N1} MB)" -f $zipPath, ((Get-Item $zipPath).Length / 1MB))
}

Step "生成 MSI"
if ($NoMsi) { Warn "已跳过 MSI"; exit 0 }
if (-not (Test-Path (Join-Path $WixDir "candle.exe"))) {
    $wixZip = Join-Path $Downloads "wix314-binaries.zip"
    if (-not (Test-Path $wixZip)) {
        Warn "正在下载 WiX 3.14…"
        Download "https://ghfast.top/https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip" $wixZip
    }
    Expand-Archive -Path $wixZip -DestinationPath $WixDir -Force
}
New-Item -ItemType Directory -Force -Path $MsiDir, (Join-Path $MsiDir "obj") | Out-Null
Copy-Item (Join-Path $Packaging "msi\Product.wxs") $MsiDir -Force
Copy-Item (Join-Path $Packaging "msi\license.rtf") $MsiDir -Force
Copy-Item (Join-Path $Root "assets\cx.ico") (Join-Path $MsiDir "cx.ico") -Force
$filesWxs = Join-Path $MsiDir "files.wxs"
& (Join-Path $WixDir "heat.exe") dir $PkgRoot -cg CxFiles -dr INSTALLDIR -gg -g1 -sfrag -srd -sreg -var var.SourceDir -out $filesWxs | Out-Null
& (Join-Path $WixDir "candle.exe") -arch x64 -dSourceDir="$PkgRoot" -out "$MsiDir\obj\" (Join-Path $MsiDir "Product.wxs") $filesWxs | Out-Null
if ($LASTEXITCODE -ne 0) { throw "candle 失败" }
$msiPath = Join-Path $MsiDir "$PkgName-x64.msi"
& (Join-Path $WixDir "light.exe") -ext WixUIExtension -cultures:zh-CN -sice:ICE03 -sice:ICE61 -out $msiPath "$MsiDir\obj\Product.wixobj" "$MsiDir\obj\files.wixobj" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "light 失败" }
Ok ("MSI: {0} ({1:N1} MB)" -f $msiPath, ((Get-Item $msiPath).Length / 1MB))

Step "完成"
Get-ChildItem $Build -Filter "ChengXing-ONVIF-*" | Select-Object FullName, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize
