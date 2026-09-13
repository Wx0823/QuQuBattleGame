@echo off
chcp 65001 >nul
cd /d "%~dp0"
"C:\Users\Admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe" "%~dp0main.py"
pause
