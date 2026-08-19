"""Blueprint ghi nhận XUẤT GIAO THỰC TẾ (sale_deliveries) — loại heo, số
lượng, trọng lượng, ngày xuất THẬT của từng lần giao, có thể lệch kế hoạch
mà không phải sửa số kế hoạch gốc.

Tách khỏi routes/plans.py (đã >1200 dòng) theo đúng tiền lệ routes/incidents.py.
Không có PATCH — sửa = xoá + tạo lại, khớp quy ước của incident/đối soát."""
from datetime import date

from flask import Blueprint, jsonify, request, session

from core.services import delivery_service
from core import permissions as perm
from data_access import (
    get_delivery_locked,
    get_order_locked,
    get_plan_locked,
    list_deliveries_for_order_locked,
    list_deliveries_for_plan_locked,
    list_pig_types_locked,
    sum_delivered_for_plan_locked,
)
from extensions import DB_PATH
from routes.auth import allowed_farm_ids, permission_required

deliveries_bp = Blueprint("deliveries", __name__)

# Xem đơn ở đâu thì xem được lần xuất giao của đơn đó ở đấy — dùng đúng tập
# quyền allocations.html đang dùng, không tạo quyền "xem" riêng.
_VIEW_ORDER_PERMS = (
    perm.PLAN_ALLOCATION_CREATE,
    perm.PLAN_ALLOCATION_MANAGE,
    perm.PLAN_SALE_DETAILS,
    perm.PLAN_REVENUE_DETAILS,
)
_VIEW_PLAN_PERMS = (perm.PLAN_REVIEW, perm.PLAN_RECEIVE, perm.PLAN_EDIT, perm.DELIVERY_CREATE)


def _parse_optional_positive(raw, label: str, cast):
    """('', None) -> (None, None) | giá trị hợp lệ -> (value, None) | lỗi -> (None, msg)."""
    if raw is None or str(raw).strip() == "":
        return None, None
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        return None, f"{label} không hợp lệ."
    if value <= 0:
        return None, f"{label} phải lớn hơn 0."
    return value, None


@deliveries_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>/deliveries", methods=["POST"])
@permission_required(perm.DELIVERY_CREATE)
def api_delivery_create(order_id: int, line_id: int):
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    line = next((l for l in order["lines"] if l["id"] == line_id), None)
    if line is None:
        return jsonify({"error": "Không tìm thấy dòng hàng."}), 404
    if order["status"] in ("cancelled", "disabled"):
        return jsonify({"error": "Đơn đã huỷ/vô hiệu hoá, không ghi nhận xuất giao được."}), 400
    # Chặn TRƯỚC khi ghi: nếu đơn/dòng đã Data Freeze thì bước đồng bộ ngược
    # actual_quantity về sale_allocations sẽ bị trigger ABORT giữa transaction.
    if order.get("locked_at"):
        return jsonify({"error": "Đơn đã khoá vĩnh viễn, không thể ghi nhận xuất giao."}), 400
    if line.get("locked_at"):
        return jsonify({"error": "Dòng hàng đã khoá vĩnh viễn, không thể ghi nhận xuất giao."}), 400

    plan = get_plan_locked(line["sale_plan_id"])
    if plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch trại của dòng hàng."}), 404
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    data = request.get_json(silent=True) or {}

    try:
        pig_type_id = int(data.get("pig_type_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn loại heo thực tế."}), 400
    if not any(pt["id"] == pig_type_id for pt in list_pig_types_locked(active_only=True)):
        return jsonify({"error": "Loại heo không hợp lệ hoặc đã ngừng dùng."}), 400

    try:
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"error": "Số lượng không hợp lệ."}), 400
    if quantity <= 0:
        return jsonify({"error": "Số lượng phải lớn hơn 0."}), 400

    # Chặn xuất vượt kế hoạch trại (cộng dồn mọi đơn của kế hoạch đó). Xuất dư
    # thật sự phải đi qua đối soát để có lý do, không ghi âm thầm.
    already = sum_delivered_for_plan_locked(plan["id"])
    if already + quantity > plan["quantity"]:
        remain = plan["quantity"] - already
        return jsonify(
            {"error": f"Vượt quá số lượng kế hoạch {plan['plan_code']}: còn có thể xuất {remain} con."}
        ), 400

    total_weight_kg, err = _parse_optional_positive(data.get("total_weight_kg"), "Trọng lượng", float)
    if err:
        return jsonify({"error": err}), 400
    unit_price, err = _parse_optional_positive(data.get("unit_price"), "Đơn giá", int)
    if err:
        return jsonify({"error": err}), 400

    raw_date = (data.get("delivered_date") or "").strip()
    if raw_date:
        try:
            date.fromisoformat(raw_date)
        except ValueError:
            return jsonify({"error": "Ngày xuất không hợp lệ."}), 400
        delivered_date = raw_date
    else:
        delivered_date = date.today().isoformat()

    username = session["user"]["username"]
    delivery = delivery_service.create_delivery(
        line_id,
        {
            "pig_type_id": pig_type_id,
            "quantity": quantity,
            "total_weight_kg": total_weight_kg,
            "unit_price": unit_price,
            "delivered_date": delivered_date,
            "weighing_ref": (data.get("weighing_ref") or "").strip() or None,
            "note": (data.get("note") or "").strip() or None,
        },
        {
            "plan_code": plan["plan_code"],
            "order_code": order.get("order_code"),
            "pig_type_id": pig_type_id,
            "quantity": quantity,
            "total_weight_kg": total_weight_kg,
            "delivered_date": delivered_date,
        },
        DB_PATH,
        ip=request.remote_addr,
        username=username,
    )
    return jsonify(delivery), 201


@deliveries_bp.route("/api/orders/<int:order_id>/deliveries", methods=["GET"])
@permission_required(*_VIEW_ORDER_PERMS)
def api_deliveries_for_order(order_id: int):
    if get_order_locked(order_id) is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    return jsonify(list_deliveries_for_order_locked(order_id))


@deliveries_bp.route("/api/plans/<int:plan_id>/deliveries", methods=["GET"])
@permission_required(*_VIEW_PLAN_PERMS)
def api_deliveries_for_plan(plan_id: int):
    if get_plan_locked(plan_id) is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    return jsonify(list_deliveries_for_plan_locked(plan_id))


@deliveries_bp.route("/api/deliveries/<int:delivery_id>", methods=["DELETE"])
@permission_required(perm.DELIVERY_DELETE)
def api_delivery_delete(delivery_id: int):
    delivery = get_delivery_locked(delivery_id)
    if delivery is None:
        return jsonify({"error": "Không tìm thấy bản ghi xuất giao."}), 404
    deleted, err = delivery_service.delete_delivery(
        delivery_id, delivery, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    if not deleted:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})
