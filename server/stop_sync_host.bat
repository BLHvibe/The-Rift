@echo off
REM Stop the Draft Sync host: closes the server and ngrok windows.

echo Stopping ngrok tunnel...
taskkill /F /IM ngrok.exe /T 2>nul

echo Stopping draft-sync Python server (port 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /F /PID %%a 2>nul
)

echo Done.
timeout /t 2 /nobreak >nul
