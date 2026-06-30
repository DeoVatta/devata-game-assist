@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 判断是否已管理员
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b 0
)

if exist "TaskBarHero助手\TaskBarHero助手.exe" (
    start "" "TaskBarHero助手\TaskBarHero助手.exe"
    exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
    echo 请先运行「打包.bat」生成 exe，或安装 Python 3.10+
    pause
    exit /b 1
)

python app.py
if errorlevel 1 pause
