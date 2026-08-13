@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Dang dung web server dang chay (neu co)...
set found=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    set found=1
)

if "%found%"=="1" (
    echo Da dung server cu.
) else (
    echo Khong co server nao dang chay tren cong 5000.
)

timeout /t 1 >nul

echo.
echo Dang khoi dong lai server...
call "%~dp0start_server.bat"
