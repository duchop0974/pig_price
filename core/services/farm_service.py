"""Service layer cho danh mục Trang trại / Khu (farms/zones) — nối dài
Service Layer sang phần quản trị, theo STEP 4 (Transaction Standardization)
của PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm gộp đúng 1 lần ghi
repo + 1 lần audit_log vào chung 1 transaction qua run_in_transaction.

STEP 7 (Route Refactor): validate định dạng/giá trị + trùng mã đã chuyển
vào service (create/update). Check "còn kế hoạch xuất bán tham chiếu" khi
xoá VẪN ở route layer — khớp nguyên tắc phạm vi đã dùng cho
customer_service.delete_customer (route đã có sẵn count trước khi gọi,
đây là business rule tham chiếu sang domain khác, không phải validate
input thuần)."""
from pathlib import Path

from core import audit_actions
from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, farms_repo

_write = run_in_transaction


def _validate_farm_fields(code: str, province: str | None, db_path: Path, *, exclude_farm_id: int | None = None) -> None:
    if not code or len(code) > 30:
        raise ValueError("Vui lòng nhập mã trang trại hợp lệ." if exclude_farm_id is None else "Mã trang trại không hợp lệ.")
    if province and len(province) > 100:
        raise ValueError("Tên tỉnh quá dài.")
    with db_lock:
        farms = farms_repo.list_farms(db_path)
    if any(f["code"] == code and f["id"] != exclude_farm_id for f in farms):
        raise ValueError("Mã trang trại đã tồn tại.")


def _validate_zone_fields(
    farm_id: int, code: str, db_path: Path, *, exclude_zone_id: int | None = None
) -> None:
    if not code or len(code) > 30:
        raise ValueError("Vui lòng nhập tên khu hợp lệ." if exclude_zone_id is None else "Tên khu không hợp lệ.")
    with db_lock:
        zones = farms_repo.list_zones(farm_id, db_path)
    if any(z["code"] == code and z["id"] != exclude_zone_id for z in zones):
        raise ValueError("Tên khu đã tồn tại trong trang trại này.")


def create_farm(code: str, province: str | None, db_path: Path, *, ip=None, username=None) -> int:
    _validate_farm_fields(code, province, db_path)
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
    _validate_farm_fields(code, province, db_path, exclude_farm_id=farm_id)

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
    """Route đã kiểm tra farm_id tồn tại (404) trước khi gọi — service chỉ
    lo validate code + trùng mã trong trại."""
    _validate_zone_fields(farm_id, code, db_path)
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
    _validate_zone_fields(old_zone["farm_id"], code, db_path, exclude_zone_id=zone_id)

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
