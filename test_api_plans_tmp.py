import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("webapp").resolve()))

from app_factory import create_app
from core.db import get_connection
import data_access
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

    # Route và data_access đang giữ DB_PATH riêng.
    # Patch cả hai để toàn bộ request sử dụng DB test.
    plans_route.DB_PATH = test_db
    data_access.DB_PATH = test_db

    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 999999,
                "username": "integration_test",
                "display_name": "Integration Test",
                "role": "sales",
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
    plan = conn.execute(
        """
        SELECT
            id,
            plan_code,
            planned_date,
            farm_id,
            pig_type_id,
            quantity,
            status,
            note
        FROM sale_plans
        WHERE id = ?
        """,
        (plan_id,),
    ).fetchone()

    audit = conn.execute(
        """
        SELECT
            action,
            entity_type,
            entity_id
        FROM audit_log
        WHERE entity_type = 'sale_plan'
          AND entity_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (plan_id,),
    ).fetchone()

    conn.close()

    print("Plan =", tuple(plan) if plan else None)
    print("Audit =", tuple(audit) if audit else None)

    if plan is None:
        raise RuntimeError("Không tìm thấy sale_plan.")

    if audit is None:
        raise RuntimeError("Không tìm thấy audit_log.")

    if audit[1] != "sale_plan":
        raise RuntimeError("audit entity_type không đúng.")

    if str(audit[2]) != str(plan_id):
        raise RuntimeError("audit entity_id không khớp.")

    print("API PLAN INTEGRATION TEST = PASS")
