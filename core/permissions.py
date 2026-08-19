"""Danh mục quyền (permission key) dùng cho hệ thống phân quyền tuỳ biến theo
role — thay cho việc hardcode tập role được phép ngay tại từng route
(role_required(...) cũ). Danh mục này CHỈ đổi khi dev thêm/bớt một điểm chặn
mới trong code; việc role nào có quyền nào là dữ liệu (bảng role_permissions),
không nằm ở đây."""

# Kế hoạch xuất bán
PLAN_CREATE = "plans.create"
PLAN_EDIT = "plans.edit"  # sửa nội dung kế hoạch trại khi nhập nhầm — mặc định chỉ admin có
PLAN_REVIEW = "plans.review"  # duyệt / từ chối / cập nhật trạng thái kế hoạch trại
PLAN_RECEIVE = "plans.receive"  # trại ghi nhận số lượng thực nhận/xuất chuồng
PLAN_ALLOCATION_CREATE = "plans.allocation_create"  # tạo kế hoạch bán (nhặt từ kế hoạch trại)
PLAN_ALLOCATION_MANAGE = "plans.allocation_manage"  # done / cancelled / disabled kế hoạch bán
PLAN_SALE_DETAILS = "plans.sale_details"  # cập nhật thông tin bán hàng (trên kế hoạch bán)
PLAN_REVENUE_DETAILS = "plans.revenue_details"  # ghi nhận doanh thu & hoá đơn (trên kế hoạch bán)
PLAN_DELETE = "plans.delete"  # xoá vĩnh viễn kế hoạch trại — mặc định chỉ admin có
ORDER_DELETE = "plans.order_delete"  # xoá vĩnh viễn đơn hàng — mặc định chỉ admin có
ORDER_EDIT_LINE = "plans.order_edit_line"  # sửa số lượng/giá 1 dòng hàng bất kể trạng thái đơn — mặc định chỉ admin có
INCIDENT_CREATE = "incident.create"  # ghi nhận heo loại/hủy (kèm ảnh) trên 1 dòng hàng
INCIDENT_DELETE = "incident.delete"  # xoá bản ghi heo loại/hủy — mặc định chỉ admin có
ORDER_LOCK = "plans.order_lock"  # khoá vĩnh viễn đơn hàng (Data Freeze) — mặc định chỉ admin có
PLAN_RECONCILE_CREATE = "plans.reconcile_create"  # ghi nhận xử lý chênh lệch kế hoạch trại (còn tại trại/loại/hủy/chuyển/khác)
PLAN_RECONCILE_DELETE = "plans.reconcile_delete"  # xoá bản ghi đối soát kế hoạch trại — mặc định chỉ admin có
DELIVERY_CREATE = "plans.delivery_create"  # ghi nhận lần xuất giao thực tế (loại heo/số lượng/kg/ngày)
DELIVERY_DELETE = "plans.delivery_delete"  # xoá bản ghi xuất giao — mặc định chỉ admin có

# Khách hàng
CUSTOMER_VIEW = "customers.view"
CUSTOMER_MANAGE = "customers.manage"

# Danh mục trang trại / khu
ADMIN_FARMS_VIEW = "admin.farms.view"
ADMIN_FARMS_MANAGE = "admin.farms.manage"

# Danh mục loại heo bán
ADMIN_PIG_TYPES_VIEW = "admin.pig_types.view"
ADMIN_PIG_TYPES_MANAGE = "admin.pig_types.manage"

# Quản trị hệ thống
ADMIN_USERS_MANAGE = "admin.users.manage"
ADMIN_AUDIT_VIEW = "admin.audit.view"
ADMIN_PERMISSIONS_MANAGE = "admin.permissions.manage"

