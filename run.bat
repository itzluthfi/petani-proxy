@echo off
chcp 65001 >nul
title PetaniProxy - Panen Proxy Segar by @itzluthfi
mode con: cols=108 lines=40
cd /d "%~dp0"

echo ========================================================================
echo   🌾 Starting PetaniProxy: Panen Proxy Bersih, Segar & Residential 🚜
echo ========================================================================

:: Smart Python Detection (Local project venv -> Parent workspace venv -> System python)
set "PY_CMD=python"
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0..\venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0..\venv\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0..\.venv\Scripts\python.exe"
)

:: Check Python availability
%PY_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan di sistem Anda!
    echo Silakan install Python 3.8+ dari https://www.python.org/
    echo Pastikan centang "Add Python to PATH" saat instalasi.
    pause
    exit /b 1
)

:: Auto install dependencies if missing
%PY_CMD% -c "import httpx, requests, colorama, DrissionPage, speech_recognition" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [SETUP] Memasang paket dependencies untuk pengguna baru...
    %PY_CMD% -m pip install -r requirements.txt
    echo.
)

:: Run Harvester Interactive Menu
%PY_CMD% main.py
pause
