"""Hằng số action cho audit_log — dùng thay cho gõ tay chuỗi tiếng Việt rải
rác ở nhiều route. Mục đích: tránh lỗi gõ/gán nhầm nhãn (từng xảy ra ở
routes/admin.py: nhánh khoá tài khoản bị gán nhãn "khoá/mở tài khoản"), và
cho phép đổi câu chữ hiển thị mà không phải sửa dữ liệu đã ghi trong DB
(giá trị lưu DB ổn định, nhãn hiển thị tra qua LABELS)."""

# Đăng nhập / đăng xuất
LOGIN = "login"
LOGIN_FAILED = "login_failed"
LOGOUT = "logout"

# Tài khoản người dùng
USER_CREATE = "user.create"
USER_ACTIVATE = "user.activate"
USER_DEACTIVATE = "user.deactivate"
USER_RESET_PASSWORD = "user.reset_password"
USER_UPDATE_ROLE = "user.update_role"
USER_ASSIGN_FARMS = "user.assign_farms"
USER_DELETE = "user.delete"

# Vai trò & phân quyền tuỳ biến
ROLE_CREATE = "role.create"
ROLE_DELETE = "role.delete"
ROLE_UPDATE_PERMISSIONS = "role.update_permissions"

# Trang trại / khu
FARM_CREATE = "farm.create"
FARM_UPDATE = "farm.update"
FARM_DELETE = "farm.delete"
ZONE_CREATE = "zone.create"
ZONE_UPDATE = "zone.update"
ZONE_DELETE = "zone.delete"

# Danh mục loại heo bán
PIG_TYPE_CREATE = "pig_type.create"
PIG_TYPE_UPDATE = "pig_type.update"
PIG_TYPE_ACTIVATE = "pig_type.activate"
PIG_TYPE_DEACTIVATE = "pig_type.deactivate"
PIG_TYPE_DELETE = "pig_type.delete"

# Kế hoạch trại (nguồn cung, BM01)
PLAN_CREATE = "plan.create"
PLAN_UPDATE_STATUS = "plan.update_status"
PLAN_APPROVE = "plan.approve"
PLAN_REJECT = "plan.reject"
PLAN_UPDATE_RECEIVED = "plan.update_received"
PLAN_UPDATE_EDIT = "plan.update_edit"
PLAN_DELETE = "plan.delete"
PLAN_RECONCILE_CREATE = "plan.reconcile_create"
PLAN_RECONCILE_DELETE = "plan.reconcile_delete"
# Giữ lại 2 hằng số cũ (không còn được ghi mới) chỉ để label() đọc đúng các
# dòng audit_log lịch sử từ trước khi tách kế hoạch trại/kế hoạch bán.
PLAN_UPDATE_SALE_DETAILS = "plan.update_sale_details"
PLAN_UPDATE_REVENUE_DETAILS = "plan.update_revenue_details"

# Kế hoạch bán (Phòng bán hàng, BM02) — hằng số cũ (không còn ghi mới từ
# Giai đoạn 8), giữ lại chỉ để label() đọc đúng lịch sử audit_log trước khi
# tách đơn hàng/dòng hàng.
ALLOCATION_CREATE = "allocation.create"
ALLOCATION_UPDATE_STATUS = "allocation.update_status"
ALLOCATION_UPDATE_SALE_DETAILS = "allocation.update_sale_details"
ALLOCATION_UPDATE_REVENUE_DETAILS = "allocation.update_revenue_details"

# Đơn hàng (Giai đoạn 8) — 1 đơn có thể gồm nhiều dòng hàng (khác loại
# heo/kế hoạch trại), thay cho khái niệm "kế hoạch bán" phẳng cũ ở trên.
ORDER_CREATE = "order.create"
ORDER_LINE_ADD = "order.line_add"
ORDER_LINE_REMOVE = "order.line_remove"
ORDER_UPDATE_STATUS = "order.update_status"
ORDER_MARK_DONE = "order.mark_done"
ORDER_UPDATE_SALE_DETAILS = "order.update_sale_details"
ORDER_UPDATE_REVENUE_DETAILS = "order.update_revenue_details"
ORDER_LINE_EDIT = "order.line_edit"
ORDER_DELETE = "order.delete"
ORDER_LOCK = "order.lock"

# Heo loại/hủy (đối chiếu số lượng bán, kèm ảnh bằng chứng)
INCIDENT_CREATE = "incident.create"
INCIDENT_DELETE = "incident.delete"

# Xuất giao thực tế (sale_deliveries) — loại heo/số lượng/trọng lượng/ngày
# xuất THẬT, có thể lệch kế hoạch mà không sửa số kế hoạch gốc.
DELIVERY_CREATE = "delivery.create"
DELIVERY_DELETE = "delivery.delete"

# Khách hàng
CUSTOMER_CREATE = "customer.create"
CUSTOMER_UPDATE = "customer.update"
CUSTOMER_ACTIVATE = "customer.activate"
CUSTOMER_DEACTIVATE = "customer.deactivate"
CUSTOMER_DELETE = "customer.delete"

