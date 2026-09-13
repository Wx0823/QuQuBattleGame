@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" "C:\Users\Admin\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe" "%~dp0main.py"
