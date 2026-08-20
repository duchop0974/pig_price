"""CRUD cho vai trò (role) tuỳ biến + quyền gán cho từng role. Thay cho danh
sách 5 role cố định hardcode trong routes/auth.py trước đây."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection
from core.permissions import ALL_PERMISSION_KEYS

ROLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


def list_roles(db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key, name, is_system, created_at FROM roles ORDER BY is_system DESC, key ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_role(role_key: str, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT key, name, is_system, created_at FROM roles WHERE key = ?", (role_key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_role(key: str, name: str, db_path: Path, conn: sqlite3.Connection | None = None) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO roles (key, name, is_system, created_at) VALUES (?, ?, 0, ?)",
            (key, name, datetime.now().isoformat(timespec="seconds")),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def delete_role(role_key: str, db_path: Path, conn: sqlite3.Connection | None = None) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM role_permissions WHERE role_key = ?", (role_key,))
        conn.execute("DELETE FROM roles WHERE key = ?", (role_key,))
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def count_users_with_role(role_key: str, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (role_key,)).fetchone()[0]
    finally:
        conn.close()


def list_permissions_for_role(role_key: str, db_path: Path) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT permission_key FROM role_permissions WHERE role_key = ?", (role_key,)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


_FARM_ROLE_KEY = "farm"
_FARM_ROLE_EXPECTED_PERMISSIONS = ("plans.create", "plans.receive")


def list_unexpected_farm_permissions(
    db_path: Path, expected: tuple[str, ...] = _FARM_ROLE_EXPECTED_PERMISSIONS
) -> list[str]:
    """Exception Center (STEP 10): quyền role 'farm' đang có NGOÀI phạm vi
    mặc định — tín hiệu giám sát sống cho đúng rủi ro đã vá ở STEP 3
    (farm-scope check): nếu admin lỡ cấp thêm quyền review/delete/... cho
    role 'farm' qua /admin/permissions, user vai trò farm sẽ thao tác
    được trên dữ liệu của BẤT KỲ trại nào, không chỉ trại được gán."""
    current = list_permissions_for_role(_FARM_ROLE_KEY, db_path)
    return sorted(key for key in current if key not in expected)


def set_permissions_for_role(
    role_key: str, permission_keys: list[str], db_path: Path, conn: sqlite3.Connection | None = None
) -> None:
    """Ghi đè toàn bộ tập quyền của 1 role — xoá cũ rồi chèn lại danh sách
    mới, cùng UX "tick chọn lại rồi Lưu" như assign_user_farms."""
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM role_permissions WHERE role_key = ?", (role_key,))
        conn.executemany(
            "INSERT INTO role_permissions (role_key, permission_key) VALUES (?, ?)",
            [(role_key, key) for key in permission_keys],
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def effective_permissions(role_key: str, db_path: Path) -> set[str]:
    """Tập quyền hiệu lực của 1 role. Role 'admin' luôn có toàn quyền, hardcode
    ở đây (không qua bảng role_permissions) — escape hatch để không ai tự
    khoá được quyền quản trị qua trang /admin/permissions."""
    if role_key == "admin":
        return set(ALL_PERMISSION_KEYS)
    return set(list_permissions_for_role(role_key, db_path))
