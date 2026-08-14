"""Flask app factory: tạo app, đăng ký blueprint, cấu hình chung."""
import secrets

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.plans import plans_bp
from routes.prices import prices_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    # Cloudflare Tunnel gửi IP thật của khách qua header X-Forwarded-For; nếu
    # không có ProxyFix thì request.remote_addr luôn chỉ thấy 127.0.0.1.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.register_blueprint(auth_bp)
    app.register_blueprint(prices_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(admin_bp)

    return app
