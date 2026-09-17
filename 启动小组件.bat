@echo off
rem ============================================================
rem  AI Desktop Widget - silent launcher
rem  Double-click to start (no console window).
rem  Exit: right-click the widget -> Exit
rem ============================================================
cd /d "%~dp0"

set "PYW="
where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PYW for /f "delims=" %%i in ('where python 2^>nul') do (
    if exist "%%~dpi\pythonw.exe" set "PYW=%%~dpi\pythonw.exe"
)

if defined PYW (
    start "" "%PYW%" "%~dp0deepseek_chatgpt_timer.py"
) else (
    echo [ERROR] pythonw.exe not found. Please install Python 3.9+ with "Add Python to PATH".
    pause
)
