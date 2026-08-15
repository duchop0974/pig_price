"""Blueprint trang chủ (Tổng quan) + trang Quy trình xuất bán (sơ đồ)."""
from flask import Blueprint, render_template, session

from core import permissions as perm
from data_access import dashboard_stats_locked
from routes.auth import allowed_farm_ids

dashboard_bp = Blueprint("dashboard", __name__)

# Các bước của quy trình xuất bán, theo đúng thứ tự nghiệp vụ thực tế —
# mỗi bước gắn với 1 permission key (gate hiển thị) và 1 endpoint trang đích.
# Bước 2-5 đều nằm trên cùng trang /ke-hoach (chưa có deep-link riêng theo
# trạng thái trong plans.html), chỉ khác nhau về mặt trực quan trên sơ đồ.
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
        "endpoint": "plans.plans_page",
    },
    {
        "title": "5. Chốt thông tin bán hàng",
        "desc": "Gán khách hàng, giá thoả thuận, thời gian & hình thức giao cho kế hoạch bán.",
        "icon": "🤝",
        "permission": perm.PLAN_SALE_DETAILS,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "6. Đánh dấu Đã bán",
        "desc": "Ghi nhận giá và số lượng bán thực tế khi hoàn tất xuất bán.",
        "icon": "🚚",
        "permission": perm.PLAN_ALLOCATION_MANAGE,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "7. Ghi nhận doanh thu & hoá đơn",
        "desc": "Kế toán ghi nhận số tiền đã thu, chứng từ cân, số hoá đơn.",
        "icon": "💰",
        "permission": perm.PLAN_REVENUE_DETAILS,
        "endpoint": "plans.plans_page",
    },
    {
        "title": "8. Quản lý khách hàng",
        "desc": "Danh sách khách hàng dùng để gán vào bước Chốt thông tin bán hàng.",
        "icon": "👥",
        "permission": perm.CUSTOMER_VIEW,
        "endpoint": "plans.customers_page",
    },
]


@dashboard_bp.route("/")
def index():
    farm_ids = allowed_farm_ids(session["user"])
    stats = dashboard_stats_locked(farm_ids=farm_ids)
    # Định dạng kiểu Việt Nam (dấu chấm ngăn cách hàng nghìn), khớp fmtPrice()
    # trong common.js dùng toLocaleString("vi-VN") ở các trang khác.
    stats["revenue_this_month_fmt"] = f"{stats['revenue_this_month']:,}".replace(",", ".")
    return render_template("dashboard.html", stats=stats)


@dashboard_bp.route("/quy-trinh")
def quy_trinh():
    return render_template("quy_trinh.html", steps=PROCESS_STEPS)
