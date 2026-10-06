@echo off
setlocal
if not exist "%~dp0AptosFont.ps1" goto :missing
powershell.exe -NoProfile -File "%~dp0AptosFont.ps1"
set "FONT_EXIT=%ERRORLEVEL%"
echo.
if not "%FONT_EXIT%"=="0" echo Aptos installation did not finish. Send the message and log path above to support.
pause
exit /b %FONT_EXIT%
:missing
echo The shared project folder is unavailable or AptosFont.ps1 is missing.
pause
exit /b 1
