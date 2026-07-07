@echo off
title Investment Bot - LIVE (denaro reale)
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    pause
    exit /b 1
)

echo.
echo  ########################################
echo  #   ATTENZIONE - MODALITA LIVE         #
echo  #   Ordini con DENARO REALE.           #
echo  ########################################
echo.
echo  Requisiti (altrimenti il bot ricade in PAPER):
echo    - .env: LIVE_TRADING_CONFIRM=YES
echo    - .env: REVOLUT_X_PRIVATE_KEY_PATH impostato (chiave chmod 600)
echo    - backtest e settimane di paper gia' fatti
echo.
set /p CONF="Scrivi CONFERMO per procedere: "
if /I not "%CONF%"=="CONFERMO" (
    echo Annullato.
    pause
    exit /b 0
)

echo.
echo Avvio in LIVE...
python main.py --mode live --confirm-live --loop
pause
