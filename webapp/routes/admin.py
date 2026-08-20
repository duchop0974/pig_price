"""Blueprint quản trị: tài khoản người dùng, danh mục (trang trại/khu, loại
heo bán) + nhật ký hoạt động (chỉ admin)."""
import json

from flask import Blueprint, jsonify, render_template, request, session

from core import audit_actions
from core import permissions as perm
from core.repositories import audit_repo, users_repo
from core.services import farm_service, pig_type_service, role_service, user_service
from data_access import (
    count_plans_for_farm_locked,
    count_deliveries_for_pig_type_locked,
    count_plans_for_pig_type_locked,
    count_plans_for_zone_locked,
    count_users_with_role_locked,
    get_farm_locked,
    get_pig_type_locked,
    get_role_locked,
    get_zone_locked,
    list_farms_for_user_locked,
    list_farms_locked,
    list_permissions_for_role_locked,
    list_pig_types_locked,
    list_roles_locked,
    list_zones_locked,
)
from extensions import DB_PATH, db_lock
from routes.auth import permission_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/users", methods=["GET"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def admin_users_page():
    return render_template(
        "admin_users.html", users=users_repo.list_users(DB_PATH), farms=list_farms_locked(), roles=list_roles_locked()
    )


@admin_bp.route("/api/admin/users", methods=["POST"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_create():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip() or username
    # Fallback im lặng về "sales" khi role không hợp lệ/thiếu — khác hẳn
    # validate-raise nên giữ ở route, không đưa vào service (xem docstring
    # user_service.py).
    valid_role_keys = {r["key"] for r in list_roles_locked()}
    role = data.get("role") if data.get("role") in valid_role_keys else "sales"

    try:
        user_service.create_user(
            username,
            password,
            display_name,
            role,
            DB_PATH,
            ip=request.remote_addr,
            actor_username=session["user"]["username"],
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(users_repo.list_users(DB_PATH)), 201


@admin_bp.route("/api/admin/users/<int:user_id>/role", methods=["PATCH"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_update_role(user_id: int):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    users = users_repo.list_users(DB_PATH)
    old_user = next((u for u in users if u["id"] == user_id), None)
    if old_user is None:
        return jsonify({"error": "Không tìm thấy tài khoản."}), 404
    try:
        user_service.update_role(
            user_id, role, old_user["role"], DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(users_repo.list_users(DB_PATH))


@admin_bp.route("/api/admin/users/<int:user_id>/farms", methods=["GET"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_farms_get(user_id: int):
    return jsonify(list_farms_for_user_locked(user_id))


@admin_bp.route("/api/admin/users/<int:user_id>/farms", methods=["PATCH"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_farms_update(user_id: int):
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("farm_ids")
    old_ids = [f["id"] for f in list_farms_for_user_locked(user_id)]
    try:
        user_service.assign_farms(
            user_id, raw_ids, old_ids, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_farms_for_user_locked(user_id))


@admin_bp.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_toggle(user_id: int):
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    user_service.set_active(
        user_id, is_active, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(users_repo.list_users(DB_PATH))


@admin_bp.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    try:
        user_service.reset_password(
            user_id, password, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_delete(user_id: int):
    users = users_repo.list_users(DB_PATH)
    old_user = next((u for u in users if u["id"] == user_id), None)
    if old_user is None:
        return jsonify({"error": "Không tìm thấy tài khoản."}), 404
    if user_id == session["user"]["id"]:
        return jsonify({"error": "Không thể xoá chính tài khoản đang đăng nhập."}), 400
    if old_user["role"] == "admin" and old_user["is_active"]:
        other_active_admins = [
            u for u in users if u["id"] != user_id and u["role"] == "admin" and u["is_active"]
        ]
        if not other_active_admins:
            return jsonify({"error": "Không thể xoá: đây là tài khoản admin đang hoạt động cuối cùng."}), 400
    user_service.delete_user(
        user_id, old_user, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(users_repo.list_users(DB_PATH))


@admin_bp.route("/admin/audit", methods=["GET"])
@permission_required(perm.ADMIN_AUDIT_VIEW)
def admin_audit_page():
    filters = dict(
        username=(request.args.get("username") or "").strip() or None,
        action=(request.args.get("action") or "").strip() or None,
        entity_type=(request.args.get("entity_type") or "").strip() or None,
        entity_id=(request.args.get("entity_id") or "").strip() or None,
        date_from=(request.args.get("date_from") or "").strip() or None,
        date_to=(request.args.get("date_to") or "").strip() or None,
    )
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    page_size = 50
    with db_lock:
        total = audit_repo.count_audit_log(DB_PATH, **filters)
        entries = audit_repo.list_audit_log(
            DB_PATH, limit=page_size, offset=(page - 1) * page_size, **filters
        )
    for e in entries:
        e["old_value"] = json.loads(e["old_value"]) if e["old_value"] else None
        e["new_value"] = json.loads(e["new_value"]) if e["new_value"] else None
    return render_template(
        "admin_audit.html",
        entries=entries,
        filters=filters,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, -(-total // page_size)),
        action_label=audit_actions.label,
        action_icon=audit_actions.icon_for,
        is_danger_action=audit_actions.is_danger,
        all_actions=sorted(audit_actions.LABELS.items(), key=lambda kv: kv[1]),
    )


# ---------------------------------------------------------------------------
# Danh mục trang trại / khu — chỉ admin được tạo/sửa/xóa. Xóa bị chặn nếu còn
# kế hoạch xuất bán nào đang tham chiếu, để không phá vỡ lịch sử đối soát.
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/farms", methods=["GET"])
@permission_required(perm.ADMIN_FARMS_VIEW)
def admin_farms_page():
    return render_template("admin_farms.html", farms=list_farms_locked())


@admin_bp.route("/api/admin/farms", methods=["POST"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_farms_create():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    province = (data.get("province") or "").strip() or None
    try:
        farm_service.create_farm(
            code, province, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_farms_locked()), 201


@admin_bp.route("/api/admin/farms/<int:farm_id>", methods=["PATCH"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_farms_update(farm_id: int):
    old_farm = get_farm_locked(farm_id)
    if old_farm is None:
        return jsonify({"error": "Không tìm thấy trang trại."}), 404
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    province = (data.get("province") or "").strip() or None
    try:
        farm_service.update_farm(
            farm_id, code, province, old_farm, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_farms_locked())


@admin_bp.route("/api/admin/farms/<int:farm_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_farms_delete(farm_id: int):
    old_farm = get_farm_locked(farm_id)
    if old_farm is None:
        return jsonify({"error": "Không tìm thấy trang trại."}), 404
    if count_plans_for_farm_locked(farm_id) > 0:
        return jsonify({"error": "Không thể xóa: trang trại đang được dùng trong kế hoạch xuất bán."}), 400
    farm_service.delete_farm(farm_id, old_farm, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    return jsonify(list_farms_locked())


@admin_bp.route("/api/admin/zones", methods=["POST"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_zones_create():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    try:
        farm_id = int(data.get("farm_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Thiếu trang trại."}), 400
    if get_farm_locked(farm_id) is None:
        return jsonify({"error": "Không tìm thấy trang trại."}), 404
    try:
        farm_service.create_zone(farm_id, code, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_zones_locked(farm_id)), 201


@admin_bp.route("/api/admin/zones/<int:zone_id>", methods=["PATCH"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_zones_update(zone_id: int):
    zone = get_zone_locked(zone_id)
    if zone is None:
        return jsonify({"error": "Không tìm thấy khu."}), 404
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    try:
        farm_service.update_zone(zone_id, code, zone, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_zones_locked(zone["farm_id"]))


@admin_bp.route("/api/admin/zones/<int:zone_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_zones_delete(zone_id: int):
    zone = get_zone_locked(zone_id)
    if zone is None:
        return jsonify({"error": "Không tìm thấy khu."}), 404
    if count_plans_for_zone_locked(zone_id) > 0:
        return jsonify({"error": "Không thể xóa: khu đang được dùng trong kế hoạch xuất bán."}), 400
    farm_service.delete_zone(zone_id, zone, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    return jsonify(list_zones_locked(zone["farm_id"]))


# ---------------------------------------------------------------------------
# Danh mục loại heo bán — chỉ admin được tạo/sửa/xóa/khoá. Xóa bị chặn nếu
# còn kế hoạch xuất bán nào đang tham chiếu; khoá (is_active=0) dùng khi
# muốn ẩn khỏi form tạo kế hoạch mới nhưng vẫn giữ cho lịch sử cũ.
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/pig-types", methods=["GET"])
@permission_required(perm.ADMIN_PIG_TYPES_VIEW)
def admin_pig_types_page():
    return render_template("admin_pig_types.html", pig_types=list_pig_types_locked())


@admin_bp.route("/api/admin/pig-types", methods=["POST"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_create():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    try:
        pig_type_service.create_pig_type(
            code, name, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_pig_types_locked()), 201


@admin_bp.route("/api/admin/pig-types/<int:pig_type_id>", methods=["PATCH"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_update(pig_type_id: int):
    old_pig_type = get_pig_type_locked(pig_type_id)
    if old_pig_type is None:
        return jsonify({"error": "Không tìm thấy loại heo."}), 404
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    try:
        pig_type_service.update_pig_type(
            pig_type_id, code, name, old_pig_type, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(list_pig_types_locked())


@admin_bp.route("/api/admin/pig-types/<int:pig_type_id>/toggle", methods=["POST"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_toggle(pig_type_id: int):
    if get_pig_type_locked(pig_type_id) is None:
        return jsonify({"error": "Không tìm thấy loại heo."}), 404
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    pig_type_service.set_active(
        pig_type_id, is_active, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(list_pig_types_locked())


@admin_bp.route("/api/admin/pig-types/<int:pig_type_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_delete(pig_type_id: int):
    old_pig_type = get_pig_type_locked(pig_type_id)
    if old_pig_type is None:
        return jsonify({"error": "Không tìm thấy loại heo."}), 404
    # Phải kiểm CẢ sale_deliveries: cả tính năng xuất giao thực tế sinh ra để
    # ghi nhận loại heo giao KHÁC kế hoạch, nên 1 loại chỉ xuất hiện ở delivery
    # sẽ có count_plans_for_pig_type = 0 nhưng vẫn đang được dùng thật. Xoá nó
    # sẽ mất luôn câu trả lời "lệch sang loại gì" (PRAGMA foreign_keys không
    # bật nên DB không tự chặn).
    if count_plans_for_pig_type_locked(pig_type_id) > 0 or count_deliveries_for_pig_type_locked(pig_type_id) > 0:
        return jsonify(
            {"error": "Không thể xóa: loại heo đang được dùng trong kế hoạch xuất bán hoặc bản ghi xuất giao."}
        ), 400
    pig_type_service.delete_pig_type(
        pig_type_id, old_pig_type, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
    )
    return jsonify(list_pig_types_locked())


# ---------------------------------------------------------------------------
# Vai trò & phân quyền tuỳ biến — role 'admin' luôn full quyền (hardcode ở
# roles_repo.effective_permissions), không sửa/xoá được qua đây.
# ---------------------------------------------------------------------------


def _role_permissions_matrix() -> list[dict]:
    roles = list_roles_locked()
    return [
        {
            **role,
            "permission_keys": (
                list(perm.ALL_PERMISSION_KEYS)
                if role["key"] == "admin"
                else list_permissions_for_role_locked(role["key"])
            ),
        }
        for role in roles
    ]


@admin_bp.route("/admin/permissions", methods=["GET"])
@permission_required(perm.ADMIN_PERMISSIONS_MANAGE)
def admin_permissions_page():
    return render_template(
        "admin_permissions.html",
        roles=_role_permissions_matrix(),
        permission_groups=perm.PERMISSIONS,
    )


@admin_bp.route("/api/admin/roles", methods=["POST"])
@permission_required(perm.ADMIN_PERMISSIONS_MANAGE)
def api_admin_roles_create():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip().lower()
    name = (data.get("name") or "").strip()
    try:
        role_service.create_role(key, name, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(_role_permissions_matrix()), 201


@admin_bp.route("/api/admin/roles/<role_key>", methods=["DELETE"])
@permission_required(perm.ADMIN_PERMISSIONS_MANAGE)
def api_admin_roles_delete(role_key: str):
    role = get_role_locked(role_key)
    if role is None:
        return jsonify({"error": "Không tìm thấy vai trò."}), 404
    if role["is_system"]:
        return jsonify({"error": "Không thể xóa vai trò hệ thống."}), 400
    if count_users_with_role_locked(role_key) > 0:
        return jsonify({"error": "Không thể xóa: đang có tài khoản dùng vai trò này."}), 400
    role_service.delete_role(role_key, role, DB_PATH, ip=request.remote_addr, username=session["user"]["username"])
    return jsonify(_role_permissions_matrix())


@admin_bp.route("/api/admin/roles/<role_key>/permissions", methods=["PATCH"])
@permission_required(perm.ADMIN_PERMISSIONS_MANAGE)
def api_admin_roles_update_permissions(role_key: str):
    if role_key == "admin":
        return jsonify({"error": "Vai trò admin luôn có toàn quyền, không thể sửa."}), 400
    role = get_role_locked(role_key)
    if role is None:
        return jsonify({"error": "Không tìm thấy vai trò."}), 404
    data = request.get_json(silent=True) or {}
    raw_keys = data.get("permission_keys")
    old_keys = list_permissions_for_role_locked(role_key)
    try:
        role_service.update_permissions(
            role_key, raw_keys, old_keys, DB_PATH, ip=request.remote_addr, username=session["user"]["username"]
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(_role_permissions_matrix())
