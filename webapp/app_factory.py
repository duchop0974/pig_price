"""Flask app factory: tạo app, đăng ký blueprint, cấu hình chung."""
import secrets
import sqlite3

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.deliveries import deliveries_bp
from routes.incidents import incidents_bp
from routes.plans import plans_bp
from routes.prices import prices_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    # Cloudflare Tunnel gửi IP thật của khách qua header X-Forwarded-For; nếu
    # không có ProxyFix thì request.remote_addr luôn chỉ thấy 127.0.0.1.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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

    return app
