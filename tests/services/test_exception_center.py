"""Unit test cho 4 hàm repo mới của Exception Center (STEP 10) — gọi thẳng
hàm repo (không qua Flask route) để verify tiêu chí lọc đúng/không lọc
nhầm, khớp khuôn test_plan_service.py. Seed dữ liệu qua admin_client (HTTP)
vì cần đi qua đúng service/audit layer (VD thời điểm order.mark_done phải
được audit_log ghi lại thật, không giả lập trực tiếp bằng SQL)."""
from core.repositories import roles_repo, sale_deliveries_repo, sale_orders_repo, sale_plans_repo


def _create_and_mark_done_order(admin_client, ref_ids):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 10,
            "shed": "A1",
            "lot": "L1",
        },
    )
    plan_id = r.get_json()["id"]
    admin_client.post(f"/api/plans/{plan_id}/approve")
    r = admin_client.post(
        "/api/orders", json={"lines": [{"sale_plan_id": plan_id, "quantity": 2, "selling_price": 60000}]}
    )
    order = r.get_json()
    line_id = order["lines"][0]["id"]
    admin_client.patch(
        f"/api/orders/{order['id']}/mark-done",
        json={"lines": [{"allocation_id": line_id, "actual_price": 60000, "actual_quantity": 2}]},
    )
    return order["id"], line_id


def test_list_stale_awaiting_revenue_excludes_recent_includes_after_threshold(test_db, ref_ids, admin_client):
    order_id, _ = _create_and_mark_done_order(admin_client, ref_ids)

    recent = sale_orders_repo.list_stale_awaiting_revenue(test_db, days=14)
    assert order_id not in [o["id"] for o in recent["items"]]

    stale = sale_orders_repo.list_stale_awaiting_revenue(test_db, days=0)
    assert order_id in [o["id"] for o in stale["items"]]


def test_list_idle_supply_requires_approved_received_and_remaining(test_db, ref_ids, admin_client):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 10,
            "shed": "A2",
            "lot": "L2",
        },
    )
    plan_id = r.get_json()["id"]

    before_approve = sale_plans_repo.list_idle_supply(test_db, days=0)
    assert plan_id not in [p["id"] for p in before_approve["items"]]

    admin_client.post(f"/api/plans/{plan_id}/approve")
    not_received_yet = sale_plans_repo.list_idle_supply(test_db, days=0)
    assert plan_id not in [p["id"] for p in not_received_yet["items"]]

    admin_client.patch(f"/api/plans/{plan_id}/received", json={"received_quantity": 10})
    idle = sale_plans_repo.list_idle_supply(test_db, days=0)
    assert plan_id in [p["id"] for p in idle["items"]]

    not_yet_idle = sale_plans_repo.list_idle_supply(test_db, days=7)
    assert plan_id not in [p["id"] for p in not_yet_idle["items"]]


def test_list_deliveries_missing_weight_flags_null_weight_only(test_db, ref_ids, admin_client):
    order_id, line_id = _create_and_mark_done_order(admin_client, ref_ids)

    r = admin_client.post(
        f"/api/orders/{order_id}/lines/{line_id}/deliveries",
        json={"pig_type_id": ref_ids["pig_type_id"], "quantity": 1, "delivered_date": "2026-01-01"},
    )
    delivery_id = r.get_json()["id"]

    missing = sale_deliveries_repo.list_deliveries_missing_weight(test_db)
    assert delivery_id in [d["id"] for d in missing["items"]]

    r2 = admin_client.post(
        f"/api/orders/{order_id}/lines/{line_id}/deliveries",
        json={
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 1,
            "total_weight_kg": 100,
            "delivered_date": "2026-01-01",
        },
    )
    weighed_id = r2.get_json()["id"]
    missing_after = sale_deliveries_repo.list_deliveries_missing_weight(test_db)
    assert weighed_id not in [d["id"] for d in missing_after["items"]]


def test_list_unexpected_farm_permissions_flags_grants_outside_default(test_db, admin_client):
    baseline = roles_repo.list_unexpected_farm_permissions(test_db)
    assert baseline == []

    admin_client.patch(
        "/api/admin/roles/farm/permissions",
        json={"permission_keys": ["plans.create", "plans.receive", "admin.audit.view"]},
    )
    after = roles_repo.list_unexpected_farm_permissions(test_db)
    assert after == ["admin.audit.view"]
