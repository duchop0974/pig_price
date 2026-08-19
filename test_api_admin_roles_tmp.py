"""Integration test cho role_service.py (routes/admin.py, phần Roles) —
khuôn 1:1 các test_api_*_tmp.py khác. Patch DB_PATH trên routes.admin/
data_access/extensions giống test_api_admin_users_tmp.py."""
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
    test_db = Path(tmp) / "api_admin_roles_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    admin_route.DB_PATH = test_db
    data_access.DB_PATH = test_db
    extensions.DB_PATH = test_db

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    role_key = "test_role"

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 999999,
                "username": "integration_test",
                "display_name": "Integration Test",
                "role": "admin",
            }

        # --- Tạo vai trò ---
        r = client.post("/api/admin/roles", json={"key": role_key, "name": "Test Role"})
        if r.status_code != 201:
            raise RuntimeError(f"tạo vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Cập nhật quyền ---
        r = client.patch(f"/api/admin/roles/{role_key}/permissions", json={"permission_keys": ["admin.audit.view"]})
        if r.status_code != 200:
            raise RuntimeError(f"cập nhật quyền thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá ---
        r = client.delete(f"/api/admin/roles/{role_key}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    row = conn.execute("SELECT key FROM roles WHERE key = ?", (role_key,)).fetchone()
    audit_actions_list = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'role' AND entity_id = ? ORDER BY id ASC",
            (role_key,),
        ).fetchall()
    ]
    conn.close()

    print("Role (sau khi xoá) =", row)
    print("Audit role =", audit_actions_list)

    if row is not None:
        raise RuntimeError("Vai trò đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected = ["role.create", "role.update_permissions", "role.delete"]
    if audit_actions_list != expected:
        raise RuntimeError(f"Audit trail vai trò không khớp: {audit_actions_list} != {expected}")

    print("API ADMIN ROLES INTEGRATION TEST = PASS")
