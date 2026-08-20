"""Migrate từ test_api_admin_pig_types_tmp.py (đã xoá) — verify
pig_type_service.py qua HTTP thật (routes/admin.py, phần Pig Types)."""


def test_admin_pig_type_full_lifecycle(admin_client, db_connection, audit_actions):
    r = admin_client.post("/api/admin/pig-types", json={"code": "TEST_PT", "name": "Test Pig Type"})
    assert r.status_code == 201, f"tạo loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}"
    pig_types = r.get_json()
    pig_type = next((p for p in pig_types if p["code"] == "TEST_PT"), None)
    assert pig_type is not None, f"Không tìm thấy loại heo vừa tạo trong response: {pig_types}"
    pig_type_id = pig_type["id"]

    r = admin_client.patch(
        f"/api/admin/pig-types/{pig_type_id}", json={"code": "TEST_PT_EDITED", "name": "Test Pig Type Edited"}
    )
    assert r.status_code == 200, f"sửa loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/admin/pig-types/{pig_type_id}/toggle", json={"is_active": False})
    assert r.status_code == 200, f"khoá loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/admin/pig-types/{pig_type_id}/toggle", json={"is_active": True})
    assert r.status_code == 200, f"mở lại loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/admin/pig-types/{pig_type_id}")
    assert r.status_code == 200, f"xoá loại heo thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute("SELECT code FROM pig_types WHERE id = ?", (pig_type_id,)).fetchone()
    assert row is None, "Loại heo đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = ["pig_type.create", "pig_type.update", "pig_type.deactivate", "pig_type.activate", "pig_type.delete"]
    actions = audit_actions("pig_type", pig_type_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"
