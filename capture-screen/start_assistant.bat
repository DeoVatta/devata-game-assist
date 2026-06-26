@echo off
title Devata Gaming Assistant
cd /d "%~dp0"

echo ============================================
echo    Devata Gaming Assistant - Starting
echo ============================================
echo.

echo [1] Starting Input Logger (keyboard + mouse)...
start "INPUT-LOGGER" /min python "%~dp0input_logger.py" --start
echo    OK - Input logger running in background

echo.
echo [2] Starting Screen Capture Loop (10s interval)...
start "SCREEN-CAPTURE" /min python "%~dp0capture_loop.py"
echo    OK - Capture loop running in background

echo.
echo ============================================
echo    Both services running in background
echo ============================================
echo.
echo Commands:
echo   python vision_monitor.py          - Analyze current screen
echo   python vision_monitor.py --retro  - Last 5 min review
echo   python vision_monitor.py --retro --input  - Full review + input
echo   python vision_monitor.py --retro 3 --input - Last 3 min + input
echo.
echo   python input_logger.py --status   - Check input buffer
echo   python input_logger.py --stop     - Stop input logger
echo.
pause
