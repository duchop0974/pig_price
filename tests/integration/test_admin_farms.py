"""Migrate từ test_api_admin_farms_tmp.py (đã xoá) — verify farm_service.py
qua HTTP thật (routes/admin.py, phần Farms+Zones)."""


def test_admin_farm_and_zone_lifecycle(admin_client, db_connection, audit_actions):
    r = admin_client.post("/api/admin/farms", json={"code": "TEST_FARM", "province": "Test Province"})
    assert r.status_code == 201, f"tạo trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}"
    farms = r.get_json()
    farm = next((f for f in farms if f["code"] == "TEST_FARM"), None)
    assert farm is not None, f"Không tìm thấy trang trại vừa tạo trong response: {farms}"
    farm_id = farm["id"]

    r = admin_client.patch(
        f"/api/admin/farms/{farm_id}", json={"code": "TEST_FARM_EDITED", "province": "Edited Province"}
    )
    assert r.status_code == 200, f"sửa trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.post("/api/admin/zones", json={"farm_id": farm_id, "code": "TEST_ZONE"})
    assert r.status_code == 201, f"tạo khu thất bại: {r.status_code} {r.get_data(as_text=True)}"
    zones = r.get_json()
    zone = next((z for z in zones if z["code"] == "TEST_ZONE"), None)
    assert zone is not None, f"Không tìm thấy khu vừa tạo trong response: {zones}"
    zone_id = zone["id"]

    r = admin_client.patch(f"/api/admin/zones/{zone_id}", json={"code": "TEST_ZONE_EDITED"})
    assert r.status_code == 200, f"sửa khu thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/admin/zones/{zone_id}")
    assert r.status_code == 200, f"xoá khu thất bại: {r.status_code} {r.get_data(as_text=True)}"

    r = admin_client.delete(f"/api/admin/farms/{farm_id}")
    assert r.status_code == 200, f"xoá trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}"

    farm_row = db_connection.execute("SELECT code FROM farms WHERE id = ?", (farm_id,)).fetchone()
    zone_row = db_connection.execute("SELECT code FROM zones WHERE id = ?", (zone_id,)).fetchone()
    assert farm_row is None, "Trang trại đáng lẽ đã bị xoá nhưng vẫn còn."
    assert zone_row is None, "Khu đáng lẽ đã bị xoá nhưng vẫn còn."

    farm_actions = audit_actions("farm", farm_id)
    zone_actions = audit_actions("zone", zone_id)
    assert farm_actions == ["farm.create", "farm.update", "farm.delete"], f"Audit trail farm không khớp: {farm_actions}"
    assert zone_actions == ["zone.create", "zone.update", "zone.delete"], f"Audit trail zone không khớp: {zone_actions}"
