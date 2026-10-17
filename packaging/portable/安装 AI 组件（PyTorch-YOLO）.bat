@echo off
chcp 65001 >nul
cd /d "%~dp0app"
echo.
echo   安装 AI 组件（Ultralytics + PyTorch CPU）
echo   安装后可使用 .pt 模型（YOLO26/11/8、RT-DETR、YOLO-World 等）。
echo   安装包较大（约 300MB），请保持网络畅通。
echo.
choice /C YN /M "继续安装"
if errorlevel 2 exit /b 0
..\python\python.exe -m pip install --upgrade pip
..\python\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
..\python\python.exe -m pip install ultralytics
..\python\python.exe -m pip install opencv-python-headless
echo.
echo   安装完成。请重启程星 ONVIF 服务。
pause
