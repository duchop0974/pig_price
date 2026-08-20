"""Blueprint hộp thư Thông báo (Phase 5, brief nghiệp vụ) — bản ghi PERSIST
riêng của từng user, khác Cần xử lý/Cảnh báo (tính động, không lưu). Không
gate permission riêng — ai đăng nhập cũng xem được thông báo CỦA CHÍNH
MÌNH (đã lọc theo recipient_username ở tầng repo)."""
from flask import Blueprint, jsonify, render_template, session

from data_access import (
    count_unread_notifications_locked,
    list_notifications_for_user_locked,
    mark_all_notifications_read_locked,
    mark_notification_read_locked,
)

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/thong-bao")
def thong_bao_page():
    return render_template("thong_bao.html")


@notifications_bp.route("/api/notifications", methods=["GET"])
def api_notifications_list():
    username = session["user"]["username"]
    return jsonify(list_notifications_for_user_locked(username))


@notifications_bp.route("/api/notifications/unread-count", methods=["GET"])
def api_notifications_unread_count():
    username = session["user"]["username"]
    return jsonify({"count": count_unread_notifications_locked(username)})


@notifications_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def api_notifications_mark_read(notification_id: int):
    username = session["user"]["username"]
    ok = mark_notification_read_locked(notification_id, username)
    if not ok:
        return jsonify({"error": "Không tìm thấy thông báo."}), 404
    return jsonify({"ok": True})


@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
def api_notifications_mark_all_read():
    username = session["user"]["username"]
    mark_all_notifications_read_locked(username)
    return jsonify({"ok": True})
