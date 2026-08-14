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
echo   (nongnghiepmoitruong.vn, vietnambiz.vn, greenfeed.com.vn, vinanet.vn, baovanhoa.vn)
echo ============================================
echo.
echo   1. Xem gia hom nay (so sanh cac nguon)
echo   2. Xem gia theo ngay cu the
echo   3. Lay du lieu gan day (backfill nhanh) - tat ca nguon
echo   4. Lay du lieu SAU (nhieu ngay/thang qua sitemap) - tat ca nguon
echo   5. Lay 1 bai viet theo URL (nongnghiepmoitruong/vietnambiz/vinanet/baovanhoa)
echo   6. Xuat du lieu ra Excel
echo   7. Khoi dong web server (xem tren dien thoai/trinh duyet)
echo   8. Khoi dong LAI web server (sau khi doi mat khau, sua code...)
echo   9. DUNG web server
echo   10. Tao duong link xem tu Internet (Cloudflare Tunnel)
echo   11. DUNG duong link Internet (tunnel)
echo   12. Xem lich su truy cap (ai da vao xem gia)
echo   13. Thoat
echo.
set /p chon="Chon (1-13): "

if "%chon%"=="1" goto today
if "%chon%"=="2" goto bydate
if "%chon%"=="3" goto backfill
if "%chon%"=="4" goto deepbackfill
if "%chon%"=="5" goto url
if "%chon%"=="6" goto openfile
if "%chon%"=="7" goto webserver
if "%chon%"=="8" goto restartserver
if "%chon%"=="9" goto stopserver
if "%chon%"=="10" goto tunnel
if "%chon%"=="11" goto stoptunnel
if "%chon%"=="12" goto accesslog
if "%chon%"=="13" goto end
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

:deepbackfill
echo Che do nay do sitemap/nhieu trang danh muc de lay duoc du lieu cu hon
echo nhieu so voi "backfill nhanh" (nguon nao khong ho tro se tu bo qua).
set /p songay="Muon lay sau bao nhieu ngay ve truoc (mac dinh 30): "
if "%songay%"=="" set songay=30
python pig_price_scraper.py --source all --mode deep-backfill --days %songay%
pause
goto menu

:url
set /p link="Dan URL bai viet: "
set nguon=nongnghiepmoitruong
echo %link% | findstr /i "vietnambiz.vn" >nul
if not errorlevel 1 set nguon=vietnambiz
echo %link% | findstr /i "vinanet.vn" >nul
if not errorlevel 1 set nguon=vinanet
echo %link% | findstr /i "baovanhoa.vn" >nul
if not errorlevel 1 set nguon=baovanhoa
python pig_price_scraper.py --source %nguon% --mode url --url "%link%"
pause
goto menu

:openfile
if not exist "data\gia_heo_hoi.db" (
    echo Chua co du lieu. Hay lay du lieu truoc.
    pause
    goto menu
)
python pig_price_scraper.py --mode export
for /f "delims=" %%f in ('dir /b /o-d "data\gia_heo_hoi_*.xlsx" 2^>nul') do (
    start "" "data\%%f"
    goto menu
)
pause
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
