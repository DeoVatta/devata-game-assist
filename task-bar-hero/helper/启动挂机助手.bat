@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 判断是否已管理员
net session >nul 2>&1
if errorlevel 1 (
    :: 非管理员 → 弹 UAC 提权
    echo 正在请求管理员权限（点击通常需要与游戏同级权限）…
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b 0
)

:: 已管理员 → 启动
if exist "TaskBarHero助手\TaskBarHero助手.exe" (
    start "" "TaskBarHero助手\TaskBarHero助手.exe"
    exit /b 0
)

if exist "TaskBarHero助手.exe" (
    start "" "TaskBarHero助手.exe"
    exit /b 0
)

:: 回退：Python 源码
where python >nul 2>&1
if errorlevel 1 (
    echo 未找到程序。请解压完整包。
    pause
    exit /b 1
)

python app.py
if errorlevel 1 pause
