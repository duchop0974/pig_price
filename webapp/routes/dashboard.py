"""Blueprint trang chủ (Tổng quan) + trang Quy trình xuất bán (sơ đồ)."""
from flask import Blueprint, jsonify, render_template, request, session, url_for

from core import permissions as perm
from data_access import (
    dashboard_summary_locked,
    daily_reconciliation_series_locked,
    list_awaiting_receipt_locked,
    list_awaiting_revenue_locked,
    list_awaiting_sale_details_locked,
    list_deliveries_missing_weight_locked,
    list_idle_supply_locked,
    list_needs_reconciliation_locked,
    list_pending_review_locked,
    list_stale_awaiting_revenue_locked,
    list_unexpected_farm_permissions_locked,
    pig_type_composition_locked,
)
from routes.auth import allowed_farm_ids, current_user_can, permission_required

dashboard_bp = Blueprint("dashboard", __name__)

# Cảnh báo (Exception Center) vào được nếu có ÍT NHẤT 1 trong 4 quyền dưới —
# khớp khuôn _VIEW_PLAN_RECONCILE_PERMS ở routes/plans.py.
_VIEW_EXCEPTION_PERMS = (
    perm.PLAN_REVENUE_DETAILS,
    perm.PLAN_ALLOCATION_CREATE,
    perm.DELIVERY_CREATE,
    perm.ADMIN_PERMISSIONS_MANAGE,
)

# Các bước của quy trình xuất bán, theo đúng thứ tự nghiệp vụ thực tế —
# mỗi bước gắn với 1 permission key (gate hiển thị) và 1 endpoint trang đích.
# Bước 1-3 nằm trên /ke-hoach (kế hoạch trại), bước 4-7 nằm trên /ke-hoach-ban
# (kế hoạch bán) — 2 trang riêng từ GĐ6.
PROCESS_STEPS = [
    {
        "title": "1. Tạo kế hoạch trại",
        "desc": "Trại đăng ký nguồn cung heo có sẵn (ngày, số lượng, loại heo, khu/chuồng/lô) — không có giá.",
        "icon": "📝",
        "permission": perm.PLAN_CREATE,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "2. Duyệt / Từ chối kế hoạch trại",
        "desc": "Phòng bán hàng xét duyệt kế hoạch trại gửi lên (bước tiếp nhận).",
        "icon": "✅",
        "permission": perm.PLAN_REVIEW,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "3. Ghi nhận xuất chuồng thực tế",
        "desc": "Trại ghi nhận số lượng thực tế đã xuất chuồng, bàn giao ra nhà chờ bán.",
        "icon": "📦",
        "permission": perm.PLAN_RECEIVE,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "4. Tạo kế hoạch bán",
        "desc": "Phòng bán hàng nhặt số lượng/loại heo từ kế hoạch trại đã duyệt, gán giá chào bán.",
        "icon": "🧾",
        "permission": perm.PLAN_ALLOCATION_CREATE,
        "endpoint": "plans.allocations_page",
    },
    {
        "title": "5. Chốt thông tin bán hàng",
        "desc": "Gán khách hàng, giá thoả thuận, thời gian & hình thức giao cho kế hoạch bán.",
        "icon": "🤝",
        "permission": perm.PLAN_SALE_DETAILS,
        "endpoint": "plans.allocations_page",
    },
    {
        "title": "6. Đánh dấu Đã bán",
        "desc": "Ghi nhận giá và số lượng bán thực tế khi hoàn tất xuất bán.",
        "icon": "🚚",
        "permission": perm.PLAN_ALLOCATION_MANAGE,
        "endpoint": "plans.allocations_page",
    },
    {
        "title": "7. Ghi nhận doanh thu & hoá đơn",
        "desc": "Kế toán ghi nhận số tiền đã thu, chứng từ cân, số hoá đơn.",
        "icon": "💰",
        "permission": perm.PLAN_REVENUE_DETAILS,
        "endpoint": "plans.allocations_page",
    },
    {
        "title": "8. Quản lý khách hàng",
        "desc": "Danh sách khách hàng dùng để gán vào bước Chốt thông tin bán hàng.",
        "icon": "👥",
        "permission": perm.CUSTOMER_VIEW,
        "endpoint": "plans.customers_page",
    },
]


