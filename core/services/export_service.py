"""Xuất dữ liệu ra Excel: giá heo hơi và kế hoạch xuất bán."""
import sqlite3
from pathlib import Path

import pandas as pd

from core.db import get_connection
from core.repositories.prices_repo import load_records_df
from core.repositories.sale_plans_repo import SALE_PLAN_ALL_COLUMNS

EXPORT_COLUMNS = {
    "date": "Ngày",
    "source": "Nguồn",
    "region": "Miền",
    "province": "Địa phương",
    "price_vnd_per_kg": "Giá (đ/kg)",
    "change_vnd_per_kg": "Biến động (đ/kg)",
    "benchmark_price_vnd_per_kg": "Giá heo cám GreenFeed (đ/kg)",
    "source_url": "Nguồn URL",
}


def export_to_excel(db_path: Path, dest) -> int:
    """Xuất toàn bộ dữ liệu ra Excel. `dest` có thể là đường dẫn file hoặc
    buffer (BytesIO, dùng khi trả file trực tiếp qua web). Trả về số dòng
    đã xuất."""
    df = load_records_df(db_path)
    if df.empty:
        raise ValueError("Chưa có dữ liệu để xuất.")

    export_df = df.copy()
    export_df["_date_sort"] = pd.to_datetime(export_df["date"], format="%d/%m/%Y")
    export_df = export_df.sort_values(["_date_sort", "source", "province"]).drop(columns="_date_sort")
    export_df = export_df.rename(columns=EXPORT_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Gia heo hoi")
        ws = writer.sheets["Gia heo hoi"]
        for col_idx, col_name in enumerate(export_df.columns, start=1):
            max_len = max(
                len(str(col_name)),
                int(export_df.iloc[:, col_idx - 1].fillna("").astype(str).str.len().max())
                if len(export_df)
                else 0,
            )
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 45)
        ws.freeze_panes = "A2"

    return len(export_df)


SALE_PLAN_EXPORT_COLUMNS = {
    "id": "Mã KH",
    "planned_date": "Ngày dự kiến",
    "farm": "Trang trại",
    "zone": "Khu",
    "quantity": "Số lượng (con)",
    "target_price": "Giá mong muốn (đ/kg)",
    "note": "Ghi chú",
    "status": "Trạng thái",
    "created_by": "Người tạo",
    "created_at": "Tạo lúc",
    "created_ip": "IP tạo",
    "updated_by": "Người sửa gần nhất",
    "updated_at": "Sửa lúc",
    "updated_ip": "IP sửa",
}

SALE_PLAN_STATUS_LABEL = {
    "active": "Đang chờ",
    "done": "Đã bán",
    "cancelled": "Đã hủy",
}


def export_sale_plans_to_excel(db_path: Path, dest) -> int:
    """Xuất toàn bộ kế hoạch xuất bán ra Excel, gồm cả trường ẩn để đối soát.
    `dest` có thể là đường dẫn file hoặc buffer (BytesIO)."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {', '.join(SALE_PLAN_ALL_COLUMNS)} FROM sale_plans "
            "WHERE status != 'deleted' ORDER BY planned_date ASC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError("Chưa có kế hoạch nào để xuất.")

    df = pd.DataFrame([dict(r) for r in rows])
    df["status"] = df["status"].map(lambda s: SALE_PLAN_STATUS_LABEL.get(s, s))
    df = df.rename(columns=SALE_PLAN_EXPORT_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Ke hoach xuat ban")
        ws = writer.sheets["Ke hoach xuat ban"]
        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = max(
                len(str(col_name)),
                int(df.iloc[:, col_idx - 1].fillna("").astype(str).str.len().max()) if len(df) else 0,
            )
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 45)
        ws.freeze_panes = "A2"

    return len(df)
