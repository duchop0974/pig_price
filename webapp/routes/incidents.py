"""Blueprint ghi nhận heo Loại/Hủy (incident_reports, kind='culled'/
'cancelled') gắn với 1 dòng hàng, kèm ảnh bằng chứng (media_proof) — và
route serve ảnh có authorization (chưa route nào trong app làm việc này
trước đây)."""
from flask import Blueprint, jsonify, request, send_file, session

from core import audit_actions
from core import permissions as perm
from core.repositories.incident_repo import VALID_KINDS
from data_access import (
    create_incident_locked,
    delete_incident_locked,
    get_incident_locked,
    get_media_locked,
    get_order_locked,
    list_incidents_for_order_locked,
    list_media_for_entity_locked,
    save_media_upload_locked,
)
from extensions import MEDIA_ROOT, log_audit
from routes.auth import current_user_permissions, permission_required

incidents_bp = Blueprint("incidents", __name__)

# Xem đơn hàng ở đâu thì xem được incident/ảnh gắn với đơn đó ở đấy — dùng
# đúng tập quyền allocations.html đang dùng để quyết định hiện trang, không
# tạo quyền "xem" riêng.
_VIEW_ORDER_PERMS = (
    perm.PLAN_ALLOCATION_CREATE,
    perm.PLAN_ALLOCATION_MANAGE,
    perm.PLAN_SALE_DETAILS,
    perm.PLAN_REVENUE_DETAILS,
)
# Tương tự nhưng cho ảnh gắn với đối soát kế hoạch trại (media_proof
# entity_type='plan_reconciliation') — khớp _VIEW_PLAN_RECONCILE_PERMS ở
# routes/plans.py. Định nghĩa lại (không import từ plans.py) để tránh vòng
# import (plans.py đã import _validate_photo từ module này).
_VIEW_PLAN_RECONCILE_PERMS = (
    perm.PLAN_REVIEW,
    perm.PLAN_RECEIVE,
    perm.PLAN_EDIT,
    perm.PLAN_RECONCILE_CREATE,
)

_PHOTO_EXT_WHITELIST = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
_PHOTO_MIME_WHITELIST = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_PHOTO_MAX_BYTES = 8 * 1024 * 1024
_PHOTO_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # + "WEBP" ở byte 8-12, kiểm riêng bên dưới
}


def _validate_photo(file_storage) -> str | None:
    """Trả về thông báo lỗi (str) nếu ảnh không hợp lệ, None nếu hợp lệ.
    Kiểm tra đuôi file + MIME khai báo + magic bytes thực tế (bỏ qua HEIC —
    không có signature đơn giản để tự kiểm) + dung lượng — theo yêu cầu
    §27 brief: không tin hoàn toàn filename/mime type client gửi lên."""
    filename = file_storage.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in _PHOTO_EXT_WHITELIST:
        return f"Định dạng ảnh không được hỗ trợ: {filename}"
    mime = (file_storage.mimetype or "").lower()
    if mime not in _PHOTO_MIME_WHITELIST:
        return f"Kiểu file không hợp lệ: {filename}"

    head = file_storage.stream.read(16)
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > _PHOTO_MAX_BYTES:
        return f"Ảnh quá lớn (tối đa {_PHOTO_MAX_BYTES // (1024 * 1024)}MB): {filename}"
    if size == 0:
        return f"File rỗng: {filename}"

    signatures = _PHOTO_SIGNATURES.get(mime)
    if signatures:
        if not any(head.startswith(sig) for sig in signatures):
            return f"Nội dung file không khớp định dạng ảnh khai báo: {filename}"
        if mime == "image/webp" and head[8:12] != b"WEBP":
            return f"Nội dung file không khớp định dạng ảnh khai báo: {filename}"
    return None


