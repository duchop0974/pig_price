"""Service layer cho toàn bộ vòng đời đơn hàng (sale_orders + sale_allocations)
— khuôn 1:1 với core/services/plan_service.py: mỗi hàm gộp 1 lệnh ghi repo +
audit log vào chung 1 transaction qua core.db.run_in_transaction(), thay cho
pattern cũ (data_access.*_locked() rồi log_audit() tách rời, không atomic)."""
from pathlib import Path

from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, sale_orders_repo, sale_plans_repo
from core.repositories import weighing_repo
from core import audit_actions

_write = run_in_transaction


def _validate_lines(raw_lines: list, db_path: Path) -> list[dict]:
    """STEP 7 (Route Refactor): chuyển nguyên logic validate 1 hoặc nhiều
    dòng hàng cùng lúc — trước đây là _validate_order_lines() ở
    webapp/routes/plans.py. Dùng cho cả tạo đơn mới lẫn thêm 1 dòng vào
    đơn có sẵn. Cộng dồn số lượng đã "đặt chỗ" trong CHÍNH lần gọi này
    theo từng sale_plan_id — phòng trường hợp cùng 1 kế hoạch trại xuất
    hiện ở nhiều dòng trong 1 lần gửi, vượt quá remaining_quantity dù mỗi
    dòng riêng lẻ có vẻ hợp lệ. Raise ValueError(msg) thay vì trả
    (None, msg) như hàm gốc — route bắt bằng try/except ValueError."""
    validated: list[dict] = []
    reserved_by_plan: dict[int, int] = {}
    plan_cache: dict[int, dict] = {}
    for raw in raw_lines:
        if not isinstance(raw, dict):
            raise ValueError("Dữ liệu dòng hàng không hợp lệ.")
        try:
            sale_plan_id = int(raw.get("sale_plan_id"))
        except (TypeError, ValueError):
            raise ValueError("Vui lòng chọn kế hoạch trại cho từng dòng.")
        plan = plan_cache.get(sale_plan_id)
        if plan is None:
            with db_lock:
                plan = sale_plans_repo.get_sale_plan(sale_plan_id, db_path)
            if plan is None:
                raise ValueError("Không tìm thấy kế hoạch trại.")
            if plan["status"] != "approved":
                raise ValueError("Chỉ tạo dòng hàng từ kế hoạch trại đã duyệt.")
            plan_cache[sale_plan_id] = plan
        try:
            quantity = int(raw.get("quantity"))
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Số lượng không hợp lệ.")
        reserved_by_plan[sale_plan_id] = reserved_by_plan.get(sale_plan_id, 0) + quantity
        if reserved_by_plan[sale_plan_id] > plan["remaining_quantity"]:
            raise ValueError(f"Vượt quá số lượng còn lại của {plan['plan_code']} ({plan['remaining_quantity']} con).")
        try:
            selling_price = int(raw.get("selling_price"))
            if selling_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Vui lòng nhập giá chào bán hợp lệ.")
        note = (raw.get("note") or "").strip() or None
        validated.append(
            {"sale_plan_id": sale_plan_id, "quantity": quantity, "selling_price": selling_price, "note": note}
        )
    return validated


