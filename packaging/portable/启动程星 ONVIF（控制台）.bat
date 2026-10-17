@echo off
chcp 65001 >nul
cd /d "%~dp0app"
echo.
echo   程星 ONVIF 正在启动（控制台模式，便于查看日志）...
echo   网页控制台: http://localhost:5552
echo   按 Ctrl+C 可停止服务
echo.
"..\python\python.exe" -m cxonvif serve
pause
