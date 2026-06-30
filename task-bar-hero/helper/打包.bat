@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "dist\release\启动挂机助手.bat" (
    start "" "dist\release\启动挂机助手.bat"
    exit /b 0
)

python build_release.py
pause
