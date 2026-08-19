"""Integration test cho user_service.py (routes/admin.py, phần Users) —
khuôn 1:1 các test_api_*_tmp.py khác. routes.admin import DB_PATH ở top
level (bị app_factory.py import ngay lúc create_app()), nên phải patch
DB_PATH trên module đó riêng, giống bug đã gặp với routes.deliveries."""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("webapp").resolve()))

from app_factory import create_app
from core.db import get_connection
import data_access
import extensions
import routes.admin as admin_route


SOURCE_DB = Path("data/gia_heo_hoi.db")


with tempfile.TemporaryDirectory() as tmp:
    test_db = Path(tmp) / "api_admin_users_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    admin_route.DB_PATH = test_db
    data_access.DB_PATH = test_db
    extensions.DB_PATH = test_db

    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 999999,
                "username": "integration_test",
                "display_name": "Integration Test",
                "role": "admin",
            }

        # --- Tạo tài khoản ---
        r = client.post(
            "/api/admin/users",
            json={
                "username": "integration_test_user",
                "password": "password123",
                "display_name": "Integration Test User",
                "role": "sales",
            },
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo tài khoản thất bại: {r.status_code} {r.get_data(as_text=True)}")
        users = r.get_json()
        user = next((u for u in users if u["username"] == "integration_test_user"), None)
        if user is None:
            raise RuntimeError(f"Không tìm thấy tài khoản vừa tạo trong response: {users}")
        user_id = user["id"]

        # --- Đổi vai trò ---
        r = client.patch(f"/api/admin/users/{user_id}/role", json={"role": "accounting"})
        if r.status_code != 200:
            raise RuntimeError(f"đổi vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Gán trại ---
        conn = get_connection(test_db)
        farm_row = conn.execute("SELECT id FROM farms LIMIT 1").fetchone()
        conn.close()
        if farm_row is not None:
            r = client.patch(f"/api/admin/users/{user_id}/farms", json={"farm_ids": [farm_row[0]]})
            if r.status_code != 200:
                raise RuntimeError(f"gán trại thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Vô hiệu hoá ---
        r = client.post(f"/api/admin/users/{user_id}/toggle", json={"is_active": False})
        if r.status_code != 200:
            raise RuntimeError(f"vô hiệu hoá thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Kích hoạt lại ---
        r = client.post(f"/api/admin/users/{user_id}/toggle", json={"is_active": True})
        if r.status_code != 200:
            raise RuntimeError(f"kích hoạt lại thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Đặt lại mật khẩu ---
        r = client.post(f"/api/admin/users/{user_id}/reset-password", json={"password": "newpassword123"})
        if r.status_code != 200:
            raise RuntimeError(f"đặt lại mật khẩu thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá ---
        r = client.delete(f"/api/admin/users/{user_id}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá tài khoản thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    audit_actions_list = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'user' AND entity_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    ]
    conn.close()

    print("User (sau khi xoá) =", row)
    print("Audit user =", audit_actions_list)

    if row is not None:
        raise RuntimeError("Tài khoản đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected = [
        "user.create",
        "user.update_role",
        "user.assign_farms",
        "user.deactivate",
        "user.activate",
        "user.reset_password",
        "user.delete",
    ]
    if audit_actions_list != expected:
        raise RuntimeError(f"Audit trail tài khoản không khớp: {audit_actions_list} != {expected}")

    print("API ADMIN USERS INTEGRATION TEST = PASS")
