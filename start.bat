@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo    SmartShop v2.0
echo    LangGraph + MCP SDK + SSE
echo ============================================================
echo.

:: ====================================================================
:: Python
:: ====================================================================
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe
set VENV_STREAMLIT=%~dp0.venv\Scripts\streamlit.exe

if not exist "%VENV_PYTHON%" (
    echo [ERROR] .venv not found!
    echo         Please run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo [ OK ] .venv

:: Check deps
"%VENV_PYTHON%" -c "import mcp, langgraph, streamlit, uvicorn, fastapi, pymysql, openai; print('[ OK ] All deps OK')" 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Dependencies missing, installing...
    "%VENV_PYTHON%" -m pip install -r requirements.txt -q
)
echo.

:: ====================================================================
:: MySQL
:: ====================================================================
echo [CHECK] MySQL...
mysqladmin ping -h 127.0.0.1 --silent 2>nul
if %errorlevel% neq 0 (
    echo [WARN] MySQL not responding, please start MySQL 8.0 first
    echo        Download: https://dev.mysql.com/downloads/
    pause
    exit /b 1
)
echo [ OK ] MySQL connected
echo.

:: ====================================================================
:: Kill old processes on target ports
:: ====================================================================
echo [CLEAN] Freeing ports 8100 8101 8008 8502...
for %%p in (8100 8101 8008 8502) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        echo   Port %%p occupied by PID %%a, killing...
        taskkill /PID %%a /F >nul 2>&1
    )
)
echo [ OK ] Ports freed
timeout /t 2 /nobreak >nul
echo.

:: ====================================================================
:: Launch all 4 services (using cmd /c wrapper for reliable quoting)
:: ====================================================================
echo ============================================================
echo   Starting 4 services...
echo ============================================================
echo.

echo [START] Product MCP Server (port 8100)...
start "SmartShop-ProductMCP" cmd /c "cd /d "%~dp0" && "%VENV_PYTHON%" -m uvicorn mcp_servers.mcp_product_server:app --host 127.0.0.1 --port 8100"

echo [START] Order MCP Server (port 8101)...
start "SmartShop-OrderMCP" cmd /c "cd /d "%~dp0" && "%VENV_PYTHON%" -m uvicorn mcp_servers.mcp_order_server:app --host 127.0.0.1 --port 8101"

echo [WAIT] MCP Servers starting...
timeout /t 4 /nobreak >nul
echo.

echo [START] A2A Router Server (port 8008)...
start "SmartShop-Router" cmd /c "cd /d "%~dp0" && "%VENV_PYTHON%" -m uvicorn core.router_A2Aagent_Server:app --host 127.0.0.1 --port 8008"

echo [WAIT] Router starting...
timeout /t 4 /nobreak >nul
echo.

echo [START] Streamlit Frontend (port 8502)...
start "SmartShop-Streamlit" cmd /c "cd /d "%~dp0" && "%VENV_STREAMLIT%" run main.py --server.port 8502"

echo [WAIT] Frontend starting...
timeout /t 5 /nobreak >nul

echo.
echo ============================================================
echo   SmartShop v2.0 -- All services started!
echo ============================================================
echo.
echo   Frontend:    http://localhost:8502
echo   API Docs:    http://localhost:8008/docs
echo   Health:      http://localhost:8008/api/health
echo.
echo   Stop:        Double-click stop.bat or close the 4 windows
echo ============================================================
echo.
pause
