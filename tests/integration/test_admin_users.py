"""Migrate từ test_api_admin_users_tmp.py (đã xoá) — verify user_service.py
qua HTTP thật (routes/admin.py, phần Users)."""


def test_admin_user_full_lifecycle(admin_client, ref_ids, db_connection, audit_actions):
    r = admin_client.post(
        "/api/admin/users",
        json={
            "username": "integration_test_user",
            "password": "password123",
            "display_name": "Integration Test User",
            "role": "sales",
        },
    )
    assert r.status_code == 201, f"tạo tài khoản thất bại: {r.status_code} {r.get_data(as_text=True)}"
    users = r.get_json()
    user = next((u for u in users if u["username"] == "integration_test_user"), None)
    assert user is not None, f"Không tìm thấy tài khoản vừa tạo trong response: {users}"
    user_id = user["id"]

    r = admin_client.patch(f"/api/admin/users/{user_id}/role", json={"role": "accounting"})
    assert r.status_code == 200, f"đổi vai trò thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(f"/api/admin/users/{user_id}/farms", json={"farm_ids": [ref_ids["farm_id"]]})
    assert r.status_code == 200, f"gán trại thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/admin/users/{user_id}/toggle", json={"is_active": False})
    assert r.status_code == 200, f"vô hiệu hoá thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/admin/users/{user_id}/toggle", json={"is_active": True})
    assert r.status_code == 200, f"kích hoạt lại thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/admin/users/{user_id}/reset-password", json={"password": "newpassword123"})
    assert r.status_code == 200, f"đặt lại mật khẩu thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/admin/users/{user_id}")
    assert r.status_code == 200, f"xoá tài khoản thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    assert row is None, "Tài khoản đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = [
        "user.create",
        "user.update_role",
        "user.assign_farms",
        "user.deactivate",
        "user.activate",
        "user.reset_password",
        "user.delete",
    ]
    actions = audit_actions("user", user_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"
