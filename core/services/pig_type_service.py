"""Service layer cho danh mục Loại heo bán (pig_types) — nối dài Service
Layer sang phần quản trị, theo STEP 4 (Transaction Standardization) của
PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp đúng 1 lần ghi repo +
1 lần audit_log vào chung 1 transaction qua run_in_transaction. Validate
nghiệp vụ (trùng code, còn kế hoạch/delivery tham chiếu...) giữ ở route
layer."""
from pathlib import Path

from core import audit_actions
from core.db import run_in_transaction
from core.repositories import audit_repo, pig_types_repo

_write = run_in_transaction


def create_pig_type(code: str, name: str, db_path: Path, *, ip=None, username=None) -> int:
    result = {}

    def _do(conn):
        pig_type_id = pig_types_repo.create_pig_type(code, name, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.PIG_TYPE_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="pig_type",
            entity_id=pig_type_id,
            new_value={"code": code, "name": name},
            conn=conn,
        )
        result["pig_type_id"] = pig_type_id

    _write(db_path, _do)
    return result["pig_type_id"]


def update_pig_type(
    pig_type_id: int, code: str, name: str, old_pig_type: dict, db_path: Path, *, ip=None, username=None
) -> None:
    def _do(conn):
        pig_types_repo.update_pig_type(pig_type_id, code, name, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.PIG_TYPE_UPDATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="pig_type",
            entity_id=pig_type_id,
            old_value={"code": old_pig_type["code"], "name": old_pig_type["name"]},
            new_value={"code": code, "name": name},
            conn=conn,
        )

    _write(db_path, _do)


def set_active(pig_type_id: int, is_active: bool, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        pig_types_repo.set_pig_type_active(pig_type_id, is_active, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.PIG_TYPE_ACTIVATE if is_active else audit_actions.PIG_TYPE_DEACTIVATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="pig_type",
            entity_id=pig_type_id,
            conn=conn,
        )

    _write(db_path, _do)


def delete_pig_type(pig_type_id: int, old_pig_type: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        pig_types_repo.delete_pig_type(pig_type_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.PIG_TYPE_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="pig_type",
            entity_id=pig_type_id,
            old_value={"code": old_pig_type["code"], "name": old_pig_type["name"]},
            conn=conn,
        )

    _write(db_path, _do)
