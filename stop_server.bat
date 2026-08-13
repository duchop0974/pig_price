@echo off
chcp 65001 >nul
cd /d "%~dp0"

set found=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    set found=1
)

if "%found%"=="1" (
    echo Da dung web server.
) else (
    echo Khong co server nao dang chay tren cong 5000.
)
echo.
echo Luu y: neu tunnel (start_tunnel.bat) van dang chay, no se tu bao loi
echo "khong ket noi duoc" cho toi khi ban chay lai start_server.bat.
echo Muon dung ca tunnel, chay them stop_tunnel.bat.
pause
