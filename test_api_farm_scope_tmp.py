"""Verify STEP 3 (Authorization + Data Scope): 6 route ghi trên sale_plans/
reconciliation/delivery phải chặn tài khoản vai trò 'farm' thao tác trên
trại KHÔNG được gán, kể cả khi role 'farm' được admin lỡ cấp thêm quyền
review/delete/reconcile_delete/delivery_delete qua /admin/permissions.

Khuôn 1:1 các test_api_*_tmp.py khác — copy DB thật ra bản tạm, patch
DB_PATH trên mọi module import nó ở top level."""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("webapp").resolve()))

from app_factory import create_app
from core.db import get_connection
import data_access
import extensions
import routes.admin as admin_route
import routes.auth as auth_route
import routes.deliveries as deliveries_route
import routes.plans as plans_route


SOURCE_DB = Path("data/gia_heo_hoi.db")

ADMIN_SESSION = {"id": 999999, "username": "integration_test", "display_name": "Integration Test", "role": "admin"}


def as_admin(client):
    with client.session_transaction() as sess:
        sess["user"] = dict(ADMIN_SESSION)


def as_user(client, user):
    with client.session_transaction() as sess:
        sess["user"] = user


with tempfile.TemporaryDirectory() as tmp:
    test_db = Path(tmp) / "api_farm_scope_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    conn = get_connection(test_db)
    farm_a = conn.execute("SELECT id FROM farms ORDER BY id LIMIT 1").fetchone()[0]
    farm_b = conn.execute("SELECT id FROM farms WHERE id != ? ORDER BY id LIMIT 1", (farm_a,)).fetchone()[0]
    zone_b = conn.execute("SELECT id FROM zones WHERE farm_id = ? ORDER BY id LIMIT 1", (farm_b,)).fetchone()[0]
    pig_type_id = conn.execute("SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1").fetchone()[0]
    conn.close()

    admin_route.DB_PATH = test_db
    auth_route.DB_PATH = test_db
    deliveries_route.DB_PATH = test_db
    plans_route.DB_PATH = test_db
    data_access.DB_PATH = test_db
    extensions.DB_PATH = test_db

    app = create_app()
    app.config["TESTING"] = True

    def make_plan(client, note):
        r = client.post(
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
        if r.status_code != 201:
            raise RuntimeError(f"tạo kế hoạch nguồn ({note}) thất bại: {r.status_code} {r.get_data(as_text=True)}")
        return r.get_json()["id"]

    with app.test_client() as client:
        as_admin(client)

        # --- Cấp thêm 4 quyền review/delete/reconcile_delete/delivery_delete
        # cho role 'farm' (mô phỏng đúng tình huống admin cấu hình sai qua
        # /admin/permissions) — giữ lại 2 quyền mặc định plans.create/receive.
        r = client.patch(
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
        if r.status_code != 200:
            raise RuntimeError(f"cấp quyền role farm thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Tạo 2 tài khoản vai trò farm: wrong (gán farm A) và right (gán farm B) ---
        def make_farm_user(username, farm_id):
            r = client.post(
                "/api/admin/users",
                json={"username": username, "password": "password123", "display_name": username, "role": "farm"},
            )
            if r.status_code != 201:
                raise RuntimeError(f"tạo user {username} thất bại: {r.status_code} {r.get_data(as_text=True)}")
            users = r.get_json()
            user = next(u for u in users if u["username"] == username)
            r = client.patch(f"/api/admin/users/{user['id']}/farms", json={"farm_ids": [farm_id]})
            if r.status_code != 200:
                raise RuntimeError(f"gán trại cho {username} thất bại: {r.status_code} {r.get_data(as_text=True)}")
            return {"id": user["id"], "username": username, "display_name": username, "role": "farm"}

        user_wrong = make_farm_user("test_fs_wrong", farm_a)
        user_right = make_farm_user("test_fs_right", farm_b)

        # --- Tạo dữ liệu nguồn (5 kế hoạch, đều thuộc farm B) làm admin ---
        plan_approve = make_plan(client, "FS_APPROVE")
        plan_reject = make_plan(client, "FS_REJECT")
        plan_update = make_plan(client, "FS_UPDATE")
        plan_delete = make_plan(client, "FS_DELETE")
        plan_reconcile = make_plan(client, "FS_RECONCILE")
        plan_delivery = make_plan(client, "FS_DELIVERY")

        r = client.post(f"/api/plans/{plan_update}/approve")
        if r.status_code != 200:
            raise RuntimeError("duyệt plan_update thất bại")

        r = client.post(f"/api/plans/{plan_reconcile}/approve")
        if r.status_code != 200:
            raise RuntimeError("duyệt plan_reconcile thất bại")
        r = client.patch(f"/api/plans/{plan_reconcile}/received", json={"received_quantity": 20})
        if r.status_code != 200:
            raise RuntimeError("ghi nhận thực nhận plan_reconcile thất bại")
        r = client.post(
            f"/api/plans/{plan_reconcile}/reconciliations",
            data={"kind": "still_at_farm", "reason": "TEST_FS", "quantity": "5"},
            content_type="multipart/form-data",
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo đối soát plan_reconcile thất bại: {r.status_code} {r.get_data(as_text=True)}")
        reconciliation_id = r.get_json()["id"]

        r = client.post(f"/api/plans/{plan_delivery}/approve")
        if r.status_code != 200:
            raise RuntimeError("duyệt plan_delivery thất bại")
        r = client.post("/api/orders", json={"lines": [{"sale_plan_id": plan_delivery, "quantity": 10, "selling_price": 65000}]})
        if r.status_code != 201:
            raise RuntimeError(f"tạo đơn cho plan_delivery thất bại: {r.status_code} {r.get_data(as_text=True)}")
        order = r.get_json()
        order_id, line_id = order["id"], order["lines"][0]["id"]
        r = client.post(
            f"/api/orders/{order_id}/lines/{line_id}/deliveries",
            json={"pig_type_id": pig_type_id, "quantity": 5, "delivered_date": "2099-12-20"},
        )
        if r.status_code != 201:
            raise RuntimeError(f"tạo delivery cho plan_delivery thất bại: {r.status_code} {r.get_data(as_text=True)}")
        delivery_id = r.get_json()["id"]

        # --- Với user SAI trại (farm A) — cả 6 hành động phải bị 403 ---
        as_user(client, user_wrong)
        checks_403 = [
            ("approve", client.post(f"/api/plans/{plan_approve}/approve")),
            ("reject", client.post(f"/api/plans/{plan_reject}/reject", json={"reason": "test"})),
            ("update", client.patch(f"/api/plans/{plan_update}", json={"status": "cancelled"})),
            ("delete", client.delete(f"/api/plans/{plan_delete}")),
            ("reconcile_delete", client.delete(f"/api/reconciliations/{reconciliation_id}")),
            ("delivery_delete", client.delete(f"/api/deliveries/{delivery_id}")),
        ]
        PERMISSION_DENIED_MSG = "Bạn không có quyền thực hiện thao tác này."
        failures = [
            (name, r.status_code, r.get_data(as_text=True))
            for name, r in checks_403
            if r.status_code != 403 or PERMISSION_DENIED_MSG in r.get_data(as_text=True)
        ]
        if failures:
            raise RuntimeError(f"Kỳ vọng 403 farm-scope (không phải 403 thiếu quyền) cho user sai trại: {failures}")
        print("User SAI trại (farm A) -> cả 6 hành động đều bị 403: PASS")

        # --- Với user ĐÚNG trại (farm B) — cả 6 hành động phải thành công ---
        as_user(client, user_right)
        checks_ok = [
            ("approve", client.post(f"/api/plans/{plan_approve}/approve"), 200),
            ("reject", client.post(f"/api/plans/{plan_reject}/reject", json={"reason": "test"}), 200),
            ("update", client.patch(f"/api/plans/{plan_update}", json={"status": "cancelled"}), 200),
            ("delete", client.delete(f"/api/plans/{plan_delete}"), 200),
            ("reconcile_delete", client.delete(f"/api/reconciliations/{reconciliation_id}"), 200),
            ("delivery_delete", client.delete(f"/api/deliveries/{delivery_id}"), 200),
        ]
        failures = [(name, r.status_code, r.get_data(as_text=True)) for name, r, expect in checks_ok if r.status_code != expect]
        if failures:
            raise RuntimeError(f"Kỳ vọng thành công cho user đúng trại nhưng không đúng: {failures}")
        print("User ĐÚNG trại (farm B) -> cả 6 hành động đều thành công: PASS")

    print("API FARM SCOPE INTEGRATION TEST = PASS")
