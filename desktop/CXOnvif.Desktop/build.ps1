#Requires -Version 5.1
<#
.SYNOPSIS
    一键构建 / 发布“程星 ONVIF 桌面控制台”（WinUI 3 + .NET 8 + 自包含 x64）。

.DESCRIPTION
    还原 NuGet 包并以自包含方式发布到 desktop\dist，生成可直接双击运行的 CXOnvif.Desktop.exe
    （无需预装 Windows App Runtime，也无需 .NET 运行时）。

.PARAMETER Configuration
    Release（默认）或 Debug。

.PARAMETER Runtime
    目标运行时，默认 win-x64。

.PARAMETER DotnetPath
    dotnet.exe 路径，默认 Program Files 下的安装。

.PARAMETER OutputDirectory
    发布输出目录，默认 desktop\dist。

.PARAMETER BuildOnly
    只执行 dotnet build，不做自包含发布。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\build.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\build.ps1 -Configuration Debug -BuildOnly
#>
[CmdletBinding()]
param(
    [ValidateSet('Release', 'Debug')]
    [string]$Configuration = 'Release',

    [string]$Runtime = 'win-x64',

    [string]$DotnetPath = 'C:\Program Files\dotnet\dotnet.exe',

    [string]$OutputDirectory,

    [switch]$BuildOnly
)

$ErrorActionPreference = 'Stop'

# 部分网络环境下 NuGet 的在线证书吊销检查会长时间挂起，默认改用离线检查
if (-not $env:NUGET_CERT_REVOCATION_MODE) {
    $env:NUGET_CERT_REVOCATION_MODE = 'offline'
}
if (-not $env:DOTNET_CLI_TELEMETRY_OPTOUT) {
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
}
if (-not $env:DOTNET_NOLOGO) {
    $env:DOTNET_NOLOGO = '1'
}

$projectDirectory = $PSScriptRoot
$desktopDirectory = Split-Path -Parent $projectDirectory
$project = Join-Path $projectDirectory 'CXOnvif.Desktop.csproj'

if (-not (Test-Path $DotnetPath)) {
    $command = Get-Command dotnet -ErrorAction SilentlyContinue
    if (-not $command) {
        throw '未找到 dotnet。请安装 .NET 8 SDK，或使用 -DotnetPath 指定 dotnet.exe。'
    }

    $DotnetPath = $command.Source
}

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $desktopDirectory 'dist'
}

Write-Host '==== 程星 ONVIF 桌面控制台 ====' -ForegroundColor Cyan
Write-Host "dotnet        : $DotnetPath"
Write-Host "project       : $project"
Write-Host "configuration : $Configuration ($Runtime)"
Write-Host "output        : $OutputDirectory"
Write-Host ''

$sdkVersion = & $DotnetPath --version
Write-Host "SDK 版本      : $sdkVersion" -ForegroundColor DarkGray

Write-Host '>> [1/2] 还原 NuGet 包…' -ForegroundColor Cyan
& $DotnetPath restore $project -r $Runtime
if ($LASTEXITCODE -ne 0) {
    throw "dotnet restore 失败（exit $LASTEXITCODE）"
}

if ($BuildOnly) {
    Write-Host '>> [2/2] 构建…' -ForegroundColor Cyan
    & $DotnetPath build $project -c $Configuration --no-restore
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet build 失败（exit $LASTEXITCODE）"
    }

    Write-Host ''
    Write-Host "构建成功：$(Join-Path $projectDirectory "bin\$Configuration\net8.0-windows10.0.19041.0\$Runtime")" -ForegroundColor Green
    return
}

Write-Host '>> [2/2] 自包含发布…' -ForegroundColor Cyan
if (Test-Path $OutputDirectory) {
    Remove-Item $OutputDirectory -Recurse -Force
}

& $DotnetPath publish $project -c $Configuration -r $Runtime --self-contained true -p:Platform=x64 -p:WindowsPackageType=None -p:WindowsAppSDKSelfContained=true -o $OutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish 失败（exit $LASTEXITCODE）"
}

$exe = Join-Path $OutputDirectory 'CXOnvif.Desktop.exe'
if (-not (Test-Path $exe)) {
    throw "发布结束，但未找到 $exe"
}

$totalBytes = (Get-ChildItem $OutputDirectory -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ''
Write-Host "发布成功：$exe" -ForegroundColor Green
Write-Host ('输出目录大小：{0:N1} MB' -f ($totalBytes / 1MB))
Write-Host '直接双击该 exe 即可运行（自包含，无需安装 Windows App Runtime）。'
