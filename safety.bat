@echo off
title Investment Bot - Controlli di sicurezza
cd /d "%~dp0"

call .venv\Scripts\activate.bat 2>nul || (
    echo [ERRORE] Ambiente virtuale non trovato.
    pause
    exit /b 1
)

:menu
cls
echo.
echo  ========================================
echo   Controlli di sicurezza
echo  ========================================
echo.
python -m core.safety --status
echo.
echo  [1] STOP bot ora        (kill-switch ON)
echo  [2] Riprendi            (kill-switch OFF)
echo  [3] Sblocca circuit-breaker (dopo un HALT)
echo  [4] Aggiorna stato
echo  [0] Esci
echo.
set /p scelta="Scelta: "

if "%scelta%"=="1" ( python -m core.safety --kill    & pause & goto menu )
if "%scelta%"=="2" ( python -m core.safety --resume  & pause & goto menu )
if "%scelta%"=="3" ( python -m core.safety --unlock  & pause & goto menu )
if "%scelta%"=="4" ( goto menu )
if "%scelta%"=="0" ( exit /b 0 )
goto menu
