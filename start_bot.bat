@echo off
title Investment Bot
cd /d "%~dp0"

echo.
echo  ========================================
echo   Investment Bot - PAPER MODE
echo  ========================================
echo.

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    echo Esegui prima: python -m venv .venv
    pause
    exit /b 1
)

python main.py
pause
