"""Blueprint kế hoạch xuất bán + API liên quan (farms/zones/pig-types/plans)."""
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from flask import Blueprint, jsonify, render_template, request, send_file, session

from core import audit_actions
from core import permissions as perm
from core.repositories.plan_reconciliation_repo import PHOTO_REQUIRED_KINDS, VALID_KINDS as RECONCILE_VALID_KINDS
from core.scrapers.utils import normalize_province
from core.services import customer_service, order_service, plan_service
from data_access import (
    count_orders_for_customer_locked,
    export_order_quotation_excel_locked,
    export_orders_excel_locked,
    export_plans_excel_locked,
    get_customer_locked,
    get_order_locked,
    get_plan_locked,
    get_plan_sale_breakdown_locked,
    get_reconciliation_locked,
    list_customers_locked,
    list_farms_locked,
    list_media_for_entity_locked,
    list_orders_locked,
    list_pig_types_locked,
    list_plans_locked,
    list_reconciliations_for_plan_locked,
    list_zones_locked,
    load_df,
    save_media_upload_locked,
)
from extensions import DB_PATH, log_audit
from routes.auth import allowed_farm_ids, current_user_permissions, permission_required
from routes.incidents import _validate_photo

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
    sang line_payload, so với selling_price của từng dòng hàng)."""
    try:
        days_left = (date.fromisoformat(plan["planned_date"]) - date.today()).days
    except ValueError:
        days_left = None
    return {**plan, "days_left": days_left}


def line_payload(line: dict, df: pd.DataFrame, nat: dict) -> dict:
    """So giá thị trường hiện tại với selling_price của TỪNG DÒNG hàng — logic
    này trước đây áp cho kế hoạch trại (target_price), nay ở cấp dòng hàng
    (Giai đoạn 8: 1 đơn có thể gồm nhiều dòng khác loại heo/tỉnh, mỗi dòng
    phải so giá riêng theo đúng kế hoạch trại nó lấy từ)."""
    cur = current_price_for_plan(df, line.get("province"), nat)
    reached = (
        cur["price"] is not None and line.get("selling_price") is not None and cur["price"] >= line["selling_price"]
    )
    try:
        days_left = (date.fromisoformat(line["planned_date"]) - date.today()).days
    except (ValueError, TypeError):
        days_left = None
    return {
        **line,
        "current_price": cur["price"],
        "current_price_date": cur["date"],
        "current_price_is_national": cur["is_national"],
        "reached_target": reached,
        "days_left": days_left,
    }


def order_payload(order: dict, df: pd.DataFrame, nat: dict) -> dict:
    return {**order, "lines": [line_payload(line, df, nat) for line in order["lines"]]}


@plans_bp.route("/ke-hoach")
def plans_page():
    return render_template("plans.html")


@plans_bp.route("/ke-hoach-ban")
def allocations_page():
    return render_template("allocations.html")


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
    """STEP 7 (Route Refactor): validate định dạng/giá trị input đã
    chuyển vào plan_service._validate_plan_fields() (dùng chung với
    api_plans_edit()) — route chỉ còn giữ lại đúng phần farm-scope check
    (403, phải biết farm_id TRƯỚC khi ghi) + gọi service."""
    data = request.get_json(silent=True) or {}
    try:
        farm_id = int(data.get("farm_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn trang trại."}), 400
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and farm_id not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    username = session["user"]["username"]
    # Tạo kế hoạch + ghi audit trong CÙNG 1 transaction (STEP 2 Service
    # Layer + STEP 4 Transaction Standardization theo
    # PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md) — trước đây 2 bước này tách
    # rời (create_plan_locked rồi log_audit riêng), nếu bước audit lỗi thì
    # kế hoạch đã tạo nhưng mất vết audit.
    try:
        plan_id = plan_service.create_plan(data, DB_PATH, ip=request.remote_addr, username=username)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
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
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    username = session["user"]["username"]
    plan_service.approve_plan(plan_id, DB_PATH, ip=request.remote_addr, username=username)
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
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    username = session["user"]["username"]
    plan_service.reject_plan(plan_id, reason, DB_PATH, ip=request.remote_addr, username=username)
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
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    username = session["user"]["username"]
    plan_service.update_plan_status(
        plan_id, status, old_plan["status"], DB_PATH, ip=request.remote_addr, username=username
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
    plan_service.record_received(
        plan_id,
        received_quantity,
        old_plan["received_quantity"],
        DB_PATH,
        ip=request.remote_addr,
        username=username,
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>/edit", methods=["PATCH"])
@permission_required(perm.PLAN_EDIT)
def api_plans_edit(plan_id: int):
    """Sửa lại nội dung kế hoạch trại (nhập nhầm) — khác PATCH /api/plans/<id>
    (chỉ đổi status). Quyền admin-only-by-default (perm.PLAN_EDIT) nên KHÔNG
    còn giới hạn theo status/allocated_quantity (Giai đoạn 9) — admin sửa
    được bất kể trạng thái, kể cả khi đã có kế hoạch bán tham chiếu."""
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    data = request.get_json(silent=True) or {}
    # farm_id mới (có thể khác old_plan["farm_id"] nếu đổi trại) cũng phải
    # nằm trong farm-scope — validate định dạng/giá trị còn lại đã chuyển
    # vào plan_service._validate_plan_fields() (STEP 7 Route Refactor).
    try:
        new_farm_id = int(data.get("farm_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Vui lòng chọn trang trại."}), 400
    if farm_ids is not None and new_farm_id not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    username = session["user"]["username"]
    try:
        updated = plan_service.edit_plan(
            plan_id, data, old_plan, DB_PATH, ip=request.remote_addr, username=username
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not updated:
        return jsonify({"error": "Kế hoạch không còn tồn tại, vui lòng tải lại trang."}), 404
    df = load_df()
    nat = national_price(df)
    plan = get_plan_locked(plan_id)
    return jsonify(plan_payload(plan, df, nat))


@plans_bp.route("/api/plans/<int:plan_id>", methods=["DELETE"])
@permission_required(perm.PLAN_DELETE)
def api_plans_delete(plan_id: int):
    """Xoá vĩnh viễn kế hoạch trại — quyền admin-only-by-default. Chặn nếu
    còn kế hoạch bán nào (dòng hàng) từng tạo từ đó, kể cả đã huỷ."""
    old_plan = get_plan_locked(plan_id)
    if old_plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and old_plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403
    deleted = plan_service.delete_plan(
        plan_id, old_plan, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    if not deleted:
        return jsonify({"error": "Không thể xoá: đã có kế hoạch bán tạo từ kế hoạch này."}), 400
    return jsonify({"ok": True})


_VIEW_PLAN_RECONCILE_PERMS = (perm.PLAN_REVIEW, perm.PLAN_RECEIVE, perm.PLAN_EDIT, perm.PLAN_RECONCILE_CREATE)


@plans_bp.route("/api/plans/<int:plan_id>/reconciliations", methods=["POST"])
@permission_required(perm.PLAN_RECONCILE_CREATE)
def api_plan_reconciliation_create(plan_id: int):
    """Xử lý chênh lệch kế hoạch trại — ghi nhận 1 phần (hoặc toàn bộ) số
    lượng chưa giải thích (remaining_to_reconcile) là: còn tại trại/tiếp tục
    bán (ghi nhận, không đóng kế hoạch) hoặc chuyển nguồn/loại/khách hủy/khác
    (đóng dần kế hoạch). KHÔNG đụng sale_plans.quantity."""
    plan = get_plan_locked(plan_id)
    if plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    if plan["status"] != "approved":
        return jsonify({"error": "Chỉ xử lý chênh lệch cho kế hoạch đã duyệt."}), 400
    if plan.get("locked_at"):
        return jsonify({"error": "Kế hoạch đã khoá vĩnh viễn, không thể xử lý chênh lệch."}), 400
    farm_ids = allowed_farm_ids(session["user"])
    if farm_ids is not None and plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403

    kind = (request.form.get("kind") or "").strip()
    if kind not in RECONCILE_VALID_KINDS:
        return jsonify({"error": "Loại xử lý không hợp lệ."}), 400
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "Vui lòng nhập lý do."}), 400
    try:
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return jsonify({"error": "Số lượng không hợp lệ."}), 400
    if quantity <= 0:
        return jsonify({"error": "Số lượng phải lớn hơn 0."}), 400
    remaining = plan["remaining_to_reconcile"]
    if quantity > remaining:
        return jsonify({"error": f"Số lượng vượt quá số chưa xử lý ({remaining} con)."}), 400

    photos = [f for f in request.files.getlist("photos") if f and f.filename]
    if kind in PHOTO_REQUIRED_KINDS and not photos:
        return jsonify({"error": "Vui lòng đính kèm ít nhất 1 ảnh làm bằng chứng."}), 400
    for photo in photos:
        err = _validate_photo(photo)
        if err:
            return jsonify({"error": err}), 400

    username = session["user"]["username"]
    ip = request.remote_addr
    reconciliation = plan_service.create_reconciliation(plan_id, kind, quantity, reason, DB_PATH, ip=ip, username=username)

    media_list = []
    for photo in photos:
        saved = save_media_upload_locked(
            photo.read(),
            "plan_reconciliation",
            reconciliation["id"],
            kind,
            username,
            ip,
            photo.filename,
            photo.mimetype,
        )
        media_list.append(saved)

    log_audit(
        audit_actions.PLAN_RECONCILE_CREATE,
        entity_type="sale_plan",
        entity_id=plan_id,
        new_value={"kind": kind, "quantity": quantity, "reason": reason, "photos": len(media_list)},
    )
    reconciliation["media"] = media_list
    return jsonify(reconciliation), 201


@plans_bp.route("/api/plans/<int:plan_id>/reconciliations", methods=["GET"])
@permission_required(*_VIEW_PLAN_RECONCILE_PERMS)
def api_plan_reconciliation_list(plan_id: int):
    plan = get_plan_locked(plan_id)
    if plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    items = list_reconciliations_for_plan_locked(plan_id)
    for item in items:
        item["media"] = list_media_for_entity_locked("plan_reconciliation", item["id"])
    return jsonify(items)


@plans_bp.route("/api/reconciliations/<int:reconciliation_id>", methods=["DELETE"])
@permission_required(perm.PLAN_RECONCILE_DELETE)
def api_plan_reconciliation_delete(reconciliation_id: int):
    reconciliation = get_reconciliation_locked(reconciliation_id)
    if reconciliation is None:
        return jsonify({"error": "Không tìm thấy bản ghi."}), 404
    plan = get_plan_locked(reconciliation["sale_plan_id"])
    farm_ids = allowed_farm_ids(session["user"])
    if plan is not None and farm_ids is not None and plan["farm_id"] not in farm_ids:
        return jsonify({"error": "Bạn không được gán quản lý trang trại này."}), 403
    plan_service.delete_reconciliation(
        reconciliation_id, reconciliation, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>/sale-breakdown", methods=["GET"])
@permission_required(*_VIEW_PLAN_RECONCILE_PERMS)
def api_plan_sale_breakdown(plan_id: int):
    """Đối soát đa chiều (Phase 2): breakdown Khách hàng/Giá/Phiếu cân theo
    kế hoạch — 1 kế hoạch có thể tách nhiều đơn/khách/giá nên trả về danh
    sách (mỗi phần tử = 1 dòng hàng đã nhặt từ kế hoạch), không rút gọn về
    1 field. Xem get_plan_sale_breakdown() (sale_plans_repo.py)."""
    plan = get_plan_locked(plan_id)
    if plan is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    return jsonify(get_plan_sale_breakdown_locked(plan_id))


@plans_bp.route("/doi-soat")
@permission_required(*_VIEW_PLAN_RECONCILE_PERMS)
def doi_soat_page():
    """Trang triage đối soát — dữ liệu load qua JS (fetch /api/plans có
    sẵn), không truyền gì qua Jinja, khớp khuôn allocations_page()."""
    return render_template("doi_soat.html")


@plans_bp.route("/bao-cao")
def bao_cao_page():
    """Trang gộp link tới 3 export Excel đã có (giá heo/kế hoạch trại/kế
    hoạch bán) — không gate permission, khớp đúng thực tế cả 3 route export
    đích đều không gate (chỉ cần đăng nhập)."""
    return render_template("bao_cao.html")


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
    """STEP 7 (Route Refactor): validate đã chuyển vào
    customer_service._validate_customer_fields() (dùng chung với
    api_customers_update())."""
    data = request.get_json(silent=True) or {}
    try:
        customer_service.create_customer(
            data, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_customers_locked()), 201


@plans_bp.route("/api/customers/<int:customer_id>", methods=["PATCH"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_update(customer_id: int):
    old_customer = get_customer_locked(customer_id)
    if old_customer is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    data = request.get_json(silent=True) or {}
    try:
        customer_service.update_customer(
            customer_id, data, old_customer, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_customers_locked())


@plans_bp.route("/api/customers/<int:customer_id>/toggle", methods=["POST"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_toggle(customer_id: int):
    if get_customer_locked(customer_id) is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    customer_service.set_active(
        customer_id, is_active, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(list_customers_locked())


@plans_bp.route("/api/customers/<int:customer_id>", methods=["DELETE"])
@permission_required(perm.CUSTOMER_MANAGE)
def api_customers_delete(customer_id: int):
    old_customer = get_customer_locked(customer_id)
    if old_customer is None:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    if count_orders_for_customer_locked(customer_id) > 0:
        return jsonify({"error": "Không thể xóa: khách hàng đang được dùng trong kế hoạch xuất bán."}), 400
    customer_service.delete_customer(
        customer_id, old_customer, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(list_customers_locked())


@plans_bp.route("/api/orders", methods=["GET"])
def api_orders_list():
    """Không gate cứng bằng permission_required — vai trò farm (không có bất
    kỳ quyền nào liên quan đơn hàng) chỉ nhận [] thay vì 403, khớp cách
    /api/plans hiện xử lý farm chưa được gán trại (trả rỗng, không lỗi)."""
    user_perms = {
        perm.PLAN_ALLOCATION_CREATE,
        perm.PLAN_ALLOCATION_MANAGE,
        perm.PLAN_SALE_DETAILS,
        perm.PLAN_REVENUE_DETAILS,
    }
    if not (current_user_permissions() & user_perms):
        return jsonify([])
    df = load_df()
    nat = national_price(df)
    orders = list_orders_locked()
    return jsonify([order_payload(o, df, nat) for o in orders])


@plans_bp.route("/api/orders", methods=["POST"])
@permission_required(perm.PLAN_ALLOCATION_CREATE)
def api_orders_create():
    """STEP 7 (Route Refactor): validate dòng hàng đã chuyển vào
    order_service._validate_lines() (dùng chung với api_order_add_line())."""
    data = request.get_json(silent=True) or {}
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        return jsonify({"error": "Vui lòng thêm ít nhất 1 dòng heo vào đơn."}), 400

    username = session["user"]["username"]
    try:
        order_id = order_service.create_order(raw_lines, DB_PATH, ip=request.remote_addr, username=username)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    df = load_df()
    nat = national_price(df)
    order = get_order_locked(order_id)
    return jsonify(order_payload(order, df, nat)), 201


@plans_bp.route("/api/orders/<int:order_id>/lines", methods=["POST"])
@permission_required(perm.PLAN_ALLOCATION_CREATE)
def api_order_add_line(order_id: int):
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if order["status"] != "active":
        return jsonify({"error": "Chỉ thêm dòng vào đơn đang xử lý."}), 400
    data = request.get_json(silent=True) or {}

    username = session["user"]["username"]
    try:
        line_id = order_service.add_line(order_id, data, DB_PATH, ip=request.remote_addr, username=username)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    df = load_df()
    nat = national_price(df)
    order = get_order_locked(order_id)
    return jsonify(order_payload(order, df, nat)), 201


@plans_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>", methods=["DELETE"])
@permission_required(perm.PLAN_ALLOCATION_CREATE)
def api_order_remove_line(order_id: int, line_id: int):
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if order["status"] != "active":
        return jsonify({"error": "Chỉ xoá dòng khi đơn đang xử lý."}), 400
    if len(order["lines"]) <= 1:
        return jsonify({"error": "Đơn hàng phải có ít nhất 1 dòng."}), 400

    username = session["user"]["username"]
    removed = order_service.remove_line(order_id, line_id, DB_PATH, ip=request.remote_addr, username=username)
    if not removed:
        return jsonify({"error": "Không tìm thấy dòng hàng."}), 404
    df = load_df()
    nat = national_price(df)
    order = get_order_locked(order_id)
    return jsonify(order_payload(order, df, nat))


@plans_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>", methods=["PATCH"])
@permission_required(perm.ORDER_EDIT_LINE)
def api_order_edit_line(order_id: int, line_id: int):
    """Sửa số lượng/giá/ghi chú 1 dòng hàng ĐÃ TẠO, bất kể trạng thái đơn —
    quyền admin-only-by-default, khác hẳn thêm/xoá dòng (PLAN_ALLOCATION_CREATE,
    chỉ áp dụng khi đơn active). Không validate lại remaining_quantity của kế
    hoạch trại — người dùng quyền này tự chịu trách nhiệm số liệu."""
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    old_line = next((line for line in order["lines"] if line["id"] == line_id), None)
    if old_line is None:
        return jsonify({"error": "Không tìm thấy dòng hàng."}), 404

    data = request.get_json(silent=True) or {}
    fields: dict = {}
    if "quantity" in data:
        try:
            quantity = int(data["quantity"])
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Số lượng không hợp lệ."}), 400
        fields["quantity"] = quantity
    if "selling_price" in data:
        try:
            selling_price = int(data["selling_price"])
            if selling_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Giá chào bán không hợp lệ."}), 400
        fields["selling_price"] = selling_price
    if "note" in data:
        note = (data["note"] or "").strip()
        fields["note"] = note or None
    if not fields:
        return jsonify({"error": "Không có dữ liệu để cập nhật."}), 400

    username = session["user"]["username"]
    order_service.edit_line(
        order_id, line_id, old_line, fields, DB_PATH, ip=request.remote_addr, username=username
    )
    df = load_df()
    nat = national_price(df)
    order = get_order_locked(order_id)
    return jsonify(order_payload(order, df, nat))


@plans_bp.route("/api/orders/<int:order_id>", methods=["PATCH"])
@permission_required(perm.PLAN_ALLOCATION_MANAGE)
def api_orders_update(order_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("cancelled", "disabled", "active"):
        return jsonify({"error": "Trạng thái không hợp lệ."}), 400
    old_order = get_order_locked(order_id)
    if old_order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404

    username = session["user"]["username"]
    order_service.update_status(
        order_id, status, old_order["status"], DB_PATH, ip=request.remote_addr, username=username
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/orders/<int:order_id>", methods=["DELETE"])
@permission_required(perm.ORDER_DELETE)
def api_orders_delete(order_id: int):
    """Xoá vĩnh viễn đơn hàng + toàn bộ dòng hàng — quyền admin-only-by-default.
    Chặn nếu có lần cân/sự cố gắn với dòng hàng của đơn (xem sale_orders_repo.delete_order)."""
    old_order = get_order_locked(order_id)
    if old_order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if old_order.get("locked_at"):
        return jsonify({"error": "Đơn hàng đã khoá, không thể xoá."}), 400
    deleted, reason = order_service.delete_order(
        order_id, old_order, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    if not deleted:
        return jsonify({"error": reason or "Không thể xoá đơn hàng."}), 400
    return jsonify({"ok": True})


@plans_bp.route("/api/orders/<int:order_id>/lock", methods=["PATCH"])
@permission_required(perm.ORDER_LOCK)
def api_orders_lock(order_id: int):
    """Data Freeze — khoá vĩnh viễn 1 đơn hàng đã hoàn tất (status='done').
    Sau khi khoá, mọi UPDATE lên sale_orders/sale_allocations của đơn này bị
    trigger DB chặn (DATA_FROZEN); DELETE bị chặn riêng ở route xoá phía
    trên (trigger DB hiện chỉ canh UPDATE)."""
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if order["status"] != "done":
        return jsonify({"error": "Chỉ khoá được đơn hàng đã hoàn tất (Đã bán)."}), 400
    if order.get("locked_at"):
        return jsonify({"error": "Đơn hàng đã được khoá từ trước."}), 400

    username = session["user"]["username"]
    locked = order_service.lock_order(
        order_id, order["order_code"], DB_PATH, ip=request.remote_addr, username=username
    )
    if not locked:
        return jsonify({"error": "Không thể khoá đơn hàng."}), 400
    order = get_order_locked(order_id)
    return jsonify(order)


@plans_bp.route("/api/orders/<int:order_id>/mark-done", methods=["PATCH"])
@permission_required(perm.PLAN_ALLOCATION_MANAGE)
def api_orders_mark_done(order_id: int):
    old_order = get_order_locked(order_id)
    if old_order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if old_order["status"] != "active":
        return jsonify({"error": "Chỉ đánh dấu Đã bán cho đơn đang xử lý."}), 400

    data = request.get_json(silent=True) or {}
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        return jsonify({"error": "Vui lòng nhập giá/số lượng bán thực tế cho từng dòng."}), 400
    line_ids = {line["id"] for line in old_order["lines"]}
    line_actuals = []
    for raw in raw_lines:
        if not isinstance(raw, dict):
            return jsonify({"error": "Dữ liệu dòng hàng không hợp lệ."}), 400
        try:
            allocation_id = int(raw.get("allocation_id"))
            actual_price = int(raw.get("actual_price"))
            actual_quantity = int(raw.get("actual_quantity"))
            if actual_price <= 0 or actual_quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Giá/số lượng bán thực tế không hợp lệ."}), 400
        if allocation_id not in line_ids:
            return jsonify({"error": "Dòng hàng không thuộc đơn này."}), 400
        line_actuals.append(
            {"allocation_id": allocation_id, "actual_price": actual_price, "actual_quantity": actual_quantity}
        )
    if len(line_actuals) != len(line_ids):
        return jsonify({"error": "Vui lòng nhập đủ giá/số lượng bán thực tế cho mọi dòng."}), 400

    username = session["user"]["username"]
    order_service.mark_done(order_id, line_actuals, DB_PATH, ip=request.remote_addr, username=username)
    return jsonify({"ok": True})


@plans_bp.route("/api/orders/<int:order_id>/sale-details", methods=["PATCH"])
@permission_required(perm.PLAN_SALE_DETAILS)
def api_orders_sale_details(order_id: int):
    old_order = get_order_locked(order_id)
    if old_order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404

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
    order_service.update_sale_details(
        order_id, old_order, fields, DB_PATH, ip=request.remote_addr, username=username
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/orders/<int:order_id>/revenue-details", methods=["PATCH"])
@permission_required(perm.PLAN_REVENUE_DETAILS)
def api_orders_revenue_details(order_id: int):
    old_order = get_order_locked(order_id)
    if old_order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    if old_order["status"] != "done":
        return jsonify({"error": "Chỉ ghi nhận doanh thu cho đơn đã bán."}), 400

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
    order_service.update_revenue_details(
        order_id, old_order, fields, DB_PATH, ip=request.remote_addr, username=username
    )
    return jsonify({"ok": True})


@plans_bp.route("/api/orders/export.xlsx")
def export_orders_excel():
    buffer = BytesIO()
    try:
        export_orders_excel_locked(buffer)
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


@plans_bp.route("/api/orders/quotation.xlsx")
@permission_required(perm.PLAN_SALE_DETAILS)
def export_order_quotation_excel():
    raw_ids = (request.args.get("ids") or "").strip()
    try:
        order_ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        return jsonify({"error": "Danh sách đơn hàng không hợp lệ."}), 400
    if not order_ids:
        return jsonify({"error": "Vui lòng chọn ít nhất 1 đơn hàng."}), 400
    buffer = BytesIO()
    try:
        export_order_quotation_excel_locked(buffer, order_ids)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    if len(order_ids) == 1:
        order = get_order_locked(order_ids[0])
        code = order["order_code"] if order else str(order_ids[0])
        safe_code = "".join(c if (c.isalnum() or c in "-_") else "_" for c in code)
        filename = f"Phieu_chao_gia_{safe_code}.xlsx"
    else:
        filename = f"Phieu_chao_gia_{datetime.now():%Y%m%d}.xlsx"
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
