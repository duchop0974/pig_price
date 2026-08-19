from pathlib import Path

from core.db import run_in_transaction
from core.repositories import audit_repo, plan_reconciliation_repo, sale_plans_repo
from core import audit_actions

# Alias nội bộ — giữ tên `_write` cũ trong toàn bộ file này để không phải
# đổi lại mọi lời gọi bên dưới; helper thật giờ sống ở core/db.py để
# order_service.py (và các service khác sau này) dùng chung, không lặp lại.
_write = run_in_transaction


def create_plan(
    plan: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Tạo kế hoạch trại và audit trong cùng transaction."""

    def _do(conn):
        plan_id = sale_plans_repo.create_sale_plan(plan, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.PLAN_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            new_value={
                "planned_date": plan["planned_date"],
                "farm_id": plan["farm_id"],
                "zone_id": plan.get("zone_id"),
                "shed": plan.get("shed"),
                "lot": plan.get("lot"),
                "pig_type_id": plan["pig_type_id"],
                "quantity": plan["quantity"],
                "expected_avg_weight_kg": plan.get("expected_avg_weight_kg"),
                "note": plan.get("note"),
            },
            conn=conn,
        )
        return plan_id

    return _write(db_path, _do)


def approve_plan(
    plan_id: int,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Duyệt kế hoạch đang chờ duyệt + audit trong cùng transaction. Route
    đã xác nhận plan.status == 'pending_approval' trước khi gọi (điều kiện
    này lặp lại trong WHERE của approve_sale_plan làm lớp bảo vệ thứ 2)."""

    def _do(conn):
        sale_plans_repo.approve_sale_plan(plan_id, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.PLAN_APPROVE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={"status": "pending_approval"},
            new_value={"status": "approved", "approved_by": username},
            conn=conn,
        )

    _write(db_path, _do)


def reject_plan(
    plan_id: int,
    reason: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Từ chối kế hoạch đang chờ duyệt + audit trong cùng transaction."""

    def _do(conn):
        sale_plans_repo.reject_sale_plan(plan_id, reason, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.PLAN_REJECT,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={"status": "pending_approval"},
            new_value={"status": "rejected", "rejected_by": username, "rejected_reason": reason},
            conn=conn,
        )

    _write(db_path, _do)


def update_plan_status(
    plan_id: int,
    status: str,
    old_status: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Đổi trạng thái kế hoạch (approved/disabled/cancelled, KHÔNG dùng cho
    duyệt/từ chối — 2 hành động đó có hàm riêng ở trên) + audit cùng
    transaction. `old_status` do route truyền vào (đã fetch để validate
    trước khi gọi), tránh service phải tự SELECT lại."""

    def _do(conn):
        sale_plans_repo.update_sale_plan_status(plan_id, status, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.PLAN_UPDATE_STATUS,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={"status": old_status},
            new_value={"status": status},
            conn=conn,
        )

    _write(db_path, _do)


def record_received(
    plan_id: int,
    received_quantity: int,
    old_received_quantity: int | None,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Ghi nhận số lượng thực tế đã xuất chuồng + audit cùng transaction."""

    def _do(conn):
        sale_plans_repo.update_plan_received_quantity(
            plan_id, received_quantity, db_path, ip, username, conn=conn
        )
        audit_repo.log_action(
            audit_actions.PLAN_UPDATE_RECEIVED,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={"received_quantity": old_received_quantity},
            new_value={"received_quantity": received_quantity},
            conn=conn,
        )

    _write(db_path, _do)


def edit_plan(
    plan_id: int,
    plan: dict,
    old_plan: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Sửa nội dung kế hoạch trại + audit cùng transaction. Có thể raise
    ValueError (chặn sửa quantity khi đã có đơn/đối soát tham chiếu — xem
    sale_plans_repo.update_sale_plan_edit) — transaction() tự rollback khi
    exception, route bắt ValueError y hệt trước đây. Trả False (không audit)
    nếu kế hoạch không còn tồn tại, khớp hành vi cũ của route."""

    def _do(conn):
        updated = sale_plans_repo.update_sale_plan_edit(plan_id, plan, db_path, ip, username, conn=conn)
        if not updated:
            return False
        audit_repo.log_action(
            audit_actions.PLAN_UPDATE_EDIT,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={
                "planned_date": old_plan["planned_date"],
                "farm_id": old_plan["farm_id"],
                "pig_type": old_plan["pig_type"],
                "quantity": old_plan["quantity"],
            },
            new_value={
                "planned_date": plan["planned_date"],
                "farm_id": plan["farm_id"],
                "zone_id": plan.get("zone_id"),
                "pig_type_id": plan["pig_type_id"],
                "quantity": plan["quantity"],
            },
            conn=conn,
        )
        return True

    return _write(db_path, _do)


def create_reconciliation(
    sale_plan_id: int,
    kind: str,
    quantity: int,
    reason: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> dict:
    """Tạo bản ghi đối soát trong 1 transaction. KHÔNG ghi audit ở đây —
    khác các hàm khác trong file này: route cần lưu ảnh bằng chứng (I/O file,
    không thuộc SQL transaction) SAU khi bản ghi được tạo, và audit muốn kèm
    số ảnh đã lưu, nên audit vẫn do route ghi sau khi hoàn tất upload ảnh."""

    def _do(conn):
        return plan_reconciliation_repo.create_reconciliation(
            sale_plan_id, kind, quantity, reason, db_path, reported_by=username, ip=ip, conn=conn
        )

    return _write(db_path, _do)


def delete_reconciliation(
    reconciliation_id: int,
    old_reconciliation: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Xoá bản ghi đối soát + audit trong cùng transaction (không đụng
    media_proof/ảnh liên quan — giữ evidence trail, khớp
    plan_reconciliation_repo.delete_reconciliation). Trả False (không audit)
    nếu bản ghi không còn tồn tại."""

    def _do(conn):
        deleted = plan_reconciliation_repo.delete_reconciliation(reconciliation_id, db_path, conn=conn)
        if not deleted:
            return False
        audit_repo.log_action(
            audit_actions.PLAN_RECONCILE_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=old_reconciliation["sale_plan_id"],
            old_value=old_reconciliation,
            conn=conn,
        )
        return True

    return _write(db_path, _do)


def delete_plan(
    plan_id: int,
    old_plan: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Xoá vĩnh viễn kế hoạch trại + audit cùng transaction. Trả False
    (không audit) nếu bị chặn xoá (còn kế hoạch bán tham chiếu), khớp hành
    vi cũ của route."""

    def _do(conn):
        deleted = sale_plans_repo.delete_sale_plan(plan_id, db_path, conn=conn)
        if not deleted:
            return False
        audit_repo.log_action(
            audit_actions.PLAN_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_plan",
            entity_id=plan_id,
            old_value={
                "plan_code": old_plan["plan_code"],
                "planned_date": old_plan["planned_date"],
                "farm_id": old_plan["farm_id"],
                "quantity": old_plan["quantity"],
                "status": old_plan["status"],
            },
            conn=conn,
        )
        return True

    return _write(db_path, _do)