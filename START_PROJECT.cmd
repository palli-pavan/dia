@echo off
cd /d "%~dp0emergency-resource-allocation"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
) else (
  python run.py
)
pause
