@echo off
rem ============================================================
rem  发条AI时段小组件 - launcher
rem  优先启动 exe（无控制台窗口）；无 exe 时退回源码 pythonw
rem ============================================================
cd /d "%~dp0"

if exist "%~dp0发条AI时段小组件.exe" (
    start "" "%~dp0发条AI时段小组件.exe"
    exit /b
)

set "PYW="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~D\pythonw.exe" if not defined PYW set "PYW=%%~D\pythonw.exe"
)
if not defined PYW for /d %%D in ("C:\Python3*") do (
    if exist "%%~D\pythonw.exe" if not defined PYW set "PYW=%%~D\pythonw.exe"
)
if not defined PYW where pythonw >nul 2>nul && set "PYW=pythonw"

if defined PYW (
    start "" "%PYW%" "%~dp0deepseek_chatgpt_timer.py"
) else (
    echo [ERROR] exe 不存在且未找到 Python 3.9+（需 tkinter / Pillow）。
    echo 请安装 Python: https://www.python.org/downloads/ 后重试。
    pause
)
