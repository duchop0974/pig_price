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
# Giữ lại 2 hằng số cũ (không còn được ghi mới) chỉ để label() đọc đúng các
# dòng audit_log lịch sử từ trước khi tách kế hoạch trại/kế hoạch bán.
PLAN_UPDATE_SALE_DETAILS = "plan.update_sale_details"
PLAN_UPDATE_REVENUE_DETAILS = "plan.update_revenue_details"

# Kế hoạch bán (Phòng bán hàng, BM02)
ALLOCATION_CREATE = "allocation.create"
ALLOCATION_UPDATE_STATUS = "allocation.update_status"
ALLOCATION_UPDATE_SALE_DETAILS = "allocation.update_sale_details"
ALLOCATION_UPDATE_REVENUE_DETAILS = "allocation.update_revenue_details"

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
    PLAN_UPDATE_SALE_DETAILS: "Cập nhật thông tin bán hàng (cũ)",
    PLAN_UPDATE_REVENUE_DETAILS: "Ghi nhận doanh thu & hoá đơn (cũ)",
    ALLOCATION_CREATE: "Tạo kế hoạch bán",
    ALLOCATION_UPDATE_STATUS: "Cập nhật kế hoạch bán",
    ALLOCATION_UPDATE_SALE_DETAILS: "Cập nhật thông tin bán hàng",
    ALLOCATION_UPDATE_REVENUE_DETAILS: "Ghi nhận doanh thu & hoá đơn",
    CUSTOMER_CREATE: "Tạo khách hàng",
    CUSTOMER_UPDATE: "Sửa khách hàng",
    CUSTOMER_ACTIVATE: "Mở khách hàng",
    CUSTOMER_DEACTIVATE: "Khoá khách hàng",
    CUSTOMER_DELETE: "Xóa khách hàng",
}


def label(action: str) -> str:
    """Nhãn tiếng Việt để hiển thị; action lạ (chưa khai báo) hiển thị nguyên văn."""
    return LABELS.get(action, action)
