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
    test_db = Path(tmp) / "api_plans_test.db"

    shutil.copy2(SOURCE_DB, test_db)

    conn = get_connection(test_db)

    farm = conn.execute(
        "SELECT id FROM farms ORDER BY id LIMIT 1"
    ).fetchone()

    zone = conn.execute(
        "SELECT id FROM zones ORDER BY id LIMIT 1"
    ).fetchone()

    pig_type = conn.execute(
        "SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()

    if farm is None:
        raise RuntimeError("Không tìm thấy farm.")

    if zone is None:
        raise RuntimeError("Không tìm thấy zone.")

    if pig_type is None:
        raise RuntimeError("Không tìm thấy pig_type active.")

    farm_id = farm[0]
    zone_id = zone[0]
    pig_type_id = pig_type[0]

    conn.close()

    # Route, data_access, VÀ extensions (log_audit() dùng trực tiếp
    # extensions.DB_PATH ở module-level, không nhận db_path qua tham số) đều
    # giữ DB_PATH riêng — bỏ sót extensions sẽ khiến các log_audit() còn lại
    # (route đối soát, do audit cần biết số ảnh đã lưu SAU khi upload nên
    # chưa chuyển hết vào plan_service) âm thầm ghi vào DB THẬT thay vì DB
    # test — đã phát hiện thật lỗi này lúc verify (1 dòng audit_log rò rỉ
    # vào data/gia_heo_hoi.db, đã dọn bằng tay theo đúng id).
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

        response = client.post(
            "/api/plans",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 1,
                "expected_avg_weight_kg": 100.0,
                "shed": "TEST",
                "lot": "TEST",
                "note": "API_SERVICE_INTEGRATION_TEST",
            },
        )

        print("HTTP status =", response.status_code)
        print("Response =", response.get_json())

        if response.status_code != 201:
            raise RuntimeError(
                f"POST /api/plans thất bại: "
                f"{response.status_code} {response.get_data(as_text=True)}"
            )

        payload = response.get_json()

        plan_id = payload.get("id")
        if plan_id is None:
            raise RuntimeError("Response không có plan id.")

        # --- Duyệt ---
        r = client.post(f"/api/plans/{plan_id}/approve")
        if r.status_code != 200:
            raise RuntimeError(f"approve thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Ghi nhận thực nhận ---
        r = client.patch(f"/api/plans/{plan_id}/received", json={"received_quantity": 1})
        if r.status_code != 200:
            raise RuntimeError(f"received thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Sửa nội dung ---
        r = client.patch(
            f"/api/plans/{plan_id}/edit",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 1,
                "expected_avg_weight_kg": 100.0,
                "shed": "TEST",
                "lot": "TEST",
                "note": "API_SERVICE_INTEGRATION_TEST_EDITED",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"edit thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Vô hiệu hoá rồi kích hoạt lại ---
        r = client.patch(f"/api/plans/{plan_id}", json={"status": "disabled"})
        if r.status_code != 200:
            raise RuntimeError(f"disable thất bại: {r.status_code} {r.get_data(as_text=True)}")
        r = client.patch(f"/api/plans/{plan_id}", json={"status": "approved"})
        if r.status_code != 200:
            raise RuntimeError(f"re-enable thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Tạo kế hoạch thứ 2 để test Từ chối (cần status pending_approval) ---
        r2 = client.post(
            "/api/plans",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 1,
                "shed": "TEST2",
                "lot": "TEST2",
                "note": "API_SERVICE_INTEGRATION_TEST_2",
            },
        )
        if r2.status_code != 201:
            raise RuntimeError(f"POST /api/plans (2) thất bại: {r2.status_code} {r2.get_data(as_text=True)}")
        plan_id_2 = r2.get_json()["id"]

        r = client.post(f"/api/plans/{plan_id_2}/reject", json={"reason": "TEST_REJECT_REASON"})
        if r.status_code != 200:
            raise RuntimeError(f"reject thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá kế hoạch đầu tiên ---
        r = client.delete(f"/api/plans/{plan_id}")
        if r.status_code != 200:
            raise RuntimeError(f"delete thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Đối soát: tạo kế hoạch 3, duyệt, ghi nhận đối soát, xoá ---
        r3 = client.post(
            "/api/plans",
            json={
                "planned_date": "2099-12-31",
                "farm_id": farm_id,
                "zone_id": zone_id,
                "pig_type_id": pig_type_id,
                "quantity": 5,
                "shed": "TEST3",
                "lot": "TEST3",
                "note": "API_SERVICE_INTEGRATION_TEST_3",
            },
        )
        if r3.status_code != 201:
            raise RuntimeError(f"POST /api/plans (3) thất bại: {r3.status_code} {r3.get_data(as_text=True)}")
        plan_id_3 = r3.get_json()["id"]

        r = client.post(f"/api/plans/{plan_id_3}/approve")
        if r.status_code != 200:
            raise RuntimeError(f"approve (3) thất bại: {r.status_code} {r.get_data(as_text=True)}")

        r = client.post(
            f"/api/plans/{plan_id_3}/reconciliations",
            data={"kind": "transferred", "quantity": "5", "reason": "TEST_RECONCILE_REASON"},
        )
        if r.status_code != 201:
            raise RuntimeError(f"reconciliation create thất bại: {r.status_code} {r.get_data(as_text=True)}")
        reconciliation_id = r.get_json()["id"]

        r = client.get(f"/api/plans/{plan_id_3}/reconciliations")
        if r.status_code != 200:
            raise RuntimeError(f"reconciliation list thất bại: {r.status_code} {r.get_data(as_text=True)}")
        recon_list = r.get_json()
        if len(recon_list) != 1 or recon_list[0]["id"] != reconciliation_id:
            raise RuntimeError(f"reconciliation list không đúng: {recon_list}")

        r = client.delete(f"/api/reconciliations/{reconciliation_id}")
        if r.status_code != 200:
            raise RuntimeError(f"reconciliation delete thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    try:
        farm = conn.execute(
            "SELECT id FROM farms ORDER BY id LIMIT 1"
        ).fetchone()

        zone = conn.execute(
            "SELECT id FROM zones ORDER BY id LIMIT 1"
        ).fetchone()

        pig_type = conn.execute(
            "SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1"
        ).fetchone()

        if farm is None:
            raise RuntimeError("Không tìm thấy farm.")

        if zone is None:
            raise RuntimeError("Không tìm thấy zone.")

        if pig_type is None:
            raise RuntimeError("Không tìm thấy pig_type active.")

        farm_id = farm[0]
        zone_id = zone[0]
        pig_type_id = pig_type[0]

    finally:
        conn.close()

    conn = get_connection(test_db)

    # plan_id đã bị xoá ở bước cuối — phải KHÔNG còn tồn tại.
    plan1 = conn.execute("SELECT id FROM sale_plans WHERE id = ?", (plan_id,)).fetchone()

    plan2 = conn.execute(
        "SELECT id, status, rejected_reason, note FROM sale_plans WHERE id = ?",
        (plan_id_2,),
    ).fetchone()

    audit1_actions = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_plan' AND entity_id = ? ORDER BY id ASC",
            (plan_id,),
        ).fetchall()
    ]
    audit2_actions = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_plan' AND entity_id = ? ORDER BY id ASC",
            (plan_id_2,),
        ).fetchall()
    ]

    conn.close()

    print("Plan1 (sau khi xoá) =", plan1)
    print("Plan2 =", tuple(plan2) if plan2 else None)
    print("Audit plan1 =", audit1_actions)
    print("Audit plan2 =", audit2_actions)

    if plan1 is not None:
        raise RuntimeError("Kế hoạch 1 đáng lẽ đã bị xoá nhưng vẫn còn.")

    if plan2 is None:
        raise RuntimeError("Không tìm thấy kế hoạch 2.")
    if plan2[1] != "rejected":
        raise RuntimeError(f"Kế hoạch 2 đáng lẽ status='rejected', thực tế: {plan2[1]}")
    if plan2[2] != "TEST_REJECT_REASON":
        raise RuntimeError("rejected_reason không khớp.")

    expected1 = [
        "plan.create",
        "plan.approve",
        "plan.update_received",
        "plan.update_edit",
        "plan.update_status",
        "plan.update_status",
        "plan.delete",
    ]
    if audit1_actions != expected1:
        raise RuntimeError(f"Audit trail kế hoạch 1 không khớp: {audit1_actions} != {expected1}")

    expected2 = ["plan.create", "plan.reject"]
    if audit2_actions != expected2:
        raise RuntimeError(f"Audit trail kế hoạch 2 không khớp: {audit2_actions} != {expected2}")

    conn = get_connection(test_db)
    recon_row = conn.execute(
        "SELECT id FROM sale_plan_reconciliations WHERE id = ?", (reconciliation_id,)
    ).fetchone()
    audit3_actions = [
        row[0]
        for row in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'sale_plan' AND entity_id = ? ORDER BY id ASC",
            (plan_id_3,),
        ).fetchall()
    ]
    conn.close()

    print("Reconciliation (sau khi xoá) =", recon_row)
    print("Audit plan3 =", audit3_actions)

    if recon_row is not None:
        raise RuntimeError("Bản ghi đối soát đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected3 = ["plan.create", "plan.approve", "plan.reconcile_create", "plan.reconcile_delete"]
    if audit3_actions != expected3:
        raise RuntimeError(f"Audit trail kế hoạch 3 không khớp: {audit3_actions} != {expected3}")

    print("API PLAN INTEGRATION TEST = PASS")
