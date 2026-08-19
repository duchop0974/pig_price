"""Service layer cho sale_deliveries (ghi nhận xuất giao thực tế) — khuôn
1:1 plan_service.py/order_service.py: gộp repo write + audit log vào 1
transaction qua core.db.run_in_transaction()."""
from pathlib import Path

from core.db import run_in_transaction
from core.repositories import audit_repo, sale_deliveries_repo
from core import audit_actions

_write = run_in_transaction


def create_delivery(
    allocation_id: int,
    delivery: dict,
    audit_new_value: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> dict:
    """Ghi nhận 1 lần xuất giao thực tế + audit trong cùng transaction.
    `audit_new_value` do route truyền vào riêng (khác payload ghi DB — audit
    còn kèm plan_code/order_code để dễ tra cứu, 2 field này route đã có sẵn
    từ get_plan_locked/get_order_locked, không cần service tự truy vấn lại)."""

    def _do(conn):
        created = sale_deliveries_repo.create_delivery(
            allocation_id, delivery, db_path, ip, username, conn=conn
        )
        audit_repo.log_action(
            audit_actions.DELIVERY_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_delivery",
            entity_id=created["id"],
            new_value=audit_new_value,
            conn=conn,
        )
        return created

    return _write(db_path, _do)


def delete_delivery(
    delivery_id: int,
    old_delivery: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> tuple[bool, str | None]:
    """Xoá 1 bản ghi xuất giao + audit trong cùng transaction. Trả
    (False, lý do) (không audit) nếu bị chặn (không tìm thấy/đã khoá), khớp
    hành vi cũ của sale_deliveries_repo.delete_delivery."""

    def _do(conn):
        deleted, err = sale_deliveries_repo.delete_delivery(delivery_id, db_path, conn=conn)
        if not deleted:
            return False, err
        audit_repo.log_action(
            audit_actions.DELIVERY_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_delivery",
            entity_id=delivery_id,
            old_value={
                "plan_code": old_delivery.get("plan_code"),
                "pig_type_name": old_delivery.get("pig_type_name"),
                "quantity": old_delivery.get("quantity"),
                "delivered_date": old_delivery.get("delivered_date"),
            },
            conn=conn,
        )
        return True, None

    return _write(db_path, _do)
