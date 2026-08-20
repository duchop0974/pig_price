"""Unit test cho get_plan_sale_breakdown() (Phase 2, đối soát đa chiều) —
gọi thẳng hàm repo, seed dữ liệu qua admin_client HTTP (đúng khuôn
test_exception_center.py) để có đơn/khách hàng/phiếu cân thật."""
from core.repositories import sale_plans_repo


def test_get_plan_sale_breakdown_empty_when_no_orders(test_db, ref_ids, admin_client):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 10,
            "shed": "B1",
            "lot": "L1",
        },
    )
    plan_id = r.get_json()["id"]
    assert sale_plans_repo.get_plan_sale_breakdown(plan_id, test_db) == []


def test_get_plan_sale_breakdown_returns_customer_price_and_ticket(test_db, ref_ids, admin_client):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 10,
            "shed": "B2",
            "lot": "L2",
        },
    )
    plan_id = r.get_json()["id"]
    admin_client.post(f"/api/plans/{plan_id}/approve")

    r = admin_client.post("/api/customers", json={"name": "Khach test breakdown"})
    customer_id = next(c["id"] for c in r.get_json() if c["name"] == "Khach test breakdown")

    r = admin_client.post(
        "/api/orders", json={"lines": [{"sale_plan_id": plan_id, "quantity": 4, "selling_price": 65000}]}
    )
    order = r.get_json()
    line_id = order["lines"][0]["id"]
    admin_client.patch(f"/api/orders/{order['id']}/sale-details", json={"customer_id": customer_id})
    admin_client.post(
        f"/api/orders/{order['id']}/lines/{line_id}/deliveries",
        json={
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 4,
            "weighing_ref": "PC-001",
            "delivered_date": "2026-01-01",
        },
    )

    breakdown = sale_plans_repo.get_plan_sale_breakdown(plan_id, test_db)
    assert len(breakdown) == 1
    line = breakdown[0]
    assert line["order_code"] == order["order_code"]
    assert line["customer_name"] == "Khach test breakdown"
    assert line["quantity"] == 4
    assert line["selling_price"] == 65000
    assert line["weighing_refs"] == ["PC-001"]
