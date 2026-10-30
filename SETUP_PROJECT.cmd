@echo off
cd /d "%~dp0emergency-resource-allocation"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-tested.txt
if errorlevel 1 goto failed
cd frontend
call npm ci
if errorlevel 1 goto failed
call npm run build
if errorlevel 1 goto failed
echo Setup completed. Run START_PROJECT.cmd from the Disaster folder.
pause
exit /b 0
:failed
echo Setup failed. Read the error above before retrying.
pause
exit /b 1
