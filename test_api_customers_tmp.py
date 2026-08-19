"""Integration test cho customer_service.py — khuôn 1:1 các test_api_*_tmp.py
khác. Route khách hàng nằm trong webapp/routes/plans.py (đã patch DB_PATH
qua plans_route), không cần patch thêm module nào khác."""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("webapp").resolve()))

from app_factory import create_app
from core.db import get_connection
import data_access
import extensions
import routes.plans as plans_route


SOURCE_DB = Path("data/gia_heo_hoi.db")


with tempfile.TemporaryDirectory() as tmp:
    test_db = Path(tmp) / "api_customers_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    plans_route.DB_PATH = test_db
    data_access.DB_PATH = test_db
    extensions.DB_PATH = test_db

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 999999,
                "username": "integration_test",
                "display_name": "Integration Test",
                "role": "admin",
            }

        # --- Tạo khách hàng ---
        r = client.post(
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
        if r.status_code != 201:
            raise RuntimeError(f"tạo khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}")
        customers = r.get_json()
        customer = next((c for c in customers if c["name"] == "Cty TEST Integration"), None)
        if customer is None:
            raise RuntimeError(f"Không tìm thấy khách hàng vừa tạo trong response: {customers}")
        customer_id = customer["id"]

        # --- Sửa khách hàng ---
        r = client.patch(
            f"/api/customers/{customer_id}",
            json={
                "name": "Cty TEST Integration EDITED",
                "phone": "0911111111",
                "address": "456 Edited St",
                "tax_code": "TEST-TAX-001",
                "email": "test@example.com",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"sửa khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Vô hiệu hoá ---
        r = client.post(f"/api/customers/{customer_id}/toggle", json={"is_active": False})
        if r.status_code != 200:
            raise RuntimeError(f"vô hiệu hoá thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Kích hoạt lại ---
        r = client.post(f"/api/customers/{customer_id}/toggle", json={"is_active": True})
        if r.status_code != 200:
            raise RuntimeError(f"kích hoạt lại thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá ---
        r = client.delete(f"/api/customers/{customer_id}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá khách hàng thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    row = conn.execute(
        "SELECT name, phone, address, is_active FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    audit_actions_list = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'customer' AND entity_id = ? ORDER BY id ASC",
            (customer_id,),
        ).fetchall()
    ]
    conn.close()

    print("Customer (sau khi xoá) =", row)
    print("Audit customer =", audit_actions_list)

    if row is not None:
        raise RuntimeError("Khách hàng đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected = ["customer.create", "customer.update", "customer.deactivate", "customer.activate", "customer.delete"]
    if audit_actions_list != expected:
        raise RuntimeError(f"Audit trail khách hàng không khớp: {audit_actions_list} != {expected}")

    print("API CUSTOMER INTEGRATION TEST = PASS")
