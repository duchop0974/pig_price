"""Integration test cho delivery_service.py — khuôn 1:1 test_api_orders_tmp.py."""
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
import routes.deliveries as deliveries_route


SOURCE_DB = Path("data/gia_heo_hoi.db")


with tempfile.TemporaryDirectory() as tmp:
    test_db = Path(tmp) / "api_deliveries_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    conn = get_connection(test_db)
    farm = conn.execute("SELECT id FROM farms ORDER BY id LIMIT 1").fetchone()
    zone = conn.execute("SELECT id FROM zones ORDER BY id LIMIT 1").fetchone()
    pig_type = conn.execute("SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1").fetchone()
    if farm is None or zone is None or pig_type is None:
        raise RuntimeError("Thiếu dữ liệu tham chiếu (farm/zone/pig_type) để test.")
    farm_id, zone_id, pig_type_id = farm[0], zone[0], pig_type[0]
    conn.close()

    # routes.deliveries import deliveries_bp ở TOP-LEVEL của app_factory.py
    # (dòng 11, không phải trong create_app()) nên module này đã bị import —
    # và `from extensions import DB_PATH` bên trong nó đã chốt giá trị CŨ —
    # ngay từ `from app_factory import create_app` ở đầu file, TRƯỚC khi các
    # dòng patch dưới đây chạy. Phải patch thêm routes.deliveries.DB_PATH
    # riêng, patch extensions.DB_PATH suông là không đủ cho module này (bài
    # học thật: lần đầu chạy thiếu dòng này, request tạo delivery đã âm thầm
    # nhắm vào DB THẬT thay vì DB test — may mắn transaction() tự rollback
    # khi FOREIGN KEY constraint failed nên không có gì bị ghi vào DB thật,
    # đã xác nhận lại bằng tay, nhưng đây là lỗi có thể ẩn/im lặng nếu FK
    # constraint không tình cờ bắt được).
    plans_route.DB_PATH = test_db
    deliveries_route.DB_PATH = test_db
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

        r = client.post(
            "/api/plans",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 20,
                "shed": "TESTDEL",
                "lot": "TESTDEL",
                "note": "API_DELIVERY_SOURCE_PLAN",
            },
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}")
        source_plan_id = r.get_json()["id"]
        r = client.post(f"/api/plans/{source_plan_id}/approve")
        if r.status_code != 200:
            raise RuntimeError(f"duyệt kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}")

        r = client.post(
            "/api/orders",
            json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 10, "selling_price": 65000}]},
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo đơn thất bại: {r.status_code} {r.get_data(as_text=True)}")
        order = r.get_json()
        order_id = order["id"]
        line_id = order["lines"][0]["id"]

        # --- Ghi nhận xuất giao thực tế (1 phần, còn có thể xuất tiếp) ---
        r = client.post(
            f"/api/orders/{order_id}/lines/{line_id}/deliveries",
            json={
                "pig_type_id": pig_type_id,
                "quantity": 6,
                "total_weight_kg": 660,
                "unit_price": 64000,
                "delivered_date": "2099-12-20",
                "weighing_ref": "PC-TEST-001",
                "note": "TEST_DELIVERY_1",
            },
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo delivery 1 thất bại: {r.status_code} {r.get_data(as_text=True)}")
        delivery_id_1 = r.get_json()["id"]

        # --- Xuất giao lần 2 cho cùng dòng (khớp use-case "xuất nhiều lần") ---
        r = client.post(
            f"/api/orders/{order_id}/lines/{line_id}/deliveries",
            json={"pig_type_id": pig_type_id, "quantity": 4, "delivered_date": "2099-12-21"},
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo delivery 2 thất bại: {r.status_code} {r.get_data(as_text=True)}")
        delivery_id_2 = r.get_json()["id"]

        r = client.get(f"/api/orders/{order_id}/deliveries")
        if r.status_code != 200:
            raise RuntimeError(f"list deliveries thất bại: {r.status_code} {r.get_data(as_text=True)}")
        deliveries = r.get_json()
        if len(deliveries) != 2:
            raise RuntimeError(f"Kỳ vọng 2 lần xuất, thực tế: {deliveries}")

        # --- Xoá lần xuất thứ 2 ---
        r = client.delete(f"/api/deliveries/{delivery_id_2}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá delivery 2 thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)

    d1_row = conn.execute(
        "SELECT quantity, total_weight_kg, unit_price, weighing_ref FROM sale_deliveries WHERE id = ?",
        (delivery_id_1,),
    ).fetchone()
    d2_row = conn.execute("SELECT id FROM sale_deliveries WHERE id = ?", (delivery_id_2,)).fetchone()
    line_row = conn.execute(
        "SELECT actual_quantity, actual_price FROM sale_allocations WHERE id = ?", (line_id,)
    ).fetchone()

    audit_actions_list = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_delivery' "
            "AND entity_id IN (?, ?) ORDER BY id ASC",
            (delivery_id_1, delivery_id_2),
        ).fetchall()
    ]

    conn.close()

    print("Delivery1 =", d1_row)
    print("Delivery2 (sau khi xoá) =", d2_row)
    print("Line (actual sau khi xoá delivery2) =", line_row)
    print("Audit deliveries =", audit_actions_list)

    if d1_row is None:
        raise RuntimeError("Không tìm thấy delivery 1.")
    if d1_row[0] != 6 or d1_row[3] != "PC-TEST-001":
        raise RuntimeError(f"Delivery 1 không khớp: {d1_row}")

    if d2_row is not None:
        raise RuntimeError("Delivery 2 đáng lẽ đã bị xoá nhưng vẫn còn.")

    # Sau khi xoá delivery 2 (4 con), cache actual_quantity của dòng hàng
    # phải tự đồng bộ lại còn đúng 6 (chỉ còn delivery 1) — xác nhận
    # _sync_allocation_actuals() vẫn chạy đúng qua conn dùng chung.
    if line_row is None or line_row[0] != 6:
        raise RuntimeError(f"actual_quantity của dòng hàng không đồng bộ đúng sau khi xoá: {line_row}")

    expected = ["delivery.create", "delivery.create", "delivery.delete"]
    if audit_actions_list != expected:
        raise RuntimeError(f"Audit trail deliveries không khớp: {audit_actions_list} != {expected}")

    print("API DELIVERY INTEGRATION TEST = PASS")
