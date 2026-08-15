"""Blueprint kế hoạch xuất bán + API liên quan (farms/zones/pig-types/plans)."""
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from flask import Blueprint, jsonify, render_template, request, send_file, session

from core import audit_actions
from core import permissions as perm
from core.scrapers.utils import normalize_province
from data_access import (
    approve_plan_locked,
    count_allocations_for_customer_locked,
    create_allocation_locked,
    create_customer_locked,
    create_plan_locked,
    delete_customer_locked,
    export_allocation_quotation_excel_locked,
    export_allocations_excel_locked,
    export_plans_excel_locked,
    get_allocation_locked,
    get_customer_locked,
    get_plan_locked,
    list_allocations_locked,
    list_customers_locked,
    list_farms_locked,
    list_pig_types_locked,
    list_plans_locked,
    list_zones_locked,
    load_df,
    reject_plan_locked,
    set_customer_active_locked,
    update_allocation_revenue_details_locked,
    update_allocation_sale_details_locked,
    update_allocation_status_locked,
    update_customer_locked,
    update_plan_received_quantity_locked,
    update_plan_status_locked,
)
from extensions import log_audit
from routes.auth import allowed_farm_ids, current_user_permissions, permission_required

plans_bp = Blueprint("plans", __name__)

# Hình thức thanh toán — khớp 4 lựa chọn trong BM02 (Đơn hàng) + "Khác".
PAYMENT_METHODS = ("bank_transfer_immediate", "bank_transfer_24h", "cash", "credit", "other")


def national_price(df: pd.DataFrame) -> dict:
    """Giá heo hơi trung bình cả nước, ngày gần nhất có dữ liệu — dùng làm
    mốc dự phòng khi trại chưa gán tỉnh hoặc tỉnh đó chưa có dữ liệu giá."""
    if df.empty:
        return {"price": None, "date": None}
    sort_key = pd.to_datetime(df["date"], format="%d/%m/%Y")
    latest_date = df.loc[sort_key.idxmax(), "date"]
    prices = df.loc[df["date"] == latest_date, "price_vnd_per_kg"].dropna()
    avg_price = round(prices.mean()) if not prices.empty else None
    return {"price": avg_price, "date": latest_date}


def province_price(df: pd.DataFrame, province: str) -> dict | None:
    """Giá heo hơi trung bình đúng tỉnh trại đang đặt, ngày gần nhất tỉnh đó
    có dữ liệu. None nếu tỉnh chưa có dữ liệu giá nào."""
    if df.empty:
        return None
    key = normalize_province(province)
    subset = df[df["province"].map(normalize_province) == key]
    if subset.empty:
        return None
    sort_key = pd.to_datetime(subset["date"], format="%d/%m/%Y")
    latest_date = subset.loc[sort_key.idxmax(), "date"]
    prices = subset.loc[subset["date"] == latest_date, "price_vnd_per_kg"].dropna()
    avg_price = round(prices.mean()) if not prices.empty else None
    return {"price": avg_price, "date": latest_date}


def current_price_for_plan(df: pd.DataFrame, province: str | None, nat: dict) -> dict:
    """So giá theo đúng tỉnh của trại khi có dữ liệu; nếu trại chưa gán tỉnh
    hoặc tỉnh đó chưa có dữ liệu giá thì rơi về giá bình quân cả nước (kèm
    is_national để UI báo rõ đây là số liệu dự phòng, tránh hiểu nhầm là
    giá đúng vùng)."""
    if province:
        p = province_price(df, province)
        if p is not None:
            return {**p, "is_national": False}
    return {**nat, "is_national": True}


def plan_payload(plan: dict, df: pd.DataFrame, nat: dict) -> dict:
    """Kế hoạch trại KHÔNG còn giá — bỏ hẳn so sánh giá thị trường (chuyển
    sang allocation_payload, so với selling_price của kế hoạch bán)."""
    try:
        days_left = (date.fromisoformat(plan["planned_date"]) - date.today()).days
    except ValueError:
        days_left = None
    return {**plan, "days_left": days_left}


