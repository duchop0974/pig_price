"""Ghi & đọc lịch sử hoạt động (đăng nhập, tạo/sửa/xóa kế hoạch...)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def log_action(action: str, db_path: Path, username: str | None = None, detail: str | None = None, ip: str | None = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log (at, username, action, detail, ip) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), username, action, detail, ip),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_log(db_path: Path, limit: int = 200) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT at, username, action, detail, ip FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
