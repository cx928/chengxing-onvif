<#
.SYNOPSIS
    程星 ONVIF 一键安装脚本（Windows）
.DESCRIPTION
    创建虚拟环境、安装依赖、下载 FFmpeg 与 MediaMTX，并可安装开机静默自启。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
.EXAMPLE
    .\install.ps1 -WithAI -InstallAutostart
#>
[CmdletBinding()]
param(
    [int]$Port = 5552,
    [string]$PythonExe = "",
    [switch]$WithAI,
    [switch]$InstallAutostart,
    [switch]$SkipBinaries,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Vendor = Join-Path $Root "vendor"
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "  [OK] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [!] $text" -ForegroundColor Yellow }

Write-Host @"
   ______ __  __   ____  _   __ ______ _   __
  / ____// / / /  / __ \/ | / // ____// | / /
 / /    / /_/ /  / / / /  |/ // /_   /  |/ /
/ /___ / __  /  / /_/ / /|  / __/  / /|  /
\____//_/ /_/  \____/_/ |_/_/    /_/ |_/
        程星 ONVIF  v1.0.0  安装程序
"@ -ForegroundColor Green

# ------------------------------------------------------------------ Python
Write-Step "检查 Python"
if (-not $PythonExe) {
    $candidates = @("python", "python3", "py")
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            $version = & $cmd.Source -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) {
                $parts = $version.Split(".")
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) { $PythonExe = $cmd.Source; break }
            }
        }
    }
}
if (-not $PythonExe) {
    Write-Warn "未找到 Python 3.10+，请先安装：https://www.python.org/downloads/windows/"
    Write-Host "  安装时请勾选 Add python.exe to PATH，然后重新运行本脚本。" -ForegroundColor Yellow
    exit 1
}
$pyVersion = & $PythonExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
Write-Ok "Python $pyVersion  ($PythonExe)"

# ------------------------------------------------------------------ venv
Write-Step "创建虚拟环境"
if (-not (Test-Path $VenvPython) -or $Force) {
    if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
    & $PythonExe -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
}
Write-Ok ".venv 就绪"

Write-Step "安装 Python 依赖"
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
& $VenvPython -m pip install "opencv-python-headless>=4.9"
if ($WithAI) {
    Write-Host "  安装 AI 依赖（PyTorch CPU + Ultralytics，约 300MB）…" -ForegroundColor Cyan
    & $VenvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    & $VenvPython -m pip install ultralytics
}
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }
Write-Ok "依赖安装完成"

# ------------------------------------------------------------------ FFmpeg
if (-not $SkipBinaries) {
    $ffmpegDir = Join-Path $Vendor "ffmpeg"
    $ffmpegExe = Join-Path $ffmpegDir "ffmpeg.exe"
    Write-Step "准备 FFmpeg"
    if (Test-Path $ffmpegExe) {
        Write-Ok "已存在 $ffmpegExe"
    }
    else {
        New-Item -ItemType Directory -Force -Path $Vendor | Out-Null
        $zip = Join-Path $env:TEMP "cxonvif-ffmpeg.zip"
        $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        Write-Host "  下载 FFmpeg：$url" -ForegroundColor Gray
        try {
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 300
            $extract = Join-Path $env:TEMP "cxonvif-ffmpeg"
            if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
            Expand-Archive -Path $zip -DestinationPath $extract -Force
            $bin = Get-ChildItem -Path $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            if (-not $bin) { throw "压缩包内未找到 ffmpeg.exe" }
            New-Item -ItemType Directory -Force -Path $ffmpegDir | Out-Null
            Copy-Item (Join-Path $bin.DirectoryName "*") $ffmpegDir -Force
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "FFmpeg 已安装到 vendor\ffmpeg"
        }
        catch {
            Write-Warn "FFmpeg 下载失败：$($_.Exception.Message)"
            Write-Warn "可手动下载后解压到 vendor\ffmpeg，或设置系统 PATH 中的 ffmpeg"
        }
    }

    # -------------------------------------------------------------- MediaMTX
    $mtxDir = Join-Path $Vendor "mediamtx"
    $mtxExe = Join-Path $mtxDir "mediamtx.exe"
    Write-Step "准备 MediaMTX"
    if (Test-Path $mtxExe) {
        Write-Ok "已存在 $mtxExe"
    }
    else {
        New-Item -ItemType Directory -Force -Path $mtxDir | Out-Null
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/bluenviron/mediamtx/releases/latest" `
                -Headers @{ "User-Agent" = "cxonvif-installer" } -TimeoutSec 60
            $asset = $release.assets | Where-Object { $_.name -like "*windows_amd64.zip" } | Select-Object -First 1
            if (-not $asset) { throw "未找到 windows_amd64 发行包" }
            $zip = Join-Path $env:TEMP "cxonvif-mediamtx.zip"
            Write-Host "  下载 MediaMTX $($release.tag_name)…" -ForegroundColor Gray
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing -TimeoutSec 300
            $extract = Join-Path $env:TEMP "cxonvif-mediamtx"
            if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
            Expand-Archive -Path $zip -DestinationPath $extract -Force
            $exe = Get-ChildItem -Path $extract -Recurse -Filter "mediamtx.exe" | Select-Object -First 1
            if (-not $exe) { throw "压缩包内未找到 mediamtx.exe" }
            Copy-Item $exe.FullName $mtxExe -Force
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "MediaMTX 已安装到 vendor\mediamtx"
        }
        catch {
            Write-Warn "MediaMTX 下载失败：$($_.Exception.Message)"
            Write-Warn "首次启动时也会自动重试下载，或手动放入 vendor\mediamtx\mediamtx.exe"
        }
    }
}

# ------------------------------------------------------------------ 自启
if ($InstallAutostart) {
    Write-Step "安装开机静默自启"
    try {
        & $VenvPython -m cxonvif autostart install
    }
    catch {
        Write-Warn "自启安装失败：$($_.Exception.Message)"
    }
}

# ------------------------------------------------------------------ 完成
Write-Step "安装完成"
Write-Host @"
  启动命令：
    .\start.ps1
    或  .\.venv\Scripts\python.exe -m cxonvif serve

  网页控制台： http://localhost:$Port
  默认账号：   admin
  默认密码：   cx123456   （首次登录会要求修改）

  常用命令：
    .\.venv\Scripts\python.exe -m cxonvif doctor
    .\.venv\Scripts\python.exe -m cxonvif autostart install
    .\.venv\Scripts\python.exe -m cxonvif password 新密码

  提示：Intel 核显编码需要显卡驱动；NVIDIA 需要支持 NVENC 的驱动。
"@ -ForegroundColor Gray

$open = Read-Host "现在启动服务？(Y/n)"
if ($open -ne "n") {
    Start-Process -FilePath $VenvPython -ArgumentList @("-m", "cxonvif", "serve") -WorkingDirectory $Root
}
