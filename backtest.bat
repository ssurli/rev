@echo off
title Investment Bot - Backtest
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    pause
    exit /b 1
)

echo.
echo  ========================================
echo   Backtest offline su candele storiche
echo  ========================================
echo.

set /p SYM="Simbolo [BTC-USD]: "
if "%SYM%"=="" set SYM=BTC-USD

set /p PER="Periodo [2y]: "
if "%PER%"=="" set PER=2y

set /p CAP="Capitale EUR [200]: "
if "%CAP%"=="" set CAP=200

echo.
python -m backtest.run_backtest --symbol %SYM% --period %PER% --equity %CAP%
pause
