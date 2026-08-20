"""Service layer cho Authorization (RBAC + Data Scope) — STEP 3 của
PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. KHÔNG rewrite RBAC hiện có
(roles/role_permissions/user_farms) — tài liệu nói rõ nền tảng đã đủ, chỉ
tách phần LOGIC kiểm tra quyền ra khỏi webapp/routes/auth.py thành hàm
thuần (nhận `user: dict | None`, không đụng Flask `session` trực tiếp), để
route layer chỉ còn lo đúng phần HTTP (đọc session, redirect, jsonify) theo
nguyên tắc Route/Service trong tài liệu.

webapp/routes/auth.py giữ nguyên các hàm/decorator cũ
(current_user_permissions/current_user_can/allowed_farm_ids/
permission_required) làm wrapper mỏng gọi vào đây — 6 file đang import
chúng (admin.py/dashboard.py/deliveries.py/incidents.py/plans.py) không cần
đổi gì."""
from pathlib import Path

from core.db import db_lock
from core.repositories import roles_repo, users_repo

FARM_ROLE = "farm"


def effective_permissions(user: dict | None, db_path: Path) -> set[str]:
    """Tập quyền hiệu lực của user — set rỗng nếu chưa đăng nhập (user=None).
    Giữ nguyên db_lock quanh lệnh đọc — đúng quy ước hiện có của
    webapp/data_access.py (mọi hàm *_locked(), kể cả đọc, đều nắm db_lock
    trước khi mở connection), không phải riêng ghi mới cần khoá."""
    if not user:
        return set()
    with db_lock:
        return roles_repo.effective_permissions(user["role"], db_path)


def has_permission(user: dict | None, permission_key: str, db_path: Path) -> bool:
    return permission_key in effective_permissions(user, db_path)


def has_any_permission(user: dict | None, permission_keys, db_path: Path) -> bool:
    """True nếu user có ÍT NHẤT 1 trong các quyền truyền vào — dùng cho
    @permission_required(*keys), nơi nhiều quyền có thể thay thế nhau cho
    cùng 1 hành động."""
    return bool(effective_permissions(user, db_path) & set(permission_keys))


def allowed_farm_ids(user: dict, db_path: Path) -> list[int] | None:
    """None = không giới hạn theo trại (sales/accounting/admin xem được mọi
    trại). list[int] = các trại được gán cho tài khoản vai trò 'farm' (có
    thể rỗng nếu admin chưa gán trại nào)."""
    if user["role"] != FARM_ROLE:
        return None
    with db_lock:
        return users_repo.list_farm_ids_for_user(user["id"], db_path)
