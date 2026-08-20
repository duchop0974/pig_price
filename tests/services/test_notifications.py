"""Unit test cho hộp thư Thông báo (Phase 5, brief nghiệp vụ):
- notification_service.notify() gọi trực tiếp trên 1 transaction thật (đúng
  cách nó luôn được gọi trong service layer) — xác nhận KHÔNG deadlock (bug
  thật gặp lúc build: mở connection mới bên trong transaction đang mở gây
  treo >120s, xem docstring notification_service.py) và lọc đúng quyền/farm.
- 2 test wiring qua route thật (tạo kế hoạch → thông báo PLAN_REVIEW; duyệt
  kế hoạch → thông báo người tạo) để xác nhận các điểm gắn (Phase 5) hoạt
  động end-to-end, không chỉ đúng ở tầng service đơn lẻ."""
from core import permissions as perm
from core.db import run_in_transaction
from core.repositories import notifications_repo, roles_repo, users_repo
from core.services import notification_service


def test_notify_reaches_users_with_permission_excludes_actor_and_inactive(test_db):
    users_repo.create_user("notify_recipient", "pw12345", test_db, role="sales")
    users_repo.create_user("notify_no_perm", "pw12345", test_db, role="accounting")
    inactive_id = users_repo.create_user("notify_inactive", "pw12345", test_db, role="sales")
    users_repo.set_user_active(inactive_id, False, test_db)
    roles_repo.set_permissions_for_role("sales", [perm.PLAN_REVIEW], test_db)
    roles_repo.set_permissions_for_role("accounting", [], test_db)

    def _do(conn):
        notification_service.notify(
            perm.PLAN_REVIEW, "Test title", "Test body", "/somewhere", test_db,
            exclude_username="notify_recipient_actor", conn=conn,
        )

    run_in_transaction(test_db, _do)

    recipient_notes = notifications_repo.list_for_user("notify_recipient", test_db)
    assert len(recipient_notes) == 1
    assert recipient_notes[0]["title"] == "Test title"
    assert recipient_notes[0]["is_read"] == 0

    assert notifications_repo.list_for_user("notify_no_perm", test_db) == []
    assert notifications_repo.list_for_user("notify_inactive", test_db) == []


def test_notify_farm_scoped_only_reaches_assigned_farm_role_user(test_db, ref_ids):
    other_farm_user_id = users_repo.create_user("notify_farm_other", "pw12345", test_db, role="farm")
    same_farm_user_id = users_repo.create_user("notify_farm_same", "pw12345", test_db, role="farm")
    users_repo.assign_user_farms(same_farm_user_id, [ref_ids["farm_id"]], test_db)
    roles_repo.set_permissions_for_role("farm", ["plans.create", "plans.receive", perm.DELIVERY_CREATE], test_db)

    def _do(conn):
        notification_service.notify(
            perm.DELIVERY_CREATE, "Farm scoped", None, "/xuat-giao", test_db,
            farm_id=ref_ids["farm_id"], conn=conn,
        )

    run_in_transaction(test_db, _do)

    assert len(notifications_repo.list_for_user("notify_farm_same", test_db)) == 1
    assert notifications_repo.list_for_user("notify_farm_other", test_db) == []


def test_create_plan_notifies_users_with_plan_review_permission(test_db, ref_ids, admin_client):
    users_repo.create_user("notify_sales_reviewer", "pw12345", test_db, role="sales")
    roles_repo.set_permissions_for_role("sales", [perm.PLAN_REVIEW], test_db)

    admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 7,
            "shed": "N1",
            "lot": "L1",
        },
    )

    notes = notifications_repo.list_for_user("notify_sales_reviewer", test_db)
    assert any(n["title"] == "Kế hoạch trại mới chờ duyệt" for n in notes)
    # Người tạo (admin_client, username="integration_test") không tự báo cho mình.
    assert notifications_repo.list_for_user("integration_test", test_db) == []


def test_approve_plan_notifies_creator(test_db, ref_ids, admin_client):
    r = admin_client.post(
        "/api/plans",
        json={
            "planned_date": "2099-12-31",
            "farm_id": ref_ids["farm_id"],
            "zone_id": ref_ids["zone_id"],
            "pig_type_id": ref_ids["pig_type_id"],
            "quantity": 3,
            "shed": "N2",
            "lot": "L2",
        },
    )
    plan_id = r.get_json()["id"]
    admin_client.post(f"/api/plans/{plan_id}/approve")

    notes = notifications_repo.list_for_user("integration_test", test_db)
    assert any(n["title"] == "Kế hoạch trại đã được duyệt" for n in notes)
