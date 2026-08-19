"""Kết nối SQLite dùng chung, schema + migration nhẹ (thêm cột/bảng nếu chưa có)."""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core import permissions as perm

DB_COLUMNS = [
    "date",
    "source",
    "region",
    "province",
    "price_vnd_per_kg",
    "change_vnd_per_kg",
    "benchmark_price_vnd_per_kg",
    "source_url",
]

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    region TEXT,
    province TEXT NOT NULL,
    price_vnd_per_kg INTEGER,
    change_vnd_per_kg INTEGER,
    benchmark_price_vnd_per_kg INTEGER,
    source_url TEXT,
    PRIMARY KEY (date, source, province)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_prices_source ON prices(source);
CREATE INDEX IF NOT EXISTS idx_prices_province ON prices(province);

CREATE TABLE IF NOT EXISTS farms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    -- Tỉnh/thành trại đặt tại đó — dùng để so giá đúng vùng thay vì bình
    -- quân cả nước khi tính "đã đạt giá mong muốn" cho kế hoạch xuất bán.
    -- Có thể để trống với trại tạo trước khi có trường này.
    province TEXT,
    created_at TEXT NOT NULL
);
-- Seed 3 trại mặc định chỉ chạy 1 lần trong _migrate() khi bảng còn trống,
-- không đặt ở đây: script này executescript() lại ở MỌI lần mở kết nối, và
-- INSERT OR IGNORE dù bị bỏ qua vẫn ngốn số AUTOINCREMENT mỗi lần chạy —
-- để đây sẽ làm id trại tăng vọt vô ích sau vài trăm request.

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (farm_id, code)
);
-- Index tạo trong _migrate(), không đặt ở đây: trên DB nâng cấp từ bản cũ,
-- executescript() này chạy trước _migrate() nên cột farm_id có thể chưa
-- tồn tại lúc câu CREATE INDEX chạy (bảng zones cũ vẫn còn cột farm).

-- Danh mục loại heo bán (VD: heo thịt, heo giống...) — chỉ admin được thêm
-- (xem routes/admin.py). Khoá mềm bằng is_active thay vì xoá để không phá
-- vỡ tham chiếu từ các kế hoạch xuất bán cũ đã dùng loại heo đó.
CREATE TABLE IF NOT EXISTS pig_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Danh mục khách hàng mua heo — sales/admin quản lý (không chỉ admin, vì
-- sales trực tiếp thêm/sửa khi liên hệ khách). tax_code để trống được,
-- phục vụ lập hoá đơn ở Giai đoạn 3. Khoá mềm bằng is_active như pig_types.
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    tax_code TEXT,
    note TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Gán trại phụ trách cho tài khoản vai trò 'farm' — nhiều-nhiều vì 1 người có
-- thể phụ trách nhiều trại. Vai trò khác (sales/accounting/admin) không cần
-- dòng nào ở đây: "không giới hạn trại" được xử lý ở tầng ứng dụng theo role,
-- không phải bằng cách insert đủ mọi trại vào bảng này.
CREATE TABLE IF NOT EXISTS user_farms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    created_at TEXT NOT NULL,
    UNIQUE (user_id, farm_id)
);
CREATE INDEX IF NOT EXISTS idx_user_farms_user_id ON user_farms(user_id);
CREATE INDEX IF NOT EXISTS idx_user_farms_farm_id ON user_farms(farm_id);

CREATE TABLE IF NOT EXISTS sale_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Mã kế hoạch tự sinh khi tạo, dạng <mã trại>-<ngày dự kiến>-<số thứ tự
    -- trong ngày của trại đó>, VD: XH1-20260820-01 — dùng để tham chiếu/trao
    -- đổi thay vì dùng id nội bộ. Có thể NULL với kế hoạch tạo trước khi có
    -- trường này (không hồi tố).
    plan_code TEXT,
    planned_date TEXT NOT NULL,
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    zone_id INTEGER REFERENCES zones(id),
    shed TEXT,
    lot TEXT,
    pig_type_id INTEGER NOT NULL REFERENCES pig_types(id),
    quantity INTEGER NOT NULL,
    -- Số lượng thực tế trại đã xuất chuồng/bàn giao ra nhà chờ bán (BM01/QT001
    -- bước B6) — thuần đối chiếu, KHÔNG dùng để tính số lượng còn lại cho
    -- phép phân bổ (phòng bán chốt khách trước khi trại thực xuất chuồng).
    received_quantity INTEGER,
    received_at TEXT,
    received_by TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending_approval',
    -- Các trường ẩn dưới đây không hiện trên form/thẻ kế hoạch, chỉ dùng để
    -- truy vết khi cần đối soát (ai/khi nào tạo & sửa kế hoạch).
    created_at TEXT NOT NULL,
    created_ip TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_plans_status ON sale_plans(status);
CREATE INDEX IF NOT EXISTS idx_sale_plans_planned_date ON sale_plans(planned_date);
-- Index UNIQUE cho plan_code tạo trong _migrate(), không đặt ở đây — cùng lý
-- do với idx_zones_farm_id: trên DB nâng cấp, cột plan_code có thể chưa tồn
-- tại lúc executescript() này chạy (trước _migrate()).

-- Đơn hàng (Giai đoạn 8) — header của "kế hoạch bán": 1 đơn cho 1 khách hàng
-- có thể gồm NHIỀU dòng heo (nhiều loại/nhiều kế hoạch trại khác nhau, xem
-- sale_allocations bên dưới giờ là dòng hàng của đơn). Mọi trường "1 lần cho
-- cả đơn" (khách hàng, liên hệ, chốt bán, giao nhận, thanh toán, doanh thu,
-- hoá đơn) đặt ở đây, không lặp lại trên từng dòng.
CREATE TABLE IF NOT EXISTS sale_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT,
    customer_id INTEGER REFERENCES customers(id),
    contacted_by TEXT,
    contacted_at TEXT,
    contact_note TEXT,
    confirmed_sale_at TEXT,
    delivery_time TEXT,
    payment_method TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    paid_amount INTEGER,
    paid_at TEXT,
    weighing_ref TEXT,
    revenue_recorded_by TEXT,
    revenue_recorded_at TEXT,
    invoice_number TEXT,
    invoiced_by TEXT,
    invoiced_at TEXT,
    locked_at TEXT,
    locked_by TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_orders_status ON sale_orders(status);
CREATE INDEX IF NOT EXISTS idx_sale_orders_customer_id ON sale_orders(customer_id);
-- Index UNIQUE cho order_code tạo trong _migrate() (cùng lý do idx_sale_plans_plan_code
-- — bảng có thể được backfill từ dữ liệu cũ nên tạo sau khi chắc chắn hợp lệ).

