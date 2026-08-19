"""Flask app factory: tạo app, đăng ký blueprint, cấu hình chung."""
import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, jsonify
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import limiter
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.deliveries import deliveries_bp
from routes.incidents import incidents_bp
from routes.plans import plans_bp
from routes.prices import prices_bp

# Giữ nguyên tên file y hệt webapp/password.txt (bootstrap_admin_if_needed) —
# sinh 1 lần, đọc lại các lần sau, để phiên đăng nhập không bị mất hết mỗi
# khi restart/deploy (trước đây secret_key random mỗi lần khởi động).
SECRET_KEY_FILE = Path(__file__).resolve().parent / "secret_key.txt"


def _load_or_create_secret_key() -> str:
    if SECRET_KEY_FILE.exists():
        key = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _load_or_create_secret_key()
    # Cloudflare Tunnel gửi IP thật của khách qua header X-Forwarded-For; nếu
    # không có ProxyFix thì request.remote_addr luôn chỉ thấy 127.0.0.1.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Mặc định False: app hiện vừa có người vào qua Cloudflare Tunnel (HTTPS)
    # vừa có người vào thẳng qua LAN nội bộ (HTTP) — ép Secure=True vô điều
    # kiện sẽ khiến nhóm truy cập LAN không đăng nhập được (cookie không gửi
    # qua kết nối không mã hoá). Khi nào xác nhận 100% truy cập qua Tunnel,
    # chỉ cần set biến môi trường SESSION_COOKIE_SECURE=1, không cần sửa code.
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE") == "1"

    CSRFProtect(app)
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(prices_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(incidents_bp)
    app.register_blueprint(deliveries_bp)

    @app.errorhandler(sqlite3.IntegrityError)
    def handle_data_frozen(e):
        # Trigger BEFORE UPDATE ... WHEN OLD.locked_at IS NOT NULL (sale_plans/
        # sale_allocations/sale_orders/weighing_records) RAISE(ABORT, 'DATA_
        # FROZEN: ...') khi sửa dữ liệu đã khoá vĩnh viễn — không route nào tự
        # bắt lỗi này (trước Data Freeze UX, chưa ai từng thực sự set
        # locked_at nên nhánh này chưa từng chạy) nên bay thẳng thành 500 thô.
        # Bắt tập trung ở đây, chỉ nuốt đúng lỗi DATA_FROZEN — mọi
        # IntegrityError khác (VD UNIQUE constraint) vẫn báo 500 như cũ.
        if str(e).startswith("DATA_FROZEN"):
            return jsonify({"error": "Dữ liệu đã khoá vĩnh viễn, không thể sửa."}), 400
        raise e

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # CSRFProtect() bảo vệ mọi route POST/PUT/PATCH/DELETE tự động — lỗi
        # mặc định trả trang HTML, đổi sang JSON cho khớp style lỗi còn lại
        # của API (JS frontend chỉ biết parse JSON).
        return jsonify({"error": "Phiên làm việc đã hết hạn, vui lòng tải lại trang."}), 400

    return app
