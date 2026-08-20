"""Resolve người nhận + ghi Thông báo (Phase 5, brief nghiệp vụ) — gọi
cạnh audit_repo.log_action() ở các service khác, LUÔN trong cùng
transaction (conn bắt buộc, không tự mở connection riêng).

QUAN TRỌNG: notify() chạy bên trong 1 transaction ghi đang mở
(run_in_transaction đã BEGIN nhưng chưa COMMIT trên `conn`). Nếu gọi các
hàm repo đọc kiểu users_repo.list_users()/roles_repo.effective_permissions()
(mỗi hàm tự mở connection riêng qua core.db.get_connection(), mà
get_connection() luôn chạy executescript(_DB_SCHEMA) — 1 thao tác kiểu ghi
schema) thì connection mới đó sẽ tranh khoá ghi với `conn` đang mở transaction
=> deadlock/timeout dây chuyền (đã tự gặp lúc build: pytest treo >120s vì
mỗi user trong vòng lặp notify() phải chờ hết busy-timeout 10s của
get_connection()). Vì vậy toàn bộ đọc dữ liệu người nhận ở đây dùng thẳng
`conn` được truyền vào, không qua tầng repo mở connection riêng."""
import sqlite3
from pathlib import Path

from core.permissions import ALL_PERMISSION_KEYS
from core.repositories import notifications_repo

_FARM_ROLE = "farm"
_ADMIN_ROLE = "admin"


def _effective_permissions(role: str, conn: sqlite3.Connection) -> set[str]:
    if role == _ADMIN_ROLE:
        return set(ALL_PERMISSION_KEYS)
    rows = conn.execute("SELECT permission_key FROM role_permissions WHERE role_key = ?", (role,)).fetchall()
    return {r[0] for r in rows}


def notify(
    permission_key: str,
    title: str,
    body: str | None,
    link_url: str | None,
    db_path: Path,
    *,
    conn: sqlite3.Connection,
    farm_id: int | None = None,
    exclude_username: str | None = None,
) -> None:
    users = conn.execute("SELECT id, username, role FROM users WHERE is_active = 1").fetchall()
    for user_id, username, role in users:
        if username == exclude_username:
            continue
        if permission_key not in _effective_permissions(role, conn):
            continue
        if farm_id is not None and role == _FARM_ROLE:
            assigned = conn.execute(
                "SELECT 1 FROM user_farms WHERE user_id = ? AND farm_id = ?", (user_id, farm_id)
            ).fetchone()
            if not assigned:
                continue
        notifications_repo.create_notification(username, title, body, link_url, db_path, conn=conn)
