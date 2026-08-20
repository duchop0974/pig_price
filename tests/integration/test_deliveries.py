"""Migrate từ test_api_deliveries_tmp.py (đã xoá) — verify delivery_service.py
qua HTTP thật: tạo 2 lần xuất giao cho cùng 1 dòng hàng, xoá lần 2, xác
nhận actual_quantity của dòng hàng tự đồng bộ lại đúng (_sync_allocation_actuals)."""


def test_delivery_create_and_delete(admin_client, ref_ids, db_connection):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 20,
            "shed": "TESTDEL",
            "lot": "TESTDEL",
            "note": "API_DELIVERY_SOURCE_PLAN",
        },
    )
    assert r.status_code == 201, f"tạo kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    source_plan_id = r.get_json()["id"]
    r = admin_client.post(f"/api/plans/{source_plan_id}/approve")
    assert r.status_code == 200, f"duyệt kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(
        "/api/orders",
        json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 10, "selling_price": 65000}]},
    )
    assert r.status_code == 201, f"tạo đơn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    order = r.get_json()
    order_id = order["id"]
    line_id = order["lines"][0]["id"]

    # --- Ghi nhận xuất giao thực tế (1 phần, còn có thể xuất tiếp) ---
    r = admin_client.post(
        f"/api/orders/{order_id}/lines/{line_id}/deliveries",
        json={
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 6,
            "total_weight_kg": 660,
            "unit_price": 64000,
            "delivered_date": "2099-12-20",
            "weighing_ref": "PC-TEST-001",
            "note": "TEST_DELIVERY_1",
        },
    )
    assert r.status_code == 201, f"tạo delivery 1 thất bại: {r.status_code} {r.get_data(as_text=True)}"
    delivery_id_1 = r.get_json()["id"]

    # --- Xuất giao lần 2 cho cùng dòng (khớp use-case "xuất nhiều lần") ---
    r = admin_client.post(
        f"/api/orders/{order_id}/lines/{line_id}/deliveries",
        json={"pig_type_id": ref_ids["pig_type_id"], "quantity": 4, "delivered_date": "2099-12-21"},
    )
    assert r.status_code == 201, f"tạo delivery 2 thất bại: {r.status_code} {r.get_data(as_text=True)}"
    delivery_id_2 = r.get_json()["id"]

    r = admin_client.get(f"/api/orders/{order_id}/deliveries")
    assert r.status_code == 200, f"list deliveries thất bại: {r.status_code} {r.get_data(as_text=True)}"
    deliveries = r.get_json()
    assert len(deliveries) == 2, f"Kỳ vọng 2 lần xuất, thực tế: {deliveries}"

    # --- Xoá lần xuất thứ 2 ---
    r = admin_client.delete(f"/api/deliveries/{delivery_id_2}")
    assert r.status_code == 200, f"xoá delivery 2 thất bại: {r.status_code} {r.get_data(as_text=True)}"

    d1_row = db_connection.execute(
        "SELECT quantity, total_weight_kg, unit_price, weighing_ref FROM sale_deliveries WHERE id = ?",
        (delivery_id_1,),
    ).fetchone()
    d2_row = db_connection.execute("SELECT id FROM sale_deliveries WHERE id = ?", (delivery_id_2,)).fetchone()
    line_row = db_connection.execute(
        "SELECT actual_quantity, actual_price FROM sale_allocations WHERE id = ?", (line_id,)
    ).fetchone()

    assert d1_row is not None, "Không tìm thấy delivery 1."
    assert d1_row[0] == 6 and d1_row[3] == "PC-TEST-001", f"Delivery 1 không khớp: {d1_row}"

    assert d2_row is None, "Delivery 2 đáng lẽ đã bị xoá nhưng vẫn còn."

    # Sau khi xoá delivery 2 (4 con), cache actual_quantity của dòng hàng
    # phải tự đồng bộ lại còn đúng 6 (chỉ còn delivery 1).
    assert line_row is not None and line_row[0] == 6, f"actual_quantity không đồng bộ đúng: {line_row}"

    expected = ["delivery.create", "delivery.create", "delivery.delete"]
    # 2 delivery riêng biệt (entity_id khác nhau) — query IN (id1, id2) ORDER
    # BY id để gộp theo đúng thứ tự thời gian, audit_actions() fixture chỉ
    # nhận 1 entity_id nên không tái dùng được ở đây.
    all_actions = [
        row[0]
        for row in db_connection.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_delivery' AND entity_id IN (?, ?) ORDER BY id ASC",
            (delivery_id_1, delivery_id_2),
        ).fetchall()
    ]
    assert all_actions == expected, f"Audit trail deliveries không khớp: {all_actions} != {expected}"