-- Kế hoạch bán / dòng hàng (BM02) — do Phòng bán hàng tạo, "nhặt" một phần/
-- toàn bộ số lượng từ MỘT kế hoạch trại (sale_plans) đã duyệt, gán giá chào
-- bán. 1 kế hoạch trại có thể sinh nhiều dòng hàng (chia nhỏ lô); nhiều dòng
-- hàng (khác kế hoạch trại/loại heo) gộp chung 1 đơn (order_id -> sale_orders)
-- cho cùng 1 khách hàng. pig_type_id KHÔNG lặp lại ở đây — lấy qua JOIN
-- sale_plan_id (dòng hàng chỉ nhặt đúng loại heo trại đã đăng ký).
CREATE TABLE IF NOT EXISTS sale_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_code TEXT,
    order_id INTEGER NOT NULL REFERENCES sale_orders(id),
    sale_plan_id INTEGER NOT NULL REFERENCES sale_plans(id),
    quantity INTEGER NOT NULL,
    selling_price INTEGER,
    note TEXT,
    actual_price INTEGER,
    actual_quantity INTEGER,
    locked_at TEXT,
    locked_by TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_allocations_sale_plan_id ON sale_allocations(sale_plan_id);
-- idx_sale_allocations_order_id + UNIQUE plan_code tạo trong _migrate() (cùng
-- lý do idx_sale_plans_plan_code — order_id là cột MỚI, trên DB nâng cấp từ
-- bản chưa tách, executescript() này chạy TRƯỚC _migrate() nên cột/bảng lúc
-- đó có thể chưa hợp lệ để lập index).

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Vai trò tuỳ biến (thay cho 5 role cố định hardcode trong code trước đây).
-- is_system=1 đánh dấu 5 role gốc (farm/sales/accounting/admin/leadership) —
-- không xoá được vì code còn tham chiếu literal 'admin' (superuser hardcode,
-- xem core/repositories/roles_repo.py) và 'farm' (allowed_farm_ids() trong
-- routes/auth.py). Quyền của các role này (kể cả is_system) vẫn sửa được
-- tự do qua bảng role_permissions bên dưới — chỉ không xoá được cái role.
CREATE TABLE IF NOT EXISTS roles (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Quyền được gán cho từng role — role 'admin' không cần dòng nào ở đây, luôn
-- có toàn quyền theo hardcode (xem roles_repo.effective_permissions), để
-- không ai tự khoá được quyền quản trị qua trang /admin/permissions.
CREATE TABLE IF NOT EXISTS role_permissions (
    role_key TEXT NOT NULL REFERENCES roles(key),
    permission_key TEXT NOT NULL,
    PRIMARY KEY (role_key, permission_key)
);

-- Ảnh/video bằng chứng, generic theo entity_type/entity_id (cùng kiểu tham
-- chiếu tự do như audit_log) — dùng cho ảnh phiếu cân, ảnh biên bản bàn
-- giao, video sự cố... checksum_sha256 để phát hiện tái sử dụng 1 file ảnh
-- cho nhiều lần cân khác nhau (cảnh báo mềm, xem media_repo.save_upload).
CREATE TABLE IF NOT EXISTS media_proof (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    mime_type TEXT,
    checksum_sha256 TEXT,
    note TEXT,
    uploaded_by TEXT,
    uploaded_at TEXT NOT NULL,
    uploaded_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_proof_entity ON media_proof(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_media_proof_kind ON media_proof(kind);
CREATE INDEX IF NOT EXISTS idx_media_proof_checksum ON media_proof(checksum_sha256);

-- Lần cân xe tại khu giao nhận (cân bì không tải -> cân xe chở heo -> chốt).
-- Công ty đã có phần mềm cân riêng ở trạm cân, tự lưu trữ mã cân + chi tiết
-- đầy đủ mỗi lần cân — bảng này KHÔNG thay thế phần mềm đó, chỉ ghi nhận
-- tare_ticket_code/gross_ticket_code (mã phiếu cân, nguồn sự thật) theo
-- từng bước để Phòng bán hàng không bỏ qua bước cân bì (đặc biệt XH2/XH3);
-- *_weight_kg và ảnh chụp chỉ là dữ liệu đối chiếu/bằng chứng bổ sung, tuỳ
-- chọn (xem core/repositories/weighing_repo.py). 1 sale_allocation có thể có
-- nhiều lần cân (nhiều chuyến xe/ngày) nên tách bảng riêng thay vì thêm cột
-- vào sale_allocations. Bảng MỚI hoàn toàn nên locked_at có sẵn từ đầu ->
-- trigger khoá vĩnh viễn định nghĩa được ngay ở đây (khác sale_plans/
-- sale_allocations bên dưới, xem _migrate()).
CREATE TABLE IF NOT EXISTS weighing_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_allocation_id INTEGER NOT NULL REFERENCES sale_allocations(id),
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    vehicle_plate TEXT,
    tare_weight_kg INTEGER,
    tare_ticket_code TEXT,
    tare_photo_media_id INTEGER REFERENCES media_proof(id),
    tare_recorded_by TEXT,
    tare_recorded_at TEXT,
    gross_weight_kg INTEGER,
    gross_ticket_code TEXT,
    gross_photo_media_id INTEGER REFERENCES media_proof(id),
    gross_recorded_by TEXT,
    gross_recorded_at TEXT,
    net_weight_kg INTEGER,
    status TEXT NOT NULL DEFAULT 'awaiting_tare',
    locked_at TEXT,
    locked_by TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_weighing_records_allocation ON weighing_records(sale_allocation_id);
CREATE INDEX IF NOT EXISTS idx_weighing_records_farm_status ON weighing_records(farm_id, status);
CREATE TRIGGER IF NOT EXISTS trg_weighing_records_lock_guard
BEFORE UPDATE ON weighing_records
FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'DATA_FROZEN: weighing_records đã khoá vĩnh viễn, không thể sửa');
END;

-- Báo cáo sự cố nhanh (hao hụt, giảm giá, tranh chấp cân...) — QĐ 52 yêu cầu
-- mọi thay đổi phát sinh sau khi cân phải có biên bản/bằng chứng kèm theo
-- (media_proof). Chỉ tạo bảng ở đây, chưa có repo riêng (chưa cần ở phase
-- này) — ràng buộc "bắt buộc kèm ảnh/video" thực hiện ở tầng ứng dụng khi
-- route tương ứng được viết.
CREATE TABLE IF NOT EXISTS incident_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_code TEXT,
    allocation_id INTEGER REFERENCES sale_allocations(id),
    weighing_record_id INTEGER REFERENCES weighing_records(id),
    farm_id INTEGER REFERENCES farms(id),
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    compensation_amount INTEGER,
    status TEXT NOT NULL DEFAULT 'reported',
    reported_by TEXT,
    reported_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_note TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_incident_reports_allocation ON incident_reports(allocation_id);
CREATE INDEX IF NOT EXISTS idx_incident_reports_status ON incident_reports(status);

-- Đối soát kế hoạch trại: phần chênh lệch quantity (kế hoạch gốc) -
-- actual_sold_quantity (thực tế bán, cộng dồn từ sale_allocations.
-- actual_quantity của các đơn đã "Đã bán") mà CHƯA có ở incident_reports vì
-- bảng đó bắt buộc gắn allocation_id (1 dòng hàng có thật) — không biểu diễn
-- được phần số lượng chưa từng được đưa vào đơn nào. sale_plan_id gắn trực
-- tiếp vào kế hoạch trại. kind: still_at_farm/continue_selling (ghi nhận,
-- KHÔNG tính là đã đối soát) hoặc transferred/culled/cancelled/other (tính
-- vào reconciled_quantity, xem core/repositories/sale_plans_repo.py). Ảnh
-- bằng chứng (bắt buộc với culled/cancelled) qua media_proof dùng chung,
-- entity_type='plan_reconciliation'. KHÔNG đụng sale_plans.quantity.
CREATE TABLE IF NOT EXISTS sale_plan_reconciliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_plan_id INTEGER NOT NULL REFERENCES sale_plans(id),
    kind TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reported_by TEXT,
    reported_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_plan_reconciliations_plan_id ON sale_plan_reconciliations(sale_plan_id);

-- Lần xuất giao THỰC TẾ của 1 dòng hàng (sale_allocations). 1 dòng hàng ->
-- N lần xuất: đây là thứ cho phép ghi nhận "kế hoạch 100 loại 1 / thực tế
-- 80 loại 1 + 20 loại 2" và "1 kế hoạch xuất nhiều lần" mà KHÔNG đụng vào
-- sale_plans/sale_allocations (nguyên tắc: không bao giờ sửa số kế hoạch gốc
-- để làm số liệu khớp).
--
-- pig_type_id ở ĐÂY là loại heo THỰC TẾ giao, có thể KHÁC loại của kế hoạch
-- trại (sale_plans.pig_type_id) — khác hẳn sale_allocations vốn cố ý không
-- lưu loại heo riêng mà JOIN ngược về kế hoạch (xem chú thích bảng đó).
-- KHÔNG lưu customer_id: suy ra qua allocation -> sale_orders.customer_id;
-- lưu lại sẽ tạo nguồn sự thật thứ 2 lệch được khi đơn đổi khách.
-- total_weight_kg/unit_price nullable: NULL = "chưa nhập cân/giá", KHÁC 0 —
-- tầng đọc cố ý KHÔNG COALESCE 2 field này về 0 (xem sale_plans_repo.py).
-- weighing_ref: mã phiếu cân của phần mềm trạm cân (cùng quy ước
-- sale_orders.weighing_ref). Khi luồng cân trong app được dùng thật, bổ sung
-- weighing_record_id INTEGER REFERENCES weighing_records(id) bằng ALTER.
--
-- Bảng MỚI hoàn toàn nên locked_at có sẵn từ đầu -> trigger khoá vĩnh viễn
-- định nghĩa được ngay ở đây (giống weighing_records; khác sale_plans/
-- sale_allocations/sale_orders có locked_at thêm bằng ALTER nên trigger buộc
-- phải nằm trong _migrate(), xem chú thích ở đó).
CREATE TABLE IF NOT EXISTS sale_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    allocation_id INTEGER NOT NULL REFERENCES sale_allocations(id),
    pig_type_id INTEGER NOT NULL REFERENCES pig_types(id),
    quantity INTEGER NOT NULL,
    total_weight_kg REAL,
    unit_price INTEGER,
    delivered_date TEXT,
    weighing_ref TEXT,
    note TEXT,
    locked_at TEXT,
    locked_by TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_deliveries_allocation ON sale_deliveries(allocation_id);
CREATE INDEX IF NOT EXISTS idx_sale_deliveries_pig_type ON sale_deliveries(pig_type_id);
CREATE INDEX IF NOT EXISTS idx_sale_deliveries_delivered_date ON sale_deliveries(delivered_date);
CREATE TRIGGER IF NOT EXISTS trg_sale_deliveries_lock_guard
BEFORE UPDATE ON sale_deliveries
FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'DATA_FROZEN: sale_deliveries đã khoá vĩnh viễn, không thể sửa');
END;

-- Dấu vết các bước migrate DỮ LIỆU (khác migrate CẤU TRÚC): _migrate() chạy ở
-- MỌI lần mở kết nối, và mỗi hàm repo mở 1 kết nối riêng — một backfill không
-- có cờ một-lần sẽ chạy lại hàng chục lần ngay trong 1 lần tải trang, nhân số
-- liệu lên nhiều lần. KHÔNG suy ra "đã chạy chưa" từ dữ liệu nghiệp vụ (VD
-- NOT EXISTS trên bảng đích): người dùng xoá dữ liệu hợp lệ để nhập lại sẽ
-- khiến backfill hồi sinh bản ghi ma ở lần mở kết nối kế tiếp.
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    username TEXT,
    action TEXT NOT NULL,
    -- entity_type/entity_id: đối tượng bị tác động (vd "sale_plan"/"42"), tách
    -- khỏi detail để tra cứu được bằng WHERE/index thay vì phải LIKE trên
    -- chuỗi tự do (vd tìm "plan_id=123" từng khớp nhầm "zone_id=123").
    entity_type TEXT,
    entity_id TEXT,
    -- old_value/new_value: JSON, chỉ set với hành động sửa — để biết đã đổi
    -- từ gì sang gì, không chỉ giá trị mới. NULL với hành động tạo/xóa/khác.
    old_value TEXT,
    new_value TEXT,
    detail TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_at ON audit_log(at);
-- Index cho entity_type/entity_id/username tạo trong _migrate(), không đặt ở
-- đây — cùng lý do với idx_zones_farm_id/idx_sale_plans_plan_code: trên DB
-- nâng cấp từ bản cũ, executescript() này chạy trước _migrate() nên các cột
-- đó có thể chưa tồn tại lúc CREATE INDEX chạy.
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Thêm cột mới / đổi cấu trúc bảng đã tồn tại, idempotent — an toàn
    chạy lại mỗi lần mở kết nối. SQLite không có ADD COLUMN IF NOT EXISTS
    nên luôn kiểm tra PRAGMA table_info trước khi ALTER."""
    farm_cols = {row[1] for row in conn.execute("PRAGMA table_info(farms)").fetchall()}
    if "province" not in farm_cols:
        conn.execute("ALTER TABLE farms ADD COLUMN province TEXT")

    # Seed 3 trại mặc định — chỉ chèn khi bảng farms còn trống (cài mới),
    # không dùng INSERT OR IGNORE chạy lại mỗi lần mở kết nối (xem lý do ở
    # _DB_SCHEMA phía trên).
    if conn.execute("SELECT COUNT(*) FROM farms").fetchone()[0] == 0:
        now = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO farms (code, created_at) VALUES (?, ?)",
            [("XH1", now), ("XH2", now), ("XH3", now)],
        )

    # zones.farm (TEXT, tham chiếu farms.code) -> zones.farm_id (FK farms.id).
    # Tham chiếu bằng text trước đây không có ràng buộc toàn vẹn: đổi mã
    # trại là "mồ côi" hết các khu đã tạo. Dựng lại bảng vì SQLite không
    # đổi kiểu cột tại chỗ được.
    zone_cols = {row[1] for row in conn.execute("PRAGMA table_info(zones)").fetchall()}
    if "farm_id" not in zone_cols:
        conn.executescript(
            """
            CREATE TABLE zones_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                farm_id INTEGER NOT NULL REFERENCES farms(id),
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (farm_id, code)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO zones_new (id, farm_id, code, created_at)
            SELECT z.id, f.id, z.code, z.created_at
            FROM zones z JOIN farms f ON f.code = z.farm
            """
        )
        conn.executescript(
            """
            DROP TABLE zones;
            ALTER TABLE zones_new RENAME TO zones;
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zones_farm_id ON zones(farm_id)")

    plan_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_plans)").fetchall()}
    if "created_by" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN created_by TEXT")
        plan_cols.add("created_by")
    if "updated_by" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN updated_by TEXT")
        plan_cols.add("updated_by")

    # sale_plans.farm/zone (TEXT) -> farm_id/zone_id (FK); + pig_type_id
    # (danh mục loại heo bán) + actual_price/actual_quantity (đối chiếu kế
    # hoạch với kết quả bán thực tế). Cùng lý do dựng lại bảng như trên.
    if "farm_id" not in plan_cols:
        conn.executescript(
            """
            CREATE TABLE sale_plans_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_code TEXT,
                planned_date TEXT NOT NULL,
                farm_id INTEGER NOT NULL REFERENCES farms(id),
                zone_id INTEGER REFERENCES zones(id),
                pig_type_id INTEGER REFERENCES pig_types(id),
                quantity INTEGER NOT NULL,
                target_price INTEGER NOT NULL,
                actual_price INTEGER,
                actual_quantity INTEGER,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                created_ip TEXT,
                updated_at TEXT NOT NULL,
                updated_ip TEXT,
                created_by TEXT,
                updated_by TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sale_plans_new (id, planned_date, farm_id, zone_id, quantity, target_price,
                                         note, status, created_at, created_ip, updated_at, updated_ip,
                                         created_by, updated_by)
            SELECT sp.id, sp.planned_date, f.id, z.id, sp.quantity, sp.target_price,
                   sp.note, sp.status, sp.created_at, sp.created_ip, sp.updated_at, sp.updated_ip,
                   sp.created_by, sp.updated_by
            FROM sale_plans sp
            JOIN farms f ON f.code = sp.farm
            LEFT JOIN zones z ON z.farm_id = f.id AND z.code = sp.zone
            """
        )
        conn.executescript(
            """
            DROP TABLE sale_plans;
            ALTER TABLE sale_plans_new RENAME TO sale_plans;
            CREATE INDEX IF NOT EXISTS idx_sale_plans_status ON sale_plans(status);
            CREATE INDEX IF NOT EXISTS idx_sale_plans_planned_date ON sale_plans(planned_date);
            """
        )
        # Bảng vừa dựng lại đã có sẵn plan_code/actual_price/actual_quantity
        # trong DDL — nạp lại plan_cols từ bảng thật để 2 khối ALTER TABLE
        # phía dưới không cố thêm cột đã tồn tại (lỗi "duplicate column").
        plan_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_plans)").fetchall()}

    # Từ đây trở xuống, một số cột (actual_price/actual_quantity ở khối ngay
    # dưới, và cả nhóm khách hàng/giá/doanh thu/hoá đơn xa hơn) thuộc luồng
    # BÁN HÀNG — kể từ Giai đoạn 5 đã CHUYỂN HẲN sang bảng sale_allocations
    # (xem khối tách bảng phía dưới), KHÔNG được phép tự thêm lại vào
    # sale_plans một khi đã tách, nếu không sẽ bị ALTER thêm lại mỗi lần mở
    # kết nối, phá hỏng bảng vừa tách. received_quantity chỉ tồn tại sau khi
    # tách (hoặc sẵn có trên bản cài mới, đã có trong _DB_SCHEMA) — dùng làm
    # dấu hiệu nhận biết "đã tách rồi, không cần các cột legacy này nữa".
    plan_needs_legacy_sale_columns = "received_quantity" not in plan_cols

    if plan_needs_legacy_sale_columns and "actual_price" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN actual_price INTEGER")
        conn.execute("ALTER TABLE sale_plans ADD COLUMN actual_quantity INTEGER")
    if "plan_code" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN plan_code TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_plans_plan_code ON sale_plans(plan_code)")

    # Quy trình duyệt kế hoạch: pending_approval -> approved/rejected. Tách
    # approved_by/approved_at (và rejected_*) khỏi updated_by/updated_at vì
    # các trường updated_* sẽ bị ghi đè bởi các bước sau (đánh dấu "Đã bán"…)
    # — cần giữ nguyên mốc "ai/khi nào duyệt" không đổi qua các bước sau đó.
    for col in ("approved_by", "approved_at", "rejected_by", "rejected_at", "rejected_reason"):
        if col not in plan_cols:
            conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} TEXT")

    # Chuồng/Lô (Giai đoạn 4) — vẫn còn thuộc kế hoạch trại sau khi tách,
    # không gate theo plan_needs_legacy_sale_columns.
    for col in ("shed", "lot"):
        if col not in plan_cols:
            conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} TEXT")

    if plan_needs_legacy_sale_columns:
        # Chốt thông tin bán hàng (Giai đoạn 2): gán khách hàng + log liên hệ +
        # ngày chốt bán trên kế hoạch đã duyệt. Chỉ backfill cho DB CHƯA tách
        # (để khối tách bảng phía dưới đọc được dữ liệu cũ trước khi chuyển
        # hẳn sang sale_allocations) — DB đã tách không cần các cột này nữa.
        for col in ("customer_id", "contacted_by", "contacted_at", "contact_note", "confirmed_sale_at"):
            if col not in plan_cols:
                col_type = "INTEGER" if col == "customer_id" else "TEXT"
                conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} {col_type}")

        # Ghi nhận doanh thu & chứng từ (Giai đoạn 3) — cùng lý do, chỉ
        # backfill cho DB chưa tách.
        for col in (
            "paid_amount",
            "paid_at",
            "weighing_ref",
            "revenue_recorded_by",
            "revenue_recorded_at",
            "invoice_number",
            "invoiced_by",
            "invoiced_at",
        ):
            if col not in plan_cols:
                col_type = "INTEGER" if col == "paid_amount" else "TEXT"
                conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} {col_type}")

        # Giai đoạn 4 — phần giá/điều kiện giao nhận (agreed_price/delivery_time/
        # payment_method) cũng chuyển hẳn sang sale_allocations sau khi tách,
        # chỉ backfill cho DB chưa tách (khác Chuồng/Lô đã ALTER unconditional
        # ở trên vì 2 cột đó vẫn ở lại sale_plans).
        for col in ("agreed_price", "delivery_time", "payment_method"):
            if col not in plan_cols:
                col_type = "INTEGER" if col == "agreed_price" else "TEXT"
                conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} {col_type}")

    customer_cols = {row[1] for row in conn.execute("PRAGMA table_info(customers)").fetchall()}
    for col in ("email", "contact_person", "contact_title"):
        if col not in customer_cols:
            conn.execute(f"ALTER TABLE customers ADD COLUMN {col} TEXT")

    # Data migration cho bản nâng cấp từ trước khi có quy trình duyệt:
    # - status='active' (kế hoạch tạo trước khi có bước duyệt) -> 'approved',
    #   coi như đã qua duyệt để không phá vỡ dữ liệu/theo dõi giá đang có.
    #   approved_by/approved_at để NULL cho các dòng này (UI cần xử lý NULL).
    # - role='user' (vai trò cũ, không phân biệt bộ phận) -> 'sales', vai trò
    #   gần nghĩa nhất với hành vi cũ (xem/thao tác được mọi trại). Admin cần
    #   tự rà soát và đổi lại đúng vai trò (farm/accounting) sau khi nâng cấp.
    # Idempotent: sau lần chạy đầu không còn dòng nào khớp điều kiện nữa, và
    # app không bao giờ ghi lại các giá trị 'active'/'user' này nữa.
    conn.execute("UPDATE sale_plans SET status = 'approved' WHERE status = 'active'")
    conn.execute("UPDATE users SET role = 'sales' WHERE role = 'user'")

    # Giai đoạn 5 — tách "kế hoạch trại" (sale_plans, nguồn cung, BM01) khỏi
    # "kế hoạch bán" (sale_allocations, do Phòng bán hàng tạo, BM02): trước
    # đây 1 dòng sale_plans vừa là đăng ký của trại vừa là toàn bộ luồng bán
    # hàng (giá/khách hàng/doanh thu/hoá đơn) gộp chung — sai nghiệp vụ thật
    # (Phòng bán hàng "nhặt" 1 phần số lượng từ kế hoạch trại để tạo kế hoạch
    # bán riêng, 1 kế hoạch trại có thể sinh nhiều kế hoạch bán).
    # RỦI RO CAO: dựng lại bảng sale_plans (drop + rename) — bọc transaction
    # thủ công để rollback về trạng thái trước nếu lỗi giữa chừng. Vẫn cần
    # backup file DB trước khi chạy (xem hướng dẫn vận hành đi kèm bản này).
    if plan_needs_legacy_sale_columns:
        # Chốt (commit) mọi thay đổi ALTER/UPDATE đã làm phía trên trước khi
        # mở transaction thủ công — mô-đun sqlite3 mặc định (isolation_level
        # legacy) tự mở transaction ngầm trước câu INSERT/UPDATE/DELETE đầu
        # tiên, nên "BEGIN" tường minh bên dưới sẽ lỗi "transaction đã mở"
        # nếu không commit trước. Đồng thời chuyển sang isolation_level=None
        # (autocommit) để Python không tự COMMIT ngầm trước mỗi câu DDL (CREATE/
        # DROP/ALTER) như hành vi mặc định — cần vậy để CREATE TABLE + INSERT +
        # DROP + RENAME thật sự nằm trong 1 transaction, rollback được toàn bộ
        # nếu lỗi giữa chừng.
        conn.commit()
        old_isolation_level = conn.isolation_level
        conn.isolation_level = None
        try:
            conn.execute("BEGIN")
            # Bước A: chuyển dữ liệu bán hàng/doanh thu đã có (nếu có) sang
            # sale_allocations TRƯỚC khi sale_plans bị drop ở Bước B.
            # selling_price migrate = COALESCE(agreed_price, target_price) —
            # ưu tiên giá đã thoả thuận, rơi về giá mong muốn ban đầu nếu
            # sales chưa từng đổi giá. target_price của các dòng KHÔNG có sale
            # data bị loại bỏ vĩnh viễn (đúng quyết định bỏ hẳn giá khỏi kế
            # hoạch trại).
            conn.execute(
                """
                INSERT INTO sale_allocations (
                    plan_code, sale_plan_id, quantity, selling_price, status,
                    customer_id, contacted_by, contacted_at, contact_note, confirmed_sale_at,
                    delivery_time, payment_method, actual_price, actual_quantity,
                    paid_amount, paid_at, weighing_ref, revenue_recorded_by, revenue_recorded_at,
                    invoice_number, invoiced_by, invoiced_at,
                    created_at, created_ip, created_by, updated_at, updated_ip, updated_by
                )
                SELECT
                    CASE WHEN sp.plan_code IS NOT NULL THEN sp.plan_code || '-B01' ELSE NULL END,
                    sp.id, COALESCE(sp.actual_quantity, sp.quantity), COALESCE(sp.agreed_price, sp.target_price),
                    CASE sp.status WHEN 'done' THEN 'done' WHEN 'cancelled' THEN 'cancelled'
                                    WHEN 'disabled' THEN 'disabled' ELSE 'active' END,
                    sp.customer_id, sp.contacted_by, sp.contacted_at, sp.contact_note, sp.confirmed_sale_at,
                    sp.delivery_time, sp.payment_method, sp.actual_price, sp.actual_quantity,
                    sp.paid_amount, sp.paid_at, sp.weighing_ref, sp.revenue_recorded_by, sp.revenue_recorded_at,
                    sp.invoice_number, sp.invoiced_by, sp.invoiced_at,
                    sp.created_at, sp.created_ip, sp.created_by, sp.updated_at, sp.updated_ip, sp.updated_by
                FROM sale_plans sp
                WHERE sp.customer_id IS NOT NULL OR sp.agreed_price IS NOT NULL OR sp.contact_note IS NOT NULL
                   OR sp.confirmed_sale_at IS NOT NULL OR sp.paid_amount IS NOT NULL OR sp.weighing_ref IS NOT NULL
                   OR sp.invoice_number IS NOT NULL OR sp.contacted_by IS NOT NULL OR sp.status = 'done'
                """
            )
            # Bước B: dựng lại sale_plans không còn cột giá/khách hàng/doanh
            # thu, thêm received_quantity/received_at/received_by. Giữ nguyên
            # id (INSERT tường minh id) để sale_allocations.sale_plan_id ở
            # Bước A vẫn hợp lệ sau khi rename. status của dòng "có sale data"
            # chuẩn hoá về 'approved' (giả định nghiệp vụ — coi như trại đã
            # duyệt & đã được sales xử lý; admin cần rà soát lại các dòng
            # migrate sau khi nâng cấp qua trang Nhật ký/kế hoạch).
            conn.executescript(
                """
                CREATE TABLE sale_plans_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_code TEXT,
                    planned_date TEXT NOT NULL,
                    farm_id INTEGER NOT NULL REFERENCES farms(id),
                    zone_id INTEGER REFERENCES zones(id),
                    shed TEXT,
                    lot TEXT,
                    pig_type_id INTEGER REFERENCES pig_types(id),
                    quantity INTEGER NOT NULL,
                    received_quantity INTEGER,
                    received_at TEXT,
                    received_by TEXT,
                    note TEXT,
                    status TEXT NOT NULL DEFAULT 'pending_approval',
                    created_at TEXT NOT NULL,
                    created_ip TEXT,
                    created_by TEXT,
                    updated_at TEXT NOT NULL,
                    updated_ip TEXT,
                    updated_by TEXT,
                    approved_by TEXT,
                    approved_at TEXT,
                    rejected_by TEXT,
                    rejected_at TEXT,
                    rejected_reason TEXT
                );
                """
            )
            conn.execute(
                """
                INSERT INTO sale_plans_new (
                    id, plan_code, planned_date, farm_id, zone_id, shed, lot, pig_type_id, quantity, note,
                    status, created_at, created_ip, created_by, updated_at, updated_ip, updated_by,
                    approved_by, approved_at, rejected_by, rejected_at, rejected_reason
                )
                SELECT id, plan_code, planned_date, farm_id, zone_id, shed, lot, pig_type_id, quantity, note,
                    CASE WHEN (customer_id IS NOT NULL OR agreed_price IS NOT NULL OR contact_note IS NOT NULL
                               OR confirmed_sale_at IS NOT NULL OR paid_amount IS NOT NULL OR weighing_ref IS NOT NULL
                               OR invoice_number IS NOT NULL OR contacted_by IS NOT NULL OR status = 'done')
                         THEN 'approved' ELSE status END,
                    created_at, created_ip, created_by, updated_at, updated_ip, updated_by,
                    approved_by, approved_at, rejected_by, rejected_at, rejected_reason
                FROM sale_plans
                """
            )
            conn.executescript(
                """
                DROP TABLE sale_plans;
                ALTER TABLE sale_plans_new RENAME TO sale_plans;
                CREATE INDEX IF NOT EXISTS idx_sale_plans_status ON sale_plans(status);
                CREATE INDEX IF NOT EXISTS idx_sale_plans_planned_date ON sale_plans(planned_date);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_plans_plan_code ON sale_plans(plan_code);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_allocations_plan_code ON sale_allocations(plan_code);
                """
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.isolation_level = old_isolation_level
        plan_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_plans)").fetchall()}

    # Phòng trường hợp nâng cấp từ 1 DB đã tách bảng (không còn customer_id)
    # nhưng chưa có received_quantity — ALTER đơn giản, idempotent.
    if "received_quantity" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN received_quantity INTEGER")
    for col in ("received_at", "received_by"):
        if col not in plan_cols:
            conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} TEXT")

    # Trọng lượng dự kiến (kg/con) — nền cho đối soát chiều trọng lượng: khối
    # lượng kế hoạch = quantity * expected_avg_weight_kg. Đặt sau khối rebuild
    # bảng ở trên (plan_cols đã nạp lại) để không bị mất khi bảng được dựng
    # lại. Nullable và KHÔNG backfill: kế hoạch cũ không có số này, tầng đọc
    # trả NULL (không phải 0) để UI phân biệt "chưa nhập cân" với "cân = 0".
    if "expected_avg_weight_kg" not in plan_cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN expected_avg_weight_kg REAL")
        plan_cols.add("expected_avg_weight_kg")

    audit_cols = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    for col in ("entity_type", "entity_id", "old_value", "new_value"):
        if col not in audit_cols:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log(username)")

    # Seed 5 role gốc + quyền mặc định của chúng — chỉ chèn 1 lần khi bảng
    # roles còn trống (cài mới hoặc nâng cấp từ bản chưa có phân quyền tuỳ
    # biến), tái tạo đúng hành vi role_required(...) cũ để không ai bị mất
    # quyền khi nâng cấp. Không dùng INSERT OR IGNORE chạy lại mỗi lần mở kết
    # nối (cùng lý do với farms/pig_types seed phía trên).
    if conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
        now = datetime.now().isoformat(timespec="seconds")
        default_roles = [
            ("farm", "Trại"),
            ("sales", "Phòng bán hàng"),
            ("accounting", "Kế toán"),
            ("admin", "Admin"),
            ("leadership", "Ban lãnh đạo"),
        ]
        conn.executemany(
            "INSERT INTO roles (key, name, is_system, created_at) VALUES (?, ?, 1, ?)",
            [(key, name, now) for key, name in default_roles],
        )
        default_role_permissions = {
            "farm": [perm.PLAN_CREATE, perm.PLAN_RECEIVE],
            "sales": [
                perm.PLAN_CREATE,
                perm.PLAN_REVIEW,
                perm.PLAN_ALLOCATION_CREATE,
                perm.PLAN_ALLOCATION_MANAGE,
                perm.PLAN_SALE_DETAILS,
                perm.CUSTOMER_VIEW,
                perm.CUSTOMER_MANAGE,
            ],
            "accounting": [perm.PLAN_REVENUE_DETAILS],
            "leadership": [perm.CUSTOMER_VIEW, perm.ADMIN_FARMS_VIEW, perm.ADMIN_PIG_TYPES_VIEW],
            # 'admin' không cần dòng nào — luôn full quyền theo hardcode
            # trong roles_repo.effective_permissions().
        }
        conn.executemany(
            "INSERT INTO role_permissions (role_key, permission_key) VALUES (?, ?)",
            [
                (role_key, permission_key)
                for role_key, keys in default_role_permissions.items()
                for permission_key in keys
            ],
        )

    # Data Freeze (Phase 1 chống gian lận): locked_at/locked_by thêm vào 2
    # bảng ĐÃ TỒN TẠI -> phải qua ALTER trong _migrate(), không đặt trong
    # _DB_SCHEMA. Trigger tham chiếu 2 cột này vì vậy cũng phải tạo Ở ĐÂY,
    # SAU đoạn ALTER — nếu đặt trong _DB_SCHEMA (chạy trước _migrate() ở mỗi
    # lần mở kết nối) thì trên DB nâng cấp từ bản cũ, executescript() sẽ lỗi
    # vì cột locked_at chưa tồn tại lúc đó (cùng lý do với idx_zones_farm_id/
    # idx_sale_plans_plan_code phía trên).
    sale_plans_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_plans)").fetchall()}
    for col in ("locked_at", "locked_by"):
        if col not in sale_plans_cols:
            conn.execute(f"ALTER TABLE sale_plans ADD COLUMN {col} TEXT")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_sale_plans_lock_guard
        BEFORE UPDATE ON sale_plans
        FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'DATA_FROZEN: sale_plans đã khoá vĩnh viễn, không thể sửa');
        END
        """
    )

    # Giai đoạn 8 — tách "kế hoạch bán" (sale_allocations) thành đơn hàng
    # (sale_orders, header: khách hàng/liên hệ/chốt bán/giao nhận/thanh toán/
    # doanh thu/hoá đơn) + dòng hàng (sale_allocations co lại: chỉ còn
    # sale_plan_id/quantity/selling_price/actual_*) — 1 đơn cho 1 khách hàng
    # giờ gồm được NHIỀU dòng heo (nhiều loại/nhiều kế hoạch trại), theo đúng
    # BM02 gốc. weighing_records.sale_allocation_id/incident_reports.allocation_id
    # vẫn trỏ đúng bảng sale_allocations (tên bảng không đổi, id giữ nguyên
    # qua migration, chỉ co cột) nên không cần đụng 2 bảng đó.
    #
    # Đặt TRƯỚC khối locked_at/trigger ngay dưới đây để sau khi DROP+RENAME,
    # khối đó (đã có sẵn, không đụng vào) tự chạy lại và tạo lại đúng trigger
    # trên bảng mới — bảng mới ở Bước B bên dưới đã khai báo sẵn locked_at/
    # locked_by nên khối đó sẽ thấy cột đã có (ALTER no-op), chỉ CREATE
    # TRIGGER IF NOT EXISTS là còn tác dụng (trigger cũ đã mất theo DROP TABLE).
    sale_allocations_cols_pre = {row[1] for row in conn.execute("PRAGMA table_info(sale_allocations)").fetchall()}
    if "order_id" not in sale_allocations_cols_pre:
        conn.commit()
        old_isolation_level = conn.isolation_level
        conn.isolation_level = None
        try:
            conn.execute("BEGIN")
            # Đọc toàn bộ dòng cũ bằng tên cột (không đặt conn.row_factory
            # toàn cục, tránh ảnh hưởng phần còn lại của _migrate()) — dùng
            # .get() khi ghép dữ liệu vì bản chưa từng chạy qua khối
            # locked_at/trigger phía dưới (DB rất cũ) sẽ chưa có locked_at/
            # locked_by trong kết quả này.
            cur_read = conn.execute("SELECT * FROM sale_allocations")
            col_names = [d[0] for d in cur_read.description]
            old_allocs = [dict(zip(col_names, r)) for r in cur_read.fetchall()]

            # Bước A: mỗi dòng sale_allocations hiện có -> 1 sale_orders
            # tương ứng (1-1, giữ nguyên hành vi cũ), nhớ mapping id cũ ->
            # order_id mới để gắn vào Bước B. order_code sinh theo ngày tạo
            # (created_at, KHÔNG đổi qua sửa) + dò trùng trực tiếp trên cột
            # order_code — cùng kỹ thuật đã sửa ở _next_plan_code (Giai đoạn
            # 7) để không lặp lại lớp lỗi "đếm theo cột có thể đổi sau khi
            # tạo -> sinh trùng mã".
            order_id_by_alloc_id: dict[int, int] = {}
            order_seq_by_date: dict[str, int] = {}
            for row in old_allocs:
                created_date = (row.get("created_at") or "")[:10].replace("-", "") or "00000000"
                seq = order_seq_by_date.get(created_date, 0) + 1
                while True:
                    order_code = f"DH{created_date}-{seq:02d}"
                    if conn.execute("SELECT 1 FROM sale_orders WHERE order_code = ?", (order_code,)).fetchone() is None:
                        break
                    seq += 1
                order_seq_by_date[created_date] = seq
                status = row.get("status")
                if status not in ("active", "done", "cancelled", "disabled"):
                    status = "active"
                cur = conn.execute(
                    """
                    INSERT INTO sale_orders (
                        order_code, customer_id, contacted_by, contacted_at, contact_note,
                        confirmed_sale_at, delivery_time, payment_method, status,
                        paid_amount, paid_at, weighing_ref, revenue_recorded_by, revenue_recorded_at,
                        invoice_number, invoiced_by, invoiced_at,
                        created_at, created_ip, created_by, updated_at, updated_ip, updated_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_code, row.get("customer_id"), row.get("contacted_by"), row.get("contacted_at"),
                        row.get("contact_note"), row.get("confirmed_sale_at"), row.get("delivery_time"),
                        row.get("payment_method"), status,
                        row.get("paid_amount"), row.get("paid_at"), row.get("weighing_ref"),
                        row.get("revenue_recorded_by"), row.get("revenue_recorded_at"),
                        row.get("invoice_number"), row.get("invoiced_by"), row.get("invoiced_at"),
                        row.get("created_at"), row.get("created_ip"), row.get("created_by"),
                        row.get("updated_at"), row.get("updated_ip"), row.get("updated_by"),
                    ),
                )
                order_id_by_alloc_id[row["id"]] = cur.lastrowid

            # Bước B: dựng lại sale_allocations co thành dòng hàng thuần
            # (order_id thay cho toàn bộ cột khách hàng/doanh thu/hoá đơn ở
            # trên). Giữ nguyên id (INSERT tường minh) vì weighing_records/
            # incident_reports đang tham chiếu id này.
            conn.executescript(
                """
                CREATE TABLE sale_allocations_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_code TEXT,
                    order_id INTEGER NOT NULL REFERENCES sale_orders(id),
                    sale_plan_id INTEGER NOT NULL REFERENCES sale_plans(id),
                    quantity INTEGER NOT NULL,
                    selling_price INTEGER,
                    note TEXT,
                    actual_price INTEGER,
                    actual_quantity INTEGER,
                    locked_at TEXT,
                    locked_by TEXT,
                    created_at TEXT NOT NULL,
                    created_ip TEXT,
                    created_by TEXT,
                    updated_at TEXT NOT NULL,
                    updated_ip TEXT,
                    updated_by TEXT
                );
                """
            )
            for row in old_allocs:
                conn.execute(
                    """
                    INSERT INTO sale_allocations_new (
                        id, plan_code, order_id, sale_plan_id, quantity, selling_price, note,
                        actual_price, actual_quantity, locked_at, locked_by,
                        created_at, created_ip, created_by, updated_at, updated_ip, updated_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"], row.get("plan_code"), order_id_by_alloc_id[row["id"]], row["sale_plan_id"],
                        row["quantity"], row.get("selling_price"), row.get("note"),
                        row.get("actual_price"), row.get("actual_quantity"),
                        row.get("locked_at"), row.get("locked_by"),
                        row.get("created_at"), row.get("created_ip"), row.get("created_by"),
                        row.get("updated_at"), row.get("updated_ip"), row.get("updated_by"),
                    ),
                )
            conn.executescript(
                """
                DROP TABLE sale_allocations;
                ALTER TABLE sale_allocations_new RENAME TO sale_allocations;
                CREATE INDEX IF NOT EXISTS idx_sale_allocations_sale_plan_id ON sale_allocations(sale_plan_id);
                CREATE INDEX IF NOT EXISTS idx_sale_allocations_order_id ON sale_allocations(order_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_allocations_plan_code ON sale_allocations(plan_code);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_orders_order_code ON sale_orders(order_code);
                """
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.isolation_level = old_isolation_level

    sale_allocations_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_allocations)").fetchall()}
    for col in ("locked_at", "locked_by"):
        if col not in sale_allocations_cols:
            conn.execute(f"ALTER TABLE sale_allocations ADD COLUMN {col} TEXT")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_sale_allocations_lock_guard
        BEFORE UPDATE ON sale_allocations
        FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'DATA_FROZEN: sale_allocations đã khoá vĩnh viễn, không thể sửa');
        END
        """
    )

    sale_orders_cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_orders)").fetchall()}
    for col in ("locked_at", "locked_by"):
        if col not in sale_orders_cols:
            conn.execute(f"ALTER TABLE sale_orders ADD COLUMN {col} TEXT")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_sale_orders_lock_guard
        BEFORE UPDATE ON sale_orders
        FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'DATA_FROZEN: sale_orders đã khoá vĩnh viễn, không thể sửa');
        END
        """
    )

    # Ghi nhận heo Loại/Hủy (kind='culled'/'cancelled' trên incident_reports
    # đã có sẵn) cần biết SỐ LƯỢNG con bị loại/hủy — bảng cũ chưa có cột
    # này (tạo ban đầu chỉ để dành chỗ, chưa có repo/route dùng tới).
    incident_reports_cols = {row[1] for row in conn.execute("PRAGMA table_info(incident_reports)").fetchall()}
    if "quantity" not in incident_reports_cols:
        conn.execute("ALTER TABLE incident_reports ADD COLUMN quantity INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    _backfill_sale_deliveries(conn)


# Migrate DỮ LIỆU (khác các ALTER/rebuild CẤU TRÚC ở trên) — chạy đúng 1 lần
# duy nhất trong đời DB, chốt bằng cờ trong app_meta.
_BACKFILL_DELIVERIES_KEY = "backfill_sale_deliveries_v1"


def _backfill_sale_deliveries(conn: sqlite3.Connection) -> None:
    """Sinh 1 dòng sale_deliveries cho mỗi dòng hàng đã có actual_quantity —
    để việc đổi nguồn tính actual_sold_quantity (sale_allocations.actual_quantity
    -> SUM(sale_deliveries.quantity)) không làm đổi số liệu của dữ liệu cũ.

    BẮT BUỘC có cờ một-lần: _migrate() chạy trong get_connection(), mà mỗi hàm
    repo mở 1 kết nối riêng -> 1 lần tải trang mở DB hàng chục lần. Không có cờ
    thì backfill nhân số liệu lên nhiều lần ngay trong 1 request.

    Cố ý KHÔNG dùng "NOT EXISTS trên sale_deliveries" làm điều kiện: cách đó
    idempotent nhưng còn vũ trang mãi mãi — người dùng xoá 2 delivery (VD
    80 loại 1 + 20 loại 2) để nhập lại thì lần mở kết nối kế tiếp sẽ hồi sinh
    1 delivery ma 100 con, xoá đúng cái cơ cấu họ vừa định sửa.

    Cũng cố ý KHÔNG lọc theo so.status: sale_deliveries là sổ ghi sự kiện vật
    lý, ngữ nghĩa trạng thái đơn chỉ nằm ở tầng đọc (xem _DELIVERY_FROM_SQL
    trong sale_plans_repo.py) — nhúng status vào đây sẽ làm mất lịch sử nếu đơn
    đổi trạng thái sau này.
    """
    if conn.execute("SELECT 1 FROM app_meta WHERE key = ?", (_BACKFILL_DELIVERIES_KEY,)).fetchone() is not None:
        return

    old_isolation_level = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN")
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO sale_deliveries (
                allocation_id, pig_type_id, quantity, unit_price, delivered_date,
                note, created_at, created_by, updated_at, updated_by
            )
            SELECT sa.id, sp.pig_type_id, sa.actual_quantity, sa.actual_price,
                   substr(COALESCE(so.confirmed_sale_at, sa.updated_at,
                                   so.updated_at, sa.created_at), 1, 10),
                   'Sinh tự động từ sale_allocations.actual_quantity — loại heo lấy '
                   'theo kế hoạch trại, CHƯA được người dùng xác nhận cơ cấu thực tế.',
                   ?, 'system:backfill', ?, 'system:backfill'
            FROM sale_allocations sa
            JOIN sale_plans sp ON sp.id = sa.sale_plan_id
            JOIN sale_orders so ON so.id = sa.order_id
            WHERE sa.actual_quantity IS NOT NULL
            """,
            (now, now),
        )
        # Cờ nằm TRONG cùng transaction với backfill: crash giữa chừng ->
        # rollback cả hai -> lần mở kết nối sau chạy lại sạch, không nửa vời.
        conn.execute(
            "INSERT INTO app_meta (key, value, applied_at) VALUES (?, ?, ?)",
            (_BACKFILL_DELIVERIES_KEY, "done", now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.isolation_level = old_isolation_level

db_lock = threading.Lock()
@contextmanager
def transaction(conn: sqlite3.Connection):
    """
    Quản lý transaction cho một business operation.

    Connection được tạo và đóng bởi caller.
    Helper này chỉ chịu trách nhiệm BEGIN / COMMIT / ROLLBACK.
    """
    if conn.in_transaction:
        # Đã có transaction bên ngoài.
        # Không tự commit/rollback transaction của caller.
        yield conn
        return

    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def get_connection(db_path: Path) -> sqlite3.Connection:
    """Mở kết nối SQLite, tạo bảng/index nếu chưa có. WAL giúp đọc và ghi
    không chặn lẫn nhau khi nhiều tiến trình (server + script CLI) cùng
    dùng chung 1 file .db."""

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode=WAL;")

    conn.executescript(_DB_SCHEMA)
    _migrate(conn)

    return conn
