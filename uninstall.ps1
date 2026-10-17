<#
.SYNOPSIS
    卸载程星 ONVIF（移除开机自启，可选删除数据与虚拟环境）
#>
param(
    [switch]$RemoveData,
    [switch]$RemoveVenv
)
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== 移除开机自启 ==" -ForegroundColor Cyan
$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $python -m cxonvif autostart uninstall

Write-Host "== 停止正在运行的服务 ==" -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "cxonvif" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

if ($RemoveData) {
    $data = Join-Path $env:ProgramData "ChengXingOnvif"
    if (Test-Path $data) {
        Write-Host "删除数据目录 $data" -ForegroundColor Yellow
        Remove-Item -Recurse -Force $data
    }
}
if ($RemoveVenv) {
    if (Test-Path ".venv") {
        Write-Host "删除虚拟环境 .venv" -ForegroundColor Yellow
        Remove-Item -Recurse -Force ".venv"
    }
}
Write-Host "完成。程序目录可手动删除。" -ForegroundColor Green
