"""Blueprint đăng nhập/đăng xuất + guard yêu cầu đăng nhập cho toàn app."""
import functools
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from core import audit_actions
from core.repositories import users_repo
from core.services import authorization_service
from extensions import BOOTSTRAP_PASSWORD_FILE, DB_PATH, db_lock, log_access, log_audit

auth_bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {"auth.login", "static"}

# So sánh role "farm" (scoping dữ liệu theo trại) giờ nằm trong
# core/services/authorization_service.py (FARM_ROLE) — allowed_farm_ids() ở
# dưới chỉ còn là wrapper mỏng gọi service đó, không tự so sánh role nữa.


def bootstrap_admin_if_needed() -> None:
    """Nếu chưa có tài khoản nào (lần đầu chạy sau khi nâng cấp từ mật khẩu
    dùng chung, hoặc cài đặt mới), tự tạo 1 tài khoản admin mặc định
    (username 'admin') với mật khẩu ngẫu nhiên, ghi vào webapp/password.txt."""
    if users_repo.count_users(DB_PATH) > 0:
        return
    password = secrets.token_urlsafe(6)
    users_repo.create_user("admin", password, DB_PATH, display_name="Admin", role="admin")
    BOOTSTRAP_PASSWORD_FILE.write_text(
        f"Tài khoản admin mặc định:\n  Tên đăng nhập: admin\n  Mật khẩu: {password}\n"
        "\nHãy đăng nhập rồi vào mục Quản lý tài khoản để đổi mật khẩu và tạo thêm tài khoản khác.\n",
        encoding="utf-8",
    )
    print("=" * 60)
    print("Đã tạo tài khoản admin mặc định:")
    print("  Tên đăng nhập: admin")
    print(f"  Mật khẩu: {password}")
    print(f"  (lưu tại {BOOTSTRAP_PASSWORD_FILE})")
    print("=" * 60)


@auth_bp.before_app_request
def require_login():
    if request.endpoint in ("dashboard.index", "auth.login"):
        log_access("truy cập" if session.get("user") else "chưa đăng nhập")
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if not session.get("user"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Chưa đăng nhập."}), 401
        return redirect(url_for("auth.login", next=request.path))


def current_user_permissions() -> set[str]:
    return authorization_service.effective_permissions(session.get("user"), DB_PATH)


def current_user_can(permission_key: str) -> bool:
    return permission_key in current_user_permissions()


@auth_bp.app_context_processor
def inject_current_user():
    return {
        "current_user": session.get("user"),
        "current_user_can": current_user_can,
        "current_user_permissions": sorted(current_user_permissions()),
    }


def permission_required(*permission_keys):
    """Decorator chặn route theo tập quyền được phép — quyền hiệu lực của
    role được tra từ bảng role_permissions (tuỳ biến qua /admin/permissions),
    thay cho danh sách role hardcode như trước (role_required cũ)."""

    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = session.get("user")
            allowed = authorization_service.has_any_permission(user, permission_keys, DB_PATH)
            if not allowed:
                if request.path.startswith("/api/") or request.path.startswith("/admin/"):
                    return jsonify({"error": "Bạn không có quyền thực hiện thao tác này."}), 403
                return redirect(url_for("dashboard.index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def allowed_farm_ids(user: dict) -> list[int] | None:
    """None = không giới hạn theo trại (sales/accounting/admin xem được mọi
    trại). list[int] = các trại được gán cho tài khoản vai trò 'farm' (có
    thể rỗng nếu admin chưa gán trại nào)."""
    return authorization_service.allowed_farm_ids(user, DB_PATH)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password", "")
        user = None
        if username and password:
            with db_lock:
                user = users_repo.verify_password(username, password, DB_PATH)
        if user:
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
            }
            log_access("đăng nhập thành công")
            log_audit(audit_actions.LOGIN)
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        error = "Sai tên đăng nhập hoặc mật khẩu."
        log_access(f"đăng nhập SAI (tên đăng nhập: {username})")
        # Ghi cả vào audit_log (không chỉ access.log) để admin xem được số lần
        # đăng nhập sai qua trang /admin/audit thay vì phải mở file text riêng
        # — kênh audit chính cần thấy được dấu hiệu dò mật khẩu (brute-force).
        log_audit(audit_actions.LOGIN_FAILED, detail=f"username={username}", entity_type="user", entity_id=username)
    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    log_audit(audit_actions.LOGOUT)
    session.pop("user", None)
    return redirect(url_for("auth.login"))