def create_order(
    raw_lines: list,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Validate input thô (STEP 7 Route Refactor) rồi tạo đơn hàng (kèm N
    dòng ban đầu) + audit trong cùng transaction. Có thể raise ValueError."""
    lines = _validate_lines(raw_lines, db_path)

    def _do(conn):
        order_id = sale_orders_repo.create_order(lines, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            new_value={"lines": lines},
            conn=conn,
        )
        return order_id

    return _write(db_path, _do)


def add_line(
    order_id: int,
    raw_line: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Validate input thô (STEP 7 Route Refactor, dùng chung
    _validate_lines() với create_order()) rồi thêm 1 dòng vào đơn đang xử
    lý + audit cùng transaction. Có thể raise ValueError."""
    line = _validate_lines([raw_line], db_path)[0]

    def _do(conn):
        line_id = sale_orders_repo.add_order_line(order_id, line, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_LINE_ADD,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            new_value={"allocation_id": line_id, **line},
            conn=conn,
        )
        return line_id

    return _write(db_path, _do)


def remove_line(
    order_id: int,
    allocation_id: int,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Xoá 1 dòng khỏi đơn đang xử lý + audit cùng transaction. Trả False
    (không audit) nếu dòng không thuộc đơn này."""

    def _do(conn):
        removed = sale_orders_repo.remove_order_line(order_id, allocation_id, db_path, ip, username, conn=conn)
        if not removed:
            return False
        audit_repo.log_action(
            audit_actions.ORDER_LINE_REMOVE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={"allocation_id": allocation_id},
            conn=conn,
        )
        return True

    return _write(db_path, _do)


def edit_line(
    order_id: int,
    allocation_id: int,
    old_line: dict,
    fields: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Sửa số lượng/giá/ghi chú 1 dòng hàng (quyền ORDER_EDIT_LINE, không
    kiểm lại trạng thái đơn — khớp hành vi cũ) + audit cùng transaction. Trả
    False (không audit) nếu dòng không còn tồn tại."""

    def _do(conn):
        updated = sale_orders_repo.update_order_line(allocation_id, db_path, ip, username, fields, conn=conn)
        if not updated:
            return False
        audit_repo.log_action(
            audit_actions.ORDER_LINE_EDIT,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={"allocation_id": allocation_id, **{k: old_line.get(k) for k in fields}},
            new_value={"allocation_id": allocation_id, **fields},
            conn=conn,
        )
        return True

    return _write(db_path, _do)


def update_status(
    order_id: int,
    status: str,
    old_status: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Đổi trạng thái đơn (active/disabled/cancelled) + audit cùng
    transaction. `old_status` do route truyền vào (đã fetch để validate)."""

    def _do(conn):
        sale_orders_repo.update_order_status(order_id, status, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_UPDATE_STATUS,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={"status": old_status},
            new_value={"status": status},
            conn=conn,
        )

    _write(db_path, _do)


def delete_order(
    order_id: int,
    old_order: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> tuple[bool, str | None]:
    """Xoá vĩnh viễn đơn hàng + audit cùng transaction. Trả (False, reason)
    (không audit) nếu bị chặn xoá (còn cân/sự cố/xuất giao tham chiếu),
    khớp hành vi cũ của sale_orders_repo.delete_order."""

    def _do(conn):
        deleted, reason = sale_orders_repo.delete_order(order_id, db_path, conn=conn)
        if not deleted:
            return False, reason
        audit_repo.log_action(
            audit_actions.ORDER_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={
                "order_code": old_order["order_code"],
                "status": old_order["status"],
                "line_count": len(old_order["lines"]),
            },
            conn=conn,
        )
        return True, None

    return _write(db_path, _do)


def lock_order(
    order_id: int,
    order_code: str,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Data Freeze — khoá vĩnh viễn 1 đơn đã hoàn tất + audit cùng
    transaction (xem weighing_repo.lock_record, dùng chung cho nhiều bảng).
    Trả False (không audit) nếu đã khoá từ trước."""

    def _do(conn):
        locked = weighing_repo.lock_record("sale_orders", order_id, db_path, ip=ip, username=username, conn=conn)
        if not locked:
            return False
        audit_repo.log_action(
            audit_actions.ORDER_LOCK,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            new_value={"order_code": order_code},
            conn=conn,
        )
        return True

    return _write(db_path, _do)


def mark_done(
    order_id: int,
    line_actuals: list[dict],
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Đánh dấu đơn 'Đã bán' + ghi giá/số lượng bán thực tế từng dòng +
    audit, tất cả cùng 1 transaction (trước đây mark_order_done() đã tự
    transaction nội bộ 1 connection, audit lại tách rời — giờ audit cũng
    nằm trong cùng transaction đó)."""

    def _do(conn):
        sale_orders_repo.mark_order_done(order_id, line_actuals, db_path, ip, username, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_MARK_DONE,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            new_value={"lines": line_actuals},
            conn=conn,
        )

    _write(db_path, _do)


def update_sale_details(
    order_id: int,
    old_order: dict,
    fields: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Chốt thông tin bán hàng (khách hàng/liên hệ/ngày chốt/giao/thanh
    toán) + audit cùng transaction."""

    def _do(conn):
        sale_orders_repo.update_order_sale_details(order_id, db_path, ip, username, fields, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_UPDATE_SALE_DETAILS,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={k: old_order.get(k) for k in fields},
            new_value=fields,
            conn=conn,
        )

    _write(db_path, _do)


def update_revenue_details(
    order_id: int,
    old_order: dict,
    fields: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Ghi nhận doanh thu/hoá đơn + audit cùng transaction."""

    def _do(conn):
        sale_orders_repo.update_order_revenue_details(order_id, db_path, ip, username, fields, conn=conn)
        audit_repo.log_action(
            audit_actions.ORDER_UPDATE_REVENUE_DETAILS,
            db_path,
            username=username,
            ip=ip,
            entity_type="sale_order",
            entity_id=order_id,
            old_value={k: old_order.get(k) for k in fields},
            new_value=fields,
            conn=conn,
        )

    _write(db_path, _do)
