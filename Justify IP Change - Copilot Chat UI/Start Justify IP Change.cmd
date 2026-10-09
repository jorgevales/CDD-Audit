@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto :failed
set "JIP_ACTION=Start"
powershell.exe -NoProfile -File "%~dp0WorkflowBootstrap.ps1" -Action "%JIP_ACTION%"
set "JIP_EXIT=%ERRORLEVEL%"
popd >nul 2>&1
if "%JIP_EXIT%"=="0" exit /b 0
:failed
echo.
echo Justify IP Change could not start. Run Setup.cmd once, then try again.
echo Copy the diagnostic log path shown above if support is needed.
pause
exit /b 1
