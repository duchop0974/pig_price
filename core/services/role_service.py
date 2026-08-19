"""Service layer cho Vai trò & phân quyền tuỳ biến (roles/role_permissions)
— nối dài Service Layer sang phần quản trị, theo STEP 4 (Transaction
Standardization) của PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp
đúng 1 lần ghi repo + 1 lần audit_log vào chung 1 transaction qua
run_in_transaction. Validate nghiệp vụ (role 'admin' bất khả xâm phạm,
role hệ thống không xoá được, còn tài khoản dùng role...) giữ ở route
layer."""
from pathlib import Path

from core import audit_actions
from core.db import run_in_transaction
from core.repositories import audit_repo, roles_repo

_write = run_in_transaction


def create_role(key: str, name: str, db_path: Path, *, ip=None, username=None) -> None:
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
