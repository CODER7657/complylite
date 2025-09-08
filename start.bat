@echo off
REM ComplyLite Quick Start Script for Windows
setlocal ENABLEDELAYEDEXPANSION

echo Starting ComplyLite Compliance Surveillance System...

REM Detect venv Python
set VENV_PY="%~dp0.venv\Scripts\python.exe"
if exist %VENV_PY% (
	set PY=%VENV_PY%
	echo Using virtual environment Python: %PY%
) else (
	where python >nul 2>nul && (
		for /f "delims=" %%i in ('where python') do set PY="%%i" & goto :foundpy
	)
	echo Could not find Python. Please install Python 3.11+ or create a venv at .venv
	goto :eof
)
:foundpy

REM Start backend in new window (set app-dir so imports like 'from app...' work)
echo Starting Backend API...
start "ComplyLite Backend" cmd /k "cd /d %~dp0 && %PY% -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000"

REM Wait for backend to start
timeout /t 5 /nobreak > nul

REM Start frontend in new window
echo Starting Frontend...
start "ComplyLite Frontend" cmd /k "cd /d %~dp0frontend && npm start"

echo System Started
echo Backend API: http://localhost:8000
echo Frontend App: http://localhost:3000
echo API Docs: http://localhost:8000/docs

endlocal
