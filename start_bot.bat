@echo off
title Antigravity Telegram Agent v4.0
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\agy\bin;%PATH%"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bot.py
) else (
    python bot.py
)
pause
