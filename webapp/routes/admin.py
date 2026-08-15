"""Blueprint quản trị: tài khoản người dùng, danh mục (trang trại/khu, loại
heo bán) + nhật ký hoạt động (chỉ admin)."""
import json
import re

from flask import Blueprint, jsonify, render_template, request

from core import audit_actions
from core import permissions as perm
from core.repositories import audit_repo, users_repo
from data_access import (
    assign_user_farms_locked,
    count_plans_for_farm_locked,
    count_plans_for_pig_type_locked,
    count_plans_for_zone_locked,
    count_users_with_role_locked,
    create_farm_locked,
    create_pig_type_locked,
    create_role_locked,
    create_zone_locked,
    delete_farm_locked,
    delete_pig_type_locked,
    delete_role_locked,
    delete_zone_locked,
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
    set_permissions_for_role_locked,
    set_pig_type_active_locked,
    update_farm_locked,
    update_pig_type_locked,
    update_user_role_locked,
    update_zone_locked,
)
from extensions import DB_PATH, db_lock, log_audit
from routes.auth import permission_required

admin_bp = Blueprint("admin", __name__)

ROLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


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
    valid_role_keys = {r["key"] for r in list_roles_locked()}
    role = data.get("role") if data.get("role") in valid_role_keys else "sales"

    if not username or len(username) > 30:
        return jsonify({"error": "Tên đăng nhập không hợp lệ."}), 400
    if len(password) < 6:
        return jsonify({"error": "Mật khẩu cần tối thiểu 6 ký tự."}), 400
    if users_repo.get_user_by_username(username, DB_PATH):
        return jsonify({"error": "Tên đăng nhập đã tồn tại."}), 400

    with db_lock:
        user_id = users_repo.create_user(username, password, DB_PATH, display_name=display_name, role=role)
    log_audit(
        audit_actions.USER_CREATE,
        detail=f"username={username}, role={role}",
        entity_type="user",
        entity_id=user_id,
        new_value={"username": username, "display_name": display_name, "role": role},
    )
    return jsonify(users_repo.list_users(DB_PATH)), 201


