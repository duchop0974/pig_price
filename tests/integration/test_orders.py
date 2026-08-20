"""Migrate từ test_api_orders_tmp.py (đã xoá) — verify order_service.py
qua HTTP thật, tách 2 kịch bản độc lập (vòng đời đơn 1, xoá đơn 2)."""


def _create_source_plan(admin_client, ref_ids, note, quantity=10):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": quantity,
            "shed": "TESTORD",
            "lot": "TESTORD",
            "note": note,
        },
    )
    assert r.status_code == 201, f"tạo kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    plan_id = r.get_json()["id"]
    r = admin_client.post(f"/api/plans/{plan_id}/approve")
    assert r.status_code == 200, f"duyệt kế hoạch nguồn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    return plan_id


def test_order_full_lifecycle(admin_client, ref_ids, db_connection, audit_actions):
    source_plan_id = _create_source_plan(admin_client, ref_ids, "API_ORDER_SOURCE_PLAN")

    r = admin_client.post(
        "/api/orders",
        json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 2, "selling_price": 65000}]},
    )
    assert r.status_code == 201, f"tạo đơn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    order = r.get_json()
    order_id = order["id"]
    line_id = order["lines"][0]["id"]

    r = admin_client.post(
        f"/api/orders/{order_id}/lines",
        json={"sale_plan_id": source_plan_id, "quantity": 1, "selling_price": 64000},
    )
    assert r.status_code == 201, f"thêm dòng thất bại: {r.status_code} {r.get_data(as_text=True)}"
    line_id_2 = r.get_json()["lines"][-1]["id"]

    r = admin_client.patch(f"/api/orders/{order_id}/lines/{line_id}", json={"quantity": 3, "note": "EDITED"})
    assert r.status_code == 200, f"sửa dòng thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/orders/{order_id}/lines/{line_id_2}")
    assert r.status_code == 200, f"xoá dòng thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(
        f"/api/orders/{order_id}/sale-details",
        json={
            "contact_note": "Đã gọi điện xác nhận",
            "confirmed_sale_at": "2099-12-30",
            "delivery_time": "07:00 - 09:00",
            "payment_method": "cash",
        },
    )
    assert r.status_code == 200, f"chốt bán hàng thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(
        f"/api/orders/{order_id}/mark-done",
        json={"lines": [{"allocation_id": line_id, "actual_price": 65500, "actual_quantity": 3}]},
    )
    assert r.status_code == 200, f"mark-done thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(
        f"/api/orders/{order_id}/revenue-details",
        json={"paid_amount": 196500, "invoice_number": "HD-TEST-001"},
    )
    assert r.status_code == 200, f"ghi doanh thu thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(f"/api/orders/{order_id}/lock")
    assert r.status_code == 200, f"khoá đơn thất bại: {r.status_code} {r.get_data(as_text=True)}"

    order_row = db_connection.execute(
        "SELECT status, locked_at, paid_amount, invoice_number FROM sale_orders WHERE id = ?", (order_id,)
    ).fetchone()
    line_row = db_connection.execute(
        "SELECT quantity, note, actual_price, actual_quantity FROM sale_allocations WHERE id = ?", (line_id,)
    ).fetchone()
    line2_row = db_connection.execute("SELECT id FROM sale_allocations WHERE id = ?", (line_id_2,)).fetchone()

    assert order_row is not None, "Không tìm thấy đơn hàng."
    assert order_row[0] == "done", f"đáng lẽ status='done', thực tế: {order_row[0]}"
    assert order_row[1] is not None, "đáng lẽ đã khoá (locked_at) nhưng vẫn None."
    assert order_row[2] == 196500 and order_row[3] == "HD-TEST-001", "Doanh thu/hoá đơn không khớp."

    assert line_row is not None, "Không tìm thấy dòng hàng."
    assert line_row[0] == 3 and line_row[1] == "EDITED", f"Dòng sau khi sửa không khớp: {line_row}"
    assert line_row[2] == 65500 and line_row[3] == 3, f"Giá/số lượng bán thực tế không khớp: {line_row}"

    assert line2_row is None, "Dòng 2 đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = [
        "order.create",
        "order.line_add",
        "order.line_edit",
        "order.line_remove",
        "order.update_sale_details",
        "order.mark_done",
        "order.update_revenue_details",
        "order.lock",
    ]
    actions = audit_actions("sale_order", order_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"


def test_order_delete(admin_client, ref_ids, db_connection, audit_actions):
    source_plan_id = _create_source_plan(admin_client, ref_ids, "API_ORDER_SOURCE_PLAN_2")

    r = admin_client.post(
        "/api/orders",
        json={"lines": [{"sale_plan_id": source_plan_id, "quantity": 1, "selling_price": 60000}]},
    )
    assert r.status_code == 201, f"tạo đơn thất bại: {r.status_code} {r.get_data(as_text=True)}"
    order_id = r.get_json()["id"]

    r = admin_client.delete(f"/api/orders/{order_id}")
    assert r.status_code == 200, f"xoá đơn thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute("SELECT id FROM sale_orders WHERE id = ?", (order_id,)).fetchone()
    assert row is None, "Đơn đáng lẽ đã bị xoá nhưng vẫn còn."

    actions = audit_actions("sale_order", order_id)
    assert actions == ["order.create", "order.delete"], f"Audit trail không khớp: {actions}"
