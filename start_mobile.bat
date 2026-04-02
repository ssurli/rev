@echo off
title Investment Bot - Accesso Mobile
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul

echo.
echo  ========================================
echo   Accesso Mobile - Rete Locale
echo  ========================================

:: Trova IP locale
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /R "IPv4"') do (
    set LOCAL_IP=%%i
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo  Apri sul telefono (stessa rete WiFi):
echo  http://%LOCAL_IP%:8501
echo.
echo  Premi CTRL+C per fermare.
echo  ========================================
echo.

streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501
pause
