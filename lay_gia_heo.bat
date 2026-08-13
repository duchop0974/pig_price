@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python truoc roi chay lai.
    pause
    exit /b 1
)

python -c "import requests, bs4, lxml, pandas" >nul 2>&1
if errorlevel 1 (
    echo Lan dau chay, dang cai dat thu vien can thiet...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [LOI] Cai dat thu vien that bai. Kiem tra ket noi mang roi thu lai.
        pause
        exit /b 1
    )
    echo Cai dat xong.
)

:menu
cls
echo ============================================
echo   GIA HEO HOI - so sanh nhieu nguon
echo   (nongnghiepmoitruong.vn, vietnambiz.vn, greenfeed.com.vn)
echo ============================================
echo.
echo   1. Xem gia hom nay (so sanh cac nguon)
echo   2. Xem gia theo ngay cu the
echo   3. Lay du lieu gan day (backfill) - tat ca nguon
echo   4. Lay 1 bai viet theo URL (nongnghiepmoitruong/vietnambiz)
echo   5. Mo file du lieu CSV
echo   6. Khoi dong web server (xem tren dien thoai/trinh duyet)
echo   7. Khoi dong LAI web server (sau khi doi mat khau, sua code...)
echo   8. DUNG web server
echo   9. Tao duong link xem tu Internet (Cloudflare Tunnel)
echo   10. DUNG duong link Internet (tunnel)
echo   11. Xem lich su truy cap (ai da vao xem gia)
echo   12. Thoat
echo.
set /p chon="Chon (1-12): "

if "%chon%"=="1" goto today
if "%chon%"=="2" goto bydate
if "%chon%"=="3" goto backfill
if "%chon%"=="4" goto url
if "%chon%"=="5" goto openfile
if "%chon%"=="6" goto webserver
if "%chon%"=="7" goto restartserver
if "%chon%"=="8" goto stopserver
if "%chon%"=="9" goto tunnel
if "%chon%"=="10" goto stoptunnel
if "%chon%"=="11" goto accesslog
if "%chon%"=="12" goto end
goto menu

:today
python pig_price_scraper.py --source all --mode today
pause
goto menu

:bydate
set /p ngay="Nhap ngay can xem (dd/mm/yyyy): "
python pig_price_scraper.py --source all --mode date --date %ngay%
pause
goto menu

:backfill
set /p soluong="Nhap so bai muon lay moi nguon (mac dinh 20): "
if "%soluong%"=="" set soluong=20
python pig_price_scraper.py --source all --mode backfill --limit %soluong%
pause
goto menu

:url
set /p link="Dan URL bai viet: "
set nguon=nongnghiepmoitruong
echo %link% | findstr /i "vietnambiz.vn" >nul
if not errorlevel 1 set nguon=vietnambiz
python pig_price_scraper.py --source %nguon% --mode url --url "%link%"
pause
goto menu

:openfile
if exist "data\gia_heo_hoi.csv" (
    start "" "data\gia_heo_hoi.csv"
) else (
    echo Chua co file du lieu. Hay lay du lieu truoc.
    pause
)
goto menu

:webserver
call start_server.bat
goto menu

:restartserver
call restart_server.bat
goto menu

:stopserver
call stop_server.bat
goto menu

:tunnel
call start_tunnel.bat
goto menu

:stoptunnel
call stop_tunnel.bat
goto menu

:accesslog
if exist "webapp\access.log" (
    echo.
    echo === 50 luot truy cap gan nhat ===
    powershell -NoProfile -Command "Get-Content 'webapp\access.log' -Tail 50 -Encoding UTF8"
    echo.
) else (
    echo Chua co du lieu truy cap - chi ghi log tu lan khoi dong server gan day nhat.
)
pause
goto menu

:end
endlocal
exit /b 0
