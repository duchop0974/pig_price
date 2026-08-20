"""Fixture dùng chung cho toàn bộ tests/ — gộp khuôn đã lặp lại 9 lần ở
các script test_api_*_tmp.py cũ (đã xoá, xem lịch sử git): copy DB thật
ra bản tạm, patch DB_PATH trên mọi module giữ biến riêng (routes.admin/
routes.auth/routes.deliveries/routes.plans/data_access/extensions — bài
học thật từ lúc viết các script cũ: bỏ sót 1 module sẽ khiến ghi/audit
âm thầm chạy vào DB THẬT thay vì DB test), tạo Flask app + test client
với session admin sẵn."""
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBAPP_DIR = REPO_ROOT / "webapp"
for path in (str(REPO_ROOT), str(WEBAPP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

SOURCE_DB = REPO_ROOT / "data" / "gia_heo_hoi.db"

import data_access  # noqa: E402
import extensions  # noqa: E402
import routes.admin as admin_route  # noqa: E402
import routes.auth as auth_route  # noqa: E402
import routes.deliveries as deliveries_route  # noqa: E402
import routes.plans as plans_route  # noqa: E402
from app_factory import create_app  # noqa: E402
from core.db import get_connection  # noqa: E402

ADMIN_SESSION_USER = {
    "id": 999999,
    "username": "integration_test",
    "display_name": "Integration Test",
    "role": "admin",
}

_DB_PATH_MODULES = (admin_route, auth_route, deliveries_route, plans_route, data_access, extensions)


@pytest.fixture()
def test_db(tmp_path) -> Path:
    db_path = tmp_path / "test.db"
    shutil.copy2(SOURCE_DB, db_path)
    return db_path


@pytest.fixture()
def app(test_db, monkeypatch):
    for module in _DB_PATH_MODULES:
        monkeypatch.setattr(module, "DB_PATH", test_db)

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

    # extensions.limiter là singleton cấp module — dùng chung mọi lần gọi
    # create_app() trong CÙNG process. pytest chạy nhiều test trong 1
    # process nên phải reset counter mỗi lần, không thì rate-limit /login
    # (STEP 5) cộng dồn qua các test khác nhau, có thể làm 1 test đăng
    # nhập thật bị 429 oan vì IP giả (127.0.0.1) của Flask test client
    # giống nhau ở mọi test.
    extensions.limiter.reset()

    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    """Client đã có sẵn session role admin — dùng cho phần lớn test vì
    hầu hết chỉ cần verify hành vi ghi/audit, không phải verify RBAC
    (RBAC/farm-scope có test riêng ở tests/security/)."""
    with client.session_transaction() as sess:
        sess["user"] = dict(ADMIN_SESSION_USER)
    return client


@pytest.fixture()
def login_as():
    """Trả về closure `(client, user) -> None` đổi session sang user khác
    — dùng cho test cần nhiều vai trò trong cùng 1 test function (VD
    tests/security/test_farm_scope.py). Fixture-trả-callable, cùng lý do
    với `audit_actions` ở trên."""

    def _login(client, user: dict) -> None:
        with client.session_transaction() as sess:
            sess["user"] = user

    return _login


@pytest.fixture()
def db_connection(test_db):
    conn = get_connection(test_db)
    yield conn
    conn.close()


@pytest.fixture()
def ref_ids(test_db):
    """1 farm/zone/pig_type có sẵn trong DB thật (copy qua test_db) —
    dùng làm dữ liệu tham chiếu hợp lệ cho các test tạo kế hoạch/đơn
    hàng/xuất giao, khớp đúng cách 9 script cũ tự query trước khi test."""
    conn = get_connection(test_db)
    try:
        farm = conn.execute("SELECT id FROM farms ORDER BY id LIMIT 1").fetchone()
        zone = conn.execute("SELECT id FROM zones ORDER BY id LIMIT 1").fetchone()
        pig_type = conn.execute("SELECT id FROM pig_types WHERE is_active = 1 ORDER BY id LIMIT 1").fetchone()
    finally:
        conn.close()
    assert farm and zone and pig_type, "Thiếu dữ liệu tham chiếu (farm/zone/pig_type) trong DB thật để test."
    return {"farm_id": farm[0], "zone_id": zone[0], "pig_type_id": pig_type[0]}


@pytest.fixture()
def audit_actions(db_connection):
    """Trả về closure `(entity_type, entity_id) -> list[str]` đọc
    audit_log theo thứ tự thời gian — dùng fixture-trả-callable thay vì
    hàm module-level để tránh phải import xuyên thư mục con
    (tests/integration/, tests/security/) không ổn định dưới cơ chế
    rootless collection mặc định của pytest. `entity_id` giữ nguyên type
    gốc (int cho plan/order/user/..., str cho role key) — so sánh khác
    SQLite storage class (INTEGER vs TEXT) sẽ không khớp nếu ép kiểu sai."""

    def _read(entity_type: str, entity_id) -> list[str]:
        rows = db_connection.execute(
            "SELECT action FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id ASC",
            (entity_type, entity_id),
        ).fetchall()
        return [row[0] for row in rows]

    return _read