LABELS = {
    LOGIN: "Đăng nhập",
    LOGIN_FAILED: "Đăng nhập thất bại",
    LOGOUT: "Đăng xuất",
    USER_CREATE: "Tạo tài khoản",
    USER_ACTIVATE: "Mở tài khoản",
    USER_DEACTIVATE: "Khoá tài khoản",
    USER_RESET_PASSWORD: "Đặt lại mật khẩu",
    USER_UPDATE_ROLE: "Đổi vai trò tài khoản",
    USER_ASSIGN_FARMS: "Gán trang trại cho tài khoản",
    USER_DELETE: "Xoá tài khoản",
    ROLE_CREATE: "Tạo vai trò",
    ROLE_DELETE: "Xóa vai trò",
    ROLE_UPDATE_PERMISSIONS: "Cập nhật quyền của vai trò",
    FARM_CREATE: "Tạo trang trại",
    FARM_UPDATE: "Sửa trang trại",
    FARM_DELETE: "Xóa trang trại",
    ZONE_CREATE: "Tạo khu",
    ZONE_UPDATE: "Sửa khu",
    ZONE_DELETE: "Xóa khu",
    PIG_TYPE_CREATE: "Thêm danh mục loại heo",
    PIG_TYPE_UPDATE: "Sửa danh mục loại heo",
    PIG_TYPE_ACTIVATE: "Mở danh mục loại heo",
    PIG_TYPE_DEACTIVATE: "Khoá danh mục loại heo",
    PIG_TYPE_DELETE: "Xóa danh mục loại heo",
    PLAN_CREATE: "Tạo kế hoạch trại",
    PLAN_UPDATE_STATUS: "Cập nhật kế hoạch trại",
    PLAN_APPROVE: "Duyệt kế hoạch trại",
    PLAN_REJECT: "Từ chối kế hoạch trại",
    PLAN_UPDATE_RECEIVED: "Ghi nhận số lượng thực nhận",
    PLAN_UPDATE_EDIT: "Sửa nội dung kế hoạch trại",
    PLAN_DELETE: "Xoá vĩnh viễn kế hoạch trại",
    PLAN_RECONCILE_CREATE: "Xử lý chênh lệch kế hoạch trại",
    PLAN_RECONCILE_DELETE: "Xoá bản ghi đối soát kế hoạch trại",
    PLAN_UPDATE_SALE_DETAILS: "Cập nhật thông tin bán hàng (cũ)",
    PLAN_UPDATE_REVENUE_DETAILS: "Ghi nhận doanh thu & hoá đơn (cũ)",
    ALLOCATION_CREATE: "Tạo kế hoạch bán (cũ)",
    ALLOCATION_UPDATE_STATUS: "Cập nhật kế hoạch bán (cũ)",
    ALLOCATION_UPDATE_SALE_DETAILS: "Cập nhật thông tin bán hàng (cũ)",
    ALLOCATION_UPDATE_REVENUE_DETAILS: "Ghi nhận doanh thu & hoá đơn (cũ)",
    ORDER_CREATE: "Tạo đơn hàng",
    ORDER_LINE_ADD: "Thêm dòng vào đơn hàng",
    ORDER_LINE_REMOVE: "Xoá dòng khỏi đơn hàng",
    ORDER_UPDATE_STATUS: "Cập nhật đơn hàng",
    ORDER_MARK_DONE: "Đánh dấu đơn hàng Đã bán",
    ORDER_UPDATE_SALE_DETAILS: "Cập nhật thông tin bán hàng",
    ORDER_UPDATE_REVENUE_DETAILS: "Ghi nhận doanh thu & hoá đơn",
    ORDER_LINE_EDIT: "Sửa dòng hàng",
    ORDER_DELETE: "Xoá vĩnh viễn đơn hàng",
    ORDER_LOCK: "Khoá vĩnh viễn đơn hàng",
    INCIDENT_CREATE: "Ghi nhận heo loại/hủy",
    INCIDENT_DELETE: "Xoá bản ghi heo loại/hủy",
    DELIVERY_CREATE: "Ghi nhận xuất giao thực tế",
    DELIVERY_DELETE: "Xoá bản ghi xuất giao thực tế",
    CUSTOMER_CREATE: "Tạo khách hàng",
    CUSTOMER_UPDATE: "Sửa khách hàng",
    CUSTOMER_ACTIVATE: "Mở khách hàng",
    CUSTOMER_DEACTIVATE: "Khoá khách hàng",
    CUSTOMER_DELETE: "Xóa khách hàng",
}


def label(action: str) -> str:
    """Nhãn tiếng Việt để hiển thị; action lạ (chưa khai báo) hiển thị nguyên văn."""
    return LABELS.get(action, action)


# Icon theo tiền tố entity của action string (VD "plan.create" → "plan") —
# dùng cho Audit Timeline (webapp/templates/admin_audit.html). Dựa vào quy
# ước đặt tên "<entity>.<verb>" đã nhất quán sẵn trong file này, không cần
# liệt kê icon riêng cho từng action.
_ICONS = {
    "login": "🔑",
    "logout": "🚪",
    "login_failed": "⚠️",
    "user": "👤",
    "role": "🎭",
    "farm": "🏠",
    "zone": "🏠",
    "pig_type": "🐷",
    "plan": "📋",
    "allocation": "📋",
    "order": "📦",
    "incident": "🐖",
    "delivery": "🚚",
    "customer": "🧑‍🤝‍🧑",
}


def icon_for(action: str) -> str:
    """Icon hiển thị cho 1 dòng audit; action lạ trả về icon mặc định."""
    if action in _ICONS:
        return _ICONS[action]
    prefix = action.split(".", 1)[0]
    return _ICONS.get(prefix, "📝")


def is_danger(action: str) -> bool:
    """Action mang tính phá huỷ/từ chối/thất bại — tô màu cảnh báo trên timeline."""
    return action.endswith((".delete", ".reject")) or action == "login_failed"
