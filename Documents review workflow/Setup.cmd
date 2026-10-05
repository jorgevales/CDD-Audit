@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto :failed
set "CDD_BOOTSTRAP=%~dp0WorkflowBootstrap.ps1"
set "CDD_BOOTSTRAP_ACTION=Setup"
powershell.exe -NoProfile -File "%CDD_BOOTSTRAP%" -Action "%CDD_BOOTSTRAP_ACTION%"
set "SETUP_EXIT=%ERRORLEVEL%"
popd >nul 2>&1
if not "%SETUP_EXIT%"=="0" goto :failed
echo.
echo Setup finished. Use "Start Workflow.cmd" to run the application.
pause
exit /b 0
:failed
echo.
echo Setup did not finish. Copy the message above and the diagnostic log path for your support team.
pause
exit /b 1
