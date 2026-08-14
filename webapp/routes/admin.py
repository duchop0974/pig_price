"""Blueprint quản trị: tài khoản người dùng + nhật ký hoạt động (chỉ admin)."""
from flask import Blueprint, jsonify, render_template, request

from core.repositories import audit_repo, users_repo
from extensions import DB_PATH, db_lock, log_audit
from routes.auth import admin_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/users", methods=["GET"])
@admin_required
def admin_users_page():
    return render_template("admin_users.html", users=users_repo.list_users(DB_PATH))


@admin_bp.route("/api/admin/users", methods=["POST"])
@admin_required
def api_admin_users_create():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip() or username
    role = data.get("role") if data.get("role") in ("admin", "user") else "user"

    if not username or len(username) > 30:
        return jsonify({"error": "Tên đăng nhập không hợp lệ."}), 400
    if len(password) < 6:
        return jsonify({"error": "Mật khẩu cần tối thiểu 6 ký tự."}), 400
    if users_repo.get_user_by_username(username, DB_PATH):
        return jsonify({"error": "Tên đăng nhập đã tồn tại."}), 400

    with db_lock:
        users_repo.create_user(username, password, DB_PATH, display_name=display_name, role=role)
    log_audit("tạo tài khoản", detail=f"username={username}, role={role}")
    return jsonify(users_repo.list_users(DB_PATH)), 201


@admin_bp.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def api_admin_users_toggle(user_id: int):
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    with db_lock:
        users_repo.set_user_active(user_id, is_active, DB_PATH)
    log_audit("khoá/mở tài khoản" if not is_active else "mở tài khoản", detail=f"user_id={user_id}")
    return jsonify(users_repo.list_users(DB_PATH))


@admin_bp.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def api_admin_users_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 6:
        return jsonify({"error": "Mật khẩu cần tối thiểu 6 ký tự."}), 400
    with db_lock:
        users_repo.reset_password(user_id, password, DB_PATH)
    log_audit("đặt lại mật khẩu", detail=f"user_id={user_id}")
    return jsonify({"ok": True})


@admin_bp.route("/admin/audit", methods=["GET"])
@admin_required
def admin_audit_page():
    with db_lock:
        entries = audit_repo.list_audit_log(DB_PATH, limit=200)
    return render_template("admin_audit.html", entries=entries)
