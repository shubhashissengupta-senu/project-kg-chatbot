@echo off
REM Stop Project KG Chatbot Server
REM Usage: stop_server.bat [port]

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Project KG Chatbot - Stopping Server
echo ========================================
echo.

REM Find and kill process on the specified port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Found server process: PID %%a
    taskkill /F /PID %%a >nul 2>&1
    if %errorlevel%==0 (
        echo Server stopped successfully.
    ) else (
        echo Failed to stop process %%a
    )
    goto :done
)

echo No server found running on port %PORT%.

:done
echo.
endlocal
