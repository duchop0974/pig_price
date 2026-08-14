"""Kết nối SQLite dùng chung, schema + migration nhẹ (thêm cột/bảng nếu chưa có)."""
import sqlite3
from pathlib import Path

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
    created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO farms (code, created_at) VALUES
    ('XH1', CURRENT_TIMESTAMP),
    ('XH2', CURRENT_TIMESTAMP),
    ('XH3', CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (farm, code)
);
CREATE INDEX IF NOT EXISTS idx_zones_farm ON zones(farm);

CREATE TABLE IF NOT EXISTS sale_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planned_date TEXT NOT NULL,
    farm TEXT NOT NULL,
    zone TEXT,
    quantity INTEGER NOT NULL,
    target_price INTEGER NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    -- Các trường ẩn dưới đây không hiện trên form/thẻ kế hoạch, chỉ dùng để
    -- truy vết khi cần đối soát (ai/khi nào tạo & sửa kế hoạch).
    created_at TEXT NOT NULL,
    created_ip TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_plans_status ON sale_plans(status);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    username TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_log_at ON audit_log(at);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Thêm cột mới vào bảng đã tồn tại (SQLite không có ADD COLUMN IF NOT
    EXISTS), idempotent — an toàn chạy lại mỗi lần mở kết nối."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sale_plans)").fetchall()}
    if "created_by" not in cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN created_by TEXT")
    if "updated_by" not in cols:
        conn.execute("ALTER TABLE sale_plans ADD COLUMN updated_by TEXT")
    conn.commit()


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Mở kết nối SQLite, tạo bảng/index nếu chưa có. WAL giúp đọc và ghi
    không chặn lẫn nhau khi nhiều tiến trình (server + script CLI) cùng
    dùng chung 1 file .db."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_DB_SCHEMA)
    _migrate(conn)
    return conn