def _build_exceptions(farm_ids: list[int] | None) -> list[dict]:
    """Khối "Cần xử lý" ở Tổng quan — mỗi nhóm chỉ hiện khi user có đúng
    quyền xử lý bước đó (giống cách PROCESS_STEPS gate hiển thị), và chỉ
    khi thực sự có việc (total > 0). ?highlight=<id> gắn vào link từng item
    để trang đích tự scroll+tô sáng đúng card (xem plan.js/allocation.js)."""
    exceptions = []

    if current_user_can(perm.PLAN_REVIEW):
        r = list_pending_review_locked(farm_ids=farm_ids)
        if r["total"]:
            exceptions.append(
                {
                    "icon": "⏳",
                    "text": f"{r['total']} kế hoạch trại chờ duyệt",
                    "entries": [
                        {
                            "label": f"{p['plan_code']} · {p['farm']} · {p['quantity']} con",
                            "url": url_for("plans.plans_page", highlight=p["id"]),
                        }
                        for p in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.plans_page"),
                }
            )

    if current_user_can(perm.PLAN_RECEIVE):
        r = list_awaiting_receipt_locked(farm_ids=farm_ids)
        if r["total"]:
            exceptions.append(
                {
                    "icon": "📦",
                    "text": f"{r['total']} kế hoạch quá ngày dự kiến chưa ghi nhận xuất chuồng",
                    "entries": [
                        {
                            "label": f"{p['plan_code']} · {p['farm']} · {p['quantity']} con",
                            "url": url_for("plans.plans_page", highlight=p["id"]),
                        }
                        for p in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.plans_page"),
                }
            )

    if current_user_can(perm.PLAN_SALE_DETAILS):
        r = list_awaiting_sale_details_locked()
        if r["total"]:
            exceptions.append(
                {
                    "icon": "🤝",
                    "text": f"{r['total']} đơn hàng chưa chốt bán hàng (chưa gán khách hàng)",
                    "entries": [
                        {"label": o["order_code"], "url": url_for("plans.allocations_page", highlight=o["id"])}
                        for o in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.allocations_page"),
                }
            )

    if current_user_can(perm.PLAN_REVENUE_DETAILS):
        r = list_awaiting_revenue_locked()
        if r["total"]:
            exceptions.append(
                {
                    "icon": "💰",
                    "text": f"{r['total']} đơn đã bán chưa ghi nhận doanh thu",
                    "entries": [
                        {"label": o["order_code"], "url": url_for("plans.allocations_page", highlight=o["id"])}
                        for o in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.allocations_page"),
                }
            )

    # Kế hoạch còn chênh lệch chưa xử lý VÀ đã quá ngày dự kiến — gate theo
    # đúng quyền hành động (plans.reconcile_create), khớp cách 4 loại trên
    # gate theo quyền xử lý bước đó, không phải quyền xem.
    if current_user_can(perm.PLAN_RECONCILE_CREATE):
        r = list_needs_reconciliation_locked(farm_ids=farm_ids)
        if r["total"]:
            exceptions.append(
                {
                    "icon": "⚖️",
                    "text": f"{r['total']} kế hoạch cần đối soát (còn chênh lệch, đã quá ngày dự kiến)",
                    "entries": [
                        {
                            "label": f"{p['plan_code']} · {p['farm']} · còn {p['remaining_to_reconcile']} con",
                            "url": url_for("plans.plans_page", highlight=p["id"]),
                        }
                        for p in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.plans_page"),
                }
            )

    return exceptions


def _build_true_exceptions(farm_ids: list[int] | None) -> list[dict]:
    """Cảnh báo thật (STEP 10) — khác _build_exceptions() (việc-thường-quy
    đang chờ, sẽ luôn tồn tại) ở chỗ đây là BẤT THƯỜNG/trễ hạn nghiêm
    trọng/rủi ro mất dữ liệu — thứ không nên tồn tại nếu vận hành trơn
    tru. Mỗi mục gate theo đúng 1 quyền xử lý vấn đề đó, khớp khuôn
    _build_exceptions() ở trên."""
    exceptions = []

    if current_user_can(perm.PLAN_REVENUE_DETAILS):
        r = list_stale_awaiting_revenue_locked()
        if r["total"]:
            exceptions.append(
                {
                    "icon": "💰",
                    "text": f"{r['total']} đơn đã bán quá lâu (≥14 ngày) chưa ghi nhận doanh thu",
                    "entries": [
                        {"label": o["order_code"], "url": url_for("plans.allocations_page", highlight=o["id"])}
                        for o in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.allocations_page"),
                }
            )

    if current_user_can(perm.PLAN_ALLOCATION_CREATE):
        r = list_idle_supply_locked(farm_ids=farm_ids)
        if r["total"]:
            exceptions.append(
                {
                    "icon": "🐖",
                    "text": f"{r['total']} kế hoạch đã xuất chuồng ứ đọng ≥7 ngày chưa đưa vào đơn hàng nào",
                    "entries": [
                        {
                            "label": f"{p['plan_code']} · {p['farm']} · còn {p['remaining_quantity']} con",
                            "url": url_for("plans.plans_page", highlight=p["id"]),
                        }
                        for p in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("plans.plans_page"),
                }
            )

    if current_user_can(perm.DELIVERY_CREATE):
        r = list_deliveries_missing_weight_locked(farm_ids=farm_ids)
        if r["total"]:
            exceptions.append(
                {
                    "icon": "⚖️",
                    "text": f"{r['total']} bản ghi xuất giao thiếu trọng lượng cân thực tế",
                    "entries": [
                        {
                            "label": f"{d['plan_code']} · {d['farm']} · {d['delivered_date']}",
                            "url": url_for("deliveries.xuat_giao_page", highlight=d["id"]),
                        }
                        for d in r["items"]
                    ],
                    "total": r["total"],
                    "more_url": url_for("deliveries.xuat_giao_page"),
                }
            )

    if current_user_can(perm.ADMIN_PERMISSIONS_MANAGE):
        extra_keys = list_unexpected_farm_permissions_locked()
        if extra_keys:
            exceptions.append(
                {
                    "icon": "🔓",
                    "text": f"Vai trò 'farm' đang có {len(extra_keys)} quyền vượt phạm vi mặc định",
                    "entries": [
                        {"label": perm.label(key), "url": url_for("admin.admin_permissions_page")}
                        for key in extra_keys
                    ],
                    "total": len(extra_keys),
                    "more_url": url_for("admin.admin_permissions_page"),
                }
            )

    return exceptions


@dashboard_bp.route("/")
def index():
    farm_ids = allowed_farm_ids(session["user"])
    exceptions = _build_exceptions(farm_ids)
    return render_template("dashboard.html", exceptions=exceptions)


@dashboard_bp.route("/canh-bao")
@permission_required(*_VIEW_EXCEPTION_PERMS)
def canh_bao():
    farm_ids = allowed_farm_ids(session["user"])
    exceptions = _build_true_exceptions(farm_ids)
    return render_template("canh_bao.html", exceptions=exceptions)


@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
def api_dashboard_summary():
    """5 KPI + biểu đồ xu hướng + biểu đồ cơ cấu cho trang Tổng quan — 1
    request duy nhất, không gate permission riêng (trang Tổng quan hiện
    không gate), chỉ lọc farm_ids như route "/" đang làm.

    Phase 3 (filter theo brief): thêm farm_id/customer_id/pig_type_id tuỳ
    chọn. farm_id chỉ thu hẹp trong PHẠM VI đã được phép (allowed_farm_ids)
    — không cho user chọn trại ngoài quyền của mình dù truyền query param
    thủ công."""
    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    farm_ids = allowed_farm_ids(session["user"])
    farm_id_raw = request.args.get("farm_id")
    if farm_id_raw:
        try:
            selected_farm_id = int(farm_id_raw)
        except ValueError:
            selected_farm_id = None
        if selected_farm_id is not None and (farm_ids is None or selected_farm_id in farm_ids):
            farm_ids = [selected_farm_id]
    customer_id = None
    if request.args.get("customer_id"):
        try:
            customer_id = int(request.args["customer_id"])
        except ValueError:
            customer_id = None
    pig_type_id = None
    if request.args.get("pig_type_id"):
        try:
            pig_type_id = int(request.args["pig_type_id"])
        except ValueError:
            pig_type_id = None
    return jsonify(
        {
            "kpi": dashboard_summary_locked(farm_ids=farm_ids, days=days, customer_id=customer_id, pig_type_id=pig_type_id),
            "daily": daily_reconciliation_series_locked(
                farm_ids=farm_ids, days=days, customer_id=customer_id, pig_type_id=pig_type_id
            ),
            "composition": pig_type_composition_locked(farm_ids=farm_ids, days=days, customer_id=customer_id),
        }
    )


@dashboard_bp.route("/quy-trinh")
def quy_trinh():
    return render_template("quy_trinh.html", steps=PROCESS_STEPS)
