"""Service layer cho sale_deliveries (ghi nhận xuất giao thực tế) — khuôn
1:1 plan_service.py/order_service.py: gộp repo write + audit log vào 1
transaction qua core.db.run_in_transaction()."""
from datetime import date
from pathlib import Path

from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, pig_types_repo, sale_deliveries_repo
from core import audit_actions

_write = run_in_transaction


def _parse_optional_positive(raw, label: str, cast):
    """Rỗng/thiếu -> None. Có nhập nhưng sai định dạng/không dương -> raise
    ValueError(msg). Chuyển nguyên từ webapp/routes/deliveries.py."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{label} không hợp lệ.")
    if value <= 0:
        raise ValueError(f"{label} phải lớn hơn 0.")
    return value


def _validate_delivery_fields(data: dict, plan: dict, db_path: Path) -> dict:
    """STEP 7 (Route Refactor): validate + parse toàn bộ trường của 1 lần
    xuất giao — chuyển từ webapp/routes/deliveries.py::api_delivery_create().
    Farm-scope + trạng thái đơn/dòng hàng (locked_at, cancelled/disabled)
    VẪN ở route (nhất quán với plan_service/order_service — đã kiểm tra
    TRƯỚC khi gọi service, cần dict order/line route đã fetch sẵn cho
    check 404 nên không lặp lại đọc ở đây)."""
    try:
        pig_type_id = int(data.get("pig_type_id"))
    except (TypeError, ValueError):
        raise ValueError("Vui lòng chọn loại heo thực tế.")
    with db_lock:
        active_pig_types = pig_types_repo.list_pig_types(db_path, active_only=True)
    if not any(pt["id"] == pig_type_id for pt in active_pig_types):
        raise ValueError("Loại heo không hợp lệ hoặc đã ngừng dùng.")

    try:
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        raise ValueError("Số lượng không hợp lệ.")
    if quantity <= 0:
        raise ValueError("Số lượng phải lớn hơn 0.")

    # Chặn xuất vượt kế hoạch trại (cộng dồn mọi đơn của kế hoạch đó). Xuất
    # dư thật sự phải đi qua đối soát để có lý do, không ghi âm thầm.
    with db_lock:
        already = sale_deliveries_repo.sum_delivered_for_plan(plan["id"], db_path)
    if already + quantity > plan["quantity"]:
        remain = plan["quantity"] - already
        raise ValueError(f"Vượt quá số lượng kế hoạch {plan['plan_code']}: còn có thể xuất {remain} con.")

    total_weight_kg = _parse_optional_positive(data.get("total_weight_kg"), "Trọng lượng", float)
    unit_price = _parse_optional_positive(data.get("unit_price"), "Đơn giá", int)

    raw_date = (data.get("delivered_date") or "").strip()
    if raw_date:
        try:
            date.fromisoformat(raw_date)
        except ValueError:
            raise ValueError("Ngày xuất không hợp lệ.")
        delivered_date = raw_date
    else:
        delivered_date = date.today().isoformat()

    return {
        "pig_type_id": pig_type_id,
        "quantity": quantity,
        "total_weight_kg": total_weight_kg,
        "unit_price": unit_price,
        "delivered_date": delivered_date,
        "weighing_ref": (data.get("weighing_ref") or "").strip() or None,
        "note": (data.get("note") or "").strip() or None,
    }


def create_delivery(
    allocation_id: int,
    plan: dict,
    order_code: str | None,
    data: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> dict:
    """Validate input thô (STEP 7 Route Refactor) rồi ghi nhận 1 lần xuất
    giao thực tế + audit trong cùng transaction. Có thể raise ValueError.
    `plan`/`order_code` do route truyền vào (đã fetch sẵn cho check 404/
    farm-scope) — dùng để validate "vượt quá kế hoạch" và build audit
    new_value (plan_code/order_code để dễ tra cứu), không cần service tự
    truy vấn lại."""
    delivery = _validate_delivery_fields(data, plan, db_path)

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
            new_value={
                "plan_code": plan["plan_code"],
                "order_code": order_code,
                "pig_type_id": delivery["pig_type_id"],
                "quantity": delivery["quantity"],
                "total_weight_kg": delivery["total_weight_kg"],
                "delivered_date": delivery["delivered_date"],
            },
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
