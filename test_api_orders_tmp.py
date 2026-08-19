"""Integration test cho order_service.py (core/services/order_service.py) —
khuôn 1:1 test_api_plans_tmp.py: copy DB thật ra bản tạm, patch DB_PATH ở
mọi module giữ biến riêng (routes.plans, data_access, extensions — log_audit()
dùng thẳng extensions.DB_PATH, bỏ sót sẽ rò audit vào DB thật, đã có bài học
thật từ test_api_plans_tmp.py), chạy qua HTTP thật bằng Flask test client,
assert cả response lẫn dữ liệu ghi trong DB (bảng nghiệp vụ + audit_log)."""
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
    test_db = Path(tmp) / "api_orders_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    conn = get_connection(test_db)
    farm = conn.execute("SELECT id FROM farms ORDER BY id LIMIT 1").fetchone()
    zone = conn.execute("SELECT id FROM zones ORDER BY id LIMIT 1").fetchone()
    pig_type = conn.execute("SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1").fetchone()
    if farm is None or zone is None or pig_type is None:
        raise RuntimeError("Thiếu dữ liệu tham chiếu (farm/zone/pig_type) để test.")
    farm_id, zone_id, pig_type_id = farm[0], zone[0], pig_type[0]
    conn.close()

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

        # --- Kế hoạch trại nguồn (tạo + duyệt để có remaining_quantity) ---
        r = client.post(
            "/api/plans",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 10,
                "shed": "TESTORD",
                "lot": "TESTORD",
                "note": "API_ORDER_SOURCE_PLAN",
            },
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}")
        source_plan_id = r.get_json()["id"]
        r = client.post(f"/api/plans/{source_plan_id}/approve")
        if r.status_code != 200:
            raise RuntimeError(f"duyệt kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Tạo đơn hàng 1 dòng ---
        r = client.post(
            "/api/orders",
            json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 2, "selling_price": 65000}]},
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo đơn thất bại: {r.status_code} {r.get_data(as_text=True)}")
        order = r.get_json()
        order_id = order["id"]
        line_id = order["lines"][0]["id"]

        # --- Thêm 1 dòng nữa ---
        r = client.post(
            f"/api/orders/{order_id}/lines",
            json={"sale_plan_id": source_plan_id, "quantity": 1, "selling_price": 64000},
        )
        if r.status_code != 201:
            raise RuntimeError(f"thêm dòng thất bại: {r.status_code} {r.get_data(as_text=True)}")
        line_id_2 = r.get_json()["lines"][-1]["id"]

        # --- Sửa dòng 1 ---
        r = client.patch(f"/api/orders/{order_id}/lines/{line_id}", json={"quantity": 3, "note": "EDITED"})
        if r.status_code != 200:
            raise RuntimeError(f"sửa dòng thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá dòng 2 (còn lại đúng 1 dòng) ---
        r = client.delete(f"/api/orders/{order_id}/lines/{line_id_2}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá dòng thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Chốt bán hàng ---
        r = client.patch(
            f"/api/orders/{order_id}/sale-details",
            json={
                "contact_note": "Đã gọi điện xác nhận",
                "confirmed_sale_at": "2099-12-30",
                "delivery_time": "07:00 - 09:00",
                "payment_method": "cash",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"chốt bán hàng thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Đánh dấu Đã bán ---
        r = client.patch(
            f"/api/orders/{order_id}/mark-done",
            json={"lines": [{"allocation_id": line_id, "actual_price": 65500, "actual_quantity": 3}]},
        )
        if r.status_code != 200:
            raise RuntimeError(f"mark-done thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Ghi nhận doanh thu ---
        r = client.patch(
            f"/api/orders/{order_id}/revenue-details",
            json={"paid_amount": 196500, "invoice_number": "HD-TEST-001"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"ghi doanh thu thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Khoá đơn (Data Freeze) ---
        r = client.patch(f"/api/orders/{order_id}/lock")
        if r.status_code != 200:
            raise RuntimeError(f"khoá đơn thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Đơn thứ 2, throwaway, để test xoá đơn (chưa khoá) ---
        r = client.post(
            "/api/orders",
            json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 1, "selling_price": 60000}]},
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo đơn 2 thất bại: {r.status_code} {r.get_data(as_text=True)}")
        order_id_2 = r.get_json()["id"]
        r = client.delete(f"/api/orders/{order_id_2}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá đơn 2 thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)

    order_row = conn.execute(
        "SELECT status, locked_at, paid_amount, invoice_number FROM sale_orders WHERE id = ?", (order_id,)
    ).fetchone()
    line_row = conn.execute(
        "SELECT quantity, note, actual_price, actual_quantity FROM sale_allocations WHERE id = ?", (line_id,)
    ).fetchone()
    line2_row = conn.execute("SELECT id FROM sale_allocations WHERE id = ?", (line_id_2,)).fetchone()
    order2_row = conn.execute("SELECT id FROM sale_orders WHERE id = ?", (order_id_2,)).fetchone()

    audit1_actions = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_order' AND entity_id = ? ORDER BY id ASC",
            (order_id,),
        ).fetchall()
    ]
    audit2_actions = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_order' AND entity_id = ? ORDER BY id ASC",
            (order_id_2,),
        ).fetchall()
    ]

    conn.close()

    print("Order1 =", order_row)
    print("Line1 =", line_row)
    print("Line2 (sau khi xoá) =", line2_row)
    print("Order2 (sau khi xoá) =", order2_row)
    print("Audit order1 =", audit1_actions)
    print("Audit order2 =", audit2_actions)

    if order_row is None:
        raise RuntimeError("Không tìm thấy đơn hàng 1.")
    if order_row[0] != "done":
        raise RuntimeError(f"Đơn 1 đáng lẽ status='done', thực tế: {order_row[0]}")
    if order_row[1] is None:
        raise RuntimeError("Đơn 1 đáng lẽ đã khoá (locked_at) nhưng vẫn None.")
    if order_row[2] != 196500 or order_row[3] != "HD-TEST-001":
        raise RuntimeError("Doanh thu/hoá đơn đơn 1 không khớp.")

    if line_row is None:
        raise RuntimeError("Không tìm thấy dòng hàng 1.")
    if line_row[0] != 3 or line_row[1] != "EDITED":
        raise RuntimeError(f"Dòng 1 sau khi sửa không khớp: {line_row}")
    if line_row[2] != 65500 or line_row[3] != 3:
        raise RuntimeError(f"Giá/số lượng bán thực tế dòng 1 không khớp: {line_row}")

    if line2_row is not None:
        raise RuntimeError("Dòng 2 đáng lẽ đã bị xoá nhưng vẫn còn.")

    if order2_row is not None:
        raise RuntimeError("Đơn 2 đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected1 = [
        "order.create",
        "order.line_add",
        "order.line_edit",
        "order.line_remove",
        "order.update_sale_details",
        "order.mark_done",
        "order.update_revenue_details",
        "order.lock",
    ]
    if audit1_actions != expected1:
        raise RuntimeError(f"Audit trail đơn 1 không khớp: {audit1_actions} != {expected1}")

    expected2 = ["order.create", "order.delete"]
    if audit2_actions != expected2:
        raise RuntimeError(f"Audit trail đơn 2 không khớp: {audit2_actions} != {expected2}")

    print("API ORDER INTEGRATION TEST = PASS")
