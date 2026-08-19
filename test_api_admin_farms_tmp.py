"""Integration test cho farm_service.py (routes/admin.py, phần Farms+Zones)
— khuôn 1:1 các test_api_*_tmp.py khác. routes.admin import DB_PATH ở top
level, phải patch riêng giống test_api_admin_users_tmp.py."""
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


SOURCE_DB = Path("data/gia_heo_hoi.db")


with tempfile.TemporaryDirectory() as tmp:
    test_db = Path(tmp) / "api_admin_farms_test.db"
    shutil.copy2(SOURCE_DB, test_db)

    admin_route.DB_PATH = test_db
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

        # --- Tạo trang trại ---
        r = client.post("/api/admin/farms", json={"code": "TEST_FARM", "province": "Test Province"})
        if r.status_code != 201:
            raise RuntimeError(f"tạo trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}")
        farms = r.get_json()
        farm = next((f for f in farms if f["code"] == "TEST_FARM"), None)
        if farm is None:
            raise RuntimeError(f"Không tìm thấy trang trại vừa tạo trong response: {farms}")
        farm_id = farm["id"]

        # --- Sửa trang trại ---
        r = client.patch(f"/api/admin/farms/{farm_id}", json={"code": "TEST_FARM_EDITED", "province": "Edited Province"})
        if r.status_code != 200:
            raise RuntimeError(f"sửa trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Tạo khu ---
        r = client.post("/api/admin/zones", json={"farm_id": farm_id, "code": "TEST_ZONE"})
        if r.status_code != 201:
            raise RuntimeError(f"tạo khu thất bại: {r.status_code} {r.get_data(as_text=True)}")
        zones = r.get_json()
        zone = next((z for z in zones if z["code"] == "TEST_ZONE"), None)
        if zone is None:
            raise RuntimeError(f"Không tìm thấy khu vừa tạo trong response: {zones}")
        zone_id = zone["id"]

        # --- Sửa khu ---
        r = client.patch(f"/api/admin/zones/{zone_id}", json={"code": "TEST_ZONE_EDITED"})
        if r.status_code != 200:
            raise RuntimeError(f"sửa khu thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá khu ---
        r = client.delete(f"/api/admin/zones/{zone_id}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá khu thất bại: {r.status_code} {r.get_data(as_text=True)}")

        # --- Xoá trang trại ---
        r = client.delete(f"/api/admin/farms/{farm_id}")
        if r.status_code != 200:
            raise RuntimeError(f"xoá trang trại thất bại: {r.status_code} {r.get_data(as_text=True)}")

    conn = get_connection(test_db)
    farm_row = conn.execute("SELECT code FROM farms WHERE id = ?", (farm_id,)).fetchone()
    zone_row = conn.execute("SELECT code FROM zones WHERE id = ?", (zone_id,)).fetchone()
    farm_audit = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'farm' AND entity_id = ? ORDER BY id ASC",
            (farm_id,),
        ).fetchall()
    ]
    zone_audit = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'zone' AND entity_id = ? ORDER BY id ASC",
            (zone_id,),
        ).fetchall()
    ]
    conn.close()

    print("Farm (sau khi xoá) =", farm_row)
    print("Zone (sau khi xoá) =", zone_row)
    print("Audit farm =", farm_audit)
    print("Audit zone =", zone_audit)

    if farm_row is not None:
        raise RuntimeError("Trang trại đáng lẽ đã bị xoá nhưng vẫn còn.")
    if zone_row is not None:
        raise RuntimeError("Khu đáng lẽ đã bị xoá nhưng vẫn còn.")

    expected_farm = ["farm.create", "farm.update", "farm.delete"]
    expected_zone = ["zone.create", "zone.update", "zone.delete"]
    if farm_audit != expected_farm:
        raise RuntimeError(f"Audit trail trang trại không khớp: {farm_audit} != {expected_farm}")
    if zone_audit != expected_zone:
        raise RuntimeError(f"Audit trail khu không khớp: {zone_audit} != {expected_zone}")

    print("API ADMIN FARMS/ZONES INTEGRATION TEST = PASS")
