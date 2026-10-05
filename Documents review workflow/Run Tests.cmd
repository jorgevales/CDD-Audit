@echo off
setlocal
set "CDD_BOOTSTRAP=%~dp0WorkflowBootstrap.ps1"
set "CDD_BOOTSTRAP_ACTION=Test"
powershell.exe -NoProfile -File "%CDD_BOOTSTRAP%" -Action "%CDD_BOOTSTRAP_ACTION%"
set "TEST_EXIT=%ERRORLEVEL%"
pause
exit /b %TEST_EXIT%
