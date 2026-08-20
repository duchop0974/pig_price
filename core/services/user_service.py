"""Service layer cho quản trị tài khoản (users) — STEP 2/STEP 4 nối dài
sang phần quản trị theo PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md. Mỗi hàm
gộp đúng 1 lần ghi repo + 1 lần audit_log vào chung 1 transaction qua
run_in_transaction, khớp khuôn đã dùng ở plan_service/order_service/
delivery_service/customer_service.

STEP 7 (Route Refactor): validate định dạng (username/password/farm_ids)
+ trùng username đã chuyển vào service. Tự xoá chính mình + xoá admin
cuối cùng (delete_user) VẪN ở route layer — gắn với session["user"]["id"]
(route/session concern), không phải validate input thuần, khớp nguyên
tắc phạm vi đã dùng cho role_service (guard 'admin' bất khả xâm phạm).
Resolve `role` mặc định "sales" khi không hợp lệ (create_user) vẫn ở
route — đây là fallback im lặng, khác hẳn validate-raise nên không đưa
vào service để giữ đúng hành vi cũ."""
from pathlib import Path

from core import audit_actions
from core.db import db_lock, run_in_transaction
from core.repositories import audit_repo, farms_repo, roles_repo, users_repo

_write = run_in_transaction


def _validate_new_username(username: str, db_path: Path) -> None:
    if not username or len(username) > 30:
        raise ValueError("Tên đăng nhập không hợp lệ.")
    if users_repo.get_user_by_username(username, db_path):
        raise ValueError("Tên đăng nhập đã tồn tại.")


def _validate_password(password: str) -> None:
    if len(password) < 6:
        raise ValueError("Mật khẩu cần tối thiểu 6 ký tự.")


def create_user(
    username: str,
    password: str,
    display_name: str,
    role: str,
    db_path: Path,
    *,
    ip=None,
    actor_username=None,
) -> int:
    with db_lock:
        _validate_new_username(username, db_path)
    _validate_password(password)
    result = {}

    def _do(conn):
        user_id = users_repo.create_user(username, password, db_path, display_name=display_name, role=role, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_CREATE,
            db_path,
            username=actor_username,
            ip=ip,
            detail=f"username={username}, role={role}",
            entity_type="user",
            entity_id=user_id,
            new_value={"username": username, "display_name": display_name, "role": role},
            conn=conn,
        )
        result["user_id"] = user_id

    _write(db_path, _do)
    return result["user_id"]


def update_role(user_id: int, role: str, old_role: str, db_path: Path, *, ip=None, username=None) -> None:
    with db_lock:
        valid_role_keys = {r["key"] for r in roles_repo.list_roles(db_path)}
    if role not in valid_role_keys:
        raise ValueError("Vai trò không hợp lệ.")

    def _do(conn):
        users_repo.update_user_role(user_id, role, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_UPDATE_ROLE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={"role": old_role},
            new_value={"role": role},
            conn=conn,
        )

    _write(db_path, _do)


def assign_farms(
    user_id: int, raw_farm_ids, old_farm_ids: list[int], db_path: Path, *, ip=None, username=None
) -> None:
    """`raw_farm_ids` là input thô (list chưa chắc toàn int) — validate +
    parse ở đây (STEP 7 Route Refactor), khớp message lỗi cũ của route."""
    if not isinstance(raw_farm_ids, list):
        raise ValueError("Danh sách trang trại không hợp lệ.")
    try:
        farm_ids = [int(fid) for fid in raw_farm_ids]
    except (TypeError, ValueError):
        raise ValueError("Danh sách trang trại không hợp lệ.")
    with db_lock:
        valid_ids = {f["id"] for f in farms_repo.list_farms(db_path)}
    if any(fid not in valid_ids for fid in farm_ids):
        raise ValueError("Có trang trại không tồn tại trong danh sách chọn.")

    def _do(conn):
        users_repo.assign_user_farms(user_id, farm_ids, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_ASSIGN_FARMS,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={"farm_ids": old_farm_ids},
            new_value={"farm_ids": farm_ids},
            conn=conn,
        )

    _write(db_path, _do)


def set_active(user_id: int, is_active: bool, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.set_user_active(user_id, is_active, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_ACTIVATE if is_active else audit_actions.USER_DEACTIVATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            conn=conn,
        )

    _write(db_path, _do)


def reset_password(user_id: int, new_password: str, db_path: Path, *, ip=None, username=None) -> None:
    _validate_password(new_password)

    def _do(conn):
        users_repo.reset_password(user_id, new_password, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_RESET_PASSWORD,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            conn=conn,
        )

    _write(db_path, _do)


def delete_user(user_id: int, old_user: dict, db_path: Path, *, ip=None, username=None) -> None:
    def _do(conn):
        users_repo.delete_user(user_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.USER_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="user",
            entity_id=user_id,
            old_value={
                "username": old_user["username"],
                "display_name": old_user["display_name"],
                "role": old_user["role"],
            },
            conn=conn,
        )

    _write(db_path, _do)