def allocation_payload(alloc: dict, df: pd.DataFrame, nat: dict) -> dict:
    """So giá thị trường hiện tại với selling_price của kế hoạch bán — logic
    này trước đây áp cho kế hoạch trại (target_price), nay chuyển hẳn sang
    đây vì giá chỉ còn tồn tại ở cấp kế hoạch bán."""
    cur = current_price_for_plan(df, alloc.get("province"), nat)
    reached = (
        cur["price"] is not None and alloc.get("selling_price") is not None and cur["price"] >= alloc["selling_price"]
    )
    try:
        days_left = (date.fromisoformat(alloc["planned_date"]) - date.today()).days
    except (ValueError, TypeError):
        days_left = None
    return {
        **alloc,
        "current_price": cur["price"],
        "current_price_date": cur["date"],
        "current_price_is_national": cur["is_national"],
        "reached_target": reached,
        "days_left": days_left,
    }


@plans_bp.route("/ke-hoach")
def plans_page():
    return render_template("plans.html")


@plans_bp.route("/api/farms", methods=["GET"])
def api_farms_list():
    """Đọc danh sách trang trại — ai đăng nhập cũng xem được để chọn trong
    form kế hoạch. Thêm/sửa/xóa trang trại chỉ admin làm được, xem routes/admin.py.
    Tài khoản vai trò farm chỉ thấy (các) trại được gán."""
    farms = list_farms_locked()
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None:
        farms = [f for f in farms if f["id"] in farm_ids]
    return jsonify(farms)


@plans_bp.route("/api/zones", methods=["GET"])
def api_zones_list():
    """Đọc danh sách khu theo trang trại — như /api/farms, chỉ đọc; thêm/sửa/xóa
    chỉ admin làm được."""
    try:
        farm_id = int(request.args.get("farm_id", ""))
    except ValueError:
        return jsonify([])
    return jsonify(list_zones_locked(farm_id))


@plans_bp.route("/api/pig-types", methods=["GET"])
def api_pig_types_list():
    """Danh mục loại heo bán (chỉ những loại đang bật) — dùng để đổ vào
    form tạo kế hoạch. Thêm/khoá danh mục chỉ admin làm được, xem routes/admin.py."""
    return jsonify(list_pig_types_locked(active_only=True))


@plans_bp.route("/api/plans", methods=["GET"])
def api_plans_list():
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and not farm_ids:
        return jsonify([])
    df = load_df()
    nat = national_price(df)
    plans = list_plans_locked(farm_ids=farm_ids)
    return jsonify([plan_payload(p, df, nat) for p in plans])


@plans_bp.route("/api/plans", methods=["POST"])
@permission_required(perm.PLAN_CREATE)
def api_plans_create():
    data = request.get_json(silent=True) or {}
    planned_date = data.get("planned_date", "")
    note = (data.get("note") or "").strip() or None
    shed = (data.get("shed") or "").strip() or None
    lot = (data.get("lot") or "").strip() or None
    if shed and len(shed) > 50:
        return jsonify({"error": "Tên chuồng quá dài."}), 400
    if lot and len(lot) > 50:
        return jsonify({"error": "Tên lô quá dài."}), 400

    try:
        farm_id = int(data.get("farm_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn trang trại."}), 400
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and farm_id not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403
    try:
        zone_id = int(data.get("zone_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn khu."}), 400
    try:
        pig_type_id = int(data.get("pig_type_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn loại heo bán."}), 400
    if not any(pt["id"] == pig_type_id for pt in list_pig_types_locked(active_only=True)):
        return jsonify({"error": "Loại heo không hợp lệ hoặc đã ngừng dùng."}), 400
    try:
        date.fromisoformat(planned_date)
    except (TypeError, ValueError):
        return jsonify({"error": "Ngày dự kiến không hợp lệ."}), 400
    try:
        quantity = int(data.get("quantity"))
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Số lượng không hợp lệ."}), 400

    username = session["user"]["username"]
    plan_id = create_plan_locked(
        {
            "planned_date": planned_date,
            "farm_id": farm_id,
            "zone_id": zone_id,
            "shed": shed,
            "lot": lot,
            "pig_type_id": pig_type_id,
            "quantity": quantity,
            "note": note,
        },
        request.remote_addr,
        username,
    )
    log_audit(
        audit_actions.PLAN_CREATE,
        entity_type="sale_plan",
        entity_id=plan_id,
        new_value={
            "planned_date": planned_date,
            "farm_id": farm_id,
            "zone_id": zone_id,
            "shed": shed,
            "lot": lot,
            "pig_type_id": pig_type_id,
            "quantity": quantity,
        },
    )
    df = load_df()
    nat = national_price(df)
    plan = get_plan_locked(plan_id)
    return jsonify(plan_payload(plan, df, nat)), 201


