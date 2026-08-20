"""Hộp thư Thông báo (Phase 5, brief nghiệp vụ) — bản ghi PERSIST nhắm tới
1 người dùng cụ thể, có trạng thái đọc/chưa đọc riêng từng người. Khác
audit_log (lịch sử mọi hành động, không ai "đọc") và Cảnh báo/Cần xử lý
(tính động lúc đọc trang, không lưu bản ghi) — xem core/db.py cho lý do
tách 3 khái niệm này."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def create_notification(
    recipient_username: str,
    title: str,
    body: str | None,
    link_url: str | None,
    db_path: Path,
    conn: sqlite3.Connection | None = None,
) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO notifications (recipient_username, title, body, link_url, is_read, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (recipient_username, title, body, link_url, datetime.now().isoformat(timespec="seconds")),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def list_for_user(username: str, db_path: Path, limit: int = 50) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, body, link_url, is_read, created_at FROM notifications "
            "WHERE recipient_username = ? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_unread(username: str, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE recipient_username = ? AND is_read = 0", (username,)
        ).fetchone()[0]
    finally:
        conn.close()


def mark_read(notification_id: int, username: str, db_path: Path) -> bool:
    """Chỉ đánh dấu đọc được bản ghi CỦA CHÍNH MÌNH — chặn ở tầng SQL (WHERE
    recipient_username = ?) thay vì chỉ kiểm tra ở route, phòng route quên
    check."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND recipient_username = ?",
            (notification_id, username),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_all_read(username: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE recipient_username = ? AND is_read = 0", (username,))
        conn.commit()
    finally:
        conn.close()
