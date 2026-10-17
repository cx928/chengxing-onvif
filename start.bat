@echo off
REM ============================================================
REM  程星 ONVIF / ChengXing ONVIF - 启动脚本
REM ============================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if "%~1"=="--silent" (
    if exist ".venv\Scripts\pythonw.exe" (
        start "" ".venv\Scripts\pythonw.exe" -m cxonvif serve --silent
    ) else (
        start "" pythonw -m cxonvif serve --silent
    )
    exit /b 0
)

echo.
echo   程星 ONVIF 正在启动…
echo   网页控制台 http://localhost:5552
echo.
"%PY%" -m cxonvif serve
pause