# (key, nhãn tiếng Việt, nhóm hiển thị) — thứ tự này dùng để render ma trận
# quyền trên trang /admin/permissions, nhóm theo nhóm để dễ quét mắt.
PERMISSIONS = [
    (PLAN_CREATE, "Tạo kế hoạch trại (đăng ký nguồn cung)", "Kế hoạch xuất bán"),
    (PLAN_EDIT, "Sửa nội dung kế hoạch trại (khi nhập nhầm)", "Kế hoạch xuất bán"),
    (PLAN_REVIEW, "Duyệt / từ chối / cập nhật trạng thái kế hoạch trại", "Kế hoạch xuất bán"),
    (PLAN_RECEIVE, "Ghi nhận số lượng thực nhận/xuất chuồng", "Kế hoạch xuất bán"),
    (PLAN_ALLOCATION_CREATE, "Tạo kế hoạch bán (nhặt từ kế hoạch trại)", "Kế hoạch xuất bán"),
    (PLAN_ALLOCATION_MANAGE, "Đánh dấu Đã bán / huỷ / vô hiệu hoá kế hoạch bán", "Kế hoạch xuất bán"),
    (PLAN_SALE_DETAILS, "Cập nhật thông tin bán hàng (kế hoạch bán)", "Kế hoạch xuất bán"),
    (PLAN_REVENUE_DETAILS, "Ghi nhận doanh thu & hoá đơn (kế hoạch bán)", "Kế hoạch xuất bán"),
    (PLAN_DELETE, "Xoá vĩnh viễn kế hoạch trại", "Kế hoạch xuất bán"),
    (ORDER_DELETE, "Xoá vĩnh viễn đơn hàng", "Kế hoạch xuất bán"),
    (ORDER_EDIT_LINE, "Sửa số lượng/giá dòng hàng bất kể trạng thái đơn", "Kế hoạch xuất bán"),
    (INCIDENT_CREATE, "Ghi nhận heo loại/hủy (kèm ảnh) trên dòng hàng", "Kế hoạch xuất bán"),
    (INCIDENT_DELETE, "Xoá bản ghi heo loại/hủy", "Kế hoạch xuất bán"),
    (ORDER_LOCK, "Khoá vĩnh viễn đơn hàng (Data Freeze)", "Kế hoạch xuất bán"),
    (PLAN_RECONCILE_CREATE, "Xử lý chênh lệch kế hoạch trại (còn tại trại/loại/hủy/chuyển/khác)", "Kế hoạch xuất bán"),
    (PLAN_RECONCILE_DELETE, "Xoá bản ghi đối soát kế hoạch trại", "Kế hoạch xuất bán"),
    (DELIVERY_CREATE, "Ghi nhận xuất giao thực tế (loại heo/số lượng/kg/ngày)", "Kế hoạch xuất bán"),
    (DELIVERY_DELETE, "Xoá bản ghi xuất giao thực tế", "Kế hoạch xuất bán"),
    (CUSTOMER_VIEW, "Xem danh sách khách hàng", "Khách hàng"),
    (CUSTOMER_MANAGE, "Thêm / sửa / khoá / xoá khách hàng", "Khách hàng"),
    (ADMIN_FARMS_VIEW, "Xem danh mục trang trại / khu", "Danh mục"),
    (ADMIN_FARMS_MANAGE, "Thêm / sửa / xoá trang trại / khu", "Danh mục"),
    (ADMIN_PIG_TYPES_VIEW, "Xem danh mục loại heo bán", "Danh mục"),
    (ADMIN_PIG_TYPES_MANAGE, "Thêm / sửa / khoá / xoá danh mục loại heo", "Danh mục"),
    (ADMIN_USERS_MANAGE, "Quản lý tài khoản người dùng", "Quản trị"),
    (ADMIN_AUDIT_VIEW, "Xem nhật ký hoạt động", "Quản trị"),
    (ADMIN_PERMISSIONS_MANAGE, "Quản lý vai trò & phân quyền", "Quản trị"),
]

ALL_PERMISSION_KEYS = tuple(key for key, _label, _group in PERMISSIONS)

LABELS = {key: label for key, label, _group in PERMISSIONS}


def label(key: str) -> str:
    """Nhãn tiếng Việt để hiển thị; key lạ (chưa khai báo) hiển thị nguyên văn."""
    return LABELS.get(key, key)
