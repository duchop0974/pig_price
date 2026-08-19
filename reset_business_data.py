"""
Reset dữ liệu nghiệp vụ của web app.

Mục đích:
- Xoá toàn bộ dữ liệu nghiệp vụ/test.
- Giữ nguyên schema, trigger, index.
- Giữ dữ liệu nền cần thiết để app tiếp tục hoạt động.
- Tự động backup DB trước khi reset.
- Không suy luận record nào là "test"; chỉ xoá các bảng nằm trong BUSINESS_TABLES.

Chạy:
    python reset_business_data.py

Script sẽ yêu cầu nhập:
    RESET
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "gia_heo_hoi.db"
MEDIA_ROOT = BASE_DIR / "data" / "media"
BACKUP_DIR = BASE_DIR / "data" / "backups"


# Chỉ các bảng nghiệp vụ được phép reset.
#
# QUAN TRỌNG:
# Không thêm bảng vào đây nếu chưa xác nhận đó là bảng dữ liệu
# nghiệp vụ có thể xoá toàn bộ.
BUSINESS_TABLES = [
    "sale_deliveries",
    "sale_plan_reconciliations",
    "logistics_handover_items",
    "logistics_handovers",
    "weighing_records",
    "incident_reports",
    "media_proof",
    "sale_allocations",
    "sale_orders",
    "sale_plans",
    "audit_log",
]


# Các bảng này tuyệt đối không được script xoá.
PROTECTED_TABLES = {
    "users",
    "roles",
    "role_permissions",
    "farms",
    "zones",
    "pig_types",
}


# ============================================================
# HELPERS
# ============================================================

def get_existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    return {row[0] for row in rows}


def get_row_count(
    conn: sqlite3.Connection,
    table_name: str,
) -> int:
    return conn.execute(
        f'SELECT COUNT(*) FROM "{table_name}"'
    ).fetchone()[0]


def backup_database() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR
        / f"gia_heo_hoi_before_reset_{timestamp}.db"
    )

    shutil.copy2(DB_PATH, backup_path)

    return backup_path


def reset_media() -> None:
    """
    Xoá toàn bộ media nghiệp vụ.

    media/ là nơi lưu file upload của incident,
    reconciliation, delivery/weighing evidence...
    """

    if not MEDIA_ROOT.exists():
        print("  - data/media: không tồn tại, bỏ qua")
        return

    removed_files = 0
    removed_dirs = 0

    for path in sorted(
        MEDIA_ROOT.rglob("*"),
        reverse=True,
    ):
        if path.is_file():
            path.unlink()
            removed_files += 1
        elif path.is_dir():
            try:
                path.rmdir()
                removed_dirs += 1
            except OSError:
                # Thư mục còn file ngoài phạm vi script thì giữ lại.
                pass

    print(
        f"  - data/media: xoá {removed_files} file, "
        f"{removed_dirs} thư mục"
    )


def reset_tables(
    conn: sqlite3.Connection,
    existing_tables: set[str],
) -> dict[str, int]:
    """
    Xoá dữ liệu theo whitelist.

    Không DROP TABLE.
    """

    results: dict[str, int] = {}

    tables_to_reset = [
        table
        for table in BUSINESS_TABLES
        if table in existing_tables
    ]

    # Kiểm tra an toàn trước khi thực hiện.
    dangerous = set(tables_to_reset) & PROTECTED_TABLES

    if dangerous:
        raise RuntimeError(
            "SAFETY CHECK FAILED: bảng protected xuất hiện trong "
            f"BUSINESS_TABLES: {sorted(dangerous)}"
        )

    print("\nSố lượng trước khi reset:")
    print("-" * 60)

    for table in tables_to_reset:
        count = get_row_count(conn, table)
        results[table] = count
        print(f"{table:<35} {count:>10}")

    print("-" * 60)

    # Foreign key của SQLite thường được bật/tắt tùy connection.
    # Tạm defer để đảm bảo transaction có thể xoá theo đúng thứ tự.
    conn.execute("PRAGMA defer_foreign_keys = ON")

    # Xoá theo thứ tự bảng con -> bảng cha.
    for table in tables_to_reset:
        conn.execute(f'DELETE FROM "{table}"')

    # Reset AUTOINCREMENT cho các bảng vừa xoá.
    #
    # sqlite_sequence chỉ tồn tại nếu DB có AUTOINCREMENT.
    sqlite_sequence_exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'sqlite_sequence'
        """
    ).fetchone()

    if sqlite_sequence_exists:
        for table in tables_to_reset:
            conn.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name = ?
                """,
                (table,),
            )

    return results


def verify_reset(
    conn: sqlite3.Connection,
    existing_tables: set[str],
) -> dict[str, int]:
    results: dict[str, int] = {}

    print("\nKiểm tra sau reset:")
    print("-" * 60)

    for table in BUSINESS_TABLES:
        if table not in existing_tables:
            print(f"{table:<35} KHÔNG TỒN TẠI")
            continue

        count = get_row_count(conn, table)
        results[table] = count

        status = "OK" if count == 0 else "CÒN DỮ LIỆU"

        print(
            f"{table:<35} "
            f"{count:>10}   {status}"
        )

    print("-" * 60)

    remaining = {
        table: count
        for table, count in results.items()
        if count != 0
    }

    if remaining:
        raise RuntimeError(
            "RESET KHÔNG HOÀN TẤT. Các bảng vẫn còn dữ liệu: "
            f"{remaining}"
        )

    return results


def verify_protected_tables(
    conn: sqlite3.Connection,
    existing_tables: set[str],
) -> None:
    """
    Chỉ kiểm tra rằng các bảng protected vẫn tồn tại.
    Không kiểm tra số lượng vì có thể có bảng vốn đang rỗng.
    """

    print("\nKiểm tra bảng được bảo vệ:")

    for table in sorted(PROTECTED_TABLES):
        if table in existing_tables:
            count = get_row_count(conn, table)
            print(f"  - {table}: còn nguyên ({count} records)")
        else:
            print(
                f"  - CẢNH BÁO: {table} không tồn tại trong DB"
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("=" * 70)
    print("RESET BUSINESS DATA")
    print("=" * 70)

    print(f"\nDatabase: {DB_PATH}")

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy database:\n{DB_PATH}"
        )

    print("\nCác bảng SẼ BỊ XOÁ DỮ LIỆU:")
    for table in BUSINESS_TABLES:
        print(f"  - {table}")

    print("\nCác bảng ĐƯỢC GIỮ LẠI:")
    for table in sorted(PROTECTED_TABLES):
        print(f"  - {table}")

    print(
        "\nLƯU Ý:"
        "\n- Script không DROP TABLE."
        "\n- Script không thay đổi schema."
        "\n- Script không xoá users/roles/farms/zones/pig_types."
        "\n- Database sẽ được backup trước khi reset."
        "\n- Toàn bộ dữ liệu trong BUSINESS_TABLES sẽ bị xoá."
    )

    confirmation = input(
        "\nNhập RESET để tiếp tục: "
    ).strip()

    if confirmation != "RESET":
        print("\nĐã huỷ. Không có dữ liệu nào bị thay đổi.")
        return

    print("\nĐang tạo backup...")

    backup_path = backup_database()

    print(f"Backup: {backup_path}")

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)

        # Foreign key nên được bật để phát hiện vấn đề quan hệ.
        conn.execute("PRAGMA foreign_keys = ON")

        existing_tables = get_existing_tables(conn)

        print("\nKiểm tra schema...")

        missing_business_tables = [
            table
            for table in BUSINESS_TABLES
            if table not in existing_tables
        ]

        if missing_business_tables:
            print(
                "\nCác bảng trong whitelist nhưng không tồn tại:"
            )
            for table in missing_business_tables:
                print(f"  - {table}")

        # Kiểm tra protected.
        dangerous = (
            set(BUSINESS_TABLES) & PROTECTED_TABLES
        )

        if dangerous:
            raise RuntimeError(
                "Phát hiện bảng protected trong danh sách xoá: "
                f"{sorted(dangerous)}"
            )

        print("\nĐang reset dữ liệu...")

        before = reset_tables(
            conn,
            existing_tables,
        )

        # Transaction được commit tại đây.
        conn.commit()

        print("\nReset database thành công.")

        # Verify sau commit.
        verify_reset(
            conn,
            existing_tables,
        )

        verify_protected_tables(
            conn,
            existing_tables,
        )

        # Xoá media sau khi DB đã reset thành công.
        print("\nĐang xử lý media...")
        reset_media()

        print("\n" + "=" * 70)
        print("RESET HOÀN TẤT")
        print("=" * 70)

        print(f"\nBackup được giữ tại:")
        print(f"  {backup_path}")

        print("\nDữ liệu nghiệp vụ đã được xoá sạch.")
        print("Schema database được giữ nguyên.")
        print("Các bảng cấu hình/nền vẫn được giữ lại.")

    except Exception:
        if conn is not None:
            conn.rollback()

        print("\n" + "=" * 70)
        print("RESET THẤT BẠI")
        print("=" * 70)
        print("\nDatabase chưa được commit thay đổi.")

        print("\nBackup an toàn:")
        print(f"  {backup_path}")

        raise

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()