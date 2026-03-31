@echo off
title Investment Bot - Dashboard
cd /d "%~dp0"

echo.
echo  ========================================
echo   Investment Bot - Dashboard Streamlit
echo  ========================================
echo.

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    pause
    exit /b 1
)

echo Avvio dashboard su http://localhost:8501
echo Premi CTRL+C per fermare.
echo.

streamlit run dashboard.py
pause
