@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "GITEXE=C:\Program Files\Git\cmd\git.exe"

echo ===========================================
echo   QuQuBattleGame  -  Push to GitHub
echo ===========================================
echo.

if not exist "%GITEXE%" (
  echo [ERROR] Git not found at %GITEXE%
  pause
  exit /b 1
)

set "GHUSER=%~1"
if "%GHUSER%"=="" set /p GHUSER=Your GitHub username:
if "%GHUSER%"=="" (
  echo [ERROR] username required
  pause
  exit /b 1
)

echo.
echo [1/2] remote -^> git@github.com:%GHUSER%/QuQuBattleGame.git
"%GITEXE%" remote remove origin >nul 2>&1
"%GITEXE%" remote add origin git@github.com:%GHUSER%/QuQuBattleGame.git

echo [2/2] pushing main branch and tags ...
"%GITEXE%" push -u origin main --tags
if errorlevel 1 goto fail

echo.
echo [OK] Push finished:
echo      https://github.com/%GHUSER%/QuQuBattleGame
pause
exit /b 0

:fail
echo.
echo [FAILED] Please check:
echo   1. Have you created an EMPTY repo named QuQuBattleGame on GitHub?
echo   2. Is your SSH public key added to GitHub - Settings - SSH and GPG keys?
echo   3. Is the username spelled correctly?
echo.
echo Tip: test SSH with   ssh -T git@github.com
pause
exit /b 1
