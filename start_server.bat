@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import flask, apscheduler" >nul 2>&1
if errorlevel 1 (
    echo Lan dau chay web server, dang cai dat thu vien can thiet...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [LOI] Cai dat thu vien that bai.
        pause
        exit /b 1
    )
)

echo Dang khoi dong web server tren cong 5000 (chay nen, khong hien cua so)...
start "PigPriceServer" /min pythonw "%~dp0webapp\app.py"

timeout /t 2 >nul
echo.
echo Server da chay. Truy cap:
echo   - Tren chinh may tinh nay: http://localhost:5000
echo   - Tu dien thoai/may khac cung mang WiFi: http://%COMPUTERNAME%:5000
echo     (hoac dung dia chi IP cua may tinh, xem bang lenh "ipconfig")
echo.
if exist "webapp\password.txt" (
    set /p PW=<webapp\password.txt
    echo Mat khau dang nhap: %PW%
) else (
    echo Mat khau dang nhap se hien sau vai giay, kiem tra file webapp\password.txt
)
echo.
echo De xem duoc tu Internet ben ngoai (khong can cung WiFi), chay them start_tunnel.bat
pause
