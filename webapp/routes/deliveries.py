"""Blueprint ghi nhận XUẤT GIAO THỰC TẾ (sale_deliveries) — loại heo, số
lượng, trọng lượng, ngày xuất THẬT của từng lần giao, có thể lệch kế hoạch
mà không phải sửa số kế hoạch gốc.

Tách khỏi routes/plans.py (đã >1200 dòng) theo đúng tiền lệ routes/incidents.py.
Không có PATCH — sửa = xoá + tạo lại, khớp quy ước của incident/đối soát."""
from flask import Blueprint, jsonify, render_template, request, session

from core.services import delivery_service
from core import permissions as perm
from data_access import (
    get_delivery_locked,
    get_order_locked,
    get_plan_locked,
    list_deliveries_for_order_locked,
    list_deliveries_for_plan_locked,
    list_deliveries_locked,
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


@deliveries_bp.route("/xuat-giao")
@permission_required(*_VIEW_PLAN_PERMS)
def xuat_giao_page():
    """Trang danh sách toàn bộ lần xuất giao (STEP 8 Enterprise UI) — dữ
    liệu load qua JS (fetch /api/deliveries), không truyền gì qua Jinja,
    khớp khuôn allocations_page()/doi_soat_page()."""
    return render_template("xuat_giao.html")


@deliveries_bp.route("/api/deliveries", methods=["GET"])
@permission_required(*_VIEW_PLAN_PERMS)
def api_deliveries_list():
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and not farm_ids:
        return jsonify([])
    return jsonify(list_deliveries_locked(farm_ids=farm_ids))


@deliveries_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>/deliveries", methods=["POST"])
@permission_required(perm.DELIVERY_CREATE)
def api_delivery_create(order_id: int, line_id: int):
    """STEP 7 (Route Refactor): validate định dạng/giá trị input + check
    "vượt quá kế hoạch" đã chuyển vào
    delivery_service._validate_delivery_fields(). Route giữ lại 404/trạng
    thái đơn-dòng-hàng (Data Freeze pre-check, khớp nguyên tắc phạm vi đã
    dùng ở plan_service — chặn trước để tránh trigger ABORT giữa
    transaction) + farm-scope check."""
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
    username = session["user"]["username"]
    try:
        delivery = delivery_service.create_delivery(
            line_id, plan, order.get("order_code"), data, DB_PATH, ip=request.remote_addr, username=username
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
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
    plan = get_plan_locked(delivery["sale_plan_id"])
    farm_ids = allowed_farm_ids(session["user"])
    if plan is not None and farm_ids is not None and plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403
    deleted, err = delivery_service.delete_delivery(
        delivery_id, delivery, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    if not deleted:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})
