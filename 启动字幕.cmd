@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating a Python environment...
  python -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import yt_dlp, faster_whisper" >nul 2>nul
if errorlevel 1 (
  echo Installing subtitle dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" subtitle_server.py
pause
exit /b 0

:failed
echo Startup failed. See README.md for help.
pause
exit /b 1
