@echo off
REM Double-click installer for graphify + autotrigger Cowork skills.
REM Calls the PowerShell installer in the same directory with ExecutionPolicy bypassed
REM so end-users do not have to fiddle with policy settings.

setlocal
set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-cowork-skills.ps1" %*
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% NEQ 0 (
  echo.
  echo Installer exited with code %EXITCODE%.
  pause
)

exit /b %EXITCODE%
