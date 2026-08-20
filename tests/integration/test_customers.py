"""Migrate từ test_api_customers_tmp.py (đã xoá) — verify customer_service.py
qua HTTP thật. Route khách hàng nằm trong webapp/routes/plans.py."""


def test_customer_full_lifecycle(admin_client, db_connection, audit_actions):
    r = admin_client.post(
        "/api/customers",
        json={
            "name": "Cty TEST Integration",
            "phone": "0900000000",
            "address": "123 Test St",
            "tax_code": "TEST-TAX-001",
            "email": "test@example.com",
            "note": "TEST_CUSTOMER",
        },
    )
    assert r.status_code == 201, f"tạo khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}"
    customers = r.get_json()
    customer = next((c for c in customers if c["name"] == "Cty TEST Integration"), None)
    assert customer is not None, f"Không tìm thấy khách hàng vừa tạo trong response: {customers}"
    customer_id = customer["id"]

    r = admin_client.patch(
        f"/api/customers/{customer_id}",
        json={
            "name": "Cty TEST Integration EDITED",
            "phone": "0911111111",
            "address": "456 Edited St",
            "tax_code": "TEST-TAX-001",
            "email": "test@example.com",
        },
    )
    assert r.status_code == 200, f"sửa khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/customers/{customer_id}/toggle", json={"is_active": False})
    assert r.status_code == 200, f"vô hiệu hoá thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(f"/api/customers/{customer_id}/toggle", json={"is_active": True})
    assert r.status_code == 200, f"kích hoạt lại thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/customers/{customer_id}")
    assert r.status_code == 200, f"xoá khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute(
        "SELECT name, phone, address, is_active FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    assert row is None, "Khách hàng đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = ["customer.create", "customer.update", "customer.deactivate", "customer.activate", "customer.delete"]
    actions = audit_actions("customer", customer_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"
