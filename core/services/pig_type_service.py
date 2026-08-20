"""Service layer cho danh mục Loại heo bán (pig_types) — nối dài Service
Layer sang phần quản trị, theo STEP 4 (Transaction Standardization) của
PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp đúng 1 lần ghi repo +
1 lần audit_log vào chung 1 transaction qua run_in_transaction.

STEP 7 (Route Refactor): validate định dạng/giá trị + trùng mã đã chuyển
vào service (create/update). Check "còn kế hoạch/delivery tham chiếu" khi
xoá VẪN ở route layer (business rule tham chiếu domain khác, khớp nguyên
tắc phạm vi ở customer_service/farm_service)."""
from pathlib import Path

from core import audit_actions
from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, pig_types_repo

_write = run_in_transaction


def _validate_pig_type_fields(code: str, name: str, db_path: Path, *, exclude_pig_type_id: int | None = None) -> None:
    if not code or len(code) > 30:
        raise ValueError("Mã loại heo không hợp lệ.")
    if not name or len(name) > 100:
        raise ValueError("Tên loại heo không hợp lệ.")
    with db_lock:
        pig_types = pig_types_repo.list_pig_types(db_path)
    if any(pt["code"] == code and pt["id"] != exclude_pig_type_id for pt in pig_types):
        raise ValueError("Mã loại heo đã tồn tại.")


def create_pig_type(code: str, name: str, db_path: Path, *, ip=None, username=None) -> int:
    _validate_pig_type_fields(code, name, db_path)
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
    _validate_pig_type_fields(code, name, db_path, exclude_pig_type_id=pig_type_id)

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
