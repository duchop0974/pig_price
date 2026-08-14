"""CRUD cho bảng prices."""
from pathlib import Path

import pandas as pd

from core.db import DB_COLUMNS, get_connection


def save_records(records: list[dict], db_path: Path) -> None:
    if not records:
        print("Không có dữ liệu mới để lưu.")
        return

    rows = [
        (
            r["date"],
            r["source"],
            r.get("region"),
            r["province"],
            r.get("price_vnd_per_kg"),
            r.get("change_vnd_per_kg"),
            r.get("benchmark_price_vnd_per_kg"),
            r.get("source_url"),
        )
        for r in records
    ]

    conn = get_connection(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO prices (date, source, region, province, price_vnd_per_kg,
                                 change_vnd_per_kg, benchmark_price_vnd_per_kg, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source, province) DO UPDATE SET
                region=excluded.region,
                price_vnd_per_kg=excluded.price_vnd_per_kg,
                change_vnd_per_kg=excluded.change_vnd_per_kg,
                benchmark_price_vnd_per_kg=excluded.benchmark_price_vnd_per_kg,
                source_url=excluded.source_url
            """,
            rows,
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    finally:
        conn.close()

    print(f"Đã lưu {len(records)} dòng mới, tổng {total} dòng vào {db_path}")


def load_records_df(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame(columns=DB_COLUMNS)
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(f"SELECT {', '.join(DB_COLUMNS)} FROM prices", conn)
    finally:
        conn.close()
