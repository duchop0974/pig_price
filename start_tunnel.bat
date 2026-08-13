@echo off
chcp 65001 >nul
cd /d "%~dp0"

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai cloudflared.
    echo Cai bang winget:  winget install --id Cloudflare.cloudflared
    echo Hoac tai thu cong tai: https://github.com/cloudflare/cloudflared/releases/latest
    pause
    exit /b 1
)

set server_running=0
for /f %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do set server_running=1
if "%server_running%"=="0" (
    echo [LOI] Web server chua chay tren cong 5000.
    echo Hay chay start_server.bat truoc, roi moi chay lai file nay.
    pause
    exit /b 1
)

echo ============================================================
echo  Dang tao duong link cong khai qua Cloudflare Tunnel...
echo  Link se hien ben duoi dang: https://xxxx-xxxx.trycloudflare.com
echo  LUU Y: link nay se DOI moi lan ban chay lai file nay
echo  (vd sau khi khoi dong lai may tinh). Chi can quay lai day
echo  de lay link moi.
echo ============================================================
echo.
echo Nho dang nhap bang mat khau trong file webapp\password.txt khi mo link.
echo.
cloudflared tunnel --url http://127.0.0.1:5000
