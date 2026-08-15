"""Trạng thái/tài nguyên dùng chung giữa các blueprint: khoá DB, đường dẫn
file, ghi log truy cập & nhật ký hoạt động."""
import logging
import threading
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import request, session

from core.repositories import audit_repo

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "gia_heo_hoi.db"

# Giữ tên file cũ để người dùng đã quen (trước đây chứa mật khẩu dùng chung,
# giờ chứa mật khẩu của tài khoản admin mặc định được tạo tự động lần đầu).
BOOTSTRAP_PASSWORD_FILE = Path(__file__).resolve().parent / "password.txt"
ACCESS_LOG_PATH = Path(__file__).resolve().parent / "access.log"

# access.log ghi MỌI request (kể cả GET không đổi dữ liệu) nên phình nhanh
# hơn audit_log rất nhiều — dùng RotatingFileHandler để tự xoay vòng thay vì
# 1 file text lớn dần vô hạn. audit_log (bảng DB) không cần rotation: dữ
# liệu có cấu trúc, tra cứu/lọc/archive được bằng SQL khi cần.
_access_logger = logging.getLogger("pig_price.access")
_access_logger.setLevel(logging.INFO)
_access_logger.propagate = False
if not _access_logger.handlers:
    _handler = RotatingFileHandler(ACCESS_LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", datefmt="%d/%m/%Y %H:%M:%S"))
    _access_logger.addHandler(_handler)

db_lock = threading.Lock()

# Trạng thái lần cập nhật giá gần nhất — dùng chung giữa nút "Cập nhật giá hôm
# nay" (routes/prices.py) và cron 7h sáng (scheduler.py) để không cho phép
# cập nhật lại quá dồn dập.
refresh_state = {"last_run": None}
REFRESH_COOLDOWN = timedelta(minutes=1)


def log_access(event: str) -> None:
    user = session.get("user")
    who = user["username"] if user else "chưa đăng nhập"
    _access_logger.info("%s - %s - %s - %s", request.remote_addr, who, event, request.path)


def log_audit(
    action: str,
    detail: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    user = session.get("user")
    with db_lock:
        audit_repo.log_action(
            action,
            DB_PATH,
            username=user["username"] if user else None,
            detail=detail,
            ip=request.remote_addr,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
        )
