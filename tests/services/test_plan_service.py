"""Unit test THẬT cho plan_service.py — gọi thẳng plan_service.create_plan()
KHÔNG qua Flask/HTTP, minh chứng cụ thể cho mục tiêu STEP 7 (Route
Refactor): validate input giờ sống trong service, test được độc lập với
web layer. Khác hẳn tests/integration/ (đi qua Flask test client)."""
import pytest

from core.services import plan_service


def _valid_payload(ref_ids, **overrides):
    payload = {
        "planned_date": "2099-12-31",
        "farm_id": ref_ids["farm_id"],
        "zone_id": ref_ids["zone_id"],
        "pig_type_id": ref_ids["pig_type_id"],
        "quantity": 10,
        "shed": "A1",
        "lot": "L1",
        "note": "unit test",
    }
    payload.update(overrides)
    return payload


def test_create_plan_valid_input_succeeds(test_db, ref_ids):
    plan_id = plan_service.create_plan(
        _valid_payload(ref_ids), test_db, ip="127.0.0.1", username="unit_test"
    )
    assert isinstance(plan_id, int) and plan_id > 0


def test_create_plan_missing_farm_id_raises(test_db, ref_ids):
    payload = _valid_payload(ref_ids)
    del payload["farm_id"]
    with pytest.raises(ValueError, match="Vui lòng chọn trang trại"):
        plan_service.create_plan(payload, test_db)


@pytest.mark.parametrize("quantity", [0, -5, "abc", None])
def test_create_plan_invalid_quantity_raises(test_db, ref_ids, quantity):
    payload = _valid_payload(ref_ids, quantity=quantity)
    with pytest.raises(ValueError, match="Số lượng không hợp lệ"):
        plan_service.create_plan(payload, test_db)


def test_create_plan_nonexistent_pig_type_raises(test_db, ref_ids):
    payload = _valid_payload(ref_ids, pig_type_id=999999)
    with pytest.raises(ValueError, match="Loại heo không hợp lệ"):
        plan_service.create_plan(payload, test_db)


def test_create_plan_invalid_date_raises(test_db, ref_ids):
    payload = _valid_payload(ref_ids, planned_date="not-a-date")
    with pytest.raises(ValueError, match="Ngày dự kiến không hợp lệ"):
        plan_service.create_plan(payload, test_db)


def test_create_plan_shed_too_long_raises(test_db, ref_ids):
    payload = _valid_payload(ref_ids, shed="X" * 51)
    with pytest.raises(ValueError, match="Tên chuồng quá dài"):
        plan_service.create_plan(payload, test_db)


def test_create_plan_invalid_expected_weight_raises(test_db, ref_ids):
    payload = _valid_payload(ref_ids, expected_avg_weight_kg=-1)
    with pytest.raises(ValueError, match="Trọng lượng dự kiến"):
        plan_service.create_plan(payload, test_db)
