@echo off
REM Start Project KG Chatbot Server
REM Usage: start_server.bat [port]

setlocal

set PORT=%1
if "%PORT%"=="" set PORT=8888

echo ========================================
echo   Project KG Chatbot - Starting Server
echo ========================================
echo.

cd /d "%~dp0.."

REM Check if port is already in use
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo ERROR: Port %PORT% is already in use.
    echo Run stop_server.bat first or use a different port.
    echo.
    pause
    exit /b 1
)

echo Starting server on http://127.0.0.1:%PORT%
echo.
echo Demo Accounts:
echo   roshan / demo123   (QA Director)
echo   krutika / demo123  (Delivery Lead)
echo   tara / demo123     (Onsite Lead)
echo   rick / demo123     (Auditor)
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

python -m uvicorn app:app --host 127.0.0.1 --port %PORT%

endlocal