@admin_bp.route("/api/admin/users/<int:user_id>/role", methods=["PATCH"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_update_role(user_id: int):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    valid_role_keys = {r["key"] for r in list_roles_locked()}
    if role not in valid_role_keys:
        return jsonify({"error": "Vai trò không hợp lệ."}), 400
    users = users_repo.list_users(DB_PATH)
    old_user = next((u for u in users if u["id"] == user_id), None)
    if old_user is None:
        return jsonify({"error": "Không tìm thấy tài khoản."}), 404
    update_user_role_locked(user_id, role)
    log_audit(
        audit_actions.USER_UPDATE_ROLE,
        entity_type="user",
        entity_id=user_id,
        old_value={"role": old_user["role"]},
        new_value={"role": role},
    )
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
    if not isinstance(raw_ids, list):
        return jsonify({"error": "Danh sách trang trại không hợp lệ."}), 400
    try:
        farm_ids = [int(fid) for fid in raw_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "Danh sách trang trại không hợp lệ."}), 400
    valid_ids = {f["id"] for f in list_farms_locked()}
    if any(fid not in valid_ids for fid in farm_ids):
        return jsonify({"error": "Có trang trại không tồn tại trong danh sách chọn."}), 400

    old_ids = [f["id"] for f in list_farms_for_user_locked(user_id)]
    assign_user_farms_locked(user_id, farm_ids)
    log_audit(
        audit_actions.USER_ASSIGN_FARMS,
        entity_type="user",
        entity_id=user_id,
        old_value={"farm_ids": old_ids},
        new_value={"farm_ids": farm_ids},
    )
    return jsonify(list_farms_for_user_locked(user_id))


@admin_bp.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_toggle(user_id: int):
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    with db_lock:
        users_repo.set_user_active(user_id, is_active, DB_PATH)
    log_audit(
        audit_actions.USER_ACTIVATE if is_active else audit_actions.USER_DEACTIVATE,
        entity_type="user",
        entity_id=user_id,
    )
    return jsonify(users_repo.list_users(DB_PATH))


@admin_bp.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
@permission_required(perm.ADMIN_USERS_MANAGE)
def api_admin_users_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 6:
        return jsonify({"error": "Mật khẩu cần tối thiểu 6 ký tự."}), 400
    with db_lock:
        users_repo.reset_password(user_id, password, DB_PATH)
    log_audit(audit_actions.USER_RESET_PASSWORD, entity_type="user", entity_id=user_id)
    return jsonify({"ok": True})


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
    if not code or len(code) > 30:
        return jsonify({"error": "Vui lòng nhập mã trang trại hợp lệ."}), 400
    if province and len(province) > 100:
        return jsonify({"error": "Tên tỉnh quá dài."}), 400
    if any(f["code"] == code for f in list_farms_locked()):
        return jsonify({"error": "Mã trang trại đã tồn tại."}), 400
    create_farm_locked(code, province)
    new_farm = next((f for f in list_farms_locked() if f["code"] == code), None)
    log_audit(
        audit_actions.FARM_CREATE,
        entity_type="farm",
        entity_id=new_farm["id"] if new_farm else code,
        new_value={"code": code, "province": province},
    )
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
    if not code or len(code) > 30:
        return jsonify({"error": "Mã trang trại không hợp lệ."}), 400
    if province and len(province) > 100:
        return jsonify({"error": "Tên tỉnh quá dài."}), 400
    if any(f["code"] == code and f["id"] != farm_id for f in list_farms_locked()):
        return jsonify({"error": "Mã trang trại đã tồn tại."}), 400
    update_farm_locked(farm_id, code, province)
    log_audit(
        audit_actions.FARM_UPDATE,
        entity_type="farm",
        entity_id=farm_id,
        old_value={"code": old_farm["code"], "province": old_farm["province"]},
        new_value={"code": code, "province": province},
    )
    return jsonify(list_farms_locked())


@admin_bp.route("/api/admin/farms/<int:farm_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_farms_delete(farm_id: int):
    old_farm = get_farm_locked(farm_id)
    if old_farm is None:
        return jsonify({"error": "Không tìm thấy trang trại."}), 404
    if count_plans_for_farm_locked(farm_id) > 0:
        return jsonify({"error": "Không thể xóa: trang trại đang được dùng trong kế hoạch xuất bán."}), 400
    delete_farm_locked(farm_id)
    log_audit(
        audit_actions.FARM_DELETE,
        entity_type="farm",
        entity_id=farm_id,
        old_value={"code": old_farm["code"], "province": old_farm["province"]},
    )
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
    if not code or len(code) > 30:
        return jsonify({"error": "Vui lòng nhập tên khu hợp lệ."}), 400
    if any(z["code"] == code for z in list_zones_locked(farm_id)):
        return jsonify({"error": "Tên khu đã tồn tại trong trang trại này."}), 400
    create_zone_locked(farm_id, code)
    new_zone = next((z for z in list_zones_locked(farm_id) if z["code"] == code), None)
    log_audit(
        audit_actions.ZONE_CREATE,
        entity_type="zone",
        entity_id=new_zone["id"] if new_zone else code,
        new_value={"farm_id": farm_id, "code": code},
    )
    return jsonify(list_zones_locked(farm_id)), 201


@admin_bp.route("/api/admin/zones/<int:zone_id>", methods=["PATCH"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_zones_update(zone_id: int):
    zone = get_zone_locked(zone_id)
    if zone is None:
        return jsonify({"error": "Không tìm thấy khu."}), 404
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code or len(code) > 30:
        return jsonify({"error": "Tên khu không hợp lệ."}), 400
    if any(z["code"] == code and z["id"] != zone_id for z in list_zones_locked(zone["farm_id"])):
        return jsonify({"error": "Tên khu đã tồn tại trong trang trại này."}), 400
    update_zone_locked(zone_id, code)
    log_audit(
        audit_actions.ZONE_UPDATE,
        entity_type="zone",
        entity_id=zone_id,
        old_value={"code": zone["code"]},
        new_value={"code": code},
    )
    return jsonify(list_zones_locked(zone["farm_id"]))


@admin_bp.route("/api/admin/zones/<int:zone_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_FARMS_MANAGE)
def api_admin_zones_delete(zone_id: int):
    zone = get_zone_locked(zone_id)
    if zone is None:
        return jsonify({"error": "Không tìm thấy khu."}), 404
    if count_plans_for_zone_locked(zone_id) > 0:
        return jsonify({"error": "Không thể xóa: khu đang được dùng trong kế hoạch xuất bán."}), 400
    delete_zone_locked(zone_id)
    log_audit(
        audit_actions.ZONE_DELETE,
        entity_type="zone",
        entity_id=zone_id,
        old_value={"farm_id": zone["farm_id"], "code": zone["code"]},
    )
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
    if not code or len(code) > 30:
        return jsonify({"error": "Mã loại heo không hợp lệ."}), 400
    if not name or len(name) > 100:
        return jsonify({"error": "Tên loại heo không hợp lệ."}), 400
    if any(pt["code"] == code for pt in list_pig_types_locked()):
        return jsonify({"error": "Mã loại heo đã tồn tại."}), 400
    pig_type_id = create_pig_type_locked(code, name)
    log_audit(
        audit_actions.PIG_TYPE_CREATE,
        entity_type="pig_type",
        entity_id=pig_type_id,
        new_value={"code": code, "name": name},
    )
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
    if not code or len(code) > 30:
        return jsonify({"error": "Mã loại heo không hợp lệ."}), 400
    if not name or len(name) > 100:
        return jsonify({"error": "Tên loại heo không hợp lệ."}), 400
    if any(pt["code"] == code and pt["id"] != pig_type_id for pt in list_pig_types_locked()):
        return jsonify({"error": "Mã loại heo đã tồn tại."}), 400
    update_pig_type_locked(pig_type_id, code, name)
    log_audit(
        audit_actions.PIG_TYPE_UPDATE,
        entity_type="pig_type",
        entity_id=pig_type_id,
        old_value={"code": old_pig_type["code"], "name": old_pig_type["name"]},
        new_value={"code": code, "name": name},
    )
    return jsonify(list_pig_types_locked())


@admin_bp.route("/api/admin/pig-types/<int:pig_type_id>/toggle", methods=["POST"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_toggle(pig_type_id: int):
    if get_pig_type_locked(pig_type_id) is None:
        return jsonify({"error": "Không tìm thấy loại heo."}), 404
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))
    set_pig_type_active_locked(pig_type_id, is_active)
    log_audit(
        audit_actions.PIG_TYPE_ACTIVATE if is_active else audit_actions.PIG_TYPE_DEACTIVATE,
        entity_type="pig_type",
        entity_id=pig_type_id,
    )
    return jsonify(list_pig_types_locked())


@admin_bp.route("/api/admin/pig-types/<int:pig_type_id>", methods=["DELETE"])
@permission_required(perm.ADMIN_PIG_TYPES_MANAGE)
def api_admin_pig_types_delete(pig_type_id: int):
    old_pig_type = get_pig_type_locked(pig_type_id)
    if old_pig_type is None:
        return jsonify({"error": "Không tìm thấy loại heo."}), 404
    if count_plans_for_pig_type_locked(pig_type_id) > 0:
        return jsonify({"error": "Không thể xóa: loại heo đang được dùng trong kế hoạch xuất bán."}), 400
    delete_pig_type_locked(pig_type_id)
    log_audit(
        audit_actions.PIG_TYPE_DELETE,
        entity_type="pig_type",
        entity_id=pig_type_id,
        old_value={"code": old_pig_type["code"], "name": old_pig_type["name"]},
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
    if not ROLE_KEY_RE.match(key):
        return jsonify({"error": "Mã vai trò không hợp lệ (chỉ chữ thường/số/gạch dưới, bắt đầu bằng chữ, 2-30 ký tự)."}), 400
    if not name or len(name) > 50:
        return jsonify({"error": "Vui lòng nhập tên vai trò hợp lệ."}), 400
    if get_role_locked(key) is not None:
        return jsonify({"error": "Mã vai trò đã tồn tại."}), 400
    create_role_locked(key, name)
    log_audit(
        audit_actions.ROLE_CREATE,
        entity_type="role",
        entity_id=key,
        new_value={"key": key, "name": name},
    )
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
    delete_role_locked(role_key)
    log_audit(
        audit_actions.ROLE_DELETE,
        entity_type="role",
        entity_id=role_key,
        old_value={"key": role_key, "name": role["name"]},
    )
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
    if not isinstance(raw_keys, list) or any(k not in perm.ALL_PERMISSION_KEYS for k in raw_keys):
        return jsonify({"error": "Danh sách quyền không hợp lệ."}), 400
    old_keys = list_permissions_for_role_locked(role_key)
    set_permissions_for_role_locked(role_key, raw_keys)
    log_audit(
        audit_actions.ROLE_UPDATE_PERMISSIONS,
        entity_type="role",
        entity_id=role_key,
        old_value={"permission_keys": old_keys},
        new_value={"permission_keys": raw_keys},
    )
    return jsonify(_role_permissions_matrix())
