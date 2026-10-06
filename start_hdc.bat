@echo off
setlocal

REM ============================================================
REM HDC AUTOMATION CONTROL SYSTEM
REM High Density Cleaner - Python + OPC DA Honeywell DCS
REM ============================================================

cd /d "%~dp0"
title HDC Automation Control System

REM ------------------------------------------------------------
REM Check virtual environment
REM ------------------------------------------------------------
if not exist "%~dp0_env\Scripts\activate.bat" (
    echo.
    echo [ERROR] Virtual environment tidak ditemukan.
    echo Expected: %~dp0_env\Scripts\activate.bat
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Activate virtual environment
REM ------------------------------------------------------------
call "%~dp0_env\Scripts\activate.bat"

if errorlevel 1 (
    echo.
    echo [ERROR] Gagal mengaktifkan virtual environment.
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Start HDC program
REM ------------------------------------------------------------
echo.
echo ============================================================
echo              HDC AUTOMATION CONTROL SYSTEM
echo ============================================================
echo.
echo Project : %~dp0
echo Python  :
python --version
echo.
echo Starting main.py ...
echo ============================================================
echo.

python main.py

REM ------------------------------------------------------------
REM Keep console open after program exits/crashes
REM ------------------------------------------------------------
echo.
echo ============================================================
echo HDC program telah berhenti.
echo Check error di atas untuk informasi lebih lanjut.
echo ============================================================
echo.
pause

endlocal
