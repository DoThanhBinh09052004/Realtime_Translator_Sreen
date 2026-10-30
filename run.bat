@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    echo [ERROR] Khong tim thay Python trong .venv\Scripts\python.exe!
    pause
)
