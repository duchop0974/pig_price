"""Unit test cho filter customer_id/pig_type_id mới (Phase 3, dashboard) —
gọi thẳng sale_plans_repo.dashboard_summary(), khớp khuôn
test_exception_center.py. planned_date = hôm nay để nằm trong cửa sổ mặc
định của _dashboard_date_range(days=1) (nhìn ngược 1 ngày + buffer tới)."""
from datetime import date

from core.repositories import sale_plans_repo


def _create_order_with_customer(admin_client, ref_ids, quantity, pig_type_id, customer_name):
    today = date.today().isoformat()
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": today,
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": pig_type_id,
            "quantity": quantity,
            "shed": "F3",
            "lot": "L3",
        },
    )
    plan_id = r.get_json()["id"]
    admin_client.post(f"/api/plans/{plan_id}/approve")
    r = admin_client.post("/api/customers", json={"name": customer_name})
    customer_id = next(c["id"] for c in r.get_json() if c["name"] == customer_name)
    r = admin_client.post(
        "/api/orders", json={"lines": [{"sale_plan_id": plan_id, "quantity": quantity, "selling_price": 60000}]}
    )
    order = r.get_json()
    admin_client.patch(f"/api/orders/{order['id']}/sale-details", json={"customer_id": customer_id})
    return plan_id, customer_id


def test_dashboard_summary_customer_filter_scopes_allocated_and_actual(test_db, ref_ids, admin_client):
    plan_id, customer_id = _create_order_with_customer(admin_client, ref_ids, 7, ref_ids["pig_type_id"], "KH Dashboard A")

    unfiltered = sale_plans_repo.dashboard_summary(test_db, days=1)
    filtered = sale_plans_repo.dashboard_summary(test_db, days=1, customer_id=customer_id)
    other_customer = sale_plans_repo.dashboard_summary(test_db, days=1, customer_id=customer_id + 999999)

    assert filtered["allocated_qty"] == 7
    # planned_qty không lọc theo khách hàng (sale_plans không có khái niệm này)
    assert filtered["planned_qty"] == unfiltered["planned_qty"]
    assert other_customer["allocated_qty"] == 0


def test_dashboard_summary_pig_type_filter_scopes_planned_and_allocated(test_db, ref_ids, admin_client):
    conn = sale_plans_repo.get_connection(test_db)
    other_pig_type = conn.execute(
        "SELECT id FROM pig_types WHERE is_active = 1 AND id != ? LIMIT 1", (ref_ids["pig_type_id"],)
    ).fetchone()
    conn.close()
    assert other_pig_type is not None, "Cần ít nhất 2 loại heo active trong DB thật để test filter."

    _create_order_with_customer(admin_client, ref_ids, 5, ref_ids["pig_type_id"], "KH Dashboard B")

    matching = sale_plans_repo.dashboard_summary(test_db, days=1, pig_type_id=ref_ids["pig_type_id"])
    non_matching = sale_plans_repo.dashboard_summary(test_db, days=1, pig_type_id=other_pig_type[0])

    assert matching["planned_qty"] >= 5
    assert matching["allocated_qty"] >= 5
    assert non_matching["planned_qty"] == 0
    assert non_matching["allocated_qty"] == 0
