@echo off
rem ============================================================
rem  AI Desktop Widget - silent launcher
rem  Double-click to start (no console window).
rem  Exit: right-click the widget -> Exit
rem ============================================================
cd /d "%~dp0"

set "PYW="
rem 1) 优先用户自己安装的 Python（官方安装器默认目录，Python310~313）
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~D\pythonw.exe" if not defined PYW set "PYW=%%~D\pythonw.exe"
)
if not defined PYW for /d %%D in ("C:\Python3*") do (
    if exist "%%~D\pythonw.exe" if not defined PYW set "PYW=%%~D\pythonw.exe"
)
rem 2) 备选：PATH 中的 pythonw
if not defined PYW where pythonw >nul 2>nul && set "PYW=pythonw"

if defined PYW (
    start "" "%PYW%" "%~dp0deepseek_chatgpt_timer.py"
) else (
    echo [ERROR] Python 3.9+ (with tkinter / Pillow) not found.
    echo Please install Python from https://www.python.org/downloads/ and re-run.
    pause
)
