@echo off
REM Check Project KG Chatbot Server Status
REM Usage: status.bat [port]

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Project KG Chatbot - Server Status
echo ========================================
echo.

REM Check if port is listening
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo Status: RUNNING
    echo.
    echo Server Details:
    for /f "tokens=2,5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
        echo   Address: %%a
        echo   PID: %%b
    )
    echo.
    echo Testing endpoint...
    curl -s -o nul -w "  HTTP Response: %%{http_code}" http://127.0.0.1:%PORT%/login
    echo.
    echo.
    echo Open in browser: http://127.0.0.1:%PORT%/login
) else (
    echo Status: STOPPED
    echo.
    echo Run start_server.bat to start the server.
)

echo.
echo ========================================
endlocal
