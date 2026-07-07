@echo off
title Investment Bot - PAPER LOOP 24/7
cd /d "%~dp0"

echo.
echo  ========================================
echo   Investment Bot v2 - PAPER LOOP 24/7
echo  ========================================
echo.

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    echo Esegui prima: python -m venv .venv ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

echo Modalita PAPER - ordini simulati, nessun rischio.
echo Un ciclo ogni CYCLE_INTERVAL_MINUTES (default 30).
echo Kill-switch: chiudi con CTRL+C oppure lancia safety.bat.
echo.

python main.py --loop
pause
