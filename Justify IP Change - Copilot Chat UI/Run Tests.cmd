@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -File "%~dp0WorkflowBootstrap.ps1" -Action Test
set "JIP_EXIT=%ERRORLEVEL%"
popd >nul 2>&1
exit /b %JIP_EXIT%
