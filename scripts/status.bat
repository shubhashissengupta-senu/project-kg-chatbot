@echo off
REM Delivery Brain - Server Status Script (Windows)
REM Usage: status.bat [port]
REM Default port: 8888

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Delivery Brain - Server Status
echo ========================================
echo.

REM Check if server is running
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >/dev/null 2>&1
if %ERRORLEVEL%==0 (
    echo Status: RUNNING
    echo.
    echo Server Details:
    netstat -ano | findstr ":%PORT% " | findstr "LISTENING"
    echo.
    echo Access URLs:
    echo   Login:      http://127.0.0.1:%PORT%/login
    echo   Dashboard:  http://127.0.0.1:%PORT%/dashboard
    echo   Chat:       http://127.0.0.1:%PORT%/chat
    echo   Graph:      http://127.0.0.1:%PORT%/graph
    echo   Simulation: http://127.0.0.1:%PORT%/simulation
) else (
    echo Status: STOPPED
    echo.
    echo Run start_server.bat to start the server.
)

echo.
endlocal
