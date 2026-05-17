@echo off
REM ==================================================================
REM  The Rift — Draft Sync Host
REM  Double-click to start hosting a synced draft session.
REM
REM  Starts two things in their own windows:
REM    1. FastAPI sync server on localhost:8000
REM    2. ngrok tunnel exposing it at:
REM         https://wife-reason-unseeing.ngrok-free.dev
REM
REM  Close either window (or run stop_sync_host.bat) to stop hosting.
REM ==================================================================

set NGROK_EXE=C:\Users\blhei\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe
set SERVER_DIR=%~dp0
set TUNNEL_URL=https://wife-reason-unseeing.ngrok-free.dev

echo Starting Draft Sync server...
start "Rift Sync Server" cmd /k "cd /d %SERVER_DIR% && python main.py"

REM Give the server a moment to bind to :8000 before the tunnel attaches.
timeout /t 2 /nobreak >nul

echo Starting ngrok tunnel...
REM cmd /k quoting rule: when the full /k argument contains nested quotes,
REM cmd strips one leading + trailing quote, so write the path with normal
REM "..." inside an outer "...". The "\""path"\"" form from earlier produced
REM literal backslash-quote chars and ngrok failed to launch.
start "Rift Sync Tunnel" cmd /k ""%NGROK_EXE%" http --url=%TUNNEL_URL% 8000"

echo.
echo ==================================================
echo  HOSTING.  Public URL:  %TUNNEL_URL%
echo.
echo  Friends open The Rift, click JOIN SYNCED DRAFT,
echo  and use whatever room code + password you choose.
echo.
echo  Leave the two new windows open while you draft.
echo  Run stop_sync_host.bat (or close them) when done.
echo ==================================================
echo.
pause
