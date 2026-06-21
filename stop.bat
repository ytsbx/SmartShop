@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   SmartShop -- Stop All Services
echo ============================================================
echo.

:: Step 1: Kill by port
for %%p in (8502 8008 8101 8100) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        echo [STOP] Port %%p, PID=%%a
        taskkill /PID %%a /F 2>nul
    )
)

:: Step 2: Kill by window title
echo.
echo [CLEAN] Closing SmartShop windows...
taskkill /FI "WINDOWTITLE eq SmartShop-ProductMCP*" /F 2>nul
taskkill /FI "WINDOWTITLE eq SmartShop-OrderMCP*" /F 2>nul
taskkill /FI "WINDOWTITLE eq SmartShop-Router*" /F 2>nul
taskkill /FI "WINDOWTITLE eq SmartShop-Streamlit*" /F 2>nul

echo.
echo ============================================================
echo   SmartShop -- All services stopped
echo ============================================================
pause
