@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
echo.
echo Setup finished. Use "Start Workflow.cmd" to run the application.
pause
exit /b 0
:failed
echo.
echo Setup did not finish. Copy the error above and give it to your support team.
pause
exit /b 1
