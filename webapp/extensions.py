"""Trạng thái/tài nguyên dùng chung giữa các blueprint: khoá DB, đường dẫn
file, ghi log truy cập & nhật ký hoạt động."""
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import request, session

from core.repositories import audit_repo

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "gia_heo_hoi.db"

# Giữ tên file cũ để người dùng đã quen (trước đây chứa mật khẩu dùng chung,
# giờ chứa mật khẩu của tài khoản admin mặc định được tạo tự động lần đầu).
BOOTSTRAP_PASSWORD_FILE = Path(__file__).resolve().parent / "password.txt"
ACCESS_LOG_PATH = Path(__file__).resolve().parent / "access.log"

db_lock = threading.Lock()

# Trạng thái lần cập nhật giá gần nhất — dùng chung giữa nút "Cập nhật giá hôm
# nay" (routes/prices.py) và cron 7h sáng (scheduler.py) để không cho phép
# cập nhật lại quá dồn dập.
refresh_state = {"last_run": None}
REFRESH_COOLDOWN = timedelta(minutes=1)


def log_access(event: str) -> None:
    user = session.get("user")
    who = user["username"] if user else "chưa đăng nhập"
    line = f"{datetime.now():%d/%m/%Y %H:%M:%S} - {request.remote_addr} - {who} - {event} - {request.path}\n"
    try:
        with open(ACCESS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def log_audit(action: str, detail: str | None = None) -> None:
    user = session.get("user")
    with db_lock:
        audit_repo.log_action(
            action,
            DB_PATH,
            username=user["username"] if user else None,
            detail=detail,
            ip=request.remote_addr,
        )
