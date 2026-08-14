"""CRUD + xác thực cho bảng users. Mật khẩu chỉ lưu dạng hash (werkzeug)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from core.db import get_connection

USER_COLUMNS = ["id", "username", "display_name", "role", "is_active", "created_at"]


def create_user(
    username: str,
    password: str,
    db_path: Path,
    display_name: str | None = None,
    role: str = "user",
) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, is_active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (
                username,
                generate_password_hash(password),
                display_name or username,
                role,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_users(db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {', '.join(USER_COLUMNS)} FROM users ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_users(db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def get_user_by_username(username: str, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, username, password_hash, display_name, role, is_active, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_password(username: str, password: str, db_path: Path) -> dict | None:
    """Trả về thông tin user (không có password_hash) nếu đăng nhập đúng và
    tài khoản đang active, ngược lại trả None."""
    user = get_user_by_username(username, db_path)
    if not user or not user["is_active"]:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    user.pop("password_hash")
    return user


def set_user_active(user_id: int, is_active: bool, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()
    finally:
        conn.close()


def reset_password(user_id: int, new_password: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()
