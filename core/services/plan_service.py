from datetime import date
from pathlib import Path

from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, notifications_repo, pig_types_repo, plan_reconciliation_repo, sale_plans_repo
from core import audit_actions, permissions as perm
from core.services import notification_service

# Alias nội bộ — giữ tên `_write` cũ trong toàn bộ file này để không phải
# đổi lại mọi lời gọi bên dưới; helper thật giờ sống ở core/db.py để
# order_service.py (và các service khác sau này) dùng chung, không lặp lại.
_write = run_in_transaction


def _parse_expected_avg_weight(data: dict) -> float | None:
    """Trọng lượng dự kiến (kg/con) — tuỳ chọn. Rỗng/thiếu -> None (không
    phải 0), để phân biệt "chưa nhập cân" với "cân bằng 0" (xem
    _PLANNED_WEIGHT_SQL ở sale_plans_repo.py). Raise ValueError nếu có
    nhập nhưng không hợp lệ."""
    raw = data.get("expected_avg_weight_kg")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("Trọng lượng dự kiến không hợp lệ.")
    if value <= 0:
        raise ValueError("Trọng lượng dự kiến phải lớn hơn 0.")
    return value


def _validate_plan_fields(data: dict, db_path: Path) -> dict:
    """STEP 7 (Route Refactor): validate + parse toàn bộ trường của kế
    hoạch trại — gộp đúng 2 khối validate trước đây bị copy-paste giống
    hệt nhau ở webapp/routes/plans.py (api_plans_create + api_plans_edit)
    thành 1 chỗ. Raise ValueError(msg) đúng message cũ cho từng trường
    hợp lỗi — route bắt bằng try/except ValueError -> 400, khớp khuôn đã
    dùng sẵn ở edit_plan()/sale_plans_repo.update_sale_plan_edit()."""
    note = (data.get("note") or "").strip() or None
    shed = (data.get("shed") or "").strip() or None
    lot = (data.get("lot") or "").strip() or None
    if shed and len(shed) > 50:
        raise ValueError("Tên chuồng quá dài.")
    if lot and len(lot) > 50:
        raise ValueError("Tên lô quá dài.")

    try:
        farm_id = int(data.get("farm_id"))
    except (TypeError, ValueError):
        raise ValueError("Vui lòng chọn trang trại.")
    try:
        zone_id = int(data.get("zone_id"))
    except (TypeError, ValueError):
        raise ValueError("Vui lòng chọn khu.")
    try:
        pig_type_id = int(data.get("pig_type_id"))
    except (TypeError, ValueError):
        raise ValueError("Vui lòng chọn loại heo bán.")
    with db_lock:
        active_pig_types = pig_types_repo.list_pig_types(db_path, active_only=True)
    if not any(pt["id"] == pig_type_id for pt in active_pig_types):
        raise ValueError("Loại heo không hợp lệ hoặc đã ngừng dùng.")

    planned_date = data.get("planned_date", "")
    try:
        date.fromisoformat(planned_date)
    except (TypeError, ValueError):
        raise ValueError("Ngày dự kiến không hợp lệ.")

    try:
        quantity = int(data.get("quantity"))
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Số lượng không hợp lệ.")

    expected_avg_weight_kg = _parse_expected_avg_weight(data)

    return {
        "planned_date": planned_date,
        "farm_id": farm_id,
        "zone_id": zone_id,
        "shed": shed,
        "lot": lot,
        "pig_type_id": pig_type_id,
        "quantity": quantity,
        "expected_avg_weight_kg": expected_avg_weight_kg,
        "note": note,
    }


def create_plan(
    data: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Validate input thô (route chỉ còn lo HTTP + farm-scope check —
    STEP 7 Route Refactor) rồi tạo kế hoạch trại + audit trong cùng
    transaction. Có thể raise ValueError (route bắt -> 400)."""
    plan = _validate_plan_fields(data, db_path)

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
        # Thông báo (Phase 5, brief nghiệp vụ): người có quyền duyệt cần biết
        # ngay có kế hoạch mới chờ xử lý, không phải tự vào /ke-hoach kiểm tra.
        notification_service.notify(
            perm.PLAN_REVIEW,
            "Kế hoạch trại mới chờ duyệt",
            f"{plan['quantity']} con — chờ duyệt.",
            f"/ke-hoach?highlight={plan_id}",
            db_path,
            farm_id=plan["farm_id"],
            exclude_username=username,
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
    created_by: str | None = None,
) -> None:
    """Duyệt kế hoạch đang chờ duyệt + audit trong cùng transaction. Route
    đã xác nhận plan.status == 'pending_approval' trước khi gọi (điều kiện
    này lặp lại trong WHERE của approve_sale_plan làm lớp bảo vệ thứ 2).
    created_by: route đã fetch sẵn (old_plan["created_by"]) — dùng để báo
    ngược cho người đã lập kế hoạch, không tự truy vấn lại trong service."""

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
        if created_by:
            notifications_repo.create_notification(
                created_by, "Kế hoạch trại đã được duyệt", None, f"/ke-hoach?highlight={plan_id}", db_path, conn=conn
            )

    _write(db_path, _do)


def reject_plan(
    plan_id: int,
    reason: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
    created_by: str | None = None,
) -> None:
    """Từ chối kế hoạch đang chờ duyệt + audit trong cùng transaction.
    created_by: xem ghi chú ở approve_plan()."""

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
        if created_by:
            notifications_repo.create_notification(
                created_by, "Kế hoạch trại bị từ chối", reason, f"/ke-hoach?highlight={plan_id}", db_path, conn=conn
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
    data: dict,
    old_plan: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Validate input thô (STEP 7 Route Refactor, dùng chung
    _validate_plan_fields() với create_plan()) rồi sửa nội dung kế hoạch
    trại + audit cùng transaction. Có thể raise ValueError — hoặc từ
    validate input, hoặc chặn sửa quantity khi đã có đơn/đối soát tham
    chiếu (xem sale_plans_repo.update_sale_plan_edit) — route bắt
    ValueError y hệt trước đây. Trả False (không audit) nếu kế hoạch
    không còn tồn tại, khớp hành vi cũ của route."""
    plan = _validate_plan_fields(data, db_path)

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