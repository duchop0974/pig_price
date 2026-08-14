"""Blueprint đăng nhập/đăng xuất + guard yêu cầu đăng nhập cho toàn app."""
import functools
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from core.repositories import users_repo
from extensions import BOOTSTRAP_PASSWORD_FILE, DB_PATH, db_lock, log_access, log_audit

auth_bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {"auth.login", "static"}


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
    if request.endpoint in ("prices.index", "auth.login"):
        log_access("truy cập" if session.get("user") else "chưa đăng nhập")
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if not session.get("user"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Chưa đăng nhập."}), 401
        return redirect(url_for("auth.login", next=request.path))


@auth_bp.app_context_processor
def inject_current_user():
    return {"current_user": session.get("user")}


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = session.get("user")
        if not user or user.get("role") != "admin":
            if request.path.startswith("/api/") or request.path.startswith("/admin/"):
                return jsonify({"error": "Chỉ admin mới có quyền truy cập."}), 403
            return redirect(url_for("prices.index"))
        return view(*args, **kwargs)

    return wrapped


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
            log_audit("login")
            return redirect(request.args.get("next") or url_for("prices.index"))
        error = "Sai tên đăng nhập hoặc mật khẩu."
        log_access(f"đăng nhập SAI (tên đăng nhập: {username})")
    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    log_audit("logout")
    session.pop("user", None)
    return redirect(url_for("auth.login"))
