@echo off
setlocal
title RAGify AI Launcher

echo ============================================================
echo    RAGify AI  -  Agentic Retrieval-Augmented Generation
echo ============================================================
echo.

REM --- Move to the folder that contains this script ---
set "ROOT=%~dp0"
cd /d "%ROOT%"

REM --- Verify Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.11 or newer from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo [OK] %%v detected

REM --- Verify Node.js ---
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found on PATH.
    echo         Install Node.js 18 or newer from https://nodejs.org/
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('node --version 2^>^&1') do echo [OK] Node %%v detected

REM --- Verify npm ---
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found on PATH.
    pause
    exit /b 1
)

REM --- Environment file ---
if not exist ".env" (
    echo [WARN] .env not found. Creating one from .env.example...
    copy ".env.example" ".env" >nul
    echo [INFO] Open the .env file and set OPENROUTER_API_KEY, then restart.
    echo.
)

REM --- Backend virtual environment + dependencies ---
cd /d "%ROOT%backend"
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul 2>nul
echo [INFO] Installing backend dependencies (this can take a while)...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install backend dependencies.
    pause
    exit /b 1
)

REM --- Frontend dependencies ---
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    echo [INFO] Installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
)

cd /d "%ROOT%"

echo.
echo [INFO] Starting the FastAPI backend on http://localhost:8000 ...
start "RAGify Backend" cmd /k "pushd "%ROOT%backend" && call .venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo [INFO] Starting the Next.js frontend on http://localhost:3000 ...
start "RAGify Frontend" cmd /k "pushd "%ROOT%frontend" && npm run dev"

echo.
echo [INFO] Waiting for the servers to boot...
timeout /t 8 /nobreak >nul

echo [INFO] Opening http://localhost:3000 in your default browser...
start "" "http://localhost:3000"

echo.
echo ============================================================
echo  RAGify AI is running:
echo    Frontend : http://localhost:3000
echo    Backend  : http://localhost:8000
echo    API docs : http://localhost:8000/docs
echo.
echo  First run downloads the embedding model (~90 MB) and may
echo  take a couple of minutes. Close the "RAGify Backend" and
echo  "RAGify Frontend" windows to stop the servers.
echo ============================================================
echo.
pause
