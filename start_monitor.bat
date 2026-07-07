@echo off
title Investment Bot - Monitor (read-only)
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul

echo.
echo  ========================================
echo   Monitor v2 - Dashboard read-only
echo  ========================================
echo.
echo  La dashboard legge data\status.json (scritto dal bot a ogni ciclo).
echo  Avvia prima il bot con start_bot_loop.bat.
echo.

:: Trova IP locale per l'accesso da telefono (stessa WiFi)
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /R "IPv4"') do (
    set LOCAL_IP=%%i
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo  Su questo PC:
echo    http://localhost:8080/ui/monitor.html?src=/data/status.json
echo.
echo  Sul telefono (stessa rete WiFi):
echo    http://%LOCAL_IP%:8080/ui/monitor.html?src=/data/status.json
echo.
echo  Premi CTRL+C per fermare.
echo  ========================================
echo.

python -m http.server 8080 --bind 0.0.0.0
pause
