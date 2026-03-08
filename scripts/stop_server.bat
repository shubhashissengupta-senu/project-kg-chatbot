@echo off
REM Delivery Brain - Stop Server Script (Windows)
REM Usage: stop_server.bat [port]
REM Default port: 8888

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Delivery Brain - Stop Server
echo ========================================
echo.

REM Find and kill process on the port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Stopping process %%a on port %PORT%...
    taskkill /F /PID %%a >NUL 2>&1
    if %ERRORLEVEL%==0 (
        echo Server stopped successfully.
    ) else (
        echo Failed to stop process %%a
    )
    goto :done
)

echo No server found running on port %PORT%.

:done
endlocal
