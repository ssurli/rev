@echo off
title Investment Bot v2 - Avvio
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    echo Esegui prima: python -m venv .venv ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

:menu
cls
echo.
echo  ============================================
echo    INVESTMENT BOT v2 - MENU
echo  ============================================
echo.
echo   AVVIO
echo    [1] Paper + Monitor  (consigliato: apre 2 finestre)
echo    [2] Solo bot paper (loop 24/7)
echo    [3] Solo monitor (dashboard read-only)
echo    [4] Dashboard Streamlit completa (vecchia)
echo.
echo   STRUMENTI
echo    [5] Backtest
echo    [6] Sicurezza (kill-switch / stato / sblocco)
echo    [7] Un solo ciclo paper (test veloce)
echo.
echo   LIVE
echo    [9] LIVE - denaro reale (richiede conferme .env)
echo.
echo    [0] Esci
echo.
set /p scelta="Scelta: "

if "%scelta%"=="1" goto paper_monitor
if "%scelta%"=="2" ( start "Bot PAPER" cmd /k python main.py --loop & goto menu )
if "%scelta%"=="3" goto monitor
if "%scelta%"=="4" ( start "Streamlit" cmd /k streamlit run dashboard.py & goto menu )
if "%scelta%"=="5" ( call backtest.bat & goto menu )
if "%scelta%"=="6" ( call safety.bat & goto menu )
if "%scelta%"=="7" ( python main.py & pause & goto menu )
if "%scelta%"=="9" ( call start_live.bat & goto menu )
if "%scelta%"=="0" exit /b 0
goto menu

:paper_monitor
echo.
echo Avvio bot paper e monitor in due finestre...
start "Bot PAPER" cmd /k python main.py --loop
timeout /t 3 >nul
start "Monitor" cmd /k python -m http.server 8080 --bind 0.0.0.0
timeout /t 2 >nul
start "" "http://localhost:8080/ui/monitor.html?src=/data/status.json"
echo.
echo  Bot e monitor avviati. Il monitor si popola dopo il primo ciclo.
echo  Dashboard: http://localhost:8080/ui/monitor.html?src=/data/status.json
echo.
pause
goto menu

:monitor
echo.
echo Monitor su http://localhost:8080/ui/monitor.html?src=/data/status.json
start "" "http://localhost:8080/ui/monitor.html?src=/data/status.json"
python -m http.server 8080 --bind 0.0.0.0
goto menu
