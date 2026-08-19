"""Integration test cho pig_type_service.py (routes/admin.py, phần Pig
Types) — khuôn 1:1 các test_api_*_tmp.py khác. Patch DB_PATH trên
routes.admin/data_access/extensions giống test_api_admin_users_tmp.py."""
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
    test_db = Path(tmp) / "api_admin_pig_types_test.db"
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

        # --- Tạo loại heo ---
        r = client.post("/api/admin/pig-types", json={"code": "TEST_PT", "name": "Test Pig Type"})
        if r.status_code != 201:
            raise RuntimeError(f"tạo loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}")
        pig_types = r.get_json()
        pig_type = next((p for p in pig_types if p["code"] == "TEST_PT"), None)
        if pig_type is None:
            raise RuntimeError(f"Không tìm thấy loại heo vừa tạo trong response: {pig_types}")
        pig_type_id = pig_type["id"]

        # --- Sửa loại heo ---
        r = client.patch(f"/api/admin/pig-types/{pig_type_id}", json={"code": "TEST_PT_EDITED", "name": "Test Pig Type Edited"})
        if r.status_code != 200:
            raise RuntimeError(f"sửa loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Khoá ---
        r = client.post(f"/api/admin/pig-types/{pig_type_id}/toggle", json={"is_active": False})
        if r.status_code != 200:
            raise RuntimeError(f"khoá loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Mở lại ---
        r = client.post(f"/api/admin/pig-types/{pig_type_id}/toggle", json={"is_active": True})
        if r.status_code != 200:
            raise RuntimeError(f"mở lại loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá ---
        r = client.delete(f"/api/admin/pig-types/{pig_type_id}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    row = conn.execute("SELECT code FROM pig_types WHERE id = ?", (pig_type_id,)).fetchone()
    audit_actions_list = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'pig_type' AND entity_id = ? ORDER BY id ASC",
            (pig_type_id,),
        ).fetchall()
    ]
    conn.close()

    print("Pig type (sau khi xoá) =", row)
    print("Audit pig_type =", audit_actions_list)

    if row is not None:
        raise RuntimeError("Loại heo đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected = ["pig_type.create", "pig_type.update", "pig_type.deactivate", "pig_type.activate", "pig_type.delete"]
    if audit_actions_list != expected:
        raise RuntimeError(f"Audit trail loại heo không khớp: {audit_actions_list} != {expected}")

    print("API ADMIN PIG TYPES INTEGRATION TEST = PASS")
