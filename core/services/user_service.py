"""Service layer cho quản trị tài khoản (users) — STEP 2/STEP 4 nối dài
sang phần quản trị theo PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm
gộp đúng 1 lần ghi repo + 1 lần audit_log vào chung 1 transaction qua
run_in_transaction, khớp khuôn đã dùng ở plan_service/order_service/
delivery_service/customer_service. Validate nghiệp vụ (trùng username, tự
xoá chính mình, xoá admin cuối cùng, role hợp lệ...) vẫn ở route layer —
route đã có sẵn logic này và cần dữ liệu (list_roles_locked, session user)
mà service không nắm."""
from pathlib import Path

from core import audit_actions
from core.db import run_in_transaction
from core.repositories import audit_repo, users_repo

_write = run_in_transaction


def create_user(
    username: str,
    password: str,
    display_name: str,
    role: str,
    db_path: Path,
    *,
    ip=None,
    actor_username=None,
) -> int:
    result = {}

    def _do(conn):
        user_id = users_repo.create_user(username, password, db_path, display_name=display_name, role=role, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_CREATE,
            db_path,
            username=actor_username,
            ip=ip,
            detail=f"username={username}, role={role}",
            entity_type="user",
            entity_id=user_id,
            new_value={"username": username, "display_name": display_name, "role": role},
            conn=conn,
        )
        result["user_id"] = user_id

    _write(db_path, _do)
    return result["user_id"]


def update_role(user_id: int, role: str, old_role: str, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.update_user_role(user_id, role, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_UPDATE_ROLE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={"role": old_role},
            new_value={"role": role},
            conn=conn,
        )

    _write(db_path, _do)


def assign_farms(user_id: int, farm_ids: list[int], old_farm_ids: list[int], db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.assign_user_farms(user_id, farm_ids, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_ASSIGN_FARMS,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={"farm_ids": old_farm_ids},
            new_value={"farm_ids": farm_ids},
            conn=conn,
        )

    _write(db_path, _do)


def set_active(user_id: int, is_active: bool, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.set_user_active(user_id, is_active, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_ACTIVATE if is_active else audit_actions.USER_DEACTIVATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            conn=conn,
        )

    _write(db_path, _do)


def reset_password(user_id: int, new_password: str, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.reset_password(user_id, new_password, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_RESET_PASSWORD,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            conn=conn,
        )

    _write(db_path, _do)


def delete_user(user_id: int, old_user: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.delete_user(user_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={
                "username": old_user["username"],
                "display_name": old_user["display_name"],
                "role": old_user["role"],
            },
            conn=conn,
        )

    _write(db_path, _do)
