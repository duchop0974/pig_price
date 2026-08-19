"""Service layer cho danh mục Trang trại / Khu (farms/zones) — nối dài
Service Layer sang phần quản trị, theo STEP 4 (Transaction Standardization)
của PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp đúng 1 lần ghi
repo + 1 lần audit_log vào chung 1 transaction qua run_in_transaction.
Validate nghiệp vụ (trùng code, còn kế hoạch tham chiếu...) giữ ở route
layer, như đã làm cho customer_service/user_service."""
from pathlib import Path

from core import audit_actions
from core.db import run_in_transaction
from core.repositories import audit_repo, farms_repo

_write = run_in_transaction


def create_farm(code: str, province: str | None, db_path: Path, *, ip=None, username=None) -> int:
    result = {}

    def _do(conn):
        farm_id = farms_repo.create_farm(code, province, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.FARM_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="farm",
            entity_id=farm_id,
            new_value={"code": code, "province": province},
            conn=conn,
        )
        result["farm_id"] = farm_id

    _write(db_path, _do)
    return result["farm_id"]


def update_farm(
    farm_id: int, code: str, province: str | None, old_farm: dict, db_path: Path, *, ip=None, username=None
) -> None:
    def _do(conn):
        farms_repo.update_farm(farm_id, code, province, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.FARM_UPDATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="farm",
            entity_id=farm_id,
            old_value={"code": old_farm["code"], "province": old_farm["province"]},
            new_value={"code": code, "province": province},
            conn=conn,
        )

    _write(db_path, _do)


def delete_farm(farm_id: int, old_farm: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        farms_repo.delete_farm(farm_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.FARM_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="farm",
            entity_id=farm_id,
            old_value={"code": old_farm["code"], "province": old_farm["province"]},
            conn=conn,
        )

    _write(db_path, _do)


def create_zone(farm_id: int, code: str, db_path: Path, *, ip=None, username=None) -> int:
    result = {}

    def _do(conn):
        zone_id = farms_repo.create_zone(farm_id, code, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ZONE_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="zone",
            entity_id=zone_id,
            new_value={"farm_id": farm_id, "code": code},
            conn=conn,
        )
        result["zone_id"] = zone_id

    _write(db_path, _do)
    return result["zone_id"]


def update_zone(zone_id: int, code: str, old_zone: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        farms_repo.update_zone(zone_id, code, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ZONE_UPDATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="zone",
            entity_id=zone_id,
            old_value={"code": old_zone["code"]},
            new_value={"code": code},
            conn=conn,
        )

    _write(db_path, _do)


def delete_zone(zone_id: int, old_zone: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        farms_repo.delete_zone(zone_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.ZONE_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="zone",
            entity_id=zone_id,
            old_value={"farm_id": old_zone["farm_id"], "code": old_zone["code"]},
            conn=conn,
        )

    _write(db_path, _do)
