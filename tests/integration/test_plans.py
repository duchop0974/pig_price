"""Migrate từ test_api_plans_tmp.py (đã xoá) — verify plan_service.py qua
HTTP thật (Flask test client), tách 3 kịch bản độc lập trong script gốc
thành 3 test function riêng để báo lỗi/chạy độc lập được."""


def _create_plan(admin_client, ref_ids, **overrides):
    payload = {
        "planned_date": "2099-12-31",
        "farm_id": ref_ids["farm_id"],
        "zone_id": ref_ids["zone_id"],
        "pig_type_id": ref_ids["pig_type_id"],
        "quantity": 1,
        "shed": "TEST",
        "lot": "TEST",
        **overrides,
    }
    r = admin_client.post("/api/plans", json=payload)
    assert r.status_code == 201, f"tạo kế hoạch thất bại: {r.status_code} {r.get_data(as_text=True)}"
    return r.get_json()["id"]


def test_plan_full_lifecycle(admin_client, ref_ids, db_connection, audit_actions):
    """create -> approve -> received -> edit -> disable -> re-enable -> delete."""
    plan_id = _create_plan(
        admin_client, ref_ids, expected_avg_weight_kg=100.0, note="API_SERVICE_INTEGRATION_TEST"
    )

    r = admin_client.post(f"/api/plans/{plan_id}/approve")
    assert r.status_code == 200, f"approve thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(f"/api/plans/{plan_id}/received", json={"received_quantity": 1})
    assert r.status_code == 200, f"received thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(
        f"/api/plans/{plan_id}/edit",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 1,
            "expected_avg_weight_kg": 100.0,
            "shed": "TEST",
            "lot": "TEST",
            "note": "API_SERVICE_INTEGRATION_TEST_EDITED",
        },
    )
    assert r.status_code == 200, f"edit thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.patch(f"/api/plans/{plan_id}", json={"status": "disabled"})
    assert r.status_code == 200, f"disable thất bại: {r.status_code} {r.get_data(as_text=True)}"
    r = admin_client.patch(f"/api/plans/{plan_id}", json={"status": "approved"})
    assert r.status_code == 200, f"re-enable thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/plans/{plan_id}")
    assert r.status_code == 200, f"delete thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute("SELECT id FROM sale_plans WHERE id = ?", (plan_id,)).fetchone()
    assert row is None, "Kế hoạch đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = [
        "plan.create",
        "plan.approve",
        "plan.update_received",
        "plan.update_edit",
        "plan.update_status",
        "plan.update_status",
        "plan.delete",
    ]
    actions = audit_actions("sale_plan", plan_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"


def test_plan_reject(admin_client, ref_ids, db_connection, audit_actions):
    plan_id = _create_plan(admin_client, ref_ids, note="API_SERVICE_INTEGRATION_TEST_2")

    r = admin_client.post(f"/api/plans/{plan_id}/reject", json={"reason": "TEST_REJECT_REASON"})
    assert r.status_code == 200, f"reject thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute(
        "SELECT status, rejected_reason FROM sale_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    assert row is not None, "Không tìm thấy kế hoạch."
    assert row[0] == "rejected", f"đáng lẽ status='rejected', thực tế: {row[0]}"
    assert row[1] == "TEST_REJECT_REASON", "rejected_reason không khớp."

    actions = audit_actions("sale_plan", plan_id)
    assert actions == ["plan.create", "plan.reject"], f"Audit trail không khớp: {actions}"


def test_plan_reconciliation_create_and_delete(admin_client, ref_ids, db_connection, audit_actions):
    plan_id = _create_plan(admin_client, ref_ids, quantity=5, note="API_SERVICE_INTEGRATION_TEST_3")

    r = admin_client.post(f"/api/plans/{plan_id}/approve")
    assert r.status_code == 200, f"approve thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post(
        f"/api/plans/{plan_id}/reconciliations",
        data={"kind": "transferred", "quantity": "5", "reason": "TEST_RECONCILE_REASON"},
    )
    assert r.status_code == 201, f"tạo đối soát thất bại: {r.status_code} {r.get_data(as_text=True)}"
    reconciliation_id = r.get_json()["id"]

    r = admin_client.get(f"/api/plans/{plan_id}/reconciliations")
    assert r.status_code == 200, f"list đối soát thất bại: {r.status_code} {r.get_data(as_text=True)}"
    recon_list = r.get_json()
    assert len(recon_list) == 1 and recon_list[0]["id"] == reconciliation_id, f"list không đúng: {recon_list}"

    r = admin_client.delete(f"/api/reconciliations/{reconciliation_id}")
    assert r.status_code == 200, f"xoá đối soát thất bại: {r.status_code} {r.get_data(as_text=True)}"

    row = db_connection.execute(
        "SELECT id FROM sale_plan_reconciliations WHERE id = ?", (reconciliation_id,)
    ).fetchone()
    assert row is None, "Bản ghi đối soát đáng lẽ đã bị xoá nhưng vẫn còn."

    expected = ["plan.create", "plan.approve", "plan.reconcile_create", "plan.reconcile_delete"]
    actions = audit_actions("sale_plan", plan_id)
    assert actions == expected, f"Audit trail không khớp: {actions} != {expected}"
