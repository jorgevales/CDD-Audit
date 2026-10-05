@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto :failed
set "CDD_BOOTSTRAP=%~dp0WorkflowBootstrap.ps1"
set "CDD_BOOTSTRAP_ACTION=Start"
powershell.exe -NoProfile -File "%CDD_BOOTSTRAP%" -Action "%CDD_BOOTSTRAP_ACTION%"
set "START_EXIT=%ERRORLEVEL%"
popd >nul 2>&1
if "%START_EXIT%"=="0" exit /b 0
:failed
echo.
echo The workflow could not start. If this is the first run, double-click Setup.cmd, then try again.
echo If it still fails, copy the message above and the diagnostic log path for your support team.
echo If Windows says scripts are disabled, ask IT to approve WorkflowBootstrap.ps1.
pause
exit /b 1
