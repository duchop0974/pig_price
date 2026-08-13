@echo off
chcp 65001 >nul

tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I "cloudflared.exe" >nul
if errorlevel 1 (
    echo Khong co tunnel nao dang chay.
) else (
    taskkill /F /IM cloudflared.exe >nul 2>&1
    echo Da dung tunnel. Link cong khai (trycloudflare.com) se ngung hoat dong.
    echo Chay lai start_tunnel.bat se tao ra mot link MOI khac voi link cu.
)
pause
