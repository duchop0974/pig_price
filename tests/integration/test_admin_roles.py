"""Migrate từ test_api_admin_roles_tmp.py (đã xoá) — verify role_service.py
qua HTTP thật (routes/admin.py, phần Roles)."""


def test_admin_role_full_lifecycle(admin_client, db_connection, audit_actions):
    role_key = "test_role"

    r = admin_client.post("/api/admin/roles", json={"key": role_key, "name": "Test Role"})
    assert r.status_code == 201, f"tạo vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(
        f"/api/admin/roles/{role_key}/permissions", json={"permission_keys": ["admin.audit.view"]}
    )
    assert r.status_code == 200, f"cập nhật quyền thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/admin/roles/{role_key}")
    assert r.status_code == 200, f"xoá vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute("SELECT key FROM roles WHERE key = ?", (role_key,)).fetchone()
    assert row is None, "Vai trò đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = ["role.create", "role.update_permissions", "role.delete"]
    actions = audit_actions("role", role_key)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"
