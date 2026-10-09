@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto :failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launcher.ps1" -Action Setup
set "JIP_EXIT=%ERRORLEVEL%"
popd >nul 2>&1
if not "%JIP_EXIT%"=="0" goto :failed
echo.
echo Setup finished. Use "Start Justify IP Change.cmd" to run the application.
pause
exit /b 0
:failed
echo.
echo Setup did not finish. Copy the diagnostic log path shown above for support.
pause
exit /b 1
