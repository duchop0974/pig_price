"""Service layer cho Vai trò & phân quyền tuỳ biến (roles/role_permissions)
— nối dài Service Layer sang phần quản trị, theo STEP 4 (Transaction
Standardization) của PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp
đúng 1 lần ghi repo + 1 lần audit_log vào chung 1 transaction qua
run_in_transaction.

STEP 7 (Route Refactor): validate định dạng key/name/trùng mã + danh sách
permission_keys hợp lệ đã chuyển vào service. Guard đặc biệt "role 'admin'
bất khả xâm phạm" (chặn sửa/xoá) VÀ "còn tài khoản dùng role" khi xoá VẪN
ở route layer — đây là bất biến bảo mật gắn với định danh 'admin' + tham
chiếu sang domain khác (users), không phải validate input thuần, khớp
nguyên tắc phạm vi đã dùng cho user_service (self-delete guard)."""
import re
from pathlib import Path

from core import audit_actions
from core import permissions as perm
from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, roles_repo

_write = run_in_transaction

ROLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


def _validate_role_fields(key: str, name: str, db_path: Path) -> None:
    if not ROLE_KEY_RE.match(key):
        raise ValueError("Mã vai trò không hợp lệ (chỉ chữ thường/số/gạch dưới, bắt đầu bằng chữ, 2-30 ký tự).")
    if not name or len(name) > 50:
        raise ValueError("Vui lòng nhập tên vai trò hợp lệ.")
    with db_lock:
        existing = roles_repo.get_role(key, db_path)
    if existing is not None:
        raise ValueError("Mã vai trò đã tồn tại.")


def _validate_permission_keys(permission_keys) -> None:
    if not isinstance(permission_keys, list) or any(k not in perm.ALL_PERMISSION_KEYS for k in permission_keys):
        raise ValueError("Danh sách quyền không hợp lệ.")


def create_role(key: str, name: str, db_path: Path, *, ip=None, username=None) -> None:
    _validate_role_fields(key, name, db_path)

    def _do(conn):
        roles_repo.create_role(key, name, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ROLE_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="role",
            entity_id=key,
            new_value={"key": key, "name": name},
            conn=conn,
        )

    _write(db_path, _do)


def delete_role(role_key: str, old_role: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        roles_repo.delete_role(role_key, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ROLE_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="role",
            entity_id=role_key,
            old_value={"key": role_key, "name": old_role["name"]},
            conn=conn,
        )

    _write(db_path, _do)


def update_permissions(
    role_key: str, permission_keys: list[str], old_keys: list[str], db_path: Path, *, ip=None, username=None
) -> None:
    _validate_permission_keys(permission_keys)

    def _do(conn):
        roles_repo.set_permissions_for_role(role_key, permission_keys, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ROLE_UPDATE_PERMISSIONS,
            db_path,
            username=username,
            ip=ip,
            entity_type="role",
            entity_id=role_key,
            old_value={"permission_keys": old_keys},
            new_value={"permission_keys": permission_keys},
            conn=conn,
        )

    _write(db_path, _do)