@incidents_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>/incidents", methods=["POST"])
@permission_required(perm.INCIDENT_CREATE)
def api_incident_create(order_id: int, line_id: int):
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    line = next((l for l in order["lines"] if l["id"] == line_id), None)
    if line is None:
        return jsonify({"error": "Không tìm thấy dòng hàng."}), 404

    kind = (request.form.get("kind") or "").strip()
    if kind not in VALID_KINDS:
        return jsonify({"error": "Loại ghi nhận không hợp lệ (chỉ nhận Loại/Hủy)."}), 400
    description = (request.form.get("description") or "").strip()
    if not description:
        return jsonify({"error": "Vui lòng nhập lý do."}), 400
    try:
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return jsonify({"error": "Số lượng không hợp lệ."}), 400
    if quantity <= 0:
        return jsonify({"error": "Số lượng phải lớn hơn 0."}), 400
    if quantity > line["quantity"]:
        return jsonify({"error": f"Số lượng vượt quá số lượng dòng hàng ({line['quantity']} con)."}), 400

    photos = [f for f in request.files.getlist("photos") if f and f.filename]
    if not photos:
        return jsonify({"error": "Vui lòng đính kèm ít nhất 1 ảnh làm bằng chứng."}), 400
    for photo in photos:
        err = _validate_photo(photo)
        if err:
            return jsonify({"error": err}), 400

    username = session["user"]["username"]
    ip = request.remote_addr
    incident = create_incident_locked(line_id, kind, quantity, description, ip, username)

    media_list = []
    for photo in photos:
        saved = save_media_upload_locked(
            photo.read(),
            "incident",
            incident["id"],
            kind,
            username,
            ip,
            photo.filename,
            photo.mimetype,
        )
        media_list.append(saved)

    log_audit(
        audit_actions.INCIDENT_CREATE,
        entity_type="incident",
        entity_id=incident["id"],
        new_value={"allocation_id": line_id, "kind": kind, "quantity": quantity, "photos": len(media_list)},
    )
    incident["media"] = media_list
    return jsonify(incident), 201


@incidents_bp.route("/api/orders/<int:order_id>/incidents", methods=["GET"])
@permission_required(*_VIEW_ORDER_PERMS)
def api_incidents_list(order_id: int):
    order = get_order_locked(order_id)
    if order is None:
        return jsonify({"error": "Không tìm thấy đơn hàng."}), 404
    incidents = list_incidents_for_order_locked(order_id)
    for inc in incidents:
        inc["media"] = list_media_for_entity_locked("incident", inc["id"])
    return jsonify(incidents)


@incidents_bp.route("/api/incidents/<int:incident_id>", methods=["DELETE"])
@permission_required(perm.INCIDENT_DELETE)
def api_incident_delete(incident_id: int):
    incident = get_incident_locked(incident_id)
    if incident is None:
        return jsonify({"error": "Không tìm thấy bản ghi."}), 404
    delete_incident_locked(incident_id)
    log_audit(audit_actions.INCIDENT_DELETE, entity_type="incident", entity_id=incident_id, old_value=incident)
    return jsonify({"ok": True})


@incidents_bp.route("/media/<int:media_id>", methods=["GET"])
def serve_media(media_id: int):
    """Không dùng @permission_required trực tiếp — tập quyền hợp lệ phụ
    thuộc entity_type của chính bản ghi media (incident của đơn hàng vs
    đối soát kế hoạch trại), phải đọc DB trước mới biết chọn tập quyền nào."""
    if not session.get("user"):
        return jsonify({"error": "Bạn không có quyền thực hiện thao tác này."}), 403
    media = get_media_locked(media_id)
    if media is None:
        return jsonify({"error": "Không tìm thấy file."}), 404

    required_perms = _VIEW_PLAN_RECONCILE_PERMS if media["entity_type"] == "plan_reconciliation" else _VIEW_ORDER_PERMS
    if not (current_user_permissions() & set(required_perms)):
        return jsonify({"error": "Bạn không có quyền thực hiện thao tác này."}), 403

    path = (MEDIA_ROOT / media["file_path"]).resolve()
    if not path.is_relative_to(MEDIA_ROOT.resolve()) or not path.is_file():
        return jsonify({"error": "Không tìm thấy file."}), 404
    return send_file(path, mimetype=media["mime_type"] or "application/octet-stream")
