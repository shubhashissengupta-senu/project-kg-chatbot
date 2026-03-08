@echo off
REM Delivery Brain - Start Server Script (Windows)
REM Usage: start_server.bat [port]
REM Default port: 8888

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Delivery Brain Server
echo ========================================
echo.
echo Starting server on port %PORT%...
echo.

cd /d "%~dp0.."

REM Check if port is in use
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >NUL 2>&1
if %ERRORLEVEL%==0 (
    echo ERROR: Port %PORT% is already in use!
    echo Run stop_server.bat first or use a different port.
    exit /b 1
)

REM Start the server
echo Server starting... (this takes ~30 seconds for initialization)
echo.
python -m uvicorn app:app --host 127.0.0.1 --port %PORT%

endlocal
