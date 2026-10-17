<#
.SYNOPSIS
    启动程星 ONVIF 服务
.EXAMPLE
    .\start.ps1
    .\start.ps1 -Silent
#>
param([switch]$Silent, [int]$Port = 0, [switch]$NoBrowser)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$cliArgs = @("-m", "cxonvif", "serve")
if ($Port -gt 0) { $cliArgs += @("--port", "$Port") }
if ($NoBrowser) { $cliArgs += "--no-browser" }
if ($Silent) {
    $pythonw = ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $pythonw)) { $pythonw = "pythonw" }
    Start-Process -FilePath $pythonw -ArgumentList ($cliArgs + "--silent") -WorkingDirectory $Root -WindowStyle Hidden
    Write-Host "程星 ONVIF 已在后台静默启动：http://localhost:$(if ($Port -gt 0) { $Port } else { 5552 })"
} else {
    & $python @cliArgs
}
