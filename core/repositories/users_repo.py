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
    conn: sqlite3.Connection | None = None,
) -> int:
    own_connection = conn is None
    if own_connection:
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
        if own_connection:
            conn.commit()
        return cur.lastrowid
    finally:
        if own_connection:
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


def update_user_role(
    user_id: int, role: str, db_path: Path, conn: sqlite3.Connection | None = None
) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def list_farm_ids_for_user(user_id: int, db_path: Path) -> list[int]:
    """Danh sách id trại được gán cho user — dùng để check quyền nhanh (vai
    trò 'farm'). Rỗng nếu chưa được admin gán trại nào."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT farm_id FROM user_farms WHERE user_id = ?", (user_id,)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def list_farms_for_user(user_id: int, db_path: Path) -> list[dict]:
    """Như list_farm_ids_for_user nhưng kèm code/province — dùng để hiển thị
    UI (form gán trại, danh sách trại của tài khoản farm)."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT f.id, f.code, f.province FROM user_farms uf "
            "JOIN farms f ON f.id = uf.farm_id WHERE uf.user_id = ? ORDER BY f.id ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def assign_user_farms(
    user_id: int, farm_ids: list[int], db_path: Path, conn: sqlite3.Connection | None = None
) -> None:
    """Ghi đè toàn bộ tập trại được gán cho user — xoá liên kết cũ rồi chèn
    lại danh sách mới, khớp UX "tick chọn lại rồi Lưu" của form admin."""
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM user_farms WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO user_farms (user_id, farm_id, created_at) VALUES (?, ?, ?)",
            [(user_id, farm_id, now) for farm_id in farm_ids],
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def set_user_active(
    user_id: int, is_active: bool, db_path: Path, conn: sqlite3.Connection | None = None
) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def delete_user(user_id: int, db_path: Path, conn: sqlite3.Connection | None = None) -> None:
    """Xoá vĩnh viễn 1 tài khoản. Không bảng nào khác FK cứng tới users.id —
    created_by/approved_by/... ở các bảng nghiệp vụ đều là TEXT tự do (chỉ
    lưu username lúc thao tác, không tham chiếu ràng buộc), nên không lo mồ
    côi dữ liệu; chỉ cần dọn user_farms (bảng gán trại, đơn thuần liên kết)."""
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM user_farms WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def reset_password(
    user_id: int, new_password: str, db_path: Path, conn: sqlite3.Connection | None = None
) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()
