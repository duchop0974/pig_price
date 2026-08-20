"""Migrate từ test_api_farm_scope_tmp.py (đã xoá) — verify STEP 3
(Authorization + Data Scope): 6 route ghi trên sale_plans/reconciliation/
delivery phải chặn tài khoản vai trò 'farm' thao tác trên trại KHÔNG
được gán, kể cả khi role 'farm' được admin lỡ cấp thêm quyền review/
delete/reconcile_delete/delivery_delete qua /admin/permissions."""
PERMISSION_DENIED_MSG = "Bạn không có quyền thực hiện thao tác này."


def _make_plan(admin_client, farm_b, zone_b, pig_type_id, note):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": farm_b,
            "zone_id": zone_b,
            "pig_type_id": pig_type_id,
            "quantity": 20,
            "shed": "TESTFS",
            "lot": "TESTFS",
            "note": note,
        },
    )
    assert r.status_code == 201, f"tạo kế hoạch nguồn ({note}) thất bại: {r.status_code} {r.get_data(as_text=True)}"
    return r.get_json()["id"]


def _make_farm_user(admin_client, username, farm_id):
    r = admin_client.post(
        "/api/admin/users",
        json={"username": username, "password": "password123", "display_name": username, "role": "farm"},
    )
    assert r.status_code == 201, f"tạo user {username} thất bại: {r.status_code} {r.get_data(as_text=True)}"
    users = r.get_json()
    user = next(u for u in users if u["username"] == username)
    r = admin_client.patch(f"/api/admin/users/{user['id']}/farms", json={"farm_ids": [farm_id]})
    assert r.status_code == 200, f"gán trại cho {username} thất bại: {r.status_code} {r.get_data(as_text=True)}"
    return {"id": user["id"], "username": username, "display_name": username, "role": "farm"}


def test_write_actions_blocked_for_wrong_farm_and_allowed_for_correct_farm(
    admin_client, db_connection, login_as
):
    farm_a = db_connection.execute("SELECT id FROM farms ORDER BY id LIMIT 1").fetchone()[0]
    farm_b = db_connection.execute(
        "SELECT id FROM farms WHERE id != ? ORDER BY id LIMIT 1", (farm_a,)
    ).fetchone()[0]
    zone_b = db_connection.execute(
        "SELECT id FROM zones WHERE farm_id = ? ORDER BY id LIMIT 1", (farm_b,)
    ).fetchone()[0]
    pig_type_id = db_connection.execute(
        "SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()[0]

    # --- Cấp thêm 4 quyền review/delete/reconcile_delete/delivery_delete cho
    # role 'farm' (mô phỏng đúng tình huống admin cấu hình sai qua
    # /admin/permissions) — giữ lại 2 quyền mặc định plans.create/receive.
    r = admin_client.patch(
        "/api/admin/roles/farm/permissions",
        json={
            "permission_keys": [
                "plans.create",
                "plans.receive",
                "plans.review",
                "plans.delete",
                "plans.reconcile_delete",
                "plans.delivery_delete",
            ]
        },
    )
    assert r.status_code == 200, f"cấp quyền role farm thất bại: {r.status_code} {r.get_data(as_text=True)}"

    user_wrong = _make_farm_user(admin_client, "test_fs_wrong", farm_a)
    user_right = _make_farm_user(admin_client, "test_fs_right", farm_b)

    plan_approve = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_APPROVE")
    plan_reject = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_REJECT")
    plan_update = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_UPDATE")
    plan_delete = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_DELETE")
    plan_reconcile = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_RECONCILE")
    plan_delivery = _make_plan(admin_client, farm_b, zone_b, pig_type_id, "FS_DELIVERY")

    r = admin_client.post(f"/api/plans/{plan_update}/approve")
    assert r.status_code == 200, "duyệt plan_update thất bại"

    r = admin_client.post(f"/api/plans/{plan_reconcile}/approve")
    assert r.status_code == 200, "duyệt plan_reconcile thất bại"
    r = admin_client.patch(f"/api/plans/{plan_reconcile}/received", json={"received_quantity": 20})
    assert r.status_code == 200, "ghi nhận thực nhận plan_reconcile thất bại"
    r = admin_client.post(
        f"/api/plans/{plan_reconcile}/reconciliations",
        data={"kind": "still_at_farm", "reason": "TEST_FS", "quantity": "5"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, f"tạo đối soát plan_reconcile thất bại: {r.status_code} {r.get_data(as_text=True)}"
    reconciliation_id = r.get_json()["id"]

    r = admin_client.post(f"/api/plans/{plan_delivery}/approve")
    assert r.status_code == 200, "duyệt plan_delivery thất bại"
    r = admin_client.post(
        "/api/orders", json={"lines": [{"sale_plan_id": plan_delivery, "quantity": 10, "selling_price": 65000}]}
    )
    assert r.status_code == 201, f"tạo đơn cho plan_delivery thất bại: {r.status_code} {r.get_data(as_text=True)}"
    order = r.get_json()
    order_id, line_id = order["id"], order["lines"][0]["id"]
    r = admin_client.post(
        f"/api/orders/{order_id}/lines/{line_id}/deliveries",
        json={"pig_type_id": pig_type_id, "quantity": 5, "delivered_date": "2099-12-20"},
    )
    assert r.status_code == 201, f"tạo delivery cho plan_delivery thất bại: {r.status_code} {r.get_data(as_text=True)}"
    delivery_id = r.get_json()["id"]

    # --- Với user SAI trại (farm A) — cả 6 hành động phải bị 403 farm-scope,
    # KHÔNG phải 403 thiếu quyền (đã cấp đủ quyền ở trên) ---
    login_as(admin_client, user_wrong)
    checks_403 = [
        ("approve", admin_client.post(f"/api/plans/{plan_approve}/approve")),
        ("reject", admin_client.post(f"/api/plans/{plan_reject}/reject", json={"reason": "test"})),
        ("update", admin_client.patch(f"/api/plans/{plan_update}", json={"status": "cancelled"})),
        ("delete", admin_client.delete(f"/api/plans/{plan_delete}")),
        ("reconcile_delete", admin_client.delete(f"/api/reconciliations/{reconciliation_id}")),
        ("delivery_delete", admin_client.delete(f"/api/deliveries/{delivery_id}")),
    ]
    for name, r in checks_403:
        body = r.get_data(as_text=True)
        assert r.status_code == 403, f"{name}: kỳ vọng 403, thực tế {r.status_code} {body}"
        assert PERMISSION_DENIED_MSG not in body, f"{name}: bị chặn bởi thiếu quyền, không phải farm-scope: {body}"

    # --- Với user ĐÚNG trại (farm B) — cả 6 hành động phải thành công ---
    login_as(admin_client, user_right)
    checks_ok = [
        ("approve", admin_client.post(f"/api/plans/{plan_approve}/approve"), 200),
        ("reject", admin_client.post(f"/api/plans/{plan_reject}/reject", json={"reason": "test"}), 200),
        ("update", admin_client.patch(f"/api/plans/{plan_update}", json={"status": "cancelled"}), 200),
        ("delete", admin_client.delete(f"/api/plans/{plan_delete}"), 200),
        ("reconcile_delete", admin_client.delete(f"/api/reconciliations/{reconciliation_id}"), 200),
        ("delivery_delete", admin_client.delete(f"/api/deliveries/{delivery_id}"), 200),
    ]
    for name, r, expect in checks_ok:
        assert r.status_code == expect, f"{name}: kỳ vọng {expect}, thực tế {r.status_code} {r.get_data(as_text=True)}"