@plans_bp.route("/api/plans/<int:plan_id>/approve", methods=["POST"])
@permission_required(perm.PLAN_REVIEW)
def api_plans_approve(plan_id: int):
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    if old_plan["status"] != "pending_approval":
        return jsonify({"error": "Kế hoạch không ở trạng thái chờ duyệt."}), 400

    username = session["user"]["username"]
    approve_plan_locked(plan_id, request.remote_addr, username)
    log_audit(
        audit_actions.PLAN_APPROVE,
        entity_type="sale_plan",
        entity_id=plan_id,
        old_value={"status": "pending_approval"},
        new_value={"status": "approved", "approved_by": username},
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>/reject", methods=["POST"])
@permission_required(perm.PLAN_REVIEW)
def api_plans_reject(plan_id: int):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "Vui lòng nhập lý do từ chối hợp lệ."}), 400
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    if old_plan["status"] != "pending_approval":
        return jsonify({"error": "Kế hoạch không ở trạng thái chờ duyệt."}), 400

    username = session["user"]["username"]
    reject_plan_locked(plan_id, reason, request.remote_addr, username)
    log_audit(
        audit_actions.PLAN_REJECT,
        entity_type="sale_plan",
        entity_id=plan_id,
        old_value={"status": "pending_approval"},
        new_value={"status": "rejected", "rejected_by": username, "rejected_reason": reason},
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>", methods=["PATCH"])
@permission_required(perm.PLAN_REVIEW)
def api_plans_update(plan_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("cancelled", "disabled", "approved"):
        return jsonify({"error": "Trạng thái không hợp lệ."}), 400
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    if old_plan["status"] in ("pending_approval", "rejected"):
        return jsonify({"error": "Chỉ dùng chức năng Duyệt/Từ chối để xử lý kế hoạch đang chờ duyệt."}), 400
    if status == "approved" and old_plan["status"] != "disabled":
        return jsonify({"error": "Chỉ dùng chức năng Duyệt để chuyển kế hoạch từ Chờ duyệt sang Đã duyệt."}), 400

    username = session["user"]["username"]
    update_plan_status_locked(plan_id, status, request.remote_addr, username)
    log_audit(
        audit_actions.PLAN_UPDATE_STATUS,
        entity_type="sale_plan",
        entity_id=plan_id,
        old_value={"status": old_plan["status"]},
        new_value={"status": status},
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>/received", methods=["PATCH"])
@permission_required(perm.PLAN_RECEIVE)
def api_plans_received(plan_id: int):
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    if old_plan["status"] != "approved":
        return jsonify({"error": "Chỉ ghi nhận số lượng thực nhận cho kế hoạch đã duyệt."}), 400
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    data = request.get_json(silent=True) or {}
    try:
        received_quantity = int(data.get("received_quantity"))
        if received_quantity < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Số lượng thực nhận không hợp lệ."}), 400

    username = session["user"]["username"]
    update_plan_received_quantity_locked(plan_id, received_quantity, request.remote_addr, username)
    log_audit(
        audit_actions.PLAN_UPDATE_RECEIVED,
        entity_type="sale_plan",
        entity_id=plan_id,
        old_value={"received_quantity": old_plan["received_quantity"]},
        new_value={"received_quantity": received_quantity},
    )
    return jsonify({"ok": True})


@plans_bp.route("/khach-hang", methods=["GET"])
@permission_required(perm.CUSTOMER_VIEW)
def customers_page():
    return render_template("khach_hang.html", customers=list_customers_locked())


@plans_bp.route("/api/customers", methods=["GET"])
@permission_required(perm.CUSTOMER_VIEW)
def api_customers_list():
    active_only = request.args.get("active_only") in ("1", "true", "True")
    return jsonify(list_customers_locked(active_only=active_only))


@plans_bp.route("/api/customers", methods=["POST"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    address = (data.get("address") or "").strip() or None
    tax_code = (data.get("tax_code") or "").strip() or None
    note = (data.get("note") or "").strip() or None
    email = (data.get("email") or "").strip() or None
    contact_person = (data.get("contact_person") or "").strip() or None
    contact_title = (data.get("contact_title") or "").strip() or None

    if not name or len(name) > 150:
        return jsonify({"error": "Vui lòng nhập tên khách hàng hợp lệ."}), 400
    if phone and len(phone) > 30:
        return jsonify({"error": "Số điện thoại quá dài."}), 400
    if tax_code and len(tax_code) > 20:
        return jsonify({"error": "Mã số thuế quá dài."}), 400
    if email and (len(email) > 100 or "@" not in email):
        return jsonify({"error": "Email không hợp lệ."}), 400
    if contact_person and len(contact_person) > 100:
        return jsonify({"error": "Tên người liên hệ quá dài."}), 400
    if contact_title and len(contact_title) > 100:
        return jsonify({"error": "Chức vụ quá dài."}), 400

    customer_id = create_customer_locked(name, phone, address, tax_code, note, email, contact_person, contact_title)
    log_audit(
        audit_actions.CUSTOMER_CREATE,
        entity_type="customer",
        entity_id=customer_id,
        new_value={"name": name, "phone": phone, "address": address, "tax_code": tax_code, "email": email},
    )
    return jsonify(list_customers_locked()), 201


@plans_bp.route("/api/customers/<int:customer_id>", methods=["PATCH"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_update(customer_id: int):
    old_customer = get_customer_locked(customer_id)
    if old_customer is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    address = (data.get("address") or "").strip() or None
    tax_code = (data.get("tax_code") or "").strip() or None
    note = (data.get("note") or "").strip() or None
    email = (data.get("email") or "").strip() or None
    contact_person = (data.get("contact_person") or "").strip() or None
    contact_title = (data.get("contact_title") or "").strip() or None

    if not name or len(name) > 150:
        return jsonify({"error": "Tên khách hàng không hợp lệ."}), 400
    if phone and len(phone) > 30:
        return jsonify({"error": "Số điện thoại quá dài."}), 400
    if tax_code and len(tax_code) > 20:
        return jsonify({"error": "Mã số thuế quá dài."}), 400
    if email and (len(email) > 100 or "@" not in email):
        return jsonify({"error": "Email không hợp lệ."}), 400
    if contact_person and len(contact_person) > 100:
        return jsonify({"error": "Tên người liên hệ quá dài."}), 400
    if contact_title and len(contact_title) > 100:
        return jsonify({"error": "Chức vụ quá dài."}), 400

    update_customer_locked(
        customer_id, name, phone, address, tax_code, note, email, contact_person, contact_title
    )
    log_audit(
        audit_actions.CUSTOMER_UPDATE,
        entity_type="customer",
        entity_id=customer_id,
        old_value={
            "name": old_customer["name"],
            "phone": old_customer["phone"],
            "address": old_customer["address"],
            "tax_code": old_customer["tax_code"],
        },
        new_value={"name": name, "phone": phone, "address": address, "tax_code": tax_code, "email": email},
    )
    return jsonify(list_customers_locked())


@plans_bp.route("/api/customers/<int:customer_id>/toggle", methods=["POST"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_toggle(customer_id: int):
    if get_customer_locked(customer_id) is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    set_customer_active_locked(customer_id, is_active)
    log_audit(
        audit_actions.CUSTOMER_ACTIVATE if is_active else audit_actions.CUSTOMER_DEACTIVATE,
        entity_type="customer",
        entity_id=customer_id,
    )
    return jsonify(list_customers_locked())


@plans_bp.route("/api/customers/<int:customer_id>", methods=["DELETE"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_delete(customer_id: int):
    old_customer = get_customer_locked(customer_id)
    if old_customer is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    if count_allocations_for_customer_locked(customer_id) > 0:
        return jsonify({"error": "Không thể xóa: khách hàng đang được dùng trong kế hoạch xuất bán."}), 400
    delete_customer_locked(customer_id)
    log_audit(
        audit_actions.CUSTOMER_DELETE,
        entity_type="customer",
        entity_id=customer_id,
        old_value={"name": old_customer["name"], "phone": old_customer["phone"]},
    )
    return jsonify(list_customers_locked())


@plans_bp.route("/api/allocations", methods=["GET"])
def api_allocations_list():
    """Không gate cứng bằng permission_required — vai trò farm (không có bất
    kỳ quyền nào liên quan allocation) chỉ nhận [] thay vì 403, khớp cách
    /api/plans hiện xử lý farm chưa được gán trại (trả rỗng, không lỗi)."""
    user_perms = {
        perm.PLAN_ALLOCATION_CREATE,
        perm.PLAN_ALLOCATION_MANAGE,
        perm.PLAN_SALE_DETAILS,
        perm.PLAN_REVENUE_DETAILS,
    }
    if not (current_user_permissions() & user_perms):
        return jsonify([])
    sale_plan_id = request.args.get("sale_plan_id", type=int)
    df = load_df()
    nat = national_price(df)
    allocs = list_allocations_locked(sale_plan_id=sale_plan_id)
    return jsonify([allocation_payload(a, df, nat) for a in allocs])


@plans_bp.route("/api/allocations", methods=["POST"])
@permission_required(perm.PLAN_ALLOCATION_CREATE)
def api_allocations_create():
    data = request.get_json(silent=True) or {}
    try:
        sale_plan_id = int(data.get("sale_plan_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn kế hoạch trại."}), 400
    plan = get_plan_locked(sale_plan_id)
    if plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch trại."}), 404
    if plan["status"] != "approved":
        return jsonify({"error": "Chỉ tạo kế hoạch bán từ kế hoạch trại đã duyệt."}), 400
    try:
        quantity = int(data.get("quantity"))
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Số lượng không hợp lệ."}), 400
    if quantity > plan["remaining_quantity"]:
        return jsonify({"error": f"Vượt quá số lượng còn lại ({plan['remaining_quantity']} con)."}), 400
    try:
        selling_price = int(data.get("selling_price"))
        if selling_price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng nhập giá chào bán hợp lệ."}), 400
    note = (data.get("note") or "").strip() or None

    username = session["user"]["username"]
    allocation_id = create_allocation_locked(
        {"sale_plan_id": sale_plan_id, "quantity": quantity, "selling_price": selling_price, "note": note},
        request.remote_addr,
        username,
    )
    log_audit(
        audit_actions.ALLOCATION_CREATE,
        entity_type="sale_allocation",
        entity_id=allocation_id,
        new_value={"sale_plan_id": sale_plan_id, "quantity": quantity, "selling_price": selling_price},
    )
    df = load_df()
    nat = national_price(df)
    alloc = get_allocation_locked(allocation_id)
    return jsonify(allocation_payload(alloc, df, nat)), 201


@plans_bp.route("/api/allocations/<int:allocation_id>", methods=["PATCH"])
@permission_required(perm.PLAN_ALLOCATION_MANAGE)
def api_allocations_update(allocation_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("done", "cancelled", "disabled", "active"):
        return jsonify({"error": "Trạng thái không hợp lệ."}), 400
    old_alloc = get_allocation_locked(allocation_id)
    if old_alloc is None:
        return jsonify({"error": "Không tìm thấy kế hoạch bán."}), 404

    actual_price = None
    actual_quantity = None
    if status == "done":
        try:
            actual_price = int(data.get("actual_price"))
            actual_quantity = int(data.get("actual_quantity"))
            if actual_price <= 0 or actual_quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Vui lòng nhập giá bán và số lượng bán thực tế hợp lệ."}), 400

    username = session["user"]["username"]
    update_allocation_status_locked(
        allocation_id, status, request.remote_addr, username, actual_price, actual_quantity
    )
    log_audit(
        audit_actions.ALLOCATION_UPDATE_STATUS,
        entity_type="sale_allocation",
        entity_id=allocation_id,
        old_value={
            "status": old_alloc["status"],
            "actual_price": old_alloc["actual_price"],
            "actual_quantity": old_alloc["actual_quantity"],
        },
        new_value={"status": status, "actual_price": actual_price, "actual_quantity": actual_quantity},
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/allocations/<int:allocation_id>/sale-details", methods=["PATCH"])
@permission_required(perm.PLAN_SALE_DETAILS)
def api_allocations_sale_details(allocation_id: int):
    old_alloc = get_allocation_locked(allocation_id)
    if old_alloc is None:
        return jsonify({"error": "Không tìm thấy kế hoạch bán."}), 404

    data = request.get_json(silent=True) or {}
    fields: dict = {}
    if "customer_id" in data:
        raw = data["customer_id"]
        if raw in (None, ""):
            fields["customer_id"] = None
        else:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Khách hàng không hợp lệ."}), 400
            if get_customer_locked(cid) is None:
                return jsonify({"error": "Không tìm thấy khách hàng."}), 400
            fields["customer_id"] = cid
    if "contact_note" in data:
        note = (data["contact_note"] or "").strip()
        if len(note) > 1000:
            return jsonify({"error": "Ghi chú liên hệ quá dài."}), 400
        fields["contact_note"] = note or None
    if "confirmed_sale_at" in data:
        raw_date = (data["confirmed_sale_at"] or "").strip()
        if raw_date:
            try:
                date.fromisoformat(raw_date)
            except ValueError:
                return jsonify({"error": "Ngày chốt bán không hợp lệ."}), 400
            fields["confirmed_sale_at"] = raw_date
        else:
            fields["confirmed_sale_at"] = None
    if "selling_price" in data:
        raw = data["selling_price"]
        if raw in (None, ""):
            fields["selling_price"] = None
        else:
            try:
                selling_price = int(raw)
                if selling_price <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return jsonify({"error": "Giá chào bán không hợp lệ."}), 400
            fields["selling_price"] = selling_price
    if "delivery_time" in data:
        dt = (data["delivery_time"] or "").strip()
        if len(dt) > 50:
            return jsonify({"error": "Khung giờ giao quá dài."}), 400
        fields["delivery_time"] = dt or None
    if "payment_method" in data:
        pm = (data["payment_method"] or "").strip() or None
        if pm is not None and pm not in PAYMENT_METHODS:
            return jsonify({"error": "Hình thức thanh toán không hợp lệ."}), 400
        fields["payment_method"] = pm
    if not fields:
        return jsonify({"error": "Không có dữ liệu để cập nhật."}), 400

    username = session["user"]["username"]
    update_allocation_sale_details_locked(allocation_id, request.remote_addr, username, fields)
    log_audit(
        audit_actions.ALLOCATION_UPDATE_SALE_DETAILS,
        entity_type="sale_allocation",
        entity_id=allocation_id,
        old_value={k: old_alloc.get(k) for k in fields},
        new_value=fields,
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/allocations/<int:allocation_id>/revenue-details", methods=["PATCH"])
@permission_required(perm.PLAN_REVENUE_DETAILS)
def api_allocations_revenue_details(allocation_id: int):
    old_alloc = get_allocation_locked(allocation_id)
    if old_alloc is None:
        return jsonify({"error": "Không tìm thấy kế hoạch bán."}), 404
    if old_alloc["status"] != "done":
        return jsonify({"error": "Chỉ ghi nhận doanh thu cho kế hoạch bán đã bán."}), 400

    data = request.get_json(silent=True) or {}
    fields: dict = {}
    if "paid_amount" in data:
        raw = data["paid_amount"]
        if raw in (None, ""):
            fields["paid_amount"] = None
        else:
            try:
                amount = int(raw)
                if amount < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return jsonify({"error": "Số tiền đã thu không hợp lệ."}), 400
            fields["paid_amount"] = amount
    if "weighing_ref" in data:
        ref = (data["weighing_ref"] or "").strip()
        if len(ref) > 100:
            return jsonify({"error": "Số chứng từ cân quá dài."}), 400
        fields["weighing_ref"] = ref or None
    if "invoice_number" in data:
        inv = (data["invoice_number"] or "").strip()
        if len(inv) > 50:
            return jsonify({"error": "Số hoá đơn quá dài."}), 400
        fields["invoice_number"] = inv or None
    if not fields:
        return jsonify({"error": "Không có dữ liệu để cập nhật."}), 400

    username = session["user"]["username"]
    update_allocation_revenue_details_locked(allocation_id, request.remote_addr, username, fields)
    log_audit(
        audit_actions.ALLOCATION_UPDATE_REVENUE_DETAILS,
        entity_type="sale_allocation",
        entity_id=allocation_id,
        old_value={k: old_alloc.get(k) for k in fields},
        new_value=fields,
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/allocations/export.xlsx")
def export_allocations_excel():
    buffer = BytesIO()
    try:
        export_allocations_excel_locked(buffer)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    filename = f"ke_hoach_ban_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@plans_bp.route("/api/allocations/quotation.xlsx")
@permission_required(perm.PLAN_SALE_DETAILS)
def export_allocation_quotation_excel():
    raw_ids = (request.args.get("ids") or "").strip()
    try:
        allocation_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        return jsonify({"error": "Danh sách kế hoạch bán không hợp lệ."}), 400
    if not allocation_ids:
        return jsonify({"error": "Vui lòng chọn ít nhất 1 kế hoạch bán."}), 400
    buffer = BytesIO()
    try:
        export_allocation_quotation_excel_locked(buffer, allocation_ids)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    filename = f"chao_hang_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@plans_bp.route("/api/plans/export.xlsx")
def export_plans_excel():
    buffer = BytesIO()
    try:
        export_plans_excel_locked(buffer)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    filename = f"ke_hoach_xuat_ban_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )
